from collections import Counter
from contextlib import contextmanager
import hashlib
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from api.database import get_connection
from api.penalty_bank import catalog,load_pack,option_key
from api import penalty_engine as game
from api import penalty_routes as routes
from src.publish_penalty_bank import publish
from trivia_app.main import app


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Rollback-only local PostgreSQL checks')
class PenaltyBankDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn=get_connection();self.addCleanup(self.conn.close);self.addCleanup(self.conn.rollback)
        @contextmanager
        def shared(): yield self.conn
        p=patch('api.penalty_routes.get_connection',shared);p.start();self.addCleanup(p.stop)
        self.release=self.conn.execute("SELECT * FROM penalty_bank_releases WHERE choice_version='bank-choices-v1' ORDER BY created_at LIMIT 1").fetchone()
        self.client=TestClient(app)

    def test_all_1950_have_one_reference_answer_and_correct_sections(self):
        rows=self.conn.execute('''SELECT p.*,q.content,c.status FROM penalty_bank_questions p
            JOIN trivia_bank_questions q USING(question_id)
            JOIN penalty_bank_releases r USING(release_id)
            JOIN trivia_bank_checks c ON c.run_id=r.validation_run_id AND c.question_id=p.question_id
            WHERE p.release_id=%s''',(self.release['release_id'],)).fetchall()
        self.assertEqual(len(rows),1950)
        counts=Counter(r['section_name'] for r in rows)
        self.assertEqual(counts.pop('General'),250)
        self.assertEqual(len(counts),34)
        self.assertEqual(set(counts.values()),{50})
        for row in rows:
            with self.subTest(question=row['content']['id']):
                q=row['question']
                self.assertEqual(q['text'],row['content']['question'])
                self.assertEqual(len({option_key(o['text']) for o in q['options']}),4)
                self.assertEqual(next(o['text'] for o in q['options'] if o['id']==q['correct']),row['content']['answer'])
                self.assertEqual(q['validation_status'],row['status'])
                self.assertEqual(q['authority'],'database_matched' if row['status']=='matched' else 'user_attested')

    def test_catalog_is_public_metadata_only(self):
        response=self.client.get('/api/penalties/packs')
        self.assertEqual(response.status_code,200)
        packs=response.json()['packs']
        self.assertEqual(packs[0]['label'],'General')
        bank=[p for p in packs if p['id'].startswith('bank:')]
        self.assertEqual(len(bank),36)
        self.assertGreaterEqual(bank[0]['count'],250)
        self.assertGreaterEqual(bank[1]['count'],1950)
        self.assertNotIn('options',response.text)
        self.assertNotIn('explanation',response.text)
        self.assertNotIn('correct',response.text)

    def test_all_packs_resolve_both_modes_without_duplicates(self):
        for pack in catalog(self.conn):
            with self.subTest(pack=pack['label']):
                ident,label,deck=load_pack(self.conn,pack['id'])
                self.assertEqual(ident,pack['id']);self.assertEqual(label,pack['label'])
                self.assertGreaterEqual(len(deck),40)
                self.assertLessEqual(len(deck),120)
                self.assertEqual(len({q['key'] for q in deck}),len(deck))
                self.assertTrue(all(q['section']==label for q in deck) if not ident.endswith(':ALL') else True)

    def test_solo_and_pvp_freeze_section_and_hide_answers(self):
        token='test-'+uuid4().hex;pid=uuid4()
        self.conn.execute('INSERT INTO pvp_players(player_id,token_hash,name) VALUES(%s,%s,%s)',
            (pid,hashlib.sha256(token.encode()).hexdigest(),'Rollback test'))
        self.client.cookies.set(routes.COOKIE,token,path='/api/penalties')
        pack=f"bank:{self.release['release_id']}:MUN"
        for mode in ['solo','pvp']:
            response=self.client.post('/api/penalties/rooms',json={'mode':mode,'pack':pack})
            if mode=='solo':
                self.assertEqual(response.status_code,410);continue
            self.assertEqual(response.status_code,201,response.text)
            code=response.json()['code']
            row=self.conn.execute('SELECT * FROM pvp_matches WHERE room_code=%s',(code,)).fetchone()
            state=row['state'];self.assertEqual(len(state['deck']),50)
            self.assertEqual({q['section'] for q in state['deck']},{'Manchester United'})
            self.assertEqual(row['pack'],pack)
            now=routes.now_ms(self.conn)
            if mode=='pvp':game.join(state,'other','Other',now);game.ready(state,'other',now)
            game.ready(state,str(pid),now);game.tick(state,now+3001)
            view=game.view(state,str(pid),now+3001)
            self.assertEqual(set(view['question']),{'text','options'})
            self.assertNotIn('deck',view)
            if mode=='pvp':game.submit(state,'other',1,state['deck'][0]['correct'],str(uuid4()),now+3600)
            game.submit(state,str(pid),1,state['deck'][0]['correct'],str(uuid4()),now+4000)
            solved=game.view(state,str(pid),now+4000)
            self.assertIn('authority',solved['question'])
            self.assertIn('correct',solved['question'])

    def test_rematch_keeps_same_release_and_team(self):
        token='test-'+uuid4().hex;pid=uuid4()
        self.conn.execute('INSERT INTO pvp_players(player_id,token_hash,name) VALUES(%s,%s,%s)',
            (pid,hashlib.sha256(token.encode()).hexdigest(),'Rollback test'))
        self.client.cookies.set(routes.COOKIE,token,path='/api/penalties')
        pack=f"bank:{self.release['release_id']}:MUN"
        created=self.client.post('/api/penalties/rooms',json={'mode':'pvp','pack':pack}).json()
        self.client.post(f"/api/penalties/rooms/{created['code']}/leave")
        response=self.client.post(f"/api/penalties/rooms/{created['code']}/rematch")
        self.assertEqual(response.status_code,200,response.text)
        row=self.conn.execute('SELECT * FROM pvp_matches WHERE room_code=%s',(response.json()['code'],)).fetchone()
        self.assertEqual(row['pack'],pack)
        self.assertEqual({q['section'] for q in row['state']['deck']},{'Manchester United'})

    def test_release_idempotent_and_frozen(self):
        result=publish(self.conn,self.release['validation_run_id'])
        self.assertTrue(result['reused']);self.assertEqual(result['release_id'],self.release['release_id'])
        with self.assertRaises(Exception),self.conn.transaction():
            self.conn.execute("UPDATE penalty_bank_questions SET question=jsonb_set(question,'{correct}','\"0\"')")
        with self.assertRaises(Exception),self.conn.transaction():
            self.conn.execute('DELETE FROM penalty_bank_releases')

    def test_unknown_pack_does_not_fall_back_to_another_library(self):
        from fastapi import HTTPException
        for ident in ['invalid',f'bank:{uuid4()}:MUN',f"bank:{self.release['release_id']}:BAD"]:
            with self.assertRaises(HTTPException):load_pack(self.conn,ident)
