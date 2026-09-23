from copy import deepcopy
from decimal import Decimal
from itertools import combinations
import unittest

from api.numeric_choices import options, refresh, spacing, POLICY_VERSION
from api.penalty_bank import make_options
from api.penalty_questions import options as library_options


class NumericChoicesTests(unittest.TestCase):
    def assert_choices(self, answer, choices, correct, gap):
        values = [Decimal(o['text'].rstrip('%').strip()) for o in choices]
        self.assertEqual(len(values), 4)
        self.assertEqual(len(set(values)), 4)
        self.assertEqual(next(o['text'] for o in choices if o['id'] == correct), answer)
        self.assertTrue(all(abs(a-b) >= gap for a, b in combinations(values, 2)))
        if answer.endswith('%'):
            self.assertTrue(all(0 <= value <= 100 for value in values))

    def test_every_tenth_of_a_percentage_point_has_ten_point_gaps(self):
        for tenth in range(1001):
            answer = f'{Decimal(tenth)/10:.1f}%'
            with self.subTest(answer=answer):
                choices, correct = options(answer)
                self.assert_choices(answer, choices, correct, 10)
                self.assertTrue(all(len(o['text'].split('.')[1].rstrip('%')) == 1 for o in choices))

    def test_reference_precision_is_preserved(self):
        for answer in ['75%', '75.0%', '75.30%', '0 %', '100.00 %']:
            choices, correct = options(answer)
            self.assert_choices(answer, choices, correct, 10)

    def test_numeric_scale_and_signed_values(self):
        for answer in ['0', '1', '7', '38', '75', '150', '0.05', '0.5', '2.37', '-12', '2017']:
            choices, correct = options(answer)
            self.assert_choices(answer, choices, correct, spacing(Decimal(answer)))
            if Decimal(answer) >= 0:
                self.assertTrue(all(Decimal(o['text']) >= 0 for o in choices))
        self.assertEqual(spacing(Decimal('75')), 10)
        self.assertEqual(spacing(Decimal('38')), 5)
        self.assertEqual(spacing(Decimal('2017')), 2)

    def test_equivalent_accepted_answers_cannot_be_wrong_choices(self):
        choices, correct = options('75%', accepted=['65%', '85.0%', '75.00%', 'text'])
        self.assert_choices('75%', choices, correct, 10)
        self.assertFalse({Decimal(65), Decimal(85)} & {Decimal(o['text'].rstrip('%')) for o in choices})

    def test_bank_and_library_use_wider_spacing(self):
        item = {'id': 'TEST', 'answer': '75.0%', 'question': 'What was the win rate?', 'topic': 'Results'}
        choices, correct = make_options(item, {})
        self.assert_choices('75.0%', choices, correct, 10)
        choices, correct = library_options(Decimal('75.0'), Decimal('.1'), ' %')
        self.assert_choices('75.0 %', choices, correct, 10)

    def test_refresh_preserves_release_and_answer(self):
        question = {'key': 'q1', 'text': 'What was the win rate?', 'correct': '1',
                    'options': [{'id': str(i), 'text': value} for i, value in enumerate(['74.9%', '75%', '75.3%', '75.6%'])]}
        before = deepcopy(question)
        result = refresh(question)
        self.assertEqual(question, before)
        self.assertEqual(result['key'], question['key'])
        self.assertEqual(result['numeric_choice_policy'], POLICY_VERSION)
        self.assert_choices('75%', result['options'], result['correct'], 10)

    def test_two_choice_and_non_numeric_questions_unchanged(self):
        for labels in [['1', '2'], ['Arsenal', 'Chelsea', 'Liverpool', 'Everton'], ['2-1', '0-0', '1-0', '3-0']]:
            question = {'text': 'Question?', 'correct': '0', 'options': [{'id': str(i), 'text': value} for i, value in enumerate(labels)]}
            self.assertEqual(refresh(question), question)

    def test_invalid_percentage_fails_closed(self):
        for value in ['-1%', '100.1%', 'NaN', 'Infinity']:
            with self.assertRaises(ValueError):
                options(value)
