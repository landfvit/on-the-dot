"""Import, independently validate and train an offline authoring baseline."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from psycopg.types.json import Jsonb
from api.database import get_connection
from api.trivia_bank_engine import VERSION, load_evaluator, parse_bank
from src.trivia_bank_model import train
from api.bank_curation import exclusion,text_key


def import_and_validate(path, output, train_model=False):
    raw = Path(path).read_bytes()
    text = raw.decode('utf-8')
    items = parse_bank(text)
    digest = hashlib.sha256(raw).hexdigest()
    with get_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        conn.execute('SELECT pg_advisory_xact_lock(84424328)')
        data = conn.execute('SELECT * FROM trivia_datasets WHERE sealed_at IS NOT NULL ORDER BY created_at DESC LIMIT 1').fetchone()
        if not data: raise ValueError('Build a sealed football snapshot first')
        existing = conn.execute('SELECT batch_id FROM trivia_bank_batches WHERE source_sha256=%s', (digest,)).fetchone()
        batch_id = existing['batch_id'] if existing else uuid4()
        if not existing:
            conn.execute('''INSERT INTO trivia_bank_batches VALUES (%s,%s,%s,%s,'user_attested',%s,DEFAULT)''',
                         (batch_id, digest, Path(path).name, text, len(items)))
            with conn.cursor() as cur:
                cur.executemany('INSERT INTO trivia_bank_questions VALUES (%s,%s,%s,%s)',
                    [(uuid4(), batch_id, item['id'], Jsonb(item)) for item in items])
        evaluator, inputs = load_evaluator(conn, data['dataset_id'])
        checks = {item['id']: evaluator.check(item) for item in items}
        existing_texts={text_key(r['content']['question']) for r in conn.execute(
            'SELECT content FROM trivia_bank_questions WHERE batch_id<>%s',(batch_id,))}
        seen=set()
        for item in items:
            key=text_key(item['question'])
            reason=exclusion(item) or ('Duplicate question wording' if key in existing_texts or key in seen else None)
            if item['id'].startswith('EM-') and checks[item['id']]['status']=='ambiguous':
                reason=reason or 'Player identity needs review before publication'
            if reason:checks[item['id']]['publication_exclusion']=reason
            seen.add(key)
        summary = dict(Counter(check['status'] for check in checks.values()))
        run_id = uuid4()
        serial_inputs = json.loads(json.dumps(inputs, default=str))
        conn.execute('INSERT INTO trivia_bank_validation_runs VALUES (%s,%s,%s,%s,%s,%s,DEFAULT)',
            (run_id, batch_id, data['dataset_id'], VERSION, Jsonb(serial_inputs), Jsonb(summary)))
        qids = {r['external_id']: r['question_id'] for r in conn.execute(
            'SELECT question_id,external_id FROM trivia_bank_questions WHERE batch_id=%s', (batch_id,))}
        with conn.cursor() as cur:
            cur.executemany('INSERT INTO trivia_bank_checks VALUES (%s,%s,%s,%s)',
                [(run_id, qids[item['id']], checks[item['id']]['status'], Jsonb(checks[item['id']])) for item in items])
        result = {'batch_id': str(batch_id), 'validation_run_id': str(run_id), 'dataset_id': str(data['dataset_id']),
                  'source_sha256': digest, 'question_count': len(items), 'summary': summary, 'reused_import': bool(existing)}
    if train_model:
        with get_connection() as conn:
            previous=conn.execute('''SELECT DISTINCT ON(q.question_id) q.content,c.result FROM trivia_bank_questions q
                JOIN trivia_bank_checks c USING(question_id) JOIN trivia_bank_validation_runs r USING(run_id)
                WHERE q.batch_id<>%s ORDER BY q.question_id,r.created_at DESC,r.run_id DESC''',(batch_id,)).fetchall()
        training_items=[];training_checks={};seen=set()
        for item,check in [*((r['content'],r['result']) for r in previous),*((i,checks[i['id']]) for i in items)]:
            key=text_key(item['question'])
            from api.penalty_bank import eligible
            if exclusion(item) or not eligible(check) or key in seen:continue
            seen.add(key);training_items.append(item);training_checks[item['id']]=check
        corpus, report, artifact = train(training_items, training_checks)
        report['excluded_new_questions']=sum(bool(c.get('publication_exclusion')) for c in checks.values())
        report['training_sources']='Current and previous imported banks; trivial/duplicate wording excluded; answers never used as features or targets'
        model_id = uuid4()
        with get_connection() as conn:
            conn.execute('INSERT INTO trivia_bank_models VALUES (%s,%s,%s,%s,%s,%s,DEFAULT)',
                (model_id, batch_id, run_id, Jsonb(corpus), Jsonb(report), Jsonb(artifact)))
        result.update(model_id=str(model_id), training=report)
    output = Path(output) / str(run_id)
    output.mkdir(parents=True, exist_ok=True)
    rows = [{**item, 'validation': checks[item['id']]} for item in items]
    (output/'report.json').write_text(json.dumps({**result, 'questions': rows}, ensure_ascii=False, indent=2))
    with (output/'questions.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['id','section','topic','question','reference_answer','database_answer','status','reason'])
        for row in rows:
            v = row['validation']
            writer.writerow([row['id'],row['section'],row['topic'],row['question'],row['answer'],v['answer'],v['status'],v['reason']])
    lines = ['# Question Bank Audit', '', f'Questions: {len(items)}', f'Dataset: `{data["dataset_id"]}`',
             f'Run: `{run_id}`', '', 'Reference answers remain user-attested and unchanged.',
             'Matched means agreement with this database snapshot, not an independent audit of cited websites.', '',
             *[f'- {status}: {count}' for status, count in sorted(summary.items())],
             f'- Excluded from publication/training: {sum(bool(c.get("publication_exclusion")) for c in checks.values())}', '', '## Flagged Questions', '',
             '| ID | Status | Reference | Database | Reason |', '|---|---|---|---|---|']
    for row in rows:
        v = row['validation']
        if v['status'] != 'matched':
            values = [row['id'],v['status'],row['answer'],v['answer'] or '',v['reason']]
            lines.append('| ' + ' | '.join(str(value).replace('|', '\\|') for value in values) + ' |')
    (output/'report.md').write_text('\n'.join(lines) + '\n')
    result['report_directory'] = str(output)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    parser.add_argument('--output', default=str(ROOT/'reports'/'trivia-bank'))
    parser.add_argument('--train', action='store_true')
    args = parser.parse_args()
    result = import_and_validate(args.path, args.output, args.train)
    if 'training' in result:
        r = result['training']
        result['training'] = {k: r[k] for k in ('scope','counts','artifact_training_rows')}
        result['training'].update(validation_accuracy=r['validation']['accuracy'], test_accuracy=r['test']['accuracy'])
    print(json.dumps(result, indent=2))
