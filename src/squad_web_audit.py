"""Check that every provider squad member is actually exposed by the website API."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.main import get_team_players


def audit(season):
    source = json.loads((ROOT / f'data/audits/squad_integrity_{season}.json').read_text())
    results = []
    for team in source['teams']:
        response = get_team_players(team['team_id'], season, source['league_id'])
        players = response['players']
        ids = [p['player_id'] for p in players]
        results.append({
            'team_id': team['team_id'], 'team_name': team['team_name'],
            'provider_count': team['api_player_count'], 'web_count': len(ids),
            'missing_player_ids': sorted(set(team['api_player_ids']) - set(ids)),
            'duplicate_ids': len(ids) != len(set(ids)),
            'goalkeepers': [p['player_name'] for p in players if p['position'] == 'Goalkeeper'],
            'without_photos': [p['player_id'] for p in players if not p['photo_url']],
            'without_position': [p['player_id'] for p in players if not p['position']],
        })
    passed = all(not t['missing_player_ids'] and not t['duplicate_ids'] for t in results)
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'season': season,
              'passed': passed, 'teams': results}
    target = ROOT / f'data/audits/squad_web_coverage_{season}.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': passed, 'teams': len(results),
                      'missing_players': sum(len(t['missing_player_ids']) for t in results),
                      'missing_photos': sum(len(t['without_photos']) for t in results),
                      'missing_positions': sum(len(t['without_position']) for t in results)}))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', required=True, type=int)
    audit(parser.parse_args().season)
