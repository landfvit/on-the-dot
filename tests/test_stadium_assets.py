import unittest

from fastapi.testclient import TestClient
from trivia_app.main import app


class StadiumAssetsTests(unittest.TestCase):
    def test_scene_is_in_public_solo_routes(self):
        client = TestClient(app)
        for path in ('/penalties', '/solo'):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn('id="stadium-layer"', response.text)
                self.assertIn('stadium_intro.js', response.text)
                self.assertIn('stadium.css', response.text)
                self.assertIn('stadium_inline.css', response.text)
                self.assertIn('class="stadium-inline"', response.text)
                self.assertIn('id="stadium-stage"', response.text)
                self.assertEqual(response.text.count('data-theme-toggle'), 1)
                self.assertEqual(response.text.count('data-sound-toggle'), 1)
                self.assertEqual(response.text.count('id="motion-toggle"'), 1)
                self.assertNotIn('stadium-exit', response.text)
                self.assertNotIn('stadium-return', response.text)
                self.assertNotIn('class="penalty-stage"', response.text)
                self.assertNotIn('2D view', response.text)
                self.assertIn('id="stadium-unavailable"', response.text)
                self.assertIn('id="stadium-retry"', response.text)
                self.assertNotIn('cdn.jsdelivr', response.text)

    def test_only_explicitly_allowed_game_assets_are_public(self):
        client = TestClient(app)
        for filename in ('stadium.css', 'stadium_inline.css', 'stadium_intro.js', 'stadium_scene.js', 'stadium_config.js', 'stadium_v6_world.js', 'stadium_motion.js', 'points_theme.css', 'penalty_shots.js', 'result_share.js', 'solo_results.css', 'icons/copy.svg', 'icons/download.svg',
                         'kit_pixels.js','player_kit.js','player_kit.css','player-kits/catalog.json','question_text.js',
                         'vendor/three/three.module.min.js', 'vendor/three/three.core.min.js', 'vendor/three/LICENSE'):
            with self.subTest(filename=filename):
                self.assertEqual(client.get('/trivia-assets/' + filename).status_code, 200)
        self.assertNotEqual(client.get('/trivia-assets/writer.js').status_code, 200)
        self.assertNotEqual(client.get('/trivia-assets/bank.js').status_code, 200)

    def test_retry_namespace_serves_the_same_public_dependency_graph(self):
        client=TestClient(app)
        for filename in ('stadium_scene.js','stadium_config.js','stadium_v6_world.js',
                         'stadium_motion.js','crowd_reaction.js','kit_pixels.js','vendor/three/three.module.min.js',
                         'vendor/three/three.core.min.js'):
            with self.subTest(filename=filename):
                original=client.get('/trivia-assets/'+filename)
                retry=client.get('/trivia-assets/_retry/2/'+filename)
                self.assertEqual(retry.status_code,200)
                self.assertEqual(retry.content,original.content)
                self.assertEqual(retry.headers['content-type'],original.headers['content-type'])
        for path in ('_retry/2/writer.js','_retry/2/bank.js','_retry/2/../writer.js',
                     '_retry/2/%2e%2e%2fwriter.js','_retry/0/stadium_scene.js','_retry/no/stadium_scene.js'):
            self.assertNotEqual(client.get('/trivia-assets/'+path).status_code,200)
