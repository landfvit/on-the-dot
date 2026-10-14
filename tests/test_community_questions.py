"""Rollback-only integration tests. Never publish test questions or accounts."""
from contextlib import contextmanager
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from api.database import get_connection
from api import challenge_engine
from trivia_app.main import app


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Local rollback-only database tests')
class CommunityQuestionsTests(unittest.TestCase):
    def setUp(self):
        self.conn=get_connection()
        self.assertIn(self.conn.info.host,('localhost','127.0.0.1','::1',''))
        self.addCleanup(self.conn.close);self.addCleanup(self.conn.rollback)
        @contextmanager
        def shared():yield self.conn
        for module in ['api.player_accounts','api.community_questions','api.challenge_routes']:
            for field,value in [('get_connection',shared),('rate_limit',lambda *a:None)]:
                p=patch(module+'.'+field,value);p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{'TRIVIA_EDITOR_USERNAME':'review-test','TRIVIA_EDITOR_PASSWORD':'local-test-password-only'});p.start();self.addCleanup(p.stop)
        self.auth=('review-test','local-test-password-only')
        self.client,self.friend=TestClient(app),TestClient(app)
        for client in (self.client,self.friend):
            name='q_'+uuid4().hex[:16]
            r=client.post('/api/players/register',json={'username':name,'email':name+'@example.com','password':'local-test-password-only'})
            self.assertEqual(r.status_code,201,r.text)

    def body(self):
        return {'question':'Which club is the example club '+uuid4().hex[:8]+'?',
                'options':['Arsenal','Chelsea','Liverpool','Everton'],'correct':0,'difficulty':'medium',
                'topic':'Club identity','explanation':'A note for the reviewer.'}

    def create(self,body=None):
        body=body or self.body();body={**body,'request_id':str(uuid4())}
        r=self.client.post('/api/players/questions',json=body);self.assertEqual(r.status_code,201,r.text)
        return r.json(),body

    def test_validation_auth_and_csrf(self):
        self.assertEqual(TestClient(app).get('/api/players/questions').status_code,401)
        self.assertEqual(self.client.get('/api/trivia/community-questions').status_code,401)
        for changes in [{'options':['A','a','C','D']},{'correct':4},{'correct':True},{'source_url':'javascript:alert(1)'},{'topic':'Unknown'},{'question':'Short'}]:
            r=self.client.post('/api/players/questions',json={**self.body(),**changes,'request_id':str(uuid4())})
            self.assertEqual(r.status_code,422,r.text)
        r=self.client.post('/api/players/questions',json={**self.body(),'request_id':str(uuid4())},headers={'Origin':'https://foreign.example'})
        self.assertEqual(r.status_code,403)

    def test_owner_revision_and_idempotency(self):
        row,body=self.create();path='/api/players/questions/'+row['submission_id']
        r=self.client.post('/api/players/questions',json=body);self.assertEqual(r.json()['submission_id'],row['submission_id'])
        changed={**row['content'],'revision':1,'question':'A revised and sufficiently long question?'}
        self.assertEqual(self.friend.put(path,json=changed).status_code,404)
        self.assertEqual(self.client.put(path,json=changed).status_code,200)
        self.assertEqual(self.client.put(path,json=changed).status_code,409)
        mine=self.friend.get('/api/players/questions').json();self.assertEqual(len(mine['questions']),0)

    def test_source_is_not_required_for_review_or_private_play(self):
        row,_=self.create()
        r=self.client.post('/api/players/questions/'+row['submission_id']+'/submit',json={'revision':1})
        self.assertEqual(r.status_code,200,r.text)
        r=self.client.post('/api/friends/rooms',json={'request_id':str(uuid4()),'question_ids':[row['submission_id']]})
        self.assertEqual(r.status_code,201,r.text);self.assertEqual(r.json()['custom_count'],1)

    def test_review_reject_edit_resubmit_and_publish(self):
        row,_=self.create();path='/api/players/questions/'+row['submission_id'];review='/api/trivia/community-questions/'+row['submission_id']+'/review'
        baseline=self.conn.execute('SELECT count(*) n FROM penalty_bank_questions').fetchone()['n']
        self.assertEqual(self.client.post(path+'/submit',json={'revision':1}).status_code,200)
        decision={'revision':1,'decision':'rejected','note':'Please clarify the season.'}
        self.assertEqual(self.client.post(review,json=decision,auth=self.auth).status_code,200)
        self.assertEqual(self.client.post(path+'/submit',json={'revision':1}).status_code,409)
        self.assertEqual(self.client.put(path,json={**row['content'],'revision':1}).status_code,200)
        self.assertEqual(self.client.post(path+'/submit',json={'revision':2}).status_code,200)
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM penalty_bank_questions').fetchone()['n'],baseline)
        decision.update(revision=2,decision='approved',note='Verified against the reference.')
        self.assertEqual(self.client.post(review,json=decision,auth=self.auth).status_code,422)
        r=self.client.post(review,json={**decision,'verified':True},auth=self.auth);self.assertEqual(r.status_code,200,r.text)
        self.conn.execute('SET CONSTRAINTS ALL IMMEDIATE')
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM penalty_bank_questions').fetchone()['n'],baseline+1)
        self.assertEqual(self.client.post(review,json={**decision,'verified':True},auth=self.auth).status_code,409)
        self.assertEqual(self.client.put(path,json={**row['content'],'revision':2}).status_code,409)
        q=self.conn.execute('SELECT p.question FROM penalty_bank_questions p JOIN game_question_submissions s USING(release_id,question_id) WHERE submission_id=%s',(row['submission_id'],)).fetchone()['question']
        self.assertEqual(q['authority'],'user_attested');self.assertEqual(q['source']['verification_method'],'editor_reviewed')
        self.assertEqual(len(self.client.get('/api/trivia/community-questions?status=approved',auth=self.auth).json()['questions']),1)

    def test_custom_duel_freezes_draft_hides_answers_and_draws_without_bank(self):
        row,_=self.create();payload={'request_id':str(uuid4()),'question_ids':[row['submission_id']]}
        created=self.client.post('/api/friends/rooms',json=payload);self.assertEqual(created.status_code,201,created.text)
        s=created.json();path='/api/friends/rooms/'+s['code'];ident=s['run_id']
        self.assertNotIn('deck',s);self.assertIsNone(s['question'])
        self.assertEqual(self.client.post('/api/friends/rooms',json={**payload,'bank_fallback':True}).status_code,409)
        self.assertEqual(self.client.put('/api/players/questions/'+row['submission_id'],json={**row['content'],'revision':1,'question':'A changed question after the invitation?'}).status_code,200)
        self.assertEqual(self.friend.post(path+'/join',json={}).status_code,200)
        for client in (self.client,self.friend):self.assertEqual(client.post(path+'/ready',json={}).status_code,200)
        frozen=self.conn.execute('SELECT state FROM game_mode_runs WHERE run_id=%s',(ident,)).fetchone()['state']
        self.assertEqual(frozen['deck'][0]['text'],row['content']['question'])
        wrong=next(o['id'] for o in frozen['deck'][0]['options'] if o['id']!=frozen['deck'][0]['correct'])
        with patch('api.challenge_routes.now_ms',return_value=frozen['round']['opens_at']+500):
            self.assertNotIn('correct',self.friend.get(path).json()['question'])
            for client in (self.client,self.friend):
                r=client.post(path+'/answers',json={'position':1,'option_id':wrong,'request_id':str(uuid4())});self.assertEqual(r.status_code,200,r.text)
        with patch('api.challenge_routes.now_ms',return_value=frozen['round']['opens_at']+500+frozen['rules']['result_ms']):
            r=self.client.get(path);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['phase'],'FINISHED');self.assertIsNone(r.json()['winner']);self.assertEqual(r.json()['reason'],'custom_questions_complete')
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM game_mode_seen WHERE run_id=%s',(ident,)).fetchone()['n'],0)
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM game_mode_xp WHERE run_id=%s',(ident,)).fetchone()['n'],0)

    def test_another_authors_questions_forbidden(self):
        row,_=self.create()
        r=self.friend.post('/api/friends/rooms',json={'request_id':str(uuid4()),'question_ids':[row['submission_id']]})
        self.assertEqual(r.status_code,404)
        r=self.client.post('/api/friends/rooms',json={'request_id':str(uuid4()),'question_ids':[row['submission_id']]*2})
        self.assertEqual(r.status_code,422)

    def test_optional_bank_fallback_is_frozen_and_only_adds_after_custom(self):
        row,_=self.create();payload={'request_id':str(uuid4()),'question_ids':[row['submission_id']],'bank_fallback':True,'difficulty':'easy'}
        r=self.client.post('/api/friends/rooms',json=payload);self.assertEqual(r.status_code,201,r.text)
        s=r.json();path='/api/friends/rooms/'+s['code']
        self.assertTrue(TestClient(app).get('/api/friends/invites/'+s['code']).json()['bank_fallback'])
        self.friend.post(path+'/join',json={})
        for client in (self.client,self.friend):client.post(path+'/ready',json={})
        state=self.conn.execute('SELECT state FROM game_mode_runs WHERE run_id=%s',(s['run_id'],)).fetchone()['state']
        self.assertEqual(len(state['deck']),1)
        wrong=next(o['id'] for o in state['deck'][0]['options'] if o['id']!=state['deck'][0]['correct'])
        with patch('api.challenge_routes.now_ms',return_value=state['round']['opens_at']+500):
            for client in (self.client,self.friend):
                r=client.post(path+'/answers',json={'position':1,'option_id':wrong,'request_id':str(uuid4())});self.assertEqual(r.status_code,200,r.text)
        with patch('api.challenge_routes.now_ms',return_value=state['round']['opens_at']+500+state['rules']['result_ms']):
            r=self.client.get(path);self.assertEqual(r.status_code,200,r.text)
        latest=self.conn.execute('SELECT state FROM game_mode_runs WHERE run_id=%s',(s['run_id'],)).fetchone()['state']
        self.assertGreater(len(latest['deck']),1);self.assertEqual(latest['deck'][0],state['deck'][0]);self.assertFalse(any(q.get('custom') for q in latest['deck'][1:]))
        self.assertEqual(r.json()['phase'],'COUNTDOWN')

    def test_stale_review_and_blocked_author(self):
        row,_=self.create();path='/api/players/questions/'+row['submission_id'];review='/api/trivia/community-questions/'+row['submission_id']+'/review'
        self.client.post(path+'/submit',json={'revision':1})
        self.client.put(path,json={**row['content'],'revision':1,'question':'Which club is the newly edited question about?'})
        decision={'revision':1,'decision':'approved','note':'Verified source and options.','verified':True}
        self.assertEqual(self.client.post(review,json=decision,auth=self.auth).status_code,409)
        self.client.post(path+'/submit',json={'revision':2})
        self.conn.execute('UPDATE game_accounts SET blocked_at=clock_timestamp() WHERE account_id=(SELECT owner_id FROM game_question_submissions WHERE submission_id=%s)',(row['submission_id'],))
        self.assertEqual(self.client.get('/api/players/questions').status_code,403)
        self.assertEqual(self.client.post(review,json={**decision,'revision':2},auth=self.auth).status_code,409)


class FiniteDuelTests(unittest.TestCase):
    def test_score_and_draw(self):
        for scores,winner in [([2,1],0),([1,2],1),([1,1],None)]:
            s=challenge_engine.friend_create('a','A','easy',0);s['score']=scores
            challenge_engine.friend_custom_finish(s,100)
            self.assertEqual(s['winner'],winner);self.assertEqual(s['phase'],'FINISHED')
