import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


class BrandingTests(unittest.TestCase):
    def test_branding_contains_database_teams_and_country_flags(self):
        with patch("api.main.fetch_all", side_effect=[
            [{"id": 63, "name": "Leeds", "logo_url": "leeds.png"}],
            [{"id": 39, "name": "Premier League", "logo_url": "pl.png"}],
            [{"code": "GB-ENG", "name": "England", "flag_url": "eng.svg"}],
        ]):
            response = TestClient(app).get("/api/branding")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["sports"]["football"]["teams"]["63"]["logo_url"], "leeds.png")
        self.assertEqual(data["sports"]["football"]["competitions"]["39"]["name"], "Premier League")
        self.assertEqual(data["countries"]["GB-ENG"]["flag_url"], "eng.svg")
