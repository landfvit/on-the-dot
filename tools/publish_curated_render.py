"""Recheck the local bundle, back up Render, then append only its audited bank.

Never replace game tables or touch player accounts. Requires typed confirmation
and the external database URL via a hidden prompt. Run from the local checkout
because Render does not carry the full football source tables.
"""
import argparse
from collections import Counter
from datetime import datetime,timezone
import getpass
import json
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from api.database import get_connection
from api.question_publication import publish
from api.bank_lifecycle import retain_curated_bank
from src.check_curated_questions import Checker
from tools.render_game_database import render_config,run_pg


def main():
    parser=argparse.ArgumentParser();parser.add_argument('questions',type=Path)
    parser.add_argument('--replace-old',action='store_true',help='Retire previous banks without deleting game history')
    args=parser.parse_args()
    items=json.loads(args.questions.read_text())
    if Counter(q['difficulty'] for q in items)!=Counter(easy=1000,medium=1000,hard=1000):raise ValueError('Expected 1,000 questions per difficulty')
    if len({q['fact_key'] for q in items})!=3000 or len({q['question'] for q in items})!=3000:raise ValueError('Duplicate questions')
    with get_connection() as conn:
        if conn.info.host not in ('localhost','127.0.0.1','::1',''):raise ValueError('The audit must use the local source database')
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');checker=Checker(conn)
        if any(checker.check(q)['status']!='matched' for q in items):raise ValueError('Local audit failed. Nothing published.')
    dataset=items[0]['evidence']['dataset_id']
    if any(q['evidence']['dataset_id']!=dataset for q in items):raise ValueError('Mixed source snapshots')
    for q in items:q['evidence']['method']='independent_source_recalculation'
    config=render_config(getpass.getpass('Render External Database URL (hidden): ').strip())
    confirmation='REPLACE BANK' if args.replace_old else 'PUBLISH 3000'
    operation='replace the playable bank with 3,000 new questions' if args.replace_old else 'append 3,000 questions'
    if input(f'Type {confirmation} to back up Render and {operation}: ').strip()!=confirmation:
        print('Cancelled. Nothing changed.');return
    backup=Path(__file__).parents[1]/'backups'/('curated-bank-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    backup.mkdir(parents=True,mode=0o700)
    run_pg(['pg_dump','--format=custom','--no-owner','--no-privileges','--file='+str(backup/'before.dump')],config)
    with psycopg.connect(**config,row_factory=dict_row) as conn:
        conn.execute("SET LOCAL lock_timeout='10s'")
        if not conn.execute('SELECT 1 FROM trivia_datasets WHERE dataset_id=%s AND sealed_at IS NOT NULL',(dataset,)).fetchone():raise ValueError('The audited source snapshot is missing on Render. Nothing published.')
        release,_=publish(conn,items,dataset,'curated-pl-3000-v1','local-database-audit')
        if args.replace_old:retain_curated_bank(conn,release,'render-bank-replacement')
        conn.execute('SET CONSTRAINTS ALL IMMEDIATE')
    print(f'Published 3000 questions. Release {release}. Existing accounts and games were retained.')
    if args.replace_old:print('Previous question banks are no longer playable.')


if __name__=='__main__':
    try:main()
    except (psycopg.Error,ValueError,RuntimeError):
        raise SystemExit('Publication failed. No partial bank was committed. Credentials were not printed.') from None
