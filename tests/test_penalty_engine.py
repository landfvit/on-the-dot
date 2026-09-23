import json
from decimal import Decimal
import re
import unittest
from api import penalty_engine as game
from api.penalty_questions import maths_pack


def deck():
    return [{'text':f'Question {i}','options':[{'id':str(j),'text':str(j)} for j in range(4)],
        'correct':'1','explanation':'One','key':str(i)} for i in range(100)]


def started(mode='pvp',first=0):
    state=game.create(mode,'a','Alice',deck(),0,first)
    if mode=='pvp':game.join(state,'b','Bob',0);game.ready(state,'b',0)
    game.ready(state,'a',0);game.tick(state,3000)
    return state


class PenaltyEngineTests(unittest.TestCase):
    def test_lobby_camera_roles_follow_randomised_server_shooter(self):
        for first in (0, 1):
            s=game.create('pvp','a','Alice',deck(),0,first)
            game.join(s,'b','Bob',0)
            for player,me in [('a',0),('b',1)]:
                view=game.view(s,player,1000)
                self.assertEqual(view['initial_shooter'],first)
                self.assertEqual(view['me'],me)
                self.assertIsNone(view['question'])
                self.assertIsNone(view['round'])
            # Intro completion itself is not a game command. Only both Ready
            # messages schedule the original, unchanged countdown/deadline.
            game.ready(s,'a',8000)
            self.assertEqual(s['phase'],'LOBBY')
            game.ready(s,'b',9000)
            self.assertEqual(s['round']['opens_at'],12000)
            self.assertEqual(s['round']['deadline'],24000)

    def test_no_answer_or_question_leaks_before_opening(self):
        s=game.create('pvp','a','Alice',deck(),0)
        game.join(s,'b','Bob',0);game.ready(s,'a',0);game.ready(s,'b',0)
        v=game.view(s,'a',1000)
        self.assertIsNone(v['question']);self.assertNotIn('deck',v)
        game.tick(s,3000);game.submit(s,'a',1,'1','a1',3200)
        for player in ('a','b'):
            v=game.view(s,player,3200)
            self.assertNotIn('correct',v['question']);self.assertNotIn('answers',v['round'])
            self.assertEqual(v['stats'][0]['correct'],0)
        self.assertIsNone(game.view(s,'b',3200)['round']['own_option'])

    def test_deadline_and_early_answers_rejected(self):
        for instant in (2999,15000,15001):
            s=started()
            with self.subTest(instant=instant),self.assertRaises(game.GameError):game.submit(s,'a',1,'1','x',instant)
        s=started();game.submit(s,'a',1,'1','x',14999)
        game.tick(s,15000);self.assertEqual(s['round']['outcome'],'goal')

    def test_duplicate_cannot_replace_answer_or_double_score(self):
        s=started();game.submit(s,'a',1,'1','x',4000)
        self.assertFalse(game.submit(s,'a',1,'1','x',4001))
        with self.assertRaises(game.GameError):game.submit(s,'a',1,'2','y',4002)
        game.submit(s,'b',1,'0','z',5000)
        game.tick(s,5100);self.assertEqual(s['score'],[1,0]);self.assertEqual(len(s['history']),1)

    def test_replay_consumes_new_question_without_changing_roles(self):
        s=started();game.submit(s,'a',1,'1','x',4000);game.submit(s,'b',1,'1','y',4080)
        self.assertEqual(s['score'],[0,0]);self.assertEqual(s['attempts'],[0,0])
        for p in s['players']:p['seen']=6600
        game.tick(s,6600);self.assertEqual(s['round']['id'],2);self.assertEqual(s['round']['shooter'],0)
        self.assertEqual(s['round']['pair'],1)

    def test_equalising_shot_and_sudden_death(self):
        s=started();s['score']=[9,9]
        game.submit(s,'a',1,'1','x',4000);game.submit(s,'b',1,'0','y',4200)
        self.assertEqual(s['phase'],'RESOLVED');self.assertEqual(s['score'],[10,9])
        for p in s['players']:p['seen']=7000
        game.tick(s,7000);game.tick(s,10000)
        game.submit(s,'a',2,'0','x2',11000);game.submit(s,'b',2,'1','y2',11200)
        self.assertEqual(s['phase'],'RESOLVED');self.assertEqual(s['score'],[10,10])
        self.assertEqual(s['pair'],2)

    def test_equaliser_missed_finishes_with_leader(self):
        s=started(first=1);s['score']=[10,9];s['slot']=1
        game.submit(s,'b',1,'0','x',4000);game.submit(s,'a',1,'0','y',4200)
        self.assertEqual(s['phase'],'FINISHED');self.assertEqual(s['winner'],0)

    def test_timeout_rotates_without_goal(self):
        s=started();game.tick(s,15000)
        self.assertEqual(s['round']['outcome'],'miss');self.assertEqual(s['shooter'],1)
        self.assertEqual([p['timeouts'] for p in s['stats']],[1,1])

    def test_solo_completion(self):
        s=started('solo');s['attempts'][0]=9
        game.submit(s,'a',1,'1','x',4000)
        self.assertEqual(s['phase'],'FINISHED');self.assertEqual(s['reason'],'solo_complete')

    def test_small_approved_pack_is_a_shorter_solo_series(self):
        s=game.create('solo','a','Alice',deck()[:1],0)
        self.assertEqual(s['rules']['solo_shots'],1)
        game.ready(s,'a',0);game.tick(s,3000);game.submit(s,'a',1,'1','x',4000)
        self.assertEqual(s['phase'],'FINISHED');self.assertEqual(s['reason'],'solo_complete')

    def test_solo_waits_for_explicit_next_even_after_animation_finishes(self):
        s=started('solo');game.submit(s,'a',1,'1','x',4000)
        game.tick(s,8000);self.assertEqual(s['phase'],'RESOLVED');self.assertEqual(s['cursor'],1)

    def test_disconnection_forfeit_only_between_penalties(self):
        s=started();game.tick(s,15000)
        s['players'][0]['seen']=21000;game.tick(s,21000)
        self.assertEqual(s['reason'],'disconnect_forfeit');self.assertEqual(s['winner'],0)

    def test_server_gap_is_not_a_player_loss(self):
        s=started();game.tick(s,29000)
        self.assertEqual(s['phase'],'ABANDONED');self.assertIsNone(s['winner'])
        self.assertEqual(s['reason'],'technical_interruption')

    def test_pool_exhaustion_and_duration_have_no_winner(self):
        s=started();s['cursor']=len(s['deck']);game.schedule(s,4000)
        self.assertEqual(s['reason'],'question_pool_exhausted');self.assertIsNone(s['winner'])
        s=started();game.tick(s,1800001);self.assertEqual(s['reason'],'time_limit')

    def test_refresh_restores_same_deadline_and_locked_answer(self):
        s=started();game.submit(s,'a',1,'1','x',4000)
        restored=json.loads(json.dumps(s));game.tick(restored,5000)
        self.assertEqual(game.view(restored,'a',5000)['round']['own_option'],'1')
        self.assertEqual(restored['round']['deadline'],15000)

    def test_unknown_player_or_option_rejected(self):
        s=started()
        for player,option in [('outsider','1'),('a','9')]:
            with self.assertRaises(game.GameError):game.submit(s,player,1,option,'x',4000)

    def test_maths_questions_unique_and_pairs_comparable(self):
        questions=maths_pack();self.assertEqual(len(questions),80)
        self.assertEqual(len({q['text'] for q in questions}),80)
        for i,q in enumerate(questions):
            self.assertEqual(len({o['text'] for o in q['options']}),4)
            self.assertIn(q['correct'],{o['id'] for o in q['options']})
            self.assertEqual(q['group'],questions[i//2*2]['group'])

    def test_all_eighty_arithmetic_answers_have_independent_oracles(self):
        for q in maths_pack():
            numbers=list(map(Decimal,re.findall(r'\d+',q['text'])))
            expected={0:lambda:numbers[0]/numbers[1]*100,1:lambda:numbers[0]*3+numbers[1],
                2:lambda:numbers[0]/numbers[1],3:lambda:numbers[0]-numbers[1]}[q['group']]()
            selected=next(o['text'] for o in q['options'] if o['id']==q['correct'])
            with self.subTest(question=q['key']):self.assertEqual(Decimal(selected.removesuffix(' %')),expected)


def outcome_case(shooter_correct,keeper_correct,difference):
    def test(self):
        a={'correct':shooter_correct,'elapsed_ms':3000+difference}
        b={'correct':keeper_correct,'elapsed_ms':3000}
        expected=('replay' if abs(difference)<150 else 'goal' if difference<0 else 'save') if shooter_correct and keeper_correct else (
            'goal' if shooter_correct else 'save' if keeper_correct else 'miss')
        self.assertEqual(game.outcome(a,b),expected)
    return test


for a in (False,True):
    for b in (False,True):
        for delta in (-1000,-151,-150,-149,-1,0,1,149,150,151,1000):
            setattr(PenaltyEngineTests,f'test_outcome_{a}_{b}_{delta}',outcome_case(a,b,delta))
