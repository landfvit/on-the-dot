from copy import deepcopy
from itertools import product
import unittest
from api import solo_engine as game
from tests.test_solo_engine import deck


def step(state,correct):
    n=state['position']
    if n==len(state['deck']):
        extra=deepcopy(deck()[:2])
        for i,q in enumerate(extra):q['key']=str(n+i)
        state['deck'].extend(extra)
    game.advance(state,n,n*1000)
    game.answer(state,n+1,'1' if correct else '0',str(n),n*1000+100)


class ShootoutTests(unittest.TestCase):
    def create(self):return game.create(deck(),'hard',{},0)

    def test_all_initial_sequences_against_independent_remaining_kicks_rule(self):
        for results in product([False,True],repeat=10):
            s=self.create();goals=[0,0];used=[0,0]
            for i,correct in enumerate(results):
                step(s,correct);side=i%2;used[side]+=1
                goals[side]+=int(correct if side==0 else not correct)
                expected=next((j for j in [0,1] if goals[j]-goals[1-j]>5-used[1-j]),None)
                self.assertEqual(s['phase']=='FINISHED',expected is not None)
                if expected is not None:
                    self.assertEqual(game.shootout(s)['winner'],['player','opponent'][expected]);break

    def test_perfect_game_finishes_three_nil_after_six_answers(self):
        s=self.create()
        for _ in range(6):step(s,True)
        self.assertEqual(game.shootout(s)['player'],3)
        self.assertEqual(game.rewards(s)['total_xp'],720)
        self.assertTrue(game.rewards(s)['streak_eligible'])
        with self.assertRaises(game.SoloError):game.advance(s,6,7000)

    def test_five_four_requires_opponents_last_kick_and_equal_sudden_death(self):
        s=self.create()
        for correct in [True,False]*4+[True]:step(s,correct)
        self.assertEqual(s['phase'],'REVIEW');self.assertIsNone(game.shootout(s)['winner'])
        step(s,False) # 5:5
        for _ in range(20):
            step(s,True);self.assertIsNone(game.shootout(s)['winner'])
            step(s,False);self.assertEqual(s['phase'],'REVIEW')
        step(s,True);step(s,True)
        self.assertEqual(s['phase'],'FINISHED');self.assertEqual(game.shootout(s)['winner'],'player')
        self.assertEqual(len(s['history']),52)

    def test_goal_and_save_roles_and_timeouts(self):
        s=self.create();step(s,True);step(s,True)
        self.assertEqual([a['outcome'] for a in s['history']],['goal','save'])
        for role in ['shooter','keeper']:
            n=s['position'];game.advance(s,n,n*1000);game.tick(s,s['deadline'])
            a=s['history'][-1];self.assertEqual(a['role'],role)
            self.assertEqual(a['outcome'],'miss' if role=='shooter' else 'goal')
        self.assertFalse(game.rewards(s)['streak_eligible'])

    def test_reload_and_retries_do_not_recount_a_kick(self):
        s=self.create();step(s,True);before=deepcopy(s)
        game.answer(s,1,'1','0',100)
        self.assertEqual(s,before)
        public=game.view(s,100)
        self.assertEqual(public['shootout']['player'],1)
        self.assertNotIn('deck',public)

    def test_nonperfect_win_gets_difficulty_multiplier_and_losses_do_not(self):
        for difficulty,rate,multiplier in [('easy',10,2),('medium',20,3),('hard',30,4)]:
            s=game.create(deck(),difficulty,{},0)
            for correct in [False,True,True,True,True,False,True,True]:step(s,correct)
            r=game.rewards(s)
            self.assertTrue(r['won']);self.assertFalse(r['perfect'])
            self.assertEqual(r['total_xp'],6*rate*multiplier)
            losing=game.create(deck(),difficulty,{},0)
            for correct in [True,False,False,False,False,False,False]:step(losing,correct)
            self.assertEqual(losing['phase'],'FINISHED')
            self.assertEqual(game.rewards(losing)['total_xp'],rate)
            losing['phase']='ABANDONED';self.assertEqual(game.rewards(losing)['bonus_xp'],0)

    def test_frozen_v4_perfect_bonus_does_not_change(self):
        s=self.create();s['rules'].pop('bonus_mode')
        for _ in range(6):step(s,True)
        self.assertEqual(game.rewards(s)['total_xp'],540)
