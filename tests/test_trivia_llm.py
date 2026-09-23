from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from api.trivia_generation_experiment import BY_KEY, wording
from api.trivia_llm_contract import DEFINITIONS, FAMILIES, SPLITS, identity, messages, parse_proposal
from src.trivia_llm import runtime_env, scope_for, snapshot, verify_bundle, resume_source
from src.trivia_llm_worker import sha256, verify_model
from src.trivia_llm_dataset import JsonCompletionDataset


class LocalLLMContractTests(unittest.TestCase):
    def setUp(self):
        self.scope = scope_for(33, 2024, 'Manchester United')
        self.job = {'scope': self.scope, 'allowed_plans': ['opening_points']}
        self.proposal = {'question': wording('opening_points', 'Manchester United', 2024),
                         'query': {'version': 'local-trivia-v1', 'plan': 'opening_points',
                                   'league_id': 39, 'team_id': 33, 'season': 2024}}

    def parse(self, proposal=None):
        return parse_proposal(json.dumps(proposal or self.proposal), self.job)

    def test_valid_proposal_keeps_model_text(self):
        text = 'Across their first six matches in the 2024/25 Premier League, how many points did Manchester United earn on the pitch?'
        self.proposal['question'] = text
        self.assertEqual(self.parse().question, text)

    def test_all_plans_have_documented_disjoint_families(self):
        keys = [plan for plans in FAMILIES.values() for plan in plans]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), set(BY_KEY))
        self.assertEqual(set(DEFINITIONS), set(keys))
        self.assertEqual(set(SPLITS), set(FAMILIES))
        self.assertEqual(set(SPLITS.values()), {'train', 'valid', 'test'})

    def test_every_reference_conforms(self):
        for plan in BY_KEY:
            self.job['allowed_plans'] = [plan]
            self.proposal['query']['plan'] = plan
            self.proposal['question'] = wording(plan, 'Manchester United', 2024)
            with self.subTest(plan=plan):
                self.parse()

    def test_scope_changes_fail(self):
        for key, value in [('season', 2023), ('team_id', 42), ('league_id', 140), ('version', 'sql-v1')]:
            proposal = deepcopy(self.proposal)
            proposal['query'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.parse(proposal)

    def test_answers_sql_and_unknown_filters_fail(self):
        for field in ('answer', 'sql', 'weather', 'minute', 'player_id'):
            for location in ('root', 'query'):
                proposal = deepcopy(self.proposal)
                target = proposal if location == 'root' else proposal['query']
                target[field] = 'untrusted'
                with self.subTest(field=field, location=location), self.assertRaises(ValueError):
                    self.parse(proposal)

    def test_unknown_and_wrong_category_fail(self):
        for plan in ('DROP TABLE fixtures', 'streak_wins'):
            self.proposal['query']['plan'] = plan
            with self.assertRaises(ValueError):
                self.parse()

    def test_string_and_boolean_ids_are_not_coerced(self):
        for value in ('33', True, 33.0):
            self.proposal['query']['team_id'] = value
            with self.assertRaises(ValueError):
                self.parse()

    def test_missing_question_scope_fails(self):
        for remove in ('Manchester United', 'Premier League', '2024/25'):
            proposal = deepcopy(self.proposal)
            proposal['question'] = proposal['question'].replace(remove, '')
            with self.assertRaises(ValueError):
                self.parse(proposal)

    def test_json_not_extracted_or_repaired(self):
        raw = json.dumps(self.proposal)
        for invalid in ('```json\n' + raw + '\n```', raw + raw, raw[:-1], 'Here: ' + raw,
                        raw[:-1] + ',"question":"duplicate key?"}', 'x' * 8001):
            with self.subTest(raw=invalid[:25]), self.assertRaises(ValueError):
                parse_proposal(invalid, self.job)

    def test_prompt_has_no_answer(self):
        prompt = messages(self.scope, ['opening_points'])
        user = json.loads(prompt[1]['content'])
        self.assertEqual(user['scope']['season'], 2024)
        self.assertNotIn('answer', user)
        self.assertEqual(list(user['catalogue']), ['opening_points'])

    def test_training_prompt_equals_inference_and_target_is_exact_json(self):
        class FakeTokenizer:
            eos_token_id = 999

            def apply_chat_template(self, messages, **kwargs):
                self_messages = [message['role'] for message in messages]
                if 'assistant' in self_messages:
                    raise AssertionError('Must not inject assistant template reasoning tags')
                return [1, 2, 3]

            def encode(self, text, add_special_tokens):
                if add_special_tokens:
                    raise AssertionError('Target must not add a second prompt prefix')
                return list(text.encode())

        raw = json.dumps(self.proposal)
        record = {'messages': messages(self.scope, ['opening_points']) + [{'role': 'assistant', 'content': raw}]}
        dataset = JsonCompletionDataset([record], FakeTokenizer())
        tokens, offset = dataset.process(dataset[0])
        self.assertEqual(tokens[:offset], [1, 2, 3])
        self.assertEqual(bytes(tokens[offset:-1]).decode(), raw)
        self.assertEqual(tokens[-1], 999)
        self.assertEqual(len(dataset), 1)

    def test_semantic_identity_ignores_question_paraphrases(self):
        self.assertEqual(identity(self.proposal['query']), ('opening_points', 33, 2024))

    def test_runtime_does_not_inherit_secrets_or_reporting(self):
        with patch.dict(os.environ, {'DB_PASSWORD': 'secret', 'OPENAI_API_KEY': 'secret', 'WANDB_API_KEY': 'secret'}):
            env = runtime_env()
        self.assertFalse({'DB_PASSWORD', 'OPENAI_API_KEY', 'WANDB_API_KEY'} & env.keys())
        self.assertEqual(env['HF_HUB_OFFLINE'], '1')
        self.assertEqual(env['TRANSFORMERS_OFFLINE'], '1')

    def test_bundle_tampering_fails(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'train.jsonl').write_text('original')
            (path / 'manifest.json').write_text(json.dumps({'sha256': {'train.jsonl': sha256(path / 'train.jsonl')}}))
            verify_bundle(path)
            (path / 'train.jsonl').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'changed'):
                verify_bundle(path)

    def test_model_requires_local_weights_and_checks_integrity(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            with self.assertRaises(ValueError):
                verify_model(path)
            (path / 'model.safetensors').write_bytes(b'test')
            (path / 'points-model.json').write_text(json.dumps({'sha256': {'model.safetensors': sha256(path / 'model.safetensors')}}))
            verify_model(path)
            (path / 'model.safetensors').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                verify_model(path)

    def test_traversal_manifest_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            outside = path / 'outside'
            outside.write_text('content')
            bundle = path / 'bundle'
            bundle.mkdir()
            (bundle / 'manifest.json').write_text(json.dumps({'sha256': {'../outside': sha256(outside)}}))
            with self.assertRaises(ValueError):
                verify_bundle(bundle)


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST') == '1', 'Read-only snapshot audit')
class LocalLLMDatabaseTests(unittest.TestCase):
    def test_complete_season_read_only(self):
        from api.database import get_connection
        with get_connection() as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            dataset, groups, digest = snapshot(conn, [2024])
            self.assertIsNotNone(dataset['sealed_at'])
            self.assertEqual(len(groups), 20)
            self.assertEqual({len(rows) for rows in groups.values()}, {38})
            self.assertEqual(len(digest), 64)

    def test_missing_and_duplicate_seasons_fail_closed(self):
        from api.database import get_connection
        with get_connection() as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            for seasons in ([], [2024, 2024], [2099]):
                with self.subTest(seasons=seasons), self.assertRaises(ValueError):
                    snapshot(conn, seasons)


class LocalLLMContinuationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.bundle = Path(temporary.name)
        self.source = self.bundle / 'adapter-json'
        self.source.mkdir()
        (self.bundle / 'manifest.json').write_text('{}')
        (self.source / 'adapters.safetensors').write_bytes(b'fake test weights')
        self.model = {'repository': 'local-test', 'revision': 'test'}
        self.metadata = {'model_manifest': self.model,
            'bundle_manifest_sha256': sha256(self.bundle / 'manifest.json'),
            'target_format': 'Exact inference prompt + JSON completion + EOS; test'}
        self.config = {'fine_tune_type': 'lora', 'num_layers': 4, 'iters': 40,
                       'lora_parameters': {'rank': 8, 'dropout': 0.0, 'scale': 20.0}}
        self.save()

    def save(self):
        (self.source / 'training-manifest.json').write_text(json.dumps(self.metadata))
        (self.source / 'adapter_config.json').write_text(json.dumps(self.config))

    def check(self):
        return resume_source(self.source, self.bundle, self.model)

    def test_legacy_completed_adapter_records_exact_lineage(self):
        before = (self.source / 'adapters.safetensors').read_bytes()
        parent = self.check()
        self.assertEqual(parent['previous_updates'], 40)
        self.assertEqual(parent['sha256'], sha256(self.source / 'adapters.safetensors'))
        self.assertEqual((self.source / 'adapters.safetensors').read_bytes(), before)
        self.assertIn('New Adam', parent['optimizer_state'])

    def test_different_model_split_or_legacy_target_rejected(self):
        original = deepcopy(self.metadata)
        for field, value in [('model_manifest', {}), ('bundle_manifest_sha256', 'changed'), ('target_format', 'old chat template')]:
            self.metadata = {**original, field: value}
            self.save()
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check()

    def test_incompatible_lora_configuration_rejected(self):
        self.config['num_layers'] = 8
        self.save()
        with self.assertRaisesRegex(ValueError, 'configuration'):
            self.check()

    def test_failed_training_cannot_resume(self):
        (self.source / 'failure.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'completed'):
            self.check()

    def test_new_continuations_require_completion_and_unchanged_weights(self):
        self.metadata.update(completion_required=True, total_updates=140)
        self.save()
        with self.assertRaisesRegex(ValueError, 'did not complete'):
            self.check()
        (self.source / 'completion.json').write_text(json.dumps({
            'adapter_sha256': sha256(self.source / 'adapters.safetensors')}))
        self.assertEqual(self.check()['previous_updates'], 140)
        (self.source / 'adapters.safetensors').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.check()


if __name__ == '__main__':
    unittest.main()
