import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from application_runner import HUNTConnection,validate_context,lever_url
import application_execution as execution

URL='https://jobs.lever.co/fixture/11111111-1111-1111-1111-111111111111'
class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.sha='a'*64
        self.meta={'package_id':'p','package_hash':'hash','sha256':self.sha,'filename':'CV.docx','document_version':'fixture'}
        self.context={'paused':False,'job':{'id':'j','raw_hash':'v','open':True,'hidden':False,'within_discovery_window':True,'publication_verified_original':True,'global_remote':True,'application_url':URL,'assessment':{'tier':'A','score':90,'role_relevant':True,'compensation':{'status':'meets_floor','monthly_min':3000},'duplicate_applications':[]}},'package':{'id':'p','payload_hash':'hash','job_version':'v','status':'review','writing_profile_current':True,'master_cv_current':True},'cv_artifact':self.meta}
        self.payload={'job_id':'j','job_version':'v','package_id':'p','package_hash':'hash','cv_artifact':self.meta,'uploads':{'resume':{'sha256':self.sha}},'application_url':URL+'/apply'}
    def test_supported_exact_form_and_reviewed_file_pass(self):validate_context(self.context,self.payload)
    def test_all_current_application_gates_fail_closed(self):
        changes=[('paused',True),('job.hidden',True),('job.open',False),('job.within_discovery_window',False),('job.global_remote',False),('job.raw_hash','changed'),('job.assessment.tier','C'),('job.assessment.compensation.monthly_min',2499),('job.assessment.compensation.status','unknown'),('job.assessment.duplicate_applications',['prior']),('job.assessment.duplicate_listing_of','prior'),('package.status','requires_revision'),('package.master_cv_current',False),('package.writing_profile_current',False),('package.payload_hash','changed'),('cv_artifact.sha256','b'*64)]
        for field,value in changes:
            with self.subTest(field=field):
                ctx=copy.deepcopy(self.context);target=ctx
                for key in field.split('.')[:-1]:target=target[key]
                target[field.split('.')[-1]]=value
                with self.assertRaises(ValueError):validate_context(ctx,self.payload)
    def test_employer_identity_must_match_exact_role(self):
        for url in ['http://jobs.lever.co/fixture/11111111-1111-1111-1111-111111111111','https://evil.example/x','https://jobs.lever.co@evil.example/x',URL+'?redirect=evil',URL+'#apply','https://jobs.lever.co:8443/x']:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):lever_url(url)
        changed={**self.payload,'application_url':URL.replace('/fixture/','/other/')}
        with self.assertRaises(ValueError):validate_context(self.context,changed)
    def test_download_rejects_changed_bytes_and_pins_package_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            client=HUNTConnection('fixture-key',tmp);raw=b'PK exact reviewed fixture';context=copy.deepcopy(self.context);context['cv_artifact']['sha256']=hashlib.sha256(raw).hexdigest();calls=[]
            def request(path,binary=False):calls.append(path);self.assertTrue(binary);return raw
            client.request=request
            target=client.download_cv(context);self.assertEqual(target.read_bytes(),raw);self.assertIn('id=p&hash=hash',calls[0]);self.assertEqual(target.stat().st_mode&0o777,0o600)
            target.write_bytes(b'PK altered');
            with self.assertRaises(ValueError):client.download_cv(context)
            client.request=lambda *a,**k:b'PK wrong file'
            with self.assertRaises(ValueError):client.download_cv(context)
    def test_plan_rejects_wrong_reviewed_file_before_creating_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            from application_runner import runner_db
            engine=execution.ApplicationExecution(runner_db(tmp),lambda p:None)
            file=Path(tmp)/'cv.docx';file.write_bytes(b'fixture file')
            form={'url':URL,'action_url':URL,'provider':'lever','questions':[{'id':'resume','label':'Resume','type':'file','required':True}]}
            with self.assertRaisesRegex(ValueError,'exact reviewed CV'):engine.plan(job_id='j',job_version='v',package_id='p',package_hash='hash',form=form,answers={},uploads={'resume':file},cv_artifact=self.meta)
            artifact={**self.meta,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()};plan=engine.plan(job_id='j',job_version='v',package_id='p',package_hash='hash',form=form,answers={},uploads={'resume':file},cv_artifact=artifact);self.assertEqual(plan['payload']['cv_artifact']['sha256'],artifact['sha256']);self.assertEqual(plan['status'],'review')
if __name__=='__main__':unittest.main()
