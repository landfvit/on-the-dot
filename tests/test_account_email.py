"""Email transport is always mocked. No live recipient or provider credentials."""
import os
import unittest
from unittest.mock import Mock, patch

from api import account_email


SETTINGS = {
    'PUBLIC_SITE_URL': 'https://onthedot.gg',
    'RESEND_API_KEY': 'test-only-api-key',
    'ACCOUNT_EMAIL_FROM': 'ON THE DOT. <accounts@mail.onthedot.gg>',
}


class AccountEmailTests(unittest.TestCase):
    def test_configuration_fails_closed(self):
        with patch.dict(os.environ, SETTINGS):
            self.assertTrue(account_email.reset_enabled())
            for key in SETTINGS:
                with self.subTest(key=key), patch.dict(os.environ, {key: ' '}):
                    self.assertFalse(account_email.reset_enabled())
        for url in ('http://onthedot.gg', 'https://user:secret@onthedot.gg',
                    'https://onthedot.gg/account', 'https://onthedot.gg?next=x',
                    'https://onthedot.gg#fragment', 'https://[invalid',
                    'https://onthedot.gg:notaport', 'not a url'):
            with self.subTest(url=url), patch.dict(os.environ, {**SETTINGS, 'PUBLIC_SITE_URL': url}):
                self.assertFalse(account_email.reset_enabled())

    def test_disabled_transport_does_not_send(self):
        with patch.dict(os.environ, {**SETTINGS, 'RESEND_API_KEY': ''}), patch.object(account_email.requests, 'post') as post:
            with self.assertRaisesRegex(RuntimeError, 'not configured'):
                account_email.send_reset('player@example.com', 'test-token')
            post.assert_not_called()

    def test_only_canonical_origin_and_fragment_are_sent(self):
        with patch.dict(os.environ, SETTINGS), patch.object(account_email.requests, 'post', return_value=Mock(status_code=200)) as post:
            account_email.send_reset('player@example.com', 'test-token')
            args, kwargs = post.call_args
            self.assertEqual(args, ('https://api.resend.com/emails',))
            self.assertFalse(kwargs['allow_redirects'])
            self.assertEqual(kwargs['timeout'], (5, 10))
            self.assertEqual(kwargs['json']['to'], ['player@example.com'])
            self.assertEqual(kwargs['json']['from'], SETTINGS['ACCOUNT_EMAIL_FROM'])
            self.assertIn('https://onthedot.gg/account#reset=test-token', kwargs['json']['text'])
            self.assertNotIn('?reset=', kwargs['json']['text'])
            self.assertIn('expires in 30 minutes', kwargs['json']['text'])

    def test_provider_errors_and_redirects_do_not_leak_details(self):
        with patch.dict(os.environ, SETTINGS):
            for status in (301, 400, 401, 403, 429, 500):
                with self.subTest(status=status), patch.object(account_email.requests, 'post', return_value=Mock(status_code=status)):
                    with self.assertRaisesRegex(RuntimeError, '^Account email delivery failed$'):
                        account_email.send_reset('player@example.com', 'secret-test-token')
            with patch.object(account_email.requests, 'post', side_effect=account_email.requests.Timeout('secret-test-token')):
                with self.assertRaises(RuntimeError) as error:
                    account_email.send_reset('player@example.com', 'secret-test-token')
                self.assertEqual(str(error.exception), 'Account email delivery failed')


if __name__ == '__main__':
    unittest.main()
