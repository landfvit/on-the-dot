"""Private operational reporting. Never return decks, answers or session tokens."""
from contextlib import contextmanager
from typing import Literal
from uuid import UUID
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, field_validator

from api.database import get_connection
from api.solo_routes import active_releases
from api.trivia_access import require_editor
from api.trivia_models import StrictModel

router = APIRouter(prefix='/api/developer', dependencies=[Depends(require_editor)])

# Project only operational fields in PostgreSQL; a Daily deck can hold 1,000
# questions and must never travel to the dashboard. Friend rooms count once.
RUNS = """
WITH raw_runs AS (
 SELECT run_id,'solo'::text mode,account_id owner_id,created_at,state FROM game_solo_runs
 UNION ALL
 SELECT run_id,mode,owner_id,created_at,state FROM game_mode_runs
), runs AS (
 SELECT run_id,mode,owner_id,created_at,
 CASE WHEN state->>'phase' NOT IN ('FINISHED','ABANDONED') AND
   COALESCE((state->>'expires_at')::numeric,
     (state->>'created_at')::numeric+COALESCE((state#>>'{rules,max_run_ms}')::numeric,
     (state#>>'{rules,max_match_ms}')::numeric)) <= extract(epoch FROM now())*1000
   THEN 'EXPIRED' ELSE state->>'phase' END phase,
 state->>'difficulty' difficulty,state->>'end_reason' end_reason,
 jsonb_array_length(COALESCE(state->'history','[]')) rounds,
 to_timestamp((state->>'finished_at')::double precision/1000) finished_at,
 GREATEST(created_at,
   CASE WHEN mode<>'friend' THEN to_timestamp((state->>'opened_at')::double precision/1000) END,
   to_timestamp((SELECT max((h->>'answered_at')::double precision)
     FROM jsonb_array_elements(state->'history') h WHERE h->>'option_id' IS NOT NULL)/1000),
   to_timestamp((SELECT max((p->>'seen')::double precision)
     FROM jsonb_array_elements(state->'players') p)/1000)) last_activity
 FROM raw_runs
), participants AS (
 SELECT run_id,account_id FROM game_solo_runs
 UNION ALL SELECT run_id,account_id FROM game_mode_members
)
"""


@contextmanager
def connection(readonly=True):
    with get_connection() as conn:
        if readonly:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute("SET LOCAL statement_timeout='8s'")
        conn.execute("SET LOCAL lock_timeout='3s'")
        if not conn.execute("SELECT to_regclass('game_admin_audit') ready").fetchone()['ready']:
            raise HTTPException(503, 'Apply migration 050_developer_dashboard first')
        yield conn


@router.get('/overview')
def overview(days: int = Query(7, ge=7, le=90)):
    if days not in (7,30,90): raise HTTPException(422,'Choose 7, 30 or 90 days')
    with connection() as conn:
        # Whole UTC calendar days, including today; every chart uses this window.
        window = conn.execute("SELECT now() generated_at, date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' - (%s-1)*interval '1 day' since", (days,)).fetchone()
        since = window['since']
        totals = conn.execute('''SELECT count(*) FILTER(WHERE NOT is_guest AND deleted_at IS NULL) registered,
            count(*) FILTER(WHERE NOT is_guest AND deleted_at IS NULL AND created_at>=%s) new_players,
            count(*) FILTER(WHERE blocked_at IS NOT NULL AND deleted_at IS NULL) blocked
            FROM game_accounts''', (since,)).fetchone()
        totals.update(conn.execute(RUNS + '''SELECT count(*) games,
            count(*) FILTER(WHERE phase='FINISHED') completed,
            count(*) FILTER(WHERE phase IN ('ABANDONED','EXPIRED')) abandoned,
            count(*) FILTER(WHERE phase NOT IN ('FINISHED','ABANDONED','EXPIRED')
                AND last_activity>=now()-interval '5 minutes') active_games
            FROM runs WHERE created_at>=%s''', (since,)).fetchone())
        totals.update(conn.execute(RUNS + '''SELECT
            count(DISTINCT a.account_id) FILTER(WHERE NOT a.is_guest) players,
            count(DISTINCT a.account_id) FILTER(WHERE a.is_guest) guests
            FROM runs r JOIN participants p USING(run_id) JOIN game_accounts a USING(account_id)
            WHERE r.last_activity>=%s AND a.deleted_at IS NULL''', (since,)).fetchone())
        trend = conn.execute(RUNS + '''SELECT d::date AS day,count(r.run_id) games,
            count(r.run_id) FILTER(WHERE r.mode='solo') solo,
            count(r.run_id) FILTER(WHERE r.mode='daily') daily,
            count(r.run_id) FILTER(WHERE r.mode='friend') friend
            FROM generate_series((%s AT TIME ZONE 'UTC')::date,(now() AT TIME ZONE 'UTC')::date,interval '1 day') d
            LEFT JOIN runs r ON (r.created_at AT TIME ZONE 'UTC')::date=d::date
            GROUP BY d ORDER BY d''', (since,)).fetchall()
        modes = conn.execute(RUNS + '''SELECT mode,count(*) games,
            count(*) FILTER(WHERE phase='FINISHED') completed,
            count(*) FILTER(WHERE phase IN ('ABANDONED','EXPIRED')) abandoned
            FROM runs WHERE created_at>=%s GROUP BY mode ORDER BY mode''', (since,)).fetchall()
        releases = active_releases(conn)
        questions = conn.execute('''SELECT d.difficulty,count(*) approved FROM penalty_bank_questions p
            JOIN game_current_difficulty d USING(release_id,question_id)
            WHERE p.release_id=ANY(%s) AND d.approved GROUP BY d.difficulty''', (releases,)).fetchall()
    return {**window, 'days': days, 'totals': totals, 'trend': trend, 'modes': modes, 'questions': questions}


def literal_search(value):
    return '%' + value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


@router.get('/players')
def players(search: str = Query('', max_length=100), status: Literal['all','blocked','guests'] = 'all',
            offset: int = Query(0, ge=0, le=100000), limit: int = Query(25, ge=1, le=100)):
    where = 'a.deleted_at IS NULL AND (a.username ILIKE %s OR a.email ILIKE %s)'
    where += ' AND a.is_guest' if status == 'guests' else ' AND NOT a.is_guest'
    if status == 'blocked': where += ' AND a.blocked_at IS NOT NULL'
    params = [literal_search(search.strip())]*2
    with connection() as conn:
        total = conn.execute('SELECT count(*) n FROM game_accounts a WHERE '+where, params).fetchone()['n']
        rows = conn.execute(RUNS + '''SELECT a.account_id,a.username,a.email,a.is_guest,a.created_at,a.blocked_at,
            c.name club,COALESCE(x.xp,0) xp,COALESCE(g.games,0) games,g.last_activity,
            (SELECT max(level) FROM game_levels WHERE minimum_xp<=COALESCE(x.xp,0)) level
            FROM game_accounts a LEFT JOIN game_clubs c ON c.team_id=a.club_id
            LEFT JOIN LATERAL (SELECT sum(amount) xp FROM game_all_xp WHERE account_id=a.account_id) x ON TRUE
            LEFT JOIN LATERAL (SELECT count(*) games,max(r.last_activity) last_activity
                FROM participants p JOIN runs r USING(run_id) WHERE p.account_id=a.account_id) g ON TRUE
            WHERE '''+where+' ORDER BY a.created_at DESC,a.account_id LIMIT %s OFFSET %s', [*params,limit,offset]).fetchall()
    return {'items':rows,'total':total,'offset':offset,'limit':limit}


@router.get('/games')
def games(mode: Literal['all','solo','daily','friend'] = 'all',
          status: Literal['all','active','finished','abandoned'] = 'all', account_id: UUID | None = None,
          offset: int = Query(0, ge=0, le=100000), limit: int = Query(25, ge=1, le=100)):
    where, params = ['TRUE'], []
    if mode != 'all': where.append('r.mode=%s'); params.append(mode)
    if status == 'active': where.append("r.phase NOT IN ('FINISHED','ABANDONED','EXPIRED') AND r.last_activity>=now()-interval '5 minutes'")
    elif status == 'finished': where.append("r.phase='FINISHED'")
    elif status == 'abandoned': where.append("r.phase IN ('ABANDONED','EXPIRED')")
    if account_id:
        where.append('EXISTS(SELECT 1 FROM participants WHERE run_id=r.run_id AND account_id=%s)'); params.append(account_id)
    clause = ' FROM runs r WHERE '+' AND '.join(where)
    with connection() as conn:
        total = conn.execute(RUNS+'SELECT count(*) n'+clause,params).fetchone()['n']
        rows = conn.execute(RUNS+'''SELECT r.*,
            (SELECT jsonb_agg(jsonb_build_object('username',CASE WHEN a.is_guest THEN 'Guest' ELSE a.username END,
                'account_id',a.account_id,'is_guest',a.is_guest) ORDER BY a.username)
             FROM participants p JOIN game_accounts a USING(account_id) WHERE p.run_id=r.run_id) players,
            (SELECT COALESCE(sum(amount),0) FROM game_all_xp WHERE run_id=r.run_id) xp
            '''+clause+' ORDER BY r.created_at DESC,r.run_id LIMIT %s OFFSET %s',[*params,limit,offset]).fetchall()
    return {'items':rows,'total':total,'offset':offset,'limit':limit}


@router.get('/players/{account_id}')
def player(account_id: UUID):
    with connection() as conn:
        row = conn.execute('''SELECT a.account_id,a.username,a.email,a.bio,a.created_at,a.blocked_at,a.is_guest,
            c.name club FROM game_accounts a LEFT JOIN game_clubs c ON c.team_id=a.club_id
            WHERE a.account_id=%s AND a.deleted_at IS NULL''',(account_id,)).fetchone()
        if not row: raise HTTPException(404,'Player not found')
        row['sessions'] = conn.execute('SELECT count(*) n FROM game_sessions WHERE account_id=%s AND expires_at>now()', (account_id,)).fetchone()['n']
        row['audit'] = conn.execute('''SELECT request_id,action,reason,actor,created_at FROM game_admin_audit
            WHERE account_id=%s ORDER BY created_at DESC LIMIT 30''',(account_id,)).fetchall()
    return row


class Action(StrictModel):
    action: Literal['block','unblock','revoke_sessions']
    reason: str = Field(min_length=3,max_length=500)
    confirmation: str = Field(min_length=3,max_length=24)
    request_id: UUID

    @field_validator('reason')
    @classmethod
    def meaningful(cls,value):
        value=value.strip()
        if len(value)<3: raise ValueError('Enter a reason')
        return value


@router.post('/players/{account_id}/actions')
def action(account_id: UUID, body: Action):
    with connection(readonly=False) as conn:
        # Account-first lock ordering matches login/password changes. Revocation,
        # blocking and the immutable audit entry either all commit or all roll back.
        row = conn.execute('SELECT username,is_guest FROM game_accounts WHERE account_id=%s AND deleted_at IS NULL FOR UPDATE', (account_id,)).fetchone()
        if not row or row['is_guest']: raise HTTPException(404,'Registered player not found')
        if body.confirmation != row['username']: raise HTTPException(422,'Type the exact username to confirm')
        actor = os.environ['TRIVIA_EDITOR_USERNAME']
        inserted = conn.execute('''INSERT INTO game_admin_audit(request_id,account_id,action,reason,actor)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING request_id''',
            (body.request_id,account_id,body.action,body.reason,actor)).fetchone()
        if not inserted:
            previous = conn.execute('SELECT * FROM game_admin_audit WHERE request_id=%s', (body.request_id,)).fetchone()
            if (previous['account_id'],previous['action'],previous['reason'],previous['actor']) != (account_id,body.action,body.reason,actor):
                raise HTTPException(409,'Request ID already used for a different action')
            return {'ok':True,'request_id':body.request_id}
        if body.action == 'block':
            conn.execute('UPDATE game_accounts SET blocked_at=COALESCE(blocked_at,clock_timestamp()) WHERE account_id=%s',(account_id,))
        elif body.action == 'unblock':
            conn.execute('UPDATE game_accounts SET blocked_at=NULL WHERE account_id=%s',(account_id,))
        if body.action in ('block','revoke_sessions'):
            conn.execute('DELETE FROM game_sessions WHERE account_id=%s',(account_id,))
        if body.action == 'block':
            conn.execute('DELETE FROM game_password_resets WHERE account_id=%s',(account_id,))
    return {'ok':True,'request_id':body.request_id}


@router.get('/audit')
def audit(offset: int = Query(0,ge=0,le=100000)):
    with connection() as conn:
        total = conn.execute('SELECT count(*) n FROM game_admin_audit').fetchone()['n']
        rows = conn.execute('''SELECT l.*,a.username FROM game_admin_audit l JOIN game_accounts a USING(account_id)
            ORDER BY created_at DESC,request_id LIMIT 25 OFFSET %s''',(offset,)).fetchall()
    return {'items':rows,'total':total,'offset':offset,'limit':25}
