"""Versioned quiz content and transactional, server-graded anonymous attempts."""
from datetime import datetime, timezone
import hashlib
import os
import secrets
from uuid import UUID, uuid4
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field, model_validator
from psycopg.types.json import Jsonb

from api.database import get_connection
from api.trivia import grade_answer
from api.trivia_access import require_editor
from api.trivia_models import GradeAnswer, StrictModel

router = APIRouter(prefix='/api/trivia', tags=['trivia quizzes'])


class QuizDefinition(StrictModel):
    quiz_id: UUID | None = None
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default='', max_length=1000)
    question_versions: list[UUID] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def valid(self):
        self.title = self.title.strip()
        if not self.title or len(set(self.question_versions)) != len(self.question_versions):
            raise ValueError('A title and distinct question versions are required')
        return self


def same_origin(request: Request):
    origin = request.headers.get('origin')
    if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and (
        urlsplit(origin).scheme != request.url.scheme or urlsplit(origin).netloc != request.url.netloc)):
        raise HTTPException(403, 'Cross-origin writes are not allowed')


@router.post('/quizzes', dependencies=[Depends(require_editor)], status_code=201)
def save_quiz(definition: QuizDefinition):
    with get_connection() as conn:
        questions = conn.execute('SELECT version_id,question_id,state,verified_at FROM trivia_question_versions WHERE version_id=ANY(%s) FOR SHARE',
                                 (definition.question_versions,)).fetchall()
        if len(questions) != len(definition.question_versions) or any(q['state'] != 'published' or not q['verified_at'] for q in questions):
            raise HTTPException(409, 'Choose verified, published questions')
        if len({q['question_id'] for q in questions}) != len(questions):
            raise HTTPException(422, 'A quiz cannot contain two revisions of the same question')
        quiz_id = definition.quiz_id or uuid4()
        if definition.quiz_id:
            if not conn.execute('SELECT 1 FROM trivia_quizzes WHERE quiz_id=%s FOR UPDATE', (quiz_id,)).fetchone():
                raise HTTPException(404, 'Quiz not found')
        else:
            conn.execute('INSERT INTO trivia_quizzes(quiz_id) VALUES (%s)', (quiz_id,))
        revision = conn.execute('SELECT COALESCE(MAX(revision),0)+1 n FROM trivia_quiz_versions WHERE quiz_id=%s', (quiz_id,)).fetchone()['n']
        version_id = uuid4()
        conn.execute('''INSERT INTO trivia_quiz_versions(version_id,quiz_id,revision,title,description,created_by)
            VALUES (%s,%s,%s,%s,%s,%s)''', (version_id, quiz_id, revision, definition.title, definition.description,
                                          os.getenv('TRIVIA_EDITOR_USERNAME') or 'local-service'))
        with conn.cursor() as cur:
            cur.executemany('INSERT INTO trivia_quiz_questions VALUES (%s,%s,%s)',
                            [(version_id, n, q) for n, q in enumerate(definition.question_versions, 1)])
    return {'quiz_id': quiz_id, 'version_id': version_id, 'revision': revision, 'state': 'draft'}


@router.post('/quizzes/{version_id}/publish', dependencies=[Depends(require_editor)])
def publish_quiz(version_id: UUID):
    with get_connection() as conn:
        quiz = conn.execute('SELECT * FROM trivia_quiz_versions WHERE version_id=%s FOR UPDATE', (version_id,)).fetchone()
        if not quiz:
            raise HTTPException(404, 'Quiz not found')
        if quiz['state'] == 'retired':
            raise HTTPException(409, 'Quiz retired')
        questions = conn.execute('''SELECT q.* FROM trivia_quiz_questions x JOIN trivia_question_versions q
            ON q.version_id=x.question_version_id WHERE x.quiz_version_id=%s FOR SHARE OF q''', (version_id,)).fetchall()
        if not questions or any(q['state'] != 'published' or not q['verified_at'] for q in questions):
            raise HTTPException(409, 'A quiz requires verified, published questions')
        conn.execute("UPDATE trivia_quiz_versions SET state='published',published_at=COALESCE(published_at,NOW()) WHERE version_id=%s", (version_id,))
    return {'version_id': version_id, 'state': 'published'}


def quiz_list(conn, public):
    where = "WHERE state='published'" if public else ''
    return conn.execute('''SELECT v.version_id,v.quiz_id,v.revision,v.title,v.description,v.state,v.created_at,
        (SELECT COUNT(*) FROM trivia_quiz_questions WHERE quiz_version_id=v.version_id) question_count
        FROM (SELECT DISTINCT ON(quiz_id) * FROM trivia_quiz_versions ''' + where + '''
        ORDER BY quiz_id,revision DESC) v ORDER BY v.created_at DESC LIMIT 100''').fetchall()


@router.get('/quizzes', dependencies=[Depends(require_editor)])
def quizzes():
    with get_connection() as conn:
        return {'quizzes': quiz_list(conn, False)}


@router.get('/play/quizzes')
def playable_quizzes():
    with get_connection() as conn:
        return {'quizzes': quiz_list(conn, True)}


@router.get('/quizzes/{version_id}', dependencies=[Depends(require_editor)])
def quiz_detail(version_id: UUID):
    with get_connection() as conn:
        row = conn.execute('SELECT * FROM trivia_quiz_versions WHERE version_id=%s', (version_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Quiz not found')
        row['questions'] = conn.execute('''SELECT q.version_id,q.question_text,q.state FROM trivia_quiz_questions x
            JOIN trivia_question_versions q ON q.version_id=x.question_version_id
            WHERE x.quiz_version_id=%s ORDER BY x.position''', (version_id,)).fetchall()
    return row


def cookie_name(attempt_id):
    return f'points_attempt_{attempt_id.hex}'


def load_attempt(conn, attempt_id, request, lock=False):
    row = conn.execute('SELECT * FROM trivia_quiz_attempts WHERE attempt_id=%s' + (' FOR UPDATE' if lock else ''), (attempt_id,)).fetchone()
    token = request.cookies.get(cookie_name(attempt_id), '')
    if not row or not secrets.compare_digest(row['token_hash'], hashlib.sha256(token.encode()).hexdigest()):
        raise HTTPException(404, 'Attempt not found in this browser')
    if row['expires_at'] <= datetime.now(timezone.utc):
        raise HTTPException(410, 'Attempt expired')
    return row


def attempt_view(conn, attempt):
    items = conn.execute('''SELECT x.position,q.version_id,q.question_text,q.answer->>'kind' answer_kind,
            a.response,a.correct,a.submitted_at
        FROM trivia_quiz_questions x JOIN trivia_question_versions q ON q.version_id=x.question_version_id
        LEFT JOIN trivia_attempt_answers a ON a.attempt_id=%s AND a.position=x.position
        WHERE x.quiz_version_id=%s ORDER BY x.position''', (attempt['attempt_id'], attempt['quiz_version_id'])).fetchall()
    answered = sum(q['submitted_at'] is not None for q in items)
    current = next(({'position': q['position'], 'question_text': q['question_text'], 'answer_kind': q['answer_kind']}
                    for q in items if q['submitted_at'] is None), None)
    result = {'attempt_id': attempt['attempt_id'], 'quiz_version_id': attempt['quiz_version_id'],
              'total': len(items), 'answered': answered, 'score': sum(q['correct'] is True for q in items),
              'finished': attempt['finished_at'] is not None, 'question': current}
    if result['finished']:
        result['review'] = conn.execute('''SELECT x.position,q.question_text,q.answer,a.response,a.correct
            FROM trivia_attempt_answers a JOIN trivia_quiz_questions x ON x.quiz_version_id=a.quiz_version_id AND x.position=a.position
            JOIN trivia_question_versions q ON q.version_id=x.question_version_id WHERE a.attempt_id=%s ORDER BY x.position''',
            (attempt['attempt_id'],)).fetchall()
    return result


@router.post('/play/quizzes/{version_id}/attempts', dependencies=[Depends(same_origin)], status_code=201)
def start_attempt(version_id: UUID, request: Request, response: Response):
    token, ident = secrets.token_urlsafe(32), uuid4()
    with get_connection() as conn:
        quiz = conn.execute("SELECT * FROM trivia_quiz_versions WHERE version_id=%s AND state='published' FOR SHARE", (version_id,)).fetchone()
        if not quiz:
            raise HTTPException(404, 'Published quiz not found')
        invalid = conn.execute('''SELECT 1 FROM trivia_quiz_questions x JOIN trivia_question_versions q ON q.version_id=x.question_version_id
            WHERE x.quiz_version_id=%s AND q.state<>'published' LIMIT 1''', (version_id,)).fetchone()
        if invalid:
            raise HTTPException(409, 'This quiz is awaiting question review')
        row = conn.execute('''INSERT INTO trivia_quiz_attempts(attempt_id,quiz_version_id,token_hash)
            VALUES (%s,%s,%s) RETURNING *''', (ident, version_id, hashlib.sha256(token.encode()).hexdigest())).fetchone()
        result = attempt_view(conn, row)
    response.set_cookie(cookie_name(ident), token, httponly=True, secure=request.url.scheme == 'https',
                        samesite='strict', max_age=14*86400, path=f'/api/trivia/attempts/{ident}')
    return result


@router.get('/attempts/{attempt_id}')
def get_attempt(attempt_id: UUID, request: Request):
    with get_connection() as conn:
        return attempt_view(conn, load_attempt(conn, attempt_id, request, lock=True))


@router.post('/attempts/{attempt_id}/answers/{position}', dependencies=[Depends(same_origin)])
def submit_answer(attempt_id: UUID, position: int, response: GradeAnswer, request: Request):
    with get_connection() as conn:
        attempt = load_attempt(conn, attempt_id, request, lock=True)
        existing = conn.execute('SELECT * FROM trivia_attempt_answers WHERE attempt_id=%s AND position=%s', (attempt_id, position)).fetchone()
        payload = response.model_dump(exclude_none=True)
        if existing:
            if existing['response'] != payload:
                raise HTTPException(409, 'This answer was already submitted and cannot be replaced')
            q = conn.execute('SELECT answer FROM trivia_question_versions WHERE version_id=%s', (existing['question_version_id'],)).fetchone()
            return {'correct': existing['correct'], 'answer': q['answer'], 'attempt': attempt_view(conn, attempt)}
        if attempt['finished_at']:
            raise HTTPException(409, 'Attempt is already finished')
        view = attempt_view(conn, attempt)
        if not view['question'] or position != view['question']['position']:
            raise HTTPException(409, 'Answer the current question first')
        q = conn.execute('''SELECT q.* FROM trivia_quiz_questions x JOIN trivia_question_versions q ON q.version_id=x.question_version_id
            WHERE x.quiz_version_id=%s AND x.position=%s''', (attempt['quiz_version_id'], position)).fetchone()
        grade = grade_answer(q['answer'], response)
        conn.execute('INSERT INTO trivia_attempt_answers(attempt_id,quiz_version_id,position,question_version_id,response,correct) VALUES (%s,%s,%s,%s,%s,%s)',
            (attempt_id, attempt['quiz_version_id'], position, q['version_id'], Jsonb(payload), grade['correct']))
        if position == view['total']:
            attempt = conn.execute('UPDATE trivia_quiz_attempts SET finished_at=NOW() WHERE attempt_id=%s RETURNING *', (attempt_id,)).fetchone()
        return {**grade, 'attempt': attempt_view(conn, attempt)}
