"""Private query endpoints; execution shares trivia's snapshot, evidence and quality gates."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.types.json import Jsonb

from api.database import get_connection
from api.sports_query import DEFINITIONS, METRICS, PARSER_VERSION, ParseRequest, SportsQuery, parse_query
from api.trivia import dataset, evaluate
from api.trivia_access import require_editor
from api.trivia_audit import audit_dataset
from api.trivia_models import EvaluationRequest

router = APIRouter(prefix='/api/query', tags=['sports-query'], dependencies=[Depends(require_editor)])


def catalogue(conn, competition_id, dataset_id=None):
    data = dataset(conn, dataset_id)
    league = data['summary']['leagues'].get(str(competition_id))
    if not league:
        raise HTTPException(422, 'Competition is not present in this snapshot')
    teams = conn.execute('''SELECT DISTINCT team_id,team_name FROM trivia_match_team_facts
        WHERE dataset_id=%s AND league_id=%s ORDER BY team_name''', (data['dataset_id'], competition_id)).fetchall()
    if not teams:
        raise HTTPException(422, 'No team facts exist for this competition snapshot')
    aliases = conn.execute('SELECT team_id,alias FROM trivia_team_aliases ORDER BY alias,team_id').fetchall()
    for team in teams:
        team['aliases'] = [a['alias'] for a in aliases if a['team_id'] == team['team_id']]
    return {'dataset_id': str(data['dataset_id']), 'snapshot_date': data['created_at'].isoformat(),
            'competition_id': competition_id, 'competition_name': league['name'],
            'competition_aliases': sorted({league['name'].casefold(), *(['premier league', 'pl', 'epl'] if competition_id == 39 else [])}),
            'teams': teams, 'seasons': audit_dataset(conn, data, competition_id),
            'groups': conn.execute('SELECT * FROM trivia_opponent_groups WHERE league_id=%s ORDER BY group_key,version', (competition_id,)).fetchall(),
            'metrics': METRICS, 'definitions': DEFINITIONS}


@router.get('/catalogue')
def get_catalogue(competition_id: int = Query(..., gt=0), dataset_id: UUID | None = None):
    with get_connection() as conn:
        return catalogue(conn, competition_id, dataset_id)


@router.post('/parse')
def parse(request: ParseRequest):
    with get_connection() as conn:
        context = catalogue(conn, request.competition_id, request.dataset_id)
        result = parse_query(request, context)
        if not result['ok']:
            conn.execute('''INSERT INTO trivia_unrecognized_queries(dataset_id,parser_version,query_text,recognized,issues)
                VALUES (%s,%s,%s,%s,%s)''', (context['dataset_id'], PARSER_VERSION, request.text,
                Jsonb(result['recognized']), Jsonb(result['issues'])))
        return result


@router.post('/evaluate')
def run(query: SportsQuery):
    with get_connection() as conn:
        result = evaluate(conn, EvaluationRequest(specification=query.specification(), dataset_id=query.dataset_id))
        result['query'] = query.model_dump(mode='json')
        result['metric_definition'] = DEFINITIONS[query.metric]
        return result
