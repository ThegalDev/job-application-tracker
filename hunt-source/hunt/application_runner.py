"""Production Lever adapter and exact reviewed-CV integration.

Inspection is read-only. Filling/uploading requires a complete approved plan;
submission is permitted only by ApplicationExecution's exact approval ledger.
This is a desktop runner, not an always-on cloud browser service.
"""
import argparse
import contextlib
import hashlib
import json
import os
import re
import selectors
import secrets
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import application_execution as execution

ROOT=Path(__file__).resolve().parent
BASE='https://hunt-aminat.netlify.app'
LEVER_HOSTS={'jobs.lever.co','jobs.eu.lever.co'}


def lever_url(url):
    u=urlsplit(url)
    if u.scheme!='https' or u.hostname not in LEVER_HOSTS or u.username or u.password or u.port or u.query or u.fragment or not re.fullmatch(r'/[A-Za-z0-9_-]+/[a-f0-9-]{36}(?:/apply)?/?',u.path):
        raise ValueError('An exact public Lever job URL is required')
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Unexpected credential-bearing redirect')


class HUNTConnection:
    def __init__(self,owner_key,root=ROOT):
        if not owner_key:raise ValueError('Existing HUNT owner connection required')
        self.owner_key=owner_key
        self.root=Path(root)

    def request(self,path,binary=False,body=None):
        if not path.startswith(('/api/application-context?','/api/cv-artifact?','/api/application-candidates','/api/application-runner-status','/api/package','/api/application-receipt')):raise ValueError('Runner read path denied')
        headers={'X-HUNT-Owner-Key':self.owner_key,'Cache-Control':'no-cache'}
        if body is not None:
            token=secrets.token_hex(32);headers.update({'Origin':BASE,'Cookie':'__Host-hunt_csrf='+token,'X-CSRF-Token':token,'Content-Type':'application/json'})
        req=Request(BASE+path,headers=headers,data=json.dumps(body).encode() if body is not None else None)
        with build_opener(NoRedirect).open(req,timeout=25) as response:
            data=response.read(10*1024*1024+1)
        if len(data)>10*1024*1024:raise ValueError('Runner response exceeds read bound')
        return data if binary else json.loads(data)

    def context(self,job_id,package_id):
        return self.request('/api/application-context?'+urlencode({'job_id':job_id,'package_id':package_id}))

    def download_cv(self,context):
        meta=context['cv_artifact'];p=context['package']
        if meta['package_id']!=p['id'] or meta['package_hash']!=p['payload_hash'] or not re.fullmatch('[a-f0-9]{64}',meta['sha256']):raise ValueError('Reviewed document identity mismatch')
        data=self.request('/api/cv-artifact?'+urlencode({'id':p['id'],'hash':p['payload_hash']}),binary=True)
        if hashlib.sha256(data).hexdigest()!=meta['sha256'] or not data.startswith(b'PK'):raise ValueError('Reviewed CV integrity check failed')
        directory=self.root/'data/application-files';directory.mkdir(parents=True,exist_ok=True,mode=0o700);directory.chmod(0o700)
        target=directory/(meta['sha256']+'.docx')
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest()!=meta['sha256']:raise ValueError('Local reviewed document changed')
        else:
            fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as file:file.write(data)
        return target

    def checkpoint(self,payload):
        current=self.context(payload['job_id'],payload['package_id'])
        validate_context(current,payload)


def validate_context(context,payload):
    j=context['job'];p=context['package'];a=j['assessment'];cv=context['cv_artifact']
    if context.get('paused'):raise ValueError('HUNT is paused')
    if not j.get('open') or j.get('hidden'):raise ValueError('Role is closed or hidden')
    if j['id']!=payload['job_id'] or j['raw_hash']!=payload['job_version'] or p['id']!=payload['package_id'] or p['payload_hash']!=payload['package_hash'] or p['job_version']!=j['raw_hash']:raise ValueError('Job or reviewed package version changed')
    if p.get('status') in ('superseded','rejected','requires_revision') or not p.get('writing_profile_current') or not p.get('master_cv_current'):raise ValueError('Current reviewed CV wording and source are required')
    if a.get('score',0)<85:raise ValueError('Role has not reached the priority fit threshold')
    if not j.get('publication_verified_original'):raise ValueError('Verify the employer-original posting date before automatic application')
    if not j.get('within_discovery_window') or not j.get('global_remote') or a.get('tier') not in ('A','B') or a.get('role_relevant') is False:raise ValueError('Resolve current 48-hour freshness and Nigeria remote eligibility first')
    pay=a.get('compensation',{})
    if pay.get('status')!='meets_floor' or not isinstance(pay.get('monthly_min'),(int,float)) or pay['monthly_min']<2500:raise ValueError('Resolve the verified USD 2500 monthly salary gate first')
    if a.get('duplicate_applications') or a.get('duplicate_listing_of'):raise ValueError('An application or duplicate listing already exists')
    reviewed=payload.get('cv_artifact')
    if not reviewed or reviewed['sha256']!=cv['sha256'] or reviewed['package_hash']!=p['payload_hash']:raise ValueError('Reviewed CV file version changed')
    if not any(u['sha256']==cv['sha256'] for u in payload['uploads'].values()):raise ValueError('The exact reviewed CV must be attached')
    expected=lever_url(j['application_url']).rstrip('/').removesuffix('/apply')
    selected=lever_url(payload['application_url']).rstrip('/').removesuffix('/apply')
    if expected!=selected:raise ValueError('Employer form does not match the selected job')


class ProductionLeverAdapter:
    def __init__(self,url,node_executable=None,evidence_dir=None):
        self.url=lever_url(url)
        self.node=node_executable or shutil.which('node') or '/Users/theoneglobal/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
        self.evidence_dir=Path(evidence_dir or ROOT/'data/application-evidence')
        self.process=None

    def _call(self,command,**values):
        if self.process is None:
            env=dict(os.environ)
            runtime=Path('/Users/theoneglobal/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs')
            if runtime.exists():env.setdefault('HUNT_PLAYWRIGHT_MODULE',str(runtime))
            if Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome').exists():env.setdefault('HUNT_CHROME_EXECUTABLE','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
            self.process=subprocess.Popen([self.node,str(ROOT/'employer_browser.mjs'),self.url,str(self.evidence_dir)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1,env=env)
        self.process.stdin.write(execution.encode({'command':command,**values})+'\n');self.process.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout,selectors.EVENT_READ)
            if not selector.select(55):self.close();raise RuntimeError('Employer browser step timed out; no automatic retry')
        line=self.process.stdout.readline()
        if not line:raise RuntimeError('Employer browser exited without a verified result')
        result=json.loads(line)
        if result.get('ok') is not True:raise RuntimeError('Employer browser step could not be verified: '+result.get('error_type','Error'))
        return result['result']

    def inspect(self,payload=None):return self._call('inspect')
    def preflight(self,payload):
        if payload['form'].get('fixture_only') or payload['form'].get('provider')!='lever':raise ValueError('Exact production Lever form required')
        if lever_url(payload['application_url']).rstrip('/').removesuffix('/apply')!=self.url.rstrip('/').removesuffix('/apply'):raise ValueError('Browser is bound to a different employer job')
    def fill(self,payload):return self._call('fill',payload=payload)
    def submit(self,payload,idempotency_key):return self._call('submit',payload=payload,idempotency_key=idempotency_key)
    def close(self):
        if self.process:
            try:
                self.process.stdin.write('{"command":"close"}\n');self.process.stdin.flush();self.process.wait(timeout=3)
            except (OSError,subprocess.TimeoutExpired):self.process.kill();self.process.wait(timeout=5)
            finally:self.process.stdin.close();self.process.stdout.close();self.process=None


def runner_db(root=ROOT):
    path=Path(root)/'data/application-runner.sqlite3';path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    @contextlib.contextmanager
    def db():
        c=sqlite3.connect(path,timeout=30);path.chmod(0o600);c.row_factory=sqlite3.Row
        try:
            with c:yield c
        finally:c.close()
    return db


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['inspect','plan','show','approve','execute'])
    parser.add_argument('--job-id');parser.add_argument('--package-id');parser.add_argument('--plan-id');parser.add_argument('--expected-hash');parser.add_argument('--answers-file',type=Path);parser.add_argument('--actor')
    args=parser.parse_args()
    key=next((line.partition('=')[2].strip().strip('\"\'') for line in (ROOT.parent.parent/'work/netlify-runtime.env').read_text().splitlines() if line.partition('=')[0].strip()=='HUNT_OWNER_KEY'),None)
    connection=HUNTConnection(key);engine=execution.ApplicationExecution(runner_db(),connection.checkpoint)
    if args.command in ('inspect','plan'):
        if not args.job_id or not args.package_id:parser.error('Exact --job-id and --package-id are required')
        context=connection.context(args.job_id,args.package_id);j=context['job'];p=context['package'];adapter=ProductionLeverAdapter(j['application_url'])
        try:form=adapter.inspect()
        finally:adapter.close()
        if args.command=='inspect':
            output={'context':context,'form':form,'employer_submissions':0}
        else:
            if not args.answers_file:parser.error('An explicit owner-reviewed --answers-file is required')
            draft=json.loads(args.answers_file.read_text());uploads={}
            if draft.get('cv_question_id'):uploads[draft['cv_question_id']]=connection.download_cv(context)
            output=engine.plan(job_id=j['id'],job_version=j['raw_hash'],package_id=p['id'],package_hash=p['payload_hash'],form=form,answers=draft.get('answers',{}),uploads=uploads,cv_artifact=context['cv_artifact'])
    elif args.command=='approve':
        if not args.actor or not args.expected_hash:parser.error('Exact --expected-hash and explicit --actor are required')
        output=engine.approve(args.plan_id,args.expected_hash,args.actor)
    elif args.command=='execute':
        plan=engine.get(args.plan_id);adapter=ProductionLeverAdapter(plan['payload']['application_url'])
        try:output=engine.execute(args.plan_id,adapter)
        finally:adapter.close()
    else:output=engine.get(args.plan_id)
    directory=ROOT/'data/application-reviews';directory.mkdir(exist_ok=True,mode=0o700);directory.chmod(0o700)
    target=directory/((output.get('id') or 'inspection')+'.json');fd=os.open(target,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as file:json.dump(output,file,indent=2)
    print(json.dumps({'private_review_file':str(target),'status':output.get('status','inspected'),'plan_id':output.get('id'),'payload_hash':output.get('payload_hash'),'employer_submissions':1 if output.get('status')=='submitted' else 0}))


if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps({'status':'stopped','error_type':type(e).__name__,'message':'Runner stopped. No successful submission is claimed; inspect private plan state before retrying.'}));sys.exit(1)
