import unittest

from pydantic import ValidationError

from api.trivia_events import aggregate_events, normalized_name
from api.trivia_models import TriviaSpec, GradeAnswer
from api.trivia_player_facts import player_facts, clock_key


def spec(**kwargs):
    return TriviaSpec.model_validate({'template': 'top_scorer', 'league_id': 39,
        'period': {'mode': 'seasons', 'seasons': [2024]}, 'minimum_sample': 1, **kwargs})


def team(fid=1, tid=1, **kwargs):
    return dict(fixture_id=fid, team_id=tid, team_name=f'Team {tid}', opponent_name='Opponent',
        season=2024, match_date='2024-09-01', is_home=tid == 1, goals_for=2, goals_against=1,
        result='W', was_behind=True, timeline_valid=True, reasons=[], scorers_valid=True,
        substitutes_valid=True, scorer_reasons=[], substitute_reasons=[], **kwargs)


def goal(pid=10, minute=86, **kwargs):
    result = dict(fixture_id=1, team_id=1, source_order=0, player_id=pid, player_name=f'Player name {pid}',
        aliases=[f'Player name {pid}'], clock_key=minute * 1000, elapsed_minute=minute,
        extra_minute=None, event_type='Goal', event_detail='Normal Goal', scorer_role='substitute')
    return {**result, **kwargs}


class EventSpecTests(unittest.TestCase):
    def test_period_still_required(self):
        with self.assertRaises(ValidationError):
            TriviaSpec(template='top_scorer', league_id=39)

    def test_scope_and_filter_compatibility(self):
        for changes in [{'template': 'player_goals'}, {'template': 'win_rate'},
                        {'template': 'top_scorer', 'player_id': 1},
                        {'template': 'most_comeback_wins', 'team_id': 1},
                        {'template': 'comeback_wins', 'team_id': 1, 'goal_filter': {}},
                        {'goal_filter': {'after_minute': 85, 'extra': 1}}]:
            with self.assertRaises(ValidationError):
                spec(**changes)

    def test_answer_requires_exactly_one_nonempty_value(self):
        for answer in [{}, {'value': 1, 'text': 'name'}, {'text': '   '}, {'value': float('nan')}]:
            with self.assertRaises(ValidationError):
                GradeAnswer(**answer)
        self.assertEqual(GradeAnswer(text='Bruno Fernandes').text, 'Bruno Fernandes')

    def test_name_normalization(self):
        self.assertEqual(normalized_name('  T. Soucek '), normalized_name('T. Sou\u010dek'))
        self.assertNotEqual(normalized_name('Smith'), normalized_name('Smith Rowe'))


class GoalAggregationTests(unittest.TestCase):
    def test_threshold_is_strict_and_stoppage_not_added_to_elapsed(self):
        result = aggregate_events(spec(goal_filter={'after_minute': 85}), [team()],
                                  [goal(minute=85), goal(minute=86), goal(minute=45, clock_key=45007)])
        self.assertEqual(result['answer']['value'], 1)

    def test_stoppage_boundary(self):
        result = aggregate_events(spec(goal_filter={'after_minute': 90, 'extra': 3}), [team()],
                                  [goal(clock_key=90003), goal(clock_key=90004)])
        self.assertEqual(result['answer']['value'], 1)

    def test_own_goals_missed_penalties_and_starters_excluded(self):
        result = aggregate_events(spec(goal_filter={'role': 'substitute'}), [team()], [goal(),
            goal(event_detail='Own Goal'), goal(event_detail='Missed Penalty'), goal(scorer_role='starter')])
        self.assertEqual(result['answer']['value'], 1)

    def test_scoring_matches_not_goal_count(self):
        result = aggregate_events(spec(goal_filter={'count': 'scoring_matches'}), [team(), team(2)],
                                  [goal(), goal(), goal(fixture_id=2)])
        self.assertEqual(result['answer']['value'], 2)

    def test_transferred_player_is_one_entity_and_fixture_not_duplicated(self):
        result = aggregate_events(spec(), [team(), team(tid=2), team(2, 3)],
                                  [goal(), goal(fixture_id=2, team_id=3)])
        self.assertEqual(result['answer']['value'], 2)
        self.assertEqual(len(result['leaderboard']), 1)
        self.assertEqual(len(result['evidence']), 2)
        self.assertEqual(result['coverage']['requested_matches'], 2)

    def test_opponent_goals_do_not_count_in_team_scope(self):
        result = aggregate_events(spec(team_id=1), [team()], [goal(), goal(20, team_id=2)])
        self.assertEqual(len(result['leaderboard']), 1)

    def test_away_evidence_keeps_home_away_score_order(self):
        result = aggregate_events(spec(venue='away'), [team(tid=2)], [goal(team_id=2)])
        row = result['evidence'][0]
        self.assertEqual((row['final_home'], row['final_away']), (1, 2))
        self.assertEqual(row['result_label'], 'Away win')

    def test_player_total_can_be_zero_but_empty_ranking_cannot_publish(self):
        result = aggregate_events(spec(template='player_goals', player_id=99), [team()], [goal()])
        self.assertEqual(result['answer']['value'], 0)
        self.assertTrue(result['coverage']['publishable'])
        empty = aggregate_events(spec(), [team()], [])
        self.assertIsNone(empty['answer']['value'])
        self.assertFalse(empty['coverage']['publishable'])

    def test_ties_keep_all_winners(self):
        result = aggregate_events(spec(), [team()], [goal(), goal(20)])
        self.assertEqual({r['entity_id'] for r in result['answer']['accepted']}, {10, 20})
        self.assertTrue(result['coverage']['publishable'])

    def test_ambiguous_alias_is_not_an_accepted_answer(self):
        result = aggregate_events(spec(), [team()], [goal(player_name='J. Smith', aliases=['John Smith']),
            goal(player_name='J. Smith', aliases=['John Smith']), goal(20, player_name='J. Smith', aliases=['James Smith'])])
        self.assertEqual(result['answer']['accepted'][0]['aliases'], ['John Smith'])

    def test_missing_roles_block_only_substitute_questions(self):
        row = {**team(), 'substitutes_valid': False, 'substitute_reasons': ['unverified_scorer_role']}
        self.assertTrue(aggregate_events(spec(), [row], [goal()])['coverage']['publishable'])
        result = aggregate_events(spec(goal_filter={'role': 'substitute'}), [row], [goal()])
        self.assertFalse(result['coverage']['publishable'])
        self.assertIsNone(result['answer']['value'])

    def test_partial_coverage_is_never_silently_published(self):
        rows = [team(), {**team(2), 'scorers_valid': False, 'scorer_reasons': ['missing_scorer_identity']}]
        result = aggregate_events(spec(), rows, [goal()])
        self.assertEqual(result['answer']['value'], 1)
        self.assertEqual(result['coverage']['excluded_matches'], 1)
        self.assertFalse(result['coverage']['publishable'])

    def test_comeback_requires_behind_and_final_win(self):
        rows = [team(), {**team(2), 'result': 'D'}, {**team(3), 'was_behind': False}]
        result = aggregate_events(spec(template='comeback_wins', team_id=1), rows, [])
        self.assertEqual(result['answer']['value'], 1)
        self.assertEqual(result['answer']['sample_size'], 3)

    def test_team_ranking_counts_each_victory_once(self):
        rows = [team(), {**team(tid=2), 'result': 'L'}, team(2, 2)]
        result = aggregate_events(spec(template='most_comeback_wins'), rows, [])
        self.assertEqual(result['answer']['value'], 1)
        self.assertEqual(len(result['answer']['accepted']), 2)
        self.assertEqual(len(result['evidence']), 2)


class PlayerSnapshotTests(unittest.TestCase):
    def build(self, events, lineups=None, stats=None, timeline=True):
        return player_facts({'home_team_id': 1, 'away_team_id': 2}, events, lineups or [], stats or [],
                            {10: {'player_name': 'M. Player', 'first_name': 'Mike', 'last_name': 'Player'}}, timeline)

    def test_unused_bench_is_not_appearance_or_proof_of_substitute_goal(self):
        rows = [{'team_id': 1, 'player_id': 10, 'lineup_type': 'substitute'}]
        data = self.build([goal()], rows)
        self.assertFalse(data['substitutes_valid'])
        self.assertIsNone(data['events'][0]['scorer_role'])
        unused = self.build([], rows)['players'][0]
        self.assertFalse(unused['appeared'])

    def test_substitution_confirms_incoming_not_outgoing_player(self):
        sub = goal(player_id=20, event_type='subst', assist_player_id=10, minute=70)
        data = self.build([sub, goal(source_order=1)])
        self.assertTrue(data['substitutes_valid'])
        self.assertEqual(data['events'][1]['scorer_role'], 'substitute')
        self.assertEqual(data['players'][0]['role'], 'substitute')

    def test_entry_after_goal_is_not_proof(self):
        sub = goal(event_type='subst', assist_player_id=10, player_id=20, minute=89)
        self.assertFalse(self.build([goal(), sub])['substitutes_valid'])

    def test_starter_and_conflicting_memberships(self):
        lineup = [{'team_id': 1, 'player_id': 10, 'lineup_type': 'start_xi'}]
        self.assertEqual(self.build([goal()], lineup)['events'][0]['scorer_role'], 'starter')
        data = self.build([goal()], lineup + [{'team_id': 2, 'player_id': 10, 'lineup_type': 'start_xi'}])
        self.assertFalse(data['scorers_valid'])
        self.assertFalse(data['substitutes_valid'])

    def test_missing_identity_and_bad_timeline_are_quarantined(self):
        self.assertFalse(self.build([goal(player_id=None, player_name=None)])['scorers_valid'])
        self.assertFalse(self.build([goal()], timeline=False)['scorers_valid'])

    def test_own_goal_does_not_require_beneficiary_membership(self):
        data = self.build([goal(event_detail='Own Goal')], [{'team_id': 2, 'player_id': 10, 'lineup_type': 'start_xi'}])
        self.assertTrue(data['scorers_valid'])

    def test_snapshot_aliases_and_metrics(self):
        data = self.build([], stats=[{'team_id': 1, 'player_id': 10, 'minutes': 0, 'rating': None}])
        self.assertIn('Mike Player', data['players'][0]['aliases'])
        self.assertIsNone(data['players'][0]['statistics']['assists'])
        self.assertFalse(data['players'][0]['appeared'])

    def test_invalid_clock_is_unknown(self):
        self.assertIsNone(clock_key(goal(elapsed_minute=-1)))
        self.assertIsNone(clock_key(goal(extra_minute=4)))


if __name__ == '__main__':
    unittest.main()
