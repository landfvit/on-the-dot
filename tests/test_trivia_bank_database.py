import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from api.database import get_connection
from api.trivia_bank_engine import load_evaluator
from trivia_app.main import app


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1', 'Opt-in rollback-only PostgreSQL tests')
class BankDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn=get_connection()
        self.addCleanup(self.conn.close); self.addCleanup(self.conn.rollback)
        @contextmanager
        def shared(): yield self.conn
        mock=patch('api.trivia_bank_routes.get_connection',shared); mock.start(); self.addCleanup(mock.stop)
        self.client=TestClient(app)
        self.auth=(os.environ['TRIVIA_EDITOR_USERNAME'],os.environ['TRIVIA_EDITOR_PASSWORD'])

    def test_private_routes_and_cross_origin(self):
        for path in ['/summary','/questions','/authoring/drafts']:
            self.assertEqual(self.client.get('/api/trivia/bank'+path).status_code,401)
        body={'question':'How many away Premier League wins did Arsenal record in 2024/25?'}
        self.assertEqual(self.client.post('/api/trivia/bank/authoring/check',json=body).status_code,401)
        self.assertEqual(self.client.post('/api/trivia/bank/authoring/check',json=body,auth=self.auth,headers={'Origin':'https://foreign.example'}).status_code,403)

    def test_all_questions_present_and_filters(self):
        summary=self.client.get('/api/trivia/bank/summary',auth=self.auth).json()
        expected=self.conn.execute('SELECT question_count FROM trivia_bank_batches WHERE batch_id=%s',(summary['batch_id'],)).fetchone()['question_count']
        self.assertEqual(summary['question_count'],expected)
        self.assertEqual(sum(summary['summary'].values()),expected)
        self.assertEqual(len(summary['sections']),35)
        self.assertGreaterEqual(summary['model']['training_rows'],1950)
        result=self.client.get('/api/trivia/bank/questions',params={'section':'Manchester United'},auth=self.auth).json()
        self.assertEqual(result['total'],50)
        self.assertEqual(len(result['questions']),25)
        self.assertTrue(all(q['content']['section']=='Manchester United' for q in result['questions']))
        flagged=self.client.get('/api/trivia/bank/questions?status=flagged&limit=100',auth=self.auth).json()
        self.assertTrue(all(q['status']!='matched' for q in flagged['questions']))
        self.assertEqual(self.client.get('/api/trivia/bank/questions?search=%25',auth=self.auth).status_code,200)
        self.assertEqual(self.client.get('/api/trivia/bank/questions?status=not-real',auth=self.auth).status_code,422)
        one=self.client.get('/api/trivia/bank/questions?status=matched&limit=1',auth=self.auth).json()
        evidence=self.client.get('/api/trivia/bank/questions/'+one['questions'][0]['question_id']+'/evidence',auth=self.auth).json()
        self.assertGreater(len(evidence['evidence_fixture_ids']),0)

    def test_authoring_computes_answer_not_model_guess(self):
        q='How many away Premier League wins did Arsenal record in 2024/25?'
        response=self.client.post('/api/trivia/bank/authoring/check',json={'question':q},auth=self.auth)
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertEqual(result['scope'],'suggestion_only')
        self.assertEqual(result['calculation']['status'],'calculated')
        self.assertTrue(result['neighbors'])
        self.assertIsInstance(result['calculation']['answer'],str)

    def test_fabricated_client_answer_forbidden(self):
        response=self.client.post('/api/trivia/bank/authoring/drafts',json={'question':'A very long question?', 'answer':'Invented'},auth=self.auth)
        self.assertEqual(response.status_code,422)

    def test_incomplete_question_cannot_be_saved(self):
        response=self.client.post('/api/trivia/bank/authoring/drafts',json={'question':'How many away Premier League wins did Arsenal record in 2090/91?'},auth=self.auth)
        self.assertEqual(response.status_code,422,response.text)

    def test_save_draft_and_immutable_content(self):
        response=self.client.post('/api/trivia/bank/authoring/drafts',json={'question':'How many away Premier League wins did Arsenal record in 2024/25?'},auth=self.auth)
        self.assertEqual(response.status_code,201,response.text)
        ident=response.json()['draft_id']
        stored=self.conn.execute('SELECT * FROM trivia_bank_authored_drafts WHERE draft_id=%s',(ident,)).fetchone()
        self.assertEqual(stored['calculation']['status'],'calculated')
        self.assertIn('validator_sha256',stored['inputs'])
        with self.assertRaises(Exception),self.conn.transaction():
            self.conn.execute("UPDATE trivia_bank_authored_drafts SET question_text='Changed content' WHERE draft_id=%s",(ident,))

    def test_import_and_audit_immutable_and_consistent(self):
        batch=self.conn.execute('SELECT * FROM trivia_bank_batches ORDER BY created_at DESC LIMIT 1').fetchone()
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM trivia_bank_batches WHERE source_sha256=%s',(batch['source_sha256'],)).fetchone()['n'],1)
        with self.assertRaises(Exception),self.conn.transaction():
            self.conn.execute("UPDATE trivia_bank_questions SET content=jsonb_set(content,'{answer}','\"Wrong\"') WHERE batch_id=%s",(batch['batch_id'],))
        with self.assertRaises(Exception),self.conn.transaction():
            self.conn.execute('DELETE FROM trivia_bank_checks')
        with self.assertRaises(Exception),self.conn.transaction():
            self.conn.execute('INSERT INTO trivia_bank_batches VALUES (%s,%s,%s,%s,%s,%s,DEFAULT)',
                (uuid4(),batch['source_sha256'],'Duplicate','content','user_attested',1))

    def test_model_split_and_no_answer_training(self):
        row=self.conn.execute('SELECT corpus,report FROM trivia_bank_models ORDER BY created_at DESC LIMIT 1').fetchone()
        memberships={}
        for item in row['corpus']:
            self.assertNotIn('answer',item)
            memberships.setdefault(item['family'],set()).add(item['split'])
        self.assertTrue(all(len(s)==1 for s in memberships.values()))
        self.assertFalse(row['report']['answer_prediction'])
        self.assertEqual(row['report']['artifact_training_rows'],len(row['corpus']))
        self.assertGreaterEqual(len(row['corpus']),1950)

    def test_complete_bank_recalculation_and_deliberate_wrong_answer(self):
        run=self.conn.execute('SELECT * FROM trivia_bank_validation_runs ORDER BY created_at DESC LIMIT 1').fetchone()
        engine,_=load_evaluator(self.conn,run['dataset_id'])
        rows=self.conn.execute('''SELECT q.content,c.result FROM trivia_bank_questions q
            JOIN trivia_bank_checks c USING(question_id) WHERE c.run_id=%s''',(run['run_id'],)).fetchall()
        expected=self.conn.execute('SELECT question_count FROM trivia_bank_batches WHERE batch_id=%s',(run['batch_id'],)).fetchone()['question_count']
        self.assertEqual(len(rows),expected)
        for row in rows:
            with self.subTest(question=row['content']['id']):
                self.assertEqual(engine.check(row['content'])['status'],row['result']['status'])
        item=next(r['content'] for r in rows if r['result']['status']=='matched')
        altered={**item,'answer':'9999999'}
        self.assertEqual(engine.check(altered)['status'],'conflict')

    def test_database_rejects_forged_draft(self):
        row=self.conn.execute('''SELECT m.model_id,r.dataset_id FROM trivia_bank_models m
            JOIN trivia_bank_validation_runs r ON r.run_id=m.validation_run_id LIMIT 1''').fetchone()
        with self.assertRaises(Exception),self.conn.transaction():
            self.conn.execute('INSERT INTO trivia_bank_authored_drafts VALUES (%s,%s,%s,%s,%s,%s,%s,DEFAULT)',
                (uuid4(),row['model_id'],row['dataset_id'],'An invalid question?',None,Jsonb({'status':'incomplete','answer':'99'}),Jsonb({})))

    def test_database_rejects_incomplete_audit_and_late_questions(self):
        run=self.conn.execute('SELECT * FROM trivia_bank_validation_runs ORDER BY created_at DESC LIMIT 1').fetchone()
        with self.assertRaises(Exception),self.conn.transaction():
            self.conn.execute('INSERT INTO trivia_bank_questions VALUES (%s,%s,%s,%s)',
                (uuid4(),run['batch_id'],'LATE-001',Jsonb({'id':'LATE-001','question':'Late question?','answer':'One',
                    'topic':'Test','section':'Test','sources':[],'check':'Test'})))
        with self.assertRaises(Exception),self.conn.transaction():
            self.conn.execute('INSERT INTO trivia_bank_validation_runs VALUES (%s,%s,%s,%s,%s,%s,DEFAULT)',
                (uuid4(),run['batch_id'],run['dataset_id'],'test',Jsonb({}),Jsonb({'matched':1950})))
            self.conn.execute('SET CONSTRAINTS bank_complete_audit IMMEDIATE')
