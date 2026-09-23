import copy
from decimal import Decimal
import unittest
from unittest.mock import MagicMock, patch

from api.penalty_questions import english_maths_view, maths_pack
from api.penalty_routes import packs


class EnglishPenaltyTests(unittest.TestCase):
    def test_all_eighty_practice_questions_are_english_and_correct(self):
        questions=maths_pack()
        self.assertEqual(len(questions),80)
        for question in questions:
            with self.subTest(key=question['key']):
                _,kind,number=question['key'].split(':')
                n=int(number)
                expected=[f'{n*4} %',str(n*3+3),f'{n/2:g}',str(24-n)][int(kind)]
                self.assertTrue(question['text'].startswith('A team '))
                self.assertTrue(question['text'].isascii())
                self.assertTrue(question['explanation'].isascii())
                actual=next(o['text'] for o in question['options'] if o['id']==question['correct'])
                self.assertEqual(Decimal(actual.removesuffix(' %')),Decimal(expected.removesuffix(' %')))
                self.assertEqual(actual.endswith(' %'),expected.endswith(' %'))

    def test_legacy_wording_translation_neither_mutates_nor_exposes_answers(self):
        original={'text':'Legacy wording','options':[{'id':'b','text':'18'}]}
        saved=copy.deepcopy(original)
        translated=english_maths_view(original,'maths-v1:1:5')
        self.assertEqual(original,saved)
        self.assertEqual(set(translated),set(original))
        self.assertEqual(translated['options'],original['options'])
        self.assertIn('5 wins and 3 draws',translated['text'])
        revealed={**original,'correct':'b','explanation':'Legacy explanation'}
        translated=english_maths_view(revealed,'maths-v1:1:5')
        self.assertEqual(translated['explanation'],'5 x 3 + 3 = 18 points.')
        self.assertEqual(translated['correct'],'b')
        self.assertEqual(revealed['explanation'],'Legacy explanation')

    def test_unknown_question_keys_are_not_reinterpreted(self):
        original={'text':'A custom question','options':[]}
        for key in ['custom:1:5','maths-v1:4:5','maths-v1:1:0','maths-v1:1:21','maths-v1:1:bad','']:
            self.assertEqual(english_maths_view(original,key),original)

    def test_catalogue_practice_metadata_is_english(self):
        with patch('api.penalty_routes.get_connection',return_value=MagicMock()), \
             patch('api.penalty_routes.catalog',return_value=[]), \
             patch('api.penalty_routes.library_pack',return_value=[]):
            result=packs()['packs']
        self.assertEqual(result[0]['label'],'Football maths · practice questions')
        self.assertEqual(result[0]['language'],'EN')
        self.assertEqual(result[0]['group'],'Practice')
        self.assertEqual(result[1]['label'],'Verified POINTS questions')
        self.assertEqual(result[1]['group'],'Other packs')
