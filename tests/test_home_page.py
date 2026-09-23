"""The entry page uses verified player sessions, never just cookie presence."""
import hashlib
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from psycopg import OperationalError

from api.player_accounts import COOKIE
from trivia_app.main import app


class HomePageTests(unittest.TestCase):
    def assert_private(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['cache-control'], 'private, no-store')
        self.assertEqual(response.headers['vary'], 'Cookie')

    def test_visitors_and_returning_guests_get_guide_without_database(self):
        for cookies in ({}, {'points_trial': 'returning-guest'}, {'points_editor': 'editor-only'}):
            with self.subTest(cookies=cookies), patch('trivia_app.main.get_connection') as connection:
                response = TestClient(app, cookies=cookies).get('/')
                self.assert_private(response)
                self.assertIn('<h1>How to play</h1>', response.text)
                self.assertIn('href="/penalties"', response.text)
                self.assertNotIn('stadium_intro.js', response.text)
                connection.assert_not_called()

    def test_valid_registered_session_keeps_penalties_as_home(self):
        with patch('trivia_app.main.get_connection') as connection:
            conn = connection.return_value.__enter__.return_value
            conn.execute.return_value.fetchone.return_value = {'account_id': 'registered-player'}
            response = TestClient(app, cookies={COOKIE: 'valid-session'}).get('/')
            self.assert_private(response)
            self.assertIn('<h1>Penalties</h1>', response.text)
            self.assertIn('id="stadium-layer"', response.text)
            self.assertNotIn('<h1>How to play</h1>', response.text)
            self.assertNotIn('set-cookie', response.headers)
            conn.execute.assert_called_once()
            sql, params = conn.execute.call_args.args
            self.assertEqual(params, (hashlib.sha256(b'valid-session').hexdigest(),))
            for condition in ('s.expires_at>clock_timestamp()', 'NOT a.is_guest', 'a.deleted_at IS NULL'):
                self.assertIn(condition, sql)

    def test_expired_or_unknown_session_gets_guide_and_cookie_is_cleared(self):
        with patch('trivia_app.main.get_connection') as connection:
            connection.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
            client = TestClient(app, base_url='http://testserver')
            client.cookies.set(COOKIE, 'expired-session', domain='testserver.local', path='/')
            response = client.get('/')
            self.assert_private(response)
            self.assertIn('<h1>How to play</h1>', response.text)
            self.assertIn('Max-Age=0', response.headers['set-cookie'])
            self.assertNotIn(COOKIE, client.cookies)
            connection.reset_mock()
            self.assertEqual(client.get('/').status_code, 200)
            connection.assert_not_called()

    def test_malformed_session_does_not_query_database(self):
        with patch('trivia_app.main.get_connection') as connection:
            response = TestClient(app, cookies={COOKIE: 'x' * 101}).get('/')
            self.assert_private(response)
            self.assertIn('<h1>How to play</h1>', response.text)
            self.assertIn('Max-Age=0', response.headers['set-cookie'])
            connection.assert_not_called()

    def test_explicit_game_and_guide_urls_remain_public(self):
        with patch('trivia_app.main.get_connection') as connection:
            client = TestClient(app, cookies={COOKIE: 'unknown-session'})
            self.assertIn('<h1>Penalties</h1>', client.get('/penalties').text)
            self.assertIn('<h1>How to play</h1>', client.get('/how-to-play').text)
            connection.assert_not_called()

    def test_database_failure_does_not_silently_sign_out_player(self):
        with patch('trivia_app.main.get_connection', side_effect=OperationalError('Database unavailable')):
            client = TestClient(app, cookies={COOKIE: 'valid-session'}, raise_server_exceptions=False)
            response = client.get('/')
            self.assertEqual(response.status_code, 500)
            self.assertNotIn('set-cookie', response.headers)
