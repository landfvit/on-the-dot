from collections import Counter
from copy import deepcopy
import os
import unittest
from uuid import uuid4

from psycopg.types.json import Jsonb
from api.database import get_connection
from api.solo_routes import active_releases
from api.solo_topics import SOURCE_TOPIC
from src.publish_penalty_bank import publish,RECOGNITION_CHOICE_VERSION


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Rollback-only recognition release checks')
class RecognitionDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn=get_connection();self.addCleanup(self.conn.close);self.addCleanup(self.conn.rollback)
        self.release=self.conn.execute("SELECT * FROM penalty_bank_releases WHERE choice_version=%s ORDER BY created_at DESC LIMIT 1",(RECOGNITION_CHOICE_VERSION,)).fetchone()
        self.assertIsNotNone(self.release)

    def test_new_release_retains_source_choices_difficulty_and_audit(self):
        rows=self.conn.execute('''SELECT p.*,q.content,c.result,d.difficulty,d.approved FROM penalty_bank_questions p
            JOIN trivia_bank_questions q USING(question_id) JOIN trivia_bank_checks c USING(question_id)
            JOIN game_current_difficulty d USING(release_id,question_id)
            WHERE p.release_id=%s AND c.run_id=%s''',(self.release['release_id'],self.release['validation_run_id'])).fetchall()
        self.assertEqual(len(rows),1980)
        self.assertEqual(Counter(r['question']['authority'] for r in rows),{'database_matched':700,'user_attested':1280})
        self.assertEqual(Counter(r['difficulty'] for r in rows),{'easy':780,'medium':1200})
        for r in rows:
            with self.subTest(question=r['content']['id']):
                q=r['question'];self.assertTrue(r['approved']);self.assertIn(q['topic'],SOURCE_TOPIC)
                self.assertEqual(r['section_code'],r['content']['id'].split('-')[1])
                self.assertEqual(q['text'],r['content']['question'])
                self.assertEqual(next(o['text'] for o in q['options'] if o['id']==q['correct']),r['content']['answer'])
                self.assertEqual(r['difficulty'],r['content']['difficulty'])
                self.assertNotIn('publication_exclusion',r['result'])
                self.assertNotIn(r['result']['status'],['ambiguous','conflict'])

    def test_pool_is_cumulative_and_publish_is_idempotent(self):
        releases=active_releases(self.conn)
        self.assertGreaterEqual(len(releases),2)
        n=self.conn.execute('''SELECT count(*) n FROM penalty_bank_questions p
            JOIN game_current_difficulty d USING(release_id,question_id)
            WHERE release_id=ANY(%s) AND d.approved''',(releases,)).fetchone()['n']
        self.assertEqual(n,3930)
        result=publish(self.conn,self.release['validation_run_id'],recognition=True)
        self.assertTrue(result['reused']);self.assertEqual(result['release_id'],self.release['release_id'])

    def test_database_accepts_two_choices_but_rejects_forged_answer_and_ids(self):
        source=self.conn.execute('''SELECT * FROM penalty_bank_questions WHERE release_id=%s
            AND jsonb_array_length(question->'options')=2 LIMIT 1''',(self.release['release_id'],)).fetchone()
        for mutation in ['answer','id','one','valid']:
            with self.subTest(mutation=mutation),self.conn.transaction(force_rollback=True):
                release=uuid4();q=deepcopy(source['question'])
                if mutation=='answer':q['correct']=str(1-int(q['correct']))
                if mutation=='id':q['options'][1]['id']='0'
                if mutation=='one':q['options']=q['options'][:1]
                self.conn.execute('INSERT INTO penalty_bank_releases VALUES(%s,%s,%s,%s,TRUE,1,DEFAULT)',
                    (release,self.release['validation_run_id'],'test-'+str(release),'test'))
                def insert():
                    self.conn.execute('INSERT INTO penalty_bank_questions VALUES(%s,%s,%s,%s,%s)',
                        (release,source['question_id'],source['section_code'],source['section_name'],Jsonb(q)))
                    self.conn.execute('SET CONSTRAINTS penalty_bank_complete IMMEDIATE')
                if mutation=='valid':insert()
                else:
                    with self.assertRaises(Exception):insert()
