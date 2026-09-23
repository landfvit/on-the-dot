"""Restore and exercise a bundle in a NEW disposable local database only."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from fastapi.testclient import TestClient

from tools.database_snapshot import settings
from tools.render_game_database import restore_bundle
from trivia_app.main import app


def check(response, expected=200):
    if response.status_code != expected:
        raise AssertionError(f'{response.status_code}: {response.text}')
    return response.json()


def verify(source_env, bundle):
    source = settings(source_env)
    if source.get('host') not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Verification is restricted to a local PostgreSQL server')
    name = 'otd_bundle_test_' + uuid4().hex[:12]
    target = {**source, 'dbname': name}
    with psycopg.connect(**source, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            restore_bundle(target, bundle)
            # Repeat import must fail before changing any existing objects.
            try:
                restore_bundle(target, bundle)
            except ValueError as error:
                assert 'not empty' in str(error)
            else:
                raise AssertionError('Nonempty target was not refused')

            @contextmanager
            def connection():
                with psycopg.connect(**target, row_factory=dict_row) as conn:
                    yield conn

            from contextlib import ExitStack
            with ExitStack() as stack:
                for module in ('api.solo_routes', 'api.player_accounts', 'api.game_community', 'api.penalty_routes'):
                    stack.enter_context(patch(module + '.get_connection', connection))
                client = TestClient(app)
                catalog = check(client.get('/api/solo/catalog'))
                counts = catalog['categories'][0]['counts']
                assert all(counts[level] >= 10 for level in ('easy', 'medium', 'hard'))
                teams = check(client.get('/api/players/teams'))
                assert teams
                trial = check(client.post('/api/solo/runs', json={
                    'category': 'ALL', 'topic': 'ALL', 'difficulty': 'easy', 'request_id': str(uuid4())}), 201)
                assert trial['is_trial']
                check(client.post(f'/api/solo/runs/{trial["run_id"]}/leave'))
                check(client.post('/api/players/register', json={
                    'username': 'bundle_test', 'email': 'bundle@example.com', 'password': 'local-test-only-123'}), 201)
                run = check(client.post('/api/solo/runs', json={
                    'category': 'ALL', 'topic': 'ALL', 'difficulty': 'hard', 'request_id': str(uuid4())}), 201)
                ident = run['run_id']
                for index in range(6):
                    check(client.post(f'/api/solo/runs/{ident}/next', json={'previous': index}))
                    with connection() as conn:
                        state = conn.execute('SELECT state FROM game_solo_runs WHERE run_id=%s', (ident,)).fetchone()['state']
                    answer = state['deck'][index]['correct']
                    run = check(client.post(f'/api/solo/runs/{ident}/answers', json={
                        'position': index + 1, 'option_id': answer, 'request_id': str(uuid4())}))
                assert run['phase'] == 'FINISHED', run['phase']
                assert run['shootout']['winner'] == 'player'
                assert run['total_xp'] == 720, run['total_xp']
                profile = check(client.get('/api/players/me'))
                assert profile['total_xp'] == 720
                print(json.dumps({'catalog': counts, 'hard_win_xp': run['total_xp'],
                                  'trial': 'passed', 'account': 'passed', 'repeat_restore': 'refused'}))
        finally:
            # The name is generated here, never supplied by the caller.
            admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-env', type=Path, default=Path('.env'))
    parser.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args()
    verify(args.source_env, args.bundle.resolve())
