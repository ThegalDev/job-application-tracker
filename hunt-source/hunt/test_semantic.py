import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import hunt,semantic

class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=(hunt.DATA,hunt.DB);hunt.DATA=Path(self.tmp.name);hunt.DB=hunt.DATA/'test.sqlite3';hunt.init()
        self.job={'id':'j','raw_hash':'v','title':'People Ops','description':'Own employee onboarding and improve HR workflow automation.'}
        with hunt.db() as c:
            c.execute('INSERT INTO facts VALUES(?,?,?)',('onboarding','Coordinated employee onboarding.','private-cv-url'))
            c.execute('INSERT INTO facts VALUES(?,?,?)',('not-approved','Private unrelated career statement.','private-cv-url'))
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('j','j','ashby','test','Test','People Ops','Nigeria','https://jobs.ashbyhq.com/test/j',self.job['description'],None,None,hunt.now(),hunt.now(),1,'{}','v'))
    def tearDown(self):hunt.DATA,hunt.DB=self.old;self.tmp.cleanup()
    def response(self,ids):return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'requirements':[{'source_index':0,'required':True,'fact_ids':ids}]})}]}]}
    def test_only_approved_facts_transmitted(self):
        with patch('hunt.load_key',return_value='test'),patch('hunt.fetch_json',return_value=self.response(['onboarding'])) as req:
            r=semantic.assess(hunt,self.job)
            payload=req.call_args.args[1];self.assertNotIn('not-approved',payload['input']);self.assertNotIn('private-cv-url',payload['input']);self.assertFalse(payload['store']);self.assertNotIn('tools',payload)
            self.assertIn(r['requirements'][0]['job_quote'],self.job['description']);self.assertEqual(r['skills_rating'],100)
    def test_invented_fact_denied(self):
        with patch('hunt.load_key',return_value='test'),patch('hunt.fetch_json',return_value=self.response(['invented'])):
            with self.assertRaises(ValueError):semantic.assess(hunt,self.job)
    def test_unproven_requirement_receives_zero(self):
        with patch('hunt.load_key',return_value='test'),patch('hunt.fetch_json',return_value=self.response([])):
            self.assertEqual(semantic.assess(hunt,self.job)['skills_rating'],0)
    def test_no_persistence_after_posting_change(self):
        with hunt.db() as c:c.execute("UPDATE jobs SET raw_hash='changed'")
        with patch('hunt.load_key',return_value='test'),patch('hunt.fetch_json',return_value=self.response(['onboarding'])):
            with self.assertRaisesRegex(ValueError,'Job changed'):semantic.assess(hunt,self.job)

if __name__=='__main__':unittest.main()
