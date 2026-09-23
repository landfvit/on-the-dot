from datetime import date, datetime, time, timedelta, timezone
import json
import os
import re
from itertools import permutations
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg.types.json import Jsonb

from api.database import get_connection
from api.trivia_engine import aggregate
from api.trivia_events import EVENT_TEMPLATES, evaluate_events, normalized_name
from api.trivia_models import EvaluationRequest, GradeAnswer, SaveQuestion
from api.trivia_access import require_editor
from api.trivia_audit import POLICY_VERSION, audit_dataset, enrich_result, evidence_hash
from api.trivia_context import kit_result, snapshot as context_snapshot, filter_weather, weather_description, provenance

router = APIRouter(prefix='/api/trivia', tags=['trivia'])


def dataset(conn, ident=None):
    row = conn.execute('SELECT * FROM trivia_datasets WHERE dataset_id=%s' if ident else
                       'SELECT * FROM trivia_datasets ORDER BY created_at DESC LIMIT 1', (ident,) if ident else ()).fetchone()
    if not row:
        raise HTTPException(404 if ident else 503, 'Trivia dataset unavailable; run src/trivia_build.py')
    return row


@router.get('/metadata', dependencies=[Depends(require_editor)])
def metadata(dataset_id: UUID | None = None):
    with get_connection() as conn:
        data = dataset(conn, dataset_id)
        teams = conn.execute('''SELECT DISTINCT f.league_id, f.team_id, f.team_name, t.logo_url
            FROM trivia_match_team_facts f LEFT JOIN teams t USING(team_id)
            WHERE dataset_id=%s ORDER BY f.team_name''', (data['dataset_id'],)).fetchall()
        templates = conn.execute('SELECT * FROM trivia_templates WHERE version=1 ORDER BY template_key').fetchall()
        templates = [t for t in templates if t['template_key'] not in EVENT_TEMPLATES
                     or t['template_key'] in data['summary'].get('capabilities', [])]
        players = []
        groups = conn.execute('SELECT * FROM trivia_opponent_groups ORDER BY group_key,version').fetchall()
        context = conn.execute('''SELECT context_id,created_at,summary FROM trivia_context_snapshots
            WHERE dataset_id=%s ORDER BY created_at DESC LIMIT 1''',(data['dataset_id'],)).fetchone()
        if data['summary'].get('player_facts'):
            players = conn.execute('''SELECT DISTINCT f.league_id,p.player_id,p.player_name
                FROM trivia_match_player_facts p JOIN trivia_match_team_facts f USING(dataset_id,fixture_id,team_id)
                WHERE p.dataset_id=%s ORDER BY p.player_name,p.player_id''', (data['dataset_id'],)).fetchall()
    return {'dataset': data, 'teams': teams, 'templates': templates, 'players': players, 'opponent_groups': groups, 'context':context}


def evaluate_raw(conn, request):
    data = dataset(conn, request.dataset_id)
    spec = request.specification
    league = data['summary']['leagues'].get(str(spec.league_id))
    if not league:
        raise HTTPException(422, 'Competition is not present in this dataset')
    available = league['seasons']
    period = spec.period
    seasons = (period.seasons if period.mode == 'seasons' else list(range(period.start, period.end + 1))
               if period.mode == 'season_range' else available)
    if set(seasons) - set(available):
        raise HTTPException(422, 'Requested seasons are missing from this dataset; the range has not been reduced')
    if spec.template == 'kit_colour':
        return kit_result(conn,spec,data,league)
    if spec.template in EVENT_TEMPLATES:
        return evaluate_events(conn, spec, data, seasons, league)
    team = conn.execute('''SELECT team_name FROM trivia_match_team_facts
        WHERE dataset_id=%s AND league_id=%s AND team_id=%s LIMIT 1''',
        (data['dataset_id'], spec.league_id, spec.team_id)).fetchone()
    if not team:
        raise HTTPException(422, 'Team is not present in this competition')
    point = spec.condition.minute * 1000 + spec.condition.extra if spec.condition else None
    params = [point, point, data['dataset_id'], spec.league_id, spec.team_id]
    conditions = ['f.dataset_id=%s', 'f.league_id=%s', 'f.team_id=%s']
    if period.mode == 'dates':
        conditions.extend(['f.match_date >= %s', 'f.match_date < %s'])
        params.extend([datetime.combine(period.start, time.min, timezone.utc),
                       datetime.combine(period.end + timedelta(days=1), time.min, timezone.utc)])
        period_label = f'{period.start} to {period.end} (UTC)'
    else:
        conditions.append('f.season = ANY(%s)')
        params.append(seasons)
        labels = [f'{s}/{str(s+1)[-2:]}' for s in sorted(seasons)]
        period_label = ', '.join(labels)
    if spec.venue != 'all':
        conditions.append('f.is_home=%s')
        params.append(spec.venue == 'home')
    opponent_label = None
    if spec.opponents:
        selected = spec.opponents
        opponents = conn.execute('''SELECT DISTINCT team_id,team_name FROM trivia_match_team_facts
            WHERE dataset_id=%s AND league_id=%s AND team_id=ANY(%s) ORDER BY team_name''',
            (data['dataset_id'], spec.league_id, selected.team_ids)).fetchall()
        if {r['team_id'] for r in opponents} != set(selected.team_ids):
            raise HTTPException(422, 'An opponent is missing from this competition snapshot')
        opponent_label = ', '.join(r['team_name'] for r in opponents)
        if selected.group_key:
            group = conn.execute('SELECT * FROM trivia_opponent_groups WHERE group_key=%s AND version=%s',
                                 (selected.group_key, selected.group_version)).fetchone()
            if not group or group['league_id'] != spec.league_id or set(group['team_ids']) - {spec.team_id} != set(selected.team_ids):
                raise HTTPException(422, 'Opponent IDs do not match the versioned group definition')
            opponent_label = f"{group['label']} v{group['version']} ({opponent_label})"
        conditions.append('f.opponent_id=ANY(%s)')
        params.append(selected.team_ids)
    rows = conn.execute('''
        SELECT f.fixture_id, f.season, f.match_date, f.team_name, f.opponent_id, f.opponent_name,
               f.is_home, f.goals_for, f.goals_against, f.result, f.status,
               q.result_valid, q.timeline_valid, q.reasons,
               CASE WHEN f.is_home THEN i.home_goals ELSE i.away_goals END AS checkpoint_for,
               CASE WHEN f.is_home THEN i.away_goals ELSE i.home_goals END AS checkpoint_against
        FROM trivia_match_team_facts f JOIN trivia_match_data_quality q USING(dataset_id,fixture_id)
        LEFT JOIN trivia_match_state_intervals i ON i.dataset_id=f.dataset_id AND i.fixture_id=f.fixture_id
          AND i.start_key <= %s AND i.end_key > %s
        WHERE ''' + ' AND '.join(conditions) + ' ORDER BY f.match_date, f.fixture_id', params).fetchall()
    context = context_snapshot(conn,spec,data) if spec.weather else None
    if context:
        filter_weather(rows,context,spec.weather)
    result = aggregate(spec, rows)
    if context:
        result['context_source'] = provenance(context)
    name = team['team_name']
    context = f"{league['name']}, {period_label}"
    if spec.venue != 'all':
        context += f', {spec.venue} matches'
    if opponent_label:
        context += f', against {opponent_label}'
    if spec.weather:
        context += ', ' + weather_description(spec.weather)
    if spec.condition:
        c = spec.condition
        comparison = {'eq': 'equal to', 'lte': 'at most', 'gte': 'at least'}[c.operator]
        clock = f'{c.minute}+{c.extra}' if c.extra else str(c.minute)
        question = (f"What percentage of matches did {name} win when their goal difference was {comparison} "
                    f"{c.goal_difference:+d} after recorded minute {clock}? ({context})")
    elif spec.template == 'win_rate':
        question = f'What percentage of matches did {name} win? ({context})'
    elif spec.template == 'total_wins':
        question = f'How many matches did {name} win? ({context})'
    elif spec.template in ('loss_rate', 'draw_rate'):
        verb = 'lose' if spec.template == 'loss_rate' else 'draw'
        question = f'What percentage of matches did {name} {verb}? ({context})'
    elif spec.template == 'goals_per_game':
        question = f'How many goals per match did {name} score on average? ({context})'
    elif spec.template == 'points_per_game':
        question = f'How many points per match did {name} earn on average, using 3 per win and 1 per draw, before deductions? ({context})'
    elif spec.template == 'goals_conceded':
        question = f'How many goals did {name} concede? ({context})'
    elif spec.template == 'clean_sheets':
        question = f'How many clean sheets did {name} keep? ({context})'
    else:
        question = f'How many goals did {name} score? ({context})'
    if result['answer']['kind'] == 'percentage':
        question += ' Round to one decimal place.'
    elif result['answer']['kind'] == 'decimal':
        question += ' Round to two decimal places.'
    return {**result, 'dataset_id': data['dataset_id'], 'dataset_created_at': data['created_at'],
            'engine_version': data['engine_version'], 'question_text': question,
            'resolved_seasons': sorted({r['season'] for r in rows}),
            'specification': spec.model_dump(mode='json')}


def evaluate(conn, request):
    result = evaluate_raw(conn, request)
    return enrich_result(conn, dataset(conn, result['dataset_id']), request.specification, result)


@router.get('/audit', dependencies=[Depends(require_editor)])
def audit(league_id: int = Query(39, gt=0), dataset_id: UUID | None = None):
    with get_connection() as conn:
        data = dataset(conn, dataset_id)
        return {'dataset_id': data['dataset_id'], 'policy_version': POLICY_VERSION,
                'seasons': audit_dataset(conn, data, league_id)}


@router.post('/evaluate', dependencies=[Depends(require_editor)])
def preview(request: EvaluationRequest):
    with get_connection() as conn:
        return evaluate(conn, request)


@router.post('/questions', status_code=201, dependencies=[Depends(require_editor)])
def save(request: SaveQuestion):
    with get_connection() as conn:
        result = evaluate(conn, request)
        question_id = request.question_id or uuid4()
        if request.question_id:
            existing = conn.execute('SELECT question_id FROM trivia_questions WHERE question_id=%s FOR UPDATE',
                                    (question_id,)).fetchone()
            if not existing:
                raise HTTPException(404, 'Question not found')
        else:
            conn.execute('INSERT INTO trivia_questions(question_id) VALUES (%s)', (question_id,))
        revision = conn.execute('SELECT COALESCE(MAX(revision),0)+1 AS value FROM trivia_question_versions WHERE question_id=%s',
                                (question_id,)).fetchone()['value']
        version_id = uuid4()
        conn.execute('''INSERT INTO trivia_question_versions
            (version_id,question_id,revision,template_key,dataset_id,specification,question_text,answer,coverage,analysis,created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (version_id, question_id, revision, request.specification.template, result['dataset_id'],
             Jsonb(result['specification']), result['question_text'], Jsonb(result['answer']), Jsonb(result['coverage']),
             Jsonb(result['analysis']), os.getenv('TRIVIA_EDITOR_USERNAME') or 'local-service'))
        with conn.cursor() as cursor:
            cursor.executemany('INSERT INTO trivia_evidence VALUES (%s,%s,%s,%s)',
                [(version_id, row['fixture_id'], row['disposition'], Jsonb(row, dumps=lambda v: json.dumps(v,
                    default=lambda value: value.isoformat() if isinstance(value, (date, datetime)) else str(value))))
                 for row in result['evidence']])
    return {'question_id': question_id, 'version_id': version_id, 'revision': revision, 'state': 'draft'}


@router.get('/questions', dependencies=[Depends(require_editor)])
def questions(published_only: bool = False):
    with get_connection() as conn:
        rows = conn.execute('''SELECT * FROM (
            SELECT DISTINCT ON(question_id) version_id,question_id,revision,question_text,state,created_at,answer
            FROM trivia_question_versions ''' + ("WHERE state='published' AND verified_at IS NOT NULL" if published_only else '') + ''' ORDER BY question_id,revision DESC
        ) latest ORDER BY created_at DESC LIMIT 100''').fetchall()
    return {'questions': rows}


@router.get('/questions/{version_id}', dependencies=[Depends(require_editor)])
def question(version_id: UUID):
    with get_connection() as conn:
        row = conn.execute('SELECT * FROM trivia_question_versions WHERE version_id=%s', (version_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Question version not found')
        row['evidence'] = [r['evidence'] for r in conn.execute('SELECT evidence FROM trivia_evidence WHERE version_id=%s ORDER BY fixture_id',
                                                             (version_id,)).fetchall()]
        row['leaderboard'] = row.get('analysis', {}).get('leaderboard', [])
    return row


@router.post('/questions/{version_id}/publish', dependencies=[Depends(require_editor)])
def publish(version_id: UUID):
    with get_connection() as conn:
        row = conn.execute('SELECT * FROM trivia_question_versions WHERE version_id=%s FOR UPDATE', (version_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Question version not found')
        if row['state'] == 'published':
            return {'version_id': version_id, 'state': 'published'}
        if row['state'] == 'retired' or not row['coverage']['publishable']:
            raise HTTPException(409, 'Publication requires complete coverage, a non-empty sample and the selected minimum sample')
        if row.get('analysis', {}).get('policy_version') != POLICY_VERSION:
            raise HTTPException(409, 'Recalculate and save a new revision under the current quality policy')
        recomputed = evaluate(conn, EvaluationRequest(specification=row['specification'], dataset_id=row['dataset_id']))
        evidence = [r['evidence'] for r in conn.execute('SELECT evidence FROM trivia_evidence WHERE version_id=%s', (version_id,)).fetchall()]
        if (not recomputed['coverage']['publishable'] or recomputed['answer'] != row['answer'] or
            recomputed['analysis'] != row['analysis'] or evidence_hash(evidence) != row['analysis']['evidence_hash']):
            raise HTTPException(409, 'Stored answer or evidence does not match verification; create a new revision')
        conn.execute("""UPDATE trivia_question_versions SET state='published',published_at=NOW(),verified_at=NOW(),verified_by=%s
            WHERE version_id=%s""", (os.getenv('TRIVIA_EDITOR_USERNAME') or 'local-service', version_id))
    return {'version_id': version_id, 'state': 'published'}


@router.post('/questions/{version_id}/grade')
def grade(version_id: UUID, response: GradeAnswer):
    with get_connection() as conn:
        row = conn.execute('SELECT state, answer FROM trivia_question_versions WHERE version_id=%s', (version_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Question version not found')
    if row['state'] != 'published':
        raise HTTPException(409, 'Only published questions accept answers')
    return grade_answer(row['answer'], response)


def grade_answer(answer, response):
    if answer.get('grading_policy')=='colour-set-v2':
        components=answer['colour_components']
        parts=[normalized_name(p.strip()) for p in re.split(r'\band\b|\ba\b|[&+,/]',response.text.lower())] if response.text else []
        accepted=[{normalized_name(a) for a in c['aliases']} for c in components]
        correct=bool(accepted) and len(parts)==len(accepted) and any(all(p in aliases for p,aliases in zip(order,accepted)) for order in permutations(parts))
        return {'correct':correct,'answer':answer}
    if answer['kind'] == 'entity':
        accepted = {normalized_name(name) for entity in answer['accepted'] for name in entity['aliases']}
        return {'correct': response.text is not None and normalized_name(response.text) in accepted, 'answer': answer}
    if response.value is None:
        return {'correct': False, 'answer': answer}
    decimals = answer.get('rounding_decimals', 1 if answer['kind'] == 'percentage' else 0)
    value = Decimal(str(response.value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    correct = value == Decimal(str(answer['value']))
    if answer['kind'] == 'integer' and response.value != int(response.value):
        correct = False
    return {'correct': correct, 'answer': answer}


@router.get('/play/questions')
def play_questions(response: Response, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    response.headers['Cache-Control'] = 'no-store'
    with get_connection() as conn:
        # Draft revisions must not replace the last published question for players.
        rows = conn.execute('''SELECT version_id, question_text, answer->>'kind' AS answer_kind
            FROM (SELECT DISTINCT ON(question_id) version_id, question_id, question_text, answer, published_at
                  FROM trivia_question_versions WHERE state='published'
                  ORDER BY question_id, revision DESC) published
            ORDER BY published_at DESC, version_id LIMIT %s OFFSET %s''', (limit + 1, offset)).fetchall()
    return {'questions': rows[:limit], 'next_offset': offset + limit if len(rows) > limit else None}
