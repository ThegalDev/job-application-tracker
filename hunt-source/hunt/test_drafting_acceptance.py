"""Remediation acceptance: preserve the actual full CV; keep API inputs bounded.

Every provider result is mocked. These tests never load a real key or use a network.
"""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import drafting
import hunt

IDS = ('lifecycle', 'recruitment', 'notion', 'make', 'records', 'onboarding', 'policies', 'performance')
FACTS = [{'id': ident, 'text': 'Verified work in ' + ident + '.',
          'source': 'https://private-source.test/' + ident,
          'private_notes': 'PRIVATE_METADATA_SENTINEL'} for ident in IDS]
JOB = {'company': 'Fixture International', 'title': 'People Operations Specialist',
       'description': 'Build reliable people systems for a distributed team.',
       'private_notes': 'PRIVATE_JOB_METADATA_SENTINEL',
       'contact_email': 'private-contact@example.test',
       'raw_mail': 'PRIVATE_MAIL_SENTINEL'}
RESULT = {'cover_letter': 'Your distributed team needs reliable people systems.\n\nMy lifecycle work gives me a relevant foundation.',
          'cold_email_subject': 'The human side of a reliable system',
          'cold_email': 'Your distributed team needs systems that keep people in view.\n\nI have built relevant lifecycle processes. Please put this application before the person leading the search.',
          'cv_summary': 'People Operations professional with verified lifecycle and systems experience.',
          'fact_ids': ['lifecycle']}


def response(result):
    return {'status': 'completed', 'id': 'fixture-response', 'usage': {'output_tokens': 200},
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(result)}]}]}


class FullCvPreservationAcceptance(unittest.TestCase):
    def test_actual_master_cv_changes_only_summary_region(self):
        # decode bytes rather than read_text: preserve the original CRLF and BOM.
        source = (Path(__file__).parent / 'data/master-cv.txt').read_bytes().decode('utf-8')
        heading_end = source.index('\n', source.index('PROFESSIONAL SUMMARY')) + 1
        competencies_start = source.index('CORE COMPETENCIES', heading_end)
        prefix, suffix = source[:heading_end], source[competencies_start:]
        summary = 'An evidence-backed tailored summary for this fixture.'
        tailored = drafting.preserve_resume(source, summary)
        self.assertTrue(tailored.startswith(prefix))
        self.assertEqual(tailored[tailored.index('CORE COMPETENCIES'):], suffix)
        self.assertEqual(tailored, prefix + summary + '\n\n' + suffix)
        self.assertGreater(len(suffix), 15000, 'Fixture must cover full chronology and projects, not a short excerpt')
        for marker in ['Shae Group', 'GT Powertank', 'Palmpay', 'Culturecore',
                       'AI Career Coach', 'Recruitment Operating System',
                       'Leave Management Automation', 'ClickBot Accountability System']:
            with self.subTest(marker=marker):
                self.assertEqual(tailored[tailored.index('CORE COMPETENCIES'):].count(marker), suffix.count(marker))

    def test_no_tailoring_returns_entire_source_unchanged(self):
        source = '\ufeffHEADER\r\nPROFESSIONAL SUMMARY  \r\nOriginal.\r\nCORE COMPETENCIES\r\nEvery detail.\r\n'
        self.assertEqual(drafting.preserve_resume(source), source)
        self.assertEqual(drafting.preserve_resume(source, ''), source)

    def test_unknown_cv_structure_blocks_instead_of_shortening(self):
        with self.assertRaises(ValueError): drafting.preserve_resume('A full CV without a recognized summary boundary.', 'New summary')

    def test_public_resume_builder_does_not_reduce_to_selected_facts(self):
        source = 'HEADER\nPROFESSIONAL SUMMARY\nOld summary.\nCORE COMPETENCIES\nUnselected role, education, project and training content.\n'
        self.assertEqual(hunt.build_resume(source, [FACTS[0]], 'Tailored summary'),
                         'HEADER\nPROFESSIONAL SUMMARY\nTailored summary\n\nCORE COMPETENCIES\nUnselected role, education, project and training content.\n')


class DraftPrivacyAndEvidenceAcceptance(unittest.TestCase):
    def generate(self, result=None, facts=None, job=None):
        with patch.object(hunt, 'load_key', return_value='fixture-key'), \
             patch.object(hunt, 'value_for', return_value='https://example.test/portfolio'), \
             patch.object(hunt, 'fetch_json', return_value=response(result or RESULT)) as fetch:
            output = drafting.generate(hunt, job or JOB, facts or FACTS)
            return output, fetch.call_args.args[1]

    def test_exactly_eight_approved_excerpts_sent_without_private_metadata(self):
        facts = FACTS + [{'id': 'private-anecdote', 'text': 'PRIVATE_ANECDOTE_SENTINEL', 'source': 'private'}]
        _, body = self.generate(facts=facts)
        decoded = json.loads(body['input'])
        self.assertEqual(decoded['approved_facts'], [{'id': f['id'], 'text': f['text']} for f in FACTS])
        self.assertEqual({f['id'] for f in decoded['approved_facts']}, set(IDS))
        for sentinel in ['PRIVATE_', 'private-source.test', 'private-contact@example.test',
                         '9072546155', 'majekadegbeaminat85@gmail.com', 'PROFESSIONAL EXPERIENCE']:
            with self.subTest(sentinel=sentinel): self.assertNotIn(sentinel, body['input'])
        self.assertFalse(body['store'])
        self.assertNotIn('tools', body)
        self.assertEqual(body['text']['format']['schema']['properties']['fact_ids']['items']['enum'], list(IDS))

    def test_unapproved_only_fact_set_never_calls_provider(self):
        with patch.object(hunt, 'load_key') as key, patch.object(hunt, 'fetch_json') as fetch:
            with self.assertRaises(ValueError):
                drafting.generate(hunt, JOB, [{'id': 'private-anecdote', 'text': 'Private story'}])
            key.assert_not_called()
            fetch.assert_not_called()

    def test_response_cannot_cite_an_unapproved_private_fact(self):
        result = {**RESULT, 'fact_ids': ['private-anecdote']}
        with self.assertRaises(ValueError): self.generate(result)

    def test_employer_number_does_not_license_invented_candidate_achievement(self):
        result = {**RESULT, 'cover_letter': 'I reduced employee turnover by 42%.'}
        job = {**JOB, 'description': 'Our employer target is to reduce turnover by 42%.'}
        with self.assertRaises(ValueError): self.generate(result, job=job)

    def test_number_in_uncited_fact_does_not_license_candidate_claim(self):
        facts = copy.deepcopy(FACTS)
        facts[4]['text'] = 'Managed records for 1000 employees.'
        result = {**RESULT, 'fact_ids': ['lifecycle'], 'cover_letter': 'I managed records for 1000 employees.'}
        with self.assertRaises(ValueError): self.generate(result, facts=facts)

    def test_number_substring_is_not_a_verified_metric(self):
        facts = copy.deepcopy(FACTS)
        facts[0]['text'] = 'Managed records for 1000 employees.'
        result = {**RESULT, 'cover_letter': 'I managed records for 100 employees.'}
        with self.assertRaises(ValueError): self.generate(result, facts=facts)

    def test_distinct_cover_and_outreach_and_applied_profile_are_inspectable(self):
        (result, _, _), _ = self.generate()
        profile = json.loads((Path(__file__).parent / 'writing-profile.json').read_text())
        self.assertEqual(result['writing_profile_version'], profile['version'])
        self.assertNotEqual(result['cover_letter'], result['cold_email'])
        self.assertIn('review', result['claim_review'].lower())
        with self.assertRaises(ValueError): self.generate({**RESULT, 'cold_email': RESULT['cover_letter']})

    def test_rejected_generic_openings_are_not_accepted_as_personalized(self):
        for phrase in ['I hope this email finds you well', 'I am excited to apply']:
            with self.subTest(phrase=phrase), self.assertRaises(ValueError):
                self.generate({**RESULT, 'cold_email': phrase + '. I have relevant experience.'})

    def test_incomplete_provider_result_is_not_a_successful_draft(self):
        with patch.object(hunt, 'load_key', return_value='fixture-key'), \
             patch.object(hunt, 'fetch_json', return_value={'status': 'incomplete'}):
            with self.assertRaises(ValueError): drafting.generate(hunt, JOB, FACTS)

    def test_source_backed_day_one_reference_becomes_words_without_licensing_candidate_numbers(self):
        for token in ['Day 1', 'Day1']:
            with self.subTest(token=token):
                job = {**JOB, 'description': 'Coordinate ' + token + ' readiness for every cohort.'}
                result = {**RESULT, 'cover_letter': 'Your ' + token + ' readiness depends on reliable coordination.\n\nMy verified lifecycle work is relevant.',
                          'cold_email_subject': 'The welcome before ' + token}
                (draft, _, _), _ = self.generate(result, job=job)
                self.assertIn('first day', draft['cover_letter'].lower())
                self.assertNotRegex(draft['cover_letter'], r'\b1\b')
                self.assertNotRegex(draft['cold_email_subject'], r'\b1\b')
        job = {**JOB, 'description': 'Coordinate Day 1 readiness for every cohort.'}
        with self.assertRaises(ValueError):
            self.generate({**RESULT, 'cover_letter': 'I supported 1 employee.'}, job=job)

    def test_day_one_reference_without_public_source_is_not_silently_approved(self):
        with self.assertRaises(ValueError):
            self.generate({**RESULT, 'cover_letter': 'Your Day 1 readiness needs coordination.'})

    def test_actual_failed_draft_placeholder_and_ownership_upgrades_are_blocked(self):
        for text in ['See [Candidate Portfolio Placeholder].',
                     'I built onboarding programs supporting hundreds of new hires.']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.generate({**RESULT, 'cover_letter': text})

    def test_real_greeting_portfolio_and_signature_are_inserted_after_generation(self):
        (draft, _, _), _ = self.generate()
        self.assertTrue(draft['cover_letter'].startswith('Dear Fixture International hiring team,'))
        self.assertIn('Portfolio: https://example.test/portfolio', draft['cover_letter'])
        self.assertTrue(draft['cover_letter'].endswith('Aminat Majekadegbe'))


class WritingProfileProvenanceAcceptance(unittest.TestCase):
    def test_direct_instruction_turns_and_rejected_examples_are_retained(self):
        text = (Path(__file__).parent / 'writing-profile.json').read_text()
        profile = json.loads(text)
        self.assertTrue(profile['version'])
        for turn in ['6aa25bb9-9b86-4725-a2f3-1faa289de9c4',
                     '01a1794d-1da8-7551-8372-e53dbb950ad8',
                     '01a17951-7d42-7551-85eb-266fd269cdd7',
                     '01a17955-477f-7b53-8185-ad4bae038d7e']:
            with self.subTest(source_turn=turn): self.assertIn(turn, text)
        self.assertTrue(profile['cv']['preserve_all_content'])


if __name__ == '__main__': unittest.main()
