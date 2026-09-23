from copy import deepcopy
from datetime import datetime,timedelta,timezone
import os
import random
import unittest

from api.database import get_connection
from api.trivia_generation_experiment import PLANS,NoveltyIndex,snapshot_answer,wording
from src.check_generated_trivia import independent_answer


def matches(seed=1):
    rng=random.Random(seed);rows=[]
    for n in range(38):
        gf,ga=rng.randrange(5),rng.randrange(4)
        rows.append({'fixture_id':n+1,'match_date':datetime(2024,8,1,tzinfo=timezone.utc)+timedelta(days=7*n),
            'team_id':33,'season':2024,'opponent_id':100+n%19,'opponent_name':f'Opponent {n%19}',
            'is_home':n<19,'goals_for':gf,'goals_against':ga,'result':'W' if gf>ga else 'D' if gf==ga else 'L','result_valid':True})
    return rows


class GeneratedTriviaTests(unittest.TestCase):
    def test_twenty_distinct_plans_and_explicit_seasons(self):
        self.assertEqual(len(PLANS),20);self.assertEqual(len({p.key for p in PLANS}),20)
        self.assertIn('2024/25',wording('opening_points','Manchester United',2024))
        self.assertNotEqual(wording('opening_points','Manchester United',2024),wording('opening_points','Manchester United',2023))

    def test_chronology_not_input_order_or_fixture_round(self):
        rows=matches();expected=sum({'W':3,'D':1,'L':0}[r['result']] for r in rows[:6])
        self.assertEqual(snapshot_answer('opening_points',list(reversed(rows)))['value'],expected)
        self.assertEqual(snapshot_answer('opening_points',rows)['evidence_fixture_ids'],list(range(1,7)))

    def test_overlapping_clean_sheet_pairs_count_separately(self):
        rows=matches()
        for r in rows:r.update(goals_for=0,goals_against=1,result='L')
        for r in rows[:4]:r.update(goals_against=0,result='D')
        answer=snapshot_answer('clean_sheet_pairs',rows)
        self.assertEqual(answer['value'],3);self.assertEqual(answer['details']['pairs'],[[1,2],[2,3],[3,4]])
        self.assertEqual(snapshot_answer('streak_clean_sheets',rows)['value'],4)

    def test_tied_largest_win_is_not_arbitrarily_resolved(self):
        rows=matches()
        for r in rows:r.update(goals_for=1,goals_against=0,result='W')
        with self.assertRaisesRegex(ValueError,'unique'):snapshot_answer('biggest_home_win_opponent',rows)
        rows[0]['goals_for']=2
        self.assertEqual(snapshot_answer('biggest_home_win_opponent',rows)['value'],100)

    def test_mixed_incomplete_invalid_and_same_kickoff_scopes_fail_closed(self):
        rows=matches()
        invalid=[rows[:-1],rows[:-1]+rows[:1]]
        for field,value in [('season',2023),('result_valid',False),('team_id',42),('match_date',rows[1]['match_date'])]:
            copy=deepcopy(rows);copy[0][field]=value;invalid.append(copy)
        for case in invalid:
            with self.subTest(case=case[0]),self.assertRaises(ValueError):snapshot_answer('opening_goals',case)

    def test_exact_alias_paraphrase_and_same_fact_duplicates_rejected(self):
        q=wording('opening_points','Manchester United',2024)
        index=NoveltyIndex([{'id':'old','question':q.replace('Manchester United','Man Utd')}])
        self.assertFalse(index.check('opening_points',33,2024,q)['accepted'])
        other='Looking at the opening six league games of 2024/25, how many points did Manchester United collect?'
        index=NoveltyIndex([{'id':'old','question':other}])
        self.assertFalse(index.check('opening_points',33,2024,q)['accepted'])
        self.assertTrue(index.check('closing_goals',33,2024,wording('closing_goals','Manchester United',2024))['accepted'])


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Temporary-table independent SQL checks')
class IndependentGeneratedSQLTests(unittest.TestCase):
    def test_100_synthetic_seasons_across_all_twenty_plans(self):
        with get_connection() as conn:
            # Shadows the production table only in this session. No provider rows are changed.
            conn.execute('''CREATE TEMP TABLE fixtures(fixture_id bigint,match_date timestamptz,league_id int,season int,
                home_team_id int,away_team_id int,home_goals int,away_goals int) ON COMMIT DROP''')
            checked=0;ambiguous=0
            for seed in range(100):
                rows=matches(seed);conn.execute('TRUNCATE pg_temp.fixtures')
                with conn.cursor() as cursor:
                    cursor.executemany('INSERT INTO pg_temp.fixtures VALUES(%s,%s,39,2024,%s,%s,%s,%s)',
                        [(r['fixture_id'],r['match_date'],33 if r['is_home'] else r['opponent_id'],r['opponent_id'] if r['is_home'] else 33,
                          r['goals_for'] if r['is_home'] else r['goals_against'],r['goals_against'] if r['is_home'] else r['goals_for']) for r in rows])
                for plan in PLANS:
                    with self.subTest(seed=seed,plan=plan.key):
                        try:expected=snapshot_answer(plan.key,rows)
                        except ValueError:
                            with self.assertRaises(ValueError):independent_answer(conn,plan.key,33,2024)
                            ambiguous+=1;continue
                        actual=independent_answer(conn,plan.key,33,2024)
                        self.assertEqual(expected['value'],actual['value'])
                        self.assertEqual(expected['evidence_fixture_ids'],actual['evidence_fixture_ids']);checked+=1
            self.assertEqual(checked+ambiguous,2000);self.assertGreater(checked,1800)
            # Deliberately corrupt the first source score: the independent result must change.
            before=snapshot_answer('opening_goals',rows)['value']
            conn.execute('UPDATE pg_temp.fixtures SET home_goals=home_goals+10 WHERE fixture_id=1')
            self.assertNotEqual(before,independent_answer(conn,'opening_goals',33,2024)['value'])
