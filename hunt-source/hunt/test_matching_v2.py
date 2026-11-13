import unittest
import matching

class MatchingV2(unittest.TestCase):
    def job(self,description='',location='Remote worldwide'):
        return {'id':'j','company':'Acme','title':'People Operations Specialist','description':description,'location':location}
    def test_exact_weights(self):
        a=matching.score_job(self.job('Own onboarding. Full-time. USD 3000 per month'),[{'id':'a','text':'Managed onboarding','source':'cv'}],{},[])
        self.assertEqual(a['weights'],{'skills':30,'eligibility':25,'compensation':15,'progression':15,'company':10,'preferences':5})
        self.assertEqual(a['score'],round(sum(a['weights'][k]*a['ratings'][k]/100 for k in a['weights']),2))
    def test_floor_cannot_be_disabled(self):
        self.assertEqual(matching.eligibility(self.job('USD 1000 - 2000 per month'),{'salary_is_hard_floor':False,'monthly_usd':500})['tier'],'D')
    def test_floor_is_inclusive(self):self.assertEqual(matching.eligibility(self.job('USD 30000 per year'),{})['compensation']['status'],'meets_floor')
    def test_range_crossing_floor_unknown_offer(self):
        self.assertEqual(matching.eligibility(self.job('USD 2000 – 3500 per month'),{})['compensation']['status'],'range_crosses_floor')
    def test_currency_never_assumed(self):self.assertEqual(matching.eligibility(self.job('$3000 per month'),{})['salary'],'Unknown')
    def test_k_annual(self):self.assertEqual(matching.eligibility(self.job('USD 30k - 40k annually'),{})['compensation']['monthly_min'],2500)
    def test_ambiguity_not_promoted(self):
        a=matching.score_job(self.job('Own onboarding',location='Remote'),[],{},[])
        self.assertEqual(a['tier'],'C');self.assertEqual(a['ratings']['eligibility'],0);self.assertEqual(a['ratings']['compensation'],0)
    def test_contradictions_win(self):
        for desc in ['Applicants must be based in Germany.','We cannot hire in Nigeria.','This role is US-only.']:
            with self.subTest(desc=desc):self.assertEqual(matching.eligibility(self.job(desc),{})['tier'],'D')
    def test_negated_sponsorship(self):
        for desc in ['We do not offer visa sponsorship.','We do not provide visa sponsorship.','We are unable to provide visa sponsorship.']:
            with self.subTest(desc=desc):self.assertEqual(matching.eligibility(self.job(desc,'London'),{})['tier'],'D')
    def test_regional_inclusion(self):self.assertEqual(matching.eligibility(self.job('Hiring in Nigeria.','Remote EMEA'),{})['tier'],'B')
    def test_decision_boundaries(self):
        for score,band in [(54.99,'Archive'),(55,'Explore'),(69.99,'Explore'),(70,'Review'),(84.99,'Review'),(85,'Priority')]:
            self.assertEqual(matching.decision_band(score),band)
    def test_unknown_geographic_restriction_is_not_promoted(self):
        descriptions=['This role is restricted to residents of the United States.','Unfortunately we do not support hiring in Nigeria.','We hire remotely from the following countries only: Canada, UK, Germany.','Candidates are required to live in Japan.','Nigeria is excluded from our supported employment countries.']
        for text in descriptions:self.assertNotIn(matching.eligibility(self.job(text),{})['tier'],('A','B'))
    def test_allowance_is_not_salary(self):
        self.assertEqual(matching.eligibility(self.job('We offer a home office allowance of USD 100 per month. Salary is competitive.'),{})['salary'],'Unknown')
    def test_fetched_company_quote_not_authority(self):
        j=self.job();j['company_evidence']=[{'verified':True,'source':'https://example.org','quote':'Some fetched content'}]
        self.assertEqual(matching.score_job(j,[],{},[])['ratings']['company'],0)
    def test_traceable_skill_evidence(self):
        j=self.job('Own onboarding and performance management');f={'id':'a','text':'Managed onboarding','source':'cv'}
        a=matching.score_job(j,[f],{},[])
        self.assertEqual(a['ratings']['skills'],50)
        self.assertIn(a['matches'][0]['job_quote'],j['description']);self.assertEqual(a['matches'][0]['fact_id'],'a')
    def test_employer_evidence_not_assumed(self):
        self.assertEqual(matching.score_job(self.job(),[],{},[])['ratings']['company'],0)
    def test_disqualified_high_skills_still_excluded(self):
        a=matching.score_job(self.job('Own onboarding. USD 2000 per month'),[{'id':'a','text':'Managed onboarding','source':'cv'}],{},[])
        self.assertEqual(a['status'],'Excluded')

if __name__=='__main__':unittest.main()
