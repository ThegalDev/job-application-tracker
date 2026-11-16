"""Recruiting evidence association, resumable scans and local-only transitions."""
import base64
import datetime as dt
import html
import json
import re
from email.utils import parseaddr
from html.parser import HTMLParser
from urllib.parse import quote
from email_classification import classify_message, CLASSIFIER_VERSION

UTC=dt.timezone.utc
SCAN_VERSION='recruiting-scope-v3'
ATS_DOMAINS={'ashbyhq.com','greenhouse-mail.io','greenhouse.io','greenhousesoftware.com',
             'lever.co','workablemail.com','workable.com','recruitee.com','teamtailor.com',
             'smartrecruiters.com','bamboohr.com','pinpointhq.com','jobs.lever.co'}

def install(c):
    c.execute('''CREATE TABLE IF NOT EXISTS recruiting_message_links(
      message_id TEXT PRIMARY KEY,thread_id TEXT,application_id TEXT,sender_domain TEXT,
      provenance TEXT,association TEXT,classifier_version TEXT,at TEXT,decision_hash TEXT)''')

def timestamp(value):
    if not isinstance(value,str):raise ValueError('Recruiting event requires a timestamp')
    parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)

class _HTMLText(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        if tag in ('br','p','div','li','tr','h1','h2','h3'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
    def handle_data(self,text):
        if not self.skip:self.parts.append(text)

def mail_text(part,depth=0):
    """Prefer plain text, fall back to HTML, and never ingest attachments."""
    if depth>10 or not isinstance(part,dict) or part.get('filename'):return ''
    kind=part.get('mimeType','')
    if kind in ('text/plain','text/html'):
        data=part.get('body',{}).get('data','')
        if not isinstance(data,str):return ''
        try:text=base64.urlsafe_b64decode(data+'='*((-len(data))%4)).decode('utf-8','replace')[:60000]
        except (ValueError,TypeError):return ''
        if kind=='text/html':
            parser=_HTMLText();parser.feed(text);text=html.unescape(''.join(parser.parts))
        return text.strip()
    children=part.get('parts',[])[:20]
    if kind=='multipart/alternative':
        plain=[mail_text(x,depth+1) for x in children if x.get('mimeType')=='text/plain']
        if any(plain):return '\n'.join(x for x in plain if x)[:60000]
    return '\n'.join(x for child in children if (x:=mail_text(child,depth+1)))[:60000]

def headers_of(message):
    result={}
    for item in message.get('payload',{}).get('headers',[]):
        key=item.get('name','').lower();value=item.get('value','')
        if isinstance(value,str):result[key]=result.get(key,'')+'\n'+value
    return {k:v.strip() for k,v in result.items()}

def _domain(sender):return parseaddr(sender)[1].lower().rsplit('@',1)[-1]
def _within(domain,base):return domain==base or domain.endswith('.'+base)
def _evidence_ids(application):
    return set(re.findall(r'#(?:all|inbox|sent)/([A-Za-z0-9_-]+)',application.get('evidence') or ''))
def _contains(needle,text):return bool(needle) and (' '+needle+' ') in (' '+text+' ')

def authenticated_sender(headers,domain):
    value=headers.get('authentication-results','')+';'+headers.get('arc-authentication-results','')
    for match in re.finditer(r'(?:dmarc|dkim)=pass[^;\n]*(?:header\.from|header\.i|header\.d)=@?([A-Za-z0-9.-]+)',value,re.I):
        signed=match[1].lower()
        if _within(domain,signed) or _within(signed,domain):return True
    return False

def normalize_message(hunt,message,applications,account,verified_domains=None):
    hdr=headers_of(message);sender=_domain(hdr.get('from',''));content=mail_text(message.get('payload',{}))
    text=hdr.get('subject','')+'\n'+content;identity=hunt.norm(text);subject=hunt.norm(hdr.get('subject',''))
    # Common employer names such as "Move" also occur in rejection verbs.
    # Prefer explicit employer names in subject/sender over incidental body words.
    header_identity=hunt.norm(hdr.get('subject','')+' '+hdr.get('from',''))
    header_candidates=[a for a in applications if _contains(hunt.norm(a['company']),header_identity)]
    candidates=header_candidates or [a for a in applications if _contains(hunt.norm(a['company']),identity)]
    anchors=[a for a in applications if message.get('id') in _evidence_ids(a)]
    exact=[a for a in candidates if _contains(hunt.norm(a['role']),identity)]
    selected=anchors[0] if len(anchors)==1 else exact[0] if len(exact)==1 else candidates[0] if len(candidates)==1 else None
    reason='Existing application evidence message' if len(anchors)==1 else 'Exact company and role in recruiting message' if len(exact)==1 else 'Only tracked application for explicitly named employer' if len(candidates)==1 else 'Ambiguous or absent employer/role association'
    trusted=False;provenance='unverified_sender'
    if selected:
        domains=(verified_domains or {}).get(hunt.norm(selected['company']),set())
        if message.get('id') in _evidence_ids(selected):trusted=True;provenance='existing_application_evidence'
        elif authenticated_sender(hdr,sender):
            if any(_within(sender,x) for x in domains):trusted=True;provenance='authenticated_verified_employer'
            elif any(_within(sender,x) for x in ATS_DOMAINS):trusted=True;provenance='authenticated_ats_with_employer_association'
    try:at=dt.datetime.fromtimestamp(int(message['internalDate'])/1000,UTC).isoformat()
    except (KeyError,TypeError,ValueError,OverflowError):at=None;trusted=False;reason='Missing or invalid Gmail event timestamp'
    return {'id':message['id'],'thread_id':message.get('threadId'),'at':at,'account':account,
            'application_id':selected['id'] if selected and trusted else None,
            'company':selected['company'] if selected and trusted else '',
            'role':selected['role'] if selected and trusted else '',
            'body':text,'evidence':'https://mail.google.com/mail/u/?authuser='+quote(account,safe='')+'#all/'+message['id'],
            'association_verified':trusted,'association_reason':reason,'sender_domain':sender,'provenance':provenance,'source':'gmail_runtime'}

def scan_state(hunt,applications,at=None):
    at=at or dt.datetime.now(UTC)
    with hunt.db() as c:
        state=hunt.value(c,'google_runtime_scan_v3')
        if state and state.get('scope_version')==SCAN_VERSION:return state
        completed=hunt.value(c,'google_runtime_completed_v3')
    dates=[]
    for app in applications:
        try:dates.append(timestamp(app.get('applied','')))
        except (ValueError,TypeError):pass
    start=timestamp(completed)-dt.timedelta(days=2) if completed else min(dates)-dt.timedelta(days=2) if dates else at-dt.timedelta(days=365)
    return {'scope_version':SCAN_VERSION,'after':int(start.timestamp()),'before':int(at.timestamp()),
            'page_token':None,'companies':sorted({a['company'] for a in applications if a.get('company')})[:100]}

def save_scan(hunt,state,response):
    with hunt.db() as c:
        if response.get('complete'):
            completed=dt.datetime.fromtimestamp(state['before'],UTC).isoformat()
            c.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',('google_runtime_completed_v3',hunt.dump(completed)))
            c.execute("DELETE FROM kv WHERE key='google_runtime_scan_v3'")
        else:
            state={**state,'page_token':response.get('next_page_token')}
            if not state['page_token']:raise ValueError('Incomplete Gmail scan requires continuation token')
            c.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',('google_runtime_scan_v3',hunt.dump(state)))

def preserve_newer_mail(c,application_id,status,latest,evidence):
    """A stale tracker copy cannot erase a newer verified local mail decision."""
    install(c)
    row=c.execute('''SELECT e.status,e.at,e.evidence FROM recruiting_message_links l
      JOIN mail_events e ON e.id=l.message_id WHERE l.application_id=? AND l.association='applied'
      ORDER BY e.at DESC LIMIT 1''',(application_id,)).fetchone()
    if not row:return status,latest,evidence
    try:incoming=timestamp(latest)
    except (ValueError,TypeError):incoming=dt.datetime.min.replace(tzinfo=UTC)
    if timestamp(row['at'])>=incoming:return row['status'],row['at'],row['evidence']
    return status,latest,evidence

def reconcile_messages(hunt,messages):
    """Versioned, evidence-backed local reconciliation; never writes a Sheet."""
    results=[]
    with hunt.db() as c:
        install(c)
        if hunt.value(c,'paused'):raise ValueError('HUNT is paused')
        account=hunt.value(c,'email')
        for message in messages:
            classification=classify_message(message.get('body',''));status=classification['status']
            runtime=message.get('source')=='gmail_runtime'
            if runtime and message.get('account')!=account:raise ValueError('Gmail event account mismatch')
            valid_source=not runtime or (message.get('account')==account and message.get('association_verified') is True)
            matches=[a for a in c.execute('SELECT * FROM applications')
                     if (message.get('application_id') and a['id']==message['application_id'])
                     or (not message.get('application_id') and hunt.norm(a['company'])==hunt.norm(message.get('company',''))
                         and hunt.norm(a['role'])==hunt.norm(message.get('role','')))]
            chosen=matches[0] if len(matches)==1 and valid_source else None
            key=hunt.digest([CLASSIFIER_VERSION,status,chosen['id'] if chosen else None,classification['requires_review'],message.get('association_verified')])
            old=c.execute('SELECT * FROM recruiting_message_links WHERE message_id=?',(message['id'],)).fetchone()
            if old and old['association']=='applied' and chosen is None:
                results.append({'id':message['id'],'result':'Verified evidence retained; new association requires review'});continue
            if old and old['decision_hash']==key:
                results.append({'id':message['id'],'result':'duplicate'});continue
            disposition='Needs review: '+message.get('association_reason','ambiguous company/role association')
            try:at=timestamp(message.get('at'))
            except (ValueError,TypeError):at=None;disposition='Needs review: invalid event timestamp'
            if chosen and at and not classification['requires_review']:
                try:latest=timestamp(chosen['latest'] or chosen['applied'])
                except (ValueError,TypeError):latest=dt.datetime.min.replace(tzinfo=UTC)
                previous=c.execute('SELECT MAX(at) FROM recruiting_message_links WHERE application_id=? AND association=?',(chosen['id'],'applied')).fetchone()[0]
                if previous:
                    try:latest=max(latest,timestamp(previous))
                    except ValueError:pass
                terminal=chosen['status'] in ('Rejected','Withdrawn','Offer received','Hired','Closed')
                regression=terminal and status in ('Application acknowledged','Assessment / next step')
                if at>=latest and not regression:
                    c.execute('UPDATE applications SET status=?,latest=?,evidence=? WHERE id=?',(status,at.isoformat(),message['evidence'],chosen['id']))
                    disposition='Applied locally; external tracker unchanged'
                    hunt.audit(c,'mail_status_reconciled',{'application':chosen['id'],'message_id':message['id'],'before':chosen['status'],'after':status,'classifier_version':CLASSIFIER_VERSION})
                else:disposition='Historical evidence retained; current status not regressed'
            at_text=at.isoformat() if at else message.get('at') or hunt.now()
            c.execute('INSERT OR REPLACE INTO mail_events VALUES(?,?,?,?,?,?,?)',(message['id'],at_text,chosen['company'] if chosen else message.get('company',''),chosen['role'] if chosen else message.get('role',''),status,message.get('evidence',''),disposition))
            association='applied' if disposition.startswith('Applied locally') else 'review'
            c.execute('INSERT OR REPLACE INTO recruiting_message_links VALUES(?,?,?,?,?,?,?,?,?)',(message['id'],message.get('thread_id'),chosen['id'] if chosen else None,message.get('sender_domain'),message.get('provenance','authorized_connector_bridge'),association,CLASSIFIER_VERSION,at_text,key))
            hunt.audit(c,'mail_event_imported',{'id':message['id'],'status':status,'disposition':disposition,'classifier_version':CLASSIFIER_VERSION})
            results.append({'id':message['id'],'result':disposition,'status':status})
    return results
