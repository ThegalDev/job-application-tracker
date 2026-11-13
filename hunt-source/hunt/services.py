"""HUNT role tools, evidence-derived reports and WAT operating schedule."""
import base64
import datetime as dt
import json
import re
from email.utils import parseaddr
from collections import Counter
from zoneinfo import ZoneInfo
from orchestrator import Orchestrator,ToolSpec
import matching

WAT=ZoneInfo('Africa/Lagos')
SCHEDULE_WAT=[
    {'id':'morning-discovery','time':'07:00','trigger':'discovery','label':'Discover and verify new vacancies'},
    {'id':'morning-shortlist','time':'08:00','trigger':'shortlist','label':'Prepare ranked morning shortlist'},
    {'id':'midday-discovery','time':'12:00','trigger':'discovery','label':'Recheck employers and new roles'},
    {'id':'afternoon-pipeline','time':'16:00','trigger':'pipeline','label':'Check responses, deadlines and follow-ups'},
    {'id':'evening-discovery','time':'18:00','trigger':'discovery','report':'daily','label':'Final discovery check and daily report'},
    {'id':'weekly-report','time':'18:30','weekday':4,'report':'weekly','label':'Weekly career performance report'},
]

def install(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS career_reports(id TEXT PRIMARY KEY,period TEXT NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS scheduled_ticks(id TEXT PRIMARY KEY,slot TEXT NOT NULL,scheduled TEXT NOT NULL,status TEXT NOT NULL,result TEXT,error TEXT);
    CREATE TABLE IF NOT EXISTS pipeline_actions(id TEXT PRIMARY KEY,application_id TEXT,kind TEXT NOT NULL,due TEXT,status TEXT NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS outreach_drafts(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,package_id TEXT NOT NULL,created TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,payload_hash TEXT NOT NULL);
    ''')

def _jobs(hunt):
    with hunt.db() as c:return [{**dict(r),'assessment':json.loads(r['assessment'])} for r in c.execute('SELECT * FROM jobs WHERE open=1')]

def _eligible(j):
    a=j['assessment'];return a['tier'] in ('A','B') and not a.get('duplicate_applications') and not a.get('duplicate_listing_of')

def runtime(hunt):
    with hunt.db() as c:install(c)
    def discover(ctx,payload):
        ctx.checkpoint();results=hunt.discover();expansion=None
        if payload.get('use_ai',True) and payload.get('expand_watchlist',False):
            ctx.checkpoint()
            import research
            expansion=research.expand_watchlist(hunt)
        good=sum(r.get('status')=='success' for r in results)
        return {'status':'success' if good==len(results) and results else 'partial' if good else 'blocked','sources':results,'watchlist_expansion':expansion}
    def match(ctx,payload):
        ctx.checkpoint()
        with hunt.db() as c:rows=[dict(r) for r in c.execute('SELECT * FROM jobs')]
        counts=Counter();semantic_reviews=0;semantic_errors=[]
        for j in rows:
            ctx.checkpoint()
            with hunt.db() as c:a=hunt.current_assessment(c,j)
            if payload.get('use_ai',True) and j['open'] and a['tier']!='D' and not a['duplicate_applications'] and a['score']>=55 and semantic_reviews<2:
                with hunt.db() as c:cached=c.execute('SELECT 1 FROM semantic_assessments WHERE job_id=? AND job_version=?',(j['id'],j['raw_hash'])).fetchone()
                if not cached:
                    try:
                        import semantic
                        semantic.assess(hunt,j);semantic_reviews+=1
                        with hunt.db() as c:a=hunt.current_assessment(c,j)
                    except Exception as error:semantic_errors.append({'job_id':j['id'],'error_type':type(error).__name__})
            counts[a['status']]+=1
        with hunt.db() as c:
            hunt.audit(c,'match_agent_completed',{'run_id':ctx.run_id,'jobs':len(rows),'weights':matching.WEIGHTS,'hard_floor_usd':matching.HARD_MONTHLY_USD})
        return {'status':'partial' if semantic_errors else 'success','jobs_scored':len(rows),'decision_counts':dict(counts),'scoring_version':'prd-1.0','semantic_reviews':semantic_reviews,'semantic_errors':semantic_errors}
    def company(ctx,payload):
        candidates=sorted((j for j in _jobs(hunt) if _eligible(j) and j['assessment']['score']>=70),key=lambda j:j['assessment']['score'],reverse=True)[:2]
        complete=[];errors=[]
        for j in candidates:
            ctx.checkpoint()
            with hunt.db() as c:
                cached=c.execute('SELECT * FROM company_research WHERE job_id=?',(j['id'],)).fetchone()
            if cached and cached['job_version']==j['raw_hash'] and cached['at']>(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=24)).isoformat():
                complete.append(j['id']);continue
            if not payload.get('use_ai',True):continue
            import research
            try:
                research.employer_research(hunt,j)
                with hunt.db() as c:hunt.current_assessment(c,j)
                complete.append(j['id'])
            except Exception as exc:errors.append({'job_id':j['id'],'error_type':type(exc).__name__})
        return {'status':'partial' if errors else 'success','job_ids':complete,'eligible_candidates':len(candidates),'errors':errors,'reason':None if payload.get('use_ai',True) else 'Public web AI research disabled for this run'}
    def studio(ctx,payload):
        candidates=sorted((j for j in _jobs(hunt) if _eligible(j) and j['assessment']['score']>=85 and j['assessment']['compensation']['status']=='meets_floor'),key=lambda j:j['assessment']['score'],reverse=True)[:2]
        prepared=[];errors=[]
        for j in candidates:
            ctx.checkpoint();cached=None
            with hunt.db() as c:
                for p in c.execute('SELECT id,payload,status FROM packages WHERE job_id=? ORDER BY at DESC',(j['id'],)):
                    package=json.loads(p['payload'])
                    if package.get('job_version')==j['raw_hash'] and p['status']!='rejected':cached=p['id'];break
            if cached:prepared.append(cached);continue
            try:
                p=hunt.package(j['id'],use_ai=payload.get('use_ai',True));prepared.append(p['id'])
            except Exception as exc:errors.append({'job_id':j['id'],'error_type':type(exc).__name__})
        return {'status':'partial' if errors else 'success','package_ids':prepared,'eligible_candidates':len(candidates),'errors':errors,'reason':'No salary-qualified priority roles available' if not candidates else None}
    def outreach(ctx,payload):
        package_ids=ctx.dependencies.get('application_studio',{}).get('package_ids',[]);drafts=[];blocked=0
        for pid in package_ids:
            ctx.checkpoint()
            with hunt.db() as c:
                row=c.execute('SELECT * FROM packages WHERE id=?',(pid,)).fetchone()
                if not row:continue
                p=json.loads(row['payload']);j=c.execute('SELECT * FROM jobs WHERE id=?',(row['job_id'],)).fetchone()
                if not j:continue
                facts=p.get('facts',[]);quote=p.get('selection',{}).get('requirement_quote','')
                if quote and quote not in j['description']:quote=''
                fact=facts[0] if facts else None
                # Recipient identity must come from a separately verified public contact record.
                draft={'job_id':row['job_id'],'package_id':pid,'channel':'email','recipient':None,'subject':p['role']+' — relevant People Operations experience',
                       'body':f'Hello {p["company"]} team,\n\n'+(f'Your {p["role"]} posting highlights: “{quote}”\n\n' if quote else f'I am writing about your {p["role"]} role.\n\n')+(fact['text']+'\n\n' if fact else '')+'Would you be open to a brief conversation about the role’s priorities?\n\nAminat Majekadegbe',
                       'fact_ids':[fact['id']] if fact else [],'source_url':j['url'],'approval_required':True,'status':'recipient_unverified','limitation':'No recipient email has been verified; nothing sent.'}
                did=hunt.digest({'package_id':pid,'payload':draft})[:24]
                c.execute('INSERT OR IGNORE INTO outreach_drafts VALUES(?,?,?,?,?,?,?)',(did,row['job_id'],pid,hunt.now(),'recipient_unverified',hunt.dump(draft),hunt.digest(draft)))
                hunt.audit(c,'outreach_draft_prepared',{'draft_id':did,'package_id':pid,'recipient_status':'unverified','sent':False})
                drafts.append(did);blocked+=1
        return {'status':'partial' if blocked else 'success','draft_ids':drafts,'recipient_verification_needed':blocked,'external_actions':0}
    def pipeline(ctx,payload):
        from google_provider import GoogleProvider
        import email_pipeline
        with hunt.db() as c:
            email=hunt.value(c,'email');sheet_id=hunt.value(c,'sheet_id')
        local_queue=refresh_pipeline_queue(hunt)
        provider=GoogleProvider(email or '')
        if not provider.configured():
            return {'status':'blocked','mode':'Codex connector bridge','reason':'Standalone Google OAuth is not configured. Existing connected snapshots remain available; no fresh inbox check was performed.','local_application_count':_application_count(hunt),'local_next_actions':len(local_queue)}
        tracker=None
        if sheet_id:
            ctx.checkpoint();rows=provider.tracker(sheet_id).get('values',[])
            if rows:tracker=hunt.sync_tracker_snapshot({'sheet_id':sheet_id,'email':email,'rows':rows,'verified_at':hunt.now()})
        with hunt.db() as c:
            applications=[dict(r) for r in c.execute('SELECT * FROM applications')]
            domains={}
            for row in c.execute('SELECT j.company,m.payload FROM jobs j JOIN job_metadata m ON j.id=m.id'):
                domains.setdefault(hunt.norm(row['company']),set()).update(json.loads(row['payload']).get('verified_employer_domains',[]))
        ctx.checkpoint();scan=None
        if payload.get('repair_message_ids'):
            response=provider.recruiting_messages_by_id(payload['repair_message_ids'],checkpoint=ctx.checkpoint)
        else:
            scan=email_pipeline.scan_state(hunt,applications)
            response=provider.recruiting_messages(scan['after'],max_pages=1,page_token=scan['page_token'],before=scan['before'],companies=scan['companies'],checkpoint=ctx.checkpoint)
        if response.get('account')!=email:raise ValueError('Gmail scan account mismatch')
        normalized=[]
        for message in response['messages']:
            ctx.checkpoint()
            normalized.append(email_pipeline.normalize_message(hunt,message,applications,email,domains))
        ctx.checkpoint();events=hunt.reconcile_messages(normalized)
        if scan:email_pipeline.save_scan(hunt,scan,response)
        local_queue=refresh_pipeline_queue(hunt)
        imported=sum('status' in event for event in events)
        return {'status':'success' if response.get('complete') else 'partial','mode':'standalone_oauth','scan_mode':response.get('mode','historical_reconciliation'),'messages_examined':len(normalized),'events_processed':len(events),'events_imported':imported,'events_already_recorded':len(events)-imported,'tracker':tracker,'scan_complete':response.get('complete',False),'continuation_saved':bool(scan) and not response.get('complete',False),'bulk_messages_skipped':response.get('bulk_messages_skipped',0),'sheet_writes':0,'local_next_actions':len(local_queue),'classifier_version':email_pipeline.CLASSIFIER_VERSION}
    return Orchestrator(hunt.db,{
        'discover_jobs':ToolSpec(discover,replay_safe=True,cost_upper_bound_usd=.05),
        'match_jobs':match,
        'research_companies':ToolSpec(company,replay_safe=False,cost_upper_bound_usd=.10),
        'prepare_applications':ToolSpec(studio,replay_safe=False,cost_upper_bound_usd=.05),
        'prepare_outreach':outreach,
        'reconcile_pipeline':pipeline,
    })

def run_pipeline(hunt,trigger='full',use_ai=True,idempotency_key=None):
    engine=runtime(hunt)
    rid=engine.enqueue(trigger,{'use_ai':bool(use_ai),'expand_watchlist':trigger=='discovery' and bool(use_ai)},idempotency_key=idempotency_key,max_calls=16,max_seconds=600,max_cost_usd=.5)
    return engine.run(rid)

def _application_count(hunt):
    with hunt.db() as c:return c.execute('SELECT COUNT(*) FROM applications').fetchone()[0]

def _mail_text(part):
    from email_pipeline import mail_text
    return mail_text(part)

def make_report(hunt,period='daily'):
    if period not in ('daily','weekly'):raise ValueError('Report period must be daily or weekly')
    at=dt.datetime.now(dt.timezone.utc);since=(at-dt.timedelta(days=1 if period=='daily' else 7)).isoformat()
    with hunt.db() as c:
        install(c);jobs=[dict(r) for r in c.execute('SELECT * FROM jobs')];apps=[dict(r) for r in c.execute('SELECT * FROM applications')]
        messages=[dict(r) for r in c.execute('SELECT * FROM mail_events WHERE at>=?',(since,))]
        approvals=c.execute('SELECT COUNT(*) FROM approvals WHERE at>=?',(since,)).fetchone()[0]
        queue=[{**dict(r),'payload':json.loads(r['payload'])} for r in c.execute("SELECT * FROM pipeline_actions WHERE status='recommended' ORDER BY due,id LIMIT 30")]
        scores=[{**j,'assessment':json.loads(j['assessment'])} for j in jobs]
        priorities=[j for j in scores if j['open'] and _eligible(j) and j['assessment']['score']>=85 and j['assessment']['compensation']['status']=='meets_floor']
        status_counts=Counter(a.get('status','Unknown') for a in apps);responses=Counter(m.get('status','Needs review') for m in messages)
        payload={'period':period,'from':since,'at':at.isoformat(),'applications_total':len(apps),'application_status_counts':dict(status_counts),
                 'newly_discovered':sum(j['discovered']>=since for j in jobs),'open_jobs':sum(bool(j['open']) for j in jobs),'salary_qualified_priorities':len(priorities),
                 'recruitment_events':dict(responses),'review_decisions':approvals,'pipeline_next_actions':queue,
                 'interview_invitations_observed':sum('Interview' in m.get('status','') for m in messages),'offers_observed':sum('Offer' in m.get('status','') for m in messages),
                 'next_actions':[{'job_id':j['id'],'action':'Review prepared evidence-backed application','score':j['assessment']['score']} for j in sorted(priorities,key=lambda x:x['assessment']['score'],reverse=True)[:5]],
                 'limitations':['Recruitment counts cover imported evidence only, not an assumed complete inbox.','Automated acknowledgments and rejections are not interviews.','A conversion improvement or hiring probability is not inferred from these counts.','Silence never changes an application to Rejected.']}
        rid=hunt.digest({'period':period,'date':at.date().isoformat(),'payload':payload})[:24]
        c.execute('INSERT OR IGNORE INTO career_reports VALUES(?,?,?,?)',(rid,period,at.isoformat(),hunt.dump(payload)))
        hunt.audit(c,'career_report_created',{'report_id':rid,'period':period,'applications':len(apps),'recruiting_events':len(messages)})
    return {'id':rid,**payload}

def due_schedule(hunt,at=None):
    at=(at or dt.datetime.now(WAT)).astimezone(WAT);due=[]
    with hunt.db() as c:
        install(c)
        for slot in SCHEDULE_WAT:
            if slot.get('weekday',at.weekday())!=at.weekday() or at.strftime('%H:%M')<slot['time']:continue
            key=at.date().isoformat()+':'+slot['id']
            if not c.execute('SELECT 1 FROM scheduled_ticks WHERE id=?',(key,)).fetchone():due.append({**slot,'id':key,'slot_id':slot['id']})
    return due

def schedule_status(hunt):
    with hunt.db() as c:
        install(c);enabled=hunt.value(c,'preferences',{}).get('schedule_enabled',False)
        ticks=[dict(r) for r in c.execute('SELECT id,slot,scheduled,status,error FROM scheduled_ticks ORDER BY scheduled DESC LIMIT 20')]
    return {'timezone':'Africa/Lagos','enabled':enabled,'slots':SCHEDULE_WAT,'recent_ticks':ticks,'requirement':'Scheduled desktop runs require this Mac and Codex to be available. Independent cloud execution is not yet connected.'}

def tick_schedule(hunt,at=None):
    with hunt.db() as c:
        if hunt.value(c,'paused') or not hunt.value(c,'preferences',{}).get('schedule_enabled',False):return []
    results=[]
    for slot in due_schedule(hunt,at):
        with hunt.db() as c:
            claimed=c.execute("INSERT OR IGNORE INTO scheduled_ticks(id,slot,scheduled,status) VALUES(?,?,?,'running')",(slot['id'],slot['id'].split(':',1)[1],hunt.now())).rowcount
        if not claimed:continue
        try:
            result={}
            if slot.get('trigger'):result['workflow']=run_pipeline(hunt,slot['trigger'],idempotency_key=slot['id'])
            if slot.get('report'):result['report']=make_report(hunt,slot['report'])
            state=result.get('workflow',{}).get('status','success')
            with hunt.db() as c:c.execute('UPDATE scheduled_ticks SET status=?,result=? WHERE id=?',(state,hunt.dump(result),slot['id']))
            results.append({'slot':slot['id'],'status':state})
        except Exception as exc:
            with hunt.db() as c:c.execute("UPDATE scheduled_ticks SET status='failed',error=? WHERE id=?",(type(exc).__name__,slot['id']))
            results.append({'slot':slot['id'],'status':'failed','error_type':type(exc).__name__})
    return results


def refresh_pipeline_queue(hunt,at=None):
    """Recommend follow-ups and pending-stage reviews; never infer a rejection."""
    at=at or dt.datetime.now(dt.timezone.utc);records=[]
    with hunt.db() as c:
        install(c)
        for row in c.execute('SELECT * FROM applications'):
            a=dict(row);status=(a.get('status') or '').lower();kind=None;due=None;basis=None
            if any(x in status for x in ('rejected','withdrawn','closed','hired')):continue
            if 'interview' in status:
                kind='review_interview';basis='Interview evidence exists; review the invitation and proposed time before scheduling.'
            elif 'assessment' in status:
                kind='review_assessment';basis='Assessment event recorded; check its instructions and deadline. A completed AI interview is not an offer.'
            elif 'offer' in status:
                kind='review_offer';basis='Offer evidence requires your review; no acceptance is authorized.'
            else:
                try:last=dt.date.fromisoformat((a.get('latest') or a.get('applied') or '')[:10])
                except ValueError:continue
                if (at.date()-last).days>=7:
                    kind='consider_followup';due=(last+dt.timedelta(days=7)).isoformat();basis='At least seven days since the last recorded event. This is a suggested review date, not an employer deadline.'
            if not kind:continue
            payload={'application_id':a['id'],'company':a['company'],'role':a['role'],'kind':kind,'due':due,'basis':basis,'evidence':a.get('evidence'),'external_action':'Approval required before any message or calendar action.'}
            key=hunt.digest([a['id'],kind,a.get('latest')])[:24]
            c.execute('INSERT OR IGNORE INTO pipeline_actions VALUES(?,?,?,?,?,?)',(key,a['id'],kind,due,'recommended',hunt.dump(payload)))
            records.append({'id':key,**payload})
        current={r['id'] for r in records}
        for row in c.execute("SELECT id FROM pipeline_actions WHERE status='recommended'"):
            if row['id'] not in current:c.execute("UPDATE pipeline_actions SET status='superseded' WHERE id=?",(row['id'],))
    return records
