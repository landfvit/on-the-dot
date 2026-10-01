"""Player login regressions use disposable schemas, never real accounts."""
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api import player_accounts
from tests import test_solo_database as fixtures
from trivia_app.main import app


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST') == '1', 'Isolated PostgreSQL tests')
class PlayerLoginTests(unittest.TestCase):
    setUp = fixtures.SoloDatabaseTests.setUp
    drop_schema = fixtures.SoloDatabaseTests.drop_schema

    def test_username_and_email_reach_the_same_account(self):
        for identifier in ['test_player', 'TEST_PLAYER', '  Test_Player  ',
                           'player@example.com', '  PLAYER@EXAMPLE.COM  ']:
            with self.subTest(identifier=identifier):
                client = TestClient(app)
                response = client.post('/api/players/login', json={
                    'identifier': identifier, 'password': 'test-only-password-1234'})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['username'], 'test_player')
                self.assertEqual(client.get('/api/players/me').json()['email'], 'player@example.com')
                cookie = client.cookies.get(player_accounts.COOKIE)
                self.assertTrue(cookie)
                again = client.post('/api/players/login', json={
                    'identifier': identifier, 'password': 'test-only-password-1234'})
                self.assertEqual(again.status_code, 200)
                self.assertNotEqual(client.cookies.get(player_accounts.COOKIE), cookie)
                stale = TestClient(app)
                stale.cookies.set(player_accounts.COOKIE, cookie)
                self.assertEqual(stale.get('/api/players/me').status_code, 401)
                self.assertEqual(client.post('/api/players/logout').status_code, 200)
                self.assertEqual(client.get('/api/players/me').status_code, 401)

    def test_invalid_credentials_are_generic_and_create_no_session(self):
        for identifier in ['test_player', 'player@example.com', 'missing_player', 'missing@example.com']:
            for password in ['wrong-password', 'TEST-ONLY-PASSWORD-1234', 'test-only-password-1234 ']:
                with self.subTest(identifier=identifier, password=password):
                    client = TestClient(app)
                    response = client.post('/api/players/login', json={
                        'identifier': identifier, 'password': password})
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.json()['detail'], 'Invalid username, email or password')
                    self.assertNotIn('set-cookie', response.headers)
                    self.assertEqual(client.get('/api/players/me').status_code, 401)

    def test_blocked_account_stays_blocked_with_either_identifier(self):
        with self.connection() as conn:
            conn.execute("UPDATE game_accounts SET blocked_at=clock_timestamp() WHERE username='test_player'")
        for identifier in ['test_player', 'player@example.com']:
            client = TestClient(app)
            response = client.post('/api/players/login', json={
                'identifier': identifier, 'password': 'test-only-password-1234'})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()['detail'], player_accounts.BLOCKED_MESSAGE)
            self.assertNotIn('set-cookie', response.headers)
            wrong = client.post('/api/players/login', json={'identifier': identifier, 'password': 'wrong-password'})
            self.assertEqual(wrong.status_code, 401)

    def test_deleted_and_guest_accounts_cannot_sign_in_by_username(self):
        with self.connection() as conn:
            account_id = conn.execute("SELECT account_id FROM game_accounts WHERE username='test_player'").fetchone()['account_id']
            player_accounts.anonymize_account(conn, account_id)
            deleted = conn.execute('SELECT username FROM game_accounts WHERE account_id=%s', (account_id,)).fetchone()['username']
            conn.execute('INSERT INTO game_accounts(account_id,username,password_hash,is_guest) VALUES(%s,%s,%s,true)',
                         (uuid4(), 'trial_login', player_accounts.password_hash('test-only-password-1234')))
        for identifier in ['test_player', 'player@example.com', deleted, 'trial_login']:
            client = TestClient(app)
            response = client.post('/api/players/login', json={
                'identifier': identifier, 'password': 'test-only-password-1234'})
            self.assertEqual(response.status_code, 401)
            self.assertNotIn('set-cookie', response.headers)

    def test_username_remains_valid_after_email_change(self):
        changed = self.client.put('/api/players/email', json={
            'email': 'changed@example.com', 'password': 'test-only-password-1234'})
        self.assertEqual(changed.status_code, 200, changed.text)
        for identifier, status in [('test_player', 200), ('changed@example.com', 200), ('player@example.com', 401)]:
            response = TestClient(app).post('/api/players/login', json={
                'identifier': identifier, 'password': 'test-only-password-1234'})
            self.assertEqual(response.status_code, status, response.text)

    def test_username_still_requires_current_password_after_recovery(self):
        with patch('api.account_email.reset_enabled', return_value=True), patch('api.account_email.send_reset') as send:
            requested = self.client.post('/api/players/password-reset/request', json={'email': 'player@example.com'})
            self.assertEqual(requested.status_code, 202)
            token = send.call_args.args[1]
        reset = self.client.post('/api/players/password-reset/confirm', json={
            'token': token, 'new_password': 'recovered-password'})
        self.assertEqual(reset.status_code, 200)
        for password, status in [('test-only-password-1234', 401), ('recovered-password', 200)]:
            response = TestClient(app).post('/api/players/login', json={'identifier': 'test_player', 'password': password})
            self.assertEqual(response.status_code, status, response.text)

    def test_username_login_keeps_csrf_and_rate_limit_checks(self):
        payload = {'identifier': 'test_player', 'password': 'test-only-password-1234'}
        with patch('api.player_accounts.rate_limit') as limiter:
            response = TestClient(app).post('/api/players/login', json=payload, headers={'Origin': 'https://evil.example'})
            self.assertEqual(response.status_code, 403)
            limiter.assert_not_called()
            self.assertEqual(TestClient(app).post('/api/players/login', json=payload).status_code, 200)
            self.assertEqual(limiter.call_args.args[1:], ('account-login', 8))


if __name__ == '__main__':
    unittest.main()
