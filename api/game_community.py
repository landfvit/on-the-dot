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
                metric: Literal['level','streak','wins','win_rate','xp','daily_wins','daily_highscore']='xp',
                board: Literal['players','teams']='players',
                offset: int = Query(0, ge=0, le=10000), limit: int = Query(25, ge=1, le=100)):
    with get_connection() as conn:
        username = team_id = None
        if request.cookies.get(COOKIE):
            try:
                user = account(conn, request)
                username, team_id = user['username'], user['club_id']
            except HTTPException as exc:
                if exc.status_code != 401: raise
        now = conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
        if metric=='daily_highscore':
            return daily_highscores(conn,board,username,team_id,offset,limit,now)
        if metric in ('level','streak'):period='all'
        since = period_start(period, now)
        # Only these two fixed SQL fragments vary; no request value is SQL text.
        source = '''SELECT username,xp,total_xp,wins,losses,played,win_rate,club,level,streak,daily_wins,
                        username sort_name,username=%(username)s is_me FROM levels
                    WHERE CASE WHEN %(metric)s='daily_wins' THEN daily_wins>0
                        WHEN %(metric)s IN ('wins','win_rate') THEN played>0
                        WHEN %(metric)s='streak' THEN total_xp>0 OR played>0 OR streak>0
                        ELSE xp>0 OR played>0 END'''
        if board == 'teams':
            # Average member percentages, not total wins / total matches. Members
            # with no matches have NULL win_rate and do not dilute that average.
            source = '''SELECT c.team_id,c.name,count(l.account_id)::int members,
                        COALESCE(sum(l.xp),0)::bigint xp,COALESCE(sum(l.total_xp),0)::bigint total_xp,
                        COALESCE(sum(l.level),0)::bigint level,COALESCE(sum(l.streak),0)::bigint streak,
                        COALESCE(sum(l.daily_wins),0)::bigint daily_wins,
                        COALESCE(sum(l.wins),0)::bigint wins,COALESCE(sum(l.losses),0)::bigint losses,
                        COALESCE(sum(l.played),0)::bigint played,avg(l.win_rate) win_rate,
                        c.name sort_name,c.team_id=%(team_id)s is_me
                    FROM game_clubs c LEFT JOIN levels l ON l.club_id=c.team_id GROUP BY c.team_id,c.name'''
        # One SQL snapshot for ranks, distribution and the current player's
        # position. Ties share a rank; username only stabilizes pagination.
        result = conn.execute('''WITH points AS (
            SELECT account_id,sum(amount)::bigint total_xp,
                sum(CASE WHEN %(since)s::timestamptz IS NULL OR created_at>=%(since)s THEN amount ELSE 0 END)::bigint xp
            FROM game_all_xp WHERE created_at<=%(now)s GROUP BY account_id
        ), daily AS (
            SELECT account_id,count(*) daily_wins FROM game_daily_wins
            WHERE won_at<=%(now)s AND (%(since)s::timestamptz IS NULL OR won_at>=%(since)s) GROUP BY account_id
        ), matches AS (
            SELECT account_id,count(*) FILTER(WHERE won) wins,count(*) FILTER(WHERE NOT won) losses,count(*) played,
                100.0*count(*) FILTER(WHERE won)/NULLIF(count(*),0) win_rate
            FROM game_match_results WHERE finished_at<=%(now)s AND (%(since)s::timestamptz IS NULL OR finished_at>=%(since)s)
            GROUP BY account_id
        ), activity AS (
            SELECT account_id,day,
                day-(row_number() OVER(PARTITION BY account_id ORDER BY day))::int island
            FROM game_all_activity WHERE day<=(%(now)s::timestamptz AT TIME ZONE 'UTC')::date
        ), streaks AS (
            SELECT account_id,count(*)::int streak FROM activity GROUP BY account_id,island
            HAVING max(day)>=(%(now)s::timestamptz AT TIME ZONE 'UTC')::date-1
        ), scores AS (
            SELECT a.account_id,a.username,a.club_id,COALESCE(s.streak,0) streak,COALESCE(d.daily_wins,0) daily_wins,
                COALESCE(p.xp,0) xp,COALESCE(p.total_xp,0) total_xp,
                COALESCE(m.wins,0) wins,COALESCE(m.losses,0) losses,COALESCE(m.played,0) played,m.win_rate,
                CASE WHEN c.team_id IS NOT NULL THEN jsonb_build_object('team_id',c.team_id,'name',c.name) END club
            FROM game_accounts a LEFT JOIN points p USING(account_id) LEFT JOIN matches m USING(account_id)
            LEFT JOIN streaks s USING(account_id) LEFT JOIN daily d USING(account_id)
            LEFT JOIN game_clubs c ON c.team_id=a.club_id WHERE NOT a.is_guest AND a.deleted_at IS NULL
        ), levels AS (
            SELECT *,
                   (SELECT level FROM game_levels WHERE minimum_xp<=total_xp
                    ORDER BY minimum_xp DESC LIMIT 1) level
            FROM scores
        ), competitors AS (''' + source + '''), ranking_values AS (
            SELECT *,CASE %(metric)s WHEN 'level' THEN level WHEN 'wins' THEN wins
                WHEN 'daily_wins' THEN daily_wins WHEN 'streak' THEN streak WHEN 'win_rate' THEN win_rate ELSE xp END ranking_value FROM competitors
        ), ranked AS (
            SELECT dense_rank() OVER(ORDER BY ranking_value DESC NULLS LAST) rank,* FROM ranking_values
        ) SELECT
            (SELECT count(*) FROM ranked) participants,
            COALESCE((SELECT jsonb_agg(to_jsonb(r)-'sort_name'-'is_me' ORDER BY r.ranking_value DESC NULLS LAST,r.sort_name) FROM (
                SELECT * FROM ranked ORDER BY ranking_value DESC NULLS LAST,sort_name LIMIT %(limit)s OFFSET %(offset)s
            ) r),'[]'::jsonb) entries,
            (SELECT to_jsonb(r)-'sort_name'-'is_me' FROM ranked r WHERE is_me) me,
            (SELECT jsonb_agg(b ORDER BY b.minimum) FROM (
                SELECT minimum,label,(SELECT count(*) FROM ranked WHERE xp>=minimum
                    AND (maximum IS NULL OR xp<maximum)) count
                FROM (VALUES (0,100,'<100'),(100,250,'100-249'),(250,500,'250-499'),
                    (500,1000,'500-999'),(1000,NULL,'1,000+')) buckets(minimum,maximum,label)
            ) b) distribution''',
            {'since': since, 'now': now, 'username': username, 'team_id':team_id,
             'limit': limit, 'offset': offset,'metric':metric}).fetchone()
        return {**result, 'period': period, 'metric':metric,'board':board,'since': since, 'as_of': now, 'timezone': 'UTC',
                'offset': offset, 'limit': limit, 'signed_in': username is not None}


def daily_highscores(conn,board,username,team_id,offset,limit,now):
    """One personal best per registered account; practice never enters this table."""
    source='''SELECT a.username,b.goals daily_highscore,a.username sort_name,
        a.username=%(username)s is_me,
        CASE WHEN c.team_id IS NOT NULL THEN jsonb_build_object('team_id',c.team_id,'name',c.name) END club
        FROM best b JOIN game_accounts a USING(account_id)
        LEFT JOIN game_clubs c ON c.team_id=a.club_id WHERE NOT a.is_guest AND a.deleted_at IS NULL'''
    if board=='teams':
        source='''SELECT c.team_id,c.name,sum(b.goals)::bigint daily_highscore,c.name sort_name,
            c.team_id=%(team_id)s is_me,count(*) members FROM best b
            JOIN game_accounts a USING(account_id) JOIN game_clubs c ON c.team_id=a.club_id
            WHERE NOT a.is_guest AND a.deleted_at IS NULL GROUP BY c.team_id,c.name'''
    result=conn.execute('''WITH best AS (
        SELECT account_id,max(goals) goals FROM game_daily_scores WHERE recorded_at<=%(now)s GROUP BY account_id
    ), competitors AS ('''+source+'''), ranked AS (
        SELECT dense_rank() OVER(ORDER BY daily_highscore DESC) rank,*,daily_highscore ranking_value FROM competitors
    ) SELECT (SELECT count(*) FROM ranked) participants,
        COALESCE((SELECT jsonb_agg(to_jsonb(r)-'sort_name'-'is_me' ORDER BY daily_highscore DESC,sort_name)
            FROM (SELECT * FROM ranked ORDER BY daily_highscore DESC,sort_name LIMIT %(limit)s OFFSET %(offset)s) r),'[]'::jsonb) entries,
        (SELECT to_jsonb(r)-'sort_name'-'is_me' FROM ranked r WHERE is_me) me''',
        dict(username=username,team_id=team_id,now=now,limit=limit,offset=offset)).fetchone()
    return {**result,'distribution':[],'metric':'daily_highscore','period':'all','board':board,
            'since':None,'as_of':now,'timezone':'UTC','offset':offset,'limit':limit,'signed_in':username is not None}


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
