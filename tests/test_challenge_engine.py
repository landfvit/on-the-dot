"""No database or wall clock: cover the full score and answer transition matrix."""
import unittest
from copy import deepcopy
from api import challenge_engine as g


def deck(size=50):
    return [dict(key=str(i),question_id=str(i),text='Question '+str(i),
                 options=[{'id':str(n),'text':str(n)} for n in range(4)],correct='0',
                 explanation='Explanation',authority='database',difficulty=['easy','medium','hard'][i%3]) for i in range(size)]


class ChallengeEngineTests(unittest.TestCase):
    def friend(self):
        s=g.friend_create('a','Alice','easy',1000);s['deck']=deck()
        g.penalty.join(s,'b','Bob',1000)
        for p in ('a','b'):g.penalty.ready(s,p,1000)
        g.friend_tick(s,5000)
        return s

    def test_answer_matrix_and_boundary(self):
        for shot in (False,True):
            for keeper in (False,True):
                for gap in (-1000,-150,-149,0,149,150,1000):
                    with self.subTest(shot=shot,keeper=keeper,gap=gap):
                        a={'correct':shot,'elapsed_ms':2000+gap};b={'correct':keeper,'elapsed_ms':2000}
                        expected=('replay' if abs(gap)<150 else 'goal' if gap<0 else 'save') if shot and keeper else 'goal' if shot else 'save' if keeper else 'replay'
                        self.assertEqual(g.friend_outcome(a,b,150),expected)

    def test_replay_consumes_question_not_penalty(self):
        s=self.friend()
        for pid in ('a','b'):g.friend_submit(s,pid,1,'1',pid,5500)
        self.assertEqual(s['round']['outcome'],'replay')
        self.assertEqual(s['attempts'],[0,0]);self.assertEqual(s['shooter'],0)
        g.penalty.schedule(s,12000)
        self.assertEqual(s['round']['id'],2);self.assertEqual(s['round']['replay_of'],1)

    def test_server_redaction_and_idempotency(self):
        s=self.friend();g.friend_submit(s,'a',1,'0','req',5500)
        for pid in ('a','b'):
            v=g.penalty.view(s,pid,5500)
            self.assertNotIn('correct',v['question']);self.assertNotIn('answers',v['round']);self.assertNotIn('deck',v)
        frozen=deepcopy(s);g.friend_submit(s,'a',1,'0','req',5600);self.assertEqual(s,frozen)
        with self.assertRaises(g.penalty.GameError):g.friend_submit(s,'a',1,'1','req',5600)
        g.friend_submit(s,'b',1,'1','b',6000)
        self.assertEqual(s['score'],[1,0]);self.assertEqual(s['shooter'],1)
        g.penalty.schedule(s,12000);frozen=deepcopy(s)
        g.friend_submit(s,'a',1,'0','req',12500);self.assertEqual(s,frozen)

    def test_sporting_clinch_and_sudden_death(self):
        self.assertEqual(g.sporting_winner([4,2],[4,4]),0)
        self.assertIsNone(g.sporting_winner([5,4],[5,4]))
        self.assertIsNone(g.sporting_winner([5,5],[5,5]))
        self.assertIsNone(g.sporting_winner([6,5],[6,5]))
        self.assertEqual(g.sporting_winner([6,5],[6,6]),0)
        # All reachable first-five score combinations must use remaining kicks.
        for a in range(6):
            for b in range(6):
                if abs(a-b)>1:continue
                for x in range(a+1):
                    for y in range(b+1):
                        expected=0 if x>y+5-b else 1 if y>x+5-a else None
                        self.assertEqual(g.sporting_winner([x,y],[a,b]),expected)

    def test_timeout_and_disconnect(self):
        s=self.friend();g.friend_submit(s,'a',1,'0','a',5500)
        g.friend_tick(s,20000);self.assertEqual(s['score'],[1,0])
        s['players'][0]['seen']=51000
        g.friend_tick(s,51000);self.assertEqual(s['winner'],0)
        self.assertEqual(s['reason'],'disconnect_forfeit')

    def test_two_unanswered_questions_end_abandoned_not_draw(self):
        s=self.friend();g.friend_tick(s,20000)
        g.penalty.schedule(s,26000);g.friend_tick(s,45000)
        self.assertEqual(s['phase'],'ABANDONED');self.assertIsNone(s['winner'])
        self.assertEqual(s['attempts'],[0,0])

    def test_daily_exhaustion_and_exact_xp(self):
        s=g.daily_create(deck(3),1000,100000)
        for i in range(3):
            g.solo.advance(s,i,2000+i*1000)
            g.daily_answer(s,i+1,'0',str(i),2100+i*1000)
        v=g.daily_view(s,5000)
        self.assertFalse(v['won']);self.assertEqual(v['survival']['goals'],3);self.assertEqual(v['total_xp'],60)
        self.assertEqual(v['bonus_xp'],0);self.assertEqual(v['multiplier'],1)
        self.assertEqual([a['xp'] for a in v['review']],[10,20,30])

    def test_daily_third_mistake_ends_run(self):
        s=g.daily_create(deck(6),1000,100000)
        for i in range(3):
            g.solo.advance(s,i,2000+i*1000)
            g.daily_answer(s,i+1,'1',str(i),2100+i*1000)
        self.assertFalse(g.daily_view(s,10000)['won'])
        self.assertEqual(s['phase'],'FINISHED');self.assertEqual(s['end_reason'],'lives_exhausted')
        self.assertEqual(g.daily_view(s,10000)['survival']['lives'],0)
        with self.assertRaises(g.solo.SoloError):g.solo.advance(s,3,10000)

    def test_daily_over_fifty_goals_never_switches_role_or_clinches(self):
        s=g.daily_create(deck(1000),1000,1000000)
        for i in range(75):
            g.solo.advance(s,i,2000+i*1000);g.daily_answer(s,i+1,'0',str(i),2100+i*1000)
            v=g.daily_view(s,2200+i*1000)
            self.assertEqual(s['phase'],'REVIEW');self.assertEqual(v['role'],'shooter')
            self.assertNotIn('shootout',v);self.assertEqual(v['survival']['lives'],3)
        self.assertEqual(v['survival']['goals'],75)

    def test_daily_timeouts_and_retries_consume_exactly_one_life(self):
        s=g.daily_create(deck(),1000,1000000)
        for i in range(3):
            g.solo.advance(s,i,2000+i*20000)
            g.daily_tick(s,s['deadline']);snapshot=deepcopy(s);g.daily_tick(s,s['deadline']+1)
            self.assertEqual(snapshot,s);self.assertEqual(len(s['history']),i+1)
        self.assertEqual(s['phase'],'FINISHED');self.assertEqual(g.daily_view(s,90000)['survival']['lives'],0)

    def test_daily_answer_idempotency_privacy_and_practice_flag(self):
        s=g.daily_create(deck(),1000,100000,ranked=False);g.solo.advance(s,0,2000)
        v=g.daily_view(s,2000);self.assertNotIn('deck',v);self.assertNotIn('correct',v['question'])
        self.assertFalse(v['survival']['ranked'])
        g.daily_answer(s,1,'1','retry',2100);frozen=deepcopy(s)
        g.daily_answer(s,1,'1','retry',2200);self.assertEqual(frozen,s)
        with self.assertRaises(g.solo.SoloError):g.daily_answer(s,1,'0','retry',2200)

    def test_third_error_on_last_question_is_not_pool_completion(self):
        s=g.daily_create(deck(3),1000,100000)
        for i in range(3):
            g.solo.advance(s,i,2000+i*1000);g.daily_answer(s,i+1,'1',str(i),2100+i*1000)
        self.assertEqual(s['end_reason'],'lives_exhausted')

    def test_long_run_ends_at_daily_reset_not_solo_thirty_minute_limit(self):
        s=g.daily_create(deck(),1000,10000000)
        g.daily_tick(s,2000000);self.assertEqual(s['phase'],'READY')
        g.daily_tick(s,10000000);self.assertEqual(s['end_reason'],'daily_reset')

    def test_empty_daily_and_utc_reset(self):
        with self.assertRaises(g.solo.SoloError):g.daily_create([],1000,2000)
        s=g.daily_create(deck(),1000,2000);g.solo.advance(s,0,1500);g.daily_tick(s,2000)
        self.assertEqual(s['end_reason'],'daily_reset');self.assertFalse(g.daily_view(s,2000)['won'])


if __name__=='__main__':unittest.main()
