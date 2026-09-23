import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.database import fetch_one
from kits import source_signature

router = APIRouter()
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "enrichment"


@lru_cache(maxsize=4)
def read_snapshot(path, modified):
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot(name):
    path = DATA_DIR / name
    return read_snapshot(path, path.stat().st_mtime_ns) if path.exists() else {}


@router.get("/api/players/{player_id}/market-value")
def get_market_value(player_id: int):
    if not fetch_one("SELECT player_id FROM players WHERE player_id = %s", (player_id,)):
        raise HTTPException(404, "Player not found")
    data = snapshot("market_values.json")
    player = data.get("players", {}).get(str(player_id))
    history = player["history"] if player else []
    return {
        "player_id": player_id, "available": bool(history), "currency": "EUR",
        "source": "Transfermarkt", "source_url": player["source_url"] if player else None,
        "dataset_url": data.get("dataset_url"), "retrieved_at": data.get("retrieved_at"),
        "latest": history[-1] if history else None, "history": history,
    }


@router.get("/api/teams/{team_id}/kits")
def get_team_kits(team_id: int, season: int):
    if not fetch_one("SELECT team_id FROM teams WHERE team_id = %s", (team_id,)):
        raise HTTPException(404, "Team not found")
    entry = snapshot("team_kits.json").get("seasons", {}).get(str(season), {}).get(str(team_id), {})
    kits = {kit["type"]: kit for kit in entry.get("kits", [])}
    catalog_path = DATA_DIR.parent / "kits" / "catalog.json"
    catalog = read_snapshot(catalog_path, catalog_path.stat().st_mtime_ns) if catalog_path.exists() else {}
    local = catalog.get("seasons", {}).get(str(season), {}).get(str(team_id), {})
    for kind, kit in list(kits.items()):
        asset = local.get(kind, {})
        expected = f"/assets/kits/{season}/{team_id}/{kind}.svg"
        path = DATA_DIR.parents[1] / "web/static" / expected.removeprefix("/assets/")
        if (asset.get("source_signature") == source_signature(kit)
                and asset.get("image_url") == expected and path.is_file()):
            kits[kind] = {**kit, "image_url": expected, "render_style": "pixel"}
    return {
        "team_id": team_id, "season": season, "source": "Wikimedia Commons",
        "source_url": entry.get("source_url"),
        "kits": [kits.get(kind, {"type": kind, "label": kind.title(), "layers": []})
                 for kind in ("home", "away", "third")],
    }
