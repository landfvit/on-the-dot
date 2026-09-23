from copy import deepcopy
from pathlib import Path
import os
import unittest
from unittest.mock import patch
from uuid import uuid4
from psycopg import sql
from api import solo_engine as game
from tests.test_solo_database import SoloDatabaseTests

NEW_RULES=deepcopy(game.RULES)


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Isolated PostgreSQL tests')
class ShootoutDatabaseTests(unittest.TestCase):
    drop_schema=SoloDatabaseTests.drop_schema
    start=SoloDatabaseTests.start
    row=SoloDatabaseTests.row

    def setUp(self):
        SoloDatabaseTests.setUp(self)
        p=patch.dict(game.RULES,NEW_RULES,clear=True);p.start();self.addCleanup(p.stop)
        with self.connection() as conn:
            conn.execute("""INSERT INTO game_question_difficulty
                (release_id,question_id,difficulty,approved,reason,reviewed_by)
                SELECT release_id,question_id,difficulty,true,'Isolated sudden death test pool','test'
                FROM game_current_difficulty WHERE difficulty='hard' AND NOT approved LIMIT 20""")

    def play(self,ident,correct):
        state=self.row(ident)['state'];n=state['position']
        r=self.client.post(f'/api/solo/runs/{ident}/next',json={'previous':n})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['phase'],'ANSWERING',r.text)
        state=self.row(ident)['state'];q=state['deck'][n]
        body={'position':n+1,'option_id':q['correct'] if correct else str((int(q['correct'])+1)%4),'request_id':str(uuid4())}
        r=self.client.post(f'/api/solo/runs/{ident}/answers',json=body)
        self.assertEqual(r.status_code,200,r.text)
        return r.json(),body

    def test_early_win_rewards_streak_and_idempotency(self):
        ident=self.start('hard')['run_id']
        for _ in range(6):result,body=self.play(ident,True)
        self.assertEqual(result['shootout']['winner'],'player');self.assertEqual(result['total_xp'],720)
        repeat=self.client.post(f'/api/solo/runs/{ident}/answers',json=body)
        self.assertEqual(repeat.status_code,200,repeat.text)
        self.assertEqual(self.client.get('/api/players/me').json()['total_xp'],720)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_daily_activity').fetchone()['n'],1)

    def test_sudden_death_extends_atomically_and_cannot_edit_old_questions(self):
        ident=self.start('hard')['run_id']
        for correct in [True,False]*5:self.play(ident,correct)
        first=self.row(ident)['state']['deck']
        result,_=self.play(ident,True)
        self.assertEqual(result['phase'],'REVIEW');self.assertIsNone(result['shootout']['winner'])
        row=self.row(ident);self.assertEqual(len(row['state']['deck']),12);self.assertEqual(row['state']['deck'][:10],first)
        # Old Next retries do not reserve additional questions.
        self.assertEqual(self.client.post(f'/api/solo/runs/{ident}/next',json={'previous':10}).status_code,200)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_question_history WHERE run_id=%s',(ident,)).fetchone()['n'],12)
            with self.assertRaises(Exception):
                with conn.transaction():
                    conn.execute("UPDATE game_solo_runs SET state=jsonb_set(state,'{deck,0,text}', '\"changed\"') WHERE run_id=%s",(ident,))
        result,_=self.play(ident,True)
        self.assertEqual(result['phase'],'FINISHED');self.assertEqual(result['shootout']['player'],6)
        self.assertEqual(result['total_xp'],840)
        self.assertFalse(result['perfect']);self.assertEqual(result['multiplier'],4)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT reason FROM game_xp_ledger WHERE run_id=%s AND slot=0',(ident,)).fetchone()['reason'],'win_bonus')

    def test_exhausted_pool_never_declares_a_winner(self):
        from fastapi import HTTPException
        ident=self.start('hard')['run_id']
        for correct in [True,False]*5:self.play(ident,correct)
        with patch('api.solo_routes.load_deck',side_effect=HTTPException(409,'No questions')):
            r=self.client.post(f'/api/solo/runs/{ident}/next',json={'previous':10})
        self.assertEqual(r.status_code,200,r.text)
        result=r.json();self.assertEqual(result['phase'],'ABANDONED');self.assertIsNone(result['shootout']['winner'])
        self.assertEqual(result['end_reason'],'question_pool_exhausted');self.assertFalse(result['streak_eligible'])

    def test_club_membership_stats_rankings_and_early_exit_loss(self):
        clubs=self.client.get('/api/players/teams').json()['teams'];self.assertEqual(len(clubs),20)
        team=clubs[0]
        r=self.client.put('/api/players/me/team',json={'team_id':team['team_id']})
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['club'],team)
        self.assertEqual(self.client.put('/api/players/me/team',json={'team_id':999999}).status_code,422)
        self.assertEqual(self.client.put('/api/players/me/team',json={'team_id':team['team_id']},headers={'Origin':'https://evil.example'}).status_code,403)
        ident=self.start('hard')['run_id']
        for _ in range(6):self.play(ident,True)
        ident=self.start('hard')['run_id'];self.client.post(f'/api/solo/runs/{ident}/leave')
        stats=self.client.get('/api/players/me').json()['stats']
        self.assertEqual(stats,{'wins':1,'losses':1,'played':2,'win_rate':50})
        for metric in ['level','wins','win_rate']:
            r=self.client.get('/api/community/leaderboard',params={'metric':metric,'period':'all'})
            self.assertEqual(r.status_code,200,r.text)
            data=r.json();self.assertEqual(data['me']['rank'],1);self.assertEqual(data['me']['win_rate'],50)
            self.assertEqual(data['me']['club']['team_id'],team['team_id'])
        public=self.client.get('/api/players/profiles/test_player').json()
        self.assertEqual(public['club'],team);self.assertNotIn('email',public)
        self.assertIsNone(self.client.put('/api/players/me/team',json={'team_id':None}).json()['club'])

    def test_unplayed_exit_counts_as_loss_without_xp_or_win_bonus(self):
        ident=self.start('hard')['run_id'];self.client.post(f'/api/solo/runs/{ident}/leave')
        data=self.client.get('/api/community/leaderboard?metric=win_rate&period=all').json()
        self.assertEqual(data['participants'],1);self.assertEqual(data['me']['losses'],1)
        self.assertEqual(data['me']['win_rate'],0);self.assertEqual(data['me']['xp'],0)
        with self.connection() as conn:
            owner=conn.execute('SELECT account_id FROM game_solo_runs WHERE run_id=%s',(ident,)).fetchone()['account_id']
            with self.assertRaises(Exception):
                with conn.transaction():conn.execute("INSERT INTO game_xp_ledger VALUES(%s,%s,0,100,'win_bonus',DEFAULT)",(owner,ident))

    def test_rankings_sort_by_selected_metric_and_share_tied_ranks(self):
        from fastapi.testclient import TestClient
        from trivia_app.main import app
        original=self.client
        ident=self.start('hard')['run_id']
        for _ in range(6):self.play(ident,True)
        for _ in range(2):
            ident=self.start('hard')['run_id'];self.client.post(f'/api/solo/runs/{ident}/leave')
        self.client=TestClient(app)
        self.assertEqual(self.client.post('/api/players/register',json={'username':'another_player','email':'other@example.com','password':'test-password'}).status_code,201)
        ident=self.start('hard')['run_id']
        for _ in range(6):self.play(ident,True)
        self.client=original
        ranks=self.client.get('/api/community/leaderboard?metric=win_rate&period=all&limit=1').json()
        self.assertEqual(ranks['entries'][0]['username'],'another_player')
        self.assertEqual(ranks['entries'][0]['win_rate'],100)
        self.assertEqual(ranks['me']['rank'],2);self.assertAlmostEqual(float(ranks['me']['win_rate']),100/3)
        for metric in ['level','wins']:
            entries=self.client.get(f'/api/community/leaderboard?metric={metric}&period=all').json()['entries']
            self.assertEqual([r['rank'] for r in entries],[1,1])

    def test_expired_unfinished_game_counts_as_loss_without_opening_the_run(self):
        import time
        with patch('api.solo_routes.now_ms',return_value=int(time.time()*1000)-game.RULES['max_run_ms']-1000):
            ident=self.start('hard')['run_id']
        self.assertEqual(self.row(ident)['state']['phase'],'READY')
        stats=self.client.get('/api/players/me').json()['stats']
        self.assertEqual(stats['losses'],1);self.assertEqual(stats['win_rate'],0)
