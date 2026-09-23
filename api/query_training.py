"""Private human annotation of metric phrases. Never an executable query parser."""
import os
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, model_validator

from api.database import get_connection
from api.sports_query import DEFINITIONS, Metric, normalize
from api.trivia_access import require_editor
from api.trivia_models import StrictModel

router = APIRouter(prefix='/api/query/training', dependencies=[Depends(require_editor)])
CONTEXT_LABELS = {'kit_colour':'Historical kit shirt colour', 'historical_weather':'Historical match weather (not a forecast)'}
Label = Metric | Literal['unsupported','ambiguous','kit_colour','historical_weather']


class Annotation(StrictModel):
    example_id: UUID | None = None
    base_revision: int = Field(default=0, ge=0)
    query_text: str = Field(min_length=1, max_length=1000)
    phrase: str = Field(min_length=1, max_length=300)
    label: Label
    family_key: str = Field(pattern=r'^[a-z0-9][a-z0-9_-]{0,79}$')
    split: Literal['train','validation','test']
    note: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def validate_phrase(self):
        self.query_text = self.query_text.strip()
        self.phrase = self.phrase.strip()
        if not normalize(self.query_text) or not self.phrase or self.query_text.count(self.phrase) != 1:
            raise ValueError('Metric phrase must occur exactly once in the query, with matching spelling')
        if self.label in ('unsupported','ambiguous') and not self.note.strip():
            raise ValueError('Explain why the phrase is unsupported or ambiguous')
        return self


class Verify(StrictModel):
    confirmed: Literal[True]


class ModelProbe(StrictModel):
    phrase: str = Field(min_length=1,max_length=300)


def save_annotation(conn, body, author):
    # Serialize annotation changes, including duplicate detection and family assignment.
    conn.execute('SELECT pg_advisory_xact_lock(84424325)')
    normalized = normalize(body.query_text)
    existing = conn.execute('SELECT * FROM trivia_query_examples WHERE example_id=%s' if body.example_id else
        'SELECT * FROM trivia_query_examples WHERE normalized_text=%s', (body.example_id or normalized,)).fetchone()
    if body.example_id and not existing:
        raise HTTPException(404, 'Example not found')
    if existing and not body.example_id:
        raise HTTPException(409, 'This query already exists; open it to create a revision')
    if existing and existing['query_text'] != body.query_text:
        raise HTTPException(422, 'Existing query text is immutable; create a separate example')
    example_id = body.example_id or uuid4()
    revision = conn.execute('SELECT COALESCE(MAX(revision),0) n FROM trivia_query_annotations WHERE example_id=%s',
                            (example_id,)).fetchone()['n']
    if revision != body.base_revision:
        raise HTTPException(409, 'A newer revision exists; reload before editing')
    family = conn.execute('SELECT split FROM trivia_query_families WHERE family_key=%s', (body.family_key,)).fetchone()
    if family and family['split'] != body.split:
        raise HTTPException(409, 'This paraphrase family already belongs to another split')
    conn.execute('INSERT INTO trivia_query_families VALUES (%s,%s) ON CONFLICT DO NOTHING', (body.family_key, body.split))
    if not existing:
        conn.execute('INSERT INTO trivia_query_examples(example_id,query_text,normalized_text) VALUES (%s,%s,%s)',
                     (example_id, body.query_text, normalized))
    annotation_id = uuid4()
    conn.execute('''INSERT INTO trivia_query_annotations
        (annotation_id,example_id,revision,family_key,phrase,label,note,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
        (annotation_id,example_id,revision+1,body.family_key,body.phrase,body.label,body.note,author))
    return {'annotation_id': annotation_id, 'example_id': example_id, 'revision': revision+1}


@router.get('/examples')
def examples(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    with get_connection() as conn:
        rows = conn.execute('''SELECT e.query_text,a.*,f.split FROM trivia_query_examples e
            JOIN LATERAL (SELECT * FROM trivia_query_annotations WHERE example_id=e.example_id ORDER BY revision DESC LIMIT 1) a ON TRUE
            JOIN trivia_query_families f USING(family_key)
            ORDER BY e.created_at DESC,e.example_id LIMIT %s OFFSET %s''', (limit+1,offset)).fetchall()
        counts = conn.execute('''SELECT f.split,COUNT(*) total,COUNT(*) FILTER(WHERE a.reviewed_at IS NOT NULL) verified
            FROM (SELECT DISTINCT ON(example_id) * FROM trivia_query_annotations ORDER BY example_id,revision DESC) a
            JOIN trivia_query_families f USING(family_key) GROUP BY f.split ORDER BY f.split''').fetchall()
    return {'examples': rows[:limit], 'next_offset': offset+limit if len(rows)>limit else None,
            'counts': counts, 'labels': {**DEFINITIONS, **CONTEXT_LABELS, 'unsupported':'Outside supported metrics', 'ambiguous':'Requires clarification'}}


@router.post('/examples', status_code=201)
def save(body: Annotation):
    with get_connection() as conn:
        return save_annotation(conn, body, os.environ['TRIVIA_EDITOR_USERNAME'])


@router.post('/examples/{annotation_id}/verify')
def verify(annotation_id: UUID, body: Verify):
    with get_connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(84424325)')
        row = conn.execute('SELECT * FROM trivia_query_annotations WHERE annotation_id=%s FOR UPDATE', (annotation_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Annotation not found')
        latest = conn.execute('SELECT MAX(revision) n FROM trivia_query_annotations WHERE example_id=%s', (row['example_id'],)).fetchone()['n']
        if row['revision'] != latest:
            raise HTTPException(409, 'Only the latest revision can be verified')
        if not row['reviewed_at']:
            conn.execute('UPDATE trivia_query_annotations SET reviewed_by=%s,reviewed_at=NOW() WHERE annotation_id=%s',
                         (os.environ['TRIVIA_EDITOR_USERNAME'],annotation_id))
    return {'annotation_id': annotation_id, 'state':'human_verified', 'scope':'metric_phrase_only'}


@router.get('/inbox')
def inbox(offset: int = Query(0, ge=0)):
    with get_connection() as conn:
        rows = conn.execute('''SELECT query_id,query_text,issues,created_at FROM trivia_unrecognized_queries
            ORDER BY created_at DESC,query_id DESC LIMIT 26 OFFSET %s''', (offset,)).fetchall()
    return {'queries':rows[:25], 'next_offset':offset+25 if len(rows)>25 else None}


@router.get('/models')
def models():
    with get_connection() as conn:
        rows = conn.execute('''SELECT model_id,created_at,dataset_hash,manifest,report,corpus
            FROM trivia_query_model_runs ORDER BY created_at DESC LIMIT 20''').fetchall()
    for row in rows:
        frozen = {str(r['annotation_id']):r for r in row.pop('corpus')}
        row['evaluation_examples'] = {split:[{**prediction,
            'phrase':frozen.get(str(prediction['annotation_id']),{}).get('phrase'),
            'family_key':frozen.get(str(prediction['annotation_id']),{}).get('family_key')}
            for prediction in row['report'][split]['predictions']] for split in ('validation','test')}
    return {'models':rows, 'mode':'offline_experiment_not_deployed'}


@router.post('/models/{model_id}/probe')
def probe(model_id: UUID, body: ModelProbe):
    from src.query_model import diagnose
    with get_connection() as conn:
        row = conn.execute('SELECT artifact,corpus FROM trivia_query_model_runs WHERE model_id=%s',(model_id,)).fetchone()
    if not row:
        raise HTTPException(404,'Model not found')
    return diagnose(row['artifact'],body.phrase,row['corpus'])
