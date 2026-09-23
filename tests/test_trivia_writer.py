import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from api.trivia_bank_engine import CannotCheck
from api import trivia_writer as writer
from trivia_app.main import app


class WriterTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'TRIVIA_EDITOR_USERNAME': 'editor', 'TRIVIA_EDITOR_PASSWORD': 'long-private-test-password'})
        env.start(); self.addCleanup(env.stop)
        self.client = TestClient(app)
        self.auth = ('editor', 'long-private-test-password')
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        private = patch.object(writer, 'PRIVATE', Path(self.tmp.name)); private.start(); self.addCleanup(private.stop)
        self.evaluator = MagicMock()
        self.result = {'answer': '16', 'details': {'goals': 16}, 'evidence_fixture_ids': [1], 'seasons': [2017]}
        self.evaluator.calculate.return_value = self.result
        self.conn = MagicMock()
        db = patch.object(writer, 'get_connection', return_value=self.conn); db.start(); self.addCleanup(db.stop)
        ev = patch.object(writer, 'evaluator_for', return_value=(self.evaluator, 'test-snapshot')); ev.start(); self.addCleanup(ev.stop)
        available = patch.object(writer, 'available', return_value=True); available.start(); self.addCleanup(available.stop)
        intent_available = patch.object(writer.intent_model, 'available', return_value=False); intent_available.start(); self.addCleanup(intent_available.stop)
        self.model = patch.object(writer, 'run_model').start(); self.addCleanup(patch.stopall)
        self.original = "Who was Manchester United's top scorer in the Premier League in 2017/2018?"
        self.canonical = 'Who finished as the sole leading Premier League goalscorer for Manchester United in 2017/18?'
        self.model.return_value = {'raw': json.dumps({'question': self.canonical}), 'adapter_sha256': 'local-test-hash'}

    def post(self, path, body):
        return self.client.post('/api/trivia/writer' + path, json=body, auth=self.auth)

    def proposal(self):
        self.evaluator.calculate.side_effect = [CannotCheck('Unrecognized'), self.result]
        response = self.post('/interpret', {'question': self.original})
        self.assertEqual(response.status_code, 200, response.text)
        self.evaluator.calculate.side_effect = None
        return response.json()

    def test_auth_required_and_assets_private(self):
        for path in ['/api/trivia/writer/metadata', '/trivia-assets/writer.js', '/trivia-assets/writer.css']:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post('/api/trivia/writer/interpret', json={'question': self.original}).status_code, 401)

    def test_cross_origin_posts_rejected_before_model(self):
        response = self.client.post('/api/trivia/writer/interpret', auth=self.auth,
            headers={'origin': 'https://untrusted.example'}, json={'question': self.original})
        self.assertEqual(response.status_code, 403)
        self.model.assert_not_called()

    def test_missing_season_never_guessed(self):
        response = self.post('/interpret', {'question': 'Who was the top scorer for Manchester United?'})
        self.assertEqual(response.status_code, 422)
        self.model.assert_not_called()

    def test_trained_career_recognition_does_not_require_year(self):
        query = {'operation': 'player_goals', 'player': 'Marcus Rashford', 'team': None,
                 'league_id': 39, 'time_scope': 'career', 'season': None}
        question = 'How many goals has Marcus Rashford scored in his Premier League career?'
        with patch.object(writer.intent_model, 'available', return_value=True), patch.object(
                writer.intent_model, 'recognize', return_value=(query, 'trained-sha')) as recognition:
            response = self.post('/interpret', {'question': question})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['method'], 'intent_model')
        self.assertEqual(data['status'], 'confirm_interpretation')
        self.assertIsNone(data['calculation'])
        self.assertIn('every club', data['interpretation'])
        recognition.assert_called_once_with(question)
        self.model.assert_not_called()
        partial = dict(self.result, savable=False, coverage={'status': 'partial'})
        with patch.object(writer, 'career_goals', return_value=partial) as calculate:
            answer = self.post('/answer', {'token': data['token']})
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertFalse(answer.json()['calculation']['savable'])
        self.assertEqual(calculate.call_args.args[1:], ('test-snapshot', 'Marcus Rashford'))
        self.assertEqual(self.post('/drafts', {'token': answer.json()['token']}).status_code, 409)

    def test_recognized_question_can_need_scope_without_guessing(self):
        query = {'operation': 'player_goals', 'player': 'Marcus Rashford', 'team': None,
                 'league_id': 39, 'time_scope': 'unspecified', 'season': None}
        with patch.object(writer.intent_model, 'available', return_value=True), patch.object(
                writer.intent_model, 'recognize', return_value=(query, 'trained-sha')):
            response = self.post('/interpret', {'question': 'How many Premier League goals did Marcus Rashford score?'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'needs_scope')
        self.assertIsNone(response.json()['token'])
        self.evaluator.calculate.assert_not_called()

    def test_understood_but_unimplemented_operation_does_not_guess_answer(self):
        query = {'operation': 'player_assists', 'player': 'Marcus Rashford', 'team': None,
                 'league_id': 39, 'time_scope': 'career', 'season': None}
        with patch.object(writer.intent_model, 'available', return_value=True), patch.object(
                writer.intent_model, 'recognize', return_value=(query, 'trained-sha')):
            response = self.post('/interpret', {'question': 'How many Premier League assists did Marcus Rashford make in his career?'})
        self.assertEqual(response.json()['status'], 'recognized_unavailable')
        self.assertIsNone(response.json()['calculation'])
        self.assertIsNone(response.json()['token'])

    def test_intent_guard_failure_stops_answering(self):
        with patch.object(writer.intent_model, 'available', return_value=True), patch.object(
                writer.intent_model, 'recognize', side_effect=ValueError('Changed scope')):
            response = self.post('/interpret', {'question': 'How many Premier League career goals did Marcus Rashford score at home?'})
        self.assertEqual(response.status_code, 422)
        self.assertIn('Changed scope', response.json()['detail'])
        self.model.assert_not_called()

    def test_bounded_intent_contract_does_not_shadow_library_patterns(self):
        self.evaluator.calculate.side_effect = [CannotCheck('Unrecognized'), self.result]
        with patch.object(writer.intent_model, 'available', return_value=True), patch.object(
                writer.intent_model, 'recognize', side_effect=ValueError('Operation outside small contract')):
            response = self.post('/interpret', {'question': self.original})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['method'], 'local_model')
        self.assertEqual(response.json()['interpretation'], self.canonical)

    def test_long_season_normalizes_but_invalid_season_fails(self):
        self.assertEqual(writer.normalize_seasons('In 2017/2018?'), 'In 2017/18?')
        self.assertEqual(self.post('/interpret', {'question': 'Manchester United goals in 2017/2019?'}).status_code, 422)

    def test_exact_question_calculates_without_model(self):
        response = self.post('/interpret', {'question': self.canonical})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['calculation']['details']['goals'], 16)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.model.assert_not_called()

    def test_league_winner_without_team_uses_final_table_question(self):
        response = self.post('/interpret', {'question': 'Who won the Premier League in 2025/26 season?'})
        self.assertEqual(response.status_code, 200)
        canonical = 'Which club finished as Premier League champions in 2025/26?'
        self.assertEqual(response.json()['interpretation'], canonical)
        self.evaluator.calculate.assert_called_once_with(canonical)
        self.model.assert_not_called()

    def test_long_season_and_runner_up_without_team(self):
        response = self.post('/interpret', {'question': 'Who finished second in the Premier League in 2024/2025 season?'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['interpretation'], 'Which club finished second in the 2024/25 Premier League table?')
        self.model.assert_not_called()

    def test_incomplete_final_table_does_not_guess_champion(self):
        self.evaluator.calculate.side_effect = CannotCheck('Complete final standings unavailable', 'incomplete')
        response = self.post('/interpret', {'question': 'Who won the Premier League in 2025/26 season?'})
        self.assertEqual(response.status_code, 422)
        self.assertIn('standings unavailable', response.json()['detail'])
        self.model.assert_not_called()

    def test_incomplete_data_never_falls_back_to_model(self):
        self.evaluator.calculate.side_effect = CannotCheck('Missing scorers', 'incomplete')
        self.assertEqual(self.post('/interpret', {'question': self.original}).status_code, 422)
        self.model.assert_not_called()

    def test_model_proposal_hides_answer_until_confirmation(self):
        data = self.proposal()
        self.assertEqual(data['status'], 'confirm_interpretation')
        self.assertIsNone(data['calculation'])
        self.assertEqual(data['interpretation'], self.canonical)
        self.assertEqual(self.post('/drafts', {'token': data['token']}).status_code, 409)
        answer = self.post('/answer', {'token': data['token']})
        self.assertEqual(answer.json()['calculation'], self.result)

    def test_changed_club_or_season_rejected(self):
        for changed in [self.canonical.replace('2017/18', '2018/19'), self.canonical.replace('Manchester United', 'Chelsea')]:
            self.evaluator.calculate.side_effect = CannotCheck('Unrecognized')
            self.model.return_value['raw'] = json.dumps({'question': changed})
            self.assertEqual(self.post('/interpret', {'question': self.original}).status_code, 422)

    def test_model_cannot_supply_an_answer_or_sql(self):
        for output in [{'question': self.canonical, 'answer': '999'}, {'sql': 'SELECT 1'}, {'question': None}, []]:
            self.evaluator.calculate.side_effect = CannotCheck('Unrecognized')
            self.model.return_value['raw'] = json.dumps(output)
            self.assertEqual(self.post('/interpret', {'question': self.original}).status_code, 422)

    def test_client_cannot_supply_answer(self):
        self.assertEqual(self.post('/interpret', {'question': self.original, 'answer': '999'}).status_code, 422)

    def test_other_competition_is_not_silently_replaced(self):
        self.assertEqual(self.post('/interpret', {'question': self.original.replace('Premier League', 'Champions League')}).status_code, 422)
        self.model.assert_not_called()

    def test_article_normalization_preserves_conditions(self):
        text = 'What was the win rate of Sunderland in the 2025/26 Premier League matches in which the team kept a clean sheet, rounded to one decimal place?'
        self.assertEqual(writer.parse_model_output(json.dumps({'question': text})), text.replace('in the 2025', 'in 2025'))

    def test_duplicate_model_fields_rejected(self):
        with self.assertRaises(ValueError):
            writer.parse_model_output('{"question":"one","question":"two"}')

    def test_model_cannot_drop_explicit_minute_or_goal_threshold(self):
        self.evaluator.calculate.side_effect = CannotCheck('Unrecognized')
        self.model.return_value['raw'] = json.dumps({'question': 'What was the win rate of Manchester United in 2017/18 Premier League matches in which both teams scored, rounded to one decimal place?'})
        response = self.post('/interpret', {'question': 'What was Manchester United win rate in 2017/18 when trailing by 2 goals after 80 minutes?'})
        self.assertEqual(response.status_code, 422)

    def test_big_six_spelling_preserves_numeric_scope(self):
        self.assertEqual(writer.numeric_conditions('Big 6 in 2017/2018'), writer.numeric_conditions('Big Six in 2017/18'))

    def test_token_tampering_and_expiry_fail(self):
        token = self.proposal()['token']
        self.assertEqual(self.post('/answer', {'token': 'X' + token[1:]}).status_code, 409)
        with patch.object(writer.time, 'time', return_value=10**12):
            self.assertEqual(self.post('/answer', {'token': token}).status_code, 409)

    def test_save_preserves_user_text_and_records_interpretation(self):
        proposal = self.proposal()
        token = self.post('/answer', {'token': proposal['token']}).json()['token']
        result = {'model_id': 'test-model', 'dataset_id': 'test-snapshot', 'topic': 'Scorers',
                  'calculation': dict(self.result, status='calculated')}
        with patch.object(writer, 'authoring', return_value=(result, {})):
            response = self.post('/drafts', {'token': token})
        self.assertEqual(response.status_code, 201, response.text)
        params = self.conn.__enter__.return_value.execute.call_args.args[1]
        self.assertEqual(params[3], self.original)
        self.assertEqual(params[6].obj['text_interpretation']['interpretation'], self.canonical)
        self.assertTrue(params[6].obj['text_interpretation']['confirmed'])

    def test_changed_snapshot_prevents_stale_save(self):
        proposal = self.proposal()
        token = self.post('/answer', {'token': proposal['token']}).json()['token']
        result = {'dataset_id': 'different-snapshot', 'calculation': {'status': 'calculated'}}
        with patch.object(writer, 'authoring', return_value=(result, {})):
            self.assertEqual(self.post('/drafts', {'token': token}).status_code, 409)

    def test_unknown_neural_wording_is_not_answered(self):
        self.evaluator.calculate.side_effect = CannotCheck('Unsupported calculation')
        self.assertEqual(self.post('/interpret', {'question': self.original}).status_code, 422)

    def test_gpu_busy_fails_without_queuing(self):
        self.evaluator.calculate.side_effect = CannotCheck('Unrecognized')
        with patch.object(writer.fcntl, 'flock', side_effect=BlockingIOError):
            self.assertEqual(self.post('/interpret', {'question': self.original}).status_code, 429)
        self.model.assert_not_called()

    def test_examples_are_user_questions_not_recipe_forms(self):
        data = self.client.get('/api/trivia/writer/metadata', auth=self.auth).json()
        self.assertGreaterEqual(len(data['examples']), 5)
        self.assertNotIn('recipes', data)
        page = self.client.get('/internal/trivia', auth=self.auth)
        self.assertIn('Your question', page.text)
        self.assertIn('Find answer', page.text)


class RetrievalTests(unittest.TestCase):
    def test_league_retrieval_does_not_invent_a_subject_club(self):
        rows = [
            'Which club won 6-0 away at Ipswich Town in the 2024/25 Premier League?',
            'How many clubs won more away matches than home matches in the 2024/25 Premier League?',
            'Which club finished as Premier League champions in 2024/25?',
        ]
        writer.retrieval_index.cache_clear()
        try:
            with patch.object(writer, 'corpus', return_value=rows):
                found = writer.candidate_questions('Who won the Premier League in 2025/26 season?')
                self.assertTrue(found)
                self.assertNotIn(rows[0], found)
        finally:
            writer.retrieval_index.cache_clear()

    def test_semantic_words_outweigh_generic_question_words(self):
        rows = [
            'What was the win rate of Sheffield United against Big Six clubs in the 2019/20 Premier League, rounded to one decimal place?',
            'Who finished as the sole leading Premier League goalscorer for Everton in 2016/17?',
            'Which club recorded the most draws in the 2020/21 Premier League?',
        ]
        writer.retrieval_index.cache_clear()
        with patch.object(writer, 'corpus', return_value=rows):
            self.assertEqual(writer.candidate_questions(writer.EXAMPLES[0])[0], rows[1])
            self.assertEqual(writer.candidate_questions(writer.EXAMPLES[2])[0], rows[2])
        writer.retrieval_index.cache_clear()
