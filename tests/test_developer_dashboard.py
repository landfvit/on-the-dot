"""Private admin access plus isolated PostgreSQL reporting/moderation checks."""
import os
import hashlib
import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from psycopg import Error as DatabaseError
from tests import test_challenge_database as fixtures
from trivia_app.main import app

EDITOR={'TRIVIA_EDITOR_USERNAME':'test_editor','TRIVIA_EDITOR_PASSWORD':'dashboard-test-password-only'}
AUTH=('test_editor',EDITOR['TRIVIA_EDITOR_PASSWORD'])


class DashboardAccessTests(unittest.TestCase):
    def test_private_routes_and_assets_are_fail_closed(self):
        with patch.dict(os.environ,{'TRIVIA_EDITOR_USERNAME':'','TRIVIA_EDITOR_PASSWORD':''}):
            for path in ['/internal/dashboard','/api/developer/overview','/trivia-assets/developer_dashboard.js','/trivia-assets/developer_dashboard.css']:
                self.assertEqual(TestClient(app).get(path).status_code,404,path)
        with patch.dict(os.environ,EDITOR),patch('api.developer_dashboard.get_connection') as connection:
            client=TestClient(app)
            for path in ['/api/developer/overview','/api/developer/players','/api/developer/games','/api/developer/audit','/api/developer/players/'+str(uuid4())]:
                self.assertEqual(client.get(path).status_code,401,path)
            self.assertEqual(client.post('/api/developer/players/'+str(uuid4())+'/actions',json={}).status_code,401)
            self.assertIn('/login?next=/internal/dashboard',client.get('/internal/dashboard',follow_redirects=False).headers['location'])
            connection.assert_not_called()

    def test_editor_login_returns_to_dashboard_no_open_redirect(self):
        with patch.dict(os.environ,EDITOR):
            client=TestClient(app)
            self.assertIn('value="/internal/dashboard"',client.get('/login?next=/internal/dashboard').text)
            r=client.post('/login',data={'username':AUTH[0],'password':AUTH[1],'next':'/internal/dashboard'},follow_redirects=False)
            self.assertEqual(r.headers['location'],'/internal/dashboard')
            for path in ['/internal/dashboard','/trivia-assets/developer_dashboard.css','/trivia-assets/developer_dashboard.js']:
                response=client.get(path);self.assertEqual(response.status_code,200);self.assertEqual(response.headers['cache-control'],'no-store')
            r=client.post('/login',data={'username':AUTH[0],'password':AUTH[1],'next':'https://example.com'},follow_redirects=False)
            self.assertEqual(r.headers['location'],'/internal/trivia')

    def test_csrf_and_input_bounds(self):
        with patch.dict(os.environ,EDITOR),patch('api.developer_dashboard.get_connection') as connection:
            client=TestClient(app);client.auth=AUTH
            r=client.post('/api/developer/players/'+str(uuid4())+'/actions',json={},headers={'Origin':'https://evil.example'})
            self.assertEqual(r.status_code,403)
            for path in ['/overview?days=8','/overview?days=500','/players?limit=1000','/players?offset=-1','/games?mode=invalid','/audit?offset=-1']:
                self.assertEqual(client.get('/api/developer'+path).status_code,422,path)
            connection.assert_not_called()


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Isolated PostgreSQL tests')
class DashboardDatabaseTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.ChallengeDatabaseTests('test_daily_pool_is_shared_exact_and_private')
        fixture.setUp();self.addCleanup(fixture.doCleanups);self.fixture=fixture
        p=patch.dict(os.environ,EDITOR);p.start();self.addCleanup(p.stop)
        self.admin=TestClient(app);self.admin.auth=AUTH;self.client=fixture.client
        with fixture.connection() as conn:
            self.ident=str(conn.execute("SELECT account_id FROM game_accounts WHERE username='test_player'").fetchone()['account_id'])

    def change(self,action,**extra):
        body={'action':action,'reason':'Testing admin action','confirmation':'test_player','request_id':str(uuid4()),**extra}
        return self.admin.post('/api/developer/players/'+self.ident+'/actions',json=body)

    def test_reporting_empty_then_solo_daily_friend(self):
        empty=self.admin.get('/api/developer/overview');self.assertEqual(empty.status_code,200,empty.text)
        self.assertEqual(empty.json()['totals']['games'],0);self.assertEqual(len(empty.json()['trend']),7)
        solo=self.fixture.start('easy');self.client.post('/api/solo/runs/'+solo['run_id']+'/leave',json={})
        daily=self.fixture.daily();self.client.post('/api/daily/runs/'+daily['run_id']+'/leave',json={})
        path,_=self.fixture.duel()
        summary=self.admin.get('/api/developer/overview?days=30').json()
        self.assertEqual(summary['totals']['games'],3);self.assertEqual(sum(d['games'] for d in summary['trend']),3)
        self.assertEqual(len(summary['trend']),30);self.assertEqual(summary['totals']['players'],2)
        self.assertEqual(summary['totals']['active_games'],1)
        games=self.admin.get('/api/developer/games').json();self.assertEqual(games['total'],3)
        self.assertEqual(len(next(g for g in games['items'] if g['mode']=='friend')['players']),2)
        for forbidden in ['"state"','"deck"','"correct"','"invite"','"password_hash"','"token_hash"']:
            self.assertNotIn(forbidden,str(games).replace("'",'"'))
        self.assertEqual(self.admin.get('/api/developer/games?mode=daily').json()['total'],1)
        self.assertEqual(self.admin.get('/api/developer/games?account_id='+self.ident).json()['total'],3)
        self.client.post(path+'/leave',json={})

    def test_search_pagination_and_private_player_data(self):
        result=self.admin.get('/api/developer/players?search=test_player').json()
        self.assertEqual(result['total'],1);self.assertEqual(result['items'][0]['email'],'player@example.com')
        self.assertEqual(self.admin.get('/api/developer/players?search=%25').json()['total'],0)
        self.assertEqual(self.admin.get('/api/developer/players?offset=100').json()['items'],[])
        detail=self.admin.get('/api/developer/players/'+self.ident).json();self.assertEqual(detail['sessions'],1)
        self.assertNotIn('password_hash',detail);self.assertNotIn('token_hash',detail)
        self.assertEqual(self.client.get('/api/developer/players/'+self.ident).status_code,401)

    def test_block_revoke_unblock_and_idempotent_audit(self):
        request_id=str(uuid4());body={'request_id':request_id}
        self.assertEqual(self.change('block',**body).status_code,200)
        self.assertEqual(self.change('block',**body).status_code,200)
        self.assertEqual(self.client.get('/api/players/me').status_code,401)
        login={'identifier':'player@example.com','password':'test-only-password-1234'}
        self.assertEqual(self.client.post('/api/players/login',json=login).status_code,403)
        self.assertEqual(self.admin.get('/api/developer/players?status=blocked').json()['total'],1)
        self.assertEqual(self.admin.get('/api/developer/audit').json()['total'],1)
        self.assertEqual(self.change('unblock',**body).status_code,409)
        self.assertEqual(self.change('unblock').status_code,200)
        self.assertEqual(self.client.get('/api/players/me').status_code,401)
        self.assertEqual(self.client.post('/api/players/login',json=login).status_code,200)
        self.assertEqual(self.change('revoke_sessions').status_code,200)
        self.assertEqual(self.client.get('/api/players/me').status_code,401)

    def test_blocked_open_session_and_game_cannot_bypass(self):
        run=self.fixture.start('easy')
        with self.fixture.connection() as conn:
            conn.execute('UPDATE game_accounts SET blocked_at=now() WHERE account_id=%s',(self.ident,))
        self.assertEqual(self.client.get('/api/players/me').status_code,403)
        self.assertEqual(self.client.post('/api/solo/runs/'+run['run_id']+'/next',json={'previous':0}).status_code,403)
        self.assertEqual(self.client.patch('/api/players/me',json={'bio':'not allowed'}).status_code,403)

    def test_confirmation_and_audit_atomicity(self):
        self.assertEqual(self.change('block',confirmation='wrong').status_code,422)
        self.assertEqual(self.change('block',reason='   ').status_code,422)
        self.assertEqual(self.admin.get('/api/developer/audit').json()['total'],0)
        ident=str(uuid4())
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda _:self.change('block',request_id=ident),range(2)))
        self.assertEqual([r.status_code for r in responses],[200,200])
        self.assertEqual(self.admin.get('/api/developer/audit').json()['total'],1)
        with self.fixture.connection() as conn:
            with self.assertRaises(DatabaseError),conn.transaction():
                conn.execute('DELETE FROM game_admin_audit WHERE account_id=%s',(self.ident,))

    def test_block_prevents_password_recovery_without_email_disclosure(self):
        token=secrets.token_urlsafe(32)
        with self.fixture.connection() as conn:
            conn.execute('UPDATE game_accounts SET blocked_at=now() WHERE account_id=%s',(self.ident,))
            conn.execute('INSERT INTO game_password_resets(token_hash,account_id) VALUES(%s,%s)',
                         (hashlib.sha256(token.encode()).hexdigest(),self.ident))
        with patch('api.account_email.reset_enabled',return_value=True),patch('api.account_email.send_reset') as send:
            r=self.client.post('/api/players/password-reset/request',json={'email':'player@example.com'})
            self.assertEqual(r.status_code,202);send.assert_not_called()
        r=self.client.post('/api/players/password-reset/confirm',json={'token':token,'new_password':'new-test-password'})
        self.assertEqual(r.status_code,400)

    def test_expired_run_is_not_active_and_reads_do_not_mutate(self):
        run=self.fixture.start('easy');original=self.fixture.row(run['run_id'])['state']
        # The game start timestamp is immutable. Advance only the reporting
        # query's expiry threshold via the frozen per-run max duration fixture.
        with self.fixture.connection() as conn:
            conn.execute('ALTER TABLE game_solo_runs DISABLE TRIGGER game_run_frozen')
            state={**original,'created_at':1}
            conn.execute('UPDATE game_solo_runs SET state=%s WHERE run_id=%s',(Jsonb(state),run['run_id']))
            conn.execute('ALTER TABLE game_solo_runs ENABLE TRIGGER game_run_frozen')
        result=self.admin.get('/api/developer/games?status=active').json();self.assertEqual(result['total'],0)
        expired=self.admin.get('/api/developer/games?status=abandoned').json();self.assertEqual(expired['items'][0]['phase'],'EXPIRED')
        self.assertEqual(self.fixture.row(run['run_id'])['state'],state)
