"""Season-aware coaching staff and home ground for team profiles."""
from fastapi import APIRouter, HTTPException

from api.database import fetch_all, fetch_one

router = APIRouter()


@router.get('/api/teams/{team_id}/context')
def get_team_context(team_id: int, season: int, league_id: int = 39):
    bounds = fetch_one('''
        SELECT MIN(match_date)::date AS first_match, MAX(match_date)::date AS last_match
        FROM fixtures WHERE league_id=%s AND season=%s
          AND (home_team_id=%s OR away_team_id=%s)
    ''', (league_id, season, team_id, team_id))
    if not bounds or not bounds['first_match']:
        raise HTTPException(404, 'Team not found for this season')

    # A present-day team record must not overwrite a historical home ground.
    venues = fetch_all('''
        SELECT v.venue_id, v.venue_name, v.city, v.capacity, v.image_url,
               v.updated_at AS capacity_updated_at, COUNT(*) AS home_matches,
               MAX(f.match_date) AS last_match
        FROM fixtures f JOIN venues v USING (venue_id)
        WHERE f.league_id=%s AND f.season=%s AND f.home_team_id=%s
        GROUP BY v.venue_id
        ORDER BY COUNT(*) DESC, MAX(f.match_date) DESC, v.venue_id
    ''', (league_id, season, team_id))
    if not venues:
        venues = fetch_all('''
            SELECT v.venue_id, v.venue_name, v.city, v.capacity, v.image_url,
                   v.updated_at AS capacity_updated_at, NULL::integer AS home_matches
            FROM team_venue_snapshots s JOIN venues v USING (venue_id)
            WHERE s.league_id=%s AND s.season=%s AND s.team_id=%s
        ''', (league_id, season, team_id))
    coaches = fetch_all('''
        SELECT fl.coach_id, COALESCE(c.coach_name, MAX(fl.coach_name)) AS coach_name,
               c.first_name, c.last_name, c.nationality, c.photo_url,
               COUNT(DISTINCT f.fixture_id) AS matches,
               MIN(f.match_date)::date AS first_match, MAX(f.match_date)::date AS last_match
        FROM fixture_lineups fl JOIN fixtures f USING (fixture_id)
        LEFT JOIN coaches c ON c.coach_id=fl.coach_id
        WHERE f.league_id=%s AND f.season=%s AND fl.team_id=%s
          AND fl.coach_id IS NOT NULL AND f.match_date <= CURRENT_TIMESTAMP
          AND f.status IN ('FT', 'AET', 'PEN', '1H', 'HT', '2H', 'ET', 'P', 'LIVE', 'BT')
        GROUP BY fl.coach_id, c.coach_name, c.first_name, c.last_name, c.nationality, c.photo_url
        ORDER BY MAX(f.match_date) DESC, fl.coach_id
    ''', (league_id, season, team_id))
    coach_source = 'lineups'
    if not coaches:
        coach_source = 'careers'
        coaches = fetch_all('''
            SELECT c.coach_id, c.coach_name, c.first_name, c.last_name, c.nationality, c.photo_url,
                   NULL::integer AS matches, MIN(cc.start_date) AS start_date,
                   MAX(cc.end_date) AS end_date
            FROM coach_careers cc JOIN coaches c USING (coach_id)
            WHERE cc.team_id=%s AND cc.start_date <= LEAST(%s, CURRENT_DATE)
              AND (cc.end_date >= %s OR (cc.end_date IS NULL AND c.current_team_id=cc.team_id))
            GROUP BY c.coach_id
            ORDER BY MAX(cc.start_date) DESC, c.coach_id
        ''', (team_id, bounds['last_match'], bounds['first_match']))
    return {'team_id': team_id, 'season': season, 'source': 'API-Football',
            'venue': venues[0] if venues else None, 'venues': venues,
            'coaches': coaches, 'coach_source': coach_source}
