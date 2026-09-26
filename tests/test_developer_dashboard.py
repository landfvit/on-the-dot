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
from psycopg import Error as DatabaseError, sql
from psycopg.errors import UniqueViolation, CheckViolation
from api.player_accounts import BLOCKED_MESSAGE, anonymize_account
from tools.migrate_account_settings import apply
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
        self.assertEqual(self.client.get('/api/players/me').status_code,403)
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

    def register_again(self, email='PLAYER@EXAMPLE.COM', username='another_player'):
        return TestClient(app).post('/api/players/register',json={
            'username':username,'email':email,'password':'another-test-password'})

    def test_email_is_unique_normalized_and_cannot_be_claimed_by_another_player(self):
        self.assertEqual(self.register_again().status_code,409)
        change=self.fixture.friend.put('/api/players/email',json={
            'email':'Player@Example.com','password':'test-password-1234'})
        self.assertEqual(change.status_code,409)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda i:self.register_again('same-new@example.com','new_player_'+str(i)),range(2)))
        self.assertEqual(sorted(r.status_code for r in responses),[201,409])

    def test_revoked_blocked_session_has_notice_and_cannot_play_any_mode(self):
        solo=self.fixture.start('easy')
        self.assertEqual(self.change('block').status_code,200)
        for path in ['/api/players/me','/api/solo/active','/api/daily/catalog','/api/daily/active']:
            response=self.client.get(path)
            self.assertEqual(response.status_code,403,(path,response.text))
            self.assertEqual(response.json()['detail'],BLOCKED_MESSAGE)
        posts=[('/api/solo/runs',{'difficulty':'easy','request_id':str(uuid4())}),
               ('/api/daily/runs',{'request_id':str(uuid4())}),
               ('/api/friends/rooms',{'difficulty':'easy','request_id':str(uuid4())}),
               ('/api/solo/runs/'+solo['run_id']+'/next',{'previous':0})]
        for path,body in posts:
            self.assertEqual(self.client.post(path,json=body).status_code,403,path)
        self.assertEqual(self.register_again().status_code,409)
        self.assertEqual(self.client.post('/api/players/login',json={
            'identifier':'player@example.com','password':'incorrect-password'}).status_code,401)
        self.assertEqual(self.client.get('/api/players/profiles/test_player').status_code,404)
        with self.fixture.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_sessions WHERE account_id=%s',(self.ident,)).fetchone()['n'],0)
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_session_notices WHERE account_id=%s',(self.ident,)).fetchone()['n'],1)
            conn.execute("UPDATE game_session_notices SET expires_at=now()-interval '1 second'")
        self.assertEqual(self.client.get('/api/players/me').status_code,401)

    def test_blocked_existing_daily_and_friend_actions_are_denied(self):
        daily=self.fixture.daily();daily_path='/api/daily/runs/'+daily['run_id']
        self.client.post(daily_path+'/leave',json={})
        friend_path,_=self.fixture.duel()
        self.change('block')
        for path in [daily_path,friend_path]:
            self.assertEqual(self.client.get(path).status_code,403)
            self.assertEqual(self.client.post(path+'/leave',json={}).status_code,403)
            self.assertEqual(self.client.post(path+'/answers',json={
                'position':1,'option_id':'0','request_id':str(uuid4())}).status_code,403)

    def test_admin_delete_confirmation_anonymization_and_retry(self):
        run=self.fixture.start('easy')
        before=self.fixture.row(run['run_id'])
        reset=secrets.token_urlsafe(32)
        with self.fixture.connection() as conn:
            conn.execute('INSERT INTO game_password_resets(token_hash,account_id) VALUES(%s,%s)',
                         (hashlib.sha256(reset.encode()).hexdigest(),self.ident))
        self.assertEqual(self.change('delete',confirmation='wrong').status_code,422)
        self.assertEqual(self.client.get('/api/players/me').status_code,200)
        ident=str(uuid4())
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda _:self.change('delete',request_id=ident),range(2)))
        self.assertEqual([r.status_code for r in responses],[200,200])
        self.assertEqual(self.change('delete',request_id=ident).status_code,200)
        self.assertEqual(self.change('delete',request_id=ident,confirmation='wrong').status_code,409)
        self.assertEqual(self.change('unblock').status_code,404)
        self.assertEqual(self.admin.get('/api/developer/players/'+self.ident).status_code,404)
        self.assertEqual(self.admin.get('/api/developer/players?search=test_player').json()['total'],0)
        self.assertEqual(self.client.get('/api/players/profiles/test_player').status_code,404)
        self.assertEqual(self.client.get('/api/players/me').json()['detail'],'This account has been deleted.')
        self.assertEqual(self.client.post('/api/players/password-reset/confirm',json={
            'token':reset,'new_password':'replacement-password'}).status_code,400)
        self.assertEqual(self.fixture.row(run['run_id']),before)
        with self.fixture.connection() as conn:
            row=conn.execute('SELECT * FROM game_accounts WHERE account_id=%s',(self.ident,)).fetchone()
            self.assertIsNotNone(row['deleted_at']);self.assertIsNone(row['email'])
            self.assertIsNone(row['club_id']);self.assertEqual(row['bio'],'');self.assertEqual(row['password_hash'],'!')
            self.assertTrue(row['username'].startswith('deleted_'))
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_email_claims WHERE account_id=%s',(self.ident,)).fetchone()['n'],0)
        audit=self.admin.get('/api/developer/audit').json()
        self.assertEqual(audit['total'],1);self.assertEqual(audit['items'][0]['username'],'test_player')
        self.assertEqual(audit['items'][0]['action'],'delete')
        self.assertEqual(self.register_again().status_code,201)

    def test_blocked_email_stays_reserved_after_deletion_in_api_and_database(self):
        self.change('block');self.assertEqual(self.change('delete').status_code,200)
        self.assertEqual(self.register_again().status_code,409)
        self.assertEqual(self.client.get('/api/players/me').json()['detail'],BLOCKED_MESSAGE)
        change=self.fixture.friend.put('/api/players/email',json={
            'email':'PLAYER@EXAMPLE.COM','password':'test-password-1234'})
        self.assertEqual(change.status_code,409)
        with self.fixture.connection() as conn:
            claim=conn.execute('SELECT * FROM game_email_claims WHERE account_id=%s',(self.ident,)).fetchone()
            self.assertTrue(claim['blocked']);self.assertEqual(claim['email_hash'],hashlib.sha256(b'player@example.com').hexdigest())
            with self.assertRaises(UniqueViolation),conn.transaction():
                conn.execute("UPDATE game_accounts SET email='player@example.com' WHERE username='test_friend'")
            self.assertEqual(conn.execute("SELECT email FROM game_accounts WHERE username='test_friend'").fetchone()['email'],'friend@example.com')

    def test_unblock_then_delete_releases_email_but_not_old_session(self):
        self.change('block');self.change('unblock')
        self.assertEqual(self.register_again().status_code,409)
        self.assertEqual(self.client.get('/api/players/me').status_code,401)
        self.change('delete')
        self.assertEqual(self.register_again().status_code,201)
        self.assertEqual(self.client.get('/api/players/me').status_code,401)

    def test_database_cannot_change_email_of_blocked_account(self):
        self.change('block')
        with self.fixture.connection() as conn:
            with self.assertRaises(CheckViolation),conn.transaction():
                conn.execute("UPDATE game_accounts SET email='different@example.com' WHERE account_id=%s",(self.ident,))

    def test_registration_racing_block_and_delete_cannot_reuse_email(self):
        from threading import Event
        ready=Event();release=Event()
        def moderate():
            with self.fixture.connection() as conn:
                conn.execute('SELECT 1 FROM game_accounts WHERE account_id=%s FOR UPDATE',(self.ident,))
                conn.execute('UPDATE game_accounts SET blocked_at=now() WHERE account_id=%s',(self.ident,))
                anonymize_account(conn,self.ident)
                ready.set();release.wait(timeout=5)
        with ThreadPoolExecutor(max_workers=2) as pool:
            moderation=pool.submit(moderate);self.assertTrue(ready.wait(timeout=5))
            registration=pool.submit(self.register_again)
            release.set();moderation.result(timeout=10)
            self.assertEqual(registration.result(timeout=10).status_code,409)

    def test_blocked_scores_disappear_and_return_on_unblock(self):
        self.client.put('/api/players/me/team',json={'team_id':33})
        solo=self.fixture.start('easy');path='/api/solo/runs/'+solo['run_id']
        self.client.post(path+'/next',json={'previous':0})
        correct=self.fixture.row(solo['run_id'])['state']['deck'][0]['correct']
        self.client.post(path+'/answers',json={'position':1,'option_id':correct,'request_id':str(uuid4())})
        self.client.post(path+'/leave',json={})
        daily=self.fixture.daily();path='/api/daily/runs/'+daily['run_id']
        self.client.post(path+'/next',json={'previous':0})
        correct=self.fixture.mode_row(daily['run_id'])['state']['deck'][0]['correct']
        self.client.post(path+'/answers',json={'position':1,'option_id':correct,'request_id':str(uuid4())})
        self.client.post(path+'/leave',json={})
        public=TestClient(app)
        before=public.get('/api/community/leaderboard?metric=daily_highscore').json()
        self.assertEqual(before['entries'][0]['daily_highscore'],1)
        self.change('block')
        for metric in ['xp','level','streak','wins','win_rate','daily_wins','daily_highscore']:
            for board in ['players','teams']:
                r=self.client.get('/api/community/leaderboard',params={'metric':metric,'board':board,'period':'all'})
                self.assertEqual(r.status_code,200,r.text);data=r.json()
                self.assertFalse(data['signed_in']);self.assertIsNone(data['me'])
                if board=='players' or metric=='daily_highscore':self.assertEqual(data['entries'],[])
                else:
                    team=next(t for t in data['entries'] if t['team_id']==33)
                    self.assertEqual(team['members'],0);self.assertEqual(team['xp'],0);self.assertEqual(team['played'],0)
        self.change('unblock')
        after=public.get('/api/community/leaderboard?metric=daily_highscore').json()
        self.assertEqual(after['entries'],before['entries'])

    def test_migration_backfills_existing_bans_and_is_repeat_safe(self):
        schema='test_moderation_upgrade_'+uuid4().hex
        with self.fixture.connection() as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        try:
            with self.fixture.connection() as conn:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                conn.execute('''CREATE TABLE trivia_schema_migrations(name text PRIMARY KEY);
                    CREATE TABLE game_accounts(account_id uuid PRIMARY KEY,email text,blocked_at timestamptz,deleted_at timestamptz);
                    CREATE TABLE game_admin_audit(action text CHECK(action IN ('block','unblock','revoke_sessions')));''')
                blocked,active=uuid4(),uuid4()
                conn.execute("INSERT INTO game_accounts VALUES(%s,'blocked@example.com',now(),NULL),(%s,'active@example.com',NULL,NULL)",(blocked,active))
                self.assertTrue(apply(conn,'051_account_moderation'))
                self.assertFalse(apply(conn,'051_account_moderation'))
                claims=conn.execute('SELECT account_id,blocked FROM game_email_claims').fetchall()
                self.assertEqual({c['account_id']:c['blocked'] for c in claims},{blocked:True,active:False})
                conn.execute('UPDATE game_accounts SET email=NULL,deleted_at=now()')
                self.assertEqual(conn.execute('SELECT count(*) n FROM game_email_claims').fetchone()['n'],1)
                with self.assertRaises(UniqueViolation),conn.transaction():
                    conn.execute("INSERT INTO game_accounts VALUES(%s,'blocked@example.com',NULL,NULL)",(uuid4(),))
                conn.execute("INSERT INTO game_accounts VALUES(%s,'active@example.com',NULL,NULL)",(uuid4(),))
        finally:
            with self.fixture.connection() as conn:
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
