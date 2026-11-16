import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from mac_application_worker import verified_contact_answers
class ContactTests(unittest.TestCase):
 def test_required_company_is_read_from_current_verified_cv_and_star_labels_are_supported(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'data').mkdir();source='Fixture Candidate\nfixture@example.test\nPROFESSIONAL EXPERIENCE\nCurrent Employer\tRemote\nHR Officer\t2025 - Present\nEDUCATION\n';(root/'data/master-cv.txt').write_text(source)
   context={'package':{'master_cv_source_hash':hashlib.sha256(source.encode()).hexdigest()}};form={'questions':[{'id':'company','label':'Current company ✱','type':'text'},{'id':'name','label':'Full name ✱','type':'text'}]};answers=verified_contact_answers(form,context,root);self.assertEqual(answers['company']['value'],'Current Employer');self.assertEqual(answers['name']['value'],'Fixture Candidate')
 def test_only_verified_contacts_are_filled_and_consent_is_never_inferred(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'data').mkdir();source='Fixture Candidate\nHR Professional\nfixture@example.test\n+2349012345678\n';(root/'data/master-cv.txt').write_text(source)
   context={'package':{'master_cv_source_hash':hashlib.sha256(source.encode()).hexdigest()}}
   form={'questions':[{'id':'name','label':'Full name *','type':'text'},{'id':'email','label':'Email *','type':'email'},{'id':'auth','label':'Are you authorized to work in the US?','type':'text'},{'id':'consent','label':'Consent','type':'checkbox'},{'id':'salary','label':'Desired salary','type':'text'}]}
   answers=verified_contact_answers(form,context,root);self.assertEqual(set(answers),{'name','email'});self.assertEqual(answers['name']['source'],'verified_profile')
   bad=copy.deepcopy(context);bad['package']['master_cv_source_hash']='changed';self.assertEqual(verified_contact_answers(form,bad,root),{})
if __name__=='__main__':unittest.main()
