"""Regression coverage for compact writes, frozen snapshots and result summaries."""
from uuid import uuid4

from psycopg import DatabaseError,sql
from psycopg.types.json import Jsonb

from api import challenge_routes as daily
from tests.test_challenge_database import ChallengeDatabaseTests


class GamePerformanceTests(ChallengeDatabaseTests):
    def test_daily_projection_loads_only_necessary_snapshots(self):
        run=self.daily()['run_id']
        with self.connection() as conn:
            row=daily.daily_window(conn.execute('SELECT '+daily.DAILY_COLUMNS+' FROM game_mode_runs r WHERE run_id=%s',(run,)).fetchone())
            self.assertEqual(len(row['state']['deck']),1000)
            self.assertEqual(len(row['state']['deck'].prefix),1)
        path='/api/daily/runs/'+run
        self.assertEqual(self.client.post(path+'/next',json={'previous':0}).status_code,200)
        with self.connection() as conn:
            row=daily.daily_window(conn.execute('SELECT '+daily.DAILY_COLUMNS+' FROM game_mode_runs r WHERE run_id=%s',(run,)).fetchone())
            self.assertEqual(len(row['state']['deck'].prefix),2)
        self.assertEqual(len(self.mode_row(run)['state']['deck']),1000)

    def version(self,table,run):
        with self.connection() as conn:
            return conn.execute(sql.SQL('SELECT xmin::text version,state FROM {} WHERE run_id=%s')
                                .format(sql.Identifier(table)),(run,)).fetchone()

    def test_idle_and_duplicate_solo_requests_do_not_rewrite_state(self):
        run=self.start('easy')['run_id'];path='/api/solo/runs/'+run
        old=self.version('game_solo_runs',run)
        for _ in range(3):self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(self.version('game_solo_runs',run),old)
        self.client.post(path+'/next',json={'previous':0})
        state=self.row(run)['state']
        body={'position':1,'option_id':state['deck'][0]['correct'],'request_id':str(uuid4())}
        self.assertEqual(self.client.post(path+'/answers',json=body).status_code,200)
        old=self.version('game_solo_runs',run)
        self.assertEqual(self.client.post(path+'/answers',json=body).status_code,200)
        self.assertEqual(self.version('game_solo_runs',run),old)

    def test_daily_idle_polls_and_retry_do_not_rewrite_and_deck_stays_frozen(self):
        run=self.daily()['run_id'];path='/api/daily/runs/'+run
        old=self.version('game_mode_runs',run)
        for _ in range(3):self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(self.version('game_mode_runs',run),old)
        self.client.post(path+'/next',json={'previous':0})
        q=old['state']['deck'][0]
        body={'position':1,'option_id':q['correct'],'request_id':str(uuid4())}
        self.assertEqual(self.client.post(path+'/answers',json=body).status_code,200)
        answered=self.version('game_mode_runs',run)
        self.assertEqual(answered['state']['deck'],old['state']['deck'])
        self.assertEqual(self.client.post(path+'/answers',json=body).status_code,200)
        self.assertEqual(self.version('game_mode_runs',run),answered)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_mode_seen WHERE run_id=%s',(run,)).fetchone()['n'],1)
            self.assertEqual(conn.execute('SELECT sum(amount) n FROM game_mode_xp WHERE run_id=%s',(run,)).fetchone()['n'],daily.game.XP[q['difficulty']])

    def test_existing_daily_pool_does_not_wait_for_creation_lock(self):
        self.daily()
        with self.connection() as holder:
            now=daily.now_ms(holder);day,_=daily.day_window(now)
            holder.execute('SELECT pg_advisory_xact_lock(%s,%s)',(47001,day.toordinal()))
            with self.connection() as reader:
                reader.execute("SET LOCAL lock_timeout='100ms'")
                self.assertEqual(len(daily.daily_pool(reader,now)[0]),1000)

    def test_daily_guard_rejects_old_question_and_history_edits(self):
        run=self.daily()['run_id'];path='/api/daily/runs/'+run
        self.client.post(path+'/next',json={'previous':0})
        q=self.mode_row(run)['state']['deck'][0]
        self.client.post(path+'/answers',json={'position':1,'option_id':q['correct'],'request_id':str(uuid4())})
        with self.connection() as conn:
            for field,value in [('deck,0,text','tampered'),('history,0,correct',False)]:
                with self.subTest(field=field),self.assertRaises(DatabaseError),conn.transaction():
                    conn.execute('UPDATE game_mode_runs SET state=jsonb_set(state,%s,%s) WHERE run_id=%s',
                                 ('{'+field+'}',Jsonb(value),run))
            with self.assertRaises(DatabaseError),conn.transaction():
                conn.execute("UPDATE game_mode_runs SET state=jsonb_set(state,'{deck}',(state->'deck')-0) WHERE run_id=%s",(run,))

    def test_summary_matches_original_view_and_cannot_be_forged(self):
        run=self.start('easy')['run_id']
        for i in range(6):
            path='/api/solo/runs/'+run
            self.client.post(path+'/next',json={'previous':i})
            q=self.row(run)['state']['deck'][i]
            self.client.post(path+'/answers',json={'position':i+1,'option_id':q['correct'],'request_id':str(uuid4())})
        self.start('easy')
        with self.connection() as conn:
            expected=conn.execute("""SELECT run_id,account_id,
                state->>'phase'='FINISHED' AND game_shootout_winner(state)='player' won,
                CASE WHEN state->>'phase' IN ('FINISHED','ABANDONED') THEN to_timestamp((state->>'finished_at')::bigint/1000.0)
                ELSE to_timestamp(((state->>'created_at')::bigint+(state->'rules'->>'max_run_ms')::bigint)/1000.0) END finished_at
                FROM game_solo_runs WHERE NOT is_trial AND state->'rules'->>'format'='shootout'
                AND (state->>'phase' IN ('FINISHED','ABANDONED') OR
                 (state->>'created_at')::bigint+(state->'rules'->>'max_run_ms')::bigint<=extract(epoch FROM current_timestamp)*1000)
                ORDER BY run_id""").fetchall()
            self.assertEqual(conn.execute('SELECT * FROM game_match_results ORDER BY run_id').fetchall(),expected)
            self.assertEqual(len(expected),1);self.assertTrue(expected[0]['won'])
            with self.assertRaises(DatabaseError),conn.transaction():
                conn.execute('UPDATE game_solo_runs SET result_won=false WHERE run_id=%s',(run,))


for _name in dir(ChallengeDatabaseTests):
    if _name.startswith('test_') and _name not in GamePerformanceTests.__dict__:
        setattr(GamePerformanceTests,_name,None)
