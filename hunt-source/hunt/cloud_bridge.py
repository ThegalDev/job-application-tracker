"""Owner-private Sites synchronization. Credentials arrive only over hidden stdin.

Run with --once for bounded scheduled work, or --watch for the local phone
command runner. No key is written to disk, printed or accepted in CLI args.
"""
import argparse,json,sys,time
from urllib.parse import urlsplit
from urllib.request import Request,build_opener
from urllib.error import HTTPError
import hunt,services

class PrivateBridge:
    def __init__(self,url,token):
        p=urlsplit(url)
        if p.scheme!='https' or not p.hostname or not p.hostname.endswith('.chatgpt.site') or p.path not in ('','/') or p.username or p.password or p.port not in (None,443):raise ValueError('Use the verified private Site origin')
        if not token:raise ValueError('Private Site service access required')
        self.url=url.rstrip('/');self.token=token;self.last_digest=None
    def request(self,path,body=None):
        if path not in ('/api/bridge/state','/api/bridge/snapshot','/api/bridge/commands','/api/bridge/ack'):raise ValueError('Bridge action denied')
        req=Request(self.url+path,data=hunt.dump(body).encode() if body is not None else None,headers={'OAI-Sites-Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        try:
            with build_opener(hunt.NoRedirect).open(req,timeout=45) as r:return json.load(r)
        except HTTPError as e:raise RuntimeError('Private Site HTTP '+str(e.code)) from None
    def sync(self,process=True):
        remote=self.request('/api/bridge/state');control=remote.get('control',{})
        if isinstance(control.get('paused'),bool):
            with hunt.db() as c:
                applied=hunt.value(c,'cloud_control_at','')
                if control.get('updated_at','')>applied:
                    c.execute("UPDATE kv SET value=? WHERE key='paused'",(hunt.dump(control['paused']),))
                    c.execute("INSERT OR REPLACE INTO kv VALUES('cloud_control_at',?)",(hunt.dump(control['updated_at']),))
                    hunt.audit(c,'cloud_pause_applied',{'paused':control['paused'],'updated_at':control['updated_at']})
        results=[]
        if process:
            for command in self.request('/api/bridge/commands').get('commands',[])[:20]:
                ident=command['id'];kind=command['type'];p=command['payload']
                try:
                    with hunt.db() as c:
                        if hunt.value(c,'paused') and kind!='pause':continue
                    if kind=='pause':result={'paused':p['paused'],'external_actions':0}
                    elif kind in ('run','discover'):
                        r=services.run_pipeline(hunt,p.get('trigger','discovery'),p.get('use_ai',True),idempotency_key='phone:'+ident)
                        result={'run_id':r['id'],'status':r['status'],'external_actions':0}
                    elif kind=='report':
                        r=services.make_report(hunt,p['period']);result={'report_id':r['id'],'period':r['period']}
                    elif kind=='package':
                        with hunt.db() as c:
                            job=c.execute('SELECT * FROM jobs WHERE id=?',(p['job_id'],)).fetchone()
                            if not job or job['raw_hash']!=p['job_version']:raise ValueError('Posting changed since phone review')
                            old=c.execute("SELECT id FROM packages WHERE job_id=? AND status='review' ORDER BY at DESC LIMIT 1",(p['job_id'],)).fetchone()
                        r={'id':old['id']} if old else hunt.package(p['job_id'],p.get('use_ai',True));result={'package_id':r['id'],'external_actions':0}
                    elif kind=='review':
                        with hunt.db() as c:
                            package=c.execute('SELECT * FROM packages WHERE id=?',(p['package_id'],)).fetchone()
                            if not package or package['hash']!=p['payload_hash'] or json.loads(package['payload']).get('job_version')!=p['job_version']:raise ValueError('Draft changed since phone approval')
                        result=hunt.approve(p['package_id'],p['decision'])
                    else:raise ValueError('Unsupported phone action; sending/submission is unavailable')
                    with hunt.db() as c:hunt.audit(c,'phone_command_processed',{'command_id':ident,'type':kind,'result':result})
                    status='blocked' if result.get('status')=='blocked' else 'completed'
                    self.request('/api/bridge/ack',{'id':ident,'status':status,'result':result});results.append({'id':ident,'status':status})
                except Exception as error:
                    self.request('/api/bridge/ack',{'id':ident,'status':'blocked','result':{'error_type':type(error).__name__,'message':str(error)[:180],'external_actions':0}})
                    results.append({'id':ident,'status':'blocked','error_type':type(error).__name__})
        snapshot=hunt.snapshot()
        # Earlier superseded drafts included a near-complete source CV appendix;
        # retain those locally, outside the approved current-draft cloud scope.
        snapshot['packages']=[{k:v for k,v in p.items() if k!='resume_full'} for p in snapshot['packages'] if p['status']!='superseded']
        for package in snapshot['packages']:
            package['full_cv_location']='Preserved in the private local workspace; full CV upload not authorized.'
        stable=hunt.digest({k:v for k,v in snapshot.items() if k!='at'})
        if self.last_digest==stable and not results:return {'status':'idle','snapshot_at':remote.get('snapshot_at'),'commands':[],'readback_verified':True}
        saved=self.request('/api/bridge/snapshot',{'snapshot':snapshot});verified=self.request('/api/bridge/state')
        if verified.get('snapshot_at')!=snapshot['at'] or verified.get('counts',{}).get('applications')!=len(snapshot['applications']):raise RuntimeError('Hosted snapshot read-back mismatch')
        self.last_digest=stable
        return {'status':'success','snapshot_at':snapshot['at'],'applications':len(snapshot['applications']),'jobs':len(snapshot['jobs']),'commands':results,'readback_verified':True}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');parser.add_argument('--watch',action='store_true');parser.add_argument('--sync-only',action='store_true');args=parser.parse_args()
    hunt.init();print('Ready for private bridge JSON on stdin (input is hidden).',flush=True)
    original=None
    if sys.stdin.isatty():
        import termios
        original=termios.tcgetattr(sys.stdin);hidden=original.copy();hidden[3]&=~termios.ECHO;termios.tcsetattr(sys.stdin,termios.TCSANOW,hidden)
    try:config=json.loads(sys.stdin.readline())
    finally:
        if original is not None:termios.tcsetattr(sys.stdin,termios.TCSANOW,original)
    bridge=PrivateBridge(config['url'],config['token']);config.clear()
    if not args.watch:print(hunt.dump(bridge.sync(not args.sync_only)));return
    print('HUNT phone command runner active; no employer sending/submission capability.',flush=True)
    while True:
        try:
            r=bridge.sync();print(hunt.dump(r),flush=True)
        except Exception as error:
            with hunt.db() as c:hunt.audit(c,'cloud_bridge_error',{'error_type':type(error).__name__})
            print(hunt.dump({'status':'error','error_type':type(error).__name__}),flush=True)
        time.sleep(60)

if __name__=='__main__':main()
