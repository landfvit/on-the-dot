"""Isolated PostgreSQL schema, including concurrent real connections; removed after tests."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.types.json import Jsonb
from api.database import get_connection
from api import penalty_engine as game
from api import penalty_routes as routes
from api.penalty_questions import maths_pack
from trivia_app.main import app


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Isolated PostgreSQL integration tests')
class PenaltyDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.schema='test_penalty_'+uuid4().hex
        with get_connection() as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
            for name in ('pvp_players','pvp_matches','pvp_answers','pvp_penalties','pvp_rate_limits'):
                conn.execute(sql.SQL('CREATE TABLE {}.{} (LIKE public.{} INCLUDING ALL)').format(
                    sql.Identifier(self.schema),sql.Identifier(name),sql.Identifier(name)))
            conn.execute(sql.SQL('CREATE TRIGGER frozen BEFORE UPDATE ON {}.pvp_matches FOR EACH ROW EXECUTE FUNCTION public.pvp_match_guard()').format(sql.Identifier(self.schema)))
            for name in ('pvp_answers','pvp_penalties'):
                conn.execute(sql.SQL('CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON {}.{} FOR EACH ROW EXECUTE FUNCTION public.pvp_immutable()').format(sql.Identifier(self.schema),sql.Identifier(name)))
        self.addCleanup(self.drop_schema)
        @contextmanager
        def isolated():
            with get_connection() as conn:
                conn.execute(sql.SQL('SET search_path TO {},public').format(sql.Identifier(self.schema)))
                yield conn
        self.connection=isolated
        self.patch=patch('api.penalty_routes.get_connection',isolated);self.patch.start();self.addCleanup(self.patch.stop)
        self.tokens=['test-a-'+uuid4().hex,'test-b-'+uuid4().hex,'test-c-'+uuid4().hex]
        self.ids=[uuid4() for _ in self.tokens]
        with isolated() as conn:
            for ident,token in zip(self.ids,self.tokens):
                conn.execute('INSERT INTO pvp_players(player_id,token_hash,name) VALUES(%s,%s,%s)',
                    (ident,hashlib.sha256(token.encode()).hexdigest(),str(ident)[:8]))
            now=routes.now_ms(conn);self.deck=maths_pack()
            state=game.create('pvp',str(self.ids[0]),'A',self.deck,now)
            game.join(state,str(self.ids[1]),'B',now)
            for pid in self.ids[:2]:game.ready(state,str(pid),now-3000)
            state['last_tick']=now;game.tick(state,now)
            self.match_id=uuid4();self.code=uuid4().hex[:10].upper()
            conn.execute('INSERT INTO pvp_matches VALUES(%s,%s,%s,%s,%s,DEFAULT)',
                (self.match_id,self.code,self.ids[0],'maths',Jsonb(state)))

    def drop_schema(self):
        with get_connection() as conn:conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    def answer(self,option=None,request=None):
        return routes.Answer(penalty_id=1,option_id=option or self.deck[0]['correct'],request_id=request or uuid4())

    def test_two_simultaneous_answers_commit_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(routes.room_action,self.code,t,'answer',self.answer()) for t in self.tokens[:2]]
            for future in futures:future.result()
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) n FROM pvp_answers').fetchone()['n'],2)
            self.assertEqual(conn.execute('SELECT COUNT(*) n FROM pvp_penalties').fetchone()['n'],1)
            s=conn.execute('SELECT state FROM pvp_matches').fetchone()['state']
            self.assertEqual(len(s['history']),1)

    def test_duplicate_request_and_second_tab_do_not_double_submit(self):
        answer=self.answer()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(routes.room_action,self.code,self.tokens[0],'answer',answer) for _ in range(2)]
            for future in futures:future.result()
        with self.connection() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) n FROM pvp_answers').fetchone()['n'],1)
        with self.assertRaises(HTTPException):routes.room_action(self.code,self.tokens[0],'answer',self.answer())

    def test_timeout_race_is_atomic_and_late_answer_does_not_rollback_resolution(self):
        with self.connection() as conn:
            s=conn.execute('SELECT state FROM pvp_matches').fetchone()['state'];s['round']['deadline']=routes.now_ms(conn)
            conn.execute('UPDATE pvp_matches SET state=%s',(Jsonb(s),))
        with ThreadPoolExecutor(max_workers=2) as pool:
            answer=pool.submit(routes.room_action,self.code,self.tokens[0],'answer',self.answer())
            timeout=pool.submit(routes.room_action,self.code,self.tokens[1])
            with self.assertRaises(HTTPException):answer.result()
            timeout.result()
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) n FROM pvp_penalties').fetchone()['n'],1)
            self.assertEqual(conn.execute('SELECT COUNT(*) n FROM pvp_answers').fetchone()['n'],0)

    def test_outsider_and_invalid_token_cannot_read_or_answer(self):
        for token in [self.tokens[2],'invalid']:
            with self.assertRaises(HTTPException):routes.room_action(self.code,token)
            with self.assertRaises(HTTPException):routes.room_action(self.code,token,'answer',self.answer())

    def test_api_payloads_csrf_and_no_solution_leak(self):
        with TestClient(app) as client:
            client.cookies.set(routes.COOKIE,self.tokens[0],path='/api/penalties')
            response=client.get('/api/penalties/rooms/'+self.code)
            self.assertEqual(response.status_code,200);self.assertNotIn('correct',response.json()['question'])
            payload={'penalty_id':1,'option_id':self.deck[0]['correct'],'request_id':str(uuid4())}
            url=f'/api/penalties/rooms/{self.code}/answers'
            self.assertEqual(client.post(url,json=payload,headers={'Origin':'https://evil.example'}).status_code,403)
            self.assertEqual(client.post(url,json={**payload,'is_correct':True}).status_code,422)
            response=client.post(url,json=payload)
            self.assertEqual(response.status_code,200);self.assertNotIn('correct',response.json()['question'])
            self.assertNotIn('answers',response.json()['round'])

    def test_websocket_requires_origin_and_membership(self):
        from starlette.websockets import WebSocketDisconnect
        with TestClient(app) as client:
            client.cookies.set(routes.COOKIE,self.tokens[0],path='/api/penalties')
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect(f'/api/penalties/rooms/{self.code}/live',headers={'origin':'https://evil.example'}):pass
            with client.websocket_connect(f'/api/penalties/rooms/{self.code}/live',headers={'origin':'http://testserver'}) as ws:
                message=ws.receive_json();self.assertEqual(message['phase'],'ANSWERING')
                self.assertNotIn('correct',message['question'])

    def test_restart_keeps_frozen_question_and_answer(self):
        routes.room_action(self.code,self.tokens[0],'answer',self.answer())
        view=routes.room_action(self.code,self.tokens[0])
        self.assertEqual(view['round']['own_option'],self.deck[0]['correct'])
        self.assertEqual(view['question']['text'],self.deck[0]['text'])

    def test_background_sweep_resolves_without_any_client(self):
        with self.connection() as conn:
            s=conn.execute('SELECT state FROM pvp_matches').fetchone()['state'];s['round']['deadline']=routes.now_ms(conn)
            conn.execute('UPDATE pvp_matches SET state=%s',(Jsonb(s),))
        routes.sweep_rooms();routes.sweep_rooms()
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) n FROM pvp_penalties').fetchone()['n'],1)
            self.assertEqual(conn.execute('SELECT state FROM pvp_matches').fetchone()['state']['round']['outcome'],'miss')

    def test_frozen_pack_and_answers_cannot_be_rewritten(self):
        routes.room_action(self.code,self.tokens[0],'answer',self.answer())
        for query in ["UPDATE pvp_matches SET state=jsonb_set(state,'{deck}','[]')",
                "UPDATE pvp_matches SET state=jsonb_set(state,'{rules,target}','1')",
                "UPDATE pvp_answers SET answer='{}'"]:
            with self.assertRaises(Exception),self.connection() as conn:conn.execute(query)

    def test_pvp_cannot_skip_result_and_shared_rematch_is_idempotent(self):
        with self.assertRaises(HTTPException):routes.room_action(self.code,self.tokens[0],'next')
        routes.room_action(self.code,self.tokens[0],'leave')
        codes=[]
        for token in self.tokens[:2]:
            with TestClient(app) as client:
                client.cookies.set(routes.COOKIE,token,path='/api/penalties')
                response=client.post(f'/api/penalties/rooms/{self.code}/rematch')
                self.assertEqual(response.status_code,200);codes.append(response.json()['code'])
        self.assertEqual(codes[0],codes[1])
        view=routes.room_action(codes[0],self.tokens[1])
        self.assertEqual(len(view['players']),2);self.assertFalse(any(p['ready'] for p in view['players']))
