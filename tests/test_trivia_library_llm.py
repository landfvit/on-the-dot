from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock

from api.trivia_bank_engine import canonical, load_evaluator
from src.trivia_library_queries import TEMPLATES, compile_question, messages, parse_output, render
from src.trivia_library_llm import diverse, identity, split_rows
from src.trivia_llm import read_jsonl, verify_bundle
from src.check_library_generation import independent


class LibraryQueryTests(unittest.TestCase):
    def setUp(self):
        self.query = {'op': 'conditional_win_rate', 'params': {
            'team': 33, 'season': 2017, 'condition': 'both teams scored'}}

    def test_roundtrip_all_registered_operators(self):
        values = dict(team=33, opponent=42, left=33, right=42, season=2017,
            start=2015, end=2024, venue='away', location='at home',
            group='big six clubs', condition='both teams scored', metric='away wins',
            score='2-1', score2='1-0', goals=3, position='champions', half='bottom',
            direction='scored', comparison='finished higher',
            pair_condition='beat both home and away', team_condition='conceded at least 80 goals')
        from string import Formatter
        for op, template in TEMPLATES.items():
            fields = {name for _, name, _, _ in Formatter().parse(template) if name}
            query = {'op': op, 'params': {name: values[name] for name in fields}}
            with self.subTest(op=op):
                self.assertEqual(compile_question(render(query)), query)

    def test_aliases_and_case_are_equivalent(self):
        text = render(self.query).replace('Manchester United', 'Man Utd').upper()
        self.assertEqual(compile_question(text), self.query)

    def test_season_must_be_explicit_and_valid(self):
        text = render(self.query)
        for bad in [text.replace('2017/18', '2017/19'), text.replace('2017/18', 'last season')]:
            with self.assertRaises(ValueError):
                compile_question(bad)

    def test_no_source_wording_or_answer_in_prompt(self):
        prompt = messages(self.query)
        user = json.loads(prompt[1]['content'])
        self.assertEqual(set(user), {'query', 'clubs'})
        self.assertEqual(user['query'], self.query)
        self.assertNotIn(render(self.query), json.dumps(prompt))

    def test_original_model_output_is_not_rewritten(self):
        text = render(self.query).upper()
        self.assertEqual(parse_output(json.dumps({'question': text}), self.query), text)

    def test_wrong_subject_season_or_condition_rejected(self):
        for field, value in [('team', 42), ('season', 2018), ('condition', 'the team kept a clean sheet')]:
            wrong = deepcopy(self.query)
            wrong['params'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_output(json.dumps({'question': render(wrong)}), self.query)

    def test_wrong_question_type_rejected_even_with_same_answer(self):
        other = {'op': 'count_away_clean_sheets', 'params': {'team': 33, 'season': 2017}}
        with self.assertRaises(ValueError):
            parse_output(json.dumps({'question': render(other)}), self.query)

    def test_extra_fields_duplicate_keys_and_markdown_rejected(self):
        text = json.dumps({'question': render(self.query)})
        for raw in [text[:-1] + ',"question":"duplicate"}', '```json\n' + text + '\n```',
                    text[:-1] + ',"answer":"10"}', '[]', '{"question":42}', text + text]:
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                parse_output(raw, self.query)

    def test_unknown_operator_and_parameters_rejected(self):
        for query in [{'op': 'sql', 'params': {}}, dict(self.query, sql='SELECT 1'),
                      {'op': self.query['op'], 'params': dict(self.query['params'], limit=10)}]:
            with self.assertRaises(ValueError):
                render(query)

    def test_integer_fields_do_not_accept_bools_or_strings(self):
        for value in [True, '2017', 2017.0]:
            query = deepcopy(self.query)
            query['params']['season'] = value
            with self.assertRaises(ValueError):
                render(query)

    def test_repeated_club_perspective_must_agree(self):
        query = {'op': 'defeat_score', 'params': {'team': 33, 'opponent': 42, 'season': 2017, 'venue': 'away'}}
        text = render(query).replace("Manchester United's goals", "Arsenal's goals")
        with self.assertRaises(ValueError):
            compile_question(text)

    def test_identity_ignores_dict_order_not_semantics(self):
        self.assertEqual(identity(self.query), identity(dict(reversed(list(self.query.items())))))
        self.assertNotEqual(identity(self.query), identity({'op': 'count_away_wins', 'params': {'team': 33, 'season': 2017}}))

    def test_diverse_selection_round_robins_operators(self):
        rows = [{'id': f'{op}-{i}', 'query': {'op': op}} for op in ['a', 'b', 'c'] for i in range(10)]
        selected = diverse(rows, 6)
        self.assertEqual([r['query']['op'] for r in selected], ['a', 'b', 'c', 'a', 'b', 'c'])
        self.assertEqual(len({r['id'] for r in selected}), 6)

    def test_family_split_keeps_season_and_club_variants_together(self):
        rows = []
        for op, params in [
            ('conditional_win_rate', {'condition': 'both teams scored'}),
            ('count_away_wins', {}), ('most_frequent_score', {'venue': 'home'}),
            ('head_to_head_clean_sheets', {'opponent': 42, 'start': 2015, 'end': 2024}),
            ('opponent_most_goals_conceded', {}),
            ('club_peak_season', {'metric': 'away wins', 'start': 2015, 'end': 2024}),
            ('home_share_of_wins', {}), ('count_failed_to_score', {}),
            ('identify_defeated_opponent', {'score': '2-1', 'location': 'at home'}),
        ]:
            for team in (33, 40):
                query = {'op': op, 'params': dict(params, team=team)}
                if 'start' not in params:
                    query['params']['season'] = 2017
                rows.append({'question': render(query), 'query': query})
        splits = split_rows(rows)
        seen = {}
        for split, values in splits.items():
            for row in values:
                op = row['query']['op']
                self.assertEqual(seen.setdefault(op, split), split)


class IndependentLibrarySQLTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.conn.execute.return_value.fetchall.return_value = [{'answer': '20.0%'}]

    def test_percentage_uses_raw_results_with_escaped_literal(self):
        value = independent(self.conn, {'op': 'conditional_win_rate', 'params': {
            'season': 2017, 'team': 33, 'condition': 'both teams scored'}})
        sql, params = self.conn.execute.call_args.args
        self.assertEqual(value, '20.0%')
        self.assertIn("|| '%%'", sql)
        self.assertIn('gf>0 AND ga>0', sql)
        self.assertIn('FROM fixtures', sql)
        self.assertNotIn('trivia_match_team_facts', sql)
        self.assertEqual(params, (2017, 33))

    def test_away_filter_is_preserved(self):
        independent(self.conn, {'op': 'win_rate_opponent_group_venue', 'params': {
            'season': 2020, 'team': 49, 'group': 'big six clubs', 'location': 'away from home'}})
        self.assertTrue(self.conn.execute.call_args.args[0].endswith(' AND NOT home'))

    def test_unimplemented_query_abstains(self):
        with self.assertRaises(NotImplementedError):
            independent(self.conn, {'op': 'weather', 'params': {'season': 2017}})
        self.conn.execute.assert_not_called()

    def test_nonunique_scalar_result_fails(self):
        self.conn.execute.return_value.fetchall.return_value = [{'answer': '1-2'}, {'answer': '0-1'}]
        with self.assertRaises(ValueError):
            independent(self.conn, {'op': 'defeat_score', 'params': {
                'season': 2017, 'team': 33, 'opponent': 42, 'venue': 'home'}})

    def test_tied_record_fails(self):
        self.conn.execute.return_value.fetchall.return_value = [{'team_id': 33, 'value': 10}, {'team_id': 42, 'value': 10}]
        with self.assertRaises(ValueError):
            independent(self.conn, {'op': 'league_club_record', 'params': {'season': 2017, 'metric': 'draws'}})


@unittest.skipUnless(os.getenv('TRIVIA_LIBRARY_BUNDLE'), 'Set TRIVIA_LIBRARY_BUNDLE for frozen real-library checks')
class LibraryBundleTests(unittest.TestCase):
    def setUp(self):
        self.bundle = Path(os.environ['TRIVIA_LIBRARY_BUNDLE'])
        self.manifest = verify_bundle(self.bundle)
        self.provenance = json.loads((self.bundle / 'provenance.json').read_text())

    def test_every_source_row_roundtrips_and_has_db_provenance(self):
        seen_ids, seen_queries = set(), set()
        for split, rows in self.provenance.items():
            training = read_jsonl(self.bundle / f'{split}.jsonl')
            self.assertEqual(len(rows), len(training))
            for row, record in zip(rows, training):
                self.assertNotIn(row['id'], seen_ids)
                self.assertNotIn(identity(row['query']), seen_queries)
                seen_ids.add(row['id'])
                seen_queries.add(identity(row['query']))
                self.assertEqual(row['checked']['status'], 'matched')
                self.assertTrue(row['checked']['evidence_fixture_ids'])
                self.assertEqual(record['messages'][:-1], messages(row['query']))
                self.assertEqual(parse_output(record['messages'][-1]['content'], row['query']), row['question'])
        self.assertEqual(len(seen_ids), self.manifest['eligible_count'])

    def test_zero_family_leakage_and_large_diverse_training_set(self):
        groups = {k: {r['family'] for r in v} for k, v in self.provenance.items()}
        for a, b in [('train', 'valid'), ('train', 'test'), ('valid', 'test')]:
            self.assertFalse(groups[a] & groups[b])
        self.assertGreaterEqual(len(self.provenance['train']), 1000)
        self.assertGreaterEqual(len(groups['train']), 30)
        self.assertGreaterEqual(len({r['topic'] for r in self.provenance['train']}), 15)

    def test_new_scope_jobs_not_present_in_entire_imported_bank(self):
        known = set()
        for row in json.loads((self.bundle / 'source.json').read_text()):
            try:
                known.add(identity(compile_question(row['content']['question'])))
            except ValueError:
                pass
        jobs = read_jsonl(self.bundle / 'jobs.jsonl')
        new = [r for r in jobs if r['kind'] == 'new_scope']
        self.assertEqual(len(new), 32)
        self.assertEqual(len({identity(r['query']) for r in new}), len(new))
        self.assertFalse(known & {identity(r['query']) for r in new})

    @unittest.skipUnless(os.getenv('TRIVIA_DB_TESTS') == '1', 'Read-only DB integration is opt-in')
    def test_every_selected_answer_freshly_recomputes(self):
        from api.database import get_connection
        with get_connection() as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            evaluator, _ = load_evaluator(conn, self.manifest['dataset_id'])
            for rows in self.provenance.values():
                for row in rows:
                    result = evaluator.calculate(render(row['query']))
                    self.assertEqual(canonical(result['answer']), canonical(row['checked']['answer']))
                    self.assertEqual(result['evidence_fixture_ids'], row['checked']['evidence_fixture_ids'])

    @unittest.skipUnless(os.getenv('TRIVIA_DB_TESTS') == '1', 'Read-only DB integration is opt-in')
    def test_all_new_scope_answers_agree_with_independent_sql(self):
        from api.database import get_connection
        with get_connection() as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            jobs = [r for r in read_jsonl(self.bundle / 'jobs.jsonl') if r['kind'] == 'new_scope']
            for job in jobs:
                with self.subTest(job=job['id']):
                    self.assertEqual(canonical(independent(conn, job['query'])), canonical(job['expected']['answer']))


if __name__ == '__main__':
    unittest.main()
