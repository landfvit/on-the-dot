"""Editorial difficulty is versioned independently of answer verification."""
from typing import Literal
import os
from uuid import UUID

from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import Field

from api.database import get_connection
from api.solo_routes import active_releases
from api.trivia_access import require_editor
from api.trivia_models import StrictModel
from api.trivia_quizzes import same_origin

router=APIRouter(prefix='/api/solo/editor',dependencies=[Depends(require_editor)],tags=['difficulty review'])


class Assessment(StrictModel):
    release_id:UUID
    question_id:UUID
    difficulty:Literal['easy','medium','hard']
    approved:bool
    reason:str=Field(min_length=10,max_length=1000)


@router.get('/difficulty')
def list_difficulty(offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),pending:bool=True):
    with get_connection() as conn:
        rows=conn.execute('''SELECT p.release_id,p.question_id,p.section_name,p.question,d.revision_id,
            d.difficulty,d.approved,d.reason FROM penalty_bank_questions p
            LEFT JOIN game_current_difficulty d USING(release_id,question_id)
            WHERE p.release_id=ANY(%s) AND (NOT %s OR NOT COALESCE(d.approved,FALSE))
            ORDER BY p.question->'source'->>'external_id' LIMIT %s OFFSET %s''',
            (active_releases(conn),pending,limit,offset)).fetchall()
        return {'questions':rows,'offset':offset}


@router.post('/difficulty',dependencies=[Depends(same_origin)])
def assess(body:Assessment):
    with get_connection() as conn:
        if not conn.execute('SELECT 1 FROM penalty_bank_questions WHERE release_id=%s AND question_id=%s',
                            (body.release_id,body.question_id)).fetchone():raise HTTPException(404,'Question not found')
        row=conn.execute('''INSERT INTO game_question_difficulty(release_id,question_id,difficulty,approved,reason,reviewed_by)
            VALUES(%s,%s,%s,%s,%s,%s) RETURNING revision_id''',
            (body.release_id,body.question_id,body.difficulty,body.approved,body.reason.strip(),os.getenv('TRIVIA_EDITOR_USERNAME','editor'))).fetchone()
        return row
