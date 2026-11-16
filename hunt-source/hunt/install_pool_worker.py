"""Activate the owner-requested all-pool worker using existing private grants."""
import argparse,hashlib,json,os,plistlib,shutil,subprocess,tempfile
from pathlib import Path
from standing_authorization import read_authorization,save_authorization
FILES=['pool_worker.py','mac_application_worker.py','application_runner.py','application_execution.py','standing_authorization.py','native_google_cv.py','application_channels.py','autonomous_answers.py','breezy_runner.py','breezy_browser.mjs','employer_browser.mjs','universal_browser.mjs']
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--inspect-only',action='store_true');args=parser.parse_args()
 source=Path(__file__).resolve().parent;target=Path.home()/'Library/Application Support/HUNT/application-worker';data=target/'data';agent=Path.home()/'Library/LaunchAgents/com.hunt.application-worker.plist';service='gui/'+str(os.getuid())+'/com.hunt.application-worker'
 previous=read_authorization(data)
 if previous.get('selection_mode')!='apply_available':raise ValueError('Owner available-role policy must already be active')
 batch_path=source/'data/application-worker-approved-batch.json'
 batch=json.loads(batch_path.read_text()) if batch_path.exists() else {}
 approved=batch.get('destinations',[]) if batch.get('owner_approved') is True and not args.inspect_only else []
 grant=source/'data/notification-google.json'
 if approved:
  g=json.loads(grant.read_text())
  if g.get('account')!='majekadegbeaminat85@gmail.com' or 'https://www.googleapis.com/auth/gmail.send' not in g.get('scopes',[]):raise ValueError('Existing owner send grant is required')
 subprocess.run(['launchctl','bootout',service],capture_output=True)
 if subprocess.run(['launchctl','print',service],capture_output=True).returncode==0:raise RuntimeError('Existing worker is still active')
 backup=Path(tempfile.mkdtemp(prefix='all-pool-backup-',dir=target));shutil.copy2(agent,backup/'agent.plist');shutil.copy2(data/'standing-application-authorization.json',backup/'policy.json')
 for name in FILES:
  if (target/name).exists():shutil.copy2(target/name,backup/name)
 for name in FILES:
  shutil.copy2(source/name,target/name)
  if hashlib.sha256((source/name).read_bytes()).digest()!=hashlib.sha256((target/name).read_bytes()).digest():raise RuntimeError('Runtime parity failed')
 if approved:
  shutil.copy2(grant,data/'application-google.json');(data/'application-google.json').chmod(0o600)
 from native_google_cv import private_json
 profile=json.loads((data/'owner-application-profile.json').read_text());facts=json.loads((source/'data/second-test-owner-answers.json').read_text())
 if facts.get('source')!='owner_explicit_statement':raise ValueError('Explicit owner answer provenance required')
 private_json(data/'application-answer-profile.json',{'current_location':profile['current_location'],'us_work_authorized':facts['us_work_authorized'],'us_visa_sponsorship':facts['us_visa_sponsorship'],'source':'owner_explicit_statements','narrative_policy':'source_grounded; unresolved facts are reported per job without stopping the pool'})
 save_authorization(data,'Owner explicitly authorized all unhidden unapplied jobs across employer forms and email in this conversation',True,selection_mode='apply_available',providers=['lever','breezy','html','email'],approved_destinations=approved,daily_application_limit=5)
 config=plistlib.loads(agent.read_bytes());config['ProgramArguments'][1]=str(target/'pool_worker.py');agent.write_bytes(plistlib.dumps(config));agent.chmod(0o600)
 subprocess.run(['launchctl','bootstrap','gui/'+str(os.getuid()),str(agent)],capture_output=True,check=True)
 print('Activated full-pool inspection only; sending is disabled until a bounded destination batch is approved.' if not approved else 'Activated the approved destination batch with a five-per-day submission limit.')
