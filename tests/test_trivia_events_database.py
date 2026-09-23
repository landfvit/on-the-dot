"""Real PostgreSQL lifecycle tests; all question writes are rolled back."""
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import trivia
from api.database import get_connection
from api.main import app
from api.trivia_models import EvaluationRequest, SaveQuestion, GradeAnswer


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST') == '1', 'Set TRIVIA_DB_TEST=1 for database tests')
class EventDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_connection()
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)

        @contextmanager
        def shared():
            yield self.conn

        mock = patch('api.trivia.get_connection', shared)
        mock.start()
        self.addCleanup(mock.stop)
        self.dataset = trivia.dataset(self.conn)
        self.base = {'league_id': 39, 'period': {'mode': 'seasons', 'seasons': [2024]}, 'minimum_sample': 1}

    def test_all_event_families_have_unique_fixture_evidence(self):
        for options in [{'template': 'top_scorer', 'goal_filter': {'after_minute': 85}},
                        {'template': 'top_scorer', 'goal_filter': {'role': 'substitute', 'count': 'scoring_matches'}},
                        {'template': 'most_comeback_wins'}, {'template': 'comeback_wins', 'team_id': 33},
                        {'template': 'player_goals', 'player_id': 909}]:
            result = trivia.preview(EvaluationRequest(specification={**self.base, **options}))
            expected = 38 if options.get('team_id') else 380
            self.assertEqual(result['coverage']['requested_matches'], expected)
            self.assertEqual(len({r['fixture_id'] for r in result['evidence']}), expected)
            self.assertEqual(result['engine_version'], 'events-v2')
            if result['coverage']['excluded_matches']:
                self.assertFalse(result['coverage']['publishable'])

    def test_entity_save_publish_grade_and_private_answers(self):
        row = self.conn.execute('''SELECT f.team_id,f.match_date FROM trivia_match_team_facts f
            JOIN trivia_player_data_quality p USING(dataset_id,fixture_id)
            WHERE f.dataset_id=%s AND f.league_id=39 AND f.season=2024 AND p.scorers_valid
              AND EXISTS(SELECT 1 FROM trivia_event_facts e WHERE e.dataset_id=f.dataset_id
                AND e.fixture_id=f.fixture_id AND e.team_id=f.team_id AND e.event_type='Goal'
                AND e.event_detail IN ('Normal Goal','Penalty'))
            ORDER BY f.fixture_id LIMIT 1''', (self.dataset['dataset_id'],)).fetchone()
        day = row['match_date'].date().isoformat()
        spec = {**self.base, 'template': 'top_scorer', 'team_id': row['team_id'],
                'period': {'mode': 'dates', 'start': day, 'end': day}}
        result = trivia.preview(EvaluationRequest(specification=spec))
        self.assertTrue(result['coverage']['publishable'])
        saved = trivia.save(SaveQuestion(specification=spec))
        trivia.publish(saved['version_id'])
        answer = trivia.question(saved['version_id'])['answer']
        for winner in answer['accepted']:
            self.assertTrue(trivia.grade(saved['version_id'], GradeAnswer(text=winner['aliases'][0].upper()))['correct'])
        self.assertFalse(trivia.grade(saved['version_id'], GradeAnswer(text='Definitely not a player'))['correct'])
        self.assertFalse(trivia.grade(saved['version_id'], GradeAnswer(value=answer['value']))['correct'])
        client = TestClient(app)
        public = client.get('/api/trivia/play/questions?limit=100').json()['questions']
        item = next(item for item in public if item['version_id'] == str(saved['version_id']))
        self.assertEqual(set(item), {'version_id', 'question_text', 'answer_kind'})
        self.assertEqual(item['answer_kind'], 'entity')
        self.assertEqual(client.post(f"/api/trivia/questions/{saved['version_id']}/grade", json={}).status_code, 422)

    def test_old_dataset_rejected_without_changing_existing_questions(self):
        old = self.conn.execute("SELECT dataset_id FROM trivia_datasets WHERE engine_version='score-v1' LIMIT 1").fetchone()
        if not old:
            self.skipTest('No old snapshot retained')
        with self.assertRaises(HTTPException) as error:
            trivia.preview(EvaluationRequest(specification={**self.base, 'template': 'top_scorer'}, dataset_id=old['dataset_id']))
        self.assertEqual(error.exception.status_code, 409)
        old_result = trivia.preview(EvaluationRequest(specification={**self.base, 'template': 'total_wins', 'team_id': 33}, dataset_id=old['dataset_id']))
        self.assertEqual(old_result['answer']['value'], 11)

    def test_metadata_includes_templates_players_and_no_implicit_period(self):
        data = trivia.metadata()
        self.assertTrue(data['players'])
        templates = {t['template_key'] for t in data['templates']}
        self.assertTrue({'player_goals', 'top_scorer', 'comeback_wins', 'most_comeback_wins'} <= templates)
        for template in data['templates']:
            self.assertNotIn('period', template)


if __name__ == '__main__':
    unittest.main()
