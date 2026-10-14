"""Owner-only question drafts, private duels and explicit editorial approval."""
import os
import secrets
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field, field_validator
from psycopg.types.json import Jsonb

from api.bank_curation import text_key
from api.database import get_connection
from api.penalty_bank import option_key
from api.penalty_routes import rate_limit
from api.player_accounts import account
from api.question_publication import publish
from api.trivia_access import require_editor
from api.trivia_models import StrictModel
from api.trivia_quizzes import same_origin

router = APIRouter(tags=['community questions'])
TOPICS = ['Player milestones', 'Transfers and loans', 'Home grounds', 'Champions', 'Managers',
          'Kits and design', 'Match recognition', 'Cup history', 'Club identity']


class Content(StrictModel):
    question: str = Field(min_length=12, max_length=240)
    options: list[str] = Field(min_length=4, max_length=4)
    correct: int = Field(ge=0, le=3, strict=True)
    difficulty: Literal['easy', 'medium', 'hard'] = 'medium'
    topic: str = 'Player milestones'
    explanation: str = Field(default='', max_length=500)

    @field_validator('question', 'explanation', mode='before')
    @classmethod
    def trim(cls, value):
        return ' '.join(value.split()) if isinstance(value, str) else value

    @field_validator('options')
    @classmethod
    def choices(cls, values):
        values = [' '.join(v.split()) for v in values]
        if any(not v or len(v)>100 for v in values) or len({option_key(v) for v in values})!=4:
            raise ValueError('Use four distinct answers, each up to 100 characters.')
        return values

    @field_validator('topic')
    @classmethod
    def known_topic(cls, value):
        if value not in TOPICS: raise ValueError('Choose a topic.')
        return value


class Create(Content):
    request_id: UUID


class Edit(Content):
    revision: int = Field(ge=1)


class Revision(StrictModel):
    revision: int = Field(ge=1)


class Decision(Revision):
    decision: Literal['approved', 'rejected']
    note: str = Field(min_length=10, max_length=500)
    verified: bool = False

    @field_validator('note', mode='before')
    @classmethod
    def clean_note(cls, value):
        return ' '.join(value.split()) if isinstance(value, str) else value


def content(body):
    return body.model_dump(mode='json', exclude={'request_id', 'revision'})


def require_schema(conn):
    if not conn.execute("SELECT to_regclass('game_question_submissions') ready").fetchone()['ready']:
        raise HTTPException(503, 'Question editor is being prepared. Please try again later.')


def owned(conn, request, ident, revision=None):
    user = account(conn, request, lock=True)
    require_schema(conn)
    row = conn.execute('SELECT * FROM game_question_submissions WHERE submission_id=%s AND owner_id=%s FOR UPDATE',
                       (ident, user['account_id'])).fetchone()
    if not row: raise HTTPException(404, 'Question not found')
    if revision is not None and row['revision']!=revision: raise HTTPException(409, 'Question changed. Reload before saving.')
    return row


def shown(row):
    return {k: row[k] for k in ('submission_id', 'revision', 'content', 'status', 'created_at', 'review_note')}


@router.get('/api/players/questions')
def mine(request: Request):
    with get_connection() as conn:
        user = account(conn, request); require_schema(conn)
        rows = conn.execute('SELECT * FROM game_question_submissions WHERE owner_id=%s ORDER BY created_at DESC',
                            (user['account_id'],)).fetchall()
    return {'questions': [shown(r) for r in rows], 'topics': TOPICS}


@router.post('/api/players/questions', dependencies=[Depends(same_origin)], status_code=201)
def create(body: Create, request: Request):
    rate_limit(request, 'question-create', 20)
    with get_connection() as conn:
        user = account(conn, request, lock=True); require_schema(conn)
        old = conn.execute('SELECT * FROM game_question_submissions WHERE owner_id=%s AND request_id=%s',
                           (user['account_id'], body.request_id)).fetchone()
        if old:
            if old['content']!=content(body): raise HTTPException(409, 'Request ID already used')
            return shown(old)
        if conn.execute('SELECT count(*) n FROM game_question_submissions WHERE owner_id=%s', (user['account_id'],)).fetchone()['n']>=200:
            raise HTTPException(409, 'Your question library is full.')
        row = conn.execute('''INSERT INTO game_question_submissions(submission_id,owner_id,request_id,content)
            VALUES(%s,%s,%s,%s) RETURNING *''', (uuid4(), user['account_id'], body.request_id, Jsonb(content(body)))).fetchone()
        return shown(row)


@router.put('/api/players/questions/{ident}', dependencies=[Depends(same_origin)])
def edit(ident: UUID, body: Edit, request: Request):
    rate_limit(request, 'question-edit', 40)
    with get_connection() as conn:
        row = owned(conn, request, ident, body.revision)
        if row['status']=='approved': raise HTTPException(409, 'Approved questions are locked. Create a new question instead.')
        row = conn.execute('''UPDATE game_question_submissions SET content=%s,revision=revision+1,status='draft',
            updated_at=clock_timestamp(),submitted_at=NULL,reviewed_at=NULL,reviewed_by=NULL,review_note=''
            WHERE submission_id=%s RETURNING *''', (Jsonb(content(body)), ident)).fetchone()
        return shown(row)


@router.post('/api/players/questions/{ident}/submit', dependencies=[Depends(same_origin)])
def submit(ident: UUID, body: Revision, request: Request):
    rate_limit(request, 'question-submit', 10)
    with get_connection() as conn:
        row = owned(conn, request, ident, body.revision)
        if row['status'] in ('pending', 'approved'): return shown(row)
        if row['status']=='rejected': raise HTTPException(409, 'Edit and save the question before submitting it again.')
        row = conn.execute("UPDATE game_question_submissions SET status='pending',submitted_at=clock_timestamp() WHERE submission_id=%s RETURNING *", (ident,)).fetchone()
        return shown(row)


@router.get('/api/trivia/community-questions', dependencies=[Depends(require_editor)])
def queue(status: Literal['pending', 'approved', 'rejected', 'all']='pending', offset: int=Query(0, ge=0), limit: int=Query(25, ge=1, le=100)):
    with get_connection() as conn:
        require_schema(conn)
        where = "s.status<>'draft' AND (%s='all' OR s.status=%s)"
        total = conn.execute('SELECT count(*) n FROM game_question_submissions s WHERE '+where, (status, status)).fetchone()['n']
        rows = conn.execute('''SELECT s.*,a.username FROM game_question_submissions s JOIN game_accounts a ON a.account_id=s.owner_id
            WHERE '''+where+' ORDER BY s.submitted_at,s.submission_id LIMIT %s OFFSET %s', (status,status,limit,offset)).fetchall()
        return {'total': total, 'questions': [{**shown(r), 'username': r['username']} for r in rows]}


@router.post('/api/trivia/community-questions/{ident}/review', dependencies=[Depends(require_editor), Depends(same_origin)])
def review(ident: UUID, body: Decision):
    with get_connection() as conn:
        require_schema(conn)
        row = conn.execute('SELECT * FROM game_question_submissions WHERE submission_id=%s FOR UPDATE', (ident,)).fetchone()
        if not row: raise HTTPException(404, 'Question not found')
        if row['revision']!=body.revision or row['status']!='pending': raise HTTPException(409, 'This revision is no longer awaiting review.')
        actor = os.environ['TRIVIA_EDITOR_USERNAME']
        release = question = None
        if body.decision=='approved':
            if not body.verified: raise HTTPException(422, 'Confirm the fact, wording and all four answer choices.')
            owner = conn.execute('SELECT blocked_at,deleted_at FROM game_accounts WHERE account_id=%s', (row['owner_id'],)).fetchone()
            if owner['blocked_at'] or owner['deleted_at']: raise HTTPException(409, 'The author account is unavailable.')
            conn.execute('SELECT pg_advisory_xact_lock(84424329)')
            q = row['content']
            if any(text_key(r['text'])==text_key(q['question']) for r in conn.execute("SELECT content->>'question' text FROM trivia_bank_questions")):
                raise HTTPException(409, 'This question already exists in the bank.')
            dataset = conn.execute('SELECT dataset_id FROM trivia_datasets WHERE sealed_at IS NOT NULL ORDER BY created_at DESC LIMIT 1').fetchone()
            if not dataset: raise HTTPException(409, 'No sealed football dataset is available.')
            proof = {'status': 'unsupported', 'method': 'editor_reviewed', 'reason': body.note,
                     'reviewed_by': actor, 'submission_id': str(ident), 'revision': body.revision}
            item = {**q, 'id': f'COMMUNITY-{ident}-GEN-001', 'section': 'General',
                    'answer': q['options'][q['correct']], 'sources': [],
                    'check': body.note, 'evidence': proof}
            release, ids = publish(conn, [item], dataset['dataset_id'], f'community-{ident}-v{body.revision}', actor)
            question = ids[0]
        conn.execute('INSERT INTO game_question_reviews(review_id,submission_id,revision,decision,content,note,actor) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                     (uuid4(), ident, body.revision, body.decision, Jsonb(row['content']), body.note, actor))
        row = conn.execute('''UPDATE game_question_submissions SET status=%s,reviewed_at=clock_timestamp(),reviewed_by=%s,
            review_note=%s,release_id=%s,question_id=%s WHERE submission_id=%s RETURNING *''',
            (body.decision, actor, body.note, release, question, ident)).fetchone()
        return shown(row)


def private_deck(conn, owner, ids):
    """Freeze author-owned copies. These never become public bank candidates."""
    require_schema(conn)
    if len(ids)!=len(set(ids)): raise HTTPException(422, 'Select each question only once.')
    rows = conn.execute('SELECT * FROM game_question_submissions WHERE owner_id=%s AND submission_id=ANY(%s)', (owner, ids)).fetchall()
    if len(rows)!=len(ids): raise HTTPException(404, 'A selected question is unavailable.')
    deck = []
    for row in rows:
        q = row['content']; options = list(enumerate(q['options'])); secrets.SystemRandom().shuffle(options)
        deck.append({'question_id': str(row['submission_id']), 'revision': row['revision'], 'custom': True,
                     'key': f"custom:{row['submission_id']}:{row['revision']}", 'text': q['question'],
                     'options': [{'id': str(i), 'text': text} for i, (_, text) in enumerate(options)],
                     'correct': str(next(i for i, (original, _) in enumerate(options) if original==q['correct'])),
                     'explanation': q['options'][q['correct']], 'authority': 'author_supplied',
                     'validation_status': 'unreviewed', 'difficulty': q['difficulty']})
    secrets.SystemRandom().shuffle(deck)
    return deck
