import base64,hashlib,io,json,tempfile,unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch
from application_channels import EmailAdapter
from application_execution import ApplicationExecution
from application_runner import runner_db
from native_google_cv import private_json
class EmailTests(unittest.TestCase):
 def test_exact_pdf_is_sent_once_and_gmail_receipt_does_not_claim_employer_acknowledgement(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);private_json(root/'data/application-google.json',{'account':'majekadegbeaminat85@gmail.com','scopes':['https://www.googleapis.com/auth/gmail.send'],'client_id':'fixture','client_secret':'fixture','refresh_token':'fixture'})
   file=root/'CV.pdf';file.write_bytes(b'%PDF- fixture only');sha=hashlib.sha256(file.read_bytes()).hexdigest();posts=[]
   class Opener:
    def open(self,request,timeout=0):
     if request.full_url.endswith('/token'):return io.BytesIO(b'{"access_token":"fixture"}')
     self_message=BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(json.loads(request.data)['raw']+'==='));posts.append(self_message);return io.BytesIO(b'{"id":"abcdef1234567890","threadId":"abcdef0987654321"}')
   route={'url':'https://employer.example/job','recipient':'careers@employer.example','recipient_source':'https://employer.example/job','recipient_verified':True}
   adapter=EmailAdapter(root,route,'Fixture Employer','Recruiter','Verified recruitment experience.');engine=ApplicationExecution(runner_db(root),lambda p:None)
   meta={'package_id':'p','package_hash':'hash','sha256':sha,'filename':'CV.pdf','document_version':'v'}
   plan=engine.plan(job_id='j',job_version='v',package_id='p',package_hash='hash',form=adapter.inspect(),answers={},uploads={'resume':file},cv_artifact=meta);engine.approve(plan['id'],plan['payload_hash'],'owner-saved-policy')
   with patch('urllib.request.build_opener',return_value=Opener()):result=engine.execute(plan['id'],adapter)
   self.assertEqual(result['status'],'submitted');self.assertEqual(result['receipt']['channel'],'email');self.assertIn('acknowledgement pending',result['receipt']['confirmation_text']);self.assertEqual(len(posts),1);self.assertEqual(str(posts[0]['To']),route['recipient']);self.assertEqual(next(posts[0].iter_attachments()).get_payload(decode=True),file.read_bytes())
   engine.execute(plan['id'],adapter);self.assertEqual(len(posts),1)
if __name__=='__main__':unittest.main()
