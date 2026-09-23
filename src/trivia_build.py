"""Create an immutable, audited trivia dataset from a consistent database snapshot."""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from psycopg.types.json import Jsonb
from api.database import get_connection
from api.trivia_engine import ENGINE_VERSION, reconstruct
from api.trivia_player_facts import player_facts


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True).encode()).hexdigest()


def build():
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        conn.execute('SELECT pg_advisory_xact_lock(84424322)')
        fixtures = conn.execute('''
            SELECT f.*, h.team_name AS home_name, a.team_name AS away_name, l.league_name,
                   EXISTS (SELECT 1 FROM fixture_raw_data r WHERE r.fixture_id=f.fixture_id
                     AND ((r.data_type='fixture_complete' AND jsonb_typeof(r.payload->'events')='array')
                          OR r.data_type='events_direct')) AS events_imported
            FROM fixtures f JOIN teams h ON h.team_id=f.home_team_id
            JOIN teams a ON a.team_id=f.away_team_id JOIN leagues l USING(league_id)
            ORDER BY f.fixture_id
        ''').fetchall()
        if not fixtures:
            raise ValueError('No source fixtures; existing datasets preserved')
        events = defaultdict(list)
        for event in conn.execute('''
            SELECT fixture_id, source_order, team_id, elapsed_minute, extra_minute,
                   player_id, player_name, assist_player_id, event_type, event_detail
            FROM fixture_events ORDER BY fixture_id, source_order
        ''').fetchall():
            events[event['fixture_id']].append(event)
        lineups, statistics = defaultdict(list), defaultdict(list)
        for row in conn.execute('''SELECT fixture_id, team_id, player_id, player_name, lineup_type
            FROM fixture_lineup_players ORDER BY fixture_id,team_id,lineup_type,source_order''').fetchall():
            lineups[row['fixture_id']].append(row)
        for row in conn.execute('''SELECT fixture_id,team_id,player_id,player_name,minutes,goals,assists,
            shots_total,shots_on_goal,passes_total,key_passes,tackles_total,interceptions,
            yellow_cards,yellow_red_cards,red_cards,rating FROM fixture_player_statistics
            ORDER BY fixture_id,team_id,player_id''').fetchall():
            statistics[row['fixture_id']].append(row)
        identities = {r['player_id']: r for r in conn.execute(
            'SELECT player_id,player_name,first_name,last_name FROM players').fetchall()}
        ident = uuid4()
        quality_rows, fact_rows, interval_rows, hashes = [], [], [], []
        player_rows, event_rows, player_quality_rows = [], [], []
        counts = Counter()
        leagues = {}
        for fixture in fixtures:
            fid = fixture['fixture_id']
            quality = reconstruct(fixture, events[fid], fixture['events_imported'])
            if fixture['match_date'] > now:
                quality.update(result_valid=False, timeline_valid=False, intervals=[])
                quality['reasons'] = ['not_yet_played']
            players = player_facts(fixture, events[fid], lineups[fid], statistics[fid], identities, quality['timeline_valid'])
            source_hash = fingerprint({'fixture': fixture, 'events': events[fid], 'quality': quality, 'players': players})
            hashes.append(source_hash)
            quality_rows.append((ident, fid, quality['result_valid'], quality['timeline_valid'], Jsonb(quality['reasons']), source_hash))
            counts['fixtures'] += 1
            counts['result_valid'] += int(quality['result_valid'])
            counts['timeline_valid'] += int(quality['timeline_valid'])
            counts['scorers_valid'] += int(players['scorers_valid'])
            counts['substitutes_valid'] += int(players['substitutes_valid'])
            player_quality_rows.append((ident, fid, players['scorers_valid'], players['substitutes_valid'],
                                        Jsonb(players['reasons']), Jsonb(players['substitute_reasons'])))
            for row in players['players']:
                player_rows.append((ident, fid, row['team_id'], row['player_id'], row['player_name'],
                    Jsonb(row['aliases']), row['appeared'], row['role'], Jsonb(row['statistics'])))
            for row in players['events']:
                event_rows.append((ident, fid, row['source_order'], row['team_id'], row['player_id'],
                    row['assist_player_id'], row['player_name'], Jsonb(row['aliases']), row['clock_key'],
                    row['event_type'], row['event_detail'], row['scorer_role']))
            leagues.setdefault(str(fixture['league_id']), {'name': fixture['league_name'], 'seasons': set()})['seasons'].add(fixture['season'])
            for side, other in [('home', 'away'), ('away', 'home')]:
                gf, ga = fixture[f'{side}_goals'], fixture[f'{other}_goals']
                result = ('W' if gf > ga else 'D' if gf == ga else 'L') if quality['result_valid'] else None
                fact_rows.append((ident, fid, fixture['league_id'], fixture['season'], fixture['match_date'],
                                  fixture[f'{side}_team_id'], fixture[f'{side}_name'], fixture[f'{other}_team_id'],
                                  fixture[f'{other}_name'], side == 'home', gf, ga, result, fixture['status']))
            interval_rows.extend((ident, fid, *interval) for interval in quality['intervals'])
        for league in leagues.values():
            league['seasons'] = sorted(league['seasons'], reverse=True)
        summary = {**counts, 'leagues': leagues, 'intervals': len(interval_rows),
                   'player_facts': len(player_rows), 'event_facts': len(event_rows),
                   'capabilities': ['player_goals', 'top_scorer', 'comeback_wins', 'most_comeback_wins']}
        source_hash = fingerprint([ENGINE_VERSION, hashes])
        existing = conn.execute('SELECT dataset_id FROM trivia_datasets WHERE source_hash=%s ORDER BY created_at DESC LIMIT 1',
                                (source_hash,)).fetchone()
        if existing:
            print(f"Unchanged dataset: {existing['dataset_id']}")
            return existing['dataset_id']
        conn.execute('INSERT INTO trivia_datasets(dataset_id,engine_version,source_hash,summary) VALUES (%s,%s,%s,%s)',
                     (ident, ENGINE_VERSION, source_hash, Jsonb(summary)))
        with conn.cursor() as cursor:
            cursor.executemany('INSERT INTO trivia_match_data_quality VALUES (%s,%s,%s,%s,%s,%s)', quality_rows)
            cursor.executemany('INSERT INTO trivia_match_team_facts VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', fact_rows)
            cursor.executemany('INSERT INTO trivia_match_state_intervals VALUES (%s,%s,%s,%s,%s,%s)', interval_rows)
            cursor.executemany('INSERT INTO trivia_match_player_facts VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)', player_rows)
            cursor.executemany('INSERT INTO trivia_event_facts VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', event_rows)
            cursor.executemany('INSERT INTO trivia_player_data_quality VALUES (%s,%s,%s,%s,%s,%s)', player_quality_rows)
        conn.execute('UPDATE trivia_datasets SET sealed_at=NOW() WHERE dataset_id=%s', (ident,))
        print(json.dumps({'dataset_id': str(ident), **summary}), flush=True)
        return ident


if __name__ == '__main__':
    build()
