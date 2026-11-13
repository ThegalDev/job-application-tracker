"""Google API adapter using separately authorized runtime credentials.

No desktop connector credentials are copied. Missing setup is an explicit blocker.
Refresh credentials are loaded from a private file or runtime secret environment.
"""
import base64,datetime as dt,json,os,re
from pathlib import Path
from email.message import EmailMessage
from urllib.parse import urlencode,quote
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Google credential-bearing redirects are disabled')

def open_google(request,timeout):
    return build_opener(NoRedirect).open(request,timeout=timeout)

AUTHORIZED_TRACKER = "1H8Dgplggg8wkuNoK-lIVJ602AzQHjkXzpOVQ3ONgKeo"

class GoogleProvider:
    def __init__(self,expected_email):
        self.expected_email=expected_email;self._token=None;self.credentials={}
        path=Path(os.environ.get('HUNT_GOOGLE_OAUTH_FILE',str(Path(__file__).resolve().parents[2]/'work/google-oauth.json')))
        if path.is_file():
            if path.stat().st_mode&0o077:raise ValueError('Google credential file permissions are too broad')
            self.credentials=json.loads(path.read_text())
            if self.credentials.get('account','').lower()!=expected_email.lower():self.credentials={}
        for name,key in [('HUNT_GOOGLE_CLIENT_ID','client_id'),('HUNT_GOOGLE_CLIENT_SECRET','client_secret'),('HUNT_GOOGLE_REFRESH_TOKEN','refresh_token')]:
            if os.environ.get(name):self.credentials[key]=os.environ[name]
    def configured(self):return all(self.credentials.get(k) for k in ('client_id','client_secret','refresh_token'))
    def status(self):return {'configured':self.configured(),'mode':'standalone_oauth' if self.configured() else 'Codex connector bridge','blocker':None if self.configured() else 'Standalone Google OAuth client and user consent are not configured'}
    def token(self):
        if not self.configured():raise ValueError('Standalone Google OAuth is not configured; use the authorized Codex bridge')
        if self._token:return self._token
        data=urlencode({'client_id':self.credentials['client_id'],'client_secret':self.credentials['client_secret'],'refresh_token':self.credentials['refresh_token'],'grant_type':'refresh_token'}).encode()
        try:
            with open_google(Request('https://oauth2.googleapis.com/token',data=data,headers={'Content-Type':'application/x-www-form-urlencoded'}),timeout=30) as r:d=json.load(r)
        except Exception:raise RuntimeError('Google authorization refresh failed; reconnect required') from None
        self._token=d.get('access_token')
        if not self._token:raise RuntimeError('Google authorization returned no access token')
        return self._token
    def request(self,path,body=None,method=None):
        if not path.startswith(('https://gmail.googleapis.com/gmail/v1/users/me/','https://sheets.googleapis.com/v4/spreadsheets/')):raise ValueError('Google API target denied')
        req=Request(path,data=json.dumps(body).encode() if body is not None else None,headers={'Authorization':'Bearer '+self.token(),'Content-Type':'application/json'},method=method)
        try:
            with open_google(req,timeout=35) as r:return json.load(r)
        except HTTPError as e:
            self._token=None
            raise RuntimeError('Google API HTTP '+str(e.code)) from None
    def profile(self):
        p=self.request('https://gmail.googleapis.com/gmail/v1/users/me/profile')
        if p.get('emailAddress','').lower()!=self.expected_email.lower():raise ValueError('Google account does not match recruitment inbox')
        return p
    def recruiting_messages(self,after,max_pages=3,page_token=None,before=None,companies=None,checkpoint=None):
        """Read bounded recruiting pages; continuation always uses the same query.

        Date boundaries use epoch seconds, avoiding Gmail's date/Pacific-time
        interpretation. Callers persist the returned continuation before advancing
        the completed cursor. Metadata excludes bulk newsletters before bodies.
        """
        self.profile();result=[];page=page_token;skipped=0
        def epoch(value):
            if isinstance(value,(int,float)):return int(value)
            parsed=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
            if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=dt.timezone.utc)
            return int(parsed.timestamp())
        terms=['application','interview','assessment','offer','recruitment','recruiter','candidacy','candidature','"other candidates"','"not selected"','"hiring decision"']
        for company in (companies or [])[:100]:
            if isinstance(company,str) and company.strip():
                quoted=company.strip().replace('\\','\\\\').replace('"','\\"')[:100]
                terms.append('subject:"'+quoted+'"')
        query=f'after:{epoch(after)} '+(f'before:{epoch(before)} ' if before is not None else '')+'-in:spam -in:trash -in:sent -subject:"verification code" -subject:"one-time" {'+' '.join(terms)+'}'
        for _ in range(min(max_pages,3)):
            if checkpoint:checkpoint()
            params={'q':query,'maxResults':50}
            if page:params['pageToken']=page
            d=self.request('https://gmail.googleapis.com/gmail/v1/users/me/messages?'+urlencode(params))
            for x in d.get('messages',[]):
                if checkpoint:checkpoint()
                base='https://gmail.googleapis.com/gmail/v1/users/me/messages/'+quote(x['id'],safe='')
                meta=self.request(base+'?'+urlencode({'format':'metadata','metadataHeaders':['Subject','From','List-Id']},doseq=True))
                headers={h['name'].lower():h['value'] for h in meta.get('payload',{}).get('headers',[])}
                bulk=bool(headers.get('list-id')) or bool(re.search(r'newsletter|digest\.|jobalert\.|newsletter@',headers.get('from',''),re.I))
                bulk=bulk or bool(re.search(r'\b\d+ (?:more |new )?(?:remote )?(?:hr )?jobs\b|\bjob alerts?\b',headers.get('subject',''),re.I))
                if bulk:skipped+=1;continue
                result.append(self.request(base+'?format=full'))
            page=d.get('nextPageToken')
            if not page:break
        return {'messages':result,'next_page_token':page,'complete':not page,'bulk_messages_skipped':skipped,'account':self.expected_email}
    def check_tracker(self,sheet_id):
        if sheet_id != AUTHORIZED_TRACKER:raise ValueError('Only the explicitly authorized application tracker is accessible')
    def recruiting_messages_by_id(self,ids,checkpoint=None):
        if not isinstance(ids,list) or not 1<=len(ids)<=20 or any(not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',x) for x in ids):raise ValueError('Invalid bounded recruiting evidence IDs')
        self.profile();messages=[]
        for ident in dict.fromkeys(ids):
            if checkpoint:checkpoint()
            messages.append(self.request('https://gmail.googleapis.com/gmail/v1/users/me/messages/'+quote(ident,safe='')+'?format=full'))
        return {'messages':messages,'complete':True,'next_page_token':None,'account':self.expected_email,'mode':'targeted_evidence_repair'}
    def tracker(self,sheet_id):
        self.check_tracker(sheet_id)
        if not re.fullmatch(r'[A-Za-z0-9_-]{20,100}',sheet_id):raise ValueError('Invalid tracker identity')
        self.profile()
        return self.request('https://sheets.googleapis.com/v4/spreadsheets/'+sheet_id+'/values/'+quote('Applications!A1:J1000',safe=''))
    def compare_and_swap_row(self,sheet_id,row,expected,replacement):
        self.check_tracker(sheet_id)
        if not 2<=row<=1000 or len(replacement)!=10:raise ValueError('Invalid bounded tracker row')
        self.profile();url='https://sheets.googleapis.com/v4/spreadsheets/'+sheet_id+'/values/'+quote(f'Applications!A{row}:J{row}',safe='')
        actual=self.request(url).get('values',[[]])[0]
        if actual!=expected:raise ValueError('Tracker changed concurrently; reread and review before writing')
        # Google values writes are not an atomic CAS; do not advertise stronger consistency.
        result=self.request(url+'?valueInputOption=RAW',{'range':f'Applications!A{row}:J{row}','values':[replacement]},'PUT')
        check=self.request(url).get('values',[[]])[0]
        if check!=replacement:raise RuntimeError('Tracker write could not be verified')
        return {'verified':True,'updated_cells':result.get('updatedCells'),'concurrency':'read-compare-write-read; not provider-atomic'}
    def preflight(self,payload):
        if payload['kind']!='email':raise ValueError('This adapter only supports approved email; application/calendar adapters are unavailable')
        if not self.configured():raise ValueError('Gmail sending is not connected. No send attempted.')
        if os.environ.get('HUNT_ENABLE_GMAIL_SEND')!='1':raise ValueError('Gmail sending remains disabled until explicitly enabled')
        if self.credentials.get('scopes') and 'https://www.googleapis.com/auth/gmail.send' not in self.credentials['scopes']:raise ValueError('Gmail send permission has not been granted; no send attempted')
        self.profile()
    def send(self,payload,action_id):
        msg=EmailMessage();msg['From']=self.expected_email;msg['To']=payload['recipient'];msg['Subject']=payload['subject'];msg['Message-ID']=f'<hunt-{action_id}@local.hunt>';msg.set_content(payload['body'])
        raw=base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip('=')
        return self.request('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',{'raw':raw})
