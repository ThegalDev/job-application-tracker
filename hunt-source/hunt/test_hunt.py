import copy, json, os, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
import hunt

class HuntTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=(hunt.DATA,hunt.DB)
        hunt.DATA=Path(self.tmp.name);hunt.DB=hunt.DATA/'test.sqlite3';hunt.init()
        self.prefs={'monthly_usd':2500,'salary_is_hard_floor':False}
        self.j={'id':'test:job:1','identity':'acme people operations remote worldwide','kind':'ashby','board':'acme','company':'Acme','title':'People Operations Specialist','location':'Remote worldwide','url':'https://jobs.ashbyhq.com/acme/one','description':'Own onboarding and offboarding; build HR workflow automation and employee records.','published':None,'updated':None,'raw_hash':'x'}
    def tearDown(self):hunt.DATA,hunt.DB=self.old;self.tmp.cleanup()
    def eligible(self,loc,desc='',expected='C'):
        j={**self.j,'location':loc,'description':desc};self.assertEqual(hunt.eligibility(j,self.prefs)['tier'],expected)
    def test_nigeria(self):self.eligible('Remote, Lagos, Nigeria',expected='A')
    def test_worldwide(self):self.eligible('Remote worldwide',expected='A')
    def test_remote_unknown(self):self.eligible('Remote',expected='C')
    def test_emea_unconfirmed(self):self.eligible('Remote EMEA',expected='C')
    def test_africa_unconfirmed(self):self.eligible('Remote Africa',expected='C')
    def test_us_remote(self):self.eligible('Remote - United States',expected='D')
    def test_americas_restricted(self):self.eligible('Remote (Central & South America)',expected='D')
    def test_eu_remote(self):self.eligible('European Union',expected='D')
    def test_foreign_onsite(self):self.eligible('Tokyo',expected='D')
    def test_sponsorship(self):self.eligible('London','We provide visa sponsorship.',expected='A')
    def test_sponsorship_negated(self):self.eligible('London','We do not offer visa sponsorship.',expected='D')
    def test_restriction_overrides_marketing(self):self.eligible('Remote worldwide','US-only role.',expected='D')
    def test_nigeria_exception(self):self.eligible('Remote worldwide','Available worldwide except Nigeria.',expected='D')
    def test_hard_salary(self):
        self.prefs['salary_is_hard_floor']=True
        self.eligible('Lagos, Nigeria','USD 1000 - 2000 per month',expected='D')
    def test_salary_preference(self):self.eligible('Nigeria','USD 1000 per month',expected='D')
    def test_currency_not_assumed(self):
        self.assertEqual(hunt.eligibility({**self.j,'description':'₦250000 monthly'},self.prefs)['salary'],'Unknown')
    def test_annual_salary(self):
        a=hunt.eligibility({**self.j,'description':'USD 30000 per year'},self.prefs)
        self.assertIn('2,500',a['salary'])
    def test_evidence_matches_source(self):
        fs=[{'id':'onboarding','text':'Coordinated onboarding and offboarding.','source':'cv'}]
        a=hunt.score_job(self.j,fs,self.prefs,[])
        self.assertEqual(a['matches'][0]['fact_id'],'onboarding')
        for m in a['matches']:self.assertIn(m['job_quote'],self.j['description'])
    def test_duplicate_company_and_role(self):
        a=hunt.score_job(self.j,[],self.prefs,[{'id':'prior','company':'Acme','role':'People Operations Specialist'}])
        self.assertEqual(a['status'],'Already applied')
    def test_separate_roles_not_merged(self):
        a=hunt.score_job(self.j,[],self.prefs,[{'id':'prior','company':'Acme','role':'Recruiter'}]);self.assertEqual(a['duplicate_applications'],[])
    def test_title_alias_ops(self):self.assertEqual(hunt.norm('Talent Ops'),hunt.norm('Talent Operations'))
    def test_html_untrusted(self):self.assertEqual(hunt.text_content('<script>alert(1)</script><p>Own HR</p>'),'Own HR')
    def test_url_allowlist(self):
        with self.assertRaises(ValueError):hunt.fetch_json('http://127.0.0.1/secrets')
        with self.assertRaises(ValueError):hunt.fetch_json('https://evil.test/')
    def test_invalid_board(self):
        with self.assertRaises(ValueError):hunt.feed_url({'kind':'ashby','board':'../../secret'})
    def test_publication_not_updated(self):
        j=hunt.normalize_feed({'kind':'greenhouse','board':'acme','company':'Acme'},{'jobs':[{'id':1,'title':'People Ops','location':{'name':'Nigeria'},'absolute_url':'https://job-boards.greenhouse.io/acme/jobs/1','updated_at':'2026-11-01'}]})[0]
        self.assertIsNone(j['published']);self.assertEqual(j['updated'],'2026-11-01')
    def feed(self, jobs=None):
        return {'kind':'ashby','board':'acme','company':'Acme'},{'jobs':jobs if jobs is not None else [{'id':'one','title':'People Operations Specialist','location':'Nigeria','jobUrl':self.j['url'],'descriptionPlain':self.j['description']+' USD 3000 per month','isListed':True}]}
    def test_feed_idempotent(self):
        f,d=self.feed();hunt.ingest_feed(f,d);hunt.ingest_feed(f,d)
        with hunt.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],1)
    def test_closed_on_successful_removal(self):
        f,d=self.feed();hunt.ingest_feed(f,d);hunt.ingest_feed(f,{'jobs':[]})
        with hunt.db() as c:self.assertEqual(c.execute('SELECT open FROM jobs').fetchone()[0],0)
    def test_failed_source_preserves_jobs(self):
        f,d=self.feed();hunt.ingest_feed(f,d)
        with patch('hunt.FEEDS',[f]),patch('hunt.fetch_json',side_effect=RuntimeError('Provider HTTP 429')):hunt.discover()
        s=hunt.snapshot();self.assertEqual(s['jobs'][0]['open'],1);self.assertEqual(s['sources'][0]['status'],'error')
    def test_audit_tamper_detected(self):
        with hunt.db() as c:hunt.audit(c,'test',{'id':'one'})
        self.assertTrue(hunt.verify_audit())
        with hunt.db() as c:c.execute("UPDATE events SET kind='changed'")
        self.assertFalse(hunt.verify_audit())
    def test_classifier_rejection(self):self.assertEqual(hunt.classify_message('We decided not to progress with your application')['status'],'Rejected')
    def test_classifier_silence(self):self.assertEqual(hunt.classify_message('No updates are available')['status'],'Needs review')
    def test_interview_not_scheduled(self):self.assertEqual(hunt.classify_message('We invite you to an interview')['status'],'Interview invitation')
    def test_micro1_interview_not_offer(self):self.assertEqual(hunt.classify_message("You have completed the AI interview")['status'],'Assessment / next step')
    def test_reconcile_once_and_no_regression(self):
        with hunt.db() as c:c.execute('INSERT INTO applications VALUES(?,?,?,?,?,?,?,?,?,?)',('a','Acme','Recruiter','2026-10-01','Application acknowledged','2026-10-01','link','',2,'{}'))
        m={'id':'m1','company':'Acme','role':'Recruiter','at':'2026-11-09T01:00:00+00:00','evidence':'https://mail.google.com','body':'We decided not to progress with your application'}
        hunt.reconcile_messages([m]);self.assertEqual(hunt.reconcile_messages([m])[0]['result'],'duplicate')
        hunt.reconcile_messages([{**m,'id':'m2','at':'2026-11-01','body':'We received your application'}])
        with hunt.db() as c:self.assertEqual(c.execute('SELECT status FROM applications').fetchone()[0],'Rejected')
    def test_ambiguous_role_quarantined(self):
        m={'id':'x','at':'2026-11-09','company':'Acme','role':'Unknown','body':'We received your application','evidence':'link'}
        self.assertIn('Needs review',hunt.reconcile_messages([m])[0]['result'])
    def test_pause_blocks_discovery(self):
        with hunt.db() as c:c.execute("UPDATE kv SET value='true' WHERE key='paused'")
        with self.assertRaises(ValueError):hunt.discover()
    def test_recovery_no_replay(self):
        with hunt.db() as c:c.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',('r','discovery',hunt.now(),None,'running','{}'))
        hunt.init()
        with hunt.db() as c:self.assertEqual(c.execute('SELECT status FROM runs').fetchone()[0],'interrupted')
    def test_approval_payload_bound_idempotent(self):
        f,d=self.feed();hunt.ingest_feed(f,d)
        with hunt.db() as c:
            c.execute('INSERT INTO packages VALUES(?,?,?,?,?,?)',('p','ashby:acme:one',hunt.now(),hunt.dump({'job_version':'x'}),hunt.digest({'job_version':'x'}),'review'))
        
        with hunt.db() as c:
            version=c.execute('SELECT raw_hash FROM jobs').fetchone()[0]
            payload={'job_version':version};c.execute('UPDATE packages SET payload=?,hash=?',(hunt.dump(payload),hunt.digest(payload)))
        r=hunt.approve('p','approved_for_manual_action');r2=hunt.approve('p','approved_for_manual_action')
        self.assertEqual(r['id'],r2['id'])
        with hunt.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM approvals').fetchone()[0],1)
    def test_excluded_approval_denied(self):
        f,d=self.feed();d['jobs'][0]['location']='United States';hunt.ingest_feed(f,d)
        with hunt.db() as c:c.execute('INSERT INTO packages VALUES(?,?,?,?,?,?)',('p','ashby:acme:one',hunt.now(),hunt.dump({'job_version':'x'}),hunt.digest({'job_version':'x'}),'review'))
        with self.assertRaises(ValueError):hunt.approve('p','approved_for_manual_action')
    def test_stale_approval_denied(self):
        f,d=self.feed();hunt.ingest_feed(f,d)
        with hunt.db() as c:
            c.execute("UPDATE jobs SET verified='2020-01-01T00:00:00+00:00'")
            c.execute('INSERT INTO packages VALUES(?,?,?,?,?,?)',('p','ashby:acme:one',hunt.now(),hunt.dump({'job_version':'x'}),hunt.digest({'job_version':'x'}),'review'))
        with self.assertRaises(ValueError):hunt.approve('p','approved_for_manual_action')
    def test_job_change_invalidates_review(self):
        f,d=self.feed();hunt.ingest_feed(f,d)
        with hunt.db() as c:c.execute('INSERT INTO packages VALUES(?,?,?,?,?,?)',('p','ashby:acme:one',hunt.now(),hunt.dump({'job_version':'old'}),hunt.digest({'job_version':'old'}),'review'))
        with self.assertRaisesRegex(ValueError,'Job changed'):hunt.approve('p','approved_for_manual_action')
    def test_package_tamper_denied(self):
        f,d=self.feed();hunt.ingest_feed(f,d)
        with hunt.db() as c:c.execute('INSERT INTO packages VALUES(?,?,?,?,?,?)',('p','ashby:acme:one',hunt.now(),'{}','incorrect-hash','review'))
        with self.assertRaisesRegex(ValueError,'integrity'):hunt.approve('p','approved_for_manual_action')
    def test_cross_source_duplicate_listing(self):
        f,d=self.feed();hunt.ingest_feed(f,d)
        f2={'kind':'greenhouse','board':'acme','company':'Acme'}
        hunt.ingest_feed(f2,{'jobs':[{'id':'two','title':'People Operations Specialist','location':{'name':'Nigeria'},'absolute_url':'https://job-boards.greenhouse.io/acme/jobs/two','content':'Own onboarding.'}]})
        with hunt.db() as c:
            a=json.loads(c.execute("SELECT assessment FROM jobs WHERE kind='greenhouse'").fetchone()[0]);self.assertEqual(a['status'],'Duplicate listing')
    def test_ai_cannot_invent_facts(self):
        response={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'fact_ids':['fabricated'],'requirement_index':0,'questions':[]})}]}]}
        with patch('hunt.fetch_json',return_value=response),patch('hunt.load_key',return_value='test-key'):
            with self.assertRaisesRegex(ValueError,'Invalid fact'):hunt.ai_select(self.j,[{'id':'known','text':'Verified experience','source':'private-source-url'}])
    def test_ai_payload_minimized(self):
        response={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'fact_ids':['known'],'requirement_index':0,'questions':['How would you approach the role?']})}]}]}
        with patch('hunt.fetch_json',return_value=response) as request,patch('hunt.load_key',return_value='test-key'):
            selection,_,_=hunt.ai_select(self.j,[{'id':'known','text':'Verified experience','source':'private-source-url'}])
            body=request.call_args.args[1];self.assertFalse(body['store']);self.assertNotIn('private-source-url',body['input']);self.assertNotIn('tools',body)
            self.assertIn(selection['requirement_quote'],self.j['description'])
    def test_sync_source_mismatch_denied(self):
        with self.assertRaisesRegex(ValueError,'source/account'):hunt.sync_tracker_snapshot({'sheet_id':'wrong','email':'wrong'})
    def test_sync_preserves_missing_and_is_idempotent(self):
        with hunt.db() as c:
            for key,val in [('email','me@example.test'),('sheet_id','sheet')]:c.execute('INSERT INTO kv VALUES(?,?)',(key,json.dumps(val)))
            c.execute('INSERT INTO applications VALUES(?,?,?,?,?,?,?,?,?,?)',('older','Old company','Recruiter','2026-09-01','Rejected','2026-09-02','link','',2,'{}'))
        snap={'sheet_id':'sheet','email':'me@example.test','verified_at':hunt.now(),'rows':[['S/N','Company','Role','Applied / first email','Latest email','Current status','Response type','Follow-up priority','Email evidence','Notes'],['1','Acme','Recruiter','2026-11-01','2026-11-02','Rejected','Decision received','Closed','link','']]}
        self.assertEqual(hunt.sync_tracker_snapshot(snap)['changed'],1)
        self.assertEqual(hunt.sync_tracker_snapshot(snap)['changed'],0)
        with hunt.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM applications').fetchone()[0],2)

if __name__=='__main__':unittest.main(verbosity=2)
