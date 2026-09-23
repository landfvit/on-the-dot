"""Compare historical kit coverage against the actual PL fixture participants."""
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.database import fetch_all


def audit_coverage():
    source = json.loads((ROOT / 'data/enrichment/team_kits.json').read_text())['seasons']
    fixtures = fetch_all('SELECT season, home_team_id, away_team_id FROM fixtures WHERE league_id = 39')
    participants = defaultdict(set)
    counts = defaultdict(int)
    for fixture in fixtures:
        season = str(fixture['season'])
        participants[season].update((str(fixture['home_team_id']), str(fixture['away_team_id'])))
        counts[season] += 1
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'seasons': [], 'passed': True}
    for season, teams in sorted(source.items()):
        available = set(teams)
        missing = sorted(participants[season] - available)
        extra = sorted(available - participants[season])
        incomplete = {team: sorted({'home', 'away', 'third'} - {kit['type'] for kit in data['kits']})
                      for team, data in teams.items()}
        passed = len(participants[season]) == 20 and counts[season] == 380 and not missing and not extra
        report['passed'] = report['passed'] and passed
        report['seasons'].append({
            'season': int(season), 'fixture_count': counts[season],
            'participant_count': len(participants[season]), 'teams_with_kits': len(teams),
            'available_sets': sum(len(t['kits']) for t in teams.values()),
            'missing_team_ids': missing, 'unexpected_team_ids': extra,
            'unavailable_sets': {team: kinds for team, kinds in incomplete.items() if kinds},
            'passed': passed,
        })
    return report


if __name__ == '__main__':
    report = audit_coverage()
    path = ROOT / 'data/audits/kit_coverage.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')
    for season in report['seasons']:
        print(json.dumps(season))
    raise SystemExit(0 if report['passed'] else 1)
