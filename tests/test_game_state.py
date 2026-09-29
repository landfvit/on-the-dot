from copy import deepcopy
import unittest
from api import challenge_engine as game
from api.game_state import QuestionWindow,checkpoint,progress


class QuestionWindowTests(unittest.TestCase):
    def test_total_length_does_not_shrink_to_loaded_prefix(self):
        deck=QuestionWindow([{'id':1},{'id':2}],1000)
        self.assertEqual(len(deck),1000)
        self.assertEqual(deck[1],{'id':2})
        with self.assertRaises(RuntimeError):deck[2]
        with self.assertRaises(IndexError):deck[1000]
        with self.assertRaises(TypeError):deck[:]

    def test_partial_and_full_decks_produce_identical_daily_transitions(self):
        deck=[dict(question_id=str(i),difficulty='easy',correct='0',text=str(i),
                   options=[{'id':'0','text':'yes'},{'id':'1','text':'no'}],
                   explanation='',authority='test') for i in range(10)]
        for wrong in (False,True):
            full=game.daily_create(deck,100,1000000)
            for index in range(10):
                now=200+index*100
                window=deepcopy(full)
                window['deck']=QuestionWindow(full['deck'][:full['position']+1],len(full['deck']))
                for state in (full,window):game.solo.advance(state,index,now)
                self.assertEqual(game.daily_view(window,now),game.daily_view(full,now))
                # Each HTTP request reloads a prefix for the new position.
                window['deck']=QuestionWindow(full['deck'][:full['position']+1],len(full['deck']))
                for state in (full,window):game.daily_answer(state,index+1,'1' if wrong else '0',str(index),now+50)
                self.assertEqual(progress(window),progress(full))
                self.assertEqual(game.daily_view(window,now+50),game.daily_view(full,now+50))
                if full['phase']=='FINISHED':break
            self.assertEqual(full['end_reason'],'lives_exhausted' if wrong else 'daily_pool_exhausted')

    def test_checkpoint_copies_progress_without_copying_questions(self):
        deck=QuestionWindow([{'id':1}],1000)
        state={'deck':deck,'history':[],'position':0}
        before=checkpoint(state)
        state['history'].append({'correct':True})
        self.assertEqual(before,({'history':[],'position':0},1000))
