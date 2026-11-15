"""Install the owner-authorized Mac-awake application worker; no secrets in plist."""
import os
import plistlib
import subprocess
from pathlib import Path
from application_runner import ROOT
from standing_authorization import save_authorization
LABEL='com.hunt.application-worker'
PYTHON='/Users/theoneglobal/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
if __name__=='__main__':
    policy=save_authorization(ROOT/'data','owner authorized in HUNT workspace conversation',True)
    logs=ROOT/'data/application-worker-logs';logs.mkdir(mode=0o700,exist_ok=True)
    for name in ['stdout.log','stderr.log']:
        fd=os.open(logs/name,os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600);os.close(fd)
    agent=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist';agent.parent.mkdir(parents=True,exist_ok=True)
    configuration={'Label':LABEL,'ProgramArguments':[PYTHON,str(ROOT/'mac_application_worker.py')],'WorkingDirectory':str(ROOT),'RunAtLoad':True,'StartInterval':60,'ProcessType':'Background','StandardOutPath':str(logs/'stdout.log'),'StandardErrorPath':str(logs/'stderr.log')}
    agent.write_bytes(plistlib.dumps(configuration));agent.chmod(0o600)
    domain='gui/'+str(os.getuid())
    subprocess.run(['launchctl','bootout',domain,str(agent)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    subprocess.run(['launchctl','bootstrap',domain,str(agent)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    subprocess.run(['launchctl','print',domain+'/'+LABEL],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print('HUNT Mac-awake worker installed: checks every 60 seconds; standing authorization active; no credentials stored in startup configuration.')
