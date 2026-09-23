"""Match events and sourced environmental context; never infer missing events."""
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from api.database import get_connection
from api.trivia_engine import reconstruct, SCORING_DETAILS

router = APIRouter()


def event_order(event):
    return (event['elapsed_minute'] if event['elapsed_minute'] is not None else 10000,
            event['extra_minute'] or 0, event['source_order'])


def event_timeline(fixture, events):
    ordered = sorted(events, key=event_order)
    quality = reconstruct(fixture, ordered, fixture.get('events_imported', False))
    if fixture['match_date'] > datetime.now(timezone.utc):
        quality.update(result_valid=False, timeline_valid=False, intervals=[], reasons=['not_yet_played'])
    running = [0, 0]
    result = []
    for event in ordered:
        item = {key: value for key, value in event.items() if key != 'raw_payload'}
        item['side'] = ('home' if event['team_id'] == fixture['home_team_id'] else
                        'away' if event['team_id'] == fixture['away_team_id'] else 'unknown')
        item['score'] = None
        if quality['timeline_valid'] and event['event_type'] == 'Goal' and event['event_detail'] in SCORING_DETAILS:
            running[0 if item['side'] == 'home' else 1] += 1
            item['score'] = list(running)
        result.append(item)
    return {'events': result, 'quality': {k: v for k, v in quality.items() if k != 'intervals'},
            'source': 'API-Football'}


@router.get('/api/fixtures/{fixture_id}/context')
def match_context(fixture_id: int):
    with get_connection() as conn:
        fixture = conn.execute('''SELECT f.*, v.venue_name, v.city,
            h.team_name AS home_name, a.team_name AS away_name,
            EXISTS (SELECT 1 FROM fixture_raw_data r WHERE r.fixture_id=f.fixture_id
                AND ((r.data_type='fixture_complete' AND jsonb_typeof(r.payload->'events')='array')
                     OR r.data_type='events_direct')) AS events_imported
            FROM fixtures f LEFT JOIN venues v USING(venue_id)
            JOIN teams h ON h.team_id=f.home_team_id JOIN teams a ON a.team_id=f.away_team_id
            WHERE fixture_id=%s''', (fixture_id,)).fetchone()
        if not fixture:
            raise HTTPException(404, 'Match not found')
        events = conn.execute('''SELECT e.fixture_event_id, e.source_order, e.team_id, e.elapsed_minute,
            e.extra_minute, e.player_id, e.player_name, e.assist_player_id, e.assist_player_name,
            e.event_type, e.event_detail, e.comments, p.photo_url
            FROM fixture_events e LEFT JOIN players p ON p.player_id=e.player_id
            WHERE e.fixture_id=%s ORDER BY e.source_order''', (fixture_id,)).fetchall()
        attendance = conn.execute('SELECT * FROM fixture_attendance_sources WHERE fixture_id=%s', (fixture_id,)).fetchone()
        if attendance:
            capacity = attendance['historical_capacity']
            attendance['occupancy_percent'] = round(100 * attendance['attendance'] / capacity, 1) if capacity else None
        elif fixture['attendance'] is not None:
            attendance = {'attendance': fixture['attendance'], 'source': fixture['attendance_source'],
                          'verified_at': fixture['attendance_verified_at'], 'occupancy_percent': None}
        weather = conn.execute('''SELECT sampled_at, temperature_c, precipitation_mm, wind_kmh,
            weather_code, source_url, model, retrieved_at FROM fixture_weather
            WHERE fixture_id=%s AND kickoff_at=%s AND venue_id=%s''',
            (fixture_id, fixture['match_date'], fixture['venue_id'])).fetchone()
        rest = conn.execute('''SELECT team_id, MAX(match_date) AS previous_match FROM (
                SELECT home_team_id AS team_id, match_date FROM fixtures WHERE league_id=%s AND status='FT' AND match_date<%s
                UNION ALL SELECT away_team_id, match_date FROM fixtures WHERE league_id=%s AND status='FT' AND match_date<%s
            ) recent WHERE team_id=ANY(%s) GROUP BY team_id''',
            (fixture['league_id'], fixture['match_date'], fixture['league_id'], fixture['match_date'],
             [fixture['home_team_id'], fixture['away_team_id']])).fetchall()
    return {**event_timeline(fixture, events), 'fixture': {key: fixture[key] for key in (
        'fixture_id', 'season', 'status', 'home_team_id', 'away_team_id', 'home_name', 'away_name',
        'venue_name', 'city', 'referee', 'match_date')}, 'attendance': attendance, 'weather': weather,
        'league_rest': [{'team_id': row['team_id'], 'days': round((fixture['match_date'] - row['previous_match']).total_seconds() / 86400, 1)} for row in rest]}


def summarize_team(fixtures, events_by_fixture, team_id):
    played, verified = [], []
    buckets = [{'label': label, 'for': 0, 'against': 0} for label in ['0-15', '16-30', '31-45+', '46-60', '61-75', '76-90+']]
    situations = {key: {'matches': 0, 'wins': 0, 'draws': 0, 'losses': 0} for key in ('scored_first', 'conceded_first')}
    gained = dropped = trailing = leading = 0
    for fixture in fixtures:
        events = sorted(events_by_fixture.get(fixture['fixture_id'], []), key=event_order)
        quality = reconstruct(fixture, events, fixture['events_imported'])
        if fixture['match_date'] > datetime.now(timezone.utc) or not quality['result_valid']:
            continue
        home = fixture['home_team_id'] == team_id
        gf, ga = (fixture['home_goals'], fixture['away_goals']) if home else (fixture['away_goals'], fixture['home_goals'])
        result = 'W' if gf > ga else 'D' if gf == ga else 'L'
        points = {'W': 3, 'D': 1, 'L': 0}[result]
        played.append({'fixture_id': fixture['fixture_id'], 'date': fixture['match_date'], 'home': home,
                       'result': result, 'goals_for': gf, 'goals_against': ga, 'points': points})
        if not quality['timeline_valid']:
            continue
        verified.append(fixture['fixture_id'])
        goals = [e for e in events if e['event_type'] == 'Goal' and e['event_detail'] in SCORING_DETAILS]
        differences, difference = [], 0
        for goal in goals:
            difference += 1 if goal['team_id'] == team_id else -1
            differences.append(difference)
        if any(d < 0 for d in differences):
            gained += points; trailing += 1
        if any(d > 0 for d in differences):
            dropped += 3 - points; leading += 1
        if goals:
            # Events sharing a minute use the provider's source order, not inferred seconds.
            group = situations['scored_first' if goals[0]['team_id'] == team_id else 'conceded_first']
            group['matches'] += 1
            group[{'W': 'wins', 'D': 'draws', 'L': 'losses'}[result]] += 1
        for goal in goals:
            bucket = min(5, max(0, (goal['elapsed_minute'] - 1) // 15))
            buckets[bucket]['for' if goal['team_id'] == team_id else 'against'] += 1

    def totals(rows):
        n = len(rows)
        return {'matches': n, 'wins': sum(r['result'] == 'W' for r in rows),
                'draws': sum(r['result'] == 'D' for r in rows), 'losses': sum(r['result'] == 'L' for r in rows),
                'points': sum(r['points'] for r in rows), 'goals_for': sum(r['goals_for'] for r in rows),
                'goals_against': sum(r['goals_against'] for r in rows),
                'points_per_match': round(sum(r['points'] for r in rows) / n, 2) if n else None,
                'form': [r['result'] for r in rows]}
    played.sort(key=lambda r: (r['date'], r['fixture_id']))
    return {'results_matches': len(played), 'timeline_matches': len(verified),
            'excluded_timelines': len(played) - len(verified), 'points_gained': gained if verified else None,
            'points_dropped': dropped if verified else None, 'matches_trailed': trailing, 'matches_led': leading,
            'first_goal': situations, 'goal_intervals': buckets if verified else [],
            'splits': {'all': totals(played), 'home': totals([r for r in played if r['home']]),
                       'away': totals([r for r in played if not r['home']]),
                       'last5': totals(played[-5:]), 'last10': totals(played[-10:])}}


@router.get('/api/teams/{team_id}/insights')
def team_insights(team_id: int, season: int, league_id: int = 39):
    with get_connection() as conn:
        fixtures = conn.execute('''SELECT f.*, EXISTS (SELECT 1 FROM fixture_raw_data r WHERE r.fixture_id=f.fixture_id
            AND ((r.data_type='fixture_complete' AND jsonb_typeof(r.payload->'events')='array')
                 OR r.data_type='events_direct')) AS events_imported
            FROM fixtures f WHERE league_id=%s AND season=%s AND (home_team_id=%s OR away_team_id=%s)
            ORDER BY match_date, fixture_id''', (league_id, season, team_id, team_id)).fetchall()
        if not fixtures:
            raise HTTPException(404, 'Team not found in this season')
        events = conn.execute('''SELECT fixture_id, source_order, team_id, elapsed_minute, extra_minute,
            player_id, event_type, event_detail FROM fixture_events WHERE fixture_id=ANY(%s)''',
            ([f['fixture_id'] for f in fixtures],)).fetchall()
    grouped = defaultdict(list)
    for event in events:
        grouped[event['fixture_id']].append(event)
    return {'team_id': team_id, 'season': season, 'source': 'API-Football', **summarize_team(fixtures, grouped, team_id)}
