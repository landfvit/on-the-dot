"""Format diversity, continuation boundaries and the actual active bank."""
from collections import Counter
from copy import deepcopy
import os
import random
import unittest
from uuid import uuid4

from api.question_mix import group,sample,enrich_deck
from api.solo_topics import balanced_sample


def rows_for(families,count=30):
    return [{'question_id':f'{family}-{i}','family':family,'source_topic':'Player milestones',
             'mix_subjects':[f'player:{family}-{i}']} for family in families for i in range(count)]


class QuestionMixTests(unittest.TestCase):
    def test_1000_easy_samples_have_variety_and_bounded_nationalities_and_scores(self):
        rows=rows_for(['nationality','big_win','hat_trick','transfer','teammates','club_scorer','scoring_club'])
        original=deepcopy(rows);orders=set()
        for seed in range(1000):
            deck=sample(rows,rng=random.Random(seed));counts=Counter(group(q) for q in deck)
            self.assertEqual(len({q['question_id'] for q in deck}),10)
            self.assertEqual(counts['nationality'],1)
            self.assertLessEqual(counts['match_memory'],2)
            self.assertGreaterEqual(len({q['family'] for q in deck}),6)
            self.assertEqual(len({group(q) for q in deck[:5]}),5)
            self.assertTrue(all(group(a)!=group(b) for a,b in zip(deck,deck[1:])))
            orders.add(tuple(q['question_id'] for q in deck))
        self.assertGreater(len(orders),950);self.assertEqual(rows,original)

    def test_sudden_death_respects_previous_window(self):
        rows=rows_for(['nationality','big_win','hat_trick','transfer','teammates','club_scorer','scoring_club'],100)
        rng=random.Random(1);history=[]
        for size in [10]+[2]*45:
            selected=sample(rows,size=size,rng=rng,recent=history)
            ids={q['question_id'] for q in selected};rows=[q for q in rows if q['question_id'] not in ids]
            history.extend(selected)
        for start in range(len(history)-9):
            counts=Counter(group(q) for q in history[start:start+10])
            self.assertLessEqual(counts['nationality'],1)
            self.assertLessEqual(counts['match_memory'],2)
        self.assertEqual(len({q['question_id'] for q in history}),100)

    def test_repeated_subjects_are_avoided_when_an_alternative_exists(self):
        rows=rows_for(['transfer'],20)
        recent=[{'family':'teammates','mix_subjects':['player:transfer-0','player:transfer-1']}]
        chosen=sample(rows,size=10,recent=recent,rng=random.Random(12))
        self.assertNotIn(chosen[0]['question_id'],['transfer-0','transfer-1'])

    def test_shortage_never_repeats_or_expands_scope(self):
        rows=rows_for(['nationality'],4)
        self.assertEqual(len(sample(rows,size=10)),4)
        rows+= [{'question_id':'other','family':'stadium','source_topic':'Stadiums'}]
        chosen=balanced_sample(rows,topic='stadiums')
        self.assertEqual([r['question_id'] for r in chosen],['other'])
        self.assertEqual(sample([],size=10),[])


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Local read-only bank checks')
class ActualQuestionMixTests(unittest.TestCase):
    def setUp(self):
        from api.database import get_connection
        self.conn=get_connection();self.addCleanup(self.conn.close);self.addCleanup(self.conn.rollback)
        self.assertIn(self.conn.info.host,('localhost','127.0.0.1','::1',''))
        self.conn.execute('SET TRANSACTION READ ONLY')

    def test_300_actual_bank_samples(self):
        from api.challenge_routes import candidates
        rows=candidates(self.conn)
        for difficulty in ('easy','medium','hard'):
            eligible=[r for r in rows if r['difficulty']==difficulty]
            self.assertGreaterEqual(len(eligible),1000)
            for seed in range(100):
                with self.subTest(difficulty=difficulty,seed=seed):
                    deck=balanced_sample(eligible,rng=random.Random(seed))
                    counts=Counter(group(q) for q in deck)
                    self.assertEqual(len(deck),10)
                    self.assertLessEqual(counts['nationality'],1)
                    self.assertLessEqual(counts['match_memory'],2)
                    self.assertGreaterEqual(len({q['family'] for q in deck}),6 if difficulty=='easy' else 4)

    def test_solo_loader_preserves_the_mixed_order(self):
        from api.solo_routes import load_deck,Start
        from api import solo_engine
        for difficulty in ('easy','medium','hard'):
            deck,category=load_deck(self.conn,uuid4(),Start(request_id=uuid4(),difficulty=difficulty),0)
            self.assertEqual(len(deck),10)
            self.assertLessEqual(sum(group(q)=='nationality' for q in deck),1)
            self.assertLessEqual(sum(group(q)=='match_memory' for q in deck),2)
            state=solo_engine.create(deck,difficulty,category,100)
            solo_engine.advance(state,0,200)
            self.assertEqual(set(solo_engine.view(state,201)['question']),{'text','options'})
            extra,_=load_deck(self.conn,uuid4(),Start(request_id=uuid4(),difficulty=difficulty),0,
                             size=2,exclude=[q['question_id'] for q in deck],recent=deck[-9:])
            self.assertTrue({q['question_id'] for q in deck}.isdisjoint(q['question_id'] for q in extra))

    def test_cached_daily_metadata_does_not_change_question_content(self):
        from api.challenge_routes import candidates,snapshots
        deck=snapshots(self.conn,candidates(self.conn)[:10])
        old=[{k:v for k,v in q.items() if k not in ('family','source_topic','mix_subjects')} for q in deck]
        saved=deepcopy(old);enriched=enrich_deck(self.conn,old)
        self.assertEqual(old,saved)
        for before,after in zip(old,enriched):
            for key,value in before.items():self.assertEqual(after[key],value)
            self.assertTrue(after['family'])
