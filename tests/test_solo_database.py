"""New game tables live in disposable schemas; published questions are read-only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException,Request,Response
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.types.json import Jsonb

from api.database import get_connection
from api import solo_routes as routes
from api.solo_topics import TOPICS,SOURCE_TOPIC
from api.player_accounts import COOKIE,password_hash
from api.solo_trials import COOKIE as TRIAL_COOKIE
from src.seed_solo_difficulty import seed
from src.release_solo_bank import release as release_solo_bank
from trivia_app.main import app


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Isolated PostgreSQL integration tests')
class SoloDatabaseTests(unittest.TestCase):
    def setUp(self):
        legacy={**routes.game.RULES,'version':'solo-v3'};legacy.pop('format',None)
        legacy.pop('bonus_mode',None)
        p=patch.dict(routes.game.RULES,legacy,clear=True);p.start();self.addCleanup(p.stop)
        self.schema='test_solo_'+uuid4().hex
        with get_connection() as conn:
            original=conn.execute("SELECT release_id FROM penalty_bank_releases WHERE choice_version='bank-choices-v1' ORDER BY created_at LIMIT 1").fetchone()['release_id']
            for target in ['api.solo_routes.latest_release','src.seed_solo_difficulty.latest_release']:
                mock=patch(target,return_value=original);mock.start();self.addCleanup(mock.stop)
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
            conn.execute(sql.SQL('SET search_path TO {},public').format(sql.Identifier(self.schema)))
            for name in ['037_player_progress','038_solo_answer_guards','039_email_trials_xp','040_weekly_question_history','042_solo_answer_duration','043_solo_shootout','044_solo_community','045_account_settings','046_team_membership']:
                if name=='039_email_trials_xp':
                    conn.execute('INSERT INTO game_accounts(account_id,username,password_hash) VALUES(%s,%s,%s)',
                                 (uuid4(),'legacy_player',password_hash('legacy-password-1234')))
                migration=(Path(__file__).parents[1]/'database'/f'{name}.sql').read_text()
                conn.execute(migration.removeprefix('BEGIN;').removesuffix('COMMIT;\n'))
            seed(conn)
        self.addCleanup(self.drop_schema)
        @contextmanager
        def isolated():
            with get_connection() as conn:
                conn.execute(sql.SQL('SET search_path TO {},public').format(sql.Identifier(self.schema)))
                yield conn
        self.connection=isolated
        for module in ['api.player_accounts','api.solo_routes','api.solo_difficulty','api.game_community']:
            p=patch(module+'.get_connection',isolated);p.start();self.addCleanup(p.stop)
        for module in ['api.player_accounts','api.solo_routes']:
            p=patch(module+'.rate_limit');p.start();self.addCleanup(p.stop)
        self.client=TestClient(app)
        response=self.client.post('/api/players/register',json={'username':'test_player','email':'player@example.com','password':'test-only-password-1234'})
        self.assertEqual(response.status_code,201,response.text)
        self.request=Request({'type':'http','headers':[(b'cookie',f'{COOKIE}={self.client.cookies.get(COOKIE)}'.encode())]})

    def drop_schema(self):
        with get_connection() as conn:conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    def start(self,difficulty='hard',category='ALL'):
        response=self.client.post('/api/solo/runs',json={'category':category,'difficulty':difficulty,'request_id':str(uuid4())})
        self.assertEqual(response.status_code,201,response.text);return response.json()

    def row(self,ident):
        with self.connection() as conn:return conn.execute('SELECT * FROM game_solo_runs WHERE run_id=%s',(ident,)).fetchone()

    def complete(self,difficulty='hard',wrong=False,timeout=False):
        run=self.start(difficulty);ident=run['run_id']
        for i in range(10):
            r=self.client.post(f'/api/solo/runs/{ident}/next',json={'previous':i});self.assertEqual(r.status_code,200,r.text)
            row=self.row(ident);choice=row['state']['deck'][i]['correct']
            if wrong and i==0:choice=str((int(choice)+1)%4)
            if timeout and i==9:
                with patch('api.solo_routes.now_ms',return_value=row['state']['deadline']):
                    r=self.client.get(f'/api/solo/runs/{ident}')
            else:r=self.client.post(f'/api/solo/runs/{ident}/answers',json={'position':i+1,'option_id':choice,'request_id':str(uuid4())})
            self.assertEqual(r.status_code,200,r.text)
        return ident,r.json()

    def test_register_login_logout_public_privacy_and_profile_edit(self):
        original=self.client.cookies.get(COOKIE)
        self.assertEqual(self.client.post('/api/players/register',json={'username':'TEST_PLAYER','email':'player@example.com','password':'test-only-password-1234'}).status_code,409)
        self.assertEqual(self.client.post('/api/players/login',json={'identifier':'player@example.com','password':'wrong-password-1234'}).status_code,401)
        r=self.client.patch('/api/players/me',json={'bio':'<script>hello</script>','accent':'pink'})
        self.assertEqual(r.status_code,200)
        p=self.client.get('/api/players/profiles/test_player').json();self.assertEqual(p['accent'],'pink')
        for key in ['email','password','password_hash','account_id','token_hash']:self.assertNotIn(key,p)
        self.assertEqual(self.client.post('/api/players/logout').status_code,200)
        self.assertEqual(self.client.get('/api/players/me').status_code,401)
        self.assertEqual(self.client.post('/api/players/login',json={'identifier':'PLAYER@example.com','password':'test-only-password-1234'}).status_code,200)
        self.assertNotEqual(original,self.client.cookies.get(COOKIE))

    def test_profile_cannot_set_xp_and_csrf_is_rejected(self):
        self.assertEqual(self.client.patch('/api/players/me',json={'total_xp':9999}).status_code,422)
        self.assertEqual(self.client.patch('/api/players/me',json={'accent':'pink'},headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/solo/runs',json={'difficulty':'hard','request_id':str(uuid4())},headers={'Origin':'https://evil.example'}).status_code,403)

    def test_perfect_hard_rewards_are_atomic_and_repeat_safe(self):
        ident,result=self.complete()
        self.assertEqual(result['total_xp'],900);self.assertTrue(result['streak_eligible'])
        self.client.get(f'/api/solo/runs/{ident}');self.client.get(f'/api/solo/runs/{ident}')
        me=self.client.get('/api/players/me').json();self.assertEqual(me['total_xp'],900);self.assertEqual(me['level'],3)
        self.assertEqual(result['player_progress'],{key:me[key] for key in ('total_xp','level','level_xp','next_level_xp')})
        self.assertEqual(me['streak']['current'],1)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_xp_ledger').fetchone()['n'],11)
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_daily_activity').fetchone()['n'],1)

    def test_early_exit_returns_committed_progress_and_is_repeat_safe(self):
        ident=self.start('easy')['run_id']
        self.client.post(f'/api/solo/runs/{ident}/next',json={'previous':0})
        choice=self.row(ident)['state']['deck'][0]['correct']
        self.client.post(f'/api/solo/runs/{ident}/answers',json={'position':1,'option_id':choice,'request_id':str(uuid4())})
        for method in ('post','post','get'):
            path=f'/api/solo/runs/{ident}'+('/leave' if method=='post' else '')
            response=getattr(self.client,method)(path)
            self.assertEqual(response.status_code,200,response.text)
            result=response.json()
            self.assertEqual(result['phase'],'ABANDONED')
            self.assertEqual(result['correct'],1);self.assertEqual(result['total_xp'],10)
            self.assertEqual(result['bonus_xp'],0)
            self.assertEqual(result['player_progress']['total_xp'],10)
            self.assertIsNotNone(result['player_progress']['next_level_xp'])

    def test_leaderboard_uses_ledger_and_exposes_only_public_player_fields(self):
        self.complete('easy')
        data=self.client.get('/api/community/leaderboard?period=today').json()
        self.assertEqual(data['participants'],1);self.assertTrue(data['signed_in'])
        row=data['entries'][0]
        self.assertEqual(row['xp'],100);self.assertEqual(row['rank'],1)
        self.assertEqual(set(row),{'rank','username','xp','total_xp','level','streak','wins','losses','played','win_rate','club','ranking_value'})
        self.assertEqual(data['me'],row)
        self.assertEqual(sum(b['count'] for b in data['distribution']),1)
        self.assertEqual(data['distribution'][1]['count'],1)
        anonymous=TestClient(app).get('/api/community/leaderboard').json()
        self.assertFalse(anonymous['signed_in']);self.assertIsNone(anonymous['me'])
        self.assertEqual(anonymous['entries'],data['entries'])

    def test_leaderboard_ties_pagination_and_own_rank_outside_page(self):
        self.complete('easy')
        original=self.client
        self.client=TestClient(app)
        self.client.post('/api/players/register',json={'username':'another_player','email':'another@example.com','password':'test-only-password'})
        self.complete('easy');self.client=original
        data=self.client.get('/api/community/leaderboard?limit=1').json()
        self.assertEqual(data['participants'],2)
        self.assertEqual(data['entries'][0]['username'],'another_player')
        self.assertEqual(data['entries'][0]['rank'],1)
        self.assertEqual(data['me']['username'],'test_player');self.assertEqual(data['me']['rank'],1)
        second=self.client.get('/api/community/leaderboard?limit=1&offset=1').json()
        self.assertEqual(second['entries'][0]['username'],'test_player');self.assertEqual(second['entries'][0]['rank'],1)

    def test_leaderboard_period_filter_and_input_validation(self):
        self.complete('easy')
        from datetime import timedelta
        with patch('api.game_community.period_start',return_value=datetime.now(timezone.utc)+timedelta(days=1)):
            self.assertEqual(self.client.get('/api/community/leaderboard').json()['participants'],0)
        self.assertEqual(self.client.get('/api/community/leaderboard?period=all').json()['entries'][0]['xp'],100)
        for query in ['period=pvp','limit=0','limit=101','offset=-1','offset=10001']:
            self.assertEqual(self.client.get('/api/community/leaderboard?'+query).status_code,422)

    def test_private_history_omits_active_runs_and_other_accounts(self):
        ident,_=self.complete('easy')
        active=self.start('hard')['run_id']
        data=self.client.get('/api/community/history').json()
        self.assertEqual(len(data['items']),1);self.assertEqual(data['items'][0]['run_id'],ident)
        self.assertEqual(data['items'][0]['xp'],100)
        self.assertNotIn('deck',data['items'][0]);self.assertNotIn('answers',data['items'][0])
        self.assertEqual(TestClient(app).get('/api/community/history').status_code,401)
        other=TestClient(app)
        other.post('/api/players/register',json={'username':'other_player','email':'other@example.com','password':'test-only-password'})
        self.assertEqual(other.get('/api/community/history').json()['items'],[])
        self.assertEqual(other.get('/api/solo/runs/'+ident).status_code,404)
        self.client.post('/api/solo/runs/'+active+'/leave')
        page=self.client.get('/api/community/history?limit=1').json()
        self.assertTrue(page['has_more']);self.assertEqual(page['items'][0]['run_id'],active)
        self.assertEqual(self.client.get('/api/community/history?limit=1&offset=1').json()['items'][0]['run_id'],ident)

    def test_wrong_answer_and_timeout_have_distinct_streak_rules(self):
        _,r=self.complete(wrong=True);self.assertEqual(r['total_xp'],270);self.assertTrue(r['streak_eligible'])
        _,r=self.complete('medium',timeout=True);self.assertEqual(r['total_xp'],180);self.assertFalse(r['streak_eligible'])
        self.assertEqual(self.client.get('/api/players/me').json()['total_xp'],450)

    def test_answer_at_fourteen_seconds_is_saved_and_deck_stays_frozen(self):
        run=self.start();ident=run['run_id']
        self.assertEqual(run['rules']['answer_ms'],15000)
        self.client.post(f'/api/solo/runs/{ident}/next',json={'previous':0})
        before=self.row(ident)['state'];choice=before['deck'][0]['correct']
        with patch('api.solo_routes.now_ms',return_value=before['opened_at']+14000):
            response=self.client.post(f'/api/solo/runs/{ident}/answers',json={
                'position':1,'option_id':choice,'request_id':str(uuid4())})
        self.assertEqual(response.status_code,200,response.text)
        with self.connection() as conn:
            saved=conn.execute('SELECT correct,elapsed_ms FROM game_solo_answers WHERE run_id=%s',(ident,)).fetchone()
        self.assertEqual(saved,{'correct':True,'elapsed_ms':14000})
        self.assertEqual(self.row(ident)['state']['deck'],before['deck'])

    def test_all_difficulties_have_expected_perfect_reward(self):
        for difficulty,xp in [('easy',100),('medium',400)]:
            _,result=self.complete(difficulty);self.assertEqual(result['total_xp'],xp)

    def test_full_bank_release_is_checked_idempotent_and_keeps_started_quizzes(self):
        ident=self.start()['run_id'];frozen=self.row(ident)['state']
        with self.connection() as conn:
            published=routes.latest_release(conn)
            before=conn.execute('SELECT count(*) n FROM game_question_difficulty').fetchone()['n']
            dry=release_solo_bank(conn,published)
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_question_difficulty').fetchone()['n'],before)
            self.assertEqual(dry['actions'],{'add':1920,'keep':30})
            result=release_solo_bank(conn,published,True)
            self.assertEqual(result['available_by_difficulty'],{'medium':404,'easy':38,'hard':1508})
            self.assertTrue(all(not q['issues'] for q in result['questions']))
            self.assertEqual(sum(result['answer_authority'].values()),1950)
            again=release_solo_bank(conn,published,True)
            self.assertEqual(again['actions'],{'keep':1950})
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_question_difficulty').fetchone()['n'],before+1920)
        self.assertEqual(self.row(ident)['state'],frozen)
        self.client.post(f'/api/solo/runs/{ident}/leave')
        counts=self.client.get('/api/solo/catalog').json()['categories'][0]['counts']
        self.assertEqual(counts,{'easy':38,'medium':404,'hard':1498})
        first=self.row(self.start()['run_id'])['state']['deck']
        self.assertFalse({q['question_id'] for q in first}&{q['question_id'] for q in frozen['deck']})

    def test_bulk_release_preserves_explicit_editor_holds_and_custom_classifications(self):
        with self.connection() as conn:
            published=routes.latest_release(conn)
            rows=conn.execute('SELECT * FROM game_current_difficulty WHERE release_id=%s AND NOT approved LIMIT 2',(published,)).fetchall()
            for row,approved in zip(rows,[False,True]):
                conn.execute('''INSERT INTO game_question_difficulty(release_id,question_id,difficulty,approved,reason,reviewed_by)
                    VALUES(%s,%s,'easy',%s,'Explicit manual editorial decision','test-editor')''',
                    (published,row['question_id'],approved))
            result=release_solo_bank(conn,published,True)
            self.assertEqual(result['actions'],{'add':1918,'keep':31,'editor_hold':1})
            for row,approved in zip(rows,[False,True]):
                current=conn.execute('SELECT * FROM game_current_difficulty WHERE release_id=%s AND question_id=%s',
                                     (published,row['question_id'])).fetchone()
                self.assertEqual(current['approved'],approved);self.assertEqual(current['reviewed_by'],'test-editor')
                self.assertEqual(current['difficulty'],'easy')

    def test_every_playable_topic_is_strict_and_catalog_counts_match_decks(self):
        with self.connection() as conn:release_solo_bank(conn,routes.latest_release(conn),True)
        catalog=self.client.get('/api/solo/catalog').json()
        self.assertEqual({t['code'] for t in catalog['topics']},{'ALL',*TOPICS})
        all_counts=catalog['categories'][0]['counts']
        for level in ('easy','medium','hard'):
            self.assertEqual(sum(t['counts_by_team'].get('ALL',{}).get(level,0) for t in catalog['topics'][1:]),all_counts[level])
        with self.connection() as conn:
            source_topics=conn.execute("SELECT DISTINCT question->>'topic' topic FROM penalty_bank_questions WHERE release_id=%s",(routes.latest_release(conn),)).fetchall()
            self.assertTrue({r['topic'] for r in source_topics}<=set(SOURCE_TOPIC))
        for topic in catalog['topics'][1:]:
            for level,count in topic['counts_by_team'].get('ALL',{}).items():
                with self.subTest(topic=topic['code'],difficulty=level):
                    response=self.client.post('/api/solo/runs',json={'topic':topic['code'],'difficulty':level,'request_id':str(uuid4())})
                    if count<10:
                        self.assertEqual(response.status_code,409);continue
                    self.assertEqual(response.status_code,201,response.text)
                    ident=response.json()['run_id'];state=self.row(ident)['state']
                    self.assertEqual(state['category']['topic_code'],topic['code'])
                    self.assertEqual(len(state['deck']),10)
                    self.assertTrue(all(SOURCE_TOPIC[q['topic']]==topic['code'] for q in state['deck']))
                    now=self.client.get('/api/solo/catalog').json()
                    changed=next(t for t in now['topics'] if t['code']==topic['code'])
                    self.assertEqual(changed['counts_by_team']['ALL'][level],count-10)
                    self.client.post(f'/api/solo/runs/{ident}/leave')

    def test_topic_and_club_filters_intersect_and_unknown_topics_are_rejected(self):
        with self.connection() as conn:release_solo_bank(conn,routes.latest_release(conn),True)
        self.assertEqual(self.client.post('/api/solo/runs',json={'topic':'invented','request_id':str(uuid4())}).status_code,422)
        topics=self.client.get('/api/solo/catalog').json()['topics']
        chosen=next(t for t in topics if t['code']!='ALL' and t['counts_by_team'].get('MUN',{}).get('hard',0)>=10)
        response=self.client.post('/api/solo/runs',json={'topic':chosen['code'],'category':'MUN','difficulty':'hard','request_id':str(uuid4())})
        self.assertEqual(response.status_code,201,response.text)
        for q in self.row(response.json()['run_id'])['state']['deck']:
            self.assertEqual(SOURCE_TOPIC[q['topic']],chosen['code'])
            self.assertTrue(q['source']['external_id'].startswith('MUN-'))

    def test_topic_change_cannot_reuse_start_request_or_silently_resume_other_topic(self):
        with self.connection() as conn:release_solo_bank(conn,routes.latest_release(conn),True)
        payload={'topic':'kits','difficulty':'medium','request_id':str(uuid4())}
        response=self.client.post('/api/solo/runs',json=payload);self.assertEqual(response.status_code,201)
        ident=response.json()['run_id'];before=self.row(ident)['state']
        self.assertEqual(self.client.post('/api/solo/runs',json=payload).json()['run_id'],ident)
        for request_id in [payload['request_id'],str(uuid4())]:
            self.assertEqual(self.client.post('/api/solo/runs',json={**payload,'topic':'players','request_id':request_id}).status_code,409)
        self.assertEqual(self.row(ident)['state'],before)
        with self.connection() as conn:
            with self.assertRaises(Exception),conn.transaction():
                conn.execute("UPDATE game_solo_runs SET state=jsonb_set(state,'{category,topic_code}','\"players\"') WHERE run_id=%s",(ident,))
        self.client.post(f'/api/solo/runs/{ident}/leave')
        mixed=self.row(self.start('medium')['run_id'])['state']
        self.assertFalse({q['question_id'] for q in before['deck']}&{q['question_id'] for q in mixed['deck']})

    def test_empty_difficulty_never_silently_falls_back(self):
        r=self.client.post('/api/solo/runs',json={'category':'GEN','difficulty':'easy','request_id':str(uuid4())})
        self.assertEqual(r.status_code,409)
        catalog=self.client.get('/api/solo/catalog').json()
        for category in catalog['categories']:self.assertEqual(set(category),{'code','label','counts'})
        self.assertNotIn('options',str(catalog));self.assertNotIn('explanation',str(catalog))
        self.assertEqual(catalog['categories'][0]['counts'],{'easy':10,'medium':10,'hard':10})

    def test_weekly_history_reserves_unopened_questions_and_survives_abandonment(self):
        ident=self.start()['run_id'];before=self.row(ident)['state']
        expected={q['question_id'] for q in before['deck']}
        history=self.client.get('/api/solo/history').json()
        self.assertEqual({q for day in history['days'] for q in day['question_ids']},expected)
        self.assertEqual(len(history['days']),1)
        self.client.post(f'/api/solo/runs/{ident}/leave')
        self.assertEqual(self.client.get('/api/solo/history').json(),history)
        r=self.client.post('/api/solo/runs',json={'category':'GEN','difficulty':'hard','request_id':str(uuid4())})
        self.assertEqual(r.status_code,409);self.assertIn('No new shootout',r.json()['detail'])
        self.assertEqual(self.client.get('/api/solo/catalog').json()['categories'][0]['counts']['hard'],0)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_question_history').fetchone()['n'],10)
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_solo_runs').fetchone()['n'],1)

    def test_allocation_is_per_account_and_history_is_private(self):
        self.start()
        outsider=TestClient(app)
        self.assertEqual(outsider.get('/api/solo/history').status_code,401)
        outsider.post('/api/players/register',json={'username':'other_history','email':'other_history@example.com','password':'test-only-password'})
        self.assertEqual(outsider.get('/api/solo/history').json()['days'],[])
        self.assertEqual(outsider.get('/api/solo/catalog').json()['categories'][0]['counts']['hard'],10)
        self.assertEqual(outsider.post('/api/solo/runs',json={'difficulty':'hard','request_id':str(uuid4())}).status_code,201)

    def test_daily_ids_are_grouped_without_resetting_at_midnight(self):
        monday=int(datetime(2026,9,21,tzinfo=timezone.utc).timestamp()*1000)
        with patch('api.solo_routes.now_ms',return_value=monday):
            ident=self.start('easy')['run_id'];self.client.post(f'/api/solo/runs/{ident}/leave')
        with patch('api.solo_routes.now_ms',return_value=monday+86400000):
            self.start('medium')
            days=self.client.get('/api/solo/history').json()['days']
            self.assertEqual([day['day'] for day in days],['2026-09-21','2026-09-22'])
            self.assertTrue(all(len(day['question_ids'])==10 for day in days))
            counts=self.client.get('/api/solo/catalog').json()['categories'][0]['counts']
            self.assertEqual(counts,{'easy':0,'medium':0,'hard':10})

    def test_monday_reset_allows_reuse_without_deleting_history_or_xp(self):
        sunday=int(datetime(2026,9,27,23,59,tzinfo=timezone.utc).timestamp()*1000)
        with patch('api.solo_routes.now_ms',return_value=sunday):
            ident,_=self.complete('hard');old=self.row(ident)['state']
            self.assertEqual(self.client.get('/api/solo/catalog').json()['categories'][0]['counts']['hard'],0)
        with patch('api.solo_routes.now_ms',return_value=sunday+60000):
            catalog=self.client.get('/api/solo/catalog').json()
            self.assertEqual(catalog['week_start'],'2026-09-28')
            self.assertEqual(catalog['resets_at'],'2026-10-05T00:00:00+00:00')
            self.assertEqual(catalog['categories'][0]['counts']['hard'],10)
            self.assertEqual(self.client.get('/api/solo/history').json()['days'],[])
            new=self.row(self.start()['run_id'])['state']
            self.assertEqual({q['question_id'] for q in new['deck']},{q['question_id'] for q in old['deck']})
        self.assertEqual(self.row(ident)['state'],old)
        self.assertEqual(self.client.get('/api/players/me').json()['total_xp'],900)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_question_history').fetchone()['n'],20)

    def test_active_quiz_and_idempotent_start_keep_order_across_week_boundary(self):
        sunday=int(datetime(2026,9,27,23,59,tzinfo=timezone.utc).timestamp()*1000)
        payload={'difficulty':'hard','request_id':str(uuid4())}
        with patch('api.solo_routes.now_ms',return_value=sunday):
            ident=self.client.post('/api/solo/runs',json=payload).json()['run_id']
            self.client.post(f'/api/solo/runs/{ident}/next',json={'previous':0})
            original=self.row(ident)['state']
        with patch('api.solo_routes.now_ms',return_value=sunday+60000):
            retry=self.client.post('/api/solo/runs',json=payload)
            self.assertEqual(retry.status_code,201);self.assertEqual(retry.json()['run_id'],ident)
            self.assertEqual(self.start('easy')['run_id'],ident)
            self.assertEqual(self.row(ident)['state']['deck'],original['deck'])
            self.assertEqual(self.client.get('/api/solo/history').json()['days'],[])
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_question_history').fetchone()['n'],10)

    def test_concurrent_starts_allocate_only_one_deck(self):
        def start():return routes.start(routes.Start(difficulty='hard',request_id=uuid4()),self.request,Response())
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(start) for _ in range(2)]
            runs=[f.result() for f in futures]
        self.assertEqual(runs[0]['run_id'],runs[1]['run_id'])
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_question_history').fetchone()['n'],10)

    def test_difficulty_change_cannot_reintroduce_reserved_ids(self):
        ident=self.start()['run_id'];deck=self.row(ident)['state']['deck']
        self.client.post(f'/api/solo/runs/{ident}/leave')
        with self.connection() as conn:
            for q in deck:
                conn.execute('''INSERT INTO game_question_difficulty(release_id,question_id,difficulty,approved,reason,reviewed_by)
                    VALUES(%s,%s,'easy',true,'Test reclassification only','test')''',(q['release_id'],q['question_id']))
        self.assertEqual(self.client.get('/api/solo/catalog').json()['categories'][0]['counts']['easy'],10)
        self.assertEqual(TestClient(app).get('/api/solo/catalog').json()['categories'][0]['counts']['easy'],20)
        new=self.row(self.start('easy')['run_id'])['state']['deck']
        self.assertFalse({q['question_id'] for q in deck}&{q['question_id'] for q in new})

    def test_failed_start_rolls_back_without_allocations(self):
        with patch('api.solo_routes.public',side_effect=RuntimeError('Failure before commit')):
            with self.assertRaises(RuntimeError):self.start()
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_question_history').fetchone()['n'],0)
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_solo_runs').fetchone()['n'],0)
        self.start()

    def test_database_rejects_repeated_decks_and_history_mutation(self):
        ident=self.start()['run_id'];row=self.row(ident)
        self.client.post(f'/api/solo/runs/{ident}/leave')
        with self.connection() as conn:
            with self.assertRaises(Exception),conn.transaction():
                conn.execute('''INSERT INTO game_solo_runs(run_id,account_id,start_request_id,state)
                    VALUES(%s,%s,%s,%s)''',(uuid4(),row['account_id'],uuid4(),Jsonb(row['state'])))
            for query in ['DELETE FROM game_question_history',"UPDATE game_question_history SET day=day+7,week_start=week_start+7"]:
                with self.assertRaises(Exception),conn.transaction():conn.execute(query)
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_question_history').fetchone()['n'],10)
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_solo_runs').fetchone()['n'],1)

    def test_migration_backfills_legacy_duplicates_and_is_reentrant(self):
        ident=self.start()['run_id'];self.client.post(f'/api/solo/runs/{ident}/leave');row=self.row(ident)
        with self.connection() as conn:
            conn.execute('DROP TRIGGER game_allocate_questions ON game_solo_runs')
            conn.execute('DROP TRIGGER game_question_history_immutable ON game_question_history')
            conn.execute('DELETE FROM game_question_history')
            state=deepcopy(row['state']);state['created_at']+=1
            conn.execute('INSERT INTO game_solo_runs(run_id,account_id,start_request_id,state) VALUES(%s,%s,%s,%s)',
                         (uuid4(),row['account_id'],uuid4(),Jsonb(state)))
            migration=(Path(__file__).parents[1]/'database/040_weekly_question_history.sql').read_text().removeprefix('BEGIN;').removesuffix('COMMIT;\n')
            conn.execute(migration);conn.execute(migration)
            allocations=conn.execute('SELECT * FROM game_question_history').fetchall()
            self.assertEqual(len(allocations),10)
            self.assertTrue(all(str(a['run_id'])==ident for a in allocations))
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_solo_runs').fetchone()['n'],2)
        self.assertEqual(self.row(ident)['state'],row['state'])

    def test_stale_next_idempotency_and_no_answer_leak(self):
        run=self.start();ident=run['run_id'];self.assertIsNone(run['question'])
        first=self.client.post(f'/api/solo/runs/{ident}/next',json={'previous':0}).json()
        second=self.client.post(f'/api/solo/runs/{ident}/next',json={'previous':0}).json()
        self.assertEqual(first['deadline'],second['deadline']);self.assertEqual(set(first['question']),{'text','options'})
        self.assertEqual(self.start('easy')['run_id'],ident)
        outsider=TestClient(app)
        outsider.post('/api/players/register',json={'username':'another_player','email':'another@example.com','password':'test-only-password-1234'})
        self.assertEqual(outsider.get(f'/api/solo/runs/{ident}').status_code,404)

    def test_concurrent_answer_retries_award_once(self):
        run=self.start();ident=run['run_id'];routes.action(ident,self.request,'next',routes.Next(previous=0))
        choice=self.row(ident)['state']['deck'][0]['correct'];body=routes.Answer(position=1,option_id=choice,request_id=uuid4())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=[pool.submit(routes.action,ident,self.request,'answer',body) for _ in range(2)]
            for result in results:self.assertEqual(result.result()['total_xp'],30)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_solo_answers').fetchone()['n'],1)
            self.assertEqual(conn.execute('SELECT sum(amount) n FROM game_xp_ledger').fetchone()['n'],30)

    def test_late_answer_commits_timeout_even_when_command_rejected(self):
        ident=self.start()['run_id'];routes.action(ident,self.request,'next',routes.Next(previous=0))
        s=self.row(ident)['state']
        with patch('api.solo_routes.now_ms',return_value=s['deadline']):
            with self.assertRaises(HTTPException):routes.action(ident,self.request,'answer',routes.Answer(position=1,option_id=s['deck'][0]['correct'],request_id=uuid4()))
        with self.connection() as conn:
            row=conn.execute('SELECT * FROM game_solo_answers WHERE run_id=%s',(ident,)).fetchone()
            self.assertIsNone(row['option_id']);self.assertFalse(row['correct'])

    def test_database_guards_prevent_reward_forgery_and_history_rewrite(self):
        ident=self.start()['run_id'];row=self.row(ident)
        with self.connection() as conn:
            for query,params in [
                ("INSERT INTO game_xp_ledger VALUES(%s,%s,1,10,'correct_answer',DEFAULT)",(row['account_id'],ident)),
                ("INSERT INTO game_daily_activity VALUES(%s,CURRENT_DATE,%s)",(row['account_id'],ident)),
                ("UPDATE game_solo_runs SET state=jsonb_set(state,'{rules,answer_ms}','20000') WHERE run_id=%s",(ident,)),
                ("UPDATE game_question_difficulty SET difficulty='easy'",()),
            ]:
                with self.assertRaises(Exception),conn.transaction():conn.execute(query,params)

    def test_difficulty_change_does_not_modify_started_quiz(self):
        ident=self.start()['run_id'];before=self.row(ident)['state'];q=before['deck'][0]
        with self.connection() as conn:
            conn.execute('''INSERT INTO game_question_difficulty(release_id,question_id,difficulty,approved,reason,reviewed_by)
                VALUES(%s,%s,'easy',false,'Test editorial retirement','test')''',(q['release_id'],q['question_id']))
        self.assertEqual(self.row(ident)['state'],before)
        self.assertEqual(self.client.get('/api/solo/catalog').json()['categories'][0]['counts']['hard'],0)
        self.assertEqual(TestClient(app).get('/api/solo/catalog').json()['categories'][0]['counts']['hard'],9)

    def test_forged_answer_cannot_be_used_to_mint_xp(self):
        ident=self.start()['run_id'];q=self.row(ident)['state']['deck'][0]
        with self.connection() as conn:
            with self.assertRaises(Exception),conn.transaction():
                conn.execute('''INSERT INTO game_solo_answers VALUES(%s,1,%s,%s,%s,%s,%s,true,1000,clock_timestamp())''',
                             (ident,uuid4(),q['release_id'],q['question_id'],q['difficulty_revision'],q['correct']))

    def test_editor_difficulty_api_is_not_accessible_to_a_player(self):
        with patch.dict(os.environ,{'TRIVIA_EDITOR_USERNAME':'editor','TRIVIA_EDITOR_PASSWORD':'long-local-test-password'}):
            self.assertEqual(self.client.get('/api/solo/editor/difficulty').status_code,401)
            self.assertEqual(self.client.get('/internal/trivia/difficulty',follow_redirects=False).status_code,303)
            r=self.client.get('/api/solo/editor/difficulty',auth=('editor','long-local-test-password'))
            self.assertEqual(r.status_code,200)
            q=r.json()['questions'][0]
            payload={'release_id':q['release_id'],'question_id':q['question_id'],'difficulty':'medium','approved':True,'reason':'Editorial review test only'}
            r=self.client.post('/api/solo/editor/difficulty',json=payload,auth=('editor','long-local-test-password'))
            self.assertEqual(r.status_code,200,r.text)
            with self.connection() as conn:
                self.assertEqual(conn.execute('SELECT reviewed_by FROM game_question_difficulty WHERE revision_id=%s',(r.json()['revision_id'],)).fetchone()['reviewed_by'],'editor')

    def test_registration_requires_valid_unique_email_and_eight_character_password(self):
        new=TestClient(app)
        data={'username':'new_player','email':'new@example.com','password':'eight888'}
        self.assertEqual(new.post('/api/players/register',json={k:v for k,v in data.items() if k!='email'}).status_code,422)
        self.assertEqual(new.post('/api/players/register',json={**data,'email':'not-an-email'}).status_code,422)
        self.assertEqual(new.post('/api/players/register',json={**data,'password':'seven77'}).status_code,422)
        self.assertEqual(new.post('/api/players/register',json=data).status_code,201)
        self.assertEqual(new.post('/api/players/register',json={**data,'username':'different_player','email':'NEW@EXAMPLE.COM'}).status_code,409)
        new.post('/api/players/logout')
        self.assertEqual(new.post('/api/players/login',json={'identifier':'new_player','password':'eight888'}).status_code,401)
        self.assertEqual(new.post('/api/players/login',json={'identifier':'NEW@EXAMPLE.COM','password':'eight888'}).status_code,200)
        self.assertEqual(new.get('/api/players/me').json()['email'],'new@example.com')
        self.assertNotIn('email',new.get('/api/players/profiles/new_player').json())

    def test_legacy_account_can_add_email_without_losing_identity_or_sessions_being_reused(self):
        legacy=TestClient(app)
        self.assertEqual(legacy.post('/api/players/login',json={'identifier':'legacy_player','password':'legacy-password-1234'}).status_code,200)
        old_token=legacy.cookies.get(COOKIE)
        self.assertIsNone(legacy.get('/api/players/me').json()['email'])
        data={'email':'LEGACY@EXAMPLE.COM','password':'legacy-password-1234'}
        self.assertEqual(legacy.put('/api/players/email',json={**data,'password':'wrong-password'}).status_code,401)
        self.assertEqual(legacy.put('/api/players/email',json=data,headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(legacy.put('/api/players/email',json=data).status_code,200)
        self.assertEqual(legacy.get('/api/players/me').json()['email'],'legacy@example.com')
        self.assertNotEqual(legacy.cookies.get(COOKIE),old_token)
        stale=TestClient(app);stale.cookies.set(COOKIE,old_token)
        self.assertEqual(stale.get('/api/players/me').status_code,401)
        legacy.post('/api/players/logout')
        self.assertEqual(legacy.post('/api/players/login',json={'identifier':'legacy@example.com','password':'legacy-password-1234'}).status_code,200)

    def test_guest_can_complete_and_start_another_without_persisted_rewards(self):
        self.client=TestClient(app)
        self.assertEqual(self.client.get('/api/solo/active').json(),{'run':None,'trial_available':True})
        ident,result=self.complete('hard')
        self.assertEqual(result['total_xp'],900);self.assertTrue(result['is_trial']);self.assertFalse(result['xp_saved'])
        self.assertFalse(result['streak_eligible']);self.assertEqual(self.client.get('/api/players/me').status_code,401)
        self.assertIsNotNone(self.client.cookies.get(TRIAL_COOKIE))
        self.assertIsNone(self.client.get('/api/solo/active').json()['run'])
        self.assertEqual(self.client.post('/api/solo/runs',json={'difficulty':'hard','request_id':str(uuid4())}).status_code,201)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_xp_ledger').fetchone()['n'],0)
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_daily_activity').fetchone()['n'],0)
            row=conn.execute('SELECT * FROM game_accounts WHERE is_guest').fetchone()
            self.assertEqual(self.client.get('/api/players/profiles/'+row['username']).status_code,404)
            with self.assertRaises(Exception),conn.transaction():
                conn.execute("INSERT INTO game_xp_ledger VALUES(%s,%s,1,30,'correct_answer',DEFAULT)",(row['account_id'],ident))
        new_account=self.client.post('/api/players/register',json={'username':'after_trial','email':'after@example.com','password':'eight888'})
        self.assertEqual(new_account.status_code,201);self.assertEqual(new_account.json()['total_xp'],0)
        self.assertFalse(self.start('easy')['is_trial'])

    def test_trial_cookie_does_not_grant_account_access_and_outsiders_cannot_read(self):
        self.client=TestClient(app);ident=self.start()['run_id'];token=self.client.cookies.get(TRIAL_COOKIE)
        impostor=TestClient(app);impostor.cookies.set(COOKIE,token)
        self.assertEqual(impostor.get('/api/players/me').status_code,401)
        self.assertEqual(impostor.get(f'/api/solo/runs/{ident}').status_code,401)
        outsider=TestClient(app)
        self.assertEqual(outsider.get(f'/api/solo/runs/{ident}').status_code,401)
        self.client.post(f'/api/solo/runs/{ident}/leave')
        self.assertEqual(self.client.post('/api/solo/runs',json={'difficulty':'easy','request_id':str(uuid4())}).status_code,201)

    def test_trial_start_retries_in_two_tabs_share_one_quiz(self):
        self.client=TestClient(app);ident=self.start()['run_id'];token=self.client.cookies.get(TRIAL_COOKIE)
        request=Request({'type':'http','headers':[(b'cookie',f'{TRIAL_COOKIE}={token}'.encode())]})
        from fastapi import Response
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=[pool.submit(routes.start,routes.Start(difficulty='hard',request_id=uuid4()),request,Response()) for _ in range(2)]
            self.assertEqual({r.result()['run_id'] for r in results},{ident})
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) n FROM game_solo_runs WHERE is_trial').fetchone()['n'],1)

    def test_legacy_rules_still_pay_the_original_frozen_rate(self):
        with patch.dict(routes.game.RULES,{'version':'solo-v1','xp_by_difficulty':{'easy':10,'medium':10,'hard':10}}):
            ident,result=self.complete('hard')
        self.assertEqual(result['total_xp'],300)
        self.assertEqual(self.client.get(f'/api/solo/runs/{ident}').json()['total_xp'],300)
        self.assertEqual(self.client.get('/api/players/me').json()['total_xp'],300)

    def test_database_rejects_a_reward_at_the_wrong_difficulty_rate(self):
        ident=self.start()['run_id'];routes.action(ident,self.request,'next',routes.Next(previous=0))
        row=self.row(ident);q=row['state']['deck'][0]
        # Resolve correctly, then attempt a differently valued duplicate award.
        routes.action(ident,self.request,'answer',routes.Answer(position=1,option_id=q['correct'],request_id=uuid4()))
        with self.connection() as conn:
            with self.assertRaises(Exception),conn.transaction():
                conn.execute("INSERT INTO game_xp_ledger VALUES(%s,%s,1,10,'correct_answer',DEFAULT) ON CONFLICT DO NOTHING",(row['account_id'],ident))
