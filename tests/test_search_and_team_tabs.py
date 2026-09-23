import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader

from api.main import app


class SearchAndTeamTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch('api.main.fetch_all')
    def test_short_query_does_not_query_database(self, query):
        response = self.client.get('/api/search', params={'q': ' a '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 0)
        query.assert_not_called()

    @patch('api.main.fetch_all')
    def test_search_has_consistent_groups_and_safe_query_parameters(self, query):
        team = dict(team_id=63, team_name='Leeds', team_code='LEE', country_name='England',
                    country_code='GB-ENG', flag_url='flag.svg', logo_url='leeds.png', season=2026)
        query.side_effect = [[], [team], []]
        response = self.client.get('/api/search', params={'q': "Leeds'"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['groups']['teams'][0]['url'], '/teams/63?season=2026')
        self.assertEqual(data['groups']['teams'][0]['image_url'], 'leeds.png')
        for call in query.call_args_list:
            sql, params = call.args
            self.assertEqual(sql.count('%s'), len(params))
            self.assertNotIn("Leeds'", sql)
        self.assertIn('CONCAT_WS', query.call_args_list[2].args[0])

    @patch('api.main.fetch_one', return_value={'team_id': 63})
    @patch('api.main.fetch_all', side_effect=[[{'fixture_id': 1}], [{'fixture_id': 2}]])
    def test_team_lists_recent_and_upcoming_separately(self, query, _):
        response = self.client.get('/api/teams/63?season=2026')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['recent_matches'][0]['fixture_id'], 1)
        self.assertEqual(data['upcoming_matches'][0]['fixture_id'], 2)
        recent, upcoming = [call.args[0] for call in query.call_args_list]
        self.assertIn('LIMIT 10', recent)
        self.assertIn('fds.season <= %s', recent)
        self.assertIn("('FT', 'AET', 'PEN')", recent)
        self.assertIn("('NS', 'TBD')", upcoming)
        self.assertIn('f.match_date >= CURRENT_TIMESTAMP', upcoming)

    def test_template_wires_search_and_defaults_to_recent_matches(self):
        root = Path(__file__).resolve().parents[1]
        env = Environment(loader=FileSystemLoader(root / 'web/templates'))
        html = env.get_template('team.html').render(team_id=63, season=2026, sport='football')
        for element in ('global-search-button', 'global-search-overlay', 'global-search-input', 'global-search-content', 'global-search-close'):
            self.assertIn(f'id="{element}"', html)
        self.assertIn('/assets/js/global_search.js', html)
        self.assertIn('/assets/css/global_search.css', html)
        self.assertIn('id="tab-recent" aria-controls="panel-recent" aria-selected="true"', html)
        self.assertIn('data-entity-preview="disabled"', html)
        for name in ('recent', 'upcoming', 'stats', 'squad', 'kits'):
            self.assertIn(f'id="panel-{name}"', html)
