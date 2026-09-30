"""The public rulebook must agree with the live engine, without needing a DB."""
import unittest
from html.parser import HTMLParser
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
        for value in ('example-early', 'example-last', 'example-sudden', '15 seconds per answer', 'Win multiplier'):
            self.assertIn(value, response.text)
        for slot in ('sidebar-left', 'sidebar-right'):
            self.assertIn(f'data-ad-slot="{slot}" aria-label="Advertisement" hidden', response.text)
        self.assertNotIn('adsbygoogle', response.text)
        self.assertNotIn('stadium_intro.js', response.text)
        self.assertNotIn('id="stadium-layer"', response.text)

    def test_team_and_progress_copy_matches_current_capabilities(self):
        html = TestClient(app).get('/how-to-play').text
        for text in ('no gameplay bonuses', 'contribute your stats to the team leaderboard',
                     'change teams once every 3 days',
                     'Solo and Friend Duels need no account', "Monday's reset",
                     'Finish Solo or Daily with no timeouts', 'Ending a shootout early counts as a loss',
                     'Only your first attempt each day counts', 'Later games are practice',
                     'leaderboard tracks your best score ever', 'three lives'):
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

    def test_kit_guide_explains_own_team_number_and_role(self):
        html = TestClient(app).get('/how-to-play').text
        for text in ('Your kit and number', "your team's available kits", 'shirt number from 1 to 99',
                     'The taker wears your kit when you shoot', 'The goalkeeper wears it when you save',
                     'each player wears their own choice', "new club's home kit",
                     'Your shirt number stays the same'):
            self.assertIn(text, html)

    def test_game_selection_only_offers_difficulty_and_no_question_counts(self):
        html = TestClient(app).get('/penalties').text
        self.assertEqual(html.count('name="difficulty"'), 3)
        for removed in ('id="topic"', 'id="category"', '-available', 'Loading categories', 'Loading teams'):
            self.assertNotIn(removed, html)
        self.assertIn('id="add-team"', TestClient(app).get('/account').text)

    def test_all_guide_assets_are_public(self):
        client = TestClient(app)
        for path in ('game_guide.css', 'game_guide.js', 'guide/shooter.png', 'guide/keeper.png',
                     'guide/kit-home.png', 'guide/kit-away.png', 'guide/kit-third.png',
                     'guide/kit-number.png', 'icons/circle-help.svg'):
            response = client.get('/trivia-assets/' + path)
            self.assertEqual(response.status_code, 200, path)
        self.assertEqual(client.get('/trivia-assets/guide/shooter.png').content[:8], b'\x89PNG\r\n\x1a\n')

    def test_illustrated_steps_and_game_intro_use_current_assets(self):
        client = TestClient(app)
        html = client.get('/how-to-play').text
        for value in ('guide-club-example', 'guide-kit-example', 'guide-daily-example',
                      'Join team', 'Save kit', 'Next penalty', '360 XP',
                      'shirt number from 1 to 99', 'the third mistake'):
            self.assertIn(value.lower(), html.lower())
        for url in ('guide/shooter.png?v=6', 'guide/keeper.png?v=6'):
            self.assertIn(url, html)
            self.assertIn(url, client.get('/penalties').text)

    def test_guide_prose_avoids_symbol_shorthand(self):
        class GuideText(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_guide = False
                self.parts = []

            def handle_starttag(self, tag, attrs):
                if tag == 'main' and 'game-guide' in dict(attrs).get('class', '').split():
                    self.in_guide = True
                if self.in_guide:
                    self.parts.extend(value for key, value in attrs if key in ('alt', 'aria-label') and value)

            def handle_endtag(self, tag):
                if tag == 'main':
                    self.in_guide = False

            def handle_data(self, data):
                if self.in_guide:
                    self.parts.append(data)

        copy = GuideText()
        copy.feed(TestClient(app).get('/how-to-play').text)
        self.assertTrue(copy.parts)
        self.assertNotRegex(' '.join(copy.parts), r'[;:\-/+=&\u2010-\u2015\u00b7\u00d7\u2192]')
