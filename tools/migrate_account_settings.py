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


def apply(conn):
    # SQL and the migration marker share a transaction: retries cannot repeat
    # half an upgrade. Existing application code tolerates the added columns.
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(84424323)')
        if conn.execute('SELECT 1 FROM trivia_schema_migrations WHERE name=%s',(NAME,)).fetchone():
            return False
        sql=(ROOT/'database'/f'{NAME}.sql').read_text().removeprefix('BEGIN;').removesuffix('COMMIT;\n')
        conn.execute(sql)
        conn.execute('INSERT INTO trivia_schema_migrations(name) VALUES(%s)',(NAME,))
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render',action='store_true')
    args=parser.parse_args();os.umask(0o077)
    config=render_config(getpass.getpass('Render External Database URL (hidden): ').strip()) if args.render else settings(ROOT/'.env')
    if args.render:
        print(f'Target: {config["host"]} / {config["dbname"]}')
        print('Back up the database, then add account settings and allow repeat guest games. No existing games are deleted.')
        if input('Type MIGRATE to continue: ').strip()!='MIGRATE':return
        directory=ROOT/'backups'/('before-settings-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
        directory.mkdir(parents=True,mode=0o700)
        archive=directory/'database.dump'
        run_pg(['pg_dump','--format=custom','--no-owner','--no-privileges','--file='+str(archive)],config)
        archive.chmod(0o600)
        print(f'Private backup: {archive}')
    with psycopg.connect(**config) as conn:
        changed=apply(conn)
    print('Applied 045_account_settings.' if changed else '045_account_settings already applied.')


if __name__=='__main__':
    try:main()
    except (psycopg.Error,RuntimeError,ValueError) as error:
        raise SystemExit(f'Migration failed ({type(error).__name__}); credentials were not printed. No partial schema change was committed.') from None
