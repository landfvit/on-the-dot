"""Versioned, offline kit catalogue; only catalogue IDs enter player profiles."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def catalogue():
    path = Path(__file__).resolve().parents[1] / 'trivia_app/static/player-kits/catalog.json'
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def by_id():
    return {kit['id']: kit for kit in catalogue()['kits']}


def outfit(row):
    """Return only public cosmetic fields; never account IDs or other settings.

    An unset outfit defaults to the member club's home shirt. A saved shirt
    from a former membership is never returned, even from an old snapshot row.
    """
    kit = by_id().get(row.get('kit_id'))
    if kit and kit['team_id'] != row.get('club_id'):
        kit = None
    if kit is None and row.get('club_id'):
        kit = next((k for k in by_id().values() if k['team_id'] == row['club_id'] and k['type'] == 'home'), None)
    return {'kit_id': kit['id'] if kit else None, 'number': row.get('shirt_number') or 10}
