"""Playable bank selection, separate from immutable historical question data."""
from collections import Counter
import hashlib


def active_releases(conn):
    rows=conn.execute('''SELECT DISTINCT ON(v.batch_id) r.release_id
        FROM penalty_bank_releases r JOIN trivia_bank_validation_runs v ON v.run_id=r.validation_run_id
        WHERE NOT EXISTS(SELECT 1 FROM game_retired_bank_batches x WHERE x.batch_id=v.batch_id)
        ORDER BY v.batch_id,r.created_at DESC,r.release_id DESC''').fetchall()
    return [r['release_id'] for r in rows]


def retired_releases(conn):
    return {str(r['release_id']) for r in conn.execute('''SELECT r.release_id
        FROM game_retired_bank_batches x JOIN trivia_bank_validation_runs v USING(batch_id)
        JOIN penalty_bank_releases r ON r.validation_run_id=v.run_id''')}


def retirement_key(retired):
    return hashlib.sha256('\n'.join(sorted(retired)).encode()).hexdigest()


def retain_curated_bank(conn, release_id, actor):
    """Explicit, transaction-owned replacement. Never delete accounts or games."""
    conn.execute('SELECT pg_advisory_xact_lock(84424329)')
    release=conn.execute('''SELECT v.batch_id,b.source_name FROM penalty_bank_releases r
        JOIN trivia_bank_validation_runs v ON v.run_id=r.validation_run_id
        JOIN trivia_bank_batches b USING(batch_id) WHERE r.release_id=%s''',(release_id,)).fetchone()
    if not release or release['source_name']!='curated-pl-3000-v1':
        raise ValueError('The replacement must be the audited 3,000-question bank.')
    if release_id not in active_releases(conn):raise ValueError('Replacement release is not active.')
    rows=conn.execute('''SELECT d.difficulty,p.question->>'validation_status' AS status
        FROM penalty_bank_questions p JOIN game_current_difficulty d USING(release_id,question_id)
        WHERE p.release_id=%s AND d.approved''',(release_id,)).fetchall()
    if Counter(r['difficulty'] for r in rows)!=Counter(easy=1000,medium=1000,hard=1000) or any(r['status']!='matched' for r in rows):
        raise ValueError('Replacement must contain 1,000 approved, matched questions per difficulty.')
    retired=conn.execute('''INSERT INTO game_retired_bank_batches(batch_id,actor,reason)
        SELECT batch_id,%s,'Replaced with the curated 3,000-question bank'
        FROM trivia_bank_batches WHERE batch_id<>%s ON CONFLICT DO NOTHING RETURNING batch_id''',
        (actor,release['batch_id'])).fetchall()
    return {'retained_release':str(release_id),'retired_batches':len(retired),'playable_questions':len(rows)}
