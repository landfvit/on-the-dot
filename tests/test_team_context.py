import unittest
from datetime import date
from unittest.mock import Mock, patch

from fastapi import HTTPException

from api.team_context import get_team_context
from src.entity_history_import import import_coach


class TeamContextTests(unittest.TestCase):
    @patch('api.team_context.fetch_one', return_value={'first_match': None})
    @patch('api.team_context.fetch_all')
    def test_unknown_season_does_not_use_current_team_data(self, query, _):
        with self.assertRaises(HTTPException) as error:
            get_team_context(33, 1900)
        self.assertEqual(error.exception.status_code, 404)
        query.assert_not_called()

    @patch('api.team_context.fetch_one', return_value={'first_match': date(2024, 8, 1), 'last_match': date(2025, 5, 31)})
    @patch('api.team_context.fetch_all')
    def test_match_evidence_is_season_scoped_and_keeps_multiple_coaches(self, query, _):
        venue = {'venue_name': 'Goodison Park', 'capacity': 40569}
        coaches = [{'coach_id': 1, 'matches': 28}, {'coach_id': 2, 'matches': 10}]
        query.side_effect = [[venue], coaches]
        result = get_team_context(45, 2024)
        self.assertEqual(result['venue'], venue)
        self.assertEqual(result['coaches'], coaches)
        self.assertEqual(result['coach_source'], 'lineups')
        for call in query.call_args_list:
            sql, params = call.args
            self.assertEqual(params, (39, 2024, 45))
            self.assertIn('f.season=%s', sql)
        self.assertIn('f.match_date <= CURRENT_TIMESTAMP', query.call_args_list[1].args[0])

    @patch('api.team_context.fetch_one', return_value={'first_match': date(2026, 8, 1), 'last_match': date(2027, 5, 31)})
    @patch('api.team_context.fetch_all')
    def test_missing_match_ground_uses_only_same_season_snapshot(self, query, _):
        query.side_effect = [[], [{'venue_name': 'New stadium'}], [{'coach_id': 1}]]
        result = get_team_context(45, 2026)
        self.assertEqual(result['venue']['venue_name'], 'New stadium')
        sql, params = query.call_args_list[1].args
        self.assertIn('s.season=%s', sql)
        self.assertEqual(params, (39, 2026, 45))

    @patch('api.team_context.fetch_one', return_value={'first_match': date(2012, 8, 1), 'last_match': date(2013, 5, 31)})
    @patch('api.team_context.fetch_all')
    def test_missing_data_stays_unavailable_and_careers_require_date_overlap(self, query, _):
        query.side_effect = [[], [], [], []]
        result = get_team_context(33, 2012)
        self.assertIsNone(result['venue'])
        self.assertEqual(result['coaches'], [])
        sql, params = query.call_args_list[-1].args
        self.assertIn('cc.start_date <= LEAST(%s, CURRENT_DATE)', sql)
        self.assertIn('cc.end_date >= %s', sql)
        self.assertEqual(params, (33, date(2013, 5, 31), date(2012, 8, 1)))

    def test_empty_or_wrong_coach_response_preserves_database_history(self):
        for payload in ({'response': []}, {'response': [{'id': 2}]}):
            connection = Mock()
            with self.assertRaises(ValueError):
                import_coach(connection, Mock(), 1, payload)
            connection.execute.assert_not_called()
            connection.transaction.assert_not_called()
