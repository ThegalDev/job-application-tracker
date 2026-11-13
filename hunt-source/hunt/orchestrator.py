"""Persistent, bounded orchestration for HUNT's six cooperating roles.

Tools are injected application capabilities, never instructions found in a posting.
No outbound capability is exposed to these agents. Tool identities survive retries.
Network adapters must enforce their own transport timeout and call checkpoint before
side effects; Python cannot forcibly cancel a network call in another library.
"""
import datetime as dt
import hashlib
import json
import math
import secrets
import threading
import time
from dataclasses import dataclass

UTC=dt.timezone.utc
ROLE_TOOLS={
    'discovery':('discover_jobs',),
    'match_intelligence':('match_jobs',),
    'company_research':('research_companies',),
    'application_studio':('prepare_applications',),
    'outreach':('prepare_outreach',),
    'pipeline_intelligence':('reconcile_pipeline',),
}
ROLE_DEPENDENCIES={
    'discovery':(), 'match_intelligence':('discovery',),
    'company_research':('match_intelligence',),
    'application_studio':('company_research',),
    'outreach':('application_studio',),
    'pipeline_intelligence':(),
}
PLANS={
    'full':tuple(ROLE_TOOLS),
    'discovery':('discovery','match_intelligence'),
    'shortlist':('match_intelligence','company_research','application_studio','outreach'),
    'pipeline':('pipeline_intelligence',),
    'report':('pipeline_intelligence',),
}
MAX_ATTEMPTS=3
RUN_LOCK=threading.Lock()

def now():return dt.datetime.now(UTC).isoformat()
def dump(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False)
def identity(v):return hashlib.sha256(dump(v).encode()).hexdigest()[:32]

def install(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS agent_workflows(
      id TEXT PRIMARY KEY,idempotency_key TEXT UNIQUE NOT NULL,trigger TEXT NOT NULL,
      payload TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,
      max_calls INTEGER NOT NULL,max_seconds REAL NOT NULL,max_cost_usd REAL NOT NULL,
      calls INTEGER NOT NULL DEFAULT 0,cost_usd REAL NOT NULL DEFAULT 0,
      lease_owner TEXT,lease_until TEXT,error TEXT);
    CREATE TABLE IF NOT EXISTS agent_tasks(
      id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES agent_workflows(id),
      role TEXT NOT NULL,dependencies TEXT NOT NULL,status TEXT NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0,result TEXT,error TEXT,updated TEXT NOT NULL,
      UNIQUE(run_id,role));
    CREATE TABLE IF NOT EXISTS agent_tool_calls(
      id TEXT PRIMARY KEY,run_id TEXT NOT NULL,task_id TEXT NOT NULL,role TEXT NOT NULL,
      tool TEXT NOT NULL,attempt INTEGER NOT NULL,status TEXT NOT NULL,
      started TEXT NOT NULL,finished TEXT,result TEXT,error TEXT,cost_usd REAL NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS agent_events(
      seq INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,task_id TEXT,
      at TEXT NOT NULL,kind TEXT NOT NULL,details TEXT NOT NULL);
    ''')

def event(c,rid,kind,details=None,task_id=None):
    # Raw inputs, full candidate documents, mail bodies and credentials are not logged.
    c.execute('INSERT INTO agent_events(run_id,task_id,at,kind,details) VALUES(?,?,?,?,?)',(rid,task_id,now(),kind,dump(details or {})))

class Paused(Exception):pass
class BudgetExceeded(Exception):pass
class RetryableError(Exception):pass

@dataclass(frozen=True)
class ToolSpec:
    handler: object
    replay_safe: bool=True
    cost_upper_bound_usd: float=0.0

@dataclass
class ToolContext:
    run_id: str
    task_id: str
    role: str
    idempotency_key: str
    checkpoint: object
    dependencies: dict

class Orchestrator:
    def __init__(self,db_factory,tool_handlers):
        self.db=db_factory
        self.tools={k:(v if isinstance(v,ToolSpec) else ToolSpec(v,replay_safe=k!='prepare_applications')) for k,v in tool_handlers.items()}
        allowed={x for xs in ROLE_TOOLS.values() for x in xs}
        if set(self.tools)-allowed:raise ValueError('Tool outside the six-role capability allowlist')
        for spec in self.tools.values():
            if not callable(spec.handler) or not math.isfinite(spec.cost_upper_bound_usd) or spec.cost_upper_bound_usd<0:raise ValueError('Invalid tool specification')
        with self.db() as c:install(c)

    def enqueue(self,trigger='full',payload=None,idempotency_key=None,max_calls=24,max_seconds=300,max_cost_usd=1.0):
        if trigger not in PLANS:raise ValueError('Unknown workflow trigger')
        if type(max_calls) is not int or not 1<=max_calls<=100 or not 1<=max_seconds<=1800 or not 0<=max_cost_usd<=100:raise ValueError('Invalid execution budget')
        payload=payload or {}
        if not isinstance(payload,dict):raise ValueError('Workflow payload must be an object')
        if re_sensitive(payload):raise ValueError('Sensitive payload fields are prohibited; use persisted record IDs')
        encoded=dump(payload)
        if len(encoded)>100000:raise ValueError('Workflow payload too large; use persisted record IDs')
        key=idempotency_key or identity([trigger,payload,now(),secrets.token_hex(8)])
        if not isinstance(key,str) or not 1<=len(key)<=200:raise ValueError('Invalid workflow identity')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            prior=c.execute('SELECT id,trigger,payload FROM agent_workflows WHERE idempotency_key=?',(key,)).fetchone()
            if prior:
                if prior['trigger']!=trigger or prior['payload']!=encoded:raise ValueError('Idempotency key reused with different workflow')
                return prior['id']
            rid=identity(['workflow',key]);at=now()
            c.execute('INSERT INTO agent_workflows(id,idempotency_key,trigger,payload,status,created,updated,max_calls,max_seconds,max_cost_usd) VALUES(?,?,?,?,?,?,?,?,?,?)',(rid,key,trigger,encoded,'queued',at,at,max_calls,max_seconds,max_cost_usd))
            roles=PLANS[trigger]
            for role in roles:
                deps=[d for d in ROLE_DEPENDENCIES[role] if d in roles]
                tid=identity([rid,role])
                c.execute('INSERT INTO agent_tasks(id,run_id,role,dependencies,status,updated) VALUES(?,?,?,?,?,?)',(tid,rid,role,dump(deps),'queued',at))
            event(c,rid,'workflow_queued',{'trigger':trigger,'roles':list(roles)})
        return rid

    def _checkpoint(self,rid,owner,deadline):
        with self.db() as c:
            paused=c.execute("SELECT value FROM kv WHERE key='paused'").fetchone()
            if paused and json.loads(paused[0]):raise Paused('All agents are paused')
            r=c.execute('SELECT status,lease_owner FROM agent_workflows WHERE id=?',(rid,)).fetchone()
            if not r or r['lease_owner']!=owner or r['status']!='running':raise Paused('Workflow no longer owns the execution lease')
        if time.monotonic()>deadline:raise BudgetExceeded('Workflow execution time budget reached')

    def _finish(self,rid,status,error=None,owner=None):
        with self.db() as c:
            changed=c.execute('UPDATE agent_workflows SET status=?,error=?,updated=?,lease_owner=NULL,lease_until=NULL WHERE id=? AND lease_owner=?',(status,error,now(),rid,owner)).rowcount
            if changed:event(c,rid,'workflow_'+status,{'reason':error} if error else {})

    def run(self,run_id):
        if not RUN_LOCK.acquire(blocking=False):raise ValueError('An agent workflow is already executing in this process')
        owner=secrets.token_hex(16)
        try:
            with self.db() as c:
                c.execute('BEGIN IMMEDIATE')
                r=c.execute('SELECT * FROM agent_workflows WHERE id=?',(run_id,)).fetchone()
                if not r:raise ValueError('Unknown workflow')
                if r['status']=='success':return self.state(run_id)
                if r['lease_until'] and r['lease_until']>now():raise ValueError('Workflow is already leased to a worker')
                deadline=time.monotonic()+r['max_seconds'];until=(dt.datetime.now(UTC)+dt.timedelta(seconds=r['max_seconds']+60)).isoformat()
                c.execute("UPDATE agent_workflows SET status='running',lease_owner=?,lease_until=?,updated=?,error=NULL WHERE id=?",(owner,until,now(),run_id))
                # Crashed successful tools are reused; unresolved non-replay-safe calls require review.
                stale=c.execute("SELECT * FROM agent_tasks WHERE run_id=? AND status='running'",(run_id,)).fetchall()
                for task in stale:
                    call=c.execute('SELECT * FROM agent_tool_calls WHERE task_id=? ORDER BY attempt DESC LIMIT 1',(task['id'],)).fetchone()
                    spec=self.tools.get(ROLE_TOOLS[task['role']][0])
                    if call and call['status']=='success':
                        c.execute("UPDATE agent_tasks SET status='success',result=?,updated=? WHERE id=?",(call['result'],now(),task['id']))
                    elif spec and spec.replay_safe:
                        c.execute("UPDATE agent_tasks SET status='queued',updated=? WHERE id=?",(now(),task['id']))
                    else:
                        c.execute("UPDATE agent_tasks SET status='uncertain',error='Interrupted tool execution needs review before replay',updated=? WHERE id=?",(now(),task['id']))
                event(c,run_id,'workflow_started')
            while True:
                try:self._checkpoint(run_id,owner,deadline)
                except Paused as exc:self._finish(run_id,'paused',str(exc),owner);break
                except BudgetExceeded as exc:self._finish(run_id,'budget_exceeded',str(exc),owner);break
                with self.db() as c:
                    tasks=[dict(x) for x in c.execute('SELECT * FROM agent_tasks WHERE run_id=? ORDER BY rowid',(run_id,))]
                successful={x['role']:json.loads(x['result'] or '{}') for x in tasks if x['status'] in ('success','partial')}
                ready=next((t for t in tasks if t['status']=='queued' and all(d in successful for d in json.loads(t['dependencies']))),None)
                if not ready:
                    status='success' if all(t['status']=='success' for t in tasks) else 'partial' if all(t['status'] in ('success','partial') for t in tasks) else 'blocked'
                    self._finish(run_id,status,owner=owner);break
                tool=ROLE_TOOLS[ready['role']][0];spec=self.tools.get(tool)
                if not spec:
                    with self.db() as c:
                        c.execute("UPDATE agent_tasks SET status='blocked',error=?,updated=? WHERE id=?",('Required tool is not connected: '+tool,now(),ready['id']))
                        event(c,run_id,'tool_unavailable',{'tool':tool},ready['id'])
                    continue
                try:self._execute(run_id,ready,tool,spec,owner,deadline,successful)
                except Paused as exc:self._finish(run_id,'paused',str(exc),owner);break
                except BudgetExceeded as exc:self._finish(run_id,'budget_exceeded',str(exc),owner);break
            return self.state(run_id)
        finally:RUN_LOCK.release()

    def _execute(self,rid,task,tool,spec,owner,deadline,dependencies):
        self._checkpoint(rid,owner,deadline)
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute('SELECT * FROM agent_workflows WHERE id=?',(rid,)).fetchone()
            if r['lease_owner']!=owner or r['status']!='running':raise Paused('Workflow execution lease changed')
            if r['calls']>=r['max_calls'] or r['cost_usd']+spec.cost_upper_bound_usd>r['max_cost_usd']:raise BudgetExceeded('Tool-call or reserved cost budget reached')
            if task['attempts']>=MAX_ATTEMPTS:
                c.execute("UPDATE agent_tasks SET status='failed',error='Maximum tool attempts reached',updated=? WHERE id=?",(now(),task['id']));return
            attempt=task['attempts']+1;call_id=identity([task['id'],tool,attempt]);action_id=identity([task['id'],tool])
            c.execute("UPDATE agent_workflows SET calls=calls+1,cost_usd=cost_usd+?,updated=? WHERE id=?",(spec.cost_upper_bound_usd,now(),rid))
            c.execute("UPDATE agent_tasks SET status='running',attempts=?,updated=? WHERE id=?",(attempt,now(),task['id']))
            c.execute('INSERT INTO agent_tool_calls(id,run_id,task_id,role,tool,attempt,status,started,cost_usd) VALUES(?,?,?,?,?,?,?,?,?)',(call_id,rid,task['id'],task['role'],tool,attempt,'running',now(),spec.cost_upper_bound_usd))
            event(c,rid,'tool_started',{'role':task['role'],'tool':tool,'attempt':attempt,'action_id':action_id},task['id'])
            payload=json.loads(r['payload'])
        ctx=ToolContext(rid,task['id'],task['role'],action_id,lambda:self._checkpoint(rid,owner,deadline),{d:dependencies[d] for d in json.loads(task['dependencies'])})
        try:
            result=spec.handler(ctx,payload)
            if not isinstance(result,dict) or result.get('status') not in ('success','partial','blocked'):raise ValueError('Tool result must declare success, partial or blocked')
            encoded=dump(result)
            if len(encoded)>500000:raise ValueError('Tool result too large; store record references')
            # Results must be internal record references and public research, not private raw mail or credentials.
            if re_sensitive(result):raise ValueError('Tool result contains a forbidden private or credential field')
            # A provider may complete while paused. Preserve receipt, then stop at next checkpoint.
            with self.db() as c:
                c.execute('UPDATE agent_tool_calls SET status=?,finished=?,result=? WHERE id=?',(result['status'],now(),encoded,call_id))
                lease=c.execute('SELECT lease_owner FROM agent_workflows WHERE id=?',(rid,)).fetchone()
                if lease and lease['lease_owner']==owner:
                    c.execute('UPDATE agent_tasks SET status=?,result=?,error=NULL,updated=? WHERE id=?',(result['status'],encoded,now(),task['id']))
                event(c,rid,'tool_completed',{'tool':tool,'status':result['status'],'attempt':attempt},task['id'])
        except (Paused,BudgetExceeded):
            with self.db() as c:
                status='queued' if spec.replay_safe else 'uncertain'
                lease=c.execute('SELECT lease_owner FROM agent_workflows WHERE id=?',(rid,)).fetchone()
                if lease and lease['lease_owner']==owner:
                    c.execute('UPDATE agent_tasks SET status=?,error=?,updated=? WHERE id=?',(status,'Stopped at tool checkpoint',now(),task['id']))
                c.execute("UPDATE agent_tool_calls SET status='interrupted',finished=? WHERE id=?",(now(),call_id))
            raise
        except Exception as exc:
            # Exception text may contain URLs, credentials, or model/provider echoes. Keep only type.
            retry=isinstance(exc,(RetryableError,TimeoutError,ConnectionError)) and spec.replay_safe and attempt<MAX_ATTEMPTS
            status='queued' if retry else 'failed'
            error=type(exc).__name__
            with self.db() as c:
                lease=c.execute('SELECT lease_owner FROM agent_workflows WHERE id=?',(rid,)).fetchone()
                if lease and lease['lease_owner']==owner:
                    c.execute('UPDATE agent_tasks SET status=?,error=?,updated=? WHERE id=?',(status,error,now(),task['id']))
                c.execute("UPDATE agent_tool_calls SET status='failed',finished=?,error=? WHERE id=?",(now(),error,call_id))
                event(c,rid,'tool_failed',{'tool':tool,'error_type':error,'retry_scheduled':retry},task['id'])

    def resume(self,run_id):
        with self.db() as c:
            r=c.execute('SELECT status,lease_until FROM agent_workflows WHERE id=?',(run_id,)).fetchone()
            if not r:raise ValueError('Unknown workflow')
            if r['lease_until'] and r['lease_until']>now():raise ValueError('Workflow is already leased to a worker')
            # Missing capabilities can be connected and retried explicitly. Failed/uncertain paid tools are not blindly replayed.
            c.execute("UPDATE agent_tasks SET status='queued',updated=? WHERE run_id=? AND status='blocked' AND attempts<?",(now(),run_id,MAX_ATTEMPTS))
            event(c,run_id,'resume_requested')
        return self.run(run_id)

    def state(self,run_id=None):
        with self.db() as c:
            if run_id:
                r=c.execute('SELECT * FROM agent_workflows WHERE id=?',(run_id,)).fetchone()
                if not r:raise ValueError('Unknown workflow')
                run=dict(r);run['payload']=json.loads(run['payload']);run.pop('lease_owner',None)
                run['tasks']=[{**dict(t),'dependencies':json.loads(t['dependencies']),'result':json.loads(t['result']) if t['result'] else None} for t in c.execute('SELECT * FROM agent_tasks WHERE run_id=? ORDER BY rowid',(run_id,))]
                run['tool_calls']=[{k:v for k,v in dict(t).items() if k!='result'} for t in c.execute('SELECT * FROM agent_tool_calls WHERE run_id=? ORDER BY started',(run_id,))]
                return run
            return {'roles':[{'id':role,'tools':list(names),'dependencies':list(ROLE_DEPENDENCIES[role])} for role,names in ROLE_TOOLS.items()],
                    'runs':[{k:v for k,v in dict(r).items() if k not in ('payload','lease_owner')} for r in c.execute('SELECT * FROM agent_workflows ORDER BY created DESC LIMIT 30')]}

def re_sensitive(value):
    if isinstance(value,dict):
        return any(str(k).lower() in {'api_key','authorization','access_token','refresh_token','password','raw_mail','mail_body','cv_text','contact_email'} or re_sensitive(v) for k,v in value.items())
    if isinstance(value,list):return any(re_sensitive(x) for x in value)
    if isinstance(value,str):return 'sk-proj-' in value or 'Bearer ' in value
    return False
