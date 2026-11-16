import unittest
from source_validation import validate_feed, validate_posting_url


class SourceValidationTests(unittest.TestCase):
    def setUp(self):
        self.feed = {'kind': 'ashby', 'board': 'acme', 'company': 'Acme'}
        self.job = {'id': 'one', 'title': 'People Operations', 'location': 'Nigeria',
                    'jobUrl': 'https://jobs.ashbyhq.com/acme/one'}

    def test_complete_empty_board_is_valid(self):
        self.assertEqual(validate_feed(self.feed, {'jobs': []}), [])

    def test_greenhouse_eu_origin(self):
        url = 'https://job-boards.eu.greenhouse.io/moniepoint/jobs/123'
        self.assertEqual(validate_posting_url({'kind': 'greenhouse',
            'board': 'moniepoint'}, url, 123), url)

    def test_error_and_missing_envelopes_are_not_empty_boards(self):
        for data in ({'error': 'temporary'}, {}, {'jobs': None}, [], {'jobs': {}}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_feed(self.feed, data)

    def test_rejects_untrusted_https_origins_and_wrong_board(self):
        for url in ('https://evil.test/apply', 'https://jobs.ashbyhq.com/other/one',
                    'https://jobs.ashbyhq.com/acme/two',
                    'https://jobs.ashbyhq.com.evil.test/acme/one',
                    'https://user:password@jobs.ashbyhq.com/acme/one',
                    'https://jobs.ashbyhq.com:8443/acme/one',
                    'https://jobs.ashbyhq.com/acme/%2fetc',
                    'https://jobs.ashbyhq.com/acme/../one'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_posting_url(self.feed, url, 'one')

    def test_canonical_preserves_essential_query_identity(self):
        self.assertEqual(validate_posting_url(self.feed,
            self.job['jobUrl'] + '?utm_source=board&job_id=one#apply', 'one'),
            self.job['jobUrl'] + '?job_id=one')

    def test_custom_host_requires_explicit_source_configuration(self):
        url = 'https://careers.acme.test/apply?job_id=one'
        with self.assertRaises(ValueError):
            validate_posting_url(self.feed, url, 'one')
        self.assertEqual(validate_posting_url({**self.feed,
            'allowed_posting_hosts': ['careers.acme.test']}, url, 'one'), url)

    def test_malformed_record_does_not_silently_drop(self):
        for bad in (None, {}, {**self.job, 'location': None},
                    {**self.job, 'id': True}, {**self.job, 'jobUrl': 'https://evil.test'}):
            with self.subTest(record=bad), self.assertRaises(ValueError):
                validate_feed(self.feed, {'jobs': [self.job, bad]})

    def test_duplicate_provider_ids_are_invalid(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            validate_feed(self.feed, {'jobs': [self.job, self.job]})

    def test_incomplete_greenhouse_response_is_invalid(self):
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            validate_feed({'kind': 'greenhouse', 'board': 'acme'},
                          {'jobs': [], 'meta': {'total': 10}})

    def test_all_three_provider_urls(self):
        cases = [
            ({'kind': 'greenhouse', 'board': 'acme'}, {'jobs': [{'id': 123, 'title': 'HR',
             'location': {'name': 'Nigeria'}, 'absolute_url': 'https://job-boards.greenhouse.io/acme/jobs/123'}]}),
            ({'kind': 'lever', 'board': 'acme'}, [{'id': 'one', 'text': 'HR',
             'categories': {'location': 'Nigeria'}, 'hostedUrl': 'https://jobs.lever.co/acme/one'}]),
            (self.feed, {'jobs': [self.job]})]
        for feed, data in cases:
            with self.subTest(kind=feed['kind']):
                self.assertEqual(len(validate_feed(feed, data)), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
