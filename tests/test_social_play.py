"""Real PostgreSQL permissions, guest sessions and public-share regression tests."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from uuid import uuid4
from PIL import Image
from fastapi.testclient import TestClient
from psycopg import Error as DatabaseError
from tests.test_challenge_database import ChallengeDatabaseTests
from trivia_app.main import app


class SocialPlayTests(ChallengeDatabaseTests):
    def add(self):
        return self.client.post('/api/players/friends',json={'username':'test_friend'})

    def end_solo(self):
        run=self.start('easy')
        self.client.post('/api/solo/runs/'+run['run_id']+'/leave',json={})
        return {'run_id':run['run_id'],'mode':'solo'}

    def test_request_requires_recipient_acceptance(self):
        self.assertEqual(self.add().json()['status'],'pending')
        self.assertEqual(self.add().json()['status'],'pending')
        self.assertEqual(self.client.post('/api/players/friends/test_friend/accept',json={}).status_code,403)
        incoming=self.friend.get('/api/players/friends').json()['friends'][0]
        self.assertTrue(incoming['incoming']);self.assertEqual(incoming['username'],'test_player')
        self.assertEqual(self.friend.post('/api/players/friends/test_player/accept',json={}).json()['status'],'accepted')
        self.assertEqual(self.friend.post('/api/players/friends/test_player/accept',json={}).status_code,200)
        self.assertEqual(self.client.delete('/api/players/friends/test_friend').status_code,200)
        self.assertEqual(self.friend.get('/api/players/friends').json()['friends'],[])

    def test_guest_self_and_cross_origin_requests_rejected(self):
        anon=TestClient(app)
        self.assertEqual(anon.get('/api/players/friends').status_code,401)
        self.assertEqual(anon.post('/api/players/friends',json={'username':'test_friend'}).status_code,401)
        self.assertEqual(self.client.post('/api/players/friends',json={'username':'test_player'}).status_code,400)
        self.assertEqual(self.client.post('/api/players/friends',json={'username':'test_friend'},headers={'Origin':'https://evil.example'}).status_code,403)

    def test_crossed_requests_remain_pending(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(self.add)
            b=pool.submit(self.friend.post,'/api/players/friends',json={'username':'test_player'})
            self.assertEqual(a.result().status_code,200);self.assertEqual(b.result().status_code,200)
        with self.connection() as conn:
            rows=conn.execute('SELECT * FROM game_friendships').fetchall()
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'pending')

    def test_invitation_only_for_accepted_friends(self):
        self.add()
        s=self.client.post('/api/friends/rooms',json={'request_id':str(uuid4())}).json()
        body={'run_id':s['run_id']};path='/api/players/friends/test_friend/invite'
        self.assertEqual(self.client.post(path,json=body).status_code,403)
        self.friend.post('/api/players/friends/test_player/accept',json={})
        self.assertEqual(self.friend.post('/api/players/friends/test_player/invite',json=body).status_code,409)
        self.assertEqual(self.client.post(path,json=body).status_code,200)
        self.assertEqual(self.friend.get('/api/players/friends').json()['friends'][0]['invite'],'/friends/'+s['code'])
        self.friend.post('/api/friends/rooms/'+s['code']+'/join',json={})
        self.assertIsNone(self.friend.get('/api/players/friends').json()['friends'][0]['invite'])

    def test_two_guests_can_join_ready_and_forfeit_without_rewards(self):
        a,b=TestClient(app),TestClient(app)
        self.assertEqual(a.get('/api/friends/active').json(),{'code':None})
        r=a.post('/api/friends/rooms',json={'request_id':str(uuid4()),'difficulty':'easy'})
        self.assertEqual(r.status_code,201,r.text);s=r.json();path='/api/friends/rooms/'+s['code']
        self.assertTrue(s['is_guest']);self.assertNotIn('trial_',str(s))
        self.assertIn('HttpOnly',r.headers['set-cookie']);self.assertEqual(a.get('/api/players/me').status_code,401)
        self.assertTrue(b.get('/api/friends/invites/'+s['code']).json()['joinable'])
        self.assertFalse(b.cookies)
        r=b.post(path+'/join',json={});self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(all(p['is_guest'] for p in r.json()['players']))
        for c in [a,b]:self.assertEqual(c.post(path+'/ready',json={}).status_code,200)
        r=a.post(path+'/leave',json={});self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['winner'],1)
        self.assertEqual(b.get(path).json()['phase'],'FINISHED')
        with self.connection() as conn:
            for t in ['game_xp_ledger','game_mode_xp','game_match_results']:
                self.assertEqual(conn.execute('SELECT count(*) n FROM '+t).fetchone()['n'],0)

    def test_mixed_identity_and_third_guest_cannot_read_room(self):
        r=self.client.post('/api/friends/rooms',json={'request_id':str(uuid4())}).json();path='/api/friends/rooms/'+r['code']
        anon=TestClient(app);r=anon.post(path+'/join',json={})
        self.assertEqual(r.status_code,200,r.text)
        self.assertFalse(r.json()['players'][0]['is_guest']);self.assertTrue(r.json()['players'][1]['is_guest'])
        self.assertEqual(TestClient(app).get(path).status_code,401)

    def test_share_is_opt_in_owned_and_immutable(self):
        body=self.end_solo()
        with self.connection() as conn:self.assertEqual(conn.execute('SELECT count(*) n FROM game_result_shares').fetchone()['n'],0)
        self.assertEqual(self.friend.post('/api/shares/results',json=body).status_code,404)
        self.assertEqual(TestClient(app).post('/api/shares/results',json=body).status_code,401)
        self.assertEqual(self.client.post('/api/shares/results',json={**body,'score':[999,0]}).status_code,422)
        r=self.client.post('/api/shares/results',json=body);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.client.post('/api/shares/results',json=body).json(),r.json())
        token=r.json()['url'].split('/')[-1]
        with self.connection() as conn:
            data=conn.execute('SELECT snapshot FROM game_result_shares WHERE token=%s',(token,)).fetchone()['snapshot']
            self.assertEqual(data['score'],[0,0]);self.assertNotIn('run_id',data);self.assertNotIn('email',data);self.assertNotIn('history',data)
            with self.assertRaises(DatabaseError),conn.transaction():conn.execute("UPDATE game_result_shares SET snapshot='{}'")
        html=TestClient(app).get('/s/'+token)
        self.assertEqual(html.status_code,200);self.assertIn('property="og:image"',html.text);self.assertIn('0 : 0',html.text)
        image=TestClient(app).get('/s/'+token+'/image.png')
        self.assertEqual(image.status_code,200);self.assertEqual(Image.open(BytesIO(image.content)).size,(1200,630))

    def test_active_result_and_invalid_token_not_shared(self):
        s=self.start('easy')
        self.assertEqual(self.client.post('/api/shares/results',json={'run_id':s['run_id']}).status_code,409)
        for path in ['/s/invalid','/s/'+'a'*32,'/s/'+'a'*32+'/image.png']:
            self.assertEqual(TestClient(app).get(path).status_code,404)

    def test_friend_result_and_daily_result_server_snapshot(self):
        path,s=self.duel();self.client.post(path+'/leave',json={})
        r=self.friend.post('/api/shares/results',json={'mode':'friend','run_id':s['run_id']})
        self.assertEqual(r.status_code,200,r.text)
        with self.connection() as conn:
            d=conn.execute('SELECT snapshot FROM game_result_shares').fetchone()['snapshot']
            self.assertEqual(d['status'],'Won');self.assertEqual(d['xp'],0);self.assertEqual(d['opponent'],'test_player')
        s=self.daily();self.client.post('/api/daily/runs/'+s['run_id']+'/leave',json={})
        r=self.client.post('/api/shares/results',json={'mode':'daily','run_id':s['run_id']})
        self.assertEqual(r.status_code,200,r.text)

    def test_brand_preview_and_no_sensitive_home_cache(self):
        anon=TestClient(app);html=anon.get('/')
        self.assertEqual(html.status_code,200);self.assertIn('/share/brand.png',html.text)
        self.assertIn('no-store',html.headers['cache-control'])
        self.assertEqual(Image.open(BytesIO(anon.get('/share/brand.png').content)).size,(1200,630))


for _name in dir(ChallengeDatabaseTests):
    if _name.startswith('test_') and _name not in SocialPlayTests.__dict__:
        setattr(SocialPlayTests,_name,None)
