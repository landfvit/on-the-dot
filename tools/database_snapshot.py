"""Local PostgreSQL backup/restore; never overwrite an existing database."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

from dotenv import dotenv_values, set_key
import psycopg
from psycopg import sql


def settings(path):
    values = dotenv_values(path)
    return {key: values.get('DB_' + name) for key, name in (
        ('host', 'HOST'), ('port', 'PORT'), ('dbname', 'NAME'),
        ('user', 'USER'), ('password', 'PASSWORD')) if values.get('DB_' + name)}


def pg_env(config):
    env = os.environ.copy()
    for key, name in (('host', 'PGHOST'), ('port', 'PGPORT'), ('dbname', 'PGDATABASE'),
                      ('user', 'PGUSER'), ('password', 'PGPASSWORD')):
        env.pop(name, None)
        if config.get(key):
            env[name] = str(config[key])
    return env


def counts(conn):
    tables = conn.execute("""SELECT schemaname, tablename FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY schemaname, tablename""").fetchall()
    return {schema + '.' + table: conn.execute(sql.SQL('SELECT count(*) FROM {}.{}')
            .format(sql.Identifier(schema), sql.Identifier(table))).fetchone()[0]
            for schema, table in tables}


def export(config, archive):
    if archive.exists() or archive.with_suffix('.json').exists():
        raise SystemExit('Backup already exists; choose a new filename.')
    archive.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.umask(0o077)
    with psycopg.connect(**config) as conn:
        # Counts and pg_dump share one snapshot even if the original app is active.
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        snapshot = conn.execute('SELECT pg_export_snapshot()').fetchone()[0]
        subprocess.run(['pg_dump', '--format=custom', '--no-owner', '--no-privileges',
                        '--snapshot=' + snapshot, '--file=' + str(archive)],
                       env=pg_env(config), check=True)
        report = {'created_at': datetime.now(timezone.utc).isoformat(),
                  'source_database': config['dbname'], 'tables': counts(conn)}
    archive.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Exported {len(report["tables"])} tables to {archive}')


def restore(config, archive, name, env_path):
    if name == config['dbname']:
        raise SystemExit('Refusing to overwrite the source database.')
    report = json.loads(archive.with_suffix('.json').read_text())
    with psycopg.connect(**config, autocommit=True) as conn:
        if conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', (name,)).fetchone():
            raise SystemExit('Target database already exists; nothing was overwritten.')
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    target = {**config, 'dbname': name}
    # A failed restore leaves the NEW database for inspection, never touches the source.
    subprocess.run(['pg_restore', '--exit-on-error', '--single-transaction',
                    '--no-owner', '--no-privileges', '--dbname=' + name, str(archive)],
                   env=pg_env(target), check=True)
    with psycopg.connect(**target) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        restored = counts(conn)
    if restored != report['tables']:
        raise SystemExit('Restored table counts differ; .env was NOT switched.')
    set_key(str(env_path), 'DB_NAME', name)
    env_path.chmod(0o600)
    print(f'Restored and verified {len(restored)} tables in {name}; .env updated.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['export', 'restore'])
    parser.add_argument('--env', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--name', help='New database name, required for restore')
    args = parser.parse_args()
    if args.mode == 'export':
        export(settings(args.env), args.archive.resolve())
    elif args.name:
        restore(settings(args.env), args.archive.resolve(), args.name, args.env.resolve())
    else:
        parser.error('--name is required for restore')
