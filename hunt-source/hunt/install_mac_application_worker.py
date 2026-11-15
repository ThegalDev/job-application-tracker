"""Install the authorized worker privately outside macOS-protected Documents."""
import json
import os
import plistlib
import shutil
import subprocess
from pathlib import Path
from application_runner import ROOT,load_owner_key
from standing_authorization import save_authorization
LABEL='com.hunt.application-worker'
PYTHON='/Users/theoneglobal/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
if __name__=='__main__':
    target=Path.home()/'Library/Application Support/HUNT/application-worker';target.mkdir(parents=True,exist_ok=True,mode=0o700);target.chmod(0o700)
    for name in ['mac_application_worker.py','application_runner.py','application_execution.py','standing_authorization.py','employer_browser.mjs','native_google_cv.py']:
        shutil.copy2(ROOT/name,target/name)
    private=target/'data';private.mkdir(exist_ok=True,mode=0o700);private.chmod(0o700)
    save_authorization(private,'owner authorized in HUNT workspace conversation',True)
    shutil.copy2(ROOT/'data/master-cv.txt',private/'master-cv.txt');(private/'master-cv.txt').chmod(0o600)
    fd=os.open(private/'owner-connection.json',os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as file:json.dump({'owner_key':load_owner_key(ROOT)},file)
    logs=private/'logs';logs.mkdir(mode=0o700,exist_ok=True)
    for name in ['stdout.log','stderr.log']:
        fd=os.open(logs/name,os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600);os.close(fd)
    agent=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist';agent.parent.mkdir(parents=True,exist_ok=True)
    config={'Label':LABEL,'ProgramArguments':[PYTHON,str(target/'mac_application_worker.py')],'WorkingDirectory':str(target),'RunAtLoad':True,'StartInterval':60,'ProcessType':'Background','StandardOutPath':str(logs/'stdout.log'),'StandardErrorPath':str(logs/'stderr.log')}
    agent.write_bytes(plistlib.dumps(config));agent.chmod(0o600);domain='gui/'+str(os.getuid())
    subprocess.run(['launchctl','bootout',domain,str(agent)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    subprocess.run(['launchctl','bootstrap',domain,str(agent)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    subprocess.run(['launchctl','print',domain+'/'+LABEL],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print('HUNT worker installed in private Application Support storage. Checks every 60 seconds while this Mac is awake. No credentials printed or stored in the startup plist.')
