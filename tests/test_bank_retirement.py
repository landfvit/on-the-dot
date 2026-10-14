"""Rollback-only checks for replacement without deleting immutable game data."""
from datetime import date,datetime,timezone
import os
import unittest
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from api.bank_lifecycle import active_releases,retain_curated_bank,retired_releases
from api.challenge_routes import candidates,daily_pool,snapshots
from api.database import get_connection
from api.penalty_bank import load_pack
from api.question_publication import publish
from api.solo_routes import load_deck,Start
from api.trivia_bank_routes import latest


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Local rollback-only database tests')
class BankRetirementTests(unittest.TestCase):
    def setUp(self):
        self.conn=get_connection();self.addCleanup(self.conn.close);self.addCleanup(self.conn.rollback)
        self.assertIn(self.conn.info.host,('localhost','127.0.0.1','::1',''))
        self.keep=self.conn.execute('''SELECT r.release_id,v.dataset_id FROM penalty_bank_releases r
            JOIN trivia_bank_validation_runs v ON r.validation_run_id=v.run_id
            JOIN trivia_bank_batches b USING(batch_id) WHERE b.source_name='curated-pl-3000-v1'
            ORDER BY r.created_at DESC LIMIT 1''').fetchone()
        if not self.keep:self.skipTest('Publish the curated bank locally first')
        self.release=self.keep['release_id']
        # A separate temporary batch lets these tests run before or after the
        # real replacement. Every insert is rolled back by the fixture.
        item={'id':'RETIRE-TEST-GEN-001','question':'Which club is this retirement test about '+uuid4().hex+'?',
              'answer':'Arsenal','options':['Arsenal','Chelsea','Everton','Liverpool'],'correct':0,
              'difficulty':'easy','topic':'Club identity','section':'General','sources':[],
              'check':'Test fixture, never committed','evidence':{'status':'unsupported','method':'test'}}
        self.old,_=publish(self.conn,[item],self.keep['dataset_id'],'test-retirement-'+uuid4().hex,'rollback-test')

    def retire(self):return retain_curated_bank(self.conn,self.release,'rollback-test')

    def test_retirement_is_idempotent_and_only_new_questions_are_playable(self):
        count=self.conn.execute('SELECT count(*) n FROM penalty_bank_questions').fetchone()['n']
        self.retire();self.assertEqual(set(active_releases(self.conn)),{self.release})
        self.assertEqual(self.retire()['retired_batches'],0)
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM penalty_bank_questions').fetchone()['n'],count)
        self.assertEqual(len(candidates(self.conn)),3000)
        self.assertEqual(latest(self.conn)['question_count'],3000)
        for difficulty in ('easy','medium','hard'):
            deck,_=load_deck(self.conn,uuid4(),Start(request_id=uuid4(),difficulty=difficulty),0)
            self.assertTrue(all(q['release_id']==str(self.release) for q in deck))
        with self.assertRaises(HTTPException) as error:load_pack(self.conn,f'bank:{self.old}:ALL')
        self.assertEqual(error.exception.status_code,410)

    def test_daily_cached_pool_replaced_without_rewriting_original(self):
        old=snapshots(self.conn,[r for r in candidates(self.conn) if r['release_id']==self.old])
        day=date(2080,3,1);now=int(datetime.combine(day,datetime.min.time(),timezone.utc).timestamp()*1000)
        self.conn.execute('INSERT INTO game_daily_pools(day,deck,version) VALUES(%s,%s,2)',(day,Jsonb(old)))
        self.retire();replacement,_,_=daily_pool(self.conn,now)
        self.assertEqual(len(replacement),1000)
        self.assertTrue(all(q['release_id']==str(self.release) for q in replacement))
        self.assertEqual(daily_pool(self.conn,now)[0],replacement)
        original=self.conn.execute('SELECT deck FROM game_daily_pools WHERE day=%s',(day,)).fetchone()['deck']
        self.assertEqual(original,old)
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM game_daily_bank_pools WHERE day=%s',(day,)).fetchone()['n'],1)

    def test_invalid_replacement_leaves_current_bank_untouched(self):
        before=retired_releases(self.conn)
        with self.assertRaises(ValueError):retain_curated_bank(self.conn,self.old,'rollback-test')
        self.assertEqual(before,retired_releases(self.conn))
        self.assertIn(self.release,active_releases(self.conn))

    def test_future_approved_submission_can_join_the_new_bank(self):
        self.retire()
        item={'id':'COMMUNITY-LATER-GEN-001','question':'Which club is the later approved test about '+uuid4().hex+'?',
              'answer':'Chelsea','options':['Arsenal','Chelsea','Everton','Liverpool'],'correct':1,
              'difficulty':'medium','topic':'Club identity','section':'General','sources':[],
              'check':'Test fixture, never committed','evidence':{'status':'unsupported','method':'editor_reviewed'}}
        release,_=publish(self.conn,[item],self.keep['dataset_id'],'community-'+uuid4().hex,'rollback-test')
        self.assertEqual(set(active_releases(self.conn)),{self.release,release})
        self.assertNotIn(self.old,active_releases(self.conn))
