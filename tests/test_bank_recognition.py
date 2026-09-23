from collections import Counter
from pathlib import Path
import unittest
from unittest.mock import patch

from api.bank_choices import options,pools_for,kind,closed_answers
from api.bank_curation import exclusion,game_topic,section_code
from api.trivia_bank_engine import BankEvaluator,CLUBS,parse_bank,canonical
from api.solo_topics import SOURCE_TOPIC
from test_trivia_bank import season_facts,DOC


class RecognitionTests(unittest.TestCase):
    def setUp(self):
        self.facts=season_facts()
        self.engine=BankEvaluator(self.facts)

    def test_prefixed_parser_requires_difficulty_and_accepts_plural_sources(self):
        text=DOC.replace('GEN-001','EM-GEN-001').replace('**Question:**','**Difficulty:** Easy\n**Question:**').replace('**Source:**','**Sources:**')
        item=parse_bank(text)[0]
        self.assertEqual(item['difficulty'],'easy');self.assertEqual(section_code(item['id']),'GEN')
        with self.assertRaises(ValueError):parse_bank(text.replace('**Difficulty:** Easy\n',''))

    def test_100_home_first_score_and_both_team_goal_checks(self):
        for row in [r for r in self.facts if r['is_home']][:100]:
            home,away=CLUBS[row['team_id']],CLUBS[row['opponent_id']]
            expected=f"{row['goals_for']}-{row['goals_against']}"
            with self.subTest(home=home,away=away):
                q=f"With the home team's goals first, which was the score when {home} hosted {away} in 2024/25: {expected} or 9-8?"
                result=self.engine.check({'question':q,'answer':expected})
                self.assertEqual(result['status'],'matched');self.assertEqual(result['evidence_fixture_ids'],[row['fixture_id']])
                self.assertEqual(self.engine.check({'question':q,'answer':'999-0'})['status'],'conflict')
                q=f'Did both teams score when {home} hosted {away} in the 2024/25 Premier League?'
                answer='Yes' if min(row['goals_for'],row['goals_against'])>0 else 'No'
                self.assertEqual(self.engine.check({'question':q,'answer':answer})['status'],'matched')

    def test_comparison_ties_and_points_deductions(self):
        q='In the 2024/25 Premier League, which team finished with more league points: Manchester United or Newcastle United?'
        with patch.object(self.engine,'final_table',return_value={33:{'points':30},34:{'points':29}}):
            self.assertEqual(self.engine.calculate(q)['answer'],'Manchester United')
        with patch.object(self.engine,'final_table',return_value={33:{'points':30},34:{'points':30}}):
            self.assertEqual(self.engine.check({'question':q,'answer':'Manchester United'})['status'],'ambiguous')
        self.assertEqual(BankEvaluator([]).check({'question':q,'answer':'Manchester United'})['status'],'incomplete')

    def test_explicit_choices_keep_actual_arity_and_canonical_answer(self):
        for q,a,n in [('Did both teams score?','No',2),('Who won: Arsenal or Chelsea?','Arsenal',2),
                      ('What was the outcome: a Arsenal win, a draw, or a Chelsea win?','Draw',3)]:
            item={'id':'EM-GEN-001','topic':'Match recognition','question':q,'answer':a}
            choices,correct=options(item,{},set())
            self.assertEqual(len(choices),n)
            self.assertEqual(next(o['text'] for o in choices if o['id']==correct),a)
        with self.assertRaises(ValueError):options({**item,'answer':'Liverpool'}, {},set())

    def test_identity_and_kit_topics_are_not_season_statistics(self):
        for q,expected in [('Which country is Cardiff in?','Club identity'),('Who sponsored the shirt?','Kits and design'),
                           ('Which club won the FA Cup?','Cup history'),('Which manager was in charge?','Managers')]:
            self.assertEqual(game_topic({'topic':'Season landmarks','question':q}),expected)
        self.assertEqual(kind({'topic':'Season landmarks','question':'Which Greek club won?','answer':'Olympiacos'},set()),'club')
        for question,answer,expected in [
            ('Which club loaned Dean Henderson to Sheffield United?','Manchester United','Transfers and loans'),
            ('Which goalkeeper saved a penalty in the Championship play-off final?','Danny Ward','Cup history'),
            ('Which Manchester club did Brentford beat?','Manchester City','Match recognition'),
            ('Which competition provided their first major trophy?','FA Cup','Cup history')]:
            self.assertEqual(game_topic({'topic':'Season landmarks','question':question,'answer':answer}),expected)


class SourcePreflightTests(unittest.TestCase):
    def test_entire_new_source_has_valid_options_and_topics(self):
        source=Path(__file__).parents[1]/'data/trivia/premier_league_easy_medium_trivia_2000.md'
        if not source.exists():self.skipTest('Source fixture not present')
        items=parse_bank(source.read_text());self.assertEqual(len(items),2000)
        self.assertEqual(sum(bool(exclusion(i)) for i in items),16)
        accepted=[i for i in items if not exclusion(i)];pools,clubs=pools_for(accepted)
        arities=Counter()
        for item in accepted:
            with self.subTest(question=item['id']):
                self.assertIn(game_topic(item),SOURCE_TOPIC)
                choices,correct=options(item,pools,clubs)
                self.assertEqual(sum(canonical(o['text'])==canonical(item['answer']) for o in choices),1)
                self.assertEqual(next(o['text'] for o in choices if o['id']==correct),item['answer'])
                arities[len(choices)]+=1
        self.assertEqual(set(arities),{2,3,4})
