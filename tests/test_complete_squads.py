import sqlite3
import unittest
from unittest.mock import patch

from api.main import get_team_players


class CompleteSquadTests(unittest.TestCase):
    def test_roster_includes_unused_and_statistics_only_players_without_duplicates(self):
        connection = sqlite3.connect(':memory:')
        connection.row_factory = sqlite3.Row
        self.addCleanup(connection.close)
        connection.executescript('''
            CREATE TABLE teams (team_id INTEGER, team_name TEXT);
            INSERT INTO teams VALUES (33, 'Manchester United');
            CREATE TABLE players (player_id INTEGER, player_name TEXT, first_name TEXT,
                last_name TEXT, birth_date TEXT, nationality TEXT, height_cm INTEGER,
                weight_kg INTEGER, photo_url TEXT);
            CREATE TABLE squad_memberships (league_id INTEGER, season INTEGER, team_id INTEGER,
                player_id INTEGER, squad_number INTEGER, position TEXT, age INTEGER, photo_url TEXT);
        ''')
        stats = 'league_id season team_id player_id squad_number position appearances lineups minutes rating goals_total assists shots_total shots_on_goal passes_total key_passes pass_accuracy tackles_total blocks interceptions duels_total duels_won yellow_cards red_cards'.split()
        connection.execute('CREATE TABLE player_season_statistics (' + ','.join(stats) + ')')
        for ident, name in [(1, 'Starter'), (2, 'Unused keeper'), (3, 'Roster only'), (4, 'Stats only'), (5, 'Previous season')]:
            connection.execute('INSERT INTO players (player_id, player_name) VALUES (?,?)', (ident, name))
        for ident in (1, 2, 3, 5):
            connection.execute('INSERT INTO squad_memberships VALUES (39,?,33,?,?,?,20,?)',
                               (2025 if ident == 5 else 2026, ident, ident, 'Goalkeeper', 'photo.png'))
        for ident, appearances in ((1, 4), (2, 0), (4, 1)):
            connection.execute('INSERT INTO player_season_statistics (league_id,season,team_id,player_id,appearances,minutes) VALUES (39,2026,33,?,?,?)',
                               (ident, appearances, appearances * 90))

        def fetch_all(sql, params):
            return [dict(row) for row in connection.execute(sql.replace('%s', '?'), params)]

        def fetch_one(sql, params):
            return dict(connection.execute(sql.replace('%s', '?'), params).fetchone())

        with patch('api.main.fetch_all', side_effect=fetch_all), patch('api.main.fetch_one', side_effect=fetch_one):
            result = get_team_players(33, 2026)
        players = {p['player_id']: p for p in result['players']}
        self.assertEqual(set(players), {1, 2, 3, 4})
        self.assertEqual(result['count'], 4)
        self.assertEqual(players[2]['appearances'], 0)
        self.assertTrue(players[2]['statistics_available'])
        self.assertIsNone(players[3]['appearances'])
        self.assertFalse(players[3]['statistics_available'])
        self.assertEqual(players[3]['position'], 'Goalkeeper')
