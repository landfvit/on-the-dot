from collections import Counter
import random
import unittest
from typing import get_args

from pydantic import ValidationError
from uuid import uuid4
from api.solo_routes import Start
from api.solo_topics import TOPICS,SOURCE_TOPIC,TopicCode,balanced_sample


class SoloTopicsTests(unittest.TestCase):
    def test_taxonomy_covers_each_source_topic_exactly_once(self):
        flattened=[s for _,sources in TOPICS.values() for s in sources]
        self.assertEqual(len(flattened),len(set(flattened)))
        self.assertEqual(set(get_args(TopicCode)),{'ALL',*TOPICS})
        self.assertEqual(SOURCE_TOPIC['Discipline'],'discipline')
        with self.assertRaises(ValidationError):Start(topic='invented',request_id=uuid4())

    def test_100_mixed_decks_do_not_follow_dominant_pool_size(self):
        rows=[{'question_id':i,'source_topic':'Managers'} for i in range(1000)]
        rows += [{'question_id':1000+i,'source_topic':'Stadiums'} for i in range(20)]
        rows += [{'question_id':2000,'source_topic':'Awards'}]
        for seed in range(100):
            with self.subTest(seed=seed):
                chosen=balanced_sample(rows,rng=random.Random(seed))
                counts=Counter(SOURCE_TOPIC[r['source_topic']] for r in chosen)
                self.assertEqual(len({r['question_id'] for r in chosen}),10)
                self.assertEqual(counts['players'],1)
                self.assertIn(counts['managers'],[4,5]);self.assertIn(counts['stadiums'],[4,5])

    def test_specific_topic_never_fills_shortage_from_other_topics(self):
        rows=[{'question_id':i,'source_topic':'Managers'} for i in range(20)]
        rows += [{'question_id':100,'source_topic':'Stadiums'}]
        chosen=balanced_sample(rows,'stadiums',rng=random.Random(42))
        self.assertEqual(chosen,[{'question_id':100,'source_topic':'Stadiums'}])

    def test_subtopics_are_balanced_and_unknown_content_is_excluded(self):
        rows=[{'question_id':i,'source_topic':'Kit manufacturers'} for i in range(20)]
        rows += [{'question_id':100+i,'source_topic':'Kits and design'} for i in range(20)]
        rows += [{'question_id':200,'source_topic':'Unknown'}]
        chosen=balanced_sample(rows,'kits',rng=random.Random(1))
        self.assertEqual(Counter(r['source_topic'] for r in chosen),{'Kit manufacturers':5,'Kits and design':5})
        self.assertEqual(len(rows),41)
