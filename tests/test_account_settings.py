"""Security regressions use disposable PostgreSQL schemas and mocked email."""
from datetime import datetime,timezone,timedelta
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.player_accounts import COOKIE
from tests.test_solo_database import SoloDatabaseTests
from trivia_app.main import app


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Isolated PostgreSQL integration tests')
class AccountSettingsTests(unittest.TestCase):
    setUp=SoloDatabaseTests.setUp
    drop_schema=SoloDatabaseTests.drop_schema
    start=SoloDatabaseTests.start
    row=SoloDatabaseTests.row
    complete=SoloDatabaseTests.complete

    def test_password_change_checks_current_revokes_sessions_and_keeps_progress(self):
        self.complete('easy');old=self.client.cookies.get(COOKIE)
        body={'current_password':'wrong','new_password':'updated-password'}
        self.assertEqual(self.client.put('/api/players/password',json=body).status_code,401)
        body['current_password']='test-only-password-1234'
        self.assertEqual(self.client.put('/api/players/password',json=body,headers={'Origin':'https://evil.test'}).status_code,403)
        self.assertEqual(self.client.put('/api/players/password',json=body).status_code,200)
        self.assertNotEqual(old,self.client.cookies.get(COOKIE))
        other=TestClient(app);other.cookies.set(COOKIE,old)
        self.assertEqual(other.get('/api/players/me').status_code,401)
        self.assertEqual(other.post('/api/players/login',json={'identifier':'player@example.com','password':'test-only-password-1234'}).status_code,401)
        self.assertEqual(other.post('/api/players/login',json={'identifier':'player@example.com','password':'updated-password'}).status_code,200)
        self.assertEqual(other.get('/api/players/me').json()['total_xp'],100)

    def test_preferences_are_private_and_bio_remains_editable(self):
        r=self.client.put('/api/players/preferences',json={'animations':False,'reduced_motion':True})
        self.assertEqual(r.status_code,200)
        r=self.client.patch('/api/players/me',json={'bio':'New bio'})
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['username'],'test_player')
        self.assertEqual(r.json()['bio'],'New bio')
        self.assertEqual(r.json()['preferences'],{'animations':False,'reduced_motion':True})
        public=self.client.get('/api/players/profiles/test_player').json()
        for field in ['email','preferences','password_hash','deleted_at']:self.assertNotIn(field,public)

    def test_username_is_immutable_even_through_direct_api_requests(self):
        before=self.client.get('/api/players/me').json()
        for username in ['new_name','TEST_PLAYER','test_player','deleted_fake',None,'']:
            with self.subTest(username=username):
                response=self.client.patch('/api/players/me',json={'username':username,'bio':'Must not be applied'})
                self.assertEqual(response.status_code,422,response.text)
                after=self.client.get('/api/players/me').json()
                self.assertEqual(after['username'],before['username'])
                self.assertEqual(after['bio'],before['bio'])
        self.assertEqual(self.client.get('/api/players/profiles/test_player').status_code,200)
        self.assertEqual(self.client.get('/api/players/profiles/new_name').status_code,404)

    def test_username_unique_with_different_emails_and_case(self):
        for index,username in enumerate(['test_player','TEST_PLAYER','Test_Player']):
            response=TestClient(app).post('/api/players/register',json={
                'username':username,'email':f'duplicate{index}@example.com','password':'test-only-password'})
            self.assertEqual(response.status_code,409,response.text)
        with self.connection() as conn:
            self.assertEqual(conn.execute("SELECT count(*) n FROM game_accounts WHERE username='test_player'").fetchone()['n'],1)

    def test_concurrent_registrations_cannot_claim_the_same_username(self):
        def register(index):
            with TestClient(app) as client:
                return client.post('/api/players/register',json={
                    'username':['new_player','NEW_PLAYER'][index],
                    'email':f'new{index}@example.com','password':'test-only-password'})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(register,[0,1]))
        self.assertEqual(sorted(r.status_code for r in responses),[201,409])
        with self.connection() as conn:
            self.assertEqual(conn.execute("SELECT count(*) n FROM game_accounts WHERE username='new_player'").fetchone()['n'],1)

    def test_deletion_erases_identity_not_frozen_games(self):
        ident,_=self.complete('easy');old=self.client.cookies.get(COOKIE)
        data={'password':'test-only-password-1234','confirmation':'DELETE'}
        self.assertEqual(self.client.request('DELETE','/api/players/me',json={**data,'password':'bad'}).status_code,401)
        self.assertEqual(self.client.request('DELETE','/api/players/me',json={**data,'confirmation':'yes'}).status_code,422)
        self.assertEqual(self.client.request('DELETE','/api/players/me',json=data).status_code,200)
        self.assertEqual(self.client.get('/api/players/profiles/test_player').status_code,404)
        self.assertEqual(self.client.get('/api/community/leaderboard').json()['participants'],0)
        stale=TestClient(app);stale.cookies.set(COOKIE,old);self.assertEqual(stale.get('/api/players/me').status_code,401)
        with self.connection() as conn:
            row=conn.execute('SELECT * FROM game_accounts WHERE deleted_at IS NOT NULL').fetchone()
            self.assertIsNone(row['email']);self.assertEqual(row['password_hash'],'!');self.assertEqual(row['bio'],'');self.assertIsNone(row['club_id'])
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_solo_runs WHERE run_id=%s',(ident,)).fetchone()['n'],1)
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_sessions WHERE account_id=%s',(row['account_id'],)).fetchone()['n'],0)

    def test_reset_tokens_are_hashed_single_use_and_revoke_sessions(self):
        old=self.client.cookies.get(COOKIE)
        with patch('api.account_email.reset_enabled',return_value=True),patch('api.account_email.send_reset') as send:
            response=self.client.post('/api/players/password-reset/request',json={'email':'PLAYER@example.com'})
            self.assertEqual(response.status_code,202);token=send.call_args.args[1]
            unknown=self.client.post('/api/players/password-reset/request',json={'email':'nobody@example.com'})
            self.assertEqual(unknown.json(),response.json());self.assertEqual(send.call_count,1)
            again=self.client.post('/api/players/password-reset/request',json={'email':'player@example.com'})
            self.assertEqual(again.status_code,202);self.assertEqual(send.call_count,1)
        with self.connection() as conn:
            record=conn.execute('SELECT * FROM game_password_resets').fetchone()
            self.assertEqual(record['token_hash'],hashlib.sha256(token.encode()).hexdigest());self.assertNotIn(token,str(record))
        body={'token':token,'new_password':'after-recovery-123'}
        self.assertEqual(self.client.post('/api/players/password-reset/confirm',json=body).status_code,200)
        self.assertEqual(self.client.post('/api/players/password-reset/confirm',json=body).status_code,400)
        stale=TestClient(app);stale.cookies.set(COOKIE,old);self.assertEqual(stale.get('/api/players/me').status_code,401)
        self.assertEqual(self.client.post('/api/players/login',json={'identifier':'player@example.com','password':'after-recovery-123'}).status_code,200)

    def test_expired_and_invalidated_reset_links_fail(self):
        def token():
            with patch('api.account_email.reset_enabled',return_value=True),patch('api.account_email.send_reset') as send:
                self.client.post('/api/players/password-reset/request',json={'email':'player@example.com'})
                return send.call_args.args[1]
        value=token()
        with self.connection() as conn:conn.execute("UPDATE game_password_resets SET expires_at=clock_timestamp()-INTERVAL '1 second'")
        self.assertEqual(self.client.post('/api/players/password-reset/confirm',json={'token':value,'new_password':'new-password-123'}).status_code,400)
        self.client.put('/api/players/email',json={'email':'changed@example.com','password':'test-only-password-1234'})
        with self.connection() as conn:self.assertEqual(conn.execute('SELECT count(*) n FROM game_password_resets').fetchone()['n'],0)

    def test_recovery_unavailable_without_email_configuration(self):
        with patch('api.account_email.reset_enabled',return_value=False):
            self.assertFalse(self.client.get('/api/players/settings').json()['password_reset_available'])
            self.assertEqual(self.client.post('/api/players/password-reset/request',json={'email':'player@example.com'}).status_code,503)

    def test_guest_can_play_repeated_games_without_weekly_lock_or_rewards(self):
        self.client=TestClient(app)
        for _ in range(3):
            _,result=self.complete('easy');self.assertTrue(result['is_trial']);self.assertFalse(result['xp_saved'])
            self.assertEqual(self.client.get('/api/solo/active').json(),{'run':None,'trial_available':True})
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_solo_runs WHERE is_trial').fetchone()['n'],3)
            for table in ['game_xp_ledger','game_daily_activity','game_question_history']:
                self.assertEqual(conn.execute(f'SELECT count(*) n FROM {table}').fetchone()['n'],0)

    def test_concurrent_guest_starts_still_share_one_active_game(self):
        SoloDatabaseTests.test_trial_start_retries_in_two_tabs_share_one_quiz(self)
