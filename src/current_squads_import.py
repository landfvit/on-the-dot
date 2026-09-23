"""Import complete current squads, then audit identity and season-data coverage."""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.database import get_connection
from src.squads_import import get_API_key, get_season_teams, make_request, upsert_membership, upsert_player

PROFILE_FIELDS = ('birth_date', 'nationality', 'height_cm', 'weight_kg', 'photo_url')


def validate_current_season(payload, league, season):
    return any(row.get('league', {}).get('id') == league and
               any(s.get('current') and s.get('year') == season for s in row.get('seasons', []))
               for row in payload.get('response', []))


def save_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2, default=str) + '\n')
    temporary.replace(path)


def run(season, league=39, delay=0.5, profiles=True):
    key = get_API_key()
    def request(endpoint, params):
        time.sleep(delay)
        return make_request(endpoint, params, key)

    if not validate_current_season(request('leagues', {'id': league, 'current': 'true'}), league, season):
        raise ValueError('Current squads cannot be assigned to a historical or unverified season')

    report = {'season': season, 'league_id': league, 'checked_at': datetime.now(timezone.utc).isoformat(),
              'source': 'API-Football /players/squads', 'teams': [], 'profiles_refreshed': 0}
    output = ROOT / 'data' / 'audits' / f'squad_integrity_{season}.json'
    all_ids = set()
    with get_connection() as conn:
        teams = get_season_teams(conn, league, season)
        for team in teams:
            payload = request('players/squads', {'team': team['team_id']})
            rows = [r for r in payload.get('response', []) if r.get('team', {}).get('id') == team['team_id']]
            if len(rows) != 1 or not rows[0].get('players'):
                raise ValueError(f"Missing or ambiguous squad for {team['team_name']}")
            ids = set()
            for player in rows[0]['players']:
                if not player.get('id') or not player.get('name'):
                    raise ValueError('Squad player missing identity')
                existing = conn.execute('SELECT * FROM players WHERE player_id = %s', (player['id'],)).fetchone()
                profile = dict(player)
                if existing:
                    profile['name'] = existing['player_name']
                upsert_player(conn, profile)
                upsert_membership(conn, league, season, team['team_id'], player, {
                    'team': {'id': team['team_id']}, 'league': {'id': league, 'season': season},
                    'games': {'number': player.get('number'), 'position': player.get('position')},
                })
                ids.add(player['id'])
            conn.commit()
            all_ids.update(ids)
            stored = conn.execute('SELECT player_id FROM squad_memberships WHERE league_id=%s AND season=%s AND team_id=%s',
                                  (league, season, team['team_id'])).fetchall()
            entry = {**team, 'api_player_count': len(ids), 'api_player_ids': sorted(ids),
                     'missing_from_database': sorted(ids - {p['player_id'] for p in stored}),
                     'goalkeepers': [p['name'] for p in rows[0]['players'] if p.get('position') == 'Goalkeeper']}
            report['teams'].append(entry)
            save_report(output, report)
            print(f"{team['team_name']}: {len(ids)} players, {len(entry['goalkeepers'])} goalkeepers", flush=True)

        if profiles:
            rows = conn.execute('SELECT * FROM players WHERE player_id = ANY(%s)', (list(all_ids),)).fetchall()
            for row in rows:
                if all(row.get(field) for field in PROFILE_FIELDS):
                    continue
                payload = request('players/profiles', {'player': row['player_id']})
                for item in payload.get('response', []):
                    profile = item.get('player', {})
                    if profile.get('id') != row['player_id']:
                        continue
                    profile['name'] = row['player_name']
                    upsert_player(conn, profile)
                    conn.commit()
                    report['profiles_refreshed'] += 1
                save_report(output, report)

        rows = conn.execute('SELECT * FROM players WHERE player_id = ANY(%s)', (list(all_ids),)).fetchall()
        report['missing_profile_fields'] = [
            {'player_id': p['player_id'], 'name': p['player_name'],
             'fields': [f for f in PROFILE_FIELDS if not p.get(f)]}
            for p in rows if any(not p.get(f) for f in PROFILE_FIELDS)
        ]
        report['players_without_season_statistics'] = conn.execute('''
            SELECT sm.team_id, t.team_name, p.player_id, p.player_name
            FROM squad_memberships sm JOIN players p USING (player_id)
            JOIN teams t USING (team_id)
            LEFT JOIN player_season_statistics pss USING (league_id, season, team_id, player_id)
            WHERE sm.league_id=%s AND sm.season=%s AND pss.player_id IS NULL
            ORDER BY t.team_name, p.player_name
        ''', (league, season)).fetchall()
        report['complete'] = True
        report['unique_current_players'] = len(all_ids)
        save_report(output, report)
        print(f"Audit saved: {output}; {len(all_ids)} players; {len(report['missing_profile_fields'])} profiles still incomplete", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--league', type=int, default=39)
    parser.add_argument('--delay', type=float, default=0.5)
    parser.add_argument('--skip-profiles', action='store_true')
    args = parser.parse_args()
    run(args.season, args.league, args.delay, not args.skip_profiles)
