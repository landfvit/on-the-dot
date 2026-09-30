"""Catalogue integrity and account persistence in disposable local schemas."""
import os
import unittest
from uuid import uuid4
from unittest.mock import patch
from fastapi.testclient import TestClient
from psycopg.errors import CheckViolation, ForeignKeyViolation
from api.player_kits import catalogue, by_id, outfit
from tests.test_solo_database import SoloDatabaseTests
from trivia_app.main import app


class KitCatalogueTests(unittest.TestCase):
    def test_unique_sourced_season_specific_kits(self):
        data=catalogue();self.assertEqual(len(data['kits']),len(by_id()))
        self.assertGreaterEqual(len(data['clubs']),33)
        for club in data['clubs']:
            available=[k for k in data['kits'] if k['team_id']==club['team_id']]
            self.assertTrue(available,club['name'])
            self.assertIn('home',{k['type'] for k in available})
            for kit in available:
                self.assertEqual(kit['season'],2026 if club['last_season']==2026 else 2025)
                self.assertTrue(kit['source_url'].startswith('https://'))
                self.assertEqual(set(kit['design']),{'pattern','shirt','contrast','sleeve','trim','shorts','socks'})
                self.assertNotIn('image_url',kit)

    def test_hull_stripes_are_not_a_flat_palette(self):
        shirt=by_id()['64-2026-home']['design']
        self.assertEqual(shirt['pattern'],'stripes')
        self.assertNotEqual(shirt['shirt'],shirt['contrast'])

    def test_default_and_explicit_cosmetics(self):
        self.assertEqual(outfit({}),{'kit_id':None,'number':10})
        self.assertEqual(outfit({'club_id':64})['kit_id'],'64-2026-home')
        self.assertEqual(outfit({'club_id':64,'kit_id':'33-2026-away','shirt_number':99}),{'kit_id':'64-2026-home','number':99})


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Isolated PostgreSQL integration tests')
class PlayerKitTests(unittest.TestCase):
    setUp=SoloDatabaseTests.setUp
    drop_schema=SoloDatabaseTests.drop_schema

    def test_save_reload_and_public_profile_without_changing_membership(self):
        self.client.put('/api/players/me/team',json={'team_id':64})
        before=self.client.get('/api/players/me').json()
        body={'kit_id':'64-2026-away','number':27}
        response=self.client.put('/api/players/me/outfit',json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['outfit'],body)
        after=self.client.get('/api/players/me').json()
        self.assertEqual(after['outfit'],body)
        self.assertEqual(after['club'],before['club'])
        self.assertEqual(after['team_change'],before['team_change'])
        self.assertEqual(self.client.get('/api/players/profiles/test_player').json()['outfit'],body)
        self.assertEqual(self.client.put('/api/players/me/outfit',json={**body,'kit_id':'33-2026-away'}).status_code,422)

    def test_validation_auth_origin_and_database_constraints(self):
        path='/api/players/me/outfit';valid={'kit_id':'64-2026-home','number':10}
        self.assertEqual(TestClient(app).put(path,json=valid).status_code,401)
        self.assertEqual(self.client.put(path,json=valid,headers={'Origin':'https://evil.test'}).status_code,403)
        for number in [0,100,-1,2.5,True,'10',None]:
            self.assertEqual(self.client.put(path,json={**valid,'number':number}).status_code,422)
        self.assertEqual(self.client.put(path,json={**valid,'kit_id':'fake-kit'}).status_code,422)
        self.client.put('/api/players/me/team',json={'team_id':64})
        for field,value,error in [('shirt_number',0,CheckViolation),('kit_id','fake-kit',ForeignKeyViolation)]:
            with self.assertRaises(error),self.connection() as conn:
                conn.execute(f'UPDATE game_accounts SET {field}=%s WHERE username=%s',(value,'test_player'))

    def test_historic_clubs_are_available_and_blocked_accounts_cannot_edit(self):
        ids={c['team_id'] for c in self.client.get('/api/players/teams').json()['teams']}
        self.assertTrue({37,38,39,43,46,48,60,62,70,71,75,76,1359}<=ids)
        with self.connection() as conn:conn.execute("UPDATE game_accounts SET blocked_at=clock_timestamp() WHERE username='test_player'")
        self.assertEqual(self.client.put('/api/players/me/outfit',json={'kit_id':'64-2026-home','number':9}).status_code,403)

    def test_team_change_resets_kit_and_database_rejects_foreign_kit(self):
        self.client.put('/api/players/me/team',json={'team_id':64})
        self.client.put('/api/players/me/outfit',json={'kit_id':'64-2026-away','number':27})
        with self.assertRaises(ForeignKeyViolation),self.connection() as conn:
            conn.execute("UPDATE game_accounts SET kit_id='33-2026-home' WHERE username='test_player'")
        with self.connection() as conn:
            # Age this membership only inside the disposable test schema.
            conn.execute('ALTER TABLE game_accounts DISABLE TRIGGER game_club_change_guard')
            conn.execute("UPDATE game_accounts SET club_changed_at=clock_timestamp()-interval '4 days' WHERE username='test_player'")
            conn.execute('ALTER TABLE game_accounts ENABLE TRIGGER game_club_change_guard')
        response=self.client.put('/api/players/me/team',json={'team_id':33})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.get('/api/players/me').json()['outfit'],{'kit_id':'33-2026-home','number':27})
        with self.connection() as conn:
            self.assertIsNone(conn.execute("SELECT kit_id FROM game_accounts WHERE username='test_player'").fetchone()['kit_id'])

    def test_deletion_erases_outfit(self):
        self.client.put('/api/players/me/team',json={'team_id':64})
        self.client.put('/api/players/me/outfit',json={'kit_id':'64-2026-home','number':99})
        r=self.client.request('DELETE','/api/players/me',json={'password':'test-only-password-1234','confirmation':'DELETE'})
        self.assertEqual(r.status_code,200,r.text)
        with self.connection() as conn:
            row=conn.execute('SELECT kit_id,shirt_number FROM game_accounts WHERE deleted_at IS NOT NULL').fetchone()
            self.assertEqual(row,{'kit_id':None,'shirt_number':10})


@unittest.skipUnless(os.getenv('TRIVIA_DB_TEST')=='1','Isolated PostgreSQL integration tests')
class FriendKitTests(unittest.TestCase):
    def setUp(self):
        SoloDatabaseTests.setUp(self)
        for target,value in [('get_connection',self.connection),('rate_limit',lambda *a:None)]:
            p=patch('api.challenge_routes.'+target,value);p.start();self.addCleanup(p.stop)
        self.friend=TestClient(app)
        self.assertEqual(self.friend.post('/api/players/register',json={'username':'test_friend','email':'friend@example.com','password':'test-password-1234'}).status_code,201)
    drop_schema=SoloDatabaseTests.drop_schema

    def test_duel_keeps_each_players_outfit_snapshot(self):
        self.client.put('/api/players/me/team',json={'team_id':64})
        self.friend.put('/api/players/me/team',json={'team_id':33})
        self.client.put('/api/players/me/outfit',json={'kit_id':'64-2026-home','number':7})
        r=self.client.post('/api/friends/rooms',json={'request_id':str(uuid4()),'difficulty':'easy'})
        self.assertEqual(r.status_code,201,r.text)
        path='/api/friends/rooms/'+r.json()['code']
        self.friend.put('/api/players/me/outfit',json={'kit_id':'33-2026-home','number':11})
        joined=self.friend.post(path+'/join',json={}).json()
        self.assertEqual([p['outfit'] for p in joined['players']],
                         [{'kit_id':'64-2026-home','number':7},{'kit_id':'33-2026-home','number':11}])
        self.client.put('/api/players/me/outfit',json={'kit_id':'64-2026-away','number':99})
        self.assertEqual(self.client.get(path).json()['players'][0]['outfit']['number'],7)
