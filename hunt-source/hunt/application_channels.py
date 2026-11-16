"""Channel routing, public-link binding and checksum-bound Gmail submission."""
import copy,hashlib,json,os,re,shutil,sqlite3,datetime
from pathlib import Path
from urllib.parse import urlsplit,urlencode
from urllib.request import Request,urlopen
from email.message import EmailMessage
import base64
from application_runner import HUNTConnection,ProductionLeverAdapter,validate_context
from breezy_runner import ProductionBreezyAdapter

ACCOUNT='majekadegbeaminat85@gmail.com'
def daily_submission_count(root):
    now=datetime.datetime.now(datetime.timezone.utc);wat=now+datetime.timedelta(hours=1);start=wat.replace(hour=0,minute=0,second=0,microsecond=0)-datetime.timedelta(hours=1)
    file=Path(root)/'data/application-runner.sqlite3'
    if not file.exists():return 0
    with sqlite3.connect('file:'+str(file)+'?mode=ro',uri=True) as c:
        return c.execute("SELECT COUNT(*) FROM application_execution_events WHERE kind='final_submission_started' AND at>=?",(start.isoformat(),)).fetchone()[0]
def public_url(value):
    u=urlsplit(value)
    if u.scheme!='https' or u.username or u.password or u.port or not u.hostname or '.' not in u.hostname or re.match(r'^(?:localhost|0\.|127\.|10\.|192\.168\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.)',u.hostname) or u.hostname.endswith(('.local','.internal')):raise ValueError('Public HTTPS application URL required')
    return value

class RoutedConnection(HUNTConnection):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.bindings={}
    def bind(self,job_id,url):self.bindings[job_id]=public_url(url)
    def checkpoint(self,payload):
        from standing_authorization import read_authorization
        policy=read_authorization(self.root/'data')
        approved=policy.get('sending_enabled') is True and any(d.get('job_id')==payload['job_id'] and str(d.get('url','')).split('?')[0].rstrip('/').removesuffix('/apply')==payload['application_url'].split('?')[0].rstrip('/').removesuffix('/apply') for d in policy.get('approved_destinations',[]))
        if not approved or daily_submission_count(self.root)>=policy.get('daily_application_limit',5):raise ValueError('Destination authorization or daily submission bound prevents sending')
        current=self.context(payload['job_id'],payload['package_id']);url=self.bindings.get(payload['job_id'])
        if not url or payload['application_url'].rstrip('/').removesuffix('/apply')!=url.rstrip('/').removesuffix('/apply'):raise ValueError('Application route is not bound to this live job')
        current=copy.deepcopy(current);current['job']['application_url']=url;validate_context(current,payload,url_validator=public_url)

class HTMLAdapter(ProductionLeverAdapter):
    browser_script_name='universal_browser.mjs'
    def __init__(self,url,evidence_dir):
        self.url=public_url(url);self.node=shutil.which('node') or '/Users/theoneglobal/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node';self.evidence_dir=Path(evidence_dir);self.process=None
    def resolve(self):return self._call('route')
    def preflight(self,payload):
        if payload['form'].get('fixture_only') or payload['form'].get('provider')!='html' or payload['application_url']!=self.url:raise ValueError('Exact real HTML form required')

def form_adapter(route,evidence):
    if route['provider']=='lever':return ProductionLeverAdapter(route['url'],evidence_dir=evidence)
    if route['provider']=='breezy':
        os.environ['HUNT_BREEZY_QUESTIONNAIRE']='1'
        return ProductionBreezyAdapter(route['url'],evidence_dir=evidence)
    return HTMLAdapter(route['url'],evidence)

class EmailAdapter:
    def __init__(self,root,route,company,role,summary):
        self.root=Path(root);self.route=route;self.token=None
        recipient=route['recipient']
        if route.get('recipient_verified') is not True or not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+',recipient):raise ValueError('Posting-specified application recipient required')
        subject=re.sub(r'[\r\n]',' ',role+' application — Majekadegbe Aminat Bamitale')[:240]
        body='For your '+role+' opening at '+company+', I bring the following background:\n\n'+summary+'\n\nMy complete CV is attached. I am based in Lagos, Nigeria.\n\nKind regards,\nMajekadegbe Aminat Bamitale'
        self.form={'provider':'email','url':route['url'],'action_url':route['url'],'questions':[{'id':'resume','label':'Resume/CV','type':'file','required':True}], 'delivery':{'from':ACCOUNT,'recipient':recipient,'recipient_source':route['recipient_source'],'subject':subject,'body':body}}
    def inspect(self,payload=None):return self.form
    def preflight(self,payload):
        if payload['form']!=self.form:raise ValueError('Email recipient or content changed')
        file=self.root/'data/application-google.json'
        if file.stat().st_mode&0o077:raise ValueError('Email grant must remain private')
        grant=json.loads(file.read_text())
        if grant.get('account')!=ACCOUNT or 'https://www.googleapis.com/auth/gmail.send' not in grant.get('scopes',[]):raise ValueError('Owner Gmail send grant required')
        body=urlencode({k:grant[k] for k in ('client_id','client_secret','refresh_token')}|{'grant_type':'refresh_token'}).encode()
        from application_runner import NoRedirect
        from urllib.request import build_opener
        self.opener=build_opener(NoRedirect)
        with self.opener.open(Request('https://oauth2.googleapis.com/token',data=body),timeout=25) as r:self.token=json.load(r)['access_token']
    def fill(self,payload):return {'answers':{},'uploads':{k:v['sha256'] for k,v in payload['uploads'].items()}}
    def submit(self,payload,ident):
        if not self.token:raise ValueError('Email preflight required')
        delivery=payload['form']['delivery'];msg=EmailMessage();msg['From']=ACCOUNT;msg['To']=delivery['recipient'];msg['Subject']=delivery['subject'];msg['Message-ID']=f'<hunt-{ident}@local.hunt>';msg.set_content(delivery['body'])
        for file in payload['uploads'].values():
            data=Path(file['path']).read_bytes()
            if hashlib.sha256(data).hexdigest()!=file['sha256']:raise ValueError('CV changed before email send')
            msg.add_attachment(data,maintype='application',subtype='pdf',filename=file['name'])
        request=Request('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',data=json.dumps({'raw':base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip('=')}).encode(),headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        with self.opener.open(request,timeout=30) as r:receipt=json.load(r)
        if not receipt.get('id') or not receipt.get('threadId'):raise RuntimeError('No confirmed Gmail send receipt')
        return {'submitted':True,'channel':'email','confirmation_id':'gmail-'+receipt['id'],'gmail_message_id':receipt['id'],'gmail_thread_id':receipt['threadId'],'recipient':delivery['recipient'],'sender':ACCOUNT,'evidence_kind':'provider_receipt','evidence_url':'https://mail.google.com/mail/u/'+ACCOUNT+'/#sent/'+receipt['threadId'],'confirmation_text':'Gmail accepted the application email; employer acknowledgement pending.'}
    def close(self):pass
