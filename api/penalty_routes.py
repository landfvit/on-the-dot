"""Private guest-authenticated games; PostgreSQL serialises every room transition."""
import asyncio
from datetime import datetime,timezone
import hashlib
import secrets
from urllib.parse import urlsplit
from uuid import UUID,uuid4

from fastapi import APIRouter,Depends,HTTPException,Request,Response,WebSocket,WebSocketDisconnect
from pydantic import Field
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool
from typing import Literal

from api.database import get_connection
from api.trivia_models import StrictModel
from api.trivia_quizzes import same_origin
from api import penalty_engine as game
from api.penalty_questions import library_pack
from api.penalty_bank import catalog,load_pack

router=APIRouter(prefix='/api/penalties',tags=['penalty games'])
COOKIE='points_player'


def persist(conn,row,state):
    for event in state['history']:
        conn.execute('INSERT INTO pvp_penalties(match_id,penalty_id,snapshot) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
            (row['match_id'],event['id'],Jsonb(event)))
    conn.execute('UPDATE pvp_matches SET state=%s WHERE match_id=%s',(Jsonb(state),row['match_id']))


def sweep_rooms():
    """No client heartbeat is invented by the timer worker; safe across processes."""
    with get_connection() as conn:
        rows=conn.execute("""SELECT * FROM pvp_matches WHERE state->>'phase' NOT IN ('FINISHED','ABANDONED')
            ORDER BY created_at LIMIT 100 FOR UPDATE SKIP LOCKED""").fetchall()
        for row in rows:
            state=row['state'];game.tick(state,now_ms(conn));persist(conn,row,state)


class Identity(StrictModel):
    name:str=Field(min_length=1,max_length=32)


class NewGame(StrictModel):
    mode:Literal['solo','pvp']='solo'
    pack:str=Field(default='general',max_length=60,pattern=r'^(?:maths|library|general|bank:[0-9a-f-]{36}:[A-Z]{3})$')


class Answer(StrictModel):
    penalty_id:int=Field(gt=0)
    option_id:str=Field(pattern=r'^[0-3]$')
    request_id:UUID


def rate_limit(request:Request,bucket:str,maximum:int):
    host=request.client.host if request.client else 'local'
    key=hashlib.sha256((bucket+':'+host).encode()).hexdigest()
    with get_connection() as conn:
        row=conn.execute('''INSERT INTO pvp_rate_limits(key,bucket_start,count) VALUES (%s,date_trunc('minute',clock_timestamp()),1)
            ON CONFLICT(key,bucket_start) DO UPDATE SET count=pvp_rate_limits.count+1 RETURNING count''',(key,)).fetchone()
        conn.execute("DELETE FROM pvp_rate_limits WHERE bucket_start<clock_timestamp()-INTERVAL '10 minutes'")
    if row['count']>maximum:raise HTTPException(429,'Too many requests. Try again shortly.',headers={'Retry-After':'60'})


def player(conn,token):
    if not token:raise HTTPException(401,'Choose a player name first')
    row=conn.execute('SELECT * FROM pvp_players WHERE token_hash=%s AND expires_at>clock_timestamp()',
        (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not row:raise HTTPException(401,'Player session expired')
    return row


@router.post('/session',dependencies=[Depends(same_origin)])
def session(body:Identity,request:Request,response:Response):
    rate_limit(request,'session',20)
    name=body.name.strip()
    if not name:raise HTTPException(422,'Enter a player name')
    with get_connection() as conn:
        try:
            existing=player(conn,request.cookies.get(COOKIE))
            conn.execute('UPDATE pvp_players SET name=%s WHERE player_id=%s',(name,existing['player_id']))
            return {'name':name}
        except HTTPException:pass
        token=secrets.token_urlsafe(32)
        conn.execute('INSERT INTO pvp_players(player_id,token_hash,name) VALUES (%s,%s,%s)',
            (uuid4(),hashlib.sha256(token.encode()).hexdigest(),name))
    response.set_cookie(COOKIE,token,max_age=30*86400,httponly=True,samesite='strict',
        secure=request.url.scheme=='https',path='/api/penalties')
    return {'name':name}


@router.get('/session')
def current_session(request:Request):
    with get_connection() as conn:
        p=player(conn,request.cookies.get(COOKIE));return {'name':p['name']}


@router.get('/packs')
def packs():
    with get_connection() as conn:
        bank=catalog(conn);count=len(library_pack(conn))
    return {'packs':bank+[{'id':'maths','label':'Football maths · practice questions','count':80,'group':'Practice','language':'EN'},
        {'id':'library','label':'Verified ON THE DOT. questions','count':count,'group':'Other packs'}],
        'minimum':{'solo':1,'pvp':40}}


def now_ms(conn):
    return conn.execute('SELECT floor(extract(epoch FROM clock_timestamp())*1000)::bigint AS now').fetchone()['now']


@router.post('/rooms',dependencies=[Depends(same_origin)],status_code=201)
def create_room(body:NewGame,request:Request):
    if body.mode=='solo':raise HTTPException(410,'Solo quizzes are now penalties. Start at /penalties.')
    rate_limit(request,'create',10)
    with get_connection() as conn:
        p=player(conn,request.cookies.get(COOKIE))
        pack,label,deck=load_pack(conn,body.pack)
        minimum=1 if body.mode=='solo' else 40
        if len(deck)<minimum:raise HTTPException(409,f'This pack needs at least {minimum} distinct approved questions; it has {len(deck)}.')
        ident=uuid4();code=secrets.token_hex(5).upper()
        state=game.create(body.mode,str(p['player_id']),p['name'],deck,now_ms(conn),secrets.randbelow(2))
        state['pack_label']=label
        conn.execute('INSERT INTO pvp_matches(match_id,room_code,host_id,pack,state) VALUES (%s,%s,%s,%s,%s)',
            (ident,code,p['player_id'],pack,Jsonb(state)))
    return {'code':code,'mode':body.mode}


def room_action(code,token,action='view',payload=None):
    failure=None
    with get_connection() as conn:
        p=player(conn,token);pid=str(p['player_id'])
        row=conn.execute('SELECT * FROM pvp_matches WHERE room_code=%s FOR UPDATE',(code.upper(),)).fetchone()
        if not row:raise HTTPException(404,'Room not found')
        state=row['state'];now=now_ms(conn)
        member=any(x['id']==pid for x in state['players'])
        if not member and action!='join':raise HTTPException(403,'You are not a member of this room')
        game.tick(state,now)
        try:
            if action=='join':game.join(state,pid,p['name'],now)
            next(x for x in state['players'] if x['id']==pid)['seen']=now
            if action=='ready':game.ready(state,pid,now)
            if action=='next':
                if state['mode']!='solo' or state['phase']!='RESOLVED':raise game.GameError('Only solo results can be skipped')
                game.schedule(state,now)
            if action=='leave' and state['phase'] not in ('FINISHED','ABANDONED'):
                other=next((i for i,x in enumerate(state['players']) if x['id']!=pid),None)
                game.finish(state,'FINISHED' if other is not None else 'ABANDONED','resigned',other)
            if action=='answer':
                previous=conn.execute('SELECT penalty_id,answer FROM pvp_answers WHERE match_id=%s AND player_id=%s AND request_id=%s',
                    (row['match_id'],p['player_id'],payload.request_id)).fetchone()
                if previous:
                    if previous['penalty_id']!=payload.penalty_id or previous['answer']['option_id']!=payload.option_id:
                        raise game.GameError('Request ID was already used for a different answer')
                elif game.submit(state,pid,payload.penalty_id,payload.option_id,str(payload.request_id),now):
                    answer=state['round']['answers'][pid]
                    conn.execute('INSERT INTO pvp_answers VALUES (%s,%s,%s,%s,%s)',
                        (row['match_id'],payload.penalty_id,p['player_id'],payload.request_id,Jsonb(answer)))
        except game.GameError as error:failure=str(error)
        persist(conn,row,state)
        if failure:
            result=None
        else:
            result=game.view(state,pid,now);result.update(code=row['room_code'],pack=row['pack'],
                pack_label=('Football maths · practice questions' if row['pack']=='maths' else 'Verified ON THE DOT. questions' if row['pack']=='library' else state.get('pack_label', 'Premier League')))
            if row['pack']=='maths' and result['question']:
                from api.penalty_questions import english_maths_view
                question=state['deck'][state['round']['question_index']]
                result['question']=english_maths_view(result['question'],question['key'])
    if failure:raise HTTPException(409,failure)
    return result


@router.post('/rooms/{code}/join',dependencies=[Depends(same_origin)])
def join_room(code:str,request:Request):
    rate_limit(request,'join',20)
    return room_action(code,request.cookies.get(COOKIE),'join')


@router.get('/rooms/{code}')
def get_room(code:str,request:Request):
    return room_action(code,request.cookies.get(COOKIE))


@router.post('/rooms/{code}/ready',dependencies=[Depends(same_origin)])
def ready_room(code:str,request:Request):
    rate_limit(request,'commands',60)
    return room_action(code,request.cookies.get(COOKIE),'ready')


@router.post('/rooms/{code}/leave',dependencies=[Depends(same_origin)])
def leave_room(code:str,request:Request):
    rate_limit(request,'commands',60)
    return room_action(code,request.cookies.get(COOKIE),'leave')


@router.post('/rooms/{code}/answers',dependencies=[Depends(same_origin)])
def answer_room(code:str,body:Answer,request:Request):
    rate_limit(request,'answers',120)
    return room_action(code,request.cookies.get(COOKIE),'answer',body)


@router.post('/rooms/{code}/next',dependencies=[Depends(same_origin)])
def next_solo(code:str,request:Request):
    rate_limit(request,'commands',60)
    return room_action(code,request.cookies.get(COOKIE),'next')


@router.post('/rooms/{code}/rematch',dependencies=[Depends(same_origin)])
def rematch(code:str,request:Request):
    rate_limit(request,'create',10)
    with get_connection() as conn:
        p=player(conn,request.cookies.get(COOKIE));pid=str(p['player_id'])
        row=conn.execute('SELECT * FROM pvp_matches WHERE room_code=%s FOR UPDATE',(code.upper(),)).fetchone()
        if not row or pid not in {x['id'] for x in row['state']['players']}:raise HTTPException(403,'Not a room participant')
        old=row['state']
        if old['mode']=='solo':raise HTTPException(410,'Start a new solo shootout at /penalties.')
        if old['phase'] not in ('FINISHED','ABANDONED'):raise HTTPException(409,'Finish the current game first')
        if old.get('rematch_code'):return {'code':old['rematch_code']}
        pack,label,deck=load_pack(conn,row['pack'])
        if len(deck)<(1 if old['mode']=='solo' else 40):raise HTTPException(409,'Not enough approved questions for a rematch')
        new_code=secrets.token_hex(5).upper();now=now_ms(conn)
        state=game.create(old['mode'],pid,p['name'],deck,now,secrets.randbelow(2))
        state['pack_label']=label
        # Reserve both authenticated participants. Both must confirm ready again.
        for participant in old['players']:
            if participant['id']!=pid:game.join(state,participant['id'],participant['name'],now)
        conn.execute('INSERT INTO pvp_matches(match_id,room_code,host_id,pack,state) VALUES(%s,%s,%s,%s,%s)',
            (uuid4(),new_code,p['player_id'],row['pack'],Jsonb(state)))
        old['rematch_code']=new_code
        conn.execute('UPDATE pvp_matches SET state=%s WHERE match_id=%s',(Jsonb(old),row['match_id']))
    return {'code':new_code}


@router.websocket('/rooms/{code}/live')
async def live(ws:WebSocket,code:str):
    origin=urlsplit(ws.headers.get('origin',''))
    expected_scheme='https' if ws.url.scheme=='wss' else 'http'
    if origin.scheme!=expected_scheme or origin.netloc!=ws.url.netloc:
        await ws.close(code=1008);return
    token=ws.cookies.get(COOKIE)
    try:
        await run_in_threadpool(rate_limit,ws,'socket',30)
        initial=await run_in_threadpool(room_action,code,token)
    except HTTPException:
        await ws.close(code=1008);return
    await ws.accept()
    try:
        await ws.send_json(initial)
        snapshot=initial
        while True:
            # This stream sends committed snapshots only. Commands use CSRF-checked HTTP.
            try:
                delay=.75
                if snapshot['phase']=='COUNTDOWN':
                    delay=max(.01,min(delay,(snapshot['round']['opens_at']-snapshot['server_now'])/1000))
                message=await asyncio.wait_for(ws.receive(),timeout=delay)
                if message['type']=='websocket.disconnect':break
                await ws.close(code=1008);break
            except asyncio.TimeoutError:
                snapshot=await run_in_threadpool(room_action,code,token)
                await ws.send_json(snapshot)
    except (WebSocketDisconnect,HTTPException,RuntimeError):
        return
