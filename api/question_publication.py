"""Publish a complete, immutable audit and release in the caller's transaction."""
from collections import Counter
import hashlib
import json
from uuid import uuid4

from psycopg.types.json import Jsonb


def publish(conn, items, dataset_id, source_name, actor):
    """Each item carries explicit choices and evidence, never inferred answers."""
    raw = json.dumps(items, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    conn.execute('SELECT pg_advisory_xact_lock(84424329)')
    existing = conn.execute('''SELECT r.release_id FROM penalty_bank_releases r
        JOIN trivia_bank_validation_runs v ON v.run_id=r.validation_run_id
        JOIN trivia_bank_batches b USING(batch_id) WHERE b.source_sha256=%s''', (digest,)).fetchone()
    if existing:
        return existing['release_id'], [r['question_id'] for r in conn.execute(
            'SELECT question_id FROM penalty_bank_questions WHERE release_id=%s ORDER BY question_id', (existing['release_id'],))]
    batch, audit, release = uuid4(), uuid4(), uuid4()
    ids = [uuid4() for _ in items]
    conn.execute('INSERT INTO trivia_bank_batches VALUES(%s,%s,%s,%s,\'user_attested\',%s,DEFAULT)',
                 (batch, digest, source_name, raw, len(items)))
    for ident, item in zip(ids, items):
        conn.execute('INSERT INTO trivia_bank_questions VALUES(%s,%s,%s,%s)',
                     (ident, batch, item['id'], Jsonb(item)))
    counts = dict(Counter(item['evidence']['status'] for item in items))
    conn.execute('INSERT INTO trivia_bank_validation_runs VALUES(%s,%s,%s,%s,%s,%s,DEFAULT)',
                 (audit, batch, dataset_id, 'curated-v1', Jsonb({'source': source_name}), Jsonb(counts)))
    for ident, item in zip(ids, items):
        proof = item['evidence']
        conn.execute('INSERT INTO trivia_bank_checks VALUES(%s,%s,%s,%s)', (audit, ident, proof['status'], Jsonb(proof)))
    conn.execute('INSERT INTO penalty_bank_releases VALUES(%s,%s,%s,%s,true,%s,DEFAULT)',
                 (release, audit, 'curated-choices-v1', actor, len(items)))
    for ident, item in zip(ids, items):
        status = item['evidence']['status']
        question = {'key': f'bank:{release}:{ident}', 'text': item['question'],
                    'options': [{'id': str(i), 'text': text} for i, text in enumerate(item['options'])],
                    'correct': str(item['correct']), 'explanation': item['answer'],
                    'topic': item['topic'], 'section': 'General', 'validation_status': status,
                    'authority': 'database_matched' if status == 'matched' else 'user_attested',
                    'source': {'question_id': str(ident), 'external_id': item['id'], 'references': item['sources'],
                               'verification_method': item['evidence']['method']}}
        conn.execute('INSERT INTO penalty_bank_questions VALUES(%s,%s,\'GEN\',\'General\',%s)',
                     (release, ident, Jsonb(question)))
        conn.execute('''INSERT INTO game_question_difficulty(release_id,question_id,difficulty,approved,reason,reviewed_by)
            VALUES(%s,%s,%s,true,%s,%s)''',
            (release, ident, item['difficulty'], item['check'], actor))
    return release, ids
