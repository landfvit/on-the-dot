from datetime import datetime, timezone, timedelta
import unittest
from fastapi.testclient import TestClient
from api.game_community import period_start
from trivia_app.main import app


class CommunityTests(unittest.TestCase):
    def test_periods_are_utc_calendar_days(self):
        now=datetime(2026,1,1,1,tzinfo=timezone(timedelta(hours=2)))
        self.assertEqual(period_start('today',now),datetime(2025,12,31,tzinfo=timezone.utc))
        self.assertEqual(period_start('week',now),datetime(2025,12,25,tzinfo=timezone.utc))
        self.assertIsNone(period_start('all',now))

    def test_public_shell_routes_and_assets(self):
        client=TestClient(app)
        for path in ['/penalties','/leaderboard','/history','/account']:
            response=client.get(path);self.assertEqual(response.status_code,200)
            self.assertIn('menu-drawer',response.text);self.assertNotIn('profile-drawer',response.text)
            self.assertIn('ON THE DOT',response.text)
            self.assertNotIn('POINTS',response.text)
            self.assertNotIn('/internal/trivia',response.text)
        for asset in ['community.css','community.js','shell.js','icons/menu.svg','icons/trophy.svg','icons/LICENSE']:
            self.assertEqual(client.get('/trivia-assets/'+asset).status_code,200)
        self.assertNotEqual(client.get('/trivia-assets/writer.js').status_code,200)

    def test_pvp_is_not_routable_or_linked_and_avatar_is_removed(self):
        client=TestClient(app)
        self.assertEqual(client.get('/penalties/pvp').status_code,404)
        self.assertEqual(client.post('/api/penalties/rooms',json={}).status_code,404)
        for path in ['/penalties','/penalties?room=old-room','/account','/leaderboard']:
            html=client.get(path).text
            self.assertNotIn('Private PvP',html);self.assertNotIn('id="avatar"',html)
            self.assertNotIn('id="account-link"',html)
