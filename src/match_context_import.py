"""Explicit, resumable imports for stadium coordinates, weather and attendance."""
import argparse
import csv
import json
import math
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import requests
from psycopg.types.json import Jsonb
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.database import get_connection

WEATHER_URL = 'https://archive-api.open-meteo.com/v1/archive'
VARIABLES = ['temperature_2m', 'precipitation', 'wind_speed_10m', 'weather_code']


def source_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('A public HTTP(S) source URL is required')
    return value


def coordinates(mapping_path):
    mapping = json.loads(Path(mapping_path).read_text())
    session = requests.Session()
    session.headers['User-Agent'] = 'PLAnalytics/0.1 (local football research)'
    # Explicit venue mappings avoid matching a town, cricket ground or replacement stadium.
    pending = {}
    for venue_id, title in mapping.items():
        with get_connection() as conn:
            if conn.execute('SELECT 1 FROM venue_locations WHERE venue_id=%s', (int(venue_id),)).fetchone():
                continue
            if not conn.execute('SELECT 1 FROM venues WHERE venue_id=%s', (int(venue_id),)).fetchone():
                raise ValueError(f'Unknown venue: {venue_id}')
        pending[venue_id] = title
    entries = list(pending.items())
    for start in range(0, len(entries), 50):
        batch = entries[start:start + 50]
        response = session.get('https://en.wikipedia.org/w/api.php', params={
            'action': 'query', 'titles': '|'.join(title for _, title in batch), 'prop': 'coordinates', 'format': 'json', 'redirects': 1,
        }, timeout=30)
        response.raise_for_status()
        query = response.json().get('query', {})
        pages = {page['title']: page for page in query.get('pages', {}).values()}
        redirects = {item['from']: item['to'] for key in ('normalized', 'redirects') for item in query.get(key, [])}
        with get_connection() as conn:
            for venue_id, title in batch:
                visited = set()
                while title in redirects and title not in visited:
                    visited.add(title); title = redirects[title]
                page = pages.get(title, {})
                if not page.get('coordinates'):
                    raise ValueError(f'No unique coordinates: {title}')
                point = page['coordinates'][0]
                if point.get('globe') != 'earth' or not (49 < point['lat'] < 61 and -9 < point['lon'] < 3):
                    raise ValueError(f'Unexpected UK stadium coordinates: {title}')
                url = 'https://en.wikipedia.org/wiki/' + quote(title.replace(' ', '_'))
                conn.execute('''INSERT INTO venue_locations(venue_id,latitude,longitude,source_url)
                    VALUES (%s,%s,%s,%s) ON CONFLICT(venue_id) DO NOTHING''',
                    (int(venue_id), point['lat'], point['lon'], url))
                print(f'Location: {venue_id} {title}', flush=True)
        time.sleep(1)


def weather_sample(payload, kickoff):
    hourly = payload.get('hourly', {})
    times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in hourly.get('time', [])]
    if not times:
        raise ValueError('Weather response has no hourly samples')
    index = min(range(len(times)), key=lambda i: abs((times[i] - kickoff).total_seconds()))
    if abs((times[index] - kickoff).total_seconds()) > 1800:
        raise ValueError('Weather response does not cover kickoff within 30 minutes')
    values = {}
    for key in VARIABLES:
        series = hourly.get(key, [])
        value = series[index] if index < len(series) else None
        if value is not None and (not isinstance(value, (float, int)) or not math.isfinite(value)):
            raise ValueError(f'Invalid weather value: {key}')
        values[key] = value
    if all(value is None for value in values.values()):
        raise ValueError('Weather sample is empty')
    return times[index], values


def weather(season, league_id, refresh=False):
    session = requests.Session()
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=2, connect=2, read=2, status=0,
        backoff_factor=2, respect_retry_after_header=True, raise_on_status=False)))
    with get_connection() as conn:
        fixtures = conn.execute('''SELECT f.fixture_id, f.venue_id, f.match_date, l.latitude, l.longitude
            FROM fixtures f JOIN venue_locations l USING(venue_id)
            LEFT JOIN fixture_weather w ON w.fixture_id=f.fixture_id
            WHERE f.season=%s AND f.league_id=%s AND f.status='FT' AND f.match_date < NOW() - INTERVAL '7 days'
              AND (%s OR w.fixture_id IS NULL OR w.kickoff_at<>f.match_date OR w.venue_id<>f.venue_id)
            ORDER BY f.venue_id, f.match_date''', (season, league_id, refresh)).fetchall()
        missing = conn.execute('''SELECT COUNT(*) AS n FROM fixtures f LEFT JOIN venue_locations l USING(venue_id)
            WHERE f.season=%s AND f.league_id=%s AND f.status='FT' AND f.match_date < NOW()
              AND l.venue_id IS NULL''', (season, league_id)).fetchone()['n']
    groups = defaultdict(list)
    for fixture in fixtures:
        # Annual batches bound payloads while avoiding one provider request per fixture.
        groups[(fixture['venue_id'], fixture['match_date'].astimezone(timezone.utc).strftime('%Y'))].append(fixture)
    imported = 0
    for (venue_id, month), rows in groups.items():
        start = min(r['match_date'] for r in rows).astimezone(timezone.utc).date()
        end = max(r['match_date'] for r in rows).astimezone(timezone.utc).date() + timedelta(days=1)
        response = session.get(WEATHER_URL, params={
            'latitude': rows[0]['latitude'], 'longitude': rows[0]['longitude'],
            'start_date': start.isoformat(), 'end_date': end.isoformat(), 'hourly': ','.join(VARIABLES),
            'models': 'era5', 'timezone': 'UTC', 'wind_speed_unit': 'kmh',
        }, timeout=60)
        response.raise_for_status()  # Stop on rate limits; a later run skips completed rows.
        payload = response.json()
        with get_connection() as conn:
            for fixture in rows:
                sampled_at, values = weather_sample(payload, fixture['match_date'])
                raw = {'values': values, 'hourly_units': payload.get('hourly_units'),
                       'grid_latitude': payload.get('latitude'), 'grid_longitude': payload.get('longitude')}
                conn.execute('''INSERT INTO fixture_weather
                    (fixture_id,venue_id,kickoff_at,sampled_at,latitude,longitude,temperature_c,precipitation_mm,
                     wind_kmh,weather_code,source_url,model,raw_payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'ERA5',%s)
                    ON CONFLICT(fixture_id) DO UPDATE SET venue_id=EXCLUDED.venue_id,kickoff_at=EXCLUDED.kickoff_at,
                    sampled_at=EXCLUDED.sampled_at,latitude=EXCLUDED.latitude,longitude=EXCLUDED.longitude,
                    temperature_c=EXCLUDED.temperature_c,precipitation_mm=EXCLUDED.precipitation_mm,
                    wind_kmh=EXCLUDED.wind_kmh,weather_code=EXCLUDED.weather_code,source_url=EXCLUDED.source_url,
                    model=EXCLUDED.model,raw_payload=EXCLUDED.raw_payload,retrieved_at=NOW()''',
                    (fixture['fixture_id'], venue_id, fixture['match_date'], sampled_at, fixture['latitude'], fixture['longitude'],
                     values['temperature_2m'], values['precipitation'], values['wind_speed_10m'], values['weather_code'],
                     response.url, Jsonb(raw)))
                imported += 1
        print(f'Weather: {venue_id} {month}, {len(rows)} matches ({imported} total)', flush=True)
        time.sleep(1)
    print(f'Imported {imported}; {missing} finished matches missing stadium coordinates', flush=True)


def attendance(path, replace=False):
    with Path(path).open(newline='', encoding='utf-8-sig') as file:
        rows = list(csv.DictReader(file))
    seen = set()
    with get_connection() as conn:
        for row in rows:
            fixture_id = int(row['fixture_id'])
            if fixture_id in seen:
                raise ValueError(f'Duplicate fixture: {fixture_id}')
            seen.add(fixture_id)
            fixture = conn.execute('SELECT * FROM fixtures WHERE fixture_id=%s FOR UPDATE', (fixture_id,)).fetchone()
            if not fixture or (fixture['home_team_id'], fixture['away_team_id'], fixture['match_date'].astimezone(timezone.utc).date()) != (
                int(row['home_team_id']), int(row['away_team_id']), date.fromisoformat(row['date_utc'])
            ):
                raise ValueError(f'Fixture identity mismatch: {fixture_id}')
            if fixture['status'] != 'FT' or fixture['match_date'] > datetime.now(timezone.utc):
                raise ValueError(f'Attendance requires a completed match: {fixture_id}')
            count = int(row['attendance'])
            capacity = int(row['historical_capacity']) if row.get('historical_capacity') else None
            url = source_url(row['source_url'])
            capacity_url = source_url(row['capacity_source_url']) if capacity else None
            if count < 0 or (capacity is not None and (capacity <= 0 or count > capacity)):
                raise ValueError(f'Invalid attendance/capacity: {fixture_id}')
            existing = conn.execute('SELECT attendance FROM fixture_attendance_sources WHERE fixture_id=%s', (fixture_id,)).fetchone()
            if not replace and ((existing and existing['attendance'] != count) or
                                (fixture['attendance'] is not None and fixture['attendance'] != count)):
                raise ValueError(f'Conflicting attendance: {fixture_id}; explicit --replace required')
            conn.execute('''INSERT INTO fixture_attendance_sources
                (fixture_id,attendance,source_url,historical_capacity,capacity_source_url) VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT(fixture_id) DO UPDATE SET attendance=EXCLUDED.attendance,source_url=EXCLUDED.source_url,
                historical_capacity=EXCLUDED.historical_capacity,capacity_source_url=EXCLUDED.capacity_source_url,verified_at=NOW()''',
                (fixture_id, count, url, capacity, capacity_url))
            conn.execute("UPDATE fixtures SET attendance=%s,attendance_source='verified_report',attendance_verified_at=NOW() WHERE fixture_id=%s", (count, fixture_id))
    print(f'Imported attendance for {len(rows)} matches')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    locations = commands.add_parser('locations')
    locations.add_argument('--mapping', type=Path, default=ROOT / 'data/enrichment/venue_wikipedia.json')
    rain = commands.add_parser('weather')
    rain.add_argument('--season', type=int, required=True)
    rain.add_argument('--league-id', type=int, default=39)
    rain.add_argument('--refresh', action='store_true')
    crowd = commands.add_parser('attendance')
    crowd.add_argument('csv', type=Path)
    crowd.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    if args.command == 'locations': coordinates(args.mapping)
    elif args.command == 'weather': weather(args.season, args.league_id, args.refresh)
    else: attendance(args.csv, args.replace)


if __name__ == '__main__':
    main()
