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
                for path in ('/penalties','/how-to-play','/leaderboard','/account','/history'):
                    self.assertIn(f'href="{path}"',response.text)
                self.assertNotIn('stadium_intro.js',response.text)
                self.assertNotIn('id="stadium-layer"',response.text)
                self.assertNotIn('set-cookie',response.headers)
                connection.assert_not_called()

    def test_home_has_meaningful_rules_without_javascript(self):
        html=TestClient(app).get('/').text
        for text in ('Shoot.','Save.','Win!','Full rules'):
            self.assertIn(text,html)
        self.assertNotIn('class="step-index"',html)

    def test_play_has_no_mode_shortcuts_or_format_caption(self):
        html=TestClient(app).get('/').text
        self.assertNotIn('class="home-modes"',html)
        self.assertNotIn('class="match-format"',html)
        self.assertNotIn('15 seconds per answer',html)
        self.assertIn('id="tab-daily"',html)
        self.assertIn('id="tab-duel"',html)

    def test_explicit_game_and_guide_urls_remain_public(self):
        with patch('trivia_app.main.get_connection') as connection:
            client=TestClient(app,cookies={COOKIE:'unknown-session'})
            self.assertIn('<h1>Penalties</h1>',client.get('/penalties').text)
            self.assertIn('<h1>How to play</h1>',client.get('/how-to-play').text)
            connection.assert_not_called()

    def test_volume_is_only_in_account_settings_and_other_pages_use_mute(self):
        client=TestClient(app)
        for path in ('/','/penalties','/daily','/friends','/how-to-play','/leaderboard'):
            html=client.get(path).text
            self.assertIn('data-sound-toggle',html)
            self.assertNotIn('class="header-sound"',html)
            self.assertNotIn('data-sound-volume',html)
        html=client.get('/account').text
        self.assertIn('<summary>Sound</summary>',html)
        self.assertIn('data-sound-volume',html)

    def test_game_toolbar_replaces_duplicate_metadata_and_score(self):
        client=TestClient(app)
        for path in ('/penalties','/daily','/friends'):
            html=client.get(path).text
            self.assertIn('id="motion-toggle"',html)
            self.assertIn('icons/monitor.svg',html)
            self.assertIn('id="shootout-board"',html)
            hud=html.split('id="shootout-hud"',1)[1].split('<header class="solo-heading"',1)[0]
            self.assertIn('id="leave"',hud)
            self.assertIn('>Forfeit</button>',hud)
            self.assertEqual(html.count('id="leave"'),1)
            self.assertNotIn('id="leave"',html.split('id="question-panel"',1)[1])
            for old in ('class="run-meta"','id="run-xp"','id="run-category"','class="solo-score"','id="penalty-score"'):
                self.assertNotIn(old,html)
        self.assertNotIn('id="motion-toggle"',client.get('/').text)

    def test_ad_rails_are_prepared_without_including_accounts_or_tracking(self):
        client=TestClient(app)
        for path in ('/','/how-to-play','/penalties','/daily','/friends','/leaderboard'):
            html=client.get(path).text
            self.assertIn('data-ad-slot="sidebar-left"',html)
            self.assertIn('data-ad-slot="sidebar-right"',html)
            self.assertNotIn('adsbygoogle',html)
        for path in ('/account','/history'):
            self.assertNotIn('data-ad-slot="sidebar-left"',client.get(path).text)

    def test_new_assets_are_public_without_exposing_editor_files(self):
        client=TestClient(app)
        for name in ('home.css','home.js','redesign.css','theme.js','dark_mode.css','crowd_reaction.js','brand/logo.svg','icons/sun.svg','icons/moon.svg','icons/monitor.svg','icons/monitor-off.svg','profile.css','xp_progress.css','xp_progress.js'):
            self.assertEqual(client.get('/trivia-assets/'+name).status_code,200,name)
        self.assertNotEqual(client.get('/trivia-assets/writer.js').status_code,200)
