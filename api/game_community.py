"""Read-only rankings from the XP ledger and private, owner-scoped history."""
from datetime import datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from api.database import get_connection
from api.player_accounts import account, COOKIE
from api.solo_engine import rewards, is_shootout, shootout

router = APIRouter(prefix='/api/community', tags=['game community'])


def period_start(period, now):
    midnight = datetime.combine(now.astimezone(timezone.utc).date(), time.min, timezone.utc)
    return midnight if period == 'today' else midnight - timedelta(days=6) if period == 'week' else None


@router.get('/leaderboard')
def leaderboard(request: Request, period: Literal['today', 'week', 'all'] = 'today',
                metric: Literal['level','wins','win_rate','xp']='xp',
                offset: int = Query(0, ge=0, le=10000), limit: int = Query(25, ge=1, le=100)):
    with get_connection() as conn:
        username = None
        if request.cookies.get(COOKIE):
            try: username = account(conn, request)['username']
            except HTTPException as exc:
                if exc.status_code != 401: raise
        now = conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
        if metric=='level':period='all'
        since = period_start(period, now)
        # One SQL snapshot for ranks, distribution and the current player's
        # position. Ties share a rank; username only stabilizes pagination.
        result = conn.execute('''WITH points AS (
            SELECT account_id,sum(amount)::bigint total_xp,
                sum(CASE WHEN %(since)s::timestamptz IS NULL OR created_at>=%(since)s THEN amount ELSE 0 END)::bigint xp
            FROM game_xp_ledger WHERE created_at<=%(now)s GROUP BY account_id
        ), matches AS (
            SELECT account_id,count(*) FILTER(WHERE won) wins,count(*) FILTER(WHERE NOT won) losses,count(*) played,
                100.0*count(*) FILTER(WHERE won)/NULLIF(count(*),0) win_rate
            FROM game_match_results WHERE finished_at<=%(now)s AND (%(since)s::timestamptz IS NULL OR finished_at>=%(since)s)
            GROUP BY account_id
        ), scores AS (
            SELECT a.username,COALESCE(p.xp,0) xp,COALESCE(p.total_xp,0) total_xp,
                COALESCE(m.wins,0) wins,COALESCE(m.losses,0) losses,COALESCE(m.played,0) played,m.win_rate,
                CASE WHEN c.team_id IS NOT NULL THEN jsonb_build_object('team_id',c.team_id,'name',c.name) END club
            FROM game_accounts a LEFT JOIN points p USING(account_id) LEFT JOIN matches m USING(account_id)
            LEFT JOIN game_clubs c ON c.team_id=a.club_id WHERE NOT a.is_guest AND a.deleted_at IS NULL
        ), levels AS (
            SELECT *,
                   (SELECT level FROM game_levels WHERE minimum_xp<=total_xp
                    ORDER BY minimum_xp DESC LIMIT 1) level
            FROM scores WHERE CASE WHEN %(metric)s IN ('wins','win_rate') THEN played>0 ELSE xp>0 OR played>0 END
        ), ranking_values AS (
            SELECT *,CASE %(metric)s WHEN 'level' THEN level WHEN 'wins' THEN wins
                WHEN 'win_rate' THEN win_rate ELSE xp END ranking_value FROM levels
        ), ranked AS (
            SELECT dense_rank() OVER(ORDER BY ranking_value DESC) rank,* FROM ranking_values
        ) SELECT
            (SELECT count(*) FROM ranked) participants,
            COALESCE((SELECT jsonb_agg(r ORDER BY r.ranking_value DESC,r.username) FROM (
                SELECT * FROM ranked ORDER BY ranking_value DESC,username LIMIT %(limit)s OFFSET %(offset)s
            ) r),'[]'::jsonb) entries,
            (SELECT to_jsonb(r) FROM ranked r WHERE username=%(username)s) me,
            (SELECT jsonb_agg(b ORDER BY b.minimum) FROM (
                SELECT minimum,label,(SELECT count(*) FROM ranked WHERE xp>=minimum
                    AND (maximum IS NULL OR xp<maximum)) count
                FROM (VALUES (0,100,'<100'),(100,250,'100-249'),(250,500,'250-499'),
                    (500,1000,'500-999'),(1000,NULL,'1,000+')) buckets(minimum,maximum,label)
            ) b) distribution''',
            {'since': since, 'now': now, 'username': username, 'limit': limit, 'offset': offset,'metric':metric}).fetchone()
        return {**result, 'period': period, 'metric':metric,'since': since, 'as_of': now, 'timezone': 'UTC',
                'offset': offset, 'limit': limit, 'signed_in': username is not None}


@router.get('/history')
def history(request: Request, offset: int = Query(0, ge=0, le=10000), limit: int = Query(20, ge=1, le=100)):
    with get_connection() as conn:
        user = account(conn, request)
        rows = conn.execute('''SELECT run_id,state,created_at FROM game_solo_runs
            WHERE account_id=%s AND NOT is_trial AND state->>'phase' IN ('FINISHED','ABANDONED')
            ORDER BY (state->>'finished_at')::bigint DESC,run_id DESC LIMIT %s OFFSET %s''',
            (user['account_id'], limit+1, offset)).fetchall()
        items = []
        for row in rows[:limit]:
            s = row['state']; reward = rewards(s)
            items.append({'run_id': str(row['run_id']), 'phase': s['phase'], 'difficulty': s['difficulty'],
                          'category': s['category'], 'finished_at': s['finished_at'],
                          'correct': reward['correct'], 'questions': len(s['history']) if is_shootout(s) else s['rules']['questions'],
                          'shootout': shootout(s) if is_shootout(s) else None,
                          'xp': reward['total_xp'], 'perfect': reward['perfect']})
        return {'items': items, 'offset': offset, 'limit': limit, 'has_more': len(rows)>limit}
