"""Exact quota/uniqueness checks and 100 deliberately corrupted audit cases."""
from copy import deepcopy
from collections import Counter
import json
import os
from pathlib import Path
import random
import unittest

from api.database import get_connection
from src.check_curated_questions import Checker

PATH=Path(os.getenv('CURATED_BANK_FILE',str(Path(__file__).parents[1]/'data/trivia/curated-pl-3000-v1/questions.json')))


@unittest.skipUnless(PATH.exists(),'Generate the local curated bundle first')
class CuratedBundleTests(unittest.TestCase):
    def test_quotas_and_duplicates(self):
        rows=json.loads(PATH.read_text())
        self.assertEqual(Counter(q['difficulty'] for q in rows),Counter(easy=1000,medium=1000,hard=1000))
        for field in ('id','question','fact_key'):self.assertEqual(len({q[field] for q in rows}),3000)
        self.assertGreaterEqual(len({q['family'] for q in rows}),9)
        self.assertLessEqual(max(Counter((q['difficulty'],q['family']) for q in rows).values()),300)
        for q in rows:
            self.assertEqual(q['options'][q['correct']],q['answer'])
            self.assertEqual(len(q['options']),4)
            self.assertNotRegex(q['question'].lower(),r'fewest losses|most goals conceded|between january and february')

    @unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Local read-only audit')
    def test_every_answer_and_100_mutations(self):
        rows=json.loads(PATH.read_text())
        with get_connection() as conn:
            self.assertIn(conn.info.host,('localhost','127.0.0.1','::1',''))
            conn.execute('SET TRANSACTION READ ONLY');checker=Checker(conn)
            for q in rows:
                with self.subTest(question=q['id']):self.assertEqual(checker.check(q)['status'],'matched')
            for i,q in enumerate(random.Random(812).sample(rows,100)):
                changed=deepcopy(q)
                if i%2:changed['answer']='A deliberately wrong answer'
                else:changed['question']='Who won the Champions League in 1900?'
                with self.subTest(mutation=i):self.assertEqual(checker.check(changed)['status'],'conflict')
