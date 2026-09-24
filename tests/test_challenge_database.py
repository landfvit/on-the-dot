"""Mode routes use isolated account/game tables and read-only published data."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from unittest.mock import patch
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from psycopg import Error as DatabaseError
from tests.test_solo_database import SoloDatabaseTests
from api import solo_engine,challenge_routes as routes
from api.database import get_connection
from trivia_app.main import app


class ChallengeDatabaseTests(SoloDatabaseTests):
    # Reuse only the schema fixture, not the legacy ten-question assertions.
    def setUp(self):
        with get_connection() as conn:self.assertIn(conn.info.host,('localhost','127.0.0.1','::1',''),'Local database only')
        super().setUp()
        solo_engine.RULES.update(format='shootout',bonus_mode='win')
        with self.connection() as conn:
            conn.execute('''INSERT INTO game_question_difficulty(release_id,question_id,difficulty,approved,reason,reviewed_by)
                SELECT release_id,question_id,difficulty,approved,reason,'test-fixture'
                FROM public.game_current_difficulty WHERE approved''')
        for target,value in [('get_connection',self.connection),('rate_limit',lambda *a:None)]:
            p=patch('api.challenge_routes.'+target,value);p.start();self.addCleanup(p.stop)
        self.friend=TestClient(app)
        response=self.friend.post('/api/players/register',json={'username':'test_friend','email':'friend@example.com','password':'test-password-1234'})
        self.assertEqual(response.status_code,201,response.text)

    def mode_row(self,ident):
        with self.connection() as conn:return conn.execute('SELECT * FROM game_mode_runs WHERE run_id=%s',(ident,)).fetchone()

    def daily(self):
        r=self.client.post('/api/daily/runs',json={'request_id':str(uuid4())})
        self.assertEqual(r.status_code,201,r.text);return r.json()

    def duel(self):
        r=self.client.post('/api/friends/rooms',json={'request_id':str(uuid4()),'difficulty':'easy'})
        self.assertEqual(r.status_code,201,r.text);s=r.json();path='/api/friends/rooms/'+s['code']
        r=self.friend.post(path+'/join',json={});self.assertEqual(r.status_code,200,r.text)
        for client in (self.client,self.friend):
            r=client.post(path+'/ready',json={});self.assertEqual(r.status_code,200,r.text)
        return path,r.json()

    def test_daily_pool_is_shared_exact_and_private(self):
        self.assertEqual(TestClient(app).get('/api/daily/catalog').status_code,401)
        a=self.client.get('/api/daily/catalog');b=self.friend.get('/api/daily/catalog')
        self.assertEqual(a.status_code,200,a.text);self.assertEqual(a.json()['remaining'],50)
        self.assertEqual(a.json()['day'],b.json()['day']);self.assertNotIn('deck',a.json())
        with self.connection() as conn:
            rows=conn.execute('SELECT deck FROM game_daily_pools').fetchall();self.assertEqual(len(rows),1)
            self.assertEqual({d:sum(q['difficulty']==d for q in rows[0]['deck']) for d in ['easy','medium','hard']},{'easy':10,'medium':20,'hard':20})

    def test_daily_only_opened_questions_block_solo(self):
        run=self.daily();ident=run['run_id'];row=self.mode_row(ident)
        with self.connection() as conn:self.assertEqual(conn.execute('SELECT count(*) n FROM game_mode_seen').fetchone()['n'],0)
        path='/api/daily/runs/'+ident
        r=self.client.post(path+'/next',json={'previous':0});self.assertEqual(r.status_code,200,r.text)
        self.assertNotIn('correct',r.json()['question'])
        r=self.client.post('/api/solo/runs',json={'request_id':str(uuid4()),'difficulty':'easy'});self.assertEqual(r.status_code,409)
        self.client.post(path+'/leave',json={})
        with self.connection() as conn:
            seen=routes.used_questions(conn,[row['owner_id']],r.json().get('server_now',routes.now_ms(conn)))
            self.assertEqual(seen,{row['state']['deck'][0]['question_id']})
        self.assertEqual(self.client.get('/api/daily/catalog').json()['remaining'],49)

    def test_daily_win_xp_and_retry_are_exactly_once(self):
        run=self.daily();path='/api/daily/runs/'+run['run_id'];deck=self.mode_row(run['run_id'])['state']['deck']
        for i in range(6):
            self.client.post(path+'/next',json={'previous':i})
            body={'position':i+1,'option_id':deck[i]['correct'],'request_id':str(uuid4())}
            r=self.client.post(path+'/answers',json=body);self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(self.client.post(path+'/answers',json=body).status_code,200)
        self.assertTrue(r.json()['won']);self.assertEqual(r.json()['total_xp'],sum(routes.game.XP[q['difficulty']] for q in deck[:6]))
        self.assertEqual(self.client.get('/api/players/me').json()['stats']['wins'],0)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_daily_wins').fetchone()['n'],1)
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_mode_xp').fetchone()['n'],6)
        r=self.client.get('/api/community/leaderboard?metric=daily_wins&period=all');self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['entries'][0]['daily_wins'],1)
        self.assertEqual(self.client.post('/api/daily/runs',json={'request_id':str(uuid4())}).status_code,409)

    def test_friend_private_answers_replay_and_no_xp(self):
        path,s=self.duel();row=self.mode_row(s['run_id']);opens=row['state']['round']['opens_at'];correct=row['state']['deck'][0]['correct']
        wrong=str((int(correct)+1)%4)
        with patch('api.challenge_routes.now_ms',return_value=opens+500):
            for client in [self.client,self.friend]:
                r=client.post(path+'/answers',json={'position':1,'option_id':wrong,'request_id':str(uuid4())});self.assertEqual(r.status_code,200,r.text)
                if client is self.client:
                    v=self.friend.get(path).json();self.assertNotIn('correct',v['question']);self.assertNotIn('answers',v['round'])
            self.assertEqual(r.json()['attempts'],[0,0]);self.assertEqual(r.json()['round']['outcome'],'replay')
        self.assertEqual(TestClient(app).get(path).status_code,401)
        r=self.client.post(path+'/leave',json={});self.assertEqual(r.status_code,200,r.text)
        with self.connection() as conn:
            for table in ('game_mode_xp','game_xp_ledger','game_match_results','game_mode_activity'):
                self.assertEqual(conn.execute('SELECT count(*) n FROM '+table).fetchone()['n'],0)
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_mode_seen').fetchone()['n'],2)

    def test_daily_concurrent_start_resumes_one_run(self):
        request={'request_id':str(uuid4())}
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies=list(pool.map(lambda _:self.client.post('/api/daily/runs',json=request),range(2)))
        self.assertEqual([r.status_code for r in replies],[201,201])
        self.assertEqual(replies[0].json()['run_id'],replies[1].json()['run_id'])
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_mode_runs').fetchone()['n'],1)

    def test_daily_timeout_commits_even_if_late_answer_rejected(self):
        s=self.daily();path='/api/daily/runs/'+s['run_id']
        self.client.post(path+'/next',json={'previous':0});row=self.mode_row(s['run_id'])
        with patch('api.challenge_routes.now_ms',return_value=row['state']['deadline']):
            r=self.client.post(path+'/answers',json={'position':1,'option_id':row['state']['deck'][0]['correct'],'request_id':str(uuid4())})
        self.assertEqual(r.status_code,409)
        latest=self.mode_row(s['run_id'])['state'];self.assertEqual(len(latest['history']),1);self.assertIsNone(latest['history'][0]['option_id'])
        self.assertEqual(self.client.get('/api/daily/catalog').json()['remaining'],49)

    def test_daily_exhaustion_award_and_database_guards(self):
        # A player may have seen 49 of today's questions in earlier games.
        with self.connection() as conn:
            now=routes.now_ms(conn);deck,day,reset=routes.daily_pool(conn,now)
            user=conn.execute("SELECT * FROM game_accounts WHERE username='test_player'").fetchone()
            run=uuid4();state=routes.game.daily_create(deck[:1],now,int(reset.timestamp()*1000))
            conn.execute("INSERT INTO game_mode_runs(run_id,mode,owner_id,start_request_id,day,state) VALUES(%s,'daily',%s,%s,%s,%s)",(run,user['account_id'],uuid4(),day,Jsonb(state)))
            conn.execute('INSERT INTO game_mode_members(run_id,account_id,seat) VALUES(%s,%s,0)',(run,user['account_id']))
            with self.assertRaises(DatabaseError),conn.transaction():
                conn.execute('INSERT INTO game_daily_wins(account_id,day,run_id) VALUES(%s,%s,%s)',(user['account_id'],day,run))
        path='/api/daily/runs/'+str(run);self.client.post(path+'/next',json={'previous':0})
        r=self.client.post(path+'/answers',json={'position':1,'option_id':deck[0]['correct'],'request_id':str(uuid4())})
        self.assertEqual(r.status_code,200,r.text);self.assertTrue(r.json()['won']);self.assertEqual(r.json()['end_reason'],'daily_pool_exhausted')

    def test_friend_simultaneous_answers_are_serialized(self):
        path,s=self.duel();row=self.mode_row(s['run_id']);opens=row['state']['round']['opens_at'];correct=row['state']['deck'][0]['correct']
        with patch('api.challenge_routes.now_ms',return_value=opens+500):
            with ThreadPoolExecutor(max_workers=2) as pool:
                replies=list(pool.map(lambda c:c.post(path+'/answers',json={'position':1,'option_id':correct,'request_id':str(uuid4())}),[self.client,self.friend]))
        self.assertEqual([r.status_code for r in replies],[200,200])
        row=self.mode_row(s['run_id']);self.assertEqual(len(row['state']['history']),1);self.assertEqual(row['state']['attempts'],[0,0])
        with self.connection() as conn:
            with self.assertRaises(DatabaseError),conn.transaction():
                conn.execute("INSERT INTO game_mode_xp(account_id,run_id,slot,amount,reason) VALUES(%s,%s,1,10,'correct_answer')",(row['owner_id'],row['run_id']))

    def test_invite_cannot_be_taken_by_third_player_or_cross_origin(self):
        path,s=self.duel();third=TestClient(app)
        self.assertEqual(third.post('/api/players/register',json={'username':'test_third','email':'third@example.com','password':'test-password-1234'}).status_code,201)
        self.assertEqual(third.get(path).status_code,403)
        self.assertEqual(third.post(path+'/join',json={}).status_code,409)
        self.assertEqual(self.client.post(path+'/leave',json={},headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/daily/runs',json={'request_id':str(uuid4())}).status_code,409)
        self.assertEqual(len(self.mode_row(s['run_id'])['state']['players']),2)

    def test_utc_reset_ends_active_daily_without_win(self):
        s=self.daily();row=self.mode_row(s['run_id'])
        with patch('api.challenge_routes.now_ms',return_value=row['state']['expires_at']):
            r=self.client.get('/api/daily/active')
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['run']['end_reason'],'daily_reset')
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_daily_wins').fetchone()['n'],0)
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_mode_members WHERE active').fetchone()['n'],0)


# The fixture is inherited for its setup helpers only. Do not collect its
# separate legacy rules test suite again with the modern shootout rules.
for _name in dir(SoloDatabaseTests):
    if _name.startswith('test_') and _name not in ChallengeDatabaseTests.__dict__:
        setattr(ChallengeDatabaseTests,_name,None)
