import copy
import json
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from pydantic import ValidationError

from api.query_training import Annotation,Verify
from src.query_model import diagnose,predict,prepare,train
from src.query_training_pilot import PILOT


def corpus():
    return [{'annotation_id':str(uuid4()),'example_id':str(uuid4()),'revision':1,
        'query_text':'Manchester United '+phrase+' last 5 seasons','phrase':phrase,'label':label,
        'family_key':f'{label}-{i}','split':['train','train','validation','test'][i],
        'reviewed_by':'test-reviewer','reviewed_at':'2026-09-21T00:00:00Z'}
        for label,phrases in PILOT.items() for i,phrase in enumerate(phrases)]


class TrainingTests(unittest.TestCase):
    def test_diagnostics_use_frozen_training_only_without_mutation(self):
        model=train(corpus());before=copy.deepcopy(model)
        seen=diagnose(model['artifact'],'win rate',model['corpus'])
        self.assertTrue(seen['seen_in_training'])
        self.assertEqual(seen['training_phrase_count'],6)
        self.assertEqual(seen['rule_label'],'win_rate')
        self.assertEqual(seen['neighbors'][0]['phrase'],'win rate')
        self.assertEqual(seen['neighbors'][0]['similarity'],1)
        heldout=diagnose(model['artifact'],'stadium parking fees',model['corpus'])
        self.assertFalse(heldout['seen_in_training'])
        train_phrases={r['phrase'] for r in model['corpus'] if r['split']=='train'}
        self.assertTrue(all(n['phrase'] in train_phrases for n in heldout['neighbors']))
        missing=diagnose(model['artifact'],'goals per game',model['corpus'])
        self.assertEqual(missing['rule_label'],'goals_per_game')
        self.assertNotIn('goals_per_game',missing['trained_labels'])
        context=diagnose(model['artifact'],'shirt colour',model['corpus'])
        self.assertEqual(context['rule_label'],'kit_colour')
        self.assertNotIn('kit_colour',context['trained_labels'])
        self.assertEqual(context['label'],predict(model['artifact'],'shirt colour')['label'])
        empty=diagnose(model['artifact'],'9999999',model['corpus'])
        self.assertIsNone(empty['label'])
        self.assertEqual(empty['neighbors'],[])
        self.assertFalse(empty['executable'])
        self.assertEqual(before,model)

    def test_annotation_requires_unique_literal_phrase(self):
        base=dict(query_text='Arsenal win rate last season',phrase='win rate',label='win_rate',family_key='rates',split='train')
        self.assertEqual(Annotation(**base).phrase,'win rate')
        for change in [{'phrase':'wins'}, {'query_text':'win rate win rate'}, {'label':'sql'},
                       {'label':'unsupported'}, {'reviewed_by':'pretend-human'}, {'family_key':'../path'}]:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                Annotation(**{**base,**change})

    def test_explicit_confirmation_required(self):
        for value in [{},{'confirmed':False}]:
            with self.assertRaises(ValidationError):Verify(**value)

    def test_reject_unreviewed_or_inadequate_training_data(self):
        with self.assertRaises(ValueError):prepare([])
        rows=corpus();rows[0]['reviewed_at']=None
        with self.assertRaises(ValueError):prepare(rows)
        with self.assertRaises(ValueError):prepare(corpus()[:-1])

    def test_group_duplicate_and_near_duplicate_leakage(self):
        for change in [{'family_key':'win_rate-0'}, {'phrase':'win rate'}, {'phrase':'win rates'}]:
            rows=corpus();rows[2].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):prepare(rows)

    def test_actual_cpu_fit_report_and_safe_json_roundtrip(self):
        rows=corpus()
        with patch('socket.socket',side_effect=AssertionError('Network access during training')):
            result=train(rows)
            loaded=json.loads(json.dumps(result['artifact']))
            answer=predict(loaded,'win rate')
        self.assertEqual(answer['label'],'win_rate')
        self.assertFalse(answer['executable'])
        self.assertFalse(result['report']['deployed'])
        self.assertEqual(result['report']['counts'],{'train':6,'validation':3,'test':3})
        self.assertEqual(len(result['dataset_hash']),64)
        self.assertIn('confusion_matrix',result['report']['test'])

    def test_training_is_reproducible_and_dataset_hash_covers_labels(self):
        rows=corpus();a=train(rows);b=train(list(reversed(rows)))
        self.assertEqual(a['artifact'],b['artifact'])
        self.assertEqual(a['dataset_hash'],b['dataset_hash'])
        changed=copy.deepcopy(rows);changed[0]['query_text']+='?'
        self.assertNotEqual(a['dataset_hash'],train(changed)['dataset_hash'])

    def test_no_features_and_unknown_format_never_execute(self):
        artifact=train(corpus())['artifact']
        self.assertIsNone(predict(artifact,'')['label'])
        with self.assertRaises(ValueError):predict({**artifact,'format':'pickle'},'wins')

    def test_duplicate_phrase_does_not_inflate_fit_or_test_sample(self):
        rows=corpus(); rows.append({**rows[0],'annotation_id':str(uuid4()),'example_id':str(uuid4())})
        result=train(rows)
        self.assertEqual(result['report']['duplicate_phrases_removed'],1)
        self.assertEqual(result['report']['counts']['train'],6)

    def test_binary_classifier_roundtrip(self):
        result=train([r for r in corpus() if r['label']!='unsupported'])
        self.assertEqual(predict(result['artifact'],'goals scored')['label'],'total_goals')

    def test_management_command_registers_and_exports_real_fit(self):
        from src.train_query_model import run_training
        conn=MagicMock();conn.__enter__.return_value=conn
        conn.execute.return_value.fetchall.return_value=corpus()
        with TemporaryDirectory() as directory,patch('src.train_query_model.get_connection',return_value=conn):
            result=run_training(Path(directory))
            folder=Path(result['output'])
            artifact=json.loads((folder/'artifact.json').read_text())
            self.assertEqual(predict(artifact,'win rate')['label'],'win_rate')
            self.assertTrue((folder/'report.json').exists())
            self.assertEqual((folder/'artifact.json').stat().st_mode & 0o777,0o600)
            self.assertEqual(folder.stat().st_mode & 0o777,0o700)
        self.assertFalse(result['deployed'])
        self.assertTrue(any('INSERT INTO trivia_query_model_runs' in str(c) for c in conn.execute.call_args_list))
