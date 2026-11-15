"""One bounded autonomous Mac worker tick. Standing consent, no per-job prompts.

Only current priority Lever roles are supported. Missing verified answers stop
before filling. Receipts are retained locally before publishing to HUNT.
"""
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import application_execution as execution
from application_runner import ROOT,HUNTConnection,ProductionLeverAdapter,runner_db,load_owner_key
from standing_authorization import read_authorization,autonomous_engine,execute_under_standing_authorization


def verified_contact_answers(form,context,root=ROOT):
    source=(Path(root)/'data/master-cv.txt').read_text()
    if hashlib.sha256(source.encode()).hexdigest()!=context['package'].get('master_cv_source_hash'):return {}
    lines=[line.strip().lstrip('\ufeff') for line in source.splitlines() if line.strip()]
    email=re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',source)
    phone=re.search(r'\+\(?234\)?[\d\s-]{9,18}',source)
    known={'name':lines[0] if lines else None,'email':email.group(0) if email else None,'phone':re.sub(r'[^+\d]','',phone.group(0)) if phone else None}
    answers={}
    for question in form['questions']:
        label=question['label'].lower().strip().rstrip('*').strip()
        # Only direct contact questions; never infer authorization, consent,
        # demographics, salary, availability, years, or role-specific claims.
        field='name' if label in ('full name','name','your full name') else 'email' if label in ('email','email address','your email') else 'phone' if label in ('phone','phone number','mobile phone','mobile number') else None
        if field and known[field] and question['type'] in ('text','email','tel'):answers[question['id']]={'value':known[field],'source':'verified_profile','verified':True}
    return answers


def process_candidate(client,candidate,engine,policy,root=ROOT,adapter_factory=ProductionLeverAdapter):
    job_id=candidate['job_id'];package_id=candidate.get('package_id')
    if not package_id:
        package=client.request('/api/package',body={'job_id':job_id,'use_ai':True});package_id=package.get('id')
        if not package_id:raise ValueError('Tailored CV generation did not return a saved package')
    context=client.context(job_id,package_id);job=context['job'];package=context['package']
    # Validate all non-form gates before opening the employer page.
    probe={'job_id':job_id,'job_version':job['raw_hash'],'package_id':package_id,'package_hash':package['payload_hash'],'application_url':job['application_url'],'cv_artifact':context['cv_artifact'],'uploads':{'resume':{'sha256':context['cv_artifact']['sha256']}}}
    client.checkpoint(probe)
    adapter=adapter_factory(job['application_url'])
    try:
        form=adapter.inspect()
        resume=[q for q in form['questions'] if q['type']=='file' and re.search(r'resume|\bcv\b',q['label'],re.I)]
        if len(resume)!=1:return {'status':'needs_input','message':'The exact resume field could not be identified. No data was filled.'}
        file=client.download_cv(context);answers=verified_contact_answers(form,context,root)
        plan=engine.plan(job_id=job_id,job_version=job['raw_hash'],package_id=package_id,package_hash=package['payload_hash'],form=form,answers=answers,uploads={resume[0]['id']:file},cv_artifact=context['cv_artifact'])
        result=execute_under_standing_authorization(engine,plan['id'],adapter,policy,Path(root)/'data')
        directory=Path(root)/'data/application-reviews';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        target=directory/(plan['id']+'.json');fd=os.open(target,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as output:json.dump(result,output,indent=2)
        if result['status']=='submitted':
            receipt={k:v for k,v in result['receipt'].items() if k!='screenshot'}
            outbox=Path(root)/'data/receipt-outbox';outbox.mkdir(exist_ok=True,mode=0o700)
            pending=outbox/(plan['id']+'.json');body={'job_id':job_id,'package_id':package_id,'package_hash':package['payload_hash'],'cv_sha256':context['cv_artifact']['sha256'],'receipt':receipt}
            fd=os.open(pending,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as file:json.dump(body,file)
            client.request('/api/application-receipt',body=body);pending.unlink()
        return {'status':result['status'],'plan_id':plan['id'],'message':'Employer confirmation saved.' if result['status']=='submitted' else 'Required facts, security checks or execution gates need attention; nothing new was submitted.'}
    finally:adapter.close()


def tick(root=ROOT):
    root=Path(root);directory=root/'data';directory.mkdir(exist_ok=True,mode=0o700)
    with (directory/'application-worker.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'status':'already_running'}
        policy=read_authorization(directory)
        key=load_owner_key(root)
        client=HUNTConnection(key,root);engine,_=autonomous_engine(runner_db(root),client.checkpoint,directory)
        def report(status,message,count=0):
            output={'status':status,'message':message,'eligible_candidates':count,'standing_authorization':True};client.request('/api/application-runner-status',body=output);return output
        outbox=directory/'receipt-outbox'
        if outbox.exists():
            for file in list(outbox.glob('*.json'))[:1]:
                client.request('/api/application-receipt',body=json.loads(file.read_text()));file.unlink()
        scan=client.request('/api/application-candidates')
        if scan['paused']:return report('paused','HUNT is paused. No applications will be attempted.')
        journal_path=directory/'autonomous-attempts.json';journal=json.loads(journal_path.read_text()) if journal_path.exists() else {}
        candidates=[c for c in scan['candidates'] if execution.fingerprint([c['job_id'],c.get('job_version')]) not in journal]
        if not candidates:return report('idle','No qualifying priority Lever roles within your saved gates. No application was attempted.')
        report('running','Checking one qualifying role.',len(candidates))
        try:
            result=process_candidate(client,candidates[0],engine,policy,root)
            status=result['status'] if result['status'] in ('submitted','needs_input','blocked') else 'blocked'
            journal[execution.fingerprint([candidates[0]['job_id'],candidates[0].get('job_version')])]={**result,'at':execution.stamp()}
            fd=os.open(journal_path,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as file:json.dump(journal,file,indent=2)
            return report(status,result['message'],len(candidates))
        except Exception:
            journal[execution.fingerprint([candidates[0]['job_id'],candidates[0].get('job_version')])]={'status':'blocked','at':execution.stamp()}
            fd=os.open(journal_path,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as file:json.dump(journal,file,indent=2)
            return report('blocked','Application did not complete. Inspect the private execution record; an uncertain attempt will not be retried automatically.',len(candidates))

if __name__=='__main__':
    try:print(json.dumps(tick()))
    except Exception as error:print(json.dumps({'status':'stopped','error_type':type(error).__name__,'message':'Worker connection or authorization needs attention. No successful submission is claimed.'}))
