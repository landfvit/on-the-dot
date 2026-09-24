"""The redesigned home is a public mode selector, never an auth shortcut."""
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from api.player_accounts import COOKIE
from trivia_app.main import app


class HomePageTests(unittest.TestCase):
    def test_home_is_the_same_read_only_selector_for_every_session(self):
        for cookies in ({}, {'points_trial':'guest'}, {COOKIE:'valid-session'}, {COOKIE:'x'*101}):
            with self.subTest(cookies=cookies), patch('trivia_app.main.get_connection') as connection:
                response=TestClient(app,cookies=cookies).get('/')
                self.assertEqual(response.status_code,200)
                self.assertIn('class="play-button"',response.text)
                for path in ('/penalties','/daily','/friends','/how-to-play','/leaderboard','/account','/history'):
                    self.assertIn(f'href="{path}"',response.text)
                self.assertNotIn('stadium_intro.js',response.text)
                self.assertNotIn('id="stadium-layer"',response.text)
                self.assertNotIn('set-cookie',response.headers)
                connection.assert_not_called()

    def test_home_has_meaningful_rules_without_javascript(self):
        html=TestClient(app).get('/').text
        for text in ('Take your shot.','Make the save.','Win the shootout.','15 seconds per answer','Full rules'):
            self.assertIn(text,html)

    def test_explicit_game_and_guide_urls_remain_public(self):
        with patch('trivia_app.main.get_connection') as connection:
            client=TestClient(app,cookies={COOKIE:'unknown-session'})
            self.assertIn('<h1>Penalties</h1>',client.get('/penalties').text)
            self.assertIn('<h1>How to play</h1>',client.get('/how-to-play').text)
            connection.assert_not_called()

    def test_new_assets_are_public_without_exposing_editor_files(self):
        client=TestClient(app)
        for name in ('home.css','home.js','redesign.css','stadium_crowd.js','crowd_reaction.js','brand/logo.svg'):
            self.assertEqual(client.get('/trivia-assets/'+name).status_code,200,name)
        self.assertNotEqual(client.get('/trivia-assets/writer.js').status_code,200)
