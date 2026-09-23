import unittest
from datetime import datetime, timezone

from api.match_context import event_timeline, summarize_team
from src.match_context_import import weather_sample, source_url


def fixture(**changes):
    return dict(dict(fixture_id=1, home_team_id=1, away_team_id=2, home_goals=2, away_goals=1,
                     halftime_home=0, halftime_away=1, status='FT', events_imported=True,
                     match_date=datetime(2024, 8, 1, 19, tzinfo=timezone.utc)), **changes)


def goal(minute, team=1, order=0, **changes):
    return dict(dict(source_order=order, elapsed_minute=minute, extra_minute=None, team_id=team,
                     player_id=order + 10, event_type='Goal', event_detail='Normal Goal'), **changes)


class MatchContextTests(unittest.TestCase):
    def test_verified_progress_and_own_goal_beneficiary(self):
        events = [goal(81, order=2), goal(45, 2, 0, extra_minute=3), goal(46, order=1, event_detail='Own Goal')]
        data = event_timeline(fixture(), events)
        self.assertTrue(data['quality']['timeline_valid'])
        self.assertEqual([e['score'] for e in data['events']], [[0, 1], [1, 1], [2, 1]])
        self.assertEqual([e['elapsed_minute'] for e in data['events']], [45, 46, 81])

    def test_invalid_timeline_shows_events_without_fabricated_progress(self):
        data = event_timeline(fixture(), [goal(80)])
        self.assertFalse(data['quality']['timeline_valid'])
        self.assertIsNone(data['events'][0]['score'])
        self.assertEqual(len(data['events']), 1)

    def test_future_results_are_not_verified(self):
        data = event_timeline(fixture(match_date=datetime(2100, 1, 1, tzinfo=timezone.utc)), [goal(20, 2), goal(60), goal(80, order=2)])
        self.assertFalse(data['quality']['timeline_valid'])
        self.assertTrue(all(e['score'] is None for e in data['events']))

    def test_comeback_points_and_intervals_include_stoppage(self):
        f = fixture()
        events = [goal(45, 2, 0, extra_minute=9), goal(46, order=1), goal(90, order=2, extra_minute=8)]
        data = summarize_team([f], {1: events}, 1)
        self.assertEqual(data['points_gained'], 3)
        self.assertEqual(data['points_dropped'], 0)
        self.assertEqual(data['first_goal']['conceded_first']['wins'], 1)
        self.assertEqual(data['goal_intervals'][2]['against'], 1)
        self.assertEqual(data['goal_intervals'][3]['for'], 1)
        self.assertEqual(data['goal_intervals'][5]['for'], 1)

    def test_same_minute_uses_source_order_for_leading_and_trailing(self):
        f = fixture(home_goals=1, away_goals=1, halftime_away=0)
        data = summarize_team([f], {1: [goal(70, 1, 0), goal(70, 2, 1)]}, 1)
        self.assertEqual(data['points_dropped'], 2)
        self.assertEqual(data['matches_led'], 1)

    def test_partial_events_do_not_change_result_metrics(self):
        f = fixture()
        data = summarize_team([f], {}, 1)
        self.assertEqual(data['results_matches'], 1)
        self.assertEqual(data['timeline_matches'], 0)
        self.assertEqual(data['splits']['all']['wins'], 1)
        self.assertIsNone(data['points_gained'])
        self.assertEqual(data['goal_intervals'], [])

    def test_away_perspective_and_last_five(self):
        fixtures = [fixture(fixture_id=i, match_date=datetime(2024, 8, i, tzinfo=timezone.utc)) for i in range(1, 8)]
        data = summarize_team(fixtures, {}, 2)
        self.assertEqual(data['splits']['away']['losses'], 7)
        self.assertEqual(data['splits']['home']['matches'], 0)
        self.assertEqual(data['splits']['last5']['matches'], 5)
        self.assertEqual(data['splits']['last10']['matches'], 7)


class WeatherImportTests(unittest.TestCase):
    def sample(self):
        return {'hourly': {'time': ['2024-08-01T19:00', '2024-08-01T20:00'],
                          'temperature_2m': [18, 17], 'precipitation': [0, 1],
                          'wind_speed_10m': [10, None], 'weather_code': [0, 1]}}

    def test_nearest_hour_and_half_hour_tie(self):
        sampled, values = weather_sample(self.sample(), datetime(2024, 8, 1, 19, 30, tzinfo=timezone.utc))
        self.assertEqual(sampled.hour, 19)
        self.assertEqual(values['precipitation'], 0)

    def test_missing_values_are_not_zero(self):
        _, values = weather_sample(self.sample(), datetime(2024, 8, 1, 20, tzinfo=timezone.utc))
        self.assertIsNone(values['wind_speed_10m'])

    def test_wrong_day_and_nonfinite_values_rejected(self):
        with self.assertRaises(ValueError):
            weather_sample(self.sample(), datetime(2024, 8, 2, tzinfo=timezone.utc))
        data = self.sample(); data['hourly']['temperature_2m'][0] = float('nan')
        with self.assertRaises(ValueError):
            weather_sample(data, datetime(2024, 8, 1, 19, tzinfo=timezone.utc))

    def test_source_url_requires_http_and_no_credentials(self):
        self.assertEqual(source_url('https://example.org/report'), 'https://example.org/report')
        for url in ['javascript:alert(1)', 'file:///tmp/data', 'https://secret:token@example.org']:
            with self.assertRaises(ValueError): source_url(url)
