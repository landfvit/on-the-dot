import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from api.database import get_connection
from api import query_training
from trivia_app.main import app
from src.query_model import train
from test_query_training import corpus


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Opt-in rollback-only PostgreSQL tests')
class AnnotationDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn=get_connection();self.addCleanup(self.conn.close);self.addCleanup(self.conn.rollback)
        @contextmanager
        def shared():yield self.conn
        mock=patch('api.query_training.get_connection',shared);mock.start();self.addCleanup(mock.stop)
        self.client=TestClient(app)
        self.auth=(os.environ['TRIVIA_EDITOR_USERNAME'],os.environ['TRIVIA_EDITOR_PASSWORD'])
        self.body={'query_text':'Test club win rate '+uuid4().hex,'phrase':'win rate','label':'win_rate',
            'family_key':'test-'+uuid4().hex,'split':'train','note':''}

    def save(self,body=None):
        response=self.client.post('/api/query/training/examples',json=body or self.body,auth=self.auth)
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def test_private_endpoints_and_no_forged_review(self):
        for path in ['/examples','/inbox','/models']:
            self.assertEqual(self.client.get('/api/query/training'+path).status_code,401)
        self.assertEqual(self.client.post('/api/query/training/examples',json=self.body).status_code,401)
        self.assertEqual(self.client.post('/api/query/training/examples',json={**self.body,'reviewed_at':'today'},auth=self.auth).status_code,422)

    def test_save_review_revision_and_stale_review(self):
        first=self.save()
        path=f"/api/query/training/examples/{first['annotation_id']}/verify"
        self.assertEqual(self.client.post(path,json={'confirmed':False},auth=self.auth).status_code,422)
        self.assertEqual(self.client.post(path,json={'confirmed':True},auth=self.auth).status_code,200)
        row=self.conn.execute('SELECT * FROM trivia_query_annotations WHERE annotation_id=%s',(first['annotation_id'],)).fetchone()
        self.assertEqual(row['reviewed_by'],self.auth[0])
        second=self.save({**self.body,'example_id':first['example_id'],'base_revision':1,'note':'Corrected annotation'})
        self.assertEqual(second['revision'],2)
        self.assertEqual(self.client.post(path,json={'confirmed':True},auth=self.auth).status_code,409)
        latest=self.conn.execute('SELECT reviewed_at FROM trivia_query_annotations WHERE annotation_id=%s',(second['annotation_id'],)).fetchone()
        self.assertIsNone(latest['reviewed_at'])
        stale=self.client.post('/api/query/training/examples',json={**self.body,'example_id':first['example_id'],'base_revision':1},auth=self.auth)
        self.assertEqual(stale.status_code,409)

    def test_family_cannot_cross_splits_and_duplicates_cannot_hide(self):
        self.save()
        other={**self.body,'query_text':'Another club win rate','split':'test'}
        self.assertEqual(self.client.post('/api/query/training/examples',json=other,auth=self.auth).status_code,409)
        self.assertEqual(self.client.post('/api/query/training/examples',json=self.body,auth=self.auth).status_code,409)

    def test_database_rejects_mutating_verified_content(self):
        first=self.save()
        self.client.post(f"/api/query/training/examples/{first['annotation_id']}/verify",json={'confirmed':True},auth=self.auth)
        with self.assertRaises(Exception),self.conn.transaction():
            self.conn.execute("UPDATE trivia_query_annotations SET label='loss_rate' WHERE annotation_id=%s",(first['annotation_id'],))

    def test_model_probe_is_private_and_cannot_execute(self):
        data=train(corpus());model_id=uuid4()
        self.conn.execute('INSERT INTO trivia_query_model_runs(model_id,dataset_hash,corpus,manifest,report,artifact) VALUES (%s,%s,%s,%s,%s,%s)',
            (model_id,data['dataset_hash'],*[Jsonb(data[k]) for k in ('corpus','manifest','report','artifact')]))
        url=f'/api/query/training/models/{model_id}/probe'
        self.assertEqual(self.client.post(url,json={'phrase':'win rate'}).status_code,401)
        response=self.client.post(url,json={'phrase':'win rate'},auth=self.auth)
        self.assertEqual(response.json()['label'],'win_rate')
        self.assertFalse(response.json()['executable'])
        self.assertTrue(response.json()['seen_in_training'])
        self.assertEqual(response.json()['training_phrase_count'],6)
        listed=self.client.get('/api/query/training/models',auth=self.auth)
        self.assertEqual(listed.status_code,200)
        entry=next(m for m in listed.json()['models'] if m['model_id']==str(model_id))
        self.assertNotIn('corpus',entry)
        frozen={r['annotation_id']:r for r in data['corpus']}
        for split in ('validation','test'):
            self.assertEqual(len(entry['evaluation_examples'][split]),3)
            for example in entry['evaluation_examples'][split]:
                self.assertEqual(example['phrase'],frozen[example['annotation_id']]['phrase'])
        stored=self.conn.execute('SELECT corpus,artifact FROM trivia_query_model_runs WHERE model_id=%s',(model_id,)).fetchone()
        self.assertEqual(stored['corpus'],data['corpus'])
        self.assertEqual(stored['artifact'],data['artifact'])
