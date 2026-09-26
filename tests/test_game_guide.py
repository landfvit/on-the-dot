"""The public rulebook must agree with the live engine, without needing a DB."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.solo_engine import RULES
from trivia_app.game_guide import guide_context
from trivia_app.main import app


class GameGuideTests(unittest.TestCase):
    def test_examples_follow_real_early_finish_and_equal_kicks_rules(self):
        early, last, sudden = guide_context()['examples']
        self.assertEqual((early['score']['player'], early['score']['opponent']), (3, 0))
        self.assertEqual(early['score']['winner'], 'player')
        self.assertEqual(early['rows']['player'], [True, True, True, None, None])
        self.assertEqual((last['score']['player'], last['score']['opponent']), (5, 4))
        self.assertIsNone(last['score']['winner'])
        self.assertIsNone(last['rows']['opponent'][-1])
        self.assertEqual((sudden['score']['player'], sudden['score']['opponent']), (6, 5))
        self.assertEqual(sudden['score']['kicks'], {'player': 6, 'opponent': 6})
        self.assertEqual(sudden['score']['winner'], 'player')

    def test_rewards_use_live_rates_and_do_not_require_a_perfect_game(self):
        context = guide_context()
        self.assertEqual(context['rules'], RULES)
        reward = context['reward_example']
        self.assertTrue(reward['won'])
        self.assertFalse(reward['perfect'])
        self.assertEqual(reward['correct'], 6)
        self.assertEqual(reward['total_xp'], 6 * RULES['xp_by_difficulty']['medium'] * RULES['win_multipliers']['medium'])
        context['rules']['xp_by_difficulty']['easy'] = -1
        self.assertGreater(RULES['xp_by_difficulty']['easy'], 0)

    def test_public_page_is_read_only_and_all_examples_exist_without_javascript(self):
        with patch('psycopg.connect', side_effect=AssertionError('Rulebook must not connect to DB')):
            response = TestClient(app).get('/how-to-play')
        self.assertEqual(response.status_code, 200)
        for value in ('example-early', 'example-last', 'example-sudden', '15 seconds / answer', 'Win multiplier'):
            self.assertIn(value, response.text)
        for slot in ('sidebar-left', 'sidebar-right'):
            self.assertIn(f'data-ad-slot="{slot}" aria-label="Advertisement" hidden', response.text)
        self.assertNotIn('adsbygoogle', response.text)
        self.assertNotIn('stadium_intro.js', response.text)
        self.assertNotIn('id="stadium-layer"', response.text)

    def test_team_and_progress_copy_matches_current_capabilities(self):
        html = TestClient(app).get('/how-to-play').text
        for text in ('No gameplay bonuses', 'contribute your stats to the team leaderboard',
                     'change teams once every 3 days',
                     'Solo and Friend Duels need no account', "Monday's reset",
                     'Finish Solo or Daily with no timeouts', 'Ending a shootout early counts as a loss',
                     'Only your first attempt each day counts', 'Later games are practice',
                     'leaderboard tracks your all-time best', 'Three lives'):
            self.assertIn(text, html)
        self.assertIn('/how-to-play#teams', TestClient(app).get('/account').text)
        self.assertIn('class="game-rules-link"', TestClient(app).get('/penalties').text)

    def test_guide_and_guest_home_explain_difficulty_only_selection(self):
        client = TestClient(app)
        for path in ('/how-to-play',):
            with self.subTest(path=path):
                html = client.get(path).text
                self.assertIn('Choose Easy, Medium or Hard,', html)
                self.assertIn('with mixed teams and topics', html)
                self.assertNotIn('Team / scope', html)
                self.assertNotIn('Question availability:', html)

    def test_game_selection_only_offers_difficulty_and_no_question_counts(self):
        html = TestClient(app).get('/penalties').text
        self.assertEqual(html.count('name="difficulty"'), 3)
        for removed in ('id="topic"', 'id="category"', '-available', 'Loading categories', 'Loading teams'):
            self.assertNotIn(removed, html)
        self.assertIn('id="add-team"', TestClient(app).get('/account').text)

    def test_all_guide_assets_are_public(self):
        client = TestClient(app)
        for path in ('game_guide.css', 'game_guide.js', 'guide/shooter.png', 'guide/keeper.png', 'icons/circle-help.svg'):
            response = client.get('/trivia-assets/' + path)
            self.assertEqual(response.status_code, 200, path)
        self.assertEqual(client.get('/trivia-assets/guide/shooter.png').content[:8], b'\x89PNG\r\n\x1a\n')
