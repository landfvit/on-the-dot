"""Player history with explicit competition scope and appearance/rating provenance."""
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import re

from fastapi import APIRouter, HTTPException

from api.database import get_connection

router = APIRouter()


def count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def total(values):
    values = list(values)
    return sum(values) if values and all(v is not None for v in values) else None


def average(values):
    values = [Decimal(str(v)) for v in values if v is not None and Decimal('0') < Decimal(str(v)) <= Decimal('10')]
    return float((sum(values) / len(values)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if values else None


def season_history(records, matches):
    """Never count unused substitutes; available match ratings have equal weight."""
    grouped = defaultdict(list)
    duplicate_fixtures = {fid for fid, n in Counter(m['fixture_id'] for m in matches).items() if n > 1}
    ambiguous_keys = {(m['league_id'], m['season'], m['team_id']) for m in matches if m['fixture_id'] in duplicate_fixtures}
    by_key = {(r['league_id'], r['season'], r['team_id']): dict(r) for r in records}
    for match in matches:
        key = (match['league_id'], match['season'], match['team_id'])
        by_key.setdefault(key, {k: match[k] for k in ('league_id', 'league_name', 'season', 'team_id', 'team_name', 'logo_url')})
        if match['fixture_id'] not in duplicate_fixtures and (match.get('started') or match.get('entered') or (match.get('minutes') or 0) > 0):
            grouped[key].append(match)
    seasons = defaultdict(list)
    for key, record in by_key.items():
        games = grouped[key]
        appearances = count(record.get('appearances'))
        source = 'provider_season' if appearances is not None else None
        starts, sub_in = count(record.get('lineups')), count(record.get('substitutes_in'))
        if appearances is None and starts is not None and sub_in is not None:
            appearances, source = starts + sub_in, 'starts_plus_substitutions'
        if appearances is None and games:
            appearances, source = len(games), 'recorded_matches'
        warnings = []
        if key in ambiguous_keys: warnings.append('ambiguous_match_records')
        if source == 'recorded_matches': warnings.append('partial_appearance_coverage')
        if appearances is not None and starts is not None and sub_in is not None and appearances != starts + sub_in:
            warnings.append('appearance_total_conflict')
        if appearances is not None and len(games) > appearances:
            warnings.append('appearance_match_conflict')
        stats = {field: count(record.get(field)) for field in ('goals_total', 'assists', 'yellow_cards', 'red_cards', 'yellow_red_cards')}
        if appearances == 0 and source != 'recorded_matches':
            # No appearance implies no goal/assist, but a player can be booked on the bench.
            for field in ('goals_total', 'assists'):
                if stats[field] is None: stats[field] = 0
        # Missing provider totals can only be reconstructed from a complete appearance sample.
        if source != 'recorded_matches' and appearances and len(games) == appearances:
            for field, match_field in [('goals_total', 'goals'), ('assists', 'assists')]:
                if stats[field] is None:
                    stats[field] = total(count(g.get(match_field)) for g in games)
        ratings = [g['rating'] for g in games if g.get('rating') is not None and 0 < g['rating'] <= 10]
        rating = average(ratings)
        rating_source = 'match_ratings' if rating is not None else None
        if rating is None and appearances != 0:
            rating = average([record.get('rating')])
            if rating is not None: rating_source = 'provider_season'
        item = {'team_id': key[2], 'team_name': record['team_name'], 'logo_url': record.get('logo_url'),
                'appearances': appearances, 'appearance_source': source, 'verified_appearances': len(games),
                'goals': stats['goals_total'], 'assists': stats['assists'], 'yellow_cards': stats['yellow_cards'],
                'straight_red_cards': stats['red_cards'], 'second_yellow_cards': stats['yellow_red_cards'],
                'red_cards': total([stats['red_cards'], stats['yellow_red_cards']]),
                'rating': rating, 'rating_source': rating_source, 'rated_matches': len(ratings),
                'warnings': warnings, '_ratings': ratings, 'league_name': record['league_name']}
        seasons[key[:2]].append(item)
    result = []
    for (league_id, season), clubs in seasons.items():
        clubs.sort(key=lambda c: (-(c['appearances'] or 0), c['team_name']))
        ratings = [r for club in clubs for r in club.pop('_ratings')]
        rating = average(ratings)
        rating_source = 'match_ratings' if rating is not None else None
        if not ratings and len(clubs) == 1:
            rating, rating_source = clubs[0]['rating'], clubs[0]['rating_source']
        result.append({'league_id': league_id, 'league_name': clubs[0]['league_name'], 'season': season,
                       'clubs': clubs, 'rating': rating, 'rating_source': rating_source, 'rated_matches': len(ratings),
                       'warnings': sorted({w for club in clubs for w in club['warnings']}),
                       **{field: total(club[field] for club in clubs) for field in
                          ('appearances', 'goals', 'assists', 'yellow_cards', 'red_cards', 'verified_appearances')}})
    return sorted(result, key=lambda r: (-r['season'], r['league_name']))


def club_name_key(name):
    return re.sub(r'\butd\b', 'united', re.sub(r'[^\w]+', ' ', name.casefold())).strip()


def normalize_transfers(rows, teams, today=None):
    today = today or date.today()
    aliases = defaultdict(set)
    for row in rows:
        for side in ('out', 'in'):
            if row.get(f'team_{side}_id') is not None and row.get(f'team_{side}_name'):
                aliases[club_name_key(row[f'team_{side}_name'])].add(row[f'team_{side}_id'])
    for team in teams.values():
        aliases[club_name_key(team['team_name'])].add(team['team_id'])

    def club(row, side):
        ident, name = row.get(f'team_{side}_id'), row.get(f'team_{side}_name')
        candidates = aliases.get(club_name_key(name or ''), set())
        if ident is None and len(candidates) == 1: ident = next(iter(candidates))
        stored = teams.get(ident, {})
        raw = (row.get('raw_payload') or {}).get('teams', {}).get(side) or {}
        return {'team_id': ident, 'name': stored.get('team_name') or name or 'Unknown club',
                'logo_url': raw.get('logo') or stored.get('logo_url'),
                'profile_seasons': stored.get('profile_seasons') or [],
                'key': str(ident) if ident is not None else 'name:' + club_name_key(name or 'unknown')}

    merged = {}
    for row in rows:
        transfer = {'date': row['transfer_date'], 'date_raw': row.get('transfer_date_raw'),
                    'type': row.get('transfer_type') or 'N/A', 'out': club(row, 'out'), 'in': club(row, 'in'),
                    'upcoming': bool(row['transfer_date'] and row['transfer_date'] > today), 'source_records': 1,
                    'source_order': row.get('transfer_id', 0)}
        key = (transfer['date'] or transfer['date_raw'], transfer['out']['key'], transfer['in']['key'], transfer['type'].casefold())
        if key in merged:
            merged[key]['source_records'] += 1
        else:
            merged[key] = transfer
    return sorted(merged.values(), key=lambda r: (r['date'] is None, -(r['date'].toordinal()) if r['date'] else 0,
                                                  -r['source_order']))


def club_history(transfers, seasons):
    """Confirmed moves bound spells; gaps and repeated arrival dates stay explicit."""
    spells, current = [], None
    days = Counter(t['date'] for t in transfers if t['date'] and not t['upcoming'])
    for transfer in sorted((t for t in transfers if t['date'] and not t['upcoming']), key=lambda t: (t['date'], t.get('source_order', 0))):
        origin, destination, day = transfer['out'], transfer['in'], transfer['date']
        if origin['key'] == destination['key']:
            continue
        if (current and current['club']['key'] == destination['key'] and current.get('arrival_from') == origin['key']
                and current['arrival_dates'] and day - current['arrival_dates'][-1] <= timedelta(days=7)):
            # Nearby inconsistent records are preserved in Transfers, not invented extra spells.
            if day not in current['arrival_dates']: current['arrival_dates'].append(day)
            current['uncertain'] = True
            continue
        if current and current['club']['key'] == origin['key']:
            current['end_date'] = day
        else:
            if current: current['uncertain'] = True
            spells.append({'club': origin, 'arrival_dates': [], 'end_date': day, 'entry_type': None, 'uncertain': True})
        current = {'club': destination, 'arrival_dates': [day], 'end_date': None,
                   'entry_type': transfer['type'], 'arrival_from': origin['key'], 'uncertain': days[day] > 1}
        spells.append(current)
    recorded = {s['club']['key'] for s in spells}
    additional = {}
    for transfer in transfers:
        if transfer['date'] or transfer['upcoming']: continue
        for club in (transfer['out'], transfer['in']):
            if club['key'] in recorded: continue
            additional.setdefault(club['key'], {'club': club, 'arrival_dates': [], 'end_date': None,
                                               'entry_type': None, 'uncertain': True, 'undated_transfer': True})
    for season in seasons:
        for team in season['clubs']:
            key = str(team['team_id'])
            if key in recorded: continue
            item = additional.setdefault(key, {'club': {'team_id': team['team_id'], 'name': team['team_name'],
                                                       'logo_url': team['logo_url'], 'profile_seasons': [], 'key': key},
                                               'arrival_dates': [], 'end_date': None, 'entry_type': None,
                                               'uncertain': True, 'recorded_seasons': []})
            item.setdefault('recorded_seasons', [])
            if season['season'] not in item['recorded_seasons']:
                item['recorded_seasons'].append(season['season'])
                item['club']['profile_seasons'].append(season['season'])
    for spell in spells:
        spell.pop('arrival_from', None)
    return list(reversed(spells)) + list(additional.values())


@router.get('/api/players/{player_id}/history')
def player_history(player_id: int):
    with get_connection() as conn:
        player = conn.execute('SELECT player_id, player_name FROM players WHERE player_id=%s', (player_id,)).fetchone()
        if not player: raise HTTPException(404, 'Player not found')
        records = conn.execute('''WITH membership AS (
                SELECT league_id,season,team_id FROM player_season_statistics WHERE player_id=%s
                UNION SELECT league_id,season,team_id FROM squad_memberships WHERE player_id=%s
            ) SELECT m.*, t.team_name, t.logo_url, l.league_name, s.appearances, s.lineups, s.substitutes_in,
                s.goals_total, s.assists, s.yellow_cards, s.yellow_red_cards, s.red_cards, s.rating
            FROM membership m JOIN teams t USING(team_id) JOIN leagues l USING(league_id)
            LEFT JOIN player_season_statistics s ON s.league_id=m.league_id AND s.season=m.season
                AND s.team_id=m.team_id AND s.player_id=%s''', (player_id, player_id, player_id)).fetchall()
        matches = conn.execute('''WITH candidate AS (
                SELECT fixture_id,team_id FROM fixture_player_statistics WHERE player_id=%s
                UNION SELECT fixture_id,team_id FROM fixture_lineup_players WHERE player_id=%s AND lineup_type='start_xi'
                UNION SELECT fixture_id,team_id FROM fixture_events WHERE assist_player_id=%s AND event_type='subst'
            ) SELECT c.fixture_id,c.team_id,f.season,f.league_id,t.team_name,t.logo_url,l.league_name,
                p.minutes,p.rating,p.goals,p.assists,
                EXISTS(SELECT 1 FROM fixture_lineup_players lp WHERE lp.fixture_id=c.fixture_id AND lp.team_id=c.team_id
                    AND lp.player_id=%s AND lp.lineup_type='start_xi') AS started,
                EXISTS(SELECT 1 FROM fixture_events e WHERE e.fixture_id=c.fixture_id AND e.team_id=c.team_id
                    AND e.assist_player_id=%s AND e.event_type='subst') AS entered
            FROM candidate c JOIN fixtures f USING(fixture_id) JOIN teams t ON t.team_id=c.team_id
            JOIN leagues l USING(league_id) LEFT JOIN fixture_player_statistics p ON p.fixture_id=c.fixture_id
                AND p.team_id=c.team_id AND p.player_id=%s
            WHERE f.status IN ('FT','AET','PEN') AND f.match_date<=NOW()''', (player_id,) * 6).fetchall()
        transfers = conn.execute('SELECT * FROM player_transfers WHERE player_id=%s ORDER BY transfer_date,transfer_id', (player_id,)).fetchall()
        ids = {r['team_id'] for r in records} | {r['team_id'] for r in matches}
        ids.update(r[f'team_{side}_id'] for r in transfers for side in ('in', 'out') if r[f'team_{side}_id'] is not None)
        teams = conn.execute('''SELECT t.team_id,t.team_name,t.logo_url,
            ARRAY(SELECT DISTINCT season FROM fixtures f WHERE f.league_id=39
                AND (f.home_team_id=t.team_id OR f.away_team_id=t.team_id) ORDER BY season DESC) AS profile_seasons
            FROM teams t WHERE t.team_id=ANY(%s)''', (list(ids),)).fetchall()
        status = conn.execute('''SELECT status,rows_received,imported_at FROM entity_import_status
            WHERE entity_type='player' AND entity_id=%s AND data_type='transfers' AND source='api-football' ''', (player_id,)).fetchone()
    seasons = season_history(records, matches)
    transfer_rows = normalize_transfers(transfers, {t['team_id']: t for t in teams})
    return {'player': player, 'source': 'API-Football', 'seasons': seasons, 'transfers': transfer_rows,
            'clubs': club_history(transfer_rows, seasons), 'transfer_import': status,
            'duplicate_transfer_records': len(transfers) - len(transfer_rows)}
