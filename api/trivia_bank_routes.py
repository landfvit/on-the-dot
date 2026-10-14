"""Private imported question library and database-backed authoring suggestions."""
from uuid import UUID, uuid4
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from api.database import get_connection
from api.trivia_access import require_editor
from api.trivia_bank_engine import CannotCheck, load_evaluator

router = APIRouter(prefix='/api/trivia/bank', dependencies=[Depends(require_editor)])


def latest(conn):
    run = conn.execute('''SELECT r.*,b.source_name,b.question_count,b.answer_authority FROM trivia_bank_validation_runs r
        JOIN trivia_bank_batches b USING(batch_id) WHERE b.source_name NOT LIKE 'community-%%'
        AND NOT EXISTS(SELECT 1 FROM game_retired_bank_batches x WHERE x.batch_id=b.batch_id)
        ORDER BY r.created_at DESC LIMIT 1''').fetchone()
    if not run: raise HTTPException(404, 'No imported question bank')
    return run


@router.get('/summary')
def summary():
    with get_connection() as conn:
        run = latest(conn)
        groups = conn.execute('''SELECT DISTINCT content->>'section' AS section, content->>'topic' AS topic
            FROM trivia_bank_questions WHERE batch_id=%s''', (run['batch_id'],)).fetchall()
        model = conn.execute('''SELECT model_id,report,created_at FROM trivia_bank_models
            WHERE validation_run_id=%s ORDER BY created_at DESC LIMIT 1''', (run['run_id'],)).fetchone()
    return {k: run[k] for k in ('run_id','batch_id','dataset_id','source_name','question_count','answer_authority','summary','created_at')} | {
        'sections': sorted({g['section'] for g in groups}), 'topics': sorted({g['topic'] for g in groups}),
        'model': None if not model else {'model_id': model['model_id'], 'created_at': model['created_at'],
            'scope': model['report']['scope'], 'training_rows': model['report']['artifact_training_rows'],
            'test_topic_accuracy': model['report']['test']['accuracy'], 'counts': model['report']['counts'],
            'unseen_training_topics': model['report']['test']['unseen_training_topics']}}


@router.get('/questions')
def questions(search: str = Query('', max_length=200), status: str = 'all', section: str = Query('', max_length=100),
              topic: str = Query('', max_length=100), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    if status not in ('all','flagged','matched','conflict','ambiguous','incomplete','unsupported'):
        raise HTTPException(422, 'Invalid validation status')
    with get_connection() as conn:
        run = latest(conn)
        where, params = ['c.run_id=%s'], [run['run_id']]
        if status == 'flagged': where.append("c.status<>'matched'")
        elif status != 'all': where.append('c.status=%s'); params.append(status)
        if section: where.append("q.content->>'section'=%s"); params.append(section)
        if topic: where.append("q.content->>'topic'=%s"); params.append(topic)
        if search:
            where.append("(q.content->>'question' ILIKE %s OR q.external_id ILIKE %s)")
            literal = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            params.extend([f'%{literal}%', f'%{literal}%'])
        clause = ' FROM trivia_bank_questions q JOIN trivia_bank_checks c USING(question_id) WHERE ' + ' AND '.join(where)
        count = conn.execute('SELECT count(*) AS n' + clause, params).fetchone()['n']
        rows = conn.execute("SELECT q.question_id,q.content,c.status,c.result-'evidence_fixture_ids' AS validation, jsonb_array_length(COALESCE(c.result->'evidence_fixture_ids','[]'::jsonb)) AS evidence_count" +
            clause + ' ORDER BY q.external_id LIMIT %s OFFSET %s', [*params, limit, offset]).fetchall()
    return {'run_id': run['run_id'], 'total': count, 'offset': offset, 'limit': limit, 'questions': rows}


@router.get('/questions/{question_id}/evidence')
def evidence(question_id: UUID):
    with get_connection() as conn:
        run = latest(conn)
        check = conn.execute('SELECT result FROM trivia_bank_checks WHERE run_id=%s AND question_id=%s', (run['run_id'], question_id)).fetchone()
        if not check: raise HTTPException(404, 'Question not in current audit')
    return {'run_id': run['run_id'], 'dataset_id': run['dataset_id'], **check['result']}


class AuthoringRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=10, max_length=1000)


def authoring(conn, question):
    from src.trivia_bank_model import suggest
    run = latest(conn)
    model = conn.execute('''SELECT * FROM trivia_bank_models WHERE validation_run_id=%s
        ORDER BY created_at DESC LIMIT 1''', (run['run_id'],)).fetchone()
    if not model:
        # A new audited bank is not a new language model. Keep the existing
        # intent classifier available; answers still use the current dataset.
        model = conn.execute('SELECT * FROM trivia_bank_models ORDER BY created_at DESC LIMIT 1').fetchone()
    if not model: raise HTTPException(409, 'Train an authoring model for the current validation run first')
    result = suggest(model['artifact'], model['corpus'], question)
    evaluator, inputs = load_evaluator(conn, run['dataset_id'])
    try:
        calculation = {'status': 'calculated', **evaluator.calculate(question)}
    except CannotCheck as exc:
        calculation = {'status': exc.status, 'reason': exc.reason, 'answer': None}
    return {**result, 'model_id': str(model['model_id']), 'dataset_id': str(run['dataset_id']), 'calculation': calculation}, inputs


@router.post('/authoring/check')
def check_authoring(body: AuthoringRequest):
    with get_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        result, _ = authoring(conn, body.question.strip())
    return result


@router.post('/authoring/drafts', status_code=201)
def save_draft(body: AuthoringRequest):
    with get_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        result, inputs = authoring(conn, body.question.strip())
        if result['calculation']['status'] != 'calculated':
            raise HTTPException(422, 'A complete, unambiguous database calculation is required to save a draft')
        draft_id = uuid4()
        conn.execute('''INSERT INTO trivia_bank_authored_drafts VALUES (%s,%s,%s,%s,%s,%s,%s,DEFAULT)''',
            (draft_id, result['model_id'], result['dataset_id'], body.question.strip(), result['topic'],
             Jsonb(result['calculation']), Jsonb(json.loads(json.dumps(inputs, default=str)))))
    return {'draft_id': draft_id, 'state': 'draft', **result}


@router.get('/authoring/drafts')
def drafts():
    with get_connection() as conn:
        rows = conn.execute('''SELECT draft_id,question_text,topic_suggestion,calculation-'evidence_fixture_ids' AS calculation,
            created_at FROM trivia_bank_authored_drafts ORDER BY created_at DESC LIMIT 50''').fetchall()
    return {'drafts': rows}
