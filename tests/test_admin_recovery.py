"""Admin recovery uses isolated local schemas and mocked email delivery."""
import hashlib
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from api.player_accounts import COOKIE
from tests.test_developer_dashboard import DashboardDatabaseTests, EDITOR, AUTH
from tools.migrate_account_settings import apply
from trivia_app.main import app


class RecoveryAccessTests(unittest.TestCase):
    def test_admin_access_csrf_and_strict_input(self):
        path='/api/developer/players/'+str(uuid4())+'/password-reset'
        body={'reason':'Player requested recovery','confirmation':'test_player'}
        with patch.dict(os.environ,EDITOR), patch('api.developer_dashboard.get_connection') as connect:
            client=TestClient(app)
            self.assertEqual(client.post(path,json=body).status_code,401)
            client.auth=AUTH
            self.assertEqual(client.post(path,json=body,headers={'Origin':'https://evil.test'}).status_code,403)
            self.assertEqual(client.post(path,json=body,headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)
            for bad in ({**body,'email':'other@example.com'}, {**body,'token':'attacker'},
                        {**body,'reason':'   '}, {**body,'confirmation':''}):
                self.assertEqual(client.post(path,json=bad).status_code,422)
            connect.assert_not_called()


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Isolated PostgreSQL integration tests')
class AdminRecoveryTests(unittest.TestCase):
    def setUp(self):
        DashboardDatabaseTests.setUp(self)
        for target,value in [('api.developer_dashboard.rate_limit',lambda *a:None),
                             ('api.account_email.reset_enabled',lambda:True)]:
            p=patch(target,value);p.start();self.addCleanup(p.stop)
        delivery=patch('api.account_email.send_reset')
        self.send=delivery.start();self.addCleanup(delivery.stop)
        self.path='/api/developer/players/'+self.ident+'/password-reset'
        self.body={'reason':'Player requested recovery','confirmation':'test_player'}

    def request(self,**changes):
        return self.admin.post(self.path,json={**self.body,**changes})

    def test_admin_request_is_audited_private_single_use_and_keeps_progress(self):
        self.client.put('/api/players/me/team',json={'team_id':64})
        self.client.put('/api/players/me/outfit',json={'kit_id':'64-2026-away','number':27})
        before=self.client.get('/api/players/me').json()
        cookie=self.client.cookies.get(COOKIE)
        r=self.request();self.assertEqual(r.status_code,202,r.text)
        self.assertEqual(r.headers['cache-control'],'no-store')
        email,token=self.send.call_args.args
        self.assertEqual(email,'player@example.com')
        self.assertNotIn(token,r.text)
        self.assertEqual(self.client.get('/api/players/me').status_code,200)
        with self.fixture.connection() as conn:
            row=conn.execute('SELECT * FROM game_password_resets').fetchone()
            self.assertEqual(row['token_hash'],hashlib.sha256(token.encode()).hexdigest())
            self.assertAlmostEqual((row['expires_at']-row['created_at']).total_seconds(),1800,delta=1)
        audit=self.admin.get('/api/developer/audit').json()
        self.assertEqual(audit['total'],1)
        self.assertEqual(audit['items'][0]['action'],'password_reset_requested')
        self.assertEqual(audit['items'][0]['actor'],AUTH[0])
        self.assertNotIn(token,str(audit))
        confirmed=TestClient(app).post('/api/players/password-reset/confirm',json={'token':token,'new_password':'recovered-password'})
        self.assertEqual(confirmed.status_code,200,confirmed.text)
        self.assertEqual(TestClient(app).post('/api/players/password-reset/confirm',json={'token':token,'new_password':'replay-password'}).status_code,400)
        stale=TestClient(app);stale.cookies.set(COOKIE,cookie)
        self.assertEqual(stale.get('/api/players/me').status_code,401)
        self.assertEqual(self.client.post('/api/players/login',json={'identifier':'player@example.com','password':'test-only-password-1234'}).status_code,401)
        self.assertEqual(self.client.post('/api/players/login',json={'identifier':'player@example.com','password':'recovered-password'}).status_code,200)
        after=self.client.get('/api/players/me').json()
        for key in ('username','club','outfit','total_xp','level','stats'):
            self.assertEqual(after[key],before[key])

    def test_confirmation_blocked_deleted_and_guest_checks(self):
        self.assertEqual(self.request(confirmation='wrong').status_code,422)
        with self.fixture.connection() as conn:
            conn.execute('UPDATE game_accounts SET blocked_at=now() WHERE account_id=%s',(self.ident,))
        self.assertEqual(self.request().status_code,409)
        self.send.assert_not_called()
        self.assertEqual(self.admin.get('/api/developer/audit').json()['total'],0)
        self.assertEqual(self.admin.post('/api/developer/players/'+str(uuid4())+'/password-reset',json=self.body).status_code,404)
        guest=TestClient(app);r=guest.post('/api/solo/runs',json={'difficulty':'easy','request_id':str(uuid4())})
        self.assertEqual(r.status_code,201,r.text)
        with self.fixture.connection() as conn:
            guest_id=conn.execute('SELECT account_id FROM game_accounts WHERE is_guest').fetchone()['account_id']
        self.assertEqual(self.admin.post('/api/developer/players/'+str(guest_id)+'/password-reset',json=self.body).status_code,404)
        DashboardDatabaseTests.change(self,'delete')
        self.assertEqual(self.request().status_code,404)
        self.send.assert_not_called()

    def test_disabled_configuration_creates_no_token_or_audit(self):
        with patch('api.account_email.reset_enabled',return_value=False):
            detail=self.admin.get('/api/developer/players/'+self.ident).json()
            self.assertFalse(detail['password_reset_configured'])
            self.assertEqual(self.request().status_code,503)
        self.send.assert_not_called()
        with self.fixture.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_password_resets').fetchone()['n'],0)
        self.assertEqual(self.admin.get('/api/developer/audit').json()['total'],0)

    def test_shared_cooldown_and_concurrent_requests_send_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.request(),range(2)))
        self.assertEqual(sorted(r.status_code for r in results),[202,429])
        self.assertEqual(self.send.call_count,1)
        self.assertEqual(next(r for r in results if r.status_code==429).headers['Retry-After'],'60')
        self.assertEqual(self.client.post('/api/players/password-reset/request',json={'email':'player@example.com'}).status_code,202)
        self.assertEqual(self.send.call_count,1)
        self.assertEqual(self.admin.get('/api/developer/audit').json()['total'],1)

    def test_delivery_failure_is_visible_to_admin_and_allows_retry(self):
        self.send.side_effect=RuntimeError('provider response with private details')
        with self.assertLogs('api.developer_dashboard',level='WARNING') as logs:
            r=self.request()
        self.assertEqual(r.status_code,502)
        self.assertNotIn('private details',r.text+str(logs.output))
        with self.fixture.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_password_resets').fetchone()['n'],0)
        self.send.side_effect=None
        self.assertEqual(self.request().status_code,202)
        self.assertEqual(self.send.call_count,2)

    def test_new_request_replaces_old_token_without_disclosing_either(self):
        self.assertEqual(self.request().status_code,202)
        first=self.send.call_args.args[1]
        with self.fixture.connection() as conn:
            conn.execute("UPDATE game_password_resets SET created_at=clock_timestamp()-interval '2 minutes'")
        self.assertEqual(self.request().status_code,202)
        second=self.send.call_args.args[1]
        self.assertNotEqual(first,second)
        self.assertEqual(TestClient(app).post('/api/players/password-reset/confirm',json={'token':first,'new_password':'replacement-password'}).status_code,400)
        with self.fixture.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_password_resets').fetchone()['n'],1)

    def test_block_after_request_invalidates_link(self):
        self.assertEqual(self.request().status_code,202)
        token=self.send.call_args.args[1]
        DashboardDatabaseTests.change(self,'block')
        self.assertEqual(TestClient(app).post('/api/players/password-reset/confirm',json={'token':token,'new_password':'replacement-password'}).status_code,400)

    def test_migration_is_repeat_safe_and_preserves_existing_actions(self):
        with self.fixture.connection() as conn:
            conn.execute('CREATE TABLE trivia_schema_migrations(name text PRIMARY KEY)')
            self.assertTrue(apply(conn,'054_account_recovery'))
            self.assertFalse(apply(conn,'054_account_recovery'))
        self.assertEqual(DashboardDatabaseTests.change(self,'revoke_sessions').status_code,200)
        self.assertEqual(self.request().status_code,202)


if __name__ == '__main__':
    unittest.main()
