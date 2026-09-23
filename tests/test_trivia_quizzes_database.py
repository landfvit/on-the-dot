"""PostgreSQL lifecycle/authorization checks; every write rolls back."""
from contextlib import contextmanager
import os
import unittest
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

from api import trivia
from api.database import get_connection
from api.trivia_models import SaveQuestion
from trivia_app.main import app


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST') == '1', 'Set TRIVIA_DB_TEST=1')
class QuizDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_connection()
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        @contextmanager
        def shared():
            yield self.conn
        for target in ('api.trivia.get_connection', 'api.trivia_quizzes.get_connection'):
            patcher = patch(target, shared); patcher.start(); self.addCleanup(patcher.stop)
        env = patch.dict(os.environ, {'TRIVIA_EDITOR_USERNAME': 'editor', 'TRIVIA_EDITOR_PASSWORD': 'long-local-test-password'})
        env.start(); self.addCleanup(env.stop)
        self.client = TestClient(app)
        self.auth = ('editor', 'long-local-test-password')
        # Quiz play is now an editor-only preview; public play is penalties only.
        self.client.auth = self.auth
        self.spec = {'template': 'top_scorer', 'league_id': 39, 'team_id': 33,
                     'period': {'mode': 'seasons', 'seasons': [2017]}, 'minimum_sample': 1}

    def question(self, publish=True):
        saved = trivia.save(SaveQuestion(specification=self.spec))
        if publish:
            trivia.publish(saved['version_id'])
        return saved

    def quiz(self, questions):
        result = self.client.post('/api/trivia/quizzes', auth=self.auth,
            json={'title': 'Rollback-only test', 'question_versions': [str(q['version_id']) for q in questions]})
        self.assertEqual(result.status_code, 201, result.text)
        ident = result.json()['version_id']
        self.assertEqual(self.client.post(f'/api/trivia/quizzes/{ident}/publish', auth=self.auth).status_code, 200)
        return ident

    def start(self, quiz):
        result = self.client.post(f'/api/trivia/play/quizzes/{quiz}/attempts')
        self.assertEqual(result.status_code, 201, result.text)
        self.assertIn('HttpOnly', result.headers['set-cookie'])
        return result.json()

    def test_scorer_value_ranking_and_provenance_survive_save(self):
        q = trivia.question(self.question()['version_id'])
        self.assertEqual(q['answer']['value'], 16)
        self.assertEqual(q['answer']['unit'], 'goals')
        self.assertEqual(q['leaderboard'][0]['value'], 16)
        self.assertEqual(q['leaderboard'][1]['value'], 9)
        self.assertEqual(q['analysis']['seasons'][0]['fixtures'], 380)
        self.assertEqual(len(q['evidence']), 38)
        self.assertIsNotNone(q['verified_at'])

    def test_published_content_and_sealed_facts_cannot_change(self):
        q = trivia.question(self.question()['version_id'])
        for sql, params in [
            ("UPDATE trivia_question_versions SET answer='{}' WHERE version_id=%s", (q['version_id'],)),
            ('DELETE FROM trivia_evidence WHERE version_id=%s', (q['version_id'],)),
            ('UPDATE trivia_match_team_facts SET goals_for=99 WHERE dataset_id=%s', (q['dataset_id'],)),
        ]:
            with self.assertRaises(psycopg.errors.RaiseException):
                with self.conn.transaction():
                    self.conn.execute(sql, params)

    def test_drafts_cannot_enter_quiz(self):
        q = self.question(False)
        r = self.client.post('/api/trivia/quizzes', auth=self.auth,
            json={'title': 'Not publishable', 'question_versions': [str(q['version_id'])]})
        self.assertEqual(r.status_code, 409)

    def test_attempt_is_private_idempotent_and_graded_by_server(self):
        quiz = self.quiz([self.question()]); started = self.start(quiz)
        path = f"/api/trivia/attempts/{started['attempt_id']}"
        self.assertNotIn('answer', started['question'])
        self.assertNotIn('16', str(started['question']))
        self.assertEqual(TestClient(app).get(path).status_code, 401)
        self.assertEqual(TestClient(app).get(path,auth=self.auth).status_code, 404)
        submitted = self.client.post(path + '/answers/1', json={'text': 'Romelu Lukaku'})
        self.assertEqual(submitted.status_code, 200, submitted.text)
        data = submitted.json()
        self.assertTrue(data['correct'])
        self.assertEqual(data['attempt']['score'], 1)
        self.assertTrue(data['attempt']['finished'])
        again = self.client.post(path + '/answers/1', json={'text': 'Romelu Lukaku'})
        self.assertEqual(again.json()['attempt']['score'], 1)
        self.assertEqual(self.client.post(path + '/answers/1', json={'text': 'Martial'}).status_code, 409)
        self.assertEqual(self.client.get(path).json()['score'], 1)
        count = self.conn.execute('SELECT COUNT(*) n FROM trivia_attempt_answers WHERE attempt_id=%s', (started['attempt_id'],)).fetchone()['n']
        self.assertEqual(count, 1)

    def test_no_skipping_or_client_score_injection(self):
        quiz = self.quiz([self.question()]); started = self.start(quiz)
        path = f"/api/trivia/attempts/{started['attempt_id']}"
        self.assertEqual(self.client.post(path + '/answers/2', json={'text': 'Lukaku'}).status_code, 409)
        self.assertEqual(self.client.post(path + '/answers/1', json={'text': 'Lukaku', 'score': 10}).status_code, 422)
        self.assertEqual(self.client.get(path).json()['answered'], 0)

    def test_quiz_pins_question_revision(self):
        original = self.question(); quiz = self.quiz([original])
        newer = trivia.save(SaveQuestion(specification={**self.spec, 'template': 'total_goals'}, question_id=original['question_id']))
        trivia.publish(newer['version_id'])
        started = self.start(quiz)
        self.assertEqual(started['question']['answer_kind'], 'entity')

    def test_quiz_start_rejects_cross_origin(self):
        quiz = self.quiz([self.question()])
        r = self.client.post(f'/api/trivia/play/quizzes/{quiz}/attempts', headers={'Origin': 'https://untrusted.example'})
        self.assertEqual(r.status_code, 403)


class TriviaOnlyRoutesTests(unittest.TestCase):
    def test_form_login_logout_and_password_rotation(self):
        client = TestClient(app)
        with patch.dict(os.environ, {'TRIVIA_EDITOR_USERNAME': 'editor', 'TRIVIA_EDITOR_PASSWORD': 'long-local-test-password'}):
            self.assertEqual(client.get('/internal/trivia', follow_redirects=False).status_code, 303)
            result = client.post('/login', data={'username': 'editor', 'password': 'long-local-test-password'}, follow_redirects=False)
            self.assertEqual(result.status_code, 303)
            self.assertIn('httponly', result.headers['set-cookie'])
            self.assertEqual(client.get('/internal/trivia').status_code, 200)
            self.assertEqual(client.post('/logout', headers={'Origin': 'https://evil.example'}).status_code, 403)
            with patch.dict(os.environ, {'TRIVIA_EDITOR_PASSWORD': 'a-different-long-password'}):
                self.assertEqual(client.get('/internal/trivia', follow_redirects=False).status_code, 303)
            client.post('/logout')
            self.assertEqual(client.get('/internal/trivia', follow_redirects=False).status_code, 303)

    def test_no_football_pages_or_public_editor_link(self):
        client = TestClient(app)
        home = client.get('/')
        self.assertEqual(home.status_code, 200)
        self.assertIn('POINTS', home.text)
        self.assertNotIn('/internal/trivia', home.text)
        for path in ['/teams/33', '/matches/1', '/players/907', '/assets/../.env', '/static/templates/trivia.html']:
            self.assertEqual(client.get(path).status_code, 404)
