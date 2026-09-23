"""Opt-in integration tests. All question writes are rolled back."""
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import trivia
from api.database import get_connection
from api.trivia_models import EvaluationRequest, GradeAnswer, SaveQuestion
from api.main import app


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST') == '1', 'Set TRIVIA_DB_TEST=1 for rollback-only PostgreSQL tests')
class TriviaDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_connection()
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)

        @contextmanager
        def shared():
            yield self.conn

        self.mock = patch('api.trivia.get_connection', shared)
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.spec = {'template': 'win_rate', 'league_id': 39, 'team_id': 33,
                     'period': {'mode': 'seasons', 'seasons': [2024]}, 'minimum_sample': 10}

    def test_save_publish_grade_and_immutable_revision(self):
        data = trivia.preview(EvaluationRequest(specification=self.spec))
        self.assertEqual(data['answer']['denominator'], 38)
        self.assertEqual(data['coverage']['excluded_matches'], 0)
        saved = trivia.save(SaveQuestion(specification=self.spec, dataset_id=data['dataset_id']))
        original = trivia.question(saved['version_id'])
        self.assertEqual(len(original['evidence']), 38)
        trivia.publish(saved['version_id'])
        self.assertTrue(trivia.grade(saved['version_id'], GradeAnswer(value=data['answer']['value']))['correct'])
        next_spec = {**self.spec, 'template': 'total_goals'}
        newer = trivia.save(SaveQuestion(specification=next_spec, question_id=saved['question_id'], dataset_id=data['dataset_id']))
        self.assertEqual(newer['revision'], 2)
        self.assertNotEqual(newer['version_id'], saved['version_id'])
        self.assertEqual(trivia.question(saved['version_id'])['answer'], original['answer'])
        self.assertEqual(trivia.question(saved['version_id'])['state'], 'published')

    def test_requested_missing_season_is_not_silently_removed(self):
        with self.assertRaises(HTTPException) as error:
            trivia.preview(EvaluationRequest(specification={**self.spec, 'period': {'mode': 'seasons', 'seasons': [1900, 2024]}}))
        self.assertEqual(error.exception.status_code, 422)

    def test_empty_range_is_unavailable_and_cannot_publish(self):
        spec = {**self.spec, 'period': {'mode': 'dates', 'start': '1900-01-01', 'end': '1900-12-31'}}
        saved = trivia.save(SaveQuestion(specification=spec))
        self.assertIsNone(trivia.question(saved['version_id'])['answer']['value'])
        with self.assertRaises(HTTPException) as error:
            trivia.publish(saved['version_id'])
        self.assertEqual(error.exception.status_code, 409)

    def test_conditional_query_returns_evidence_and_explicit_exclusions(self):
        spec = {**self.spec, 'template': 'conditional_win_rate', 'condition': {'minute': 80, 'goal_difference': -2}}
        data = trivia.preview(EvaluationRequest(specification=spec))
        self.assertEqual(len(data['evidence']), 38)
        self.assertEqual(len({r['fixture_id'] for r in data['evidence']}), 38)
        for row in data['evidence']:
            if row['disposition'] == 'matched':
                self.assertEqual(row['checkpoint_for'] - row['checkpoint_against'], -2)

    def test_date_range_and_noncontiguous_selection_are_exact(self):
        dated = trivia.preview(EvaluationRequest(specification={**self.spec,
            'period': {'mode': 'dates', 'start': '2024-09-01', 'end': '2024-09-30'}}))
        self.assertTrue(dated['evidence'])
        self.assertTrue(all(str(row['match_date']).startswith('2024-09') for row in dated['evidence']))
        selected = trivia.preview(EvaluationRequest(specification={**self.spec,
            'period': {'mode': 'seasons', 'seasons': [2020, 2024]}}))
        self.assertEqual({row['season'] for row in selected['evidence']}, {2020, 2024})
        self.assertEqual(len(selected['evidence']), 76)

    def test_public_questions_exclude_drafts_and_answers(self):
        saved = trivia.save(SaveQuestion(specification=self.spec))
        client = TestClient(app)
        data = client.get('/api/trivia/play/questions?limit=100').json()
        self.assertNotIn(str(saved['version_id']), [r['version_id'] for r in data['questions']])
        trivia.publish(saved['version_id'])
        draft = trivia.save(SaveQuestion(specification=self.spec, question_id=saved['question_id']))
        response = client.get('/api/trivia/play/questions?limit=100')
        questions = response.json()['questions']
        row = next(r for r in questions if r['version_id'] == str(saved['version_id']))
        self.assertEqual(set(row), {'version_id', 'question_text', 'answer_kind'})
        self.assertNotIn(str(draft['version_id']), [r['version_id'] for r in questions])
        self.assertEqual(response.headers['cache-control'], 'no-store')
        result = client.post(f"/api/trivia/questions/{saved['version_id']}/grade", json={'value': 28.9})
        self.assertTrue(result.json()['correct'])
        self.assertEqual(client.post(f"/api/trivia/questions/{draft['version_id']}/grade", json={'value': 28.9}).status_code, 409)
        self.assertEqual(client.get('/api/trivia/play/questions?limit=101').status_code, 422)
