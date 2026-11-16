"""Owner standing authorization for submissions within HUNT's existing gates."""
import json
import os
from pathlib import Path
import application_execution as execution

POLICY_NAME='standing-application-authorization.json'
def save_authorization(directory,actor,enabled=True,selection_mode='priority_only',providers=None,approved_destinations=None,daily_application_limit=5):
    if not actor or not isinstance(enabled,bool):raise ValueError('Explicit owner identity and authorization state required')
    policy={'version':1,'enabled':enabled,'authorized_by':actor,'authorized_at':execution.stamp(),'mode':'autonomous_within_saved_gates','per_application_approval_required':False,'providers':['lever'],'posting_age_hours':48,'monthly_usd_floor':2500,'eligibility':'explicit Nigeria or worldwide remote eligibility','honor_hidden_roles_and_employers':True,'skip_previously_applied':True,'unknown_answers':'pause_without_guessing','security_challenges':'pause_without_bypass'}
    if selection_mode not in ('priority_only','apply_available'):raise ValueError('Unknown application selection mode')
    policy['selection_mode']=selection_mode;policy['fit_preferences_only']=selection_mode=='apply_available'
    if selection_mode=='apply_available':policy.update(version=2,mode='autonomous_apply_available',eligibility='Nigeria/worldwide is a ranking preference, not an application blocker')
    if providers is not None:
        if not providers or set(providers)-{'lever','breezy','html','email'}:raise ValueError('Unknown authorized channels')
        policy.update(version=3,providers=sorted(set(providers)),questions='use_saved_facts_and_grounded_narratives; report_unresolved_without_interrupting_pool')
        if not isinstance(daily_application_limit,int) or not 1<=daily_application_limit<=5:raise ValueError('A bounded daily submission limit is required')
        policy.update(approved_destinations=approved_destinations or [],daily_application_limit=daily_application_limit,sending_enabled=bool(approved_destinations))
    policy['id']=execution.fingerprint(policy);path=Path(directory)/POLICY_NAME;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as file:json.dump(policy,file,indent=2)
    return policy

def read_authorization(directory):
    path=Path(directory)/POLICY_NAME
    if not path.exists():raise ValueError('Standing authorization is not configured')
    policy=json.loads(path.read_text());ident=policy.get('id');unsigned={k:v for k,v in policy.items() if k!='id'}
    if ident!=execution.fingerprint(unsigned) or policy.get('enabled') is not True or policy.get('mode') not in ('autonomous_within_saved_gates','autonomous_apply_available'):raise ValueError('Standing authorization is disabled or changed')
    if policy.get('selection_mode','priority_only') not in ('priority_only','apply_available'):raise ValueError('Unknown selection authorization')
    if policy.get('posting_age_hours')!=48 or policy.get('monthly_usd_floor')!=2500 or not policy.get('providers') or set(policy['providers'])-{'lever','breezy','html','email'} or policy.get('unknown_answers')!='pause_without_guessing':raise ValueError('Standing authorization does not match supported execution gates')
    return policy

def autonomous_engine(db_factory,checkpoint,directory):
    policy=read_authorization(directory)
    def checked(payload):
        if read_authorization(directory)['id']!=policy['id']:raise ValueError('Standing authorization changed during execution')
        checkpoint(payload)
    return execution.ApplicationExecution(db_factory,checked),policy

def execute_under_standing_authorization(engine,plan_id,adapter,policy,directory):
    if read_authorization(directory)['id']!=policy['id']:raise ValueError('Standing authorization changed')
    plan=engine.get(plan_id)
    if plan['status']=='submitted':return engine.execute(plan_id,adapter)
    if plan['status']!='review':return {**plan,'automatic_submission_paused':True}
    if plan['payload'].get('unresolved_questions'):return {**plan,'automatic_submission_paused':True}
    engine.approve(plan_id,plan['payload_hash'],'standing-owner-authorization:'+policy['id'],valid_minutes=15)
    return engine.execute(plan_id,adapter)
