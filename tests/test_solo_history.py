from copy import deepcopy
from datetime import datetime
import random
import unittest
from unittest.mock import Mock,patch
from uuid import uuid4

from api.solo_history import week_window
from api.solo_routes import load_deck,Start


class SoloHistoryTests(unittest.TestCase):
    def test_utc_week_boundaries_including_year_and_timezone(self):
        cases=[
            ('2026-09-27T23:59:59.999+00:00','2026-09-21','2026-09-28T00:00:00+00:00'),
            ('2026-09-28T00:00:00+00:00','2026-09-28','2026-10-05T00:00:00+00:00'),
            ('2026-09-28T01:00:00+02:00','2026-09-21','2026-09-28T00:00:00+00:00'),
            ('2027-01-01T00:00:00+00:00','2026-12-28','2027-01-04T00:00:00+00:00'),
        ]
        for timestamp,expected_start,expected_reset in cases:
            with self.subTest(timestamp=timestamp):
                start,reset=week_window(datetime.fromisoformat(timestamp).timestamp()*1000)
                self.assertEqual(start.isoformat(),expected_start);self.assertEqual(reset.isoformat(),expected_reset)

    def test_100_shuffles_preserve_membership_answers_and_source_snapshots(self):
        rows=[{'release_id':uuid4(),'question_id':uuid4(),'revision_id':1,'section_name':'General','source_topic':'Managers',
               'question':{'key':str(i),'text':f'Question {i}',
                           'options':[{'id':str(j),'text':f'Answer {j}'} for j in range(4)],'correct':'2'}} for i in range(10)]
        original=deepcopy(rows);orders=set();choice_orders=set();rng=random.Random(12345)
        conn=Mock()
        conn.execute.return_value.fetchall.side_effect=lambda:deepcopy(rows)
        with patch('api.solo_routes.active_releases',return_value=[r['release_id'] for r in rows]),patch('api.solo_routes.secrets.SystemRandom',return_value=rng):
            for attempt in range(100):
                with self.subTest(attempt=attempt):
                    deck,_=load_deck(conn,uuid4(),Start(difficulty='hard',request_id=uuid4()),1790000000000)
                    self.assertEqual({q['key'] for q in deck},{str(i) for i in range(10)})
                    orders.add(tuple(q['key'] for q in deck))
                    for q in deck:
                        self.assertEqual(q['release_id'],str(next(r['release_id'] for r in rows if str(r['question_id'])==q['question_id'])))
                        choice_orders.add(tuple(o['text'] for o in q['options']))
                        self.assertEqual(next(o['text'] for o in q['options'] if o['id']==q['correct']),'Answer 2')
                        self.assertEqual([o['id'] for o in q['options']],['0','1','2','3'])
        self.assertEqual(rows,original)
        self.assertEqual(len(orders),100)
        self.assertEqual(len(choice_orders),24)
