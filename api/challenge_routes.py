"""Registered Daily Challenges and guest-capable, unrated Friend Duels."""
from copy import deepcopy
from datetime import datetime,time,timedelta,timezone
import secrets
from typing import Literal
from uuid import UUID,uuid4

from fastapi import APIRouter,Depends,HTTPException,Request,Response
from psycopg.types.json import Jsonb

from api.database import get_connection
from api.game_state import checkpoint,progress,QuestionWindow
from api.player_accounts import account,profile,xp_transition,COOKIE as ACCOUNT_COOKIE
from api.solo_trials import trial_player
from api.penalty_routes import now_ms,rate_limit
from api.solo_routes import active_releases,Answer,Next
from api.solo_history import week_window
from api.solo_topics import sources
from api.numeric_choices import refresh as refresh_choices
from api.trivia_models import StrictModel
from api.trivia_quizzes import same_origin
from api import challenge_engine as game

router=APIRouter(tags=['daily and friends'])
RANDOM=secrets.SystemRandom()
# Closed SQL projection, never derived from request input. JSONPath loads the
# answered prefix plus current/next question, not ~1 MB of unseen snapshots.
DAILY_COLUMNS="""r.run_id,r.mode,r.owner_id,r.day,r.state-'deck' AS state,
    jsonb_array_length(r.state->'deck') AS deck_size,
    jsonb_path_query_array(r.state->'deck','$[0 to $position]',
        jsonb_build_object('position',(r.state->>'position')::int)) AS deck_prefix"""


def daily_window(row):
    if row is not None:
        row['state']['deck']=QuestionWindow(row.pop('deck_prefix'),row.pop('deck_size'))
    return row


class Start(StrictModel):
    request_id:UUID


class FriendStart(Start):
    difficulty:Literal['easy','medium','hard']='medium'


def day_window(now):
    day=datetime.fromtimestamp(now/1000,timezone.utc).date()
    reset=datetime.combine(day+timedelta(days=1),time.min,timezone.utc)
    return day,reset


def candidates(conn):
    return conn.execute('''SELECT DISTINCT ON(p.question_id) p.question_id,p.release_id,d.revision_id,d.difficulty
        FROM penalty_bank_questions p JOIN game_current_difficulty d USING(release_id,question_id)
        WHERE p.release_id=ANY(%s) AND d.approved AND p.question->>'topic'=ANY(%s)
        ORDER BY p.question_id,d.revision_id DESC''',(active_releases(conn),sources('ALL'))).fetchall()


def snapshots(conn,rows):
    selected={(r['release_id'],r['question_id']):r for r in rows}
    questions=conn.execute('''SELECT release_id,question_id,question FROM penalty_bank_questions
        WHERE question_id=ANY(%s) AND release_id=ANY(%s)''',
        ([r['question_id'] for r in rows],[r['release_id'] for r in rows])).fetchall()
    deck=[]
    for row in questions:
        meta=selected.get((row['release_id'],row['question_id']))
        if not meta:continue
        q=refresh_choices(deepcopy(row['question']))
        answer=next(o for o in q['options'] if o['id']==q['correct'])
        RANDOM.shuffle(q['options'])
        for i,o in enumerate(q['options']):
            o['id']=str(i)
            if o is answer:q['correct']=str(i)
        q.update(question_id=str(row['question_id']),release_id=str(row['release_id']),
                 difficulty=meta['difficulty'],difficulty_revision=meta['revision_id'])
        deck.append(q)
    RANDOM.shuffle(deck)
    return deck


def used_questions(conn,identities,now):
    week,_=week_window(now)
    return {str(r['question_id']) for r in conn.execute('''SELECT question_id FROM game_used_questions
        WHERE account_id=ANY(%s) AND week_start=%s''',(identities,week)).fetchall()}


def daily_pool(conn,now):
    day,reset=day_window(now)
    # Existing pools are immutable: readers must not queue behind every start.
    row=conn.execute('SELECT deck,version FROM game_daily_pools WHERE day=%s',(day,)).fetchone()
    if row and row['version']==2:return row['deck'],day,reset
    # Only creation/legacy upgrades serialize, with a recheck under the lock.
    conn.execute('SELECT pg_advisory_xact_lock(%s,%s)',(47001,day.toordinal()))
    row=conn.execute('SELECT deck,version FROM game_daily_pools WHERE day=%s',(day,)).fetchone()
    if row and row['version']==2:return row['deck'],day,reset
    existing=row['deck'] if row else []
    ids={q['question_id'] for q in existing}
    eligible=[r for r in candidates(conn) if str(r['question_id']) not in ids]
    # Reserve many more than 50, but do not mark unseen questions as played.
    # Personal weekly history is filtered when each run starts.
    deck=existing+snapshots(conn,RANDOM.sample(eligible,min(len(eligible),max(0,1000-len(existing)))))
    if not deck:raise HTTPException(503,'Daily Challenge is unavailable: no approved questions.')
    if row:conn.execute('UPDATE game_daily_pools SET deck=%s,version=2 WHERE day=%s',(Jsonb(deck),day))
    else:conn.execute('INSERT INTO game_daily_pools(day,deck,version) VALUES(%s,%s,2)',(day,Jsonb(deck)))
    return deck,day,reset


def ensure_free(conn,ident,except_run=None):
    row=conn.execute('''SELECT r.mode,r.invite FROM game_mode_members m JOIN game_mode_runs r USING(run_id)
        WHERE m.account_id=%s AND m.active AND (%s::uuid IS NULL OR m.run_id<>%s)''',
        (ident,except_run,except_run)).fetchone()
    if row:raise HTTPException(409,'Finish or leave your active '+('Daily Challenge' if row['mode']=='daily' else 'Friend Duel')+' first.')
    if conn.execute("""SELECT 1 FROM game_solo_runs WHERE account_id=%s
        AND state->>'phase' NOT IN ('FINISHED','ABANDONED')""",(ident,)).fetchone():
        raise HTTPException(409,'Finish or end your active Solo shootout first.')


def mark_seen(conn,row,now):
    s=row['state']
    position=s['position'] if row['mode']=='daily' else s['round']['id'] if s['round'] and now>=s['round']['opens_at'] else 0
    if not position:return
    opened=s['opened_at'] if row['mode']=='daily' else s['round']['opens_at']
    if not opened:return
    q=s['deck'][position-1];week,_=week_window(opened);day,_=day_window(opened)
    for m in conn.execute('SELECT account_id FROM game_mode_members WHERE run_id=%s',(row['run_id'],)).fetchall():
        conn.execute('''INSERT INTO game_mode_seen(account_id,week_start,day,question_id,release_id,run_id,position)
            VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
            (m['account_id'],week,day,q['question_id'],q['release_id'],row['run_id'],position))


def persist(conn,row,now,before=None):
    s=row['state'];ident=row['owner_id'];run=row['run_id']
    if before is not None and before==(progress(s),len(s['deck'])):return
    if before is not None and before[1]==len(s['deck']):
        # Keep the frozen deck inside PostgreSQL instead of serializing and
        # sending ~1 MB twice for each Daily answer, heartbeat or transition.
        changed=conn.execute("UPDATE game_mode_runs SET state=jsonb_build_object('deck',state->'deck') || %s WHERE run_id=%s",
                             (Jsonb(progress(s)),run)).rowcount
    else:
        changed=conn.execute('UPDATE game_mode_runs SET state=%s WHERE run_id=%s AND state IS DISTINCT FROM %s',(Jsonb(s),run,Jsonb(s))).rowcount
    if not changed:return
    mark_seen(conn,row,now)
    if row['mode']=='daily':
        previous=len(before[0]['history']) if before is not None else 0
        for a in s['history'][previous:]:
            if a['correct']:
                conn.execute("""INSERT INTO game_mode_xp(account_id,run_id,slot,amount,reason)
                    VALUES(%s,%s,%s,%s,'correct_answer') ON CONFLICT DO NOTHING""",
                    (ident,run,a['position'],game.XP[s['deck'][a['position']-1]['difficulty']]))
        result=game.daily_view(s,now)
        if game.daily_survival(s) and s['rules']['ranked'] and s['phase'] in game.TERMINAL:
            conn.execute('''INSERT INTO game_daily_scores(run_id,account_id,day,goals,penalties)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                (run,ident,row['day'],result['correct'],len(s['history'])))
        if result['won']:
            conn.execute('INSERT INTO game_daily_wins(account_id,day,run_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(ident,row['day'],run))
        if s['phase']=='FINISHED' and s['history'] and all(a['option_id'] is not None for a in s['history']):
            day=day_window(s['finished_at'])[0]
            conn.execute('INSERT INTO game_mode_activity VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(ident,day,run))
    # Friend matches intentionally award no XP, rating, streak or Solo wins.
    if s['phase'] in game.TERMINAL:
        conn.execute('UPDATE game_mode_members SET active=FALSE WHERE run_id=%s AND active',(run,))


def daily_public(conn,row,now,user):
    result={**game.daily_view(row['state'],now),'run_id':str(row['run_id']),'is_trial':False,'xp_saved':True,'day':str(row['day'])}
    if row['state']['phase'] in game.TERMINAL:
        p=profile(conn,user)
        result['player_progress']={k:p[k] for k in ('total_xp','level','level_xp','next_level_xp')}
        result['xp_transition']=xp_transition(conn,user['account_id'],row['run_id'],result['player_progress'])
        if game.daily_survival(row['state']):
            result['highscore']=conn.execute('SELECT COALESCE(max(goals),0) best FROM game_daily_scores WHERE account_id=%s',
                (user['account_id'],)).fetchone()['best']
    return result


@router.get('/api/daily/catalog')
def daily_catalog(request:Request):
    with get_connection() as conn:
        user=account(conn,request);now=now_ms(conn);deck,day,reset=daily_pool(conn,now)
        used=used_questions(conn,[user['account_id']],now)
        ranked=not conn.execute('SELECT 1 FROM game_daily_attempts WHERE account_id=%s AND day=%s',(user['account_id'],day)).fetchone()
        remaining=sum(q['question_id'] not in used for q in deck) if ranked else sum(str(q['question_id']) not in used for q in candidates(conn))
        best=conn.execute('SELECT COALESCE(max(goals),0) best FROM game_daily_scores WHERE account_id=%s',(user['account_id'],)).fetchone()['best']
        return {'remaining':remaining,'ranked_available':ranked,'highscore':best,'day':day,
                'resets_at':reset,'rules':game.daily_create(deck,now,int(reset.timestamp()*1000),ranked=ranked)['rules']}


@router.get('/api/daily/active')
def daily_active(request:Request):
    with get_connection() as conn:
        user=account(conn,request,lock=True);now=now_ms(conn)
        row=daily_window(conn.execute('SELECT '+DAILY_COLUMNS+''' FROM game_mode_runs r JOIN game_mode_members m USING(run_id)
            WHERE m.account_id=%s AND m.active AND r.mode='daily' FOR UPDATE OF r''',(user['account_id'],)).fetchone())
        if not row:return {'run':None}
        before=checkpoint(row['state']);game.daily_tick(row['state'],now);persist(conn,row,now,before)
        return {'run':daily_public(conn,row,now,user)}


@router.post('/api/daily/runs',dependencies=[Depends(same_origin)],status_code=201)
def daily_start(body:Start,request:Request):
    rate_limit(request,'daily-start',20)
    with get_connection() as conn:
        user=account(conn,request,lock=True);ident=user['account_id'];now=now_ms(conn)
        row=conn.execute('SELECT * FROM game_mode_runs WHERE owner_id=%s AND start_request_id=%s',(ident,body.request_id)).fetchone()
        if row:
            if row['mode']!='daily':raise HTTPException(409,'Request ID belongs to another mode')
            before=checkpoint(row['state']);game.daily_tick(row['state'],now);persist(conn,row,now,before);return daily_public(conn,row,now,user)
        # Expired runs cannot block tomorrow's attempt, even if the player
        # starts directly without first polling the active-run endpoint.
        active=conn.execute("""SELECT r.* FROM game_mode_runs r JOIN game_mode_members m USING(run_id)
            WHERE m.account_id=%s AND m.active AND r.mode='daily' FOR UPDATE OF r""",(ident,)).fetchone()
        if active:
            before=checkpoint(active['state']);game.daily_tick(active['state'],now);persist(conn,active,now,before)
        ensure_free(conn,ident)
        pool,day,reset=daily_pool(conn,now)
        ranked=not conn.execute('SELECT 1 FROM game_daily_attempts WHERE account_id=%s AND day=%s',(ident,day)).fetchone()
        used=used_questions(conn,[ident],now)
        if ranked:deck=[q for q in pool if q['question_id'] not in used]
        else:
            rows=[q for q in candidates(conn) if str(q['question_id']) not in used]
            deck=snapshots(conn,RANDOM.sample(rows,min(len(rows),1000)))
        if not deck:raise HTTPException(409,'No unused questions remain. Try again after the question pool resets.')
        RANDOM.shuffle(deck)
        state=game.daily_create(deck,now,int(reset.timestamp()*1000),ranked=ranked)
        row=conn.execute('''INSERT INTO game_mode_runs(run_id,mode,owner_id,start_request_id,day,state)
            VALUES(%s,'daily',%s,%s,%s,%s) RETURNING *''',(uuid4(),ident,body.request_id,day,Jsonb(state))).fetchone()
        conn.execute('INSERT INTO game_mode_members(run_id,account_id,seat) VALUES(%s,%s,0)',(row['run_id'],ident))
        if ranked:conn.execute('INSERT INTO game_daily_attempts(account_id,day,run_id) VALUES(%s,%s,%s)',(ident,day,row['run_id']))
        return daily_public(conn,row,now,user)


def daily_action(run_id,request,command='view',body=None):
    failure=None
    with get_connection() as conn:
        user=account(conn,request,lock=True)
        row=daily_window(conn.execute('SELECT '+DAILY_COLUMNS+" FROM game_mode_runs r WHERE run_id=%s AND owner_id=%s AND mode='daily' FOR UPDATE",
                                     (run_id,user['account_id'])).fetchone())
        if not row:raise HTTPException(404,'Daily Challenge not found')
        now=now_ms(conn);s=row['state'];before=checkpoint(s);game.daily_tick(s,now)
        try:
            if command=='answer':game.daily_answer(s,body.position,body.option_id,str(body.request_id),now)
            if command=='next':game.solo.advance(s,body.previous,now)
            if command=='leave' and s['phase'] not in game.TERMINAL:s.update(phase='ABANDONED',finished_at=now,end_reason='resigned')
        except game.solo.SoloError as exc:failure=str(exc)
        persist(conn,row,now,before);result=daily_public(conn,row,now,user)
    if failure:raise HTTPException(409,failure)
    return result


@router.get('/api/daily/runs/{run_id}')
def daily_get(run_id:UUID,request:Request):return daily_action(run_id,request)


@router.post('/api/daily/runs/{run_id}/answers',dependencies=[Depends(same_origin)])
def daily_answer(run_id:UUID,body:Answer,request:Request):
    rate_limit(request,'daily-answer',120)
    return daily_action(run_id,request,'answer',body)


@router.post('/api/daily/runs/{run_id}/next',dependencies=[Depends(same_origin)])
def daily_next(run_id:UUID,body:Next,request:Request):return daily_action(run_id,request,'next',body)


@router.post('/api/daily/runs/{run_id}/leave',dependencies=[Depends(same_origin)])
def daily_leave(run_id:UUID,request:Request):return daily_action(run_id,request,'leave')


def friend_public(row,user,now):
    result={**game.penalty.view(row['state'],str(user['account_id']),now),'code':row['invite'],
            'run_id':str(row['run_id']),'difficulty':row['state']['difficulty'],'xp_saved':False,'is_guest':user['is_guest']}
    for shown,frozen in zip(result['players'],row['state']['players']):shown['is_guest']=frozen.get('is_guest',False)
    return result


def friend_identity(conn,request,*,response=None,create=False,lock=False):
    # Guests get the same opaque, HttpOnly browser identity used by Solo. Never
    # expose its generated trial username or turn it into a registered profile.
    if request.cookies.get(ACCOUNT_COOKIE):return account(conn,request,lock=lock)
    return trial_player(conn,request,response=response,create=create,lock=lock)


def replenish(conn,s,ids,now):
    used=used_questions(conn,ids,now)|{q['question_id'] for q in s['deck']}
    rows=[r for r in candidates(conn) if r['difficulty']==s['difficulty'] and str(r['question_id']) not in used]
    if not rows:return False
    s['deck'].extend(snapshots(conn,RANDOM.sample(rows,min(50,len(rows)))))
    return True


@router.post('/api/friends/rooms',dependencies=[Depends(same_origin)],status_code=201)
def friend_create(body:FriendStart,request:Request,response:Response):
    rate_limit(request,'friend-create',10)
    with get_connection() as conn:
        user=friend_identity(conn,request,response=response,create=True,lock=True);ident=user['account_id'];now=now_ms(conn)
        row=conn.execute('SELECT * FROM game_mode_runs WHERE owner_id=%s AND start_request_id=%s',(ident,body.request_id)).fetchone()
        if row:
            if row['mode']!='friend' or row['state']['difficulty']!=body.difficulty:raise HTTPException(409,'Request ID already used')
            return friend_public(row,user,now)
        ensure_free(conn,ident)
        s=game.friend_create(str(ident),'Friend' if user['is_guest'] else user['username'],body.difficulty,now)
        s['players'][0]['is_guest']=user['is_guest']
        s['first']=s['shooter']=secrets.randbelow(2)
        row=conn.execute('''INSERT INTO game_mode_runs(run_id,mode,owner_id,start_request_id,invite,state)
            VALUES(%s,'friend',%s,%s,%s,%s) RETURNING *''',(uuid4(),ident,body.request_id,secrets.token_urlsafe(32),Jsonb(s))).fetchone()
        conn.execute('INSERT INTO game_mode_members(run_id,account_id,seat) VALUES(%s,%s,0)',(row['run_id'],ident))
        return friend_public(row,user,now)


@router.get('/api/friends/active')
def friend_active(request:Request):
    with get_connection() as conn:
        user=friend_identity(conn,request)
        if not user:return {'code':None}
        row=conn.execute("""SELECT r.invite FROM game_mode_runs r JOIN game_mode_members m USING(run_id)
            WHERE m.account_id=%s AND m.active AND r.mode='friend'""",(user['account_id'],)).fetchone()
        return {'code':row['invite'] if row else None}


@router.get('/api/friends/invites/{code}')
def friend_invite(code:str,request:Request):
    with get_connection() as conn:
        user=friend_identity(conn,request)
        row=conn.execute("SELECT * FROM game_mode_runs WHERE invite=%s AND mode='friend'",(code,)).fetchone()
        if not row:raise HTTPException(404,'Invitation not found')
        member=user and conn.execute('SELECT 1 FROM game_mode_members WHERE run_id=%s AND account_id=%s',(row['run_id'],user['account_id'])).fetchone()
        now=now_ms(conn);s=row['state']
        return {'member':bool(member),'host':s['players'][0]['name'],'difficulty':s['difficulty'],
                'joinable':not member and s['phase']=='LOBBY' and len(s['players'])==1 and now-s['created_at']<s['rules']['max_match_ms']}


def friend_action(code,request,command='view',body=None,response=None):
    failure=None
    with get_connection() as conn:
        user=friend_identity(conn,request,response=response,create=command=='join')
        if not user:raise HTTPException(401,'Join this invitation first')
        ident=user['account_id'];pid=str(ident)
        row=conn.execute("SELECT * FROM game_mode_runs WHERE invite=%s AND mode='friend' FOR UPDATE",(code,)).fetchone()
        if not row:raise HTTPException(404,'Friend Duel not found')
        s=row['state'];before=checkpoint(s);member=any(p['id']==pid for p in s['players'])
        if not member and command!='join':raise HTTPException(403,'Join this invitation first')
        # Every route locks the match before participant accounts, in UUID order.
        # Solo/Daily only lock their own account, so cross-mode starts serialize.
        ids=sorted({UUID(p['id']) for p in s['players']}|{ident})
        conn.execute('SELECT account_id FROM game_accounts WHERE account_id=ANY(%s) ORDER BY account_id FOR UPDATE',(ids,)).fetchall()
        if not user['is_guest']:account(conn,request)
        now=now_ms(conn);mark_seen(conn,row,now);game.friend_tick(s,now)
        try:
            if command=='join' and not member:
                ensure_free(conn,ident)
                game.penalty.join(s,pid,'Friend' if user['is_guest'] else user['username'],now)
                s['players'][-1]['is_guest']=user['is_guest']
                conn.execute('INSERT INTO game_mode_members(run_id,account_id,seat) VALUES(%s,%s,1)',(row['run_id'],ident))
            if s['phase'] not in game.TERMINAL:
                player=next(p for p in s['players'] if p['id']==pid)
                if command!='view' or now-player['seen']>=4000:player['seen']=now
            if command=='ready' and s['phase']=='LOBBY':
                if len(s['players'])!=2:raise game.penalty.GameError('Wait for your friend to join')
                if not s['deck'] and not replenish(conn,s,ids,now):raise game.penalty.GameError('No unused questions at this difficulty for both players')
                game.penalty.ready(s,pid,now)
            if command=='answer':game.friend_submit(s,pid,body.position,body.option_id,str(body.request_id),now)
            if command=='leave' and s['phase'] not in game.TERMINAL:
                other=next((i for i,p in enumerate(s['players']) if p['id']!=pid),None)
                game.friend_finish(s,now,'resigned',other)
            if s['phase']=='RESOLVED' and now>=s['round']['next_at'] and all(now-p['seen']<8000 for p in s['players']):
                if s['cursor']>=len(s['deck']) and not replenish(conn,s,ids,now):game.friend_finish(s,now,'question_pool_exhausted')
                else:game.penalty.schedule(s,now)
        except (game.penalty.GameError,HTTPException) as exc:failure=exc
        persist(conn,row,now,before)
        result=friend_public(row,user,now) if any(p['id']==pid for p in s['players']) else None
    if failure:
        if isinstance(failure,HTTPException):raise failure
        raise HTTPException(409,str(failure))
    return result


@router.get('/api/friends/rooms/{code}')
def friend_get(code:str,request:Request):return friend_action(code,request)


@router.post('/api/friends/rooms/{code}/join',dependencies=[Depends(same_origin)])
def friend_join(code:str,request:Request,response:Response):
    rate_limit(request,'friend-join',20)
    return friend_action(code,request,'join',response=response)


@router.post('/api/friends/rooms/{code}/ready',dependencies=[Depends(same_origin)])
def friend_ready(code:str,request:Request):return friend_action(code,request,'ready')


@router.post('/api/friends/rooms/{code}/answers',dependencies=[Depends(same_origin)])
def friend_answer(code:str,body:Answer,request:Request):
    rate_limit(request,'friend-answer',120)
    return friend_action(code,request,'answer',body)


@router.post('/api/friends/rooms/{code}/leave',dependencies=[Depends(same_origin)])
def friend_leave(code:str,request:Request):return friend_action(code,request,'leave')
