import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import sports_query_routes as routes, trivia
from api.database import get_connection
from api.sports_query import ParseRequest, SportsQuery
from api.trivia_models import EvaluationRequest, GradeAnswer, SaveQuestion
from trivia_app.main import app


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST') == '1', 'Opt-in rollback-only database tests')
class QueryDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_connection()
        self.addCleanup(self.conn.close); self.addCleanup(self.conn.rollback)

        @contextmanager
        def shared():
            yield self.conn

        for module in ['api.sports_query_routes', 'api.trivia']:
            mock = patch(module + '.get_connection', shared); mock.start(); self.addCleanup(mock.stop)
        self.client = TestClient(app)
        self.auth = (os.environ['TRIVIA_EDITOR_USERNAME'], os.environ['TRIVIA_EDITOR_PASSWORD'])

    def parse(self, text):
        return routes.parse(ParseRequest(text=text, competition_id=39))

    def test_big_six_matches_independent_sql_and_never_self(self):
        parsed = self.parse('Manchester United win rate against Big 6 last 10 seasons')
        query = SportsQuery(**parsed['query'])
        result = routes.run(query)
        expected = self.conn.execute('''SELECT COUNT(*) n, COUNT(*) FILTER(WHERE goals_for>goals_against) wins,
            COUNT(*) FILTER(WHERE goals_for=goals_against) draws, COUNT(*) FILTER(WHERE goals_for<goals_against) losses
            FROM trivia_match_team_facts WHERE dataset_id=%s AND league_id=39 AND team_id=33
                AND opponent_id=ANY(%s) AND season=ANY(%s) AND status='FT' ''',
            (query.dataset_id, [40,42,47,49,50], query.timeframe.seasons)).fetchone()
        self.assertEqual(result['summary']['played'], expected['n'])
        self.assertEqual(expected['n'], 100)
        for key in ['wins', 'draws', 'losses']:
            self.assertEqual(result['summary'][key], expected[key])
        self.assertTrue(all(r['opponent_id'] != 33 for r in result['evidence']))
        self.assertTrue(result['coverage']['publishable'])

    def test_decimal_question_save_publish_grade_retains_evidence(self):
        query = SportsQuery(**self.parse('Arsenal points per game away 2024/25')['query'])
        saved = trivia.save(SaveQuestion(specification=query.specification(), dataset_id=query.dataset_id))
        row = trivia.question(saved['version_id'])
        self.assertEqual(row['answer']['value'], 1.84)
        self.assertEqual(row['analysis']['summary']['played'], 19)
        trivia.publish(saved['version_id'])
        self.assertTrue(trivia.grade(saved['version_id'], GradeAnswer(value=1.84))['correct'])
        self.assertFalse(trivia.grade(saved['version_id'], GradeAnswer(value=1.8))['correct'])

    def test_group_cannot_be_forged_or_mutated(self):
        data = self.parse('Man Utd win rate against Big 6 last 10 seasons')['query']
        data['filters']['opponents']['team_ids'] = [42]
        with self.assertRaises(HTTPException):
            routes.run(SportsQuery(**data))
        with self.assertRaises(Exception), self.conn.transaction():
            self.conn.execute("UPDATE trivia_opponent_groups SET team_ids=ARRAY[33,42] WHERE group_key='big_6'")

    def test_legacy_answer_and_analysis_do_not_gain_new_versioned_fields(self):
        result = trivia.evaluate(self.conn, EvaluationRequest(specification={'template': 'win_rate', 'league_id': 39, 'team_id': 33,
            'period': {'mode': 'seasons', 'seasons': [2017]}}))
        self.assertNotIn('summary', result['analysis'])
        self.assertEqual(result['answer']['value'], 65.8)

    def test_unrecognized_queries_logged_only_after_authenticated_submit(self):
        before = self.conn.execute('SELECT COUNT(*) n FROM trivia_unrecognized_queries').fetchone()['n']
        body = {'text': 'Arsenal shots on mars last season', 'competition_id': 39}
        self.assertEqual(self.client.post('/api/query/parse', json=body).status_code, 401)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) n FROM trivia_unrecognized_queries').fetchone()['n'], before)
        response = self.client.post('/api/query/parse', json=body, auth=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['query'])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) n FROM trivia_unrecognized_queries').fetchone()['n'], before + 1)
        self.parse('Chelsea clean sheets 2017/18')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) n FROM trivia_unrecognized_queries').fetchone()['n'], before + 1)

    def test_typed_execute_rejects_unsafe_fields_and_unauthorized_requests(self):
        data = self.parse('Arsenal wins last season')['query']
        self.assertEqual(self.client.post('/api/query/evaluate', json=data).status_code, 401)
        self.assertEqual(self.client.post('/api/query/evaluate', json={**data, 'sql': 'DROP TABLE teams'}, auth=self.auth).status_code, 422)
        data['filters']['opponents'] = {'team_ids': [42]}
        self.assertEqual(self.client.post('/api/query/evaluate', json=data, auth=self.auth).status_code, 422)

    def test_incomplete_current_season_cannot_be_published(self):
        parsed = self.parse('Arsenal wins all time')
        query = SportsQuery(**parsed['query'])
        result = routes.run(query)
        self.assertFalse(result['coverage']['publishable'])
        self.assertIn('season_not_complete', result['coverage']['warnings'])

    def test_example_publisher_is_idempotent_and_uses_verified_versions(self):
        import contextlib
        import io
        from src import trivia_examples

        @contextmanager
        def shared():
            yield self.conn

        with patch('src.trivia_examples.get_connection', shared), contextlib.redirect_stdout(io.StringIO()):
            first = trivia_examples.create_pack(publish=True)
            second = trivia_examples.create_pack(publish=True)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 8)
        rows = self.conn.execute('SELECT state,verified_at FROM trivia_question_versions WHERE version_id=ANY(%s)', (first,)).fetchall()
        self.assertTrue(all(r['state'] == 'published' and r['verified_at'] for r in rows))
        self.assertTrue(trivia.grade(first[0], GradeAnswer(text='Lukaku'))['correct'])
