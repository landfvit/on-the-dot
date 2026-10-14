"""Audit an exact generated bundle again before a deliberate local publication."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from api.database import get_connection
from api.question_publication import publish
from src.check_curated_questions import Checker


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('questions',type=Path)
    parser.add_argument('--publish-local',action='store_true')
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();items=json.loads(args.questions.read_text())
    if Counter(q['difficulty'] for q in items)!=Counter(easy=1000,medium=1000,hard=1000):
        raise SystemExit('Expected exactly 1,000 questions at each difficulty. Nothing published.')
    if len({q['fact_key'] for q in items})!=len(items) or len({q['question'] for q in items})!=len(items):
        raise SystemExit('Duplicate question or fact key. Nothing published.')
    with get_connection() as conn:
        if args.publish_local and conn.info.host not in ('localhost','127.0.0.1','::1',''):
            raise SystemExit('This command only publishes to the local database.')
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        checker=Checker(conn);checks=[checker.check(q) for q in items]
        conflicts=[c for c in checks if c['status']!='matched']
        report={'counts':dict(Counter(c['status'] for c in checks)),'external_fact_check':False,'conflicts':conflicts,'published':False}
        if not conflicts and args.publish_local:
            for q in items:q['evidence']['method']='independent_source_recalculation'
            dataset=items[0]['evidence']['dataset_id']
            if any(q['evidence']['dataset_id']!=dataset for q in items):raise SystemExit('Mixed snapshots. Nothing published.')
            release,_=publish(conn,items,dataset,'curated-pl-3000-v1','local-database-audit')
            conn.execute('SET CONSTRAINTS ALL IMMEDIATE')
            report.update(published=True,release_id=str(release))
    args.report.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    with args.questions.with_suffix('.csv').open('w',newline='') as file:
        writer=csv.writer(file);writer.writerow(['ID','Difficulty','Family','Question','A','B','C','D','Answer','Evidence'])
        for q in items:writer.writerow([q['id'],q['difficulty'],q['family'],q['question'],*q['options'],q['answer'],json.dumps(q['evidence'],ensure_ascii=False)])
    if conflicts:raise SystemExit('Conflicting questions must be corrected before publication.')


if __name__=='__main__':main()
