import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


class TriviaAccessTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {'TRIVIA_EDITOR_USERNAME': '', 'TRIVIA_EDITOR_PASSWORD': ''})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_public_page_has_no_editor(self):
        response = self.client.get('/trivia')
        self.assertEqual(response.status_code, 200)
        self.assertIn('play-form', response.text)
        self.assertNotIn('trivia-form', response.text)
        self.assertNotIn('internal/trivia', response.text)
        self.assertEqual(self.client.get('/static/templates/trivia.html').status_code, 404)

    def test_private_routes_fail_closed_without_configuration(self):
        with patch('api.trivia.get_connection', side_effect=AssertionError('Must not read database')):
            for method, route in [
                ('GET', '/internal/trivia'), ('GET', '/api/trivia/metadata'),
                ('GET', '/api/trivia/questions'), ('POST', '/api/trivia/questions'),
                ('POST', '/api/trivia/evaluate'),
                ('GET', '/api/trivia/questions/00000000-0000-0000-0000-000000000001'),
                ('POST', '/api/trivia/questions/00000000-0000-0000-0000-000000000001/publish'),
            ]:
                with self.subTest(route=route, method=method):
                    self.assertEqual(self.client.request(method, route, json={}).status_code, 404)

    def test_authentication_and_no_cache(self):
        with patch.dict(os.environ, {'TRIVIA_EDITOR_USERNAME': 'editor', 'TRIVIA_EDITOR_PASSWORD': 'a-long-test-password'}):
            self.assertEqual(self.client.get('/internal/trivia').status_code, 401)
            self.assertEqual(self.client.get('/internal/trivia', auth=('editor', 'wrong')).status_code, 401)
            response = self.client.get('/internal/trivia', auth=('editor', 'a-long-test-password'))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertIn('trivia-form', response.text)

    def test_editor_rejects_cross_origin_posts(self):
        with patch.dict(os.environ, {'TRIVIA_EDITOR_USERNAME': 'editor', 'TRIVIA_EDITOR_PASSWORD': 'a-long-test-password'}):
            for headers in [{'Origin': 'https://attacker.example'}, {'Sec-Fetch-Site': 'cross-site'}]:
                response = self.client.post('/api/trivia/evaluate', auth=('editor', 'a-long-test-password'), headers=headers, json={})
                self.assertEqual(response.status_code, 403)

    def test_short_password_does_not_enable_editor(self):
        with patch.dict(os.environ, {'TRIVIA_EDITOR_USERNAME': 'editor', 'TRIVIA_EDITOR_PASSWORD': 'short'}):
            self.assertEqual(self.client.get('/internal/trivia', auth=('editor', 'short')).status_code, 404)
