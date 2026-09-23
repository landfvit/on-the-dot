"""Refresh coach profiles/careers and stadium metadata without inventing season links."""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.database import get_connection
from src.entity_history_import import ApiClient, import_coach
from src.history_import import upsert_venue
from src.squads_import import get_API_key, get_season_teams
from src.current_squads_import import validate_current_season


def run(season, league_id=39):
    client = ApiClient(get_API_key(), request_delay=0.5)
    if not validate_current_season(client.get('/leagues', {'id': league_id, 'current': 'true'}), league_id, season):
        raise ValueError('Current venue snapshots require a verified current season')
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'season': season,
              'teams': [], 'coaches_imported': 0, 'venues_refreshed': 0, 'errors': []}
    imported = set()
    with get_connection() as conn:
        teams = get_season_teams(conn, league_id, season)
        participants = {t['team_id'] for t in teams}
        profiles = client.get('/teams', {'league': league_id, 'season': season}).get('response', [])
        for profile in profiles:
            team = profile.get('team', {})
            venue = profile.get('venue', {})
            if team.get('id') not in participants or not venue.get('id'):
                continue
            upsert_venue(conn, venue, team.get('country'))
            conn.execute('''
                INSERT INTO team_venue_snapshots (league_id, season, team_id, venue_id)
                VALUES (%s,%s,%s,%s) ON CONFLICT (league_id, season, team_id)
                DO UPDATE SET venue_id=EXCLUDED.venue_id, observed_at=NOW()
            ''', (league_id, season, team['id'], venue['id']))
        conn.commit()
        for team in teams:
            ident = team['team_id']
            rows = client.get('/coachs', {'team': ident}).get('response', [])
            for coach in rows:
                if coach.get('id') in imported:
                    continue
                import_coach(conn, client, coach['id'], {'response': [coach]})
                imported.add(coach['id'])
            conn.commit()
            report['teams'].append({**team, 'returned_coaches': len(rows)})
            if not rows:
                report['errors'].append(f'No coach profiles for {ident}')
            print(f"{team['team_name']}: {len(rows)} coach profiles", flush=True)

        missing = conn.execute('''
            SELECT DISTINCT fl.coach_id FROM fixture_lineups fl
            JOIN fixtures f USING (fixture_id) LEFT JOIN coaches c USING (coach_id)
            WHERE f.league_id=%s AND fl.coach_id IS NOT NULL AND c.coach_id IS NULL
        ''', (league_id,)).fetchall()
        for row in missing:
            import_coach(conn, client, row['coach_id'])
            imported.add(row['coach_id'])
            conn.commit()

        venues = conn.execute('SELECT DISTINCT venue_id FROM fixtures WHERE league_id=%s AND venue_id IS NOT NULL',
                              (league_id,)).fetchall()
        for venue in venues:
            rows = client.get('/venues', {'id': venue['venue_id']}).get('response', [])
            matched = [v for v in rows if v.get('id') == venue['venue_id']]
            for item in matched:
                upsert_venue(conn, item, item.get('country'))
                report['venues_refreshed'] += 1
            if not matched:
                report['errors'].append(f"No venue profile for {venue['venue_id']}")
            conn.commit()
        report['coaches_imported'] = len(imported)
        report['stored_coaches'] = conn.execute('SELECT count(*) AS count FROM coaches').fetchone()['count']
        report['stored_careers'] = conn.execute('SELECT count(*) AS count FROM coach_careers').fetchone()['count']
    output = ROOT / 'data/audits/team_context_import.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'teams'}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--league-id', type=int, default=39)
    args = parser.parse_args()
    run(args.season, args.league_id)
