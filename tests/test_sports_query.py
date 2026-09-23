import copy
import unittest
from unittest.mock import patch
from uuid import UUID

from pydantic import ValidationError

from api.sports_query import ParseRequest, SportsQuery, parse_query
from api.trivia import grade_answer
from api.trivia_engine import aggregate
from api.trivia_models import GradeAnswer, TriviaSpec
from api.trivia_events import aggregate_events, display_surname


class QueryParserTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = {
            'dataset_id': str(UUID(int=1)), 'snapshot_date': '2025-09-01T00:00:00Z',
            'competition_name': 'Premier League', 'competition_aliases': ['premier league', 'pl', 'epl'],
            'teams': [{'team_id': i, 'team_name': n, 'aliases': a} for i, n, a in [
                (33, 'Manchester United', ['man utd', 'man united', 'mufc', 'united']),
                (34, 'Newcastle', ['newcastle united', 'united']), (40, 'Liverpool', []),
                (42, 'Arsenal', []), (47, 'Tottenham', ['spurs']), (49, 'Chelsea', []), (50, 'Manchester City', ['man city'])]],
            'seasons': [{'season': s, 'fixtures': 380, 'finished': 40 if s == 2025 else 380} for s in range(2010, 2026)],
            'groups': [{'group_key': 'big_6', 'version': 1, 'label': 'Big 6', 'team_ids': [33, 40, 42, 47, 49, 50]}],
        }

    def parse(self, text):
        return parse_query(ParseRequest(text=text, competition_id=39), self.catalogue)

    def test_document_examples_resolve_same_explicit_scope(self):
        for text in ['Man Utd win rate against Big 6 last 10 seasons',
                     'Manchester United win percentage vs big six last 10 seasons',
                     'MUFC win rate against the big 6 teams in the last 10 seasons',
                     '  MAN UNITED  win rate against big 6 last 10 seasons?']:
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertTrue(result['ok'], result)
                query = result['query']
                self.assertEqual(query['entity_id'], 33)
                self.assertEqual(query['timeframe']['seasons'], list(range(2015, 2025)))
                self.assertEqual(query['filters']['opponents']['team_ids'], [40, 42, 47, 49, 50])

    def test_metric_period_venue_and_opponent_combinations(self):
        for metric in ['win rate', 'loss rate', 'draw rate', 'goals scored', 'goals conceded', 'goals per game', 'points per game', 'clean sheets']:
            for venue in ['at home', 'away', 'away from home']:
                with self.subTest(metric=metric, venue=venue):
                    r = self.parse(f'Arsenal {metric} {venue} against Liverpool in PL in 2020/21')
                    self.assertTrue(r['ok'], r)
                    self.assertEqual(r['query']['filters']['opponents']['team_ids'], [40])
                    self.assertEqual(r['query']['timeframe']['seasons'], [2020])

    def test_since_year_means_season_start_not_calendar_date(self):
        result = self.parse('Liverpool goals per game since 2020')
        self.assertEqual(result['query']['timeframe']['seasons'], [2020, 2021, 2022, 2023, 2024])

    def test_between_and_full_season_notation(self):
        self.assertEqual(self.parse('Arsenal wins between 2015 and 2020')['query']['timeframe']['seasons'], list(range(2015, 2021)))
        self.assertEqual(self.parse('Chelsea clean sheets 2017/2018')['query']['timeframe']['seasons'], [2017])

    def test_all_time_is_only_explicit_available_snapshot_seasons(self):
        self.assertEqual(self.parse('Arsenal wins all time')['query']['timeframe']['seasons'], list(range(2010, 2026)))

    def test_missing_seasons_are_never_silently_skipped(self):
        self.catalogue['seasons'] = [s for s in self.catalogue['seasons'] if s['season'] != 2022]
        self.assertFalse(self.parse('Arsenal wins last 5 seasons')['ok'])
        self.assertFalse(self.parse('Arsenal wins since 2020')['ok'])

    def test_completed_does_not_mean_cherry_picked_valid_seasons(self):
        self.catalogue['seasons'][-2]['results'] = 379
        self.assertEqual(self.parse('Chelsea clean sheets last season')['query']['timeframe']['seasons'], [2024])

    def test_no_period_or_unsupported_or_injection_never_executes(self):
        for text in ['Arsenal wins', 'United win rate last season', 'Arsenal win rate blah blah 2020/21',
                     'Haaland goals per game last season', 'Arsenal possession last season',
                     'Arsenal wins in Champions League last season', 'Arsenal wins last 0 seasons',
                     'Arsenal wins last 101 seasons', 'Arsenal wins in 2017/19',
                     'Arsenal wins home away last season', 'Arsenal wins last season since 2020',
                     'Arsenal wins against Arsenal last season', 'Arsenal wins 2017/18; DROP TABLE teams',
                     'Arsenal wins since 2090', 'Arsenal wins between 2020 and 2015', 'Arsenal wins 1900/01']:
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertFalse(result['ok'], result)
                self.assertIsNone(result['query'])

    def test_typo_suggestions_are_not_automatic_entity_selection(self):
        result = self.parse('Manchester Untied win rate last season')
        self.assertFalse(result['ok'])
        self.assertEqual(result['suggestions'][0]['team_id'], 33)
        self.assertTrue(self.parse(result['suggestions'][0]['query_text'])['ok'])

    def test_ambiguous_united_requires_full_name(self):
        result = self.parse('United win rate last season')
        self.assertEqual({s['team_id'] for s in result['suggestions']}, {33, 34})

    def test_unknown_tail_is_reported_with_recognized_prefix(self):
        result = self.parse('Arsenal win rate under manager x last season')
        self.assertEqual(result['recognized']['metric'], 'win_rate')
        self.assertIn('under manager', result['issues'][0])

    def test_schema_rejects_extra_sql_unsupported_metrics_and_self_opponents(self):
        base = self.parse('Arsenal wins last season')['query']
        for extra in [{'sql': 'SELECT 1'}, {'metric': 'possession'}, {'entity_type': 'player'},
                      {'filters': {'opponents': {'team_ids': [42]}}},
                      {'filters': {'opponents': {'team_ids': [33, 33]}}}]:
            with self.assertRaises(ValidationError):
                SportsQuery(**{**base, **extra})

    def test_semantically_different_expressions_are_not_approximated(self):
        for text in ['Arsenal win rate last decade',
                     'Arsenal win rate against top six last 5 seasons',
                     'Arsenal record against Chelsea last 5 seasons',
                     'Arsenal win rate without player Saka last 5 seasons',
                     'Arsenal win rate last 5 seasons without player Saka',
                     'Arsenal wins after penalties last season',
                     'Arsenal wins including extra time last season']:
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertFalse(result['ok'], result)
                self.assertIsNone(result['query'])

    def test_unsupported_result_basis_and_current_season_flags_fail_closed(self):
        base = self.parse('Arsenal wins last season')['query']
        for extra in [{'result_basis': 'penalty_shootout'}, {'include_current': True},
                      {'timeframe': {**base['timeframe'], 'include_current': True}}]:
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                SportsQuery(**{**base, **extra})

    def test_supported_typo_and_unknown_queries_work_with_network_disabled(self):
        with patch('socket.socket', side_effect=AssertionError('Parser attempted network access')) as sockets:
            self.assertTrue(self.parse('Arsenal wins last season')['ok'])
            self.assertFalse(self.parse('Arsenla wins last season')['ok'])
            self.assertFalse(self.parse('Which club is best without its captain?')['ok'])
            sockets.assert_not_called()

    def test_new_entity_is_resolved_from_catalogue_without_training(self):
        text = 'New Borough FC wins last season'
        self.assertFalse(self.parse(text)['ok'])
        self.catalogue['teams'].append({'team_id': 99999, 'team_name': 'New Borough FC', 'aliases': ['nbfc']})
        self.assertEqual(self.parse(text)['query']['entity_id'], 99999)
        self.assertEqual(self.parse('NBFC wins last season')['query']['entity_id'], 99999)

    def test_relative_period_is_frozen_even_when_a_later_season_finishes(self):
        original = self.parse('Arsenal wins last season')['query']
        self.assertEqual(original['timeframe']['seasons'], [2024])
        self.catalogue['seasons'][-1]['finished'] = 380
        self.assertEqual(self.parse('Arsenal wins last season')['query']['timeframe']['seasons'], [2025])
        self.assertEqual(SportsQuery(**original).specification().period.seasons, [2024])


class QueryMetricTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'fixture_id': i, 'goals_for': a, 'goals_against': b,
                      'result': 'W' if a > b else 'D' if a == b else 'L',
                      'result_valid': True, 'timeline_valid': True, 'reasons': []}
                     for i, (a, b) in enumerate([(3, 0), (1, 1), (0, 2), (0, 0)])]

    def spec(self, template):
        return TriviaSpec(template=template, team_id=33, league_id=39, period={'mode': 'seasons', 'seasons': [2020]}, minimum_sample=1)

    def test_metric_formulas(self):
        for key, expected in {'win_rate': 25, 'draw_rate': 50, 'loss_rate': 25, 'goals_per_game': 1,
                              'points_per_game': 1.25, 'total_goals': 4, 'goals_conceded': 3, 'clean_sheets': 2}.items():
            with self.subTest(key=key):
                r = aggregate(self.spec(key), self.rows)
                self.assertEqual(r['answer']['value'], expected)
                self.assertEqual(r['summary']['played'], 4)
                self.assertEqual(r['summary']['points'], 5)

    def test_excluded_match_is_not_in_denominator_and_blocks_publication(self):
        rows = copy.deepcopy(self.rows); rows[0]['result_valid'] = False
        result = aggregate(self.spec('points_per_game'), rows)
        self.assertEqual(result['answer']['value'], 0.67)
        self.assertEqual(result['answer']['denominator'], 3)
        self.assertFalse(result['coverage']['publishable'])

    def test_empty_sample_has_no_answer_not_zero(self):
        self.assertIsNone(aggregate(self.spec('points_per_game'), [])['answer']['value'])

    def test_decimal_grading_and_rounding(self):
        answer = {'kind': 'decimal', 'value': 1.84, 'rounding_decimals': 2}
        self.assertTrue(grade_answer(answer, GradeAnswer(value=1.84))['correct'])
        self.assertTrue(grade_answer(answer, GradeAnswer(value=1.835))['correct'])
        self.assertFalse(grade_answer(answer, GradeAnswer(value=1.8))['correct'])


class SurnameGradingTests(unittest.TestCase):
    def result(self, identities=(), policy='unique-surname-v1'):
        from test_trivia_events import spec, team, goal
        definition = spec().model_copy(update={'name_policy': policy})
        return aggregate_events(definition, [team()], [goal(player_name='R. Lukaku', aliases=['Romelu Lukaku'])], identities)

    def test_unique_surname_is_frozen_into_answer(self):
        answer = self.result()['answer']
        self.assertIn('Lukaku', answer['accepted'][0]['aliases'])
        self.assertTrue(grade_answer(answer, GradeAnswer(text='lukaku'))['correct'])

    def test_non_scoring_player_with_same_surname_prevents_acceptance(self):
        answer = self.result([{'player_id': 9999, 'player_name': 'J. Lukaku', 'aliases': ['Jordan Lukaku']}])['answer']
        self.assertNotIn('Lukaku', answer['accepted'][0]['aliases'])
        self.assertFalse(grade_answer(answer, GradeAnswer(text='Lukaku'))['correct'])
        self.assertTrue(grade_answer(answer, GradeAnswer(text='Romelu Lukaku'))['correct'])

    def test_compound_surname_and_legacy_policy_are_preserved(self):
        self.assertEqual(display_surname('E. Smith Rowe'), 'Smith Rowe')
        self.assertEqual(display_surname('A. B. Smith'), 'Smith')
        self.assertIsNone(display_surname('Emile Smith Rowe'))
        self.assertNotIn('Lukaku', self.result(policy='exact-v1')['answer']['accepted'][0]['aliases'])
