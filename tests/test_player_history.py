from datetime import date
from decimal import Decimal
import unittest

from api.player_history import club_history, normalize_transfers, season_history


def record(**changes):
    return dict(dict(league_id=39, league_name='Premier League', season=2024, team_id=1, team_name='Club A',
                     logo_url=None, appearances=2, lineups=1, substitutes_in=1, rating=Decimal('9.00'),
                     goals_total=1, assists=0, yellow_cards=1, yellow_red_cards=1, red_cards=0), **changes)


def match(ident, **changes):
    return dict(dict(fixture_id=ident, league_id=39, league_name='Premier League', season=2024,
                     team_id=1, team_name='Club A', logo_url=None, started=False, entered=False,
                     minutes=90, rating=Decimal('7.0'), goals=0, assists=0), **changes)


def transfer(day, origin=1, destination=2, **changes):
    return dict(dict(transfer_date=date.fromisoformat(day) if day else None, transfer_date_raw=day,
                     transfer_type='Transfer', team_out_id=origin, team_out_name=f'Club {origin}',
                     team_in_id=destination, team_in_name=f'Club {destination}', raw_payload={}), **changes)


class PlayerSeasonsTests(unittest.TestCase):
    def test_unused_substitute_is_not_an_appearance_or_rating(self):
        rows = [match(1, minutes=None, rating=10), match(2, minutes=0, rating=10), match(3)]
        result = season_history([record(appearances=None, lineups=None, substitutes_in=None)], rows)[0]
        self.assertEqual(result['appearances'], 1)
        self.assertEqual(result['rating'], 7)
        self.assertEqual(result['rated_matches'], 1)
        self.assertIn('partial_appearance_coverage', result['warnings'])

    def test_zero_minute_entry_and_starter_are_real_appearances(self):
        rows = [match(1, minutes=0, entered=True), match(2, minutes=None, started=True)]
        result = season_history([record()], rows)[0]
        self.assertEqual(result['verified_appearances'], 2)
        self.assertEqual(result['rated_matches'], 2)

    def test_appearances_fallback_never_uses_bench_count(self):
        result = season_history([record(appearances=None, lineups=3, substitutes_in=2, substitutes_bench=15)], [])[0]
        self.assertEqual(result['appearances'], 5)
        self.assertEqual(result['clubs'][0]['appearance_source'], 'starts_plus_substitutions')

    def test_multi_club_rating_uses_matches_not_average_of_averages(self):
        records = [record(appearances=1, lineups=1, substitutes_in=0), record(team_id=2, team_name='Club B')]
        rows = [match(1, rating=10), match(2, team_id=2, rating=4), match(3, team_id=2, rating=4)]
        result = season_history(records, rows)[0]
        self.assertEqual(result['appearances'], 3)
        self.assertEqual(result['rating'], 6)
        self.assertEqual(result['rated_matches'], 3)
        self.assertEqual(result['red_cards'], 2)

    def test_missing_totals_do_not_become_zero_or_partial_sum(self):
        rows = [record(assists=None), record(team_id=2)]
        result = season_history(rows, [])[0]
        self.assertIsNone(result['assists'])
        self.assertIsNone(result['rating'])  # No weighted average invented from club aggregates.

    def test_red_cards_include_second_yellow_and_preserve_unknown(self):
        self.assertEqual(season_history([record()], [])[0]['red_cards'], 1)
        self.assertIsNone(season_history([record(yellow_red_cards=None)], [])[0]['red_cards'])

    def test_provider_rating_is_explicit_fallback_without_sample(self):
        result = season_history([record()], [])[0]
        self.assertEqual(result['rating'], 9)
        self.assertEqual(result['rating_source'], 'provider_season')
        self.assertEqual(result['rated_matches'], 0)

    def test_counts_can_be_reconstructed_only_with_complete_match_sample(self):
        result = season_history([record(assists=None)], [match(1, assists=1), match(2, assists=2)])[0]
        self.assertEqual(result['assists'], 3)
        self.assertIsNone(season_history([record(assists=None)], [match(1, assists=1)])[0]['assists'])

    def test_same_fixture_in_two_teams_is_not_double_counted(self):
        result = season_history([record()], [match(1), match(1, team_id=2)])[0]
        self.assertEqual(result['rated_matches'], 0)
        self.assertIn('ambiguous_match_records', result['warnings'])

    def test_empty_records_and_zero_apps(self):
        self.assertEqual(season_history([], []), [])
        result = season_history([record(appearances=0, lineups=0, substitutes_in=0)], [match(1, minutes=None)])[0]
        self.assertEqual(result['appearances'], 0)
        self.assertIsNone(result['rating'])

    def test_competitions_are_not_combined(self):
        records = [record(), record(league_id=140, league_name='La Liga')]
        self.assertEqual(len(season_history(records, [])), 2)

    def test_zero_appearance_club_does_not_hide_other_clubs_goals_and_assists(self):
        records = [record(), record(team_id=2, appearances=0, lineups=0, substitutes_in=0, goals_total=None, assists=None, yellow_cards=None)]
        result = season_history(records, [])[0]
        self.assertEqual(result['goals'], 1)
        self.assertEqual(result['assists'], 0)
        self.assertIsNone(result['yellow_cards'])  # Bench bookings remain possible.


class PlayerTransfersTests(unittest.TestCase):
    def test_exact_duplicate_with_unambiguous_name_alias_is_merged(self):
        rows = [transfer('2024-01-01', destination=None, team_in_name='Manchester Utd'),
                transfer('2024-01-01', destination=33, team_in_name='Manchester United')]
        result = normalize_transfers(rows, {})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['in']['team_id'], 33)
        self.assertEqual(result[0]['source_records'], 2)

    def test_different_dates_are_not_erased(self):
        rows = [transfer('2024-01-01'), transfer('2024-01-02')]
        result = normalize_transfers(rows, {})
        self.assertEqual(len(result), 2)
        history = club_history(result, [])
        self.assertEqual(history[0]['arrival_dates'], [date(2024, 1, 1), date(2024, 1, 2)])
        self.assertTrue(history[0]['uncertain'])
        self.assertEqual(len(history), 2)

    def test_loan_return_creates_separate_spells_at_parent_club(self):
        rows = [transfer('2024-01-01', transfer_type='Loan'), transfer('2024-06-01', 2, 1, transfer_type='Return from loan')]
        history = club_history(normalize_transfers(rows, {}), [])
        self.assertEqual([h['club']['team_id'] for h in history], [1, 2, 1])
        self.assertEqual(history[-1]['arrival_dates'], [])
        self.assertIsNone(history[0]['end_date'])

    def test_future_move_does_not_change_club_history(self):
        moves = normalize_transfers([transfer('2024-01-01'), transfer('2030-01-01', 2, 3)], {}, today=date(2025, 1, 1))
        self.assertTrue(moves[0]['upcoming'])
        self.assertEqual(club_history(moves, [])[0]['club']['team_id'], 2)

    def test_undated_transfers_do_not_disappear_from_club_history(self):
        moves = normalize_transfers([transfer(None)], {})
        history = club_history(moves, [])
        self.assertEqual(len(history), 2)
        self.assertTrue(all(h['undated_transfer'] and not h['arrival_dates'] for h in history))

    def test_season_only_clubs_are_preserved_without_inventing_dates(self):
        seasons = season_history([record(), record(season=2023)], [])
        history = club_history([], seasons)
        self.assertEqual(history[0]['recorded_seasons'], [2024, 2023])
        self.assertEqual(history[0]['arrival_dates'], [])
        self.assertIsNone(history[0]['end_date'])

    def test_ambiguous_club_alias_does_not_get_guessed_id(self):
        teams = {1: {'team_id': 1, 'team_name': 'United'}, 2: {'team_id': 2, 'team_name': 'United'}}
        move = normalize_transfers([transfer('2024-01-01', destination=None, team_in_name='United')], teams)[0]
        self.assertIsNone(move['in']['team_id'])
