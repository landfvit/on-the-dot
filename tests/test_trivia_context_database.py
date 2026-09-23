"""Synthetic context snapshots and questions; every write is rolled back."""
from contextlib import contextmanager
import os
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from api import trivia
from api.database import get_connection
from api.trivia_models import EvaluationRequest,SaveQuestion,GradeAnswer


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Rollback-only PostgreSQL integration tests')
class ContextDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn=get_connection();self.addCleanup(self.conn.close);self.addCleanup(self.conn.rollback)
        @contextmanager
        def shared():yield self.conn
        mocked=patch('api.trivia.get_connection',shared);mocked.start();self.addCleanup(mocked.stop)
        self.data=trivia.dataset(self.conn)
        self.base={'league_id':39,'team_id':33,'period':{'mode':'seasons','seasons':[2024]},'minimum_sample':1}

    def freeze(self,kits=None,weather=None):
        ident=uuid4()
        self.conn.execute('INSERT INTO trivia_context_snapshots(context_id,dataset_id,source_hash,method,summary,payload) VALUES (%s,%s,%s,%s,%s,%s)',
            (ident,self.data['dataset_id'],str(ident),'synthetic-test',Jsonb({}),Jsonb({'kits':kits or {},'weather':weather or {}})))
        return ident

    def test_kit_save_publish_grade_and_frozen_source(self):
        record={'status':'available','colour':'white','source_url':'https://example.com/test-kit','palette':[{'colour':'white','share':.8}]}
        context=self.freeze({'2024:33:third':record})
        spec={**self.base,'template':'kit_colour','kit_type':'third','context_id':context}
        result=trivia.preview(EvaluationRequest(specification=spec))
        self.assertEqual(result['answer']['label'],'White');self.assertTrue(result['coverage']['publishable'])
        saved=trivia.save(SaveQuestion(specification=spec,dataset_id=self.data['dataset_id']))
        trivia.publish(saved['version_id'])
        for answer in ['white','bila','b\u00edl\u00e1']:
            self.assertTrue(trivia.grade(saved['version_id'],GradeAnswer(text=answer))['correct'])
        self.assertFalse(trivia.grade(saved['version_id'],GradeAnswer(text='red'))['correct'])
        stored=trivia.question(saved['version_id'])
        self.assertEqual(stored['analysis']['context_evidence'],record)
        with self.assertRaises(Exception),self.conn.transaction():
            self.conn.execute('UPDATE trivia_context_snapshots SET payload=%s WHERE context_id=%s',(Jsonb({}),context))
        missing=trivia.preview(EvaluationRequest(specification={**spec,'kit_type':'away'}))
        self.assertFalse(missing['coverage']['publishable']);self.assertIsNone(missing['answer']['label'])
        with self.assertRaises(HTTPException):
            trivia.preview(EvaluationRequest(specification={**spec,'context_id':uuid4()}))

    def test_weather_evidence_and_missing_coverage_block_publication(self):
        facts=self.conn.execute('SELECT fixture_id,match_date FROM trivia_match_team_facts WHERE dataset_id=%s AND team_id=33 AND season=2024',
            (self.data['dataset_id'],)).fetchall()
        weather={str(f['fixture_id']):{'kickoff_at':f['match_date'].isoformat(),'sampled_at':f['match_date'].isoformat(),
            'model':'ERA5','temperature_c':10,'precipitation_mm':1,'source_url':'https://example.com/synthetic-weather',
            'raw_payload':{'hourly_units':{'temperature_2m':'\u00b0C','precipitation':'mm'}}} for f in facts}
        spec={**self.base,'template':'win_rate','context_id':self.freeze(weather=weather),
            'weather':{'metric':'temperature_c','operator':'gte','value':10}}
        result=trivia.preview(EvaluationRequest(specification=spec))
        self.assertEqual(result['answer']['denominator'],38);self.assertTrue(result['coverage']['publishable'])
        self.assertTrue(all(r['weather']['temperature_c']==10 for r in result['evidence']))
        saved=trivia.save(SaveQuestion(specification=spec));trivia.publish(saved['version_id'])
        weather.pop(next(iter(weather)))
        spec['context_id']=self.freeze(weather=weather)
        result=trivia.preview(EvaluationRequest(specification=spec))
        self.assertEqual(result['coverage']['excluded_matches'],1)
        saved=trivia.save(SaveQuestion(specification=spec))
        with self.assertRaises(HTTPException):trivia.publish(saved['version_id'])

    def test_v2_combination_can_publish_without_changing_v1_snapshots(self):
        record={'status':'available','colour':None,'colours':['black','orange'],'method':'shirt-torso-colours-v2',
            'source_url':'https://example.com/test-kit','palette':[{'colour':'black','share':.5},{'colour':'orange','share':.5}]}
        context=self.freeze({'2024:33:third':record})
        spec={**self.base,'template':'kit_colour','kit_type':'third','context_id':context}
        result=trivia.preview(EvaluationRequest(specification=spec))
        self.assertEqual(result['answer']['label'],'Black and orange')
        self.assertEqual(len(result['answer']['swatches']),2)
        saved=trivia.save(SaveQuestion(specification=spec));trivia.publish(saved['version_id'])
        self.assertTrue(trivia.grade(saved['version_id'],GradeAnswer(text='orange and black'))['correct'])
        self.assertFalse(trivia.grade(saved['version_id'],GradeAnswer(text='orange'))['correct'])
