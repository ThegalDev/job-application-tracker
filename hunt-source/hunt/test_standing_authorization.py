import tempfile
import unittest
from pathlib import Path
import standing_authorization as standing
from application_runner import runner_db
from test_application_execution import FixtureAdapter
class StandingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.policy=standing.save_authorization(self.root,'fixture-owner');self.engine,_=standing.autonomous_engine(runner_db(self.root),lambda p:None,self.root)
  self.form={'url':'https://employer.test/jobs/one','action_url':'https://employer.test/apply','questions':[{'id':'name','label':'Name','type':'text','required':True}]}
 def tearDown(self):self.tmp.cleanup()
 def plan(self,answers):return self.engine.plan(job_id='j',job_version='v',package_id='p',package_hash='h',form=self.form,answers=answers)
 def test_submits_without_per_application_owner_approval_and_records_policy(self):
  p=self.plan({'name':{'value':'Fixture Candidate','source':'verified_profile','verified':True}});adapter=FixtureAdapter();r=standing.execute_under_standing_authorization(self.engine,p['id'],adapter,self.policy,self.root);self.assertEqual(r['status'],'submitted');self.assertTrue(r['approved_by'].startswith('standing-owner-authorization:'));self.assertEqual(adapter.submissions,1)
  standing.execute_under_standing_authorization(self.engine,p['id'],adapter,self.policy,self.root);self.assertEqual(adapter.submissions,1)
 def test_available_mode_is_an_explicit_persisted_owner_choice(self):
  policy=standing.save_authorization(self.root,'owner requested available-role applications',True,selection_mode='apply_available');self.assertTrue(policy['fit_preferences_only']);self.assertEqual(standing.read_authorization(self.root)['selection_mode'],'apply_available')
 def test_missing_facts_pause_instead_of_requesting_approval_or_guessing(self):
  p=self.plan({});adapter=FixtureAdapter();r=standing.execute_under_standing_authorization(self.engine,p['id'],adapter,self.policy,self.root);self.assertEqual(r['status'],'needs_input');self.assertEqual(adapter.submissions,0)
 def test_revocation_stops_execution(self):
  p=self.plan({'name':{'value':'Fixture Candidate','source':'owner_answer','verified':True}});standing.save_authorization(self.root,'fixture-owner',False);adapter=FixtureAdapter()
  with self.assertRaises(ValueError):standing.execute_under_standing_authorization(self.engine,p['id'],adapter,self.policy,self.root)
  self.assertEqual(adapter.submissions,0)
 def test_revocation_during_fill_prevents_final_submission(self):
  p=self.plan({'name':{'value':'Fixture Candidate','source':'owner_answer','verified':True}});adapter=FixtureAdapter();adapter.on_fill=lambda:standing.save_authorization(self.root,'fixture-owner',False)
  with self.assertRaises(RuntimeError):standing.execute_under_standing_authorization(self.engine,p['id'],adapter,self.policy,self.root)
  self.assertEqual(adapter.submissions,0)
if __name__=='__main__':unittest.main()
