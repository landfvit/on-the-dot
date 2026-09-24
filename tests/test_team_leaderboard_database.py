"""Real SQL aggregation and cooldown tests in disposable, locally scoped schemas."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.errors import CheckViolation

from api.database import get_connection
from api.player_accounts import COOKIE
from tools.migrate_account_settings import apply
from trivia_app.main import app


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST') == '1', 'Local PostgreSQL integration tests')
class TeamLeaderboardDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.schema = 'test_team_board_' + uuid4().hex
        with get_connection() as conn:
            self.assertIn(conn.info.host, ('localhost', '127.0.0.1', '::1', ''), 'Local database only')
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)

        @contextmanager
        def isolated():
            with get_connection() as conn:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.schema)))
                yield conn
        self.connection = isolated
        for module in ('api.player_accounts', 'api.game_community'):
            p = patch(module + '.get_connection', isolated);p.start();self.addCleanup(p.stop)
        p = patch('api.player_accounts.rate_limit');p.start();self.addCleanup(p.stop)
        self.ids = {name: uuid4() for name in ('alice', 'bob', 'charlie', 'dan', 'guest', 'deleted')}
        with isolated() as conn:
            conn.execute('''
                CREATE TABLE trivia_schema_migrations(name text PRIMARY KEY);
                CREATE TABLE game_clubs(team_id int PRIMARY KEY,name text,season int);
                INSERT INTO game_clubs VALUES (33,'Manchester United',2026),(40,'Liverpool',2026),(50,'Manchester City',2026);
                CREATE TABLE game_accounts(account_id uuid PRIMARY KEY,username text,club_id int REFERENCES game_clubs,
                    is_guest bool DEFAULT false,deleted_at timestamptz,email text DEFAULT 'test@example.com',
                    bio text DEFAULT '',accent text DEFAULT 'green',animations bool DEFAULT true,reduced_motion bool DEFAULT false);
                CREATE TABLE game_sessions(token_hash text,account_id uuid,expires_at timestamptz DEFAULT clock_timestamp()+INTERVAL '1 day');
                CREATE TABLE game_levels(level int,minimum_xp int);
                INSERT INTO game_levels VALUES (1,0),(2,100),(3,300),(4,1000);
                CREATE TABLE game_xp_ledger(account_id uuid,amount int,created_at timestamptz DEFAULT clock_timestamp());
                CREATE TABLE game_match_results(account_id uuid,won bool,finished_at timestamptz DEFAULT clock_timestamp());
                CREATE TABLE game_daily_activity(account_id uuid,day date,PRIMARY KEY(account_id,day));
                CREATE TABLE game_solo_runs(account_id uuid,state jsonb);
                CREATE VIEW game_all_xp AS SELECT * FROM game_xp_ledger;
                CREATE VIEW game_all_activity AS SELECT * FROM game_daily_activity;
                CREATE TABLE game_daily_wins(account_id uuid,won_at timestamptz);
            ''')
            apply(conn, '046_team_membership')
            self.now = conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            for name, club in [('alice',33),('bob',33),('charlie',33),('dan',40),('guest',33),('deleted',33)]:
                conn.execute('INSERT INTO game_accounts(account_id,username,club_id,is_guest,deleted_at) VALUES(%s,%s,%s,%s,%s)',
                             (self.ids[name],name,club,name=='guest',self.now if name=='deleted' else None))
                conn.execute('INSERT INTO game_sessions(token_hash,account_id) VALUES(%s,%s)',
                             (hashlib.sha256(name.encode()).hexdigest(),self.ids[name]))
            for name, xp in [('alice',10),('bob',300),('charlie',20),('dan',99),('guest',99999),('deleted',99999)]:
                conn.execute('INSERT INTO game_xp_ledger(account_id,amount) VALUES(%s,%s)',(self.ids[name],xp))
            conn.execute('INSERT INTO game_xp_ledger VALUES(%s,100,%s)',(self.ids['alice'],self.now-timedelta(days=10)))
            for name, outcomes in [('alice',[True,False]),('bob',[True,True,True,False]),('guest',[True]),('deleted',[True])]:
                for won in outcomes:
                    conn.execute('INSERT INTO game_match_results(account_id,won) VALUES(%s,%s)',(self.ids[name],won))
            for name, days in [('alice',[0,1,2,6]),('bob',[1,2]),('dan',[3,4])]:
                for days_ago in days:
                    conn.execute('INSERT INTO game_daily_activity VALUES(%s,%s)',(self.ids[name],self.now.date()-timedelta(days=days_ago)))
        self.client = TestClient(app, cookies={COOKIE:'alice'})

    def drop_schema(self):
        with get_connection() as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    def board(self, **params):
        response = self.client.get('/api/community/leaderboard', params={'period':'all',**params})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def membership(self, name='alice'):
        with self.connection() as conn:
            return conn.execute('SELECT club_id,club_changed_at FROM game_accounts WHERE account_id=%s',(self.ids[name],)).fetchone()

    def test_player_xp_and_current_streak_rankings(self):
        data = self.board(metric='xp')
        self.assertEqual([p['username'] for p in data['entries']],['bob','alice','dan','charlie'])
        self.assertEqual(data['me']['xp'],110)
        for p in data['entries']:
            self.assertFalse({'email','account_id','club_id','sort_name','is_me','deleted_at'} & p.keys())
        data = self.board(metric='streak',period='today')
        self.assertEqual(data['period'],'all')
        self.assertEqual([(p['username'],p['streak']) for p in data['entries']][:2],[('alice',3),('bob',2)])
        self.assertEqual(next(p for p in data['entries'] if p['username']=='dan')['streak'],0)

    def test_team_totals_and_unweighted_member_win_rate(self):
        for metric, expected in [('xp',430),('level',6),('streak',5),('wins',4),('win_rate',62.5)]:
            data = self.board(board='teams',metric=metric)
            team = next(t for t in data['entries'] if t['team_id']==33)
            self.assertEqual(team[metric],expected)
            self.assertEqual(team['members'],3)
            self.assertEqual(data['me']['team_id'],33)
            self.assertEqual(data['participants'],3)
            self.assertEqual(sum(b['count'] for b in data['distribution']),3)
            self.assertFalse({'account_id','email','sort_name','is_me'} & team.keys())
        empty = next(t for t in data['entries'] if t['team_id']==50)
        self.assertEqual(empty['members'],0)
        self.assertIsNone(empty['win_rate'])
        self.assertEqual(data['entries'][0]['team_id'],33)

    def test_periods_and_own_team_outside_pagination(self):
        self.assertEqual(self.board(board='teams',period='today')['me']['xp'],330)
        self.assertEqual(self.board(board='teams',period='week')['me']['xp'],330)
        data=self.board(board='teams',limit=1,offset=1)
        self.assertEqual(data['entries'][0]['team_id'],40)
        self.assertEqual(data['me']['team_id'],33)
        anon=TestClient(app).get('/api/community/leaderboard?board=teams').json()
        self.assertFalse(anon['signed_in']);self.assertIsNone(anon['me'])
        for query in ('board=invalid','metric=invalid','offset=-1'):
            self.assertEqual(self.client.get('/api/community/leaderboard?'+query).status_code,422)

    def test_join_switch_and_leave_are_locked_for_72_hours(self):
        response=self.client.put('/api/players/me/team',json={'team_id':40})
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()['team_change']['can_change'])
        stamp=self.membership()['club_changed_at']
        self.assertEqual(datetime.fromisoformat(response.json()['team_change']['next_change_at']),stamp+timedelta(hours=72))
        for target in (33,50,None):
            self.assertEqual(self.client.put('/api/players/me/team',json={'team_id':target}).status_code,409)
        self.assertEqual(self.membership()['club_id'],40)
        same=self.client.put('/api/players/me/team',json={'team_id':40})
        self.assertEqual(same.status_code,200)
        self.assertEqual(self.membership()['club_changed_at'],stamp)
        moved=self.board(board='teams')
        self.assertEqual(next(t for t in moved['entries'] if t['team_id']==33)['xp'],320)
        self.assertEqual(next(t for t in moved['entries'] if t['team_id']==40)['xp'],209)

    def test_removing_team_also_starts_cooldown(self):
        response=self.client.put('/api/players/me/team',json={'team_id':None})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIsNone(response.json()['club'])
        self.assertEqual(self.client.put('/api/players/me/team',json={'team_id':50}).status_code,409)
        self.assertIsNone(self.board(board='teams')['me'])

    def test_database_prevents_bypass_but_allows_deletion(self):
        self.client.put('/api/players/me/team',json={'team_id':40})
        for statement in ('UPDATE game_accounts SET club_id=50 WHERE account_id=%s',
                          'UPDATE game_accounts SET club_changed_at=NULL WHERE account_id=%s'):
            with self.assertRaises(CheckViolation),self.connection() as conn:
                conn.execute(statement,(self.ids['alice'],))
        with self.connection() as conn:
            conn.execute('UPDATE game_accounts SET deleted_at=clock_timestamp(),club_id=NULL WHERE account_id=%s',(self.ids['alice'],))
        self.assertIsNone(self.membership()['club_id'])

    def test_concurrent_changes_allow_only_one_and_migration_is_idempotent(self):
        def change(team):
            return TestClient(app,cookies={COOKIE:'alice'}).put('/api/players/me/team',json={'team_id':team}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(change,[40,50])),[200,409])
        with self.connection() as conn:
            self.assertFalse(apply(conn,'046_team_membership'))

    def test_expired_cooldown_allows_change_and_same_team_does_not_start_one(self):
        self.assertEqual(self.client.put('/api/players/me/team',json={'team_id':33}).status_code,200)
        self.assertIsNone(self.membership()['club_changed_at'])
        ident=uuid4()
        with self.connection() as conn:
            conn.execute('INSERT INTO game_accounts(account_id,username,club_id,club_changed_at) VALUES(%s,%s,33,%s)',
                         (ident,'expired',self.now-timedelta(hours=72)))
            conn.execute('INSERT INTO game_sessions(token_hash,account_id) VALUES(%s,%s)',(hashlib.sha256(b'expired').hexdigest(),ident))
        response=TestClient(app,cookies={COOKIE:'expired'}).put('/api/players/me/team',json={'team_id':40})
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()['team_change']['can_change'])
