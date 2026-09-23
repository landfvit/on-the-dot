"""Career aggregation by resolved identity, with explicit coverage limitations."""
from collections import defaultdict

from fastapi import HTTPException


def summarize(events, statistics, player, dataset):
    groups = defaultdict(lambda: {'recorded_goals': 0, 'quality_checked_goals': 0})
    for event in events:
        group = groups[event['season'], event['team_id']]
        group['recorded_goals'] += 1
        group['quality_checked_goals'] += int(bool(event['verified']))
    provider = {(r['season'], r['team_id']): r['goals_total'] for r in statistics}
    names = {r['team_id']: r.get('team_name', f"Club {r['team_id']}") for r in [*statistics, *events]}
    seasons = sorted({key[0] for key in groups} | {key[0] for key in provider})
    breakdown = []
    for season, team in sorted(set(groups) | set(provider)):
        group = groups[season, team]
        breakdown.append({'season': f'{season}/{(season+1)%100:02d}', 'team_id': team, 'team': names[team],
                          **group, 'provider_season_goals': provider.get((season, team))})
    recorded = sum(row['recorded_goals'] for row in groups.values())
    checked = sum(row['quality_checked_goals'] for row in groups.values())
    # A known player's earliest observed goal is NOT proof of their career start.
    # Provider season rows and event facts may both omit earlier seasons or matches.
    return {'answer': f'{recorded} recorded goals (partial verification)',
            'details': {'player': player['name'], 'player_id': player['player_id'],
                'recorded_goals': recorded, 'quality_checked_goals': checked,
                'scope': 'Premier League, all available seasons and clubs',
                'seasons': ', '.join(f'{s}/{(s+1)%100:02d}' for s in seasons) or 'None available',
                'dataset_sealed_at': str(dataset['sealed_at'])},
            'breakdown': breakdown, 'seasons': seasons,
            'evidence_fixture_ids': sorted({e['fixture_id'] for e in events}),
            'coverage': {'status': 'partial', 'career_complete': False,
                'message': 'Recorded goals are not a certified career total. Some match events may be missing or fail quality checks; full career coverage has not been established. Provider season totals are shown for comparison, not substituted for event evidence.'},
            'savable': False}


def calculate(conn, dataset_id, name):
    players = conn.execute('''SELECT player_id, player_name,
        trim(concat_ws(' ', first_name, last_name)) AS full_name
        FROM players WHERE lower(trim(player_name))=lower(%s)
          OR lower(trim(concat_ws(' ',first_name,last_name)))=lower(%s)
          OR lower(trim(last_name))=lower(%s)''', (name.strip(),) * 3).fetchall()
    if not players:
        raise HTTPException(422, 'The player name is understood but has no exact database identity. Check the spelling or use the full name.')
    if len(players) != 1:
        raise HTTPException(422, 'More than one player matches. Use the full name; no player was guessed.')
    player = players[0]
    dataset = conn.execute('SELECT sealed_at FROM trivia_datasets WHERE dataset_id=%s AND sealed_at IS NOT NULL', (dataset_id,)).fetchone()
    if not dataset:
        raise HTTPException(409, 'The selected sealed dataset is unavailable.')
    events = conn.execute('''SELECT e.fixture_id,f.season,e.team_id,f.team_name,
        (q.scorers_valid AND m.timeline_valid AND m.result_valid) AS verified
        FROM trivia_event_facts e
        JOIN trivia_match_team_facts f USING(dataset_id,fixture_id,team_id)
        LEFT JOIN trivia_player_data_quality q USING(dataset_id,fixture_id)
        LEFT JOIN trivia_match_data_quality m USING(dataset_id,fixture_id)
        WHERE e.dataset_id=%s AND e.player_id=%s AND f.league_id=39
          AND e.event_type='Goal' AND e.event_detail IN ('Normal Goal','Penalty')
        ORDER BY f.season,e.fixture_id,e.source_order''', (dataset_id, player['player_id'])).fetchall()
    stats = conn.execute('''SELECT s.season,s.team_id,s.goals_total,t.team_name
        FROM player_season_statistics s JOIN teams t USING(team_id)
        WHERE s.league_id=39 AND s.player_id=%s ORDER BY s.season,s.team_id''', (player['player_id'],)).fetchall()
    return summarize(events, stats, {'name': player['full_name'] or player['player_name'],
                                    'player_id': player['player_id']}, dataset)
