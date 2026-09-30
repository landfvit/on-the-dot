"""Export a game-only snapshot; restore only into an empty Render database.

Connection credentials are entered with getpass, never passed on the command
line or saved in the bundle. Existing databases are never cleaned or dropped.
"""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from tools.database_snapshot import settings

DATA_TABLES = frozenset({
    'trivia_datasets', 'trivia_bank_batches', 'trivia_bank_questions',
    'trivia_bank_validation_runs', 'trivia_bank_checks',
    'penalty_bank_releases', 'penalty_bank_questions',
    'game_question_difficulty', 'game_levels', 'game_clubs', 'game_kits',
    'trivia_schema_migrations',
})


def pg_environment(config):
    env = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
    for key, target in {'host': 'PGHOST', 'port': 'PGPORT', 'dbname': 'PGDATABASE',
                        'user': 'PGUSER', 'password': 'PGPASSWORD', 'sslmode': 'PGSSLMODE'}.items():
        if config.get(key):
            env[target] = str(config[key])
    env['PGCONNECT_TIMEOUT'] = '15'
    return env


def run_pg(command, config):
    result = subprocess.run(command, env=pg_environment(config), capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def table_counts(conn):
    tables = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
    return {name: conn.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(name))).fetchone()[0]
            for (name,) in tables}


def checksum(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def export_bundle(config, directory):
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    archive = directory / 'game.dump'
    with psycopg.connect(**config) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        tables = table_counts(conn)
        if not DATA_TABLES.issubset(tables):
            raise ValueError('Source schema is missing required game tables')
        dependencies = conn.execute("""SELECT child.relname,parent.relname
            FROM pg_constraint k JOIN pg_class child ON child.oid=k.conrelid
            JOIN pg_class parent ON parent.oid=k.confrelid
            WHERE k.contype='f' AND k.connamespace='public'::regnamespace""").fetchall()
        if any(child in DATA_TABLES and parent not in DATA_TABLES for child, parent in dependencies):
            raise ValueError('Game data has a new dependency; review the allowlist before exporting')
        snapshot = conn.execute('SELECT pg_export_snapshot()').fetchone()[0]
        relations = conn.execute("""SELECT relname FROM pg_class
            WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p','m','f')""").fetchall()
        # Full schema retains migrations, constraints, views and game triggers.
        # All row data is denied unless the table is explicitly listed above.
        command = ['pg_dump', '--format=custom', '--schema=public', '--no-owner', '--no-privileges',
                   '--snapshot=' + snapshot, '--file=' + str(archive)]
        for (name,) in relations:
            if name not in DATA_TABLES:
                command.append('--exclude-table-data=public.' + name)
        run_pg(command, config)
    archive.chmod(0o600)
    manifest = {'format': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                'sha256': checksum(archive), 'data_tables': sorted(DATA_TABLES),
                'counts': {name: count if name in DATA_TABLES else 0 for name, count in tables.items()}}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Exported {manifest["counts"]["penalty_bank_questions"]} published question rows; '
          f'{archive.stat().st_size:,} bytes; no accounts or gameplay history.')


def load_manifest(directory):
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('format') != 1 or set(manifest['data_tables']) != DATA_TABLES:
        raise ValueError('Unrecognized bundle format or data allowlist')
    if checksum(directory / 'game.dump') != manifest['sha256']:
        raise ValueError('Bundle checksum mismatch')
    if not DATA_TABLES.issubset(manifest['counts']) or any(
        not isinstance(n, int) or n < 0 or (name not in DATA_TABLES and n != 0)
        for name, n in manifest['counts'].items()
    ):
        raise ValueError('Bundle includes unexpected non-game data')
    return manifest


def assert_empty(conn):
    # Check objects, not just row counts: even an empty existing table is refused.
    objects = conn.execute("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'
        AND n.nspname NOT LIKE 'pg_temp_%'""").fetchone()[0]
    routines = conn.execute("""SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public'""").fetchone()[0]
    if objects or routines:
        raise ValueError('Target database is not empty. Nothing was changed.')


def restore_list(toc):
    # New PostgreSQL databases already contain public. Keep that schema and its
    # ownership; omit only its archive creation/comment entries, never tables.
    lines = []
    for line in toc.splitlines():
        tokens = line.split()
        if tokens[3:6] == ['SCHEMA', '-', 'public'] or tokens[3:7] == ['COMMENT', '-', 'SCHEMA', 'public']:
            continue
        lines.append(line)
    return '\n'.join(lines) + '\n'


def restore_bundle(config, directory):
    manifest = load_manifest(directory)
    with psycopg.connect(**config) as conn:
        assert_empty(conn)
        # Serializes this importer while it preflights and restores the schema.
        conn.execute('SELECT pg_advisory_lock(714039251)')
        conn.commit()
        assert_empty(conn)
        with TemporaryDirectory(prefix='otd-restore-') as temporary:
            selection = Path(temporary) / 'restore.list'
            toc = run_pg(['pg_restore', '--list', str(directory / 'game.dump')], config)
            selection.write_text(restore_list(toc))
            run_pg(['pg_restore', '--single-transaction', '--exit-on-error', '--no-owner', '--no-privileges',
                    '--use-list=' + str(selection), '--dbname=' + config['dbname'],
                    str(directory / 'game.dump')], config)
        conn.commit()
        restored = table_counts(conn)
        if restored != manifest['counts']:
            raise ValueError('Restored row counts differ. Stop and inspect; do not rerun or overwrite.')
        size = conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]
    print(f'Restored and verified {len(restored)} tables; database size {size:,} bytes. '
          'Accounts and gameplay history are empty.')
    return restored


def render_config(url):
    config = conninfo_to_dict(url)
    if not url.startswith(('postgresql://', 'postgres://')):
        raise ValueError('Use the External Database URL from Render')
    if not config.get('host', '').endswith('.render.com') or ',' in config['host']:
        raise ValueError('Expected a single external Render hostname')
    if not all(config.get(key) for key in ('dbname', 'user', 'password')):
        raise ValueError('Incomplete Render URL')
    allowed = {'host', 'port', 'dbname', 'user', 'password', 'sslmode', 'connect_timeout'}
    if set(config) - allowed:
        raise ValueError('Unexpected URL options')
    config.update(sslmode='require', connect_timeout='15')
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['export', 'restore'])
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--source-env', type=Path, default=Path('.env'))
    args = parser.parse_args()
    os.umask(0o077)
    if args.mode == 'export':
        export_bundle(settings(args.source_env), args.bundle.resolve())
        return
    load_manifest(args.bundle)
    config = render_config(getpass.getpass('Paste Render EXTERNAL Database URL (hidden): ').strip())
    print(f'Target: {config["host"]} / {config["dbname"]}')
    print('Imports game schema and questions only. Refuses any existing database objects.')
    if input('Type IMPORT to continue: ').strip() != 'IMPORT':
        print('Cancelled. Nothing was changed.')
        return
    restore_bundle(config, args.bundle.resolve())


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
    except psycopg.Error as error:
        raise SystemExit(f'Database operation failed ({type(error).__name__}). '
                         'Check the external URL and network access; no credentials were printed.') from None
