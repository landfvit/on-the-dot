import unittest
from datetime import date

from pydantic import ValidationError

from api.trivia_engine import aggregate, reconstruct
from api.trivia_models import EvaluationRequest, TriviaSpec


def fixture(**changes):
    return dict(home_team_id=1, away_team_id=2, home_goals=2, away_goals=1,
                halftime_home=1, halftime_away=0, status='FT', **changes)


def event(minute, team=1, detail='Normal Goal', extra=None, player=10):
    return {'event_type': 'Goal', 'event_detail': detail, 'team_id': team,
            'elapsed_minute': minute, 'extra_minute': extra, 'player_id': player}


def specification(**changes):
    return TriviaSpec.model_validate({'template': 'conditional_win_rate', 'team_id': 1, 'league_id': 39,
        'period': {'mode': 'seasons', 'seasons': [2024]}, 'minimum_sample': 1,
        'condition': {'minute': 80, 'goal_difference': -2}, **changes})


class TriviaTimelineTests(unittest.TestCase):
    def test_checkpoint_groups_same_minute_and_intervals_are_half_open(self):
        result = reconstruct(fixture(), [event(10), event(80), event(80, team=2)], True)
        self.assertTrue(result['timeline_valid'])
        self.assertEqual(result['intervals'], [(0, 10000, 0, 0), (10000, 80000, 1, 0), (80000, 100000, 2, 1)])

    def test_stoppage_orders_before_next_half_not_elapsed_plus_extra(self):
        result = reconstruct(fixture(), [event(45, extra=7), event(46), event(90, 2, extra=4)], True)
        self.assertTrue(result['timeline_valid'])
        self.assertIn((45007, 46000, 1, 0), result['intervals'])
        self.assertIn((46000, 90004, 2, 0), result['intervals'])

    def test_own_goal_credits_provider_beneficiary_not_scorer_team(self):
        result = reconstruct(fixture(), [event(10), event(50, detail='Own Goal'), event(81, team=2)], True)
        self.assertTrue(result['timeline_valid'])
        self.assertEqual(result['intervals'][-1][2:], (2, 1))

    def test_missed_penalty_is_not_a_goal(self):
        result = reconstruct(fixture(), [event(10), event(50), event(81, team=2), event(30, detail='Missed Penalty')], True)
        self.assertTrue(result['timeline_valid'])

    def test_var_cancellation_is_quarantined_not_guessed(self):
        events = [event(10), event(50), event(81, team=2), {'event_type': 'Var', 'event_detail': 'Goal cancelled'}]
        result = reconstruct(fixture(), events, True)
        self.assertFalse(result['timeline_valid'])
        self.assertTrue(result['result_valid'])
        self.assertIn('unresolved_var_review', result['reasons'])

    def test_missing_feed_is_not_zero_zero(self):
        f = {**fixture(), 'home_goals': 0, 'away_goals': 0, 'halftime_home': 0}
        result = reconstruct(f, [], True)
        self.assertTrue(result['result_valid'])
        self.assertFalse(result['timeline_valid'])
        self.assertEqual(result['intervals'], [])

    def test_verified_goalless_feed_has_zero_state(self):
        f = {**fixture(), 'home_goals': 0, 'away_goals': 0, 'halftime_home': 0}
        result = reconstruct(f, [{'event_type': 'Card', 'event_detail': 'Yellow Card'}], True)
        self.assertTrue(result['timeline_valid'])
        self.assertEqual(result['intervals'], [(0, 100000, 0, 0)])

    def test_duplicate_goal_and_halftime_mismatch_are_rejected(self):
        result = reconstruct(fixture(), [event(10), event(10), event(81, team=2)], True)
        self.assertIn('ambiguous_duplicate_goal', result['reasons'])
        self.assertIn('halftime_score_mismatch', result['reasons'])

    def test_invalid_times_and_goal_types_are_rejected(self):
        for goal in [event(91), event(80, extra=1), event(10, team=99), event(10, detail='Unknown')]:
            self.assertFalse(reconstruct(fixture(), [goal], True)['timeline_valid'])

    def test_future_and_conflicting_results_are_not_eligible(self):
        for f in [{**fixture(), 'status': 'NS'}, {**fixture(), 'fulltime_home': 5, 'fulltime_away': 0}]:
            self.assertFalse(reconstruct(f, [], False)['result_valid'])


class TriviaSpecTests(unittest.TestCase):
    def test_period_is_required_and_has_no_default(self):
        with self.assertRaises(ValidationError):
            TriviaSpec.model_validate({'template': 'win_rate', 'league_id': 39, 'team_id': 1})

    def test_empty_reversed_duplicate_and_extra_scope_fields_fail(self):
        periods = [{'mode': 'seasons', 'seasons': []}, {'mode': 'seasons', 'seasons': [2024, 2024]},
                   {'mode': 'season_range', 'start': 2025, 'end': 2024},
                   {'mode': 'dates', 'start': '2025-01-01', 'end': '2024-01-01'}, {'mode': 'all', 'sql': 'SELECT 1'}]
        for period in periods:
            with self.assertRaises(ValidationError):
                specification(period=period)

    def test_all_four_period_modes_are_explicit(self):
        for period in [{'mode': 'all'}, {'mode': 'seasons', 'seasons': [2020, 2024]},
                       {'mode': 'season_range', 'start': 2020, 'end': 2024},
                       {'mode': 'dates', 'start': '2020-01-01', 'end': '2020-12-31'}]:
            self.assertEqual(specification(period=period).period.mode, period['mode'])

    def test_conditions_are_typed_and_cannot_leak_into_simple_questions(self):
        with self.assertRaises(ValidationError):
            specification(template='total_wins')
        with self.assertRaises(ValidationError):
            specification(condition={'minute': 80, 'extra': 1, 'goal_difference': -2})
        with self.assertRaises(ValidationError):
            EvaluationRequest.model_validate({'specification': specification().model_dump(), 'answer': 100})


class TriviaAggregationTests(unittest.TestCase):
    def row(self, result='W', **changes):
        return {'fixture_id': 1, 'result': result, 'goals_for': 3, 'goals_against': 2,
                'result_valid': True, 'timeline_valid': True, 'reasons': [],
                'checkpoint_for': 0, 'checkpoint_against': 2, **changes}

    def test_ratio_keeps_numerator_and_denominator(self):
        result = aggregate(specification(), [self.row(), self.row(), self.row('L')])
        self.assertEqual(result['answer']['value'], 66.7)
        self.assertEqual(result['answer']['numerator'], 2)
        self.assertEqual(result['answer']['denominator'], 3)

    def test_zero_matches_is_not_zero_percent(self):
        result = aggregate(specification(), [])
        self.assertIsNone(result['answer']['value'])
        self.assertFalse(result['coverage']['publishable'])
        self.assertEqual(aggregate(specification(), [self.row('L')])['answer']['value'], 0)

    def test_excluded_matches_are_visible_and_block_publication(self):
        result = aggregate(specification(), [self.row(), self.row(timeline_valid=False, reasons=['missing_event_feed'])])
        self.assertEqual(result['answer']['denominator'], 1)
        self.assertEqual(result['coverage']['requested_matches'], 2)
        self.assertEqual(result['coverage']['excluded_matches'], 1)
        self.assertFalse(result['coverage']['publishable'])

    def test_condition_does_not_silently_change_to_at_least(self):
        rows = [self.row(), self.row(checkpoint_against=3)]
        self.assertEqual(aggregate(specification(), rows)['answer']['denominator'], 1)
        spec = specification(condition={'minute': 80, 'operator': 'lte', 'goal_difference': -2})
        self.assertEqual(aggregate(spec, rows)['answer']['denominator'], 2)

    def test_simple_questions_do_not_require_timeline(self):
        spec = specification(template='total_goals', condition=None)
        result = aggregate(spec, [self.row(timeline_valid=False, reasons=['missing_event_feed'])])
        self.assertEqual(result['answer']['value'], 3)
        self.assertTrue(result['coverage']['publishable'])

    def test_minimum_sample_blocks_publication(self):
        result = aggregate(specification(minimum_sample=10), [self.row()])
        self.assertIn('small_sample', result['coverage']['warnings'])
        self.assertFalse(result['coverage']['publishable'])
