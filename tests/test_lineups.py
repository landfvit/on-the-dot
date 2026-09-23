import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


class FixtureLineupsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.fixture = {
            "fixture_id": 123,
            "league_id": 39,
            "season": 2026,
            "home_team_id": 63,
            "home_team": "Leeds",
            "home_team_logo_url": "https://example.com/leeds.png",
            "away_team_id": 34,
            "away_team": "Newcastle",
            "away_team_logo_url": "https://example.com/newcastle.png",
        }

    def request_lineups(self, rows, fixture=None, photos=None):
        with (
            patch("api.lineups.fetch_one", return_value=fixture or self.fixture),
            patch("api.lineups.fetch_all", side_effect=[rows, photos or []]),
        ):
            response = self.client.get("/api/fixtures/123/lineups")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_route_normalizes_players_orders_teams_and_fills_branding(self):
        data = self.request_lineups([{"payload": {"response": [
            {"team": {"id": "34"}, "startXI": []},
            {
                "team": {"id": "63"},
                "formation": "3-5-2",
                "coach": {"name": "Coach"},
                "startXI": [{"player": {
                    "id": 10, "name": "Starter", "number": 1,
                    "pos": "G", "grid": "1:1",
                }}],
                "substitutes": [{"player": {"id": 11, "name": "Sub"}}],
            },
        ]}}])
        self.assertTrue(data["available"])
        self.assertEqual([x["team_id"] for x in data["lineups"]], [63, 34])
        home = data["lineups"][0]
        self.assertEqual(home["team_name"], "Leeds")
        self.assertEqual(home["team_logo_url"], self.fixture["home_team_logo_url"])
        self.assertEqual(home["formation"], "3-5-2")
        self.assertEqual(home["coach"]["name"], "Coach")
        self.assertEqual(home["starting_xi"][0]["player_name"], "Starter")
        self.assertEqual(home["starting_xi"][0]["grid"], "1:1")
        self.assertTrue(home["starting_xi"][0]["starter"])
        self.assertFalse(home["substitutes"][0]["starter"])

    def test_empty_direct_response_falls_back_to_complete_fixture(self):
        data = self.request_lineups([
            {"payload": {"response": []}},
            {"payload": {"response": [
                {"fixture": {"id": 999}, "lineups": [{"team": {"id": 99}}]},
                {"fixture": {"id": 123}, "lineups": [{"team": {
                    "id": 63, "logo": "https://example.com/api-logo.png",
                }}]},
            ]}},
        ])
        self.assertEqual(len(data["lineups"]), 1)
        self.assertEqual(data["lineups"][0]["team_id"], 63)
        self.assertEqual(data["lineups"][0]["team_logo_url"],
                         "https://example.com/api-logo.png")

    def test_unpublished_lineups_return_explicit_empty_state(self):
        data = self.request_lineups([])
        self.assertFalse(data["available"])
        self.assertEqual(data["lineups"], [])

    def test_photos_enrich_starters_and_substitutes_with_raw_fallback(self):
        data = self.request_lineups(
            [{"payload": {"lineups": [{
                "team": {"id": 63},
                "startXI": [{"player": {"id": "10"}}],
                "substitutes": [
                    {"player": {"id": 11}},
                    {"player": {"id": 12, "photo": "raw.png"}},
                    {"player": {"id": 13}},
                ],
            }]}}],
            photos=[
                {"player_id": 10, "team_id": 63, "photo_url": "starter.png"},
                {"player_id": 11, "team_id": None, "photo_url": "sub.png"},
            ],
        )
        lineup = data["lineups"][0]
        self.assertEqual(lineup["starting_xi"][0]["photo_url"], "starter.png")
        self.assertEqual([p["photo_url"] for p in lineup["substitutes"]],
                         ["sub.png", "raw.png", None])

    def test_unknown_fixture_returns_404(self):
        with patch("api.lineups.fetch_one", return_value=None):
            response = self.client.get("/api/fixtures/999/lineups")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
