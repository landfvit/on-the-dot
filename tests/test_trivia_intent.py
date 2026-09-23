import json
import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from api.trivia_intent_contract import parse, messages
from api.trivia_intent_runtime import guard, wording, executable
from api.trivia_career import summarize, calculate
from src.trivia_intent_training import examples, target


class IntentContractTests(unittest.TestCase):
    def setUp(self):
        self.query = target('career_goals', 'Marcus Rashford', None, 2025)

    def test_all_training_targets_conform_without_answers(self):
        for split, rows in examples().items():
            for row in rows:
                with self.subTest(split=split, question=row['question']):
                    self.assertEqual(parse(json.dumps({'query': row['query']})), row['query'])
                    self.assertNotIn('answer', row)
                    self.assertEqual(messages(row['question'])[-1]['content'], row['question'])

    def test_no_question_or_template_crosses_splits(self):
        data = examples()
        for field in ('question', 'template'):
            sets = [{row[field] for row in data[split]} for split in data]
            for i, values in enumerate(sets):
                for other in sets[i+1:]:
                    self.assertFalse(values & other, (field, values & other))
        self.assertEqual(len(data['train']), 426)
        self.assertEqual(len(data['test']), 42)

    def test_career_has_no_implicit_season_or_team(self):
        self.assertIsNone(self.query['season'])
        self.assertIsNone(self.query['team'])
        guard(self.query, 'How many goals has Marcus Rashford scored in his premier league career?')
        self.assertIn('every club', wording(self.query))
        self.assertTrue(executable(self.query))

    def test_unknown_answer_does_not_prevent_future_season_recognition(self):
        query = target('champion', None, None, 2030)
        guard(query, 'Who won the Premier League in 2030/2031?')
        self.assertEqual(query['season'], 2030)

    def test_invalid_json_and_extra_fields_rejected(self):
        for value in [json.dumps({'query': self.query, 'answer': 89}), '{"query":null,"query":null}',
                      '```json\n{"query":null}\n```', '[]', '{"sql":"select 1"}']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse(value)

    def test_inconsistent_typed_slots_rejected(self):
        for fields in [{'season': 2024}, {'league_id': 140}, {'team': 'Manchester United'},
                       {'operation': 'invented'}, {'player': None}, {'season': True}]:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                parse(json.dumps({'query': dict(self.query, **fields)}))

    def test_scope_or_identity_cannot_be_invented(self):
        for text in ['How many Premier League goals has Wayne Rooney scored in his career?',
                     'How many goals has Marcus Rashford scored in his career?',
                     'How many goals has Marcus Rashford scored in the Premier League?',
                     'How many goals has Marcus Rashford scored in his Premier League career in 2020/21?']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                guard(self.query, text)

    def test_extra_filters_cannot_be_silently_discarded(self):
        for extra in ['at home', 'away', 'against Arsenal', 'after minute 80', 'before 2020', 'from penalties only', 'by 2022']:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                guard(self.query, f'How many goals has Marcus Rashford scored in his Premier League career {extra}?')

    def test_missing_time_scope_is_not_career(self):
        query = dict(self.query, time_scope='unspecified')
        guard(query, 'How many Premier League goals did Marcus Rashford score?')
        self.assertFalse(executable(query))
        with self.assertRaises(ValueError):
            guard(query, 'How many Premier League goals did Marcus Rashford score in his career?')


class CareerTests(unittest.TestCase):
    def test_counts_all_clubs_and_preserves_failed_quality(self):
        events = [dict(fixture_id=1,season=2024,team_id=33,verified=True),
                  dict(fixture_id=2,season=2024,team_id=66,verified=False),
                  dict(fixture_id=2,season=2024,team_id=66,verified=True)]
        stats = [dict(season=2024, team_id=66, goals_total=9), dict(season=2023,team_id=33,goals_total=5)]
        result = summarize(events, stats, {'player_id': 909, 'name': 'Marcus Rashford'}, {'sealed_at': 'today'})
        self.assertEqual(result['details']['recorded_goals'], 3)
        self.assertEqual(result['details']['quality_checked_goals'], 2)
        self.assertEqual(result['evidence_fixture_ids'], [1, 2])
        self.assertEqual(result['seasons'], [2023, 2024])
        self.assertEqual(len(result['breakdown']), 3)
        self.assertFalse(result['savable'])
        self.assertFalse(result['coverage']['career_complete'])

    def test_no_goals_does_not_prove_zero_career_total(self):
        result = summarize([], [], {'player_id': 1, 'name': 'New Player'}, {'sealed_at': 'today'})
        self.assertEqual(result['answer'], '0 recorded goals (partial verification)')
        self.assertFalse(result['coverage']['career_complete'])

    def test_ambiguous_identity_never_chooses_first(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        for rows in [[], [{'player_id': 1}, {'player_id': 2}]]:
            conn.execute.return_value.fetchall.return_value = rows
            with self.assertRaises(HTTPException) as error:
                calculate(conn, 'dataset', 'Smith')
            self.assertEqual(error.exception.status_code, 422)

    def test_sql_uses_player_id_and_league_excludes_own_goals(self):
        conn = MagicMock()
        identities, dataset, events, stats = [MagicMock() for _ in range(4)]
        identities.fetchall.return_value = [{'player_id': 909, 'player_name': 'M. Rashford', 'full_name': 'Marcus Rashford'}]
        dataset.fetchone.return_value = {'sealed_at': 'today'}
        events.fetchall.return_value = []
        stats.fetchall.return_value = []
        conn.execute.side_effect = [identities, dataset, events, stats]
        calculate(conn, 'snapshot', 'Marcus Rashford')
        sql, params = conn.execute.call_args_list[2].args
        self.assertEqual(params, ('snapshot', 909))
        self.assertIn('f.league_id=39', sql)
        self.assertIn("IN ('Normal Goal','Penalty')", sql)
        self.assertNotIn('season=', sql)
        self.assertIn('team_id)', sql)


if __name__ == '__main__':
    unittest.main()
