"""Bounded HTTP load test against a NEW disposable LOCAL PostgreSQL database.

Copies only the existing game-data allowlist, never real accounts or matches.
Starts its own one-worker Uvicorn on an ephemeral loopback port. There is no
remote target option. Synthetic clients keep production rate limits enabled.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tools.database_snapshot import settings
from tools.render_game_database import export_bundle, restore_bundle

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {'FINISHED', 'ABANDONED'}


def local_config(path):
    config = settings(path)
    if config.get('host') not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('Only an explicitly local source database is allowed')
    return config


@contextmanager
def isolated_database(source, directory):
    name = 'otd_stress_' + uuid4().hex
    target = {**source, 'dbname': name}
    # Export is read-only and contains no accounts, sessions or game history.
    export_bundle(source, directory / 'bundle')
    with psycopg.connect(**source, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            restore_bundle(target, directory / 'bundle')
            yield target
        finally:
            # Only the UUID database created by this invocation can be dropped.
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
            print('Removed disposable stress database.', flush=True)


def identities(conn, count, prefix):
    clubs = [r['team_id'] for r in conn.execute('SELECT team_id FROM game_clubs ORDER BY team_id')]
    result = []
    for i in range(count):
        ident, token = uuid4(), uuid4().hex
        username = f'{prefix}_{i}'
        conn.execute('''INSERT INTO game_accounts(account_id,username,email,password_hash,club_id)
            VALUES(%s,%s,%s,'!',%s)''',
            (ident, username, username + '@example.invalid', clubs[i % len(clubs)] if clubs else None))
        conn.execute('INSERT INTO game_sessions(token_hash,account_id) VALUES(%s,%s)',
                     (hashlib.sha256(token.encode()).hexdigest(), ident))
        result.append({'id': str(ident), 'cookie': 'points_account=' + token})
    return result


def seed_history(config, players, runs):
    from api import solo_engine
    from api.solo_routes import load_deck, Start, persist
    now = int(time.time() * 1000)
    with psycopg.connect(**config, row_factory=dict_row) as conn:
        users = identities(conn, players, 'history')
        deck, category = load_deck(conn, None, Start(request_id=uuid4()), now)
        # One completed game per account per historical week avoids creating
        # impossible duplicate weekly question allocations. All triggers stay on.
        templates = []
        for week in range(math.ceil(runs / players)):
            then = now - (week + 1) * 7 * 86400000
            for question in deck:
                question['allocated_at'] = then
            state = solo_engine.create(deck, 'easy', category, then)
            for position in range(6):
                solo_engine.advance(state, position, then + position * 8000)
                solo_engine.answer(state, position + 1, state['deck'][position]['correct'],
                                   str(uuid4()), then + position * 8000 + 4000)
            assert state['phase'] == 'FINISHED'
            templates.append(state)
        for i in range(runs):
            state = templates[i // players]
            row = {'run_id': uuid4(), 'account_id': users[i % players]['id'], 'is_trial': False, 'state': state}
            conn.execute('''INSERT INTO game_solo_runs(run_id,account_id,start_request_id,state,created_at)
                VALUES(%s,%s,%s,%s,to_timestamp(%s/1000.0))''',
                (row['run_id'], row['account_id'], uuid4(), Jsonb(state), state['created_at']))
            persist(conn, row)
            if (i + 1) % 1000 == 0:
                print(f'Seeded {i + 1}/{runs} synthetic completed matches.', flush=True)
    with psycopg.connect(**config, autocommit=True) as conn:
        conn.execute('ANALYZE')


@contextmanager
def server(config, directory):
    env = os.environ.copy()
    env.update(DATABASE_URL=make_conninfo(**config), TRIVIA_HTTPS_ONLY='0',
               TRIVIA_SESSION_SECRET=uuid4().hex + uuid4().hex,
               TRIVIA_EDITOR_USERNAME='', TRIVIA_EDITOR_PASSWORD='', WEB_CONCURRENCY='1')
    with socket.socket() as listener, (directory / 'server.log').open('w') as log:
        listener.bind(('127.0.0.1', 0))
        listener.listen(256)
        origin = f'http://127.0.0.1:{listener.getsockname()[1]}'
        # X-Forwarded-For models distinct clients on THIS loopback-only server;
        # database-backed production throttles are not patched or disabled.
        proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'trivia_app.main:app',
            '--fd', str(listener.fileno()), '--workers', '1', '--no-access-log',
            '--proxy-headers', '--forwarded-allow-ips', '127.0.0.1'],
            cwd=ROOT, env=env, pass_fds=(listener.fileno(),), stdout=log, stderr=log)
        try:
            for _ in range(150):
                if proc.poll() is not None:
                    raise RuntimeError('Test server exited during startup')
                try:
                    if httpx.get(origin + '/', timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.2)
            else:
                raise RuntimeError('Test server readiness timeout')
            yield origin, proc
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def percentile(values, fraction):
    return round(sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)], 2) if values else None


class Measurements:
    def __init__(self):
        self.rows = []
        self.errors = Counter()
        self.missed_ticks = 0
        self.completed = Counter()

    async def request(self, client, user, method, path, label, expected=200, body=None):
        started = time.perf_counter()
        status, payload = 0, None
        try:
            response = await client.request(method, path, json=body, headers=user['headers'])
            status = response.status_code
            if status == expected:
                payload = response.json()
                if response.cookies:
                    user['headers']['Cookie'] = '; '.join(f'{k}={v}' for k, v in response.cookies.items())
            else:
                self.errors[f'{label}:HTTP {status}'] += 1
        except (httpx.HTTPError, ValueError) as error:
            self.errors[f'{label}:{type(error).__name__}'] += 1
        self.rows.append((label, (time.perf_counter() - started) * 1000, status == expected))
        return payload

    def summary(self, elapsed):
        groups = defaultdict(list)
        for label, ms, ok in self.rows:
            groups[label].append((ms, ok))
        return {'requests': len(self.rows), 'elapsed_s': round(elapsed, 2),
            'rps': round(len(self.rows) / elapsed, 2), 'errors': dict(self.errors),
            'error_rate': round(sum(not ok for _, _, ok in self.rows) / max(1, len(self.rows)), 4),
            'p95_ms': percentile([ms for _, ms, _ in self.rows], .95),
            'p99_ms': percentile([ms for _, ms, _ in self.rows], .99),
            'missed_one_second_ticks': self.missed_ticks, 'completed_games': dict(self.completed),
            'endpoints': {label: {'n': len(rows), 'errors': sum(not ok for _, ok in rows),
                'p50_ms': percentile([ms for ms, _ in rows], .5),
                'p95_ms': percentile([ms for ms, _ in rows], .95),
                'p99_ms': percentile([ms for ms, _ in rows], .99)} for label, rows in sorted(groups.items())}}


async def wait_tick(due, metrics):
    remaining = due - time.monotonic()
    if remaining < -1:
        metrics.missed_ticks += int(-remaining)
        return time.monotonic()
    await asyncio.sleep(max(0, remaining))
    return due


async def solo_player(client, user, kind, until, metrics):
    prefix = '/api/' + kind
    state = None
    next_action = time.monotonic()
    tick = next_action + random.Random(user['id']).random()
    shot_started = tick
    while time.monotonic() < until:
        tick = await wait_tick(tick, metrics)
        if time.monotonic() >= until:
            break
        current = time.monotonic()
        if state is None:
            body = {'request_id': str(uuid4())}
            if kind == 'solo':
                body['difficulty'] = user['difficulty']
            state = await metrics.request(client, user, 'POST', prefix + '/runs', kind + ':start', 201, body)
        elif state['phase'] in TERMINAL:
            metrics.completed[kind] += 1
            await metrics.request(client, user, 'GET', '/api/players/me', 'profile')
            state = None
        elif state['phase'] in ('READY', 'REVIEW'):
            if current >= next_action:
                state = await metrics.request(client, user, 'POST', prefix + '/runs/' + state['run_id'] + '/next',
                    kind + ':next', body={'previous': state['position']}) or state
                shot_started = time.monotonic()
        elif state['phase'] == 'ANSWERING':
            path = prefix + '/runs/' + state['run_id']
            if current - shot_started >= 5:
                state = await metrics.request(client, user, 'POST', path + '/answers', kind + ':answer', body={
                    'position': state['position'], 'option_id': state['question']['options'][0]['id'],
                    'request_id': str(uuid4())}) or state
                next_action = time.monotonic() + 2
            else:
                state = await metrics.request(client, user, 'GET', path, kind + ':poll') or state
        tick += 1


async def friend_pair(client, pair, until, metrics):
    a, b = pair
    state = await metrics.request(client, a, 'POST', '/api/friends/rooms', 'friend:create', 201,
                                  {'difficulty': 'medium', 'request_id': str(uuid4())})
    if not state:
        return
    path = '/api/friends/rooms/' + state['code']
    if not await metrics.request(client, b, 'POST', path + '/join', 'friend:join'):
        return
    for user in pair:
        await metrics.request(client, user, 'POST', path + '/ready', 'friend:ready')

    async def play(user):
        tick = time.monotonic()
        while time.monotonic() < until:
            tick = await wait_tick(tick, metrics)
            if time.monotonic() >= until:
                break
            state = await metrics.request(client, user, 'GET', path, 'friend:poll')
            if state and state['phase'] in TERMINAL:
                if user is a:
                    metrics.completed['friend'] += 1
                return
            if state and state['phase'] == 'ANSWERING' and state['round']['own_option'] is None:
                if state['server_now'] - state['round']['opens_at'] >= 5000:
                    await metrics.request(client, user, 'POST', path + '/answers', 'friend:answer', body={
                        'position': state['round']['id'], 'option_id': state['question']['options'][0]['id'],
                        'request_id': str(uuid4())})
            tick += 1
    await asyncio.gather(*(play(user) for user in pair))


async def boards(client, user, until, metrics):
    index = 0
    while time.monotonic() < until:
        metric = ['xp', 'wins', 'streak', 'win_rate', 'level', 'daily_highscore'][index % 6]
        board = 'players' if index % 2 == 0 else 'teams'
        await metrics.request(client, user, 'GET',
            f'/api/community/leaderboard?period=all&metric={metric}&board={board}', 'leaderboard:' + metric)
        index += 1
        await asyncio.sleep(2)


def database_snapshot(config):
    with psycopg.connect(**config, row_factory=dict_row) as conn:
        return {'bytes': conn.execute('SELECT pg_database_size(current_database()) n').fetchone()['n'],
            'tables': conn.execute('''SELECT relname,n_live_tup,n_dead_tup,n_tup_ins,n_tup_upd,
                pg_total_relation_size(relid) bytes FROM pg_stat_user_tables
                WHERE relname LIKE 'game_%' OR relname='pvp_rate_limits' ORDER BY relname''').fetchall(),
            'stats': conn.execute('''SELECT xact_commit,xact_rollback,deadlocks,temp_bytes,
                blks_hit,blks_read FROM pg_stat_database WHERE datname=current_database()''').fetchone()}


async def run_stage(config, origin, proc, count, seconds, index, scenario):
    with psycopg.connect(**config, row_factory=dict_row) as conn:
        users = identities(conn, count, 'load' + str(index))
    for i, user in enumerate(users):
        user['difficulty'] = ['easy', 'medium', 'hard'][i % 3]
        user['headers'] = {'Cookie': user.pop('cookie'), 'Origin': origin,
                           'X-Forwarded-For': f'198.18.{index}.{i + 1}'}
    before = database_snapshot(config)
    metrics = Measurements()
    started = time.monotonic()
    until = started + seconds
    async with httpx.AsyncClient(base_url=origin, timeout=10, trust_env=False,
            limits=httpx.Limits(max_connections=count * 2 + 10, max_keepalive_connections=count * 2 + 10)) as client:
        if scenario == 'mixed':
            duel_count = (count // 5) // 2 * 2
            daily_count = max(1, count // 5)
        elif scenario == 'daily':
            duel_count, daily_count = 0, count
        else:
            duel_count, daily_count = 0, 0
        solo_count = count - daily_count - duel_count
        tasks = [solo_player(client, u, 'solo', until, metrics) for u in users[:solo_count]]
        tasks += [solo_player(client, u, 'daily', until, metrics) for u in users[solo_count:solo_count + daily_count]]
        for i in range(solo_count + daily_count, count, 2):
            tasks.append(friend_pair(client, users[i:i + 2], until, metrics))
        # One additional browsing client, not one expensive leaderboard per player.
        tasks.append(boards(client, users[0], until, metrics))
        resources = []

        async def monitor():
            async with await psycopg.AsyncConnection.connect(**config, autocommit=True) as conn:
                while time.monotonic() < until:
                    cursor = await conn.execute('''SELECT count(*),count(*) FILTER(WHERE state='active'),
                        count(*) FILTER(WHERE wait_event_type='Lock') FROM pg_stat_activity
                        WHERE datname=current_database() AND pid<>pg_backend_pid()''')
                    connections, active, locks = await cursor.fetchone()
                    ps = await asyncio.create_subprocess_exec('ps', '-p', str(proc.pid), '-o', '%cpu=,rss=',
                        stdout=asyncio.subprocess.PIPE)
                    data, _ = await ps.communicate()
                    cpu, rss = map(float, data.split())
                    resources.append({'connections': connections, 'active': active, 'locks': locks,
                                      'app_cpu_percent': cpu, 'app_rss_mb': round(rss / 1024, 1)})
                    await asyncio.sleep(1)
        await asyncio.gather(*tasks, monitor())
    elapsed = time.monotonic() - started
    after = database_snapshot(config)
    result = {'players': count, 'scenario': scenario,
              'mix': {'solo': solo_count, 'daily': daily_count, 'friend_players': duel_count, 'browsers': 1},
              **metrics.summary(elapsed), 'resource_samples': resources, 'db_before': before, 'db_after': after}
    print(json.dumps({k: result[k] for k in ('players', 'scenario', 'requests', 'rps', 'p95_ms',
        'p99_ms', 'errors', 'missed_one_second_ticks', 'completed_games')}), flush=True)
    return result


async def integrity_probe(config, origin):
    """Check real DB effects, including concurrent retry safety, after the load."""
    with psycopg.connect(**config, row_factory=dict_row) as conn:
        user = identities(conn, 1, 'integrity')[0]
    user['headers'] = {'Cookie': user['cookie'], 'Origin': origin, 'X-Forwarded-For': '198.19.0.1'}
    metrics = Measurements()

    def stored(run_id, table='game_solo_runs'):
        with psycopg.connect(**config, row_factory=dict_row) as conn:
            return conn.execute(sql.SQL('''SELECT xmin::text transaction,md5(state::text) digest,
                pg_column_size(state) stored_bytes,octet_length(state::text) json_bytes,state
                FROM {} WHERE run_id=%s''').format(sql.Identifier(table)), (run_id,)).fetchone()

    async with httpx.AsyncClient(base_url=origin, timeout=15, trust_env=False) as client:
        state = await metrics.request(client, user, 'POST', '/api/solo/runs', 'probe:start', 201,
                                      {'difficulty': 'easy', 'request_id': str(uuid4())})
        assert state, 'Could not start integrity probe'
        path = '/api/solo/runs/' + state['run_id']
        before = stored(state['run_id'])
        for _ in range(5):
            await metrics.request(client, user, 'GET', path, 'probe:idle-poll')
        after = stored(state['run_id'])
        result = {'unchanged_solo_state': before['digest'] == after['digest'],
                  'idle_solo_poll_rewrites_row': before['transaction'] != after['transaction'],
                  'solo_state_json_bytes': after['json_bytes'], 'solo_state_stored_bytes': after['stored_bytes']}
        for position in range(6):
            state = await metrics.request(client, user, 'POST', path + '/next', 'probe:next', body={'previous': position})
            assert state and state['phase'] == 'ANSWERING'
            answer = stored(state['run_id'])['state']['deck'][position]['correct']
            body = {'position': position + 1, 'option_id': answer, 'request_id': str(uuid4())}
            if position == 0:
                responses = await asyncio.gather(*(metrics.request(client, user, 'POST', path + '/answers',
                    'probe:retry', body=body) for _ in range(2)))
                assert all(response and response['correct'] == 1 for response in responses)
            else:
                state = await metrics.request(client, user, 'POST', path + '/answers', 'probe:answer', body=body)
        assert state['phase'] == 'FINISHED' and state['total_xp'] == 120
        with psycopg.connect(**config, row_factory=dict_row) as conn:
            rows = conn.execute('SELECT count(*) n FROM game_solo_answers WHERE run_id=%s', (state['run_id'],)).fetchone()['n']
            xp = conn.execute('SELECT sum(amount) n FROM game_xp_ledger WHERE run_id=%s', (state['run_id'],)).fetchone()['n']
        assert rows == 6 and xp == 120
        result.update(retried_answer_saved_once=True, completed_correct_answers=rows, awarded_xp=xp)
        daily = await metrics.request(client, user, 'POST', '/api/daily/runs', 'probe:daily', 201,
                                      {'request_id': str(uuid4())})
        assert daily
        daily_row = stored(daily['run_id'], 'game_mode_runs')
        result.update(daily_deck_questions=len(daily_row['state']['deck']),
                      daily_state_json_bytes=daily_row['json_bytes'], daily_state_stored_bytes=daily_row['stored_bytes'])
        # Explicitly exercise shared-network limits without disabling them.
        with psycopg.connect(**config, row_factory=dict_row) as conn:
            network = identities(conn, 25, 'sharedip')
        statuses = Counter()
        for actor in network:
            response = await client.post('/api/solo/runs', json={'request_id': str(uuid4())},
                headers={'Cookie': actor['cookie'], 'Origin': origin, 'X-Forwarded-For': '198.19.0.2'})
            statuses[str(response.status_code)] += 1
        result['shared_ip_25_starts_statuses'] = dict(statuses)
        assert not metrics.errors
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-env', type=Path, default=ROOT / '.env')
    parser.add_argument('--concurrency', default='10,25,50,100')
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--history-players', type=int, default=1000)
    parser.add_argument('--history-runs', type=int, default=10000)
    parser.add_argument('--scenario', choices=['mixed', 'solo', 'daily'], default='mixed')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    counts = [int(c) for c in args.concurrency.split(',')]
    if not counts or any(c < 2 or c > 200 for c in counts) or len(counts) > 10:
        parser.error('Use 1-10 stages of 2-200 simultaneous players')
    if not 10 <= args.seconds <= 300 or not 1 <= args.history_players <= 5000 or not 0 <= args.history_runs <= 20000:
        parser.error('Bounded test: 10-300 seconds/stage, 1-5000 historical players, 0-20000 matches')
    if args.output.exists():
        parser.error('Output already exists; choose a new report path')
    config = local_config(args.source_env)
    report = {'created_at': datetime.now(timezone.utc).isoformat(),
        'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'machine': {'os': platform.system(), 'arch': platform.machine(), 'logical_cpus': os.cpu_count()},
        'scope': 'LOCAL real HTTP + PostgreSQL; NOT Render capacity certification',
        'worker_count': 1, 'seconds_per_stage': args.seconds,
        'history_players': args.history_players, 'history_matches': args.history_runs, 'stages': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, indent=2, default=str) + '\n')

    with TemporaryDirectory(prefix='otd-stress-') as temp:
        directory = Path(temp)
        with isolated_database(config, directory) as target:
            with psycopg.connect(**target) as conn:
                report['postgres'] = dict(conn.execute("SELECT name,setting FROM pg_settings WHERE name IN ('server_version','max_connections','shared_buffers','work_mem')").fetchall())
                report['copied_question_rows'] = conn.execute('SELECT count(*) FROM penalty_bank_questions').fetchone()[0]
            seed_history(target, args.history_players, args.history_runs)
            report['baseline'] = database_snapshot(target)
            save()
            with server(target, directory) as (origin, proc):
                for index, count in enumerate(counts):
                    print(f'Starting {args.scenario}: {count} players for {args.seconds}s', flush=True)
                    stage = asyncio.run(run_stage(target, origin, proc, count, args.seconds, index, args.scenario))
                    report['stages'].append(stage)
                    save()
                    # Stop escalation on severe failure; never create an unbounded flood.
                    if stage['error_rate'] > .05:
                        report['stopped_early'] = 'More than 5% request failures'
                        break
                report['integrity_probe'] = asyncio.run(integrity_probe(target, origin))
                print('Integrity probe: ' + json.dumps(report['integrity_probe']), flush=True)
            log = (directory / 'server.log').read_text()
            report['server_errors'] = log.count('ERROR:')
            save()
    report['cleanup'] = 'test server stopped and disposable database dropped'
    save()
    print(f'Report: {args.output}', flush=True)


if __name__ == '__main__':
    main()
