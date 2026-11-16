"""Process all visible unapplied jobs one at a time; failures never halt the pool."""
import fcntl,hashlib,json,os,re
from pathlib import Path
import application_execution as execution
from application_runner import ROOT,load_owner_key,runner_db
from application_channels import RoutedConnection,HTMLAdapter,EmailAdapter,form_adapter
from autonomous_answers import complete_answers
from mac_application_worker import verified_contact_answers
from standing_authorization import read_authorization,autonomous_engine,execute_under_standing_authorization
from native_google_cv import private_json,prepare_source_native_package

STATUSES={'submitted','email_sent','security_blocked','unreachable','closed','unsupported_form','missing_facts','unconfirmed','error','awaiting_authorization'}
def resolve_candidate(candidate,evidence):
    url=candidate.get('application_url')
    if not url:return {'status':'unreachable','message':'No application URL was saved'}
    if re.match(r'https://jobs\.(?:eu\.)?lever\.co/',url):return {'status':'ready','provider':'lever','url':url.split('?')[0].rstrip('/').removesuffix('/apply')+'/apply'}
    if re.match(r'https://[-a-z0-9]+\.breezy\.hr/p/',url):return {'status':'ready','provider':'breezy','url':url.split('?')[0].removesuffix('/apply')+'/apply'}
    resolver=HTMLAdapter(url,evidence)
    try:return resolver.resolve()
    finally:resolver.close()

def process(client,candidate,engine,policy,root):
    ident=candidate['job_id'];evidence=root/'data/application-evidence'/execution.fingerprint([ident,candidate.get('job_version')])[:24]
    if candidate.get('open') is False:return {'status':'closed','message':'Saved vacancy is closed; no application form is available'}
    route=resolve_candidate(candidate,evidence)
    if route['status']!='ready':return route
    approved=policy.get('sending_enabled') is True and any(d.get('job_id')==ident and str(d.get('url','')).split('?')[0].rstrip('/').removesuffix('/apply')==route['url'].split('?')[0].rstrip('/').removesuffix('/apply') for d in policy.get('approved_destinations',[]))
    if not approved:return {'status':'awaiting_authorization','message':'Application destination identified; no CV uploaded or email sent. Awaiting the bounded destination-batch approval.'}
    from application_channels import daily_submission_count
    if daily_submission_count(root)>=policy.get('daily_application_limit',5):return {'status':'daily_limit','message':'Daily submission limit reached; remaining applications resume tomorrow'}
    if route['provider'] not in policy['providers']:return {'status':'unsupported_form','message':'This channel is not enabled by the saved application policy'}
    adapter=None
    if route['provider']!='email':
        adapter=form_adapter(route,evidence)
        form=adapter.inspect()
        if form.get('captcha') or form.get('platform_restriction'):
            adapter.close();return {'status':'security_blocked','message':'Employer security verification is required; continuing with other jobs'}
    try:
        base_id=candidate.get('package_id')
        if not base_id:base_id=client.request('/api/package',body={'job_id':ident,'use_ai':False})['id']
        package=prepare_source_native_package(client,base_id,root);context=client.context(ident,package['id'])
        client.bind(ident,route['url'])
        if route['provider']=='email':
            source=(root/'data/master-cv.txt').read_text();summary=source.split('PROFESSIONAL SUMMARY\n',1)[1].split('\nCORE COMPETENCIES',1)[0].strip()
            adapter=EmailAdapter(root,route,context['job']['company'],context['job']['title'],summary);form=adapter.inspect();answers={}
        else:
            answers=complete_answers(form,context,root,verified_contact_answers(form,context,root))
            if 'id:location-input' in answers and route['provider']=='lever':
                answers['id:location-input']['value']=adapter.resolve_location(answers['id:location-input']['value'])['value'];form=adapter.inspect()
        resume=[q for q in form['questions'] if q['type']=='file' and re.search(r'resume|\bcv\b',q['label'],re.I)]
        if len(resume)!=1:return {'status':'unsupported_form','message':'A unique CV upload field could not be verified'}
        file=client.download_cv(context)
        plan=engine.plan(job_id=ident,job_version=context['job']['raw_hash'],package_id=package['id'],package_hash=package['payload_hash'],form=form,answers=answers,uploads={resume[0]['id']:file},cv_artifact=context['cv_artifact'])
        result=execute_under_standing_authorization(engine,plan['id'],adapter,policy,root/'data')
        private_json(evidence/'application-record.json',result)
        if result['status']=='submitted':
            receipt={k:v for k,v in result['receipt'].items() if k!='screenshot'}
            resolution={'listing_url':candidate['application_url'],'company':context['job']['company'],'role':context['job']['title'],'verified_by':'owner_desktop_apply_link','employer_url':route['url'].removesuffix('/apply'),'provider':route['provider']}
            body={'job_id':ident,'package_id':package['id'],'package_hash':package['payload_hash'],'cv_sha256':context['cv_artifact']['sha256'],'receipt':receipt,'application_resolution':resolution}
            outbox=root/'data/receipt-outbox'/(plan['id']+'.json');private_json(outbox,body)
            # Delivery is already confirmed. A sync failure must never trigger a new employer send.
            try:client.request('/api/application-receipt',body=body);outbox.unlink();sync='recorded'
            except Exception:sync='pending_sync'
            return {'status':'email_sent' if route['provider']=='email' else 'submitted','message':'Application email accepted by Gmail; acknowledgement pending' if route['provider']=='email' else 'Positive employer confirmation saved','plan_id':plan['id'],'receipt_sync':sync}
        status='missing_facts' if result['status'] in ('needs_input','needs_review') else 'security_blocked' if result['status'] in ('blocked','not_submitted') else 'unconfirmed'
        return {'status':status,'plan_id':plan['id'],'message':'Required factual answers or form changes could not be resolved automatically; continuing with other jobs' if status=='missing_facts' else 'Employer verification or confirmation needs attention; this job is held, other jobs continue'}
    finally:
        if adapter:adapter.close()

def tick(root=ROOT):
    root=Path(root);directory=root/'data';directory.mkdir(exist_ok=True,mode=0o700)
    with (directory/'application-worker.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'status':'already_running'}
        policy=read_authorization(directory);client=RoutedConnection(load_owner_key(root),root);engine,_=autonomous_engine(runner_db(root),client.checkpoint,directory)
        outbox=directory/'receipt-outbox'
        for file in list(outbox.glob('*.json'))[:3] if outbox.exists() else []:
            try:client.request('/api/application-receipt',body=json.loads(file.read_text()));file.unlink()
            except Exception:pass
        attempt_outbox=directory/'attempt-outbox'
        for file in list(attempt_outbox.glob('*.json'))[:20] if attempt_outbox.exists() else []:
            try:client.request('/api/application-attempt',body=json.loads(file.read_text()));file.unlink()
            except Exception:pass
        def report(status,message,pending=0):
            row={'status':status,'message':message,'eligible_candidates':pending,'standing_authorization':True,'selection':'all_unhidden_unapplied','providers':policy['providers'],'sending_enabled':policy.get('sending_enabled') is True,'daily_application_limit':policy.get('daily_application_limit',5)};client.request('/api/application-runner-status',body=row);return row
        scan=client.request('/api/application-candidates?all_routes=1')
        if scan['paused']:return report('paused','HUNT is paused')
        journal_path=directory/'pool-attempts.json';journal=json.loads(journal_path.read_text()) if journal_path.exists() else {}
        held=engine.held_job_ids();approved_jobs={d['job_id'] for d in policy.get('approved_destinations',[])} if policy.get('sending_enabled') else set()
        candidates=[]
        for c in scan['candidates']:
            prior=journal.get(execution.fingerprint([c['job_id'],c.get('job_version')]))
            if c['job_id'] not in held and (not prior or prior.get('status')=='awaiting_authorization' and c['job_id'] in approved_jobs):candidates.append(c)
        if not candidates:
            if attempt_outbox.exists() and any(attempt_outbox.glob('*.json')):return report('running','Outcomes are saved locally and awaiting hosted synchronization')
            if journal:
                batch_id='applications-'+execution.fingerprint(sorted(journal))[:32]
                client.request('/api/application-batch-report',body={'id':batch_id,'attempts':list(journal.values())[-1000:]})
            return report('idle','All current pool records have been processed or held; new jobs will be picked up automatically')
        c=candidates[0];report('running','Processing '+c.get('company','employer')+' · '+c.get('title','role'),len(candidates))
        try:result=process(client,c,engine,policy,root)
        except Exception as error:
            text=str(error).lower();status='unconfirmed' if 'reconciliation' in text else 'unsupported_form' if 'unsupported_form' in text else 'unreachable' if isinstance(error,TimeoutError) or any(x in text for x in ('timeout','timed out','name_not_resolved','transport','connection','net::')) else 'error'
            result={'status':status,'message':'Application attempt did not complete ('+type(error).__name__+'). Continuing with the next pool record.'}
        if result['status']=='daily_limit':return report('idle',result['message'],len(candidates))
        outcome={**result,'id':execution.fingerprint([c['job_id'],c.get('job_version')]),'job_id':c['job_id'],'job_version':c.get('job_version'),'company':c.get('company','Employer'),'role':c.get('title','Role'),'at':execution.stamp()}
        journal[outcome['id']]=outcome;private_json(journal_path,journal)
        pending_outcome=attempt_outbox/(outcome['id']+'.json');private_json(pending_outcome,outcome)
        # Local persistence precedes the hosted report so a failed status write cannot resubmit.
        try:client.request('/api/application-attempt',body=outcome);pending_outcome.unlink()
        except Exception:pass
        return report('submitted' if result['status'] in ('submitted','email_sent') else 'running',result['message']+' · '+str(max(0,len(candidates)-1))+' pool records remain.',max(0,len(candidates)-1))

if __name__=='__main__':
    try:print(json.dumps(tick()))
    except Exception as error:print(json.dumps({'status':'error','error_type':type(error).__name__,'message':'Worker check failed; no unconfirmed application is retried'}))
