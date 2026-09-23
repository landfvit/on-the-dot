import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api.profile_enrichment import get_market_value, get_team_kits
from src.profile_enrichment_import import KitParser, match_player


class ProfileEnrichmentTests(unittest.TestCase):
    def test_identity_requires_birth_date_and_rejects_ambiguity(self):
        local = dict(player_name="J. Trafford", first_name="James Harrington", last_name="Trafford", birth_date="2002-10-10")
        candidate = dict(name="James Trafford", first_name="James", last_name="Trafford")
        self.assertEqual(match_player(local, {"2002-10-10": [candidate]}), candidate)
        self.assertIsNone(match_player(local, {"2002-10-10": [candidate, candidate]}))
        self.assertIsNone(match_player(local, {"2002-10-11": [candidate]}))

    @patch("api.profile_enrichment.fetch_one", return_value={"player_id": 1})
    @patch("api.profile_enrichment.snapshot")
    def test_current_value_is_latest_record_not_selected_season(self, snapshot, _):
        history = [{"date": "2024-01-01", "value_eur": 100}, {"date": "2026-06-03", "value_eur": 200}]
        snapshot.return_value = {"players": {"1": {"history": history, "source_url": "https://www.transfermarkt.com/"}}}
        result = get_market_value(1)
        self.assertEqual(result["latest"], history[-1])
        self.assertEqual(result["history"], history)

    @patch("api.profile_enrichment.fetch_one", return_value={"player_id": 1})
    @patch("api.profile_enrichment.snapshot", return_value={})
    def test_missing_valuation_is_not_zero(self, *_):
        result = get_market_value(1)
        self.assertFalse(result["available"])
        self.assertIsNone(result["latest"])
        self.assertEqual(result["history"], [])

    @patch("api.profile_enrichment.fetch_one", return_value=None)
    def test_unknown_entities_return_404(self, _):
        for endpoint, args in [(get_market_value, (1,)), (get_team_kits, (1, 2026))]:
            with self.assertRaises(HTTPException) as error:
                endpoint(*args)
            self.assertEqual(error.exception.status_code, 404)

    @patch("api.profile_enrichment.fetch_one", return_value={"team_id": 1})
    @patch("api.profile_enrichment.snapshot")
    def test_kits_never_fall_back_to_another_season(self, snapshot, _):
        snapshot.return_value = {"seasons": {"2025": {"1": {"kits": [{"type": "home", "layers": [1]}]}}}}
        result = get_team_kits(1, 2026)
        self.assertEqual([k["type"] for k in result["kits"]], ["home", "away", "third"])
        self.assertTrue(all(not k["layers"] for k in result["kits"]))

    def test_kit_parser_keeps_layers_and_excludes_alternative_sets(self):
        parser = KitParser()
        parser.feed('<h3>Leeds United</h3><table><td><div style="position:absolute;left:31px;top:0px;width:38px;height:59px;background-color:#ffffff"><a href="/wiki/File:Kit_body.png"><img src="https://upload.wikimedia.org/test.png?tracking=1"></a></div><b>Home</b></td><td><b>Alt. Home</b></td></table>')
        kits = parser.teams["Leeds United"]
        self.assertEqual(len(kits), 1)
        self.assertEqual(kits[0]["layers"][0]["left"], 31)
        self.assertEqual(kits[0]["layers"][0]["image_url"], "https://upload.wikimedia.org/test.png")

    def test_kit_parser_ignores_hidden_label_spacers_used_by_wolves(self):
        parser = KitParser()
        layer = '<div style="position:absolute;left:31px;top:0px;width:38px;height:59px;background-color:#ff9900"><a href="/wiki/File:Kit.png"><img src="https://upload.wikimedia.org/kit.png"></a></div>'
        cells = ''.join(f'<td>{layer}<b>{label}<br/><span style="visibility:hidden; color:transparent;">0<span>0</span></span><br/><span style="display:none">0</span></b></td>'
                        for label in ('Home', 'Away', 'Third', 'Alt. Home'))
        parser.feed(f'<h3>Wolverhampton Wanderers</h3><table>{cells}</table>')
        kits = parser.teams['Wolverhampton Wanderers']
        self.assertEqual([kit['type'] for kit in kits], ['home', 'away', 'third'])
        self.assertTrue(all(len(kit['layers']) == 1 for kit in kits))
