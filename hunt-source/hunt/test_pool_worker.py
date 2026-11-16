import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pool_worker
from standing_authorization import save_authorization
from autonomous_answers import complete_answers

class PoolTests(unittest.TestCase):
 def test_failed_job_is_persisted_and_next_tick_moves_to_next_even_if_irrelevant(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);save_authorization(root/'data','owner',selection_mode='apply_available',providers=['lever','breezy','html','email'])
   rows=[{'job_id':'j1','job_version':'v1','company':'One','title':'Engineer','role_relevant':False},{'job_id':'j2','job_version':'v2','company':'Two','title':'Recruiter'}]
   calls=[]
   class Client:
    def __init__(self,*a):pass
    def checkpoint(self,payload):pass
    def request(self,path,body=None):
     calls.append((path,body))
     return {'paused':False,'candidates':rows} if 'candidates' in path else {'ok':True}
   class Engine:
    def held_job_ids(self):return set()
   def process(client,candidate,*args):
    if candidate['job_id']=='j1':raise TimeoutError('unreachable')
    return {'status':'missing_facts','message':'Other jobs continue; no prompt required'}
   with patch('pool_worker.RoutedConnection',Client),patch('pool_worker.load_owner_key',return_value='fixture'),patch('pool_worker.autonomous_engine',return_value=(Engine(),{})),patch('pool_worker.process',side_effect=process) as worker:
    pool_worker.tick(root);pool_worker.tick(root);pool_worker.tick(root)
    self.assertEqual([c.args[1]['job_id'] for c in worker.call_args_list],['j1','j2'])
    journal=json.loads((root/'data/pool-attempts.json').read_text());self.assertEqual({r['status'] for r in journal.values()},{'unreachable','missing_facts'})
    self.assertTrue(any('batch-report' in p for p,b in calls));self.assertTrue(any('all_routes=1' in p for p,b in calls))
 def test_inspection_only_stops_before_cv_generation_or_upload(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);policy=save_authorization(root/'data','owner',selection_mode='apply_available',providers=['lever','breezy','html','email'])
   with patch('pool_worker.resolve_candidate',return_value={'status':'ready','provider':'html','url':'https://employer.example/apply'}),patch('pool_worker.prepare_source_native_package') as prepare,patch('pool_worker.form_adapter') as adapter:
    result=pool_worker.process(None,{'job_id':'j','job_version':'v','application_url':'https://employer.example/apply'},None,policy,root)
    self.assertEqual(result['status'],'awaiting_authorization');prepare.assert_not_called();adapter.assert_not_called()
 def test_saved_us_answers_are_country_scoped_and_unknown_numbers_are_not_invented(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'data').mkdir();(root/'data/master-cv.txt').write_text('PROFESSIONAL SUMMARY\nVerified HR experience.\nCORE COMPETENCIES\nRecruitment')
   (root/'data/application-answer-profile.json').write_text(json.dumps({'us_work_authorized':'Yes','us_visa_sponsorship':'Yes'}))
   form={'questions':[{'id':'us','label':'Are you authorized to work in the United States?','type':'radio','options':['Yes','No']},{'id':'ca','label':'Are you authorized to work in Canada?','type':'radio','options':['Yes','No']},{'id':'years','label':'Years of offshore engineering experience','type':'text','input_type':'number'},{'id':'why','label':'Why this role?','type':'textarea'}]}
   a=complete_answers(form,{},root,{});self.assertEqual(a['us']['value'],'Yes');self.assertNotIn('ca',a);self.assertNotIn('years',a);self.assertIn('Verified HR experience',a['why']['value'])
if __name__=='__main__':unittest.main()
