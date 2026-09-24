"""Apply only the reviewed account migration, locally or to Render.

Remote credentials are prompted privately and never saved or printed. The
existing database is backed up before any remote change, including player data.
"""
import argparse
from datetime import datetime, timezone
import getpass
import os
from pathlib import Path

import psycopg

from tools.database_snapshot import settings
from tools.render_game_database import render_config, run_pg

ROOT=Path(__file__).resolve().parents[1]
NAME='045_account_settings'
MIGRATIONS={NAME, '046_team_membership', '047_daily_friends'}


def apply(conn, name=NAME):
    # SQL and the migration marker share a transaction: retries cannot repeat
    # half an upgrade. Existing application code tolerates the added columns.
    if name not in MIGRATIONS:
        raise ValueError('Unknown reviewed migration')
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(84424323)')
        if conn.execute('SELECT 1 FROM trivia_schema_migrations WHERE name=%s',(name,)).fetchone():
            return False
        sql=(ROOT/'database'/f'{name}.sql').read_text().removeprefix('BEGIN;').removesuffix('COMMIT;\n')
        conn.execute(sql)
        conn.execute('INSERT INTO trivia_schema_migrations(name) VALUES(%s)',(name,))
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--migration',choices=sorted(MIGRATIONS),default=NAME)
    args=parser.parse_args();os.umask(0o077)
    config=render_config(getpass.getpass('Render External Database URL (hidden): ').strip()) if args.render else settings(ROOT/'.env')
    if args.render:
        print(f'Target: {config["host"]} / {config["dbname"]}')
        print(f'Back up the database, then apply {args.migration}. No existing games are deleted.')
        if input('Type MIGRATE to continue: ').strip()!='MIGRATE':return
        directory=ROOT/'backups'/('before-'+args.migration+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
        directory.mkdir(parents=True,mode=0o700)
        archive=directory/'database.dump'
        run_pg(['pg_dump','--format=custom','--no-owner','--no-privileges','--file='+str(archive)],config)
        archive.chmod(0o600)
        print(f'Private backup: {archive}')
    with psycopg.connect(**config) as conn:
        changed=apply(conn,args.migration)
    print(f'Applied {args.migration}.' if changed else f'{args.migration} already applied.')


if __name__=='__main__':
    try:main()
    except (psycopg.Error,RuntimeError,ValueError) as error:
        raise SystemExit(f'Migration failed ({type(error).__name__}); credentials were not printed. No partial schema change was committed.') from None
