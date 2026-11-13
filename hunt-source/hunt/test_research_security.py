import io
import socket
import unittest
from unittest.mock import Mock, patch

import google_provider
import research


class ResearchTransportTests(unittest.TestCase):
    def setUp(self):
        self.hunt = Mock()
        self.hunt.text_content.side_effect = lambda x: x
        self.addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))]

    def test_unverified_and_linkedin_sources_never_resolve(self):
        with patch('research.socket.getaddrinfo') as resolve:
            for url, approved in [('https://unverified.test/', False),
                                  ('https://www.linkedin.com/in/person', True),
                                  ('https://linkedin.com/company/example', True)]:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    research.public_page(self.hunt, url, allowed_source=approved)
            resolve.assert_not_called()

    def test_private_address_never_connects(self):
        for ip in ('127.0.0.1', '169.254.169.254', '10.0.0.1', '::1'):
            with self.subTest(ip=ip), patch('research.socket.getaddrinfo',
                return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))]), \
                patch('research.PinnedHTTPSConnection') as connection:
                with self.assertRaises(ValueError):
                    research.public_page(self.hunt, 'https://official.test/', allowed_source=True)
                connection.assert_not_called()

    def test_transport_uses_checked_ip_and_original_host(self):
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = 200
        response.getheader.return_value = 'text/plain'
        response.read.return_value = b'Verified public source'
        with patch('research.socket.getaddrinfo', return_value=self.addresses) as resolve, \
             patch('research.PinnedHTTPSConnection', return_value=connection) as transport:
            text = research.public_page(self.hunt, 'https://official.test/about?q=public', allowed_source=True)
        self.assertEqual(text, 'Verified public source')
        self.assertEqual(resolve.call_count, 1)
        transport.assert_called_once_with('official.test', '8.8.8.8', timeout=20)
        self.assertEqual(connection.request.call_args.args, ('GET', '/about?q=public'))
        self.assertEqual(connection.request.call_args.kwargs['headers']['Host'], 'official.test')
        connection.close.assert_called_once()

    def test_tls_sni_remains_hostname_when_connecting_to_ip(self):
        context = Mock()
        with patch('research.ssl.create_default_context', return_value=context), \
             patch('research.socket.create_connection') as connect:
            client = research.PinnedHTTPSConnection('official.test', '8.8.8.8')
            client.connect()
        connect.assert_called_once_with(('8.8.8.8', 443), 20)
        context.wrap_socket.assert_called_once_with(connect.return_value, server_hostname='official.test')

    def test_redirect_is_not_followed(self):
        connection = Mock()
        connection.getresponse.return_value.status = 302
        with patch('research.socket.getaddrinfo', return_value=self.addresses), \
             patch('research.PinnedHTTPSConnection', return_value=connection):
            with self.assertRaisesRegex(ValueError, 'redirects'):
                research.public_page(self.hunt, 'https://official.test/', allowed_source=True)
        self.assertEqual(connection.request.call_count, 1)
        connection.close.assert_called_once()

    def test_employer_authority_bound_to_configured_domain_or_board(self):
        job = {'kind': 'ashby', 'board': 'acme', 'verified_employer_domains': ['acme.test']}
        self.assertTrue(research._trusted_source(job, 'https://acme.test/about'))
        self.assertTrue(research._trusted_source(job, 'https://jobs.ashbyhq.com/acme/one'))
        self.assertFalse(research._trusted_source(job, 'https://jobs.ashbyhq.com/unrelated/one'))
        self.assertFalse(research._trusted_source(job, 'https://acme.test.attacker.test/about'))
        self.assertFalse(research._trusted_source(job, 'https://random-news.test/about'))


class GoogleTransportTests(unittest.TestCase):
    def test_credential_redirect_handler_rejects(self):
        with self.assertRaisesRegex(ValueError, 'redirects'):
            google_provider.NoRedirect().redirect_request(None, None, None, None, None, None)

    def test_common_transport_always_installs_redirect_guard(self):
        request = Mock()
        with patch('google_provider.build_opener') as opener:
            google_provider.open_google(request, 30)
        opener.assert_called_once_with(google_provider.NoRedirect)
        opener.return_value.open.assert_called_once_with(request, timeout=30)

    def test_other_spreadsheets_are_denied_before_network(self):
        provider = google_provider.GoogleProvider("owner@example.test")
        with patch("google_provider.open_google") as transport:
            with self.assertRaisesRegex(ValueError,"explicitly authorized"):
                provider.tracker("another-private-spreadsheet")
            with self.assertRaisesRegex(ValueError,"explicitly authorized"):
                provider.compare_and_swap_row("another-private-spreadsheet",2,[],[""]*10)
        transport.assert_not_called()

    def test_token_and_api_requests_use_guarded_transport(self):
        env = {'HUNT_GOOGLE_CLIENT_ID': 'fake-client', 'HUNT_GOOGLE_CLIENT_SECRET': 'fake-secret',
               'HUNT_GOOGLE_REFRESH_TOKEN': 'fake-refresh'}
        def response(raw):
            result = Mock()
            result.__enter__ = Mock(return_value=io.BytesIO(raw))
            result.__exit__ = Mock(return_value=False)
            return result
        with patch.dict('os.environ', env, clear=True), \
             patch('google_provider.open_google', side_effect=[response(b'{"access_token":"fake-access"}'),
                                                             response(b'{"emailAddress":"owner@example.test"}')]) as transport:
            provider = google_provider.GoogleProvider('owner@example.test')
            self.assertEqual(provider.profile()['emailAddress'], 'owner@example.test')
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(transport.call_args_list[0].args[0].full_url, 'https://oauth2.googleapis.com/token')
        self.assertEqual(transport.call_args_list[1].args[0].full_url, 'https://gmail.googleapis.com/gmail/v1/users/me/profile')


if __name__ == '__main__':
    unittest.main(verbosity=2)
