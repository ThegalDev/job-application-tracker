import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import hunt
import services
from orchestrator import ToolContext

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=(hunt.DATA,hunt.DB)
        hunt.DATA=Path(self.tmp.name);hunt.DB=hunt.DATA/'test.sqlite3';hunt.init()
        with hunt.db() as c:services.install(c)
    def tearDown(self):hunt.DATA,hunt.DB=self.old;self.tmp.cleanup()
    def test_operating_schedule_exact_wat(self):
        self.assertEqual([(x['time'],x.get('trigger')) for x in services.SCHEDULE_WAT[:5]],[('07:00','discovery'),('08:00','shortlist'),('12:00','discovery'),('16:00','pipeline'),('18:00','discovery')])
        self.assertEqual(services.SCHEDULE_WAT[-1]['weekday'],4);self.assertEqual(services.SCHEDULE_WAT[-1]['time'],'18:30')
    def test_schedule_once_each_slot(self):
        at=dt.datetime(2026,11,12,7,1,tzinfo=services.WAT)
        self.assertEqual(len(services.due_schedule(hunt,at)),1)
        with patch('services.run_pipeline',return_value={'status':'success'}) as run:
            self.assertEqual(len(services.tick_schedule(hunt,at)),1)
            self.assertEqual(services.tick_schedule(hunt,at),[])
            self.assertEqual(run.call_count,1)
    def test_pause_prevents_scheduler(self):
        with hunt.db() as c:c.execute("UPDATE kv SET value='true' WHERE key='paused'")
        with patch('services.run_pipeline') as run:
            self.assertEqual(services.tick_schedule(hunt),[]);run.assert_not_called()
    def test_reports_do_not_invent_progress(self):
        with hunt.db() as c:
            c.execute('INSERT INTO applications VALUES(?,?,?,?,?,?,?,?,?,?)',('a','Acme','Recruiter','2026-11-01','Application acknowledged','2026-11-01','','',2,'{}'))
            c.execute('INSERT INTO mail_events VALUES(?,?,?,?,?,?,?)',('m',hunt.now(),'Acme','Recruiter','Application acknowledged','link','verified'))
        report=services.make_report(hunt,'weekly')
        self.assertEqual(report['applications_total'],1);self.assertEqual(report['interview_invitations_observed'],0);self.assertEqual(report['offers_observed'],0)
        self.assertEqual(report['recruitment_events']['Application acknowledged'],1)
    def test_missing_google_is_blocked_truthfully(self):
        with patch('google_provider.GoogleProvider.configured',return_value=False):s=services.run_pipeline(hunt,'pipeline',use_ai=False)
        self.assertEqual(s['status'],'blocked');result=s['tasks'][0]['result'];self.assertIn('no fresh inbox',result['reason'])
    def test_discovery_and_match_are_actual_tools(self):
        with patch('hunt.discover',return_value=[{'status':'success','source':'test','jobs':0}]) as discover:
            s=services.run_pipeline(hunt,'discovery',use_ai=False)
        self.assertEqual(s['status'],'success');discover.assert_called_once();self.assertEqual(s['tasks'][1]['result']['scoring_version'],'prd-1.0')
    def test_no_qualified_job_no_paid_generation(self):
        with patch('hunt.package') as package:
            s=services.run_pipeline(hunt,'shortlist',use_ai=False)
        self.assertEqual(s['status'],'success');package.assert_not_called();self.assertEqual(s['tasks'][2]['result']['package_ids'],[])
    def test_stale_silence_recommends_review_without_status_change(self):
        with hunt.db() as c:c.execute('INSERT INTO applications VALUES(?,?,?,?,?,?,?,?,?,?)',('a','Acme','Recruiter','2026-01-01','Application acknowledged','2026-01-01','link','',2,'{}'))
        queue=services.refresh_pipeline_queue(hunt,dt.datetime(2026,11,12,tzinfo=dt.timezone.utc))
        self.assertEqual(queue[0]['kind'],'consider_followup');self.assertIn('not an employer deadline',queue[0]['basis'])
        services.refresh_pipeline_queue(hunt)
        with hunt.db() as c:
            self.assertEqual(c.execute('SELECT status FROM applications').fetchone()[0],'Application acknowledged')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM pipeline_actions').fetchone()[0],1)
    def test_rejected_role_never_has_followup_recommendation(self):
        with hunt.db() as c:c.execute('INSERT INTO applications VALUES(?,?,?,?,?,?,?,?,?,?)',('a','Acme','Recruiter','2026-01-01','Rejected','2026-01-01','link','',2,'{}'))
        self.assertEqual(services.refresh_pipeline_queue(hunt),[])
    def test_application_studio_reuses_current_package(self):
        assessment={'tier':'A','score':90,'compensation':{'status':'meets_floor'},'duplicate_applications':[]}
        with hunt.db() as c:
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('j','acme people ops','ashby','acme','Acme','People Ops','Nigeria','https://jobs.ashbyhq.com/acme/j','Own onboarding',None,None,hunt.now(),hunt.now(),1,hunt.dump(assessment),'v'))
            c.execute('INSERT INTO packages VALUES(?,?,?,?,?,?)',('p','j',hunt.now(),hunt.dump({'job_version':'v'}),'hash','review'))
        engine=services.runtime(hunt);ctx=ToolContext('r','t','application_studio','key',lambda:None,{})
        with patch('hunt.package') as package:result=engine.tools['prepare_applications'].handler(ctx,{'use_ai':True})
        package.assert_not_called();self.assertEqual(result['package_ids'],['p'])
    def test_report_period_validated(self):
        with self.assertRaises(ValueError):services.make_report(hunt,'forever')
    def test_message_decode_bounded(self):
        import base64
        text='Application received'
        raw=base64.urlsafe_b64encode(text.encode()).decode().rstrip('=')
        self.assertEqual(services._mail_text({'mimeType':'multipart/mixed','parts':[{'mimeType':'text/plain','body':{'data':raw}}]}),text)
    def test_outreach_is_distinct_persistent_draft(self):
        package={'job_id':'j','job_version':'v','company':'Acme','role':'People Ops','facts':[{'id':'f','text':'Built onboarding workflows','source':'cv'}],'selection':{'requirement_quote':'Own onboarding'}}
        with hunt.db() as c:
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('j','acme people ops','ashby','acme','Acme','People Ops','Nigeria','https://jobs.ashbyhq.com/acme/j','Own onboarding',None,None,hunt.now(),hunt.now(),1,'{}','v'))
            c.execute('INSERT INTO packages VALUES(?,?,?,?,?,?)',('p','j',hunt.now(),hunt.dump(package),hunt.digest(package),'review'))
        engine=services.runtime(hunt);ctx=ToolContext('r','t','outreach','key',lambda:None,{'application_studio':{'package_ids':['p']}})
        result=engine.tools['prepare_outreach'].handler(ctx,{})
        self.assertEqual(result['recipient_verification_needed'],1);self.assertEqual(result['external_actions'],0)
        with hunt.db() as c:
            draft=c.execute('SELECT * FROM outreach_drafts').fetchone();data=json.loads(draft['payload'])
            self.assertIsNone(data['recipient']);self.assertEqual(data['fact_ids'],['f']);self.assertIn('Built onboarding workflows',data['body'])

if __name__=='__main__':unittest.main()
