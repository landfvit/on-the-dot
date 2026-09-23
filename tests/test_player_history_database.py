"""Read-only checks for the player history HTTP contract and real multi-club data."""
import os
import unittest
from fastapi.testclient import TestClient

from api.main import app
from api.database import get_connection


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST') == '1', 'Set TRIVIA_DB_TEST=1 for local PostgreSQL checks')
class PlayerHistoryDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_rashford_2024_counts_appearances_not_all_performance_rows(self):
        response = self.client.get('/api/players/909/history')
        self.assertEqual(response.status_code, 200)
        season = next(s for s in response.json()['seasons'] if s['season'] == 2024 and s['league_id'] == 39)
        self.assertEqual(season['appearances'], 25)
        self.assertEqual(season['verified_appearances'], 25)
        self.assertEqual(season['rated_matches'], 25)
        self.assertEqual(season['goals'], 6)
        self.assertEqual(season['assists'], 4)
        self.assertEqual(season['rating'], 6.94)
        self.assertEqual({r['team_id']: r['appearances'] for r in season['clubs']}, {33: 15, 66: 10})
        with get_connection() as conn:
            raw = conn.execute('''SELECT COUNT(*) AS n FROM fixture_player_statistics p JOIN fixtures f USING(fixture_id)
                WHERE p.player_id=909 AND f.season=2024 AND f.league_id=39''').fetchone()['n']
        self.assertGreater(raw, season['appearances'])

    def test_transfer_history_keeps_foreign_clubs_and_logos(self):
        response = self.client.get('/api/players/1485/history')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        names = {r['club']['name'] for r in data['clubs']}
        self.assertTrue({'Manchester United', 'Sporting CP', 'Sampdoria', 'Udinese', 'Novara'} <= names)
        self.assertTrue(all(row['club']['logo_url'] for row in data['clubs']))
        self.assertEqual(data['transfer_import']['status'], 'success')

    def test_missing_player_is_404_and_new_tabs_preserve_overview(self):
        self.assertEqual(self.client.get('/api/players/987654321/history').status_code, 404)
        response = self.client.get('/players/909?season=2024')
        self.assertEqual(response.status_code, 200)
        for ident in ['player-panel-overview', 'player-panel-seasons', 'player-panel-clubs',
                      'player-panel-transfers', 'player-team-statistics', 'market-value-dialog']:
            self.assertIn(f'id="{ident}"', response.text)
