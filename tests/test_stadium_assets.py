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
                self.assertNotIn('stadium-exit', response.text)
                self.assertNotIn('stadium-return', response.text)
                self.assertNotIn('class="penalty-stage"', response.text)
                self.assertNotIn('2D view', response.text)
                self.assertIn('id="stadium-unavailable"', response.text)
                self.assertNotIn('cdn.jsdelivr', response.text)

    def test_only_explicitly_allowed_game_assets_are_public(self):
        client = TestClient(app)
        for filename in ('stadium.css', 'stadium_intro.js', 'stadium_scene.js', 'stadium_config.js', 'stadium_v6_world.js', 'stadium_motion.js', 'points_theme.css', 'penalty_shots.js', 'result_share.js', 'icons/copy.svg', 'icons/download.svg',
                         'vendor/three/three.module.min.js', 'vendor/three/three.core.min.js', 'vendor/three/LICENSE'):
            with self.subTest(filename=filename):
                self.assertEqual(client.get('/trivia-assets/' + filename).status_code, 200)
        self.assertNotEqual(client.get('/trivia-assets/writer.js').status_code, 200)
        self.assertNotEqual(client.get('/trivia-assets/bank.js').status_code, 200)
