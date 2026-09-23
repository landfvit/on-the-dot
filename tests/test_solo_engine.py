from copy import deepcopy
from datetime import date,timedelta
import unittest
from unittest.mock import patch

from api import solo_engine as game
from api.player_accounts import password_hash,verify_password,Credentials


def deck():
    return [{'key':str(i),'text':f'Question {i}','options':[{'id':str(j),'text':str(j)} for j in range(4)],
             'correct':'1','explanation':'One','authority':'database_matched'} for i in range(10)]


def play(difficulty='easy',correct=10,timeout=False):
    s=game.create(deck(),difficulty,{'code':'ALL','label':'All clubs'},0)
    for i in range(10):
        now=i*20000;game.advance(s,i,now)
        if timeout and i==9:game.tick(s,now+s['rules']['answer_ms'])
        else:game.answer(s,i+1,'1' if i<correct else '0',str(i),now+1000)
    return s


class SoloEngineTests(unittest.TestCase):
    def setUp(self):
        # Historical ten-question runs must retain their original scoring contract.
        legacy={**game.RULES,'version':'solo-v3'};legacy.pop('format',None)
        legacy.pop('bonus_mode',None)
        p=patch.dict(game.RULES,legacy,clear=True);p.start();self.addCleanup(p.stop)
    def test_all_score_and_difficulty_combinations(self):
        for difficulty,multiplier in [('easy',1),('medium',2),('hard',3)]:
            for correct in range(11):
                with self.subTest(difficulty=difficulty,correct=correct):
                    s=play(difficulty,correct);r=game.rewards(s)
                    self.assertEqual(r['total_xp'],correct*10*multiplier*(multiplier if correct==10 else 1))
                    self.assertEqual(r['streak_eligible'],True)
                    self.assertEqual(r['perfect'],correct==10)

    def test_timeout_is_not_a_streak_answer(self):
        s=play('hard',10,True);r=game.rewards(s)
        self.assertEqual(r['total_xp'],270);self.assertFalse(r['streak_eligible']);self.assertEqual(s['phase'],'FINISHED')

    def test_exact_deadline_reload_and_duplicate_next(self):
        s=game.create(deck(),'easy',{},0);game.advance(s,0,100)
        before=deepcopy(s);game.advance(s,0,3000);self.assertEqual(before,s)
        self.assertEqual(s['deadline'],15100)
        with self.assertRaises(game.SoloError):game.answer(s,1,'1','a',15100)
        game.tick(s,15100);self.assertEqual(s['history'][0]['option_id'],None)
        self.assertEqual(s['history'][0]['elapsed_ms'],15000)

    def test_answer_after_ten_seconds_is_accepted_and_old_rules_stay_frozen(self):
        s=game.create(deck(),'easy',{},0);game.advance(s,0,100)
        game.answer(s,1,'1','a',15099)
        self.assertTrue(s['history'][0]['correct'])
        old=game.create(deck(),'easy',{},0);old['rules'].update(version='solo-v2',answer_ms=10000)
        game.advance(old,0,100);self.assertEqual(old['deadline'],10100)
        game.tick(old,10100);self.assertIsNone(old['history'][0]['option_id'])

    def test_answer_retries_are_idempotent_and_cannot_change_choice(self):
        s=game.create(deck(),'easy',{},0);game.advance(s,0,100)
        game.answer(s,1,'1','a',500);before=deepcopy(s);game.answer(s,1,'1','a',600)
        self.assertEqual(before,s)
        with self.assertRaises(game.SoloError):game.answer(s,1,'0','a',600)
        game.advance(s,1,700)
        with self.assertRaises(game.SoloError):game.answer(s,2,'1','a',800)

    def test_future_questions_and_answers_are_hidden(self):
        s=game.create(deck(),'easy',{},0)
        self.assertIsNone(game.view(s,0)['question'])
        game.advance(s,0,0);v=game.view(s,0)
        self.assertEqual(set(v['question']),{'text','options'});self.assertEqual(v['review'],[]);self.assertNotIn('deck',v)
        game.answer(s,1,'0','a',1000);v=game.view(s,1000)
        self.assertEqual(v['review'][0]['correct'],'1');self.assertFalse(v['review'][0]['is_correct'])

    def test_restart_and_abandonment_preserve_earned_xp(self):
        s=game.create(deck(),'hard',{},0);game.advance(s,0,0);game.answer(s,1,'1','a',1000)
        game.tick(s,1800000);self.assertEqual(s['phase'],'ABANDONED');self.assertEqual(game.rewards(s)['total_xp'],30)
        self.assertFalse(game.rewards(s)['streak_eligible'])

    def test_frozen_rules_and_deck_do_not_alias(self):
        d=deck();s=game.create(d,'easy',{},0);d[0]['correct']='0';self.assertEqual(s['deck'][0]['correct'],'1')
        self.assertIsNot(s['rules']['perfect_multipliers'],game.RULES['perfect_multipliers'])
        with self.assertRaises(game.SoloError):game.create(d[:9],'easy',{},0)

    def test_streak_duplicates_gaps_today_and_yesterday(self):
        today=date(2026,9,21);yesterday=today-timedelta(days=1)
        self.assertEqual(game.streak([],today),{'current':0,'longest':0,'completed_today':False})
        self.assertEqual(game.streak([yesterday,yesterday,today],today),{'current':2,'longest':2,'completed_today':True})
        self.assertEqual(game.streak([today-timedelta(days=3),today-timedelta(days=2)],today)['current'],0)
        self.assertEqual(game.streak([yesterday],today)['current'],1)

    def test_password_salted_hash_and_username_canonicalization(self):
        first=password_hash('test-password-12345');second=password_hash('test-password-12345')
        self.assertNotEqual(first,second);self.assertTrue(verify_password('test-password-12345',first))
        self.assertFalse(verify_password('wrong-password-12345',first));self.assertFalse(verify_password('x','broken'))
        self.assertEqual(Credentials(username='Some_Player',password='test-password-12345').username,'some_player')
