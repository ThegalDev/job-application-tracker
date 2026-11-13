"""Version-bound outbound intent ledger. No network calls occur on approval."""
import datetime as dt, hashlib, json, re, secrets

def stamp():return dt.datetime.now(dt.timezone.utc).isoformat()
def encode(x):return json.dumps(x,sort_keys=True,ensure_ascii=False)
def fingerprint(x):return hashlib.sha256(encode(x).encode()).hexdigest()

def install(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS outbound_actions(id TEXT PRIMARY KEY,kind TEXT,payload TEXT,payload_hash TEXT,status TEXT,created TEXT,approved TEXT,expires TEXT,actor TEXT,receipt TEXT,error TEXT);
    CREATE UNIQUE INDEX IF NOT EXISTS outbound_identity ON outbound_actions(kind,payload_hash);
    CREATE TABLE IF NOT EXISTS outbound_events(id INTEGER PRIMARY KEY,action_id TEXT,at TEXT,event TEXT,details TEXT);
    ''')

def event(c,ident,kind,details):c.execute('INSERT INTO outbound_events(action_id,at,event,details) VALUES(?,?,?,?)',(ident,stamp(),kind,encode(details)))

def propose(c,payload):
    if not isinstance(payload,dict) or payload.get('kind') not in ('email','application','calendar','withdrawal'):raise ValueError('Unsupported action')
    kind=payload['kind']
    if kind=='email':
        recipient=payload.get('recipient','')
        if not isinstance(recipient,str) or not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+',recipient):raise ValueError('One verified recipient is required')
        if not payload.get('recipient_source') or payload.get('recipient_verified') is not True:raise ValueError('Recipient evidence is required')
        if not payload.get('subject') or not payload.get('body') or '\n' in payload['subject'] or '\r' in payload['subject']:raise ValueError('Invalid final message')
        if payload.get('attachments'):raise ValueError('Attachments require a separate sensitive-document approval workflow')
    if not payload.get('job_id') or not payload.get('job_version'):raise ValueError('Job identity and version required')
    digest=fingerprint(payload);ident=digest[:32]
    old=c.execute('SELECT * FROM outbound_actions WHERE kind=? AND payload_hash=?',(kind,digest)).fetchone()
    if old:return dict(old)
    c.execute('INSERT INTO outbound_actions VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ident,kind,encode(payload),digest,'review',stamp(),None,None,None,None,None))
    event(c,ident,'proposed',{'payload_hash':digest})
    return dict(c.execute('SELECT * FROM outbound_actions WHERE id=?',(ident,)).fetchone())

def decide(c,ident,expected_hash,decision,actor):
    row=c.execute('SELECT * FROM outbound_actions WHERE id=?',(ident,)).fetchone()
    if not row or row['payload_hash']!=expected_hash or fingerprint(json.loads(row['payload']))!=expected_hash:raise ValueError('Action version changed')
    if row['status']!='review':raise ValueError('Only a pending exact action may be reviewed')
    if decision not in ('approve','reject') or not actor:raise ValueError('Explicit authenticated review required')
    expires=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=24)).isoformat()
    status='approved' if decision=='approve' else 'rejected'
    c.execute('UPDATE outbound_actions SET status=?,approved=?,expires=?,actor=? WHERE id=?',(status,stamp(),expires,actor,ident))
    event(c,ident,'reviewed',{'decision':decision,'payload_hash':expected_hash,'actor':actor,'expires':expires})
    return {'id':ident,'status':status,'sent':False}

def execute(db_factory,ident,provider,checkpoint):
    """Provider must return a receipt; uncertain calls are never replayed."""
    checkpoint()
    with db_factory() as c:
        row=c.execute('SELECT * FROM outbound_actions WHERE id=?',(ident,)).fetchone()
        if not row:raise ValueError('Unknown action')
        if row['status']=='sent':return {'status':'sent','receipt':json.loads(row['receipt']),'replayed':False}
        if row['status']!='approved':raise ValueError('Action lacks a current exact approval, or needs delivery reconciliation')
        payload=json.loads(row['payload'])
        if fingerprint(payload)!=row['payload_hash']:raise ValueError('Action content changed')
        if not row['expires'] or dt.datetime.fromisoformat(row['expires'])<=dt.datetime.now(dt.timezone.utc):raise ValueError('Approval expired')
        # No provider attempt begins if configured credentials/capability are absent.
        provider.preflight(payload)
        changed=c.execute("UPDATE outbound_actions SET status='executing' WHERE id=? AND status='approved'",(ident,)).rowcount
        if changed!=1:raise ValueError('Action already claimed')
        event(c,ident,'execution_claimed',{'payload_hash':row['payload_hash']})
    try:
        checkpoint();receipt=provider.send(payload,ident)
        if not isinstance(receipt,dict) or not receipt.get('id'):raise RuntimeError('Provider did not return a confirmation receipt')
    except Exception as error:
        with db_factory() as c:
            c.execute("UPDATE outbound_actions SET status='uncertain',error=? WHERE id=?",(type(error).__name__,ident))
            event(c,ident,'delivery_uncertain',{'error_type':type(error).__name__,'automatic_retry':False})
        raise RuntimeError('Delivery uncertain. Reconcile provider state before any retry.') from None
    with db_factory() as c:
        c.execute("UPDATE outbound_actions SET status='sent',receipt=? WHERE id=?",(encode(receipt),ident));event(c,ident,'confirmed',{'receipt_id':receipt['id']})
    return {'status':'sent','receipt':receipt,'replayed':False}
