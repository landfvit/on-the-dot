"""Account-authenticated solo quizzes, immutable evidence and atomic XP awards."""
from datetime import datetime,timezone
import secrets
from typing import Literal
from uuid import UUID,uuid4

from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import Field
from psycopg.types.json import Jsonb

from api.database import get_connection
from api import solo_engine as game
from api.numeric_choices import refresh as refresh_numeric_choices
from api.player_accounts import account,profile,xp_transition,COOKIE as ACCOUNT_COOKIE
from api.solo_trials import trial_player
from api.solo_history import week_window
from api import solo_topics as topics
from api.penalty_routes import rate_limit,now_ms
from api.trivia_models import StrictModel
from api.trivia_quizzes import same_origin

router=APIRouter(prefix='/api/solo',tags=['solo quizzes'])


class Start(StrictModel):
    category:str=Field(default='ALL',pattern=r'^[A-Z]{3}$')
    topic:topics.TopicCode='ALL'
    difficulty:Literal['easy','medium','hard']='easy'
    request_id:UUID


class Answer(StrictModel):
    position:int=Field(ge=1,le=10000)
    option_id:str=Field(pattern=r'^[0-3]$')
    request_id:UUID


class Next(StrictModel):
    previous:int=Field(ge=0,le=9999)


def latest_release(conn):
    row=conn.execute('SELECT release_id FROM penalty_bank_releases ORDER BY created_at DESC,release_id DESC LIMIT 1').fetchone()
    return row['release_id'] if row else None


def active_releases(conn):
    rows=conn.execute('''SELECT DISTINCT ON(v.batch_id) r.release_id
        FROM penalty_bank_releases r JOIN trivia_bank_validation_runs v ON v.run_id=r.validation_run_id
        ORDER BY v.batch_id,r.created_at DESC,r.release_id DESC''').fetchall()
    return [r['release_id'] for r in rows]


@router.get('/catalog')
def catalog(request:Request):
    with get_connection() as conn:
        user=account(conn,request) if request.cookies.get(ACCOUNT_COOKIE) else trial_player(conn,request)
        week,reset=week_window(now_ms(conn))
        rows=conn.execute('''SELECT p.section_code code,p.section_name label,d.difficulty,p.question->>'topic' source_topic,
            count(*) FILTER (WHERE h.question_id IS NULL) n
            FROM penalty_bank_questions p JOIN game_current_difficulty d USING(release_id,question_id)
            LEFT JOIN game_used_questions h ON h.question_id=p.question_id AND h.account_id=%s AND h.week_start=%s
            WHERE p.release_id=ANY(%s) AND d.approved AND p.question->>'topic'=ANY(%s)
            GROUP BY p.section_code,p.section_name,d.difficulty,p.question->>'topic' ORDER BY p.section_name''',
            (user['account_id'] if user and not user['is_guest'] else None,week,active_releases(conn),topics.sources('ALL'))).fetchall()
    categories={'ALL':{'code':'ALL','label':'All clubs','counts':dict.fromkeys(('easy','medium','hard'),0)}}
    topic_counts={code:{'code':code,'label':topics.label(code),'counts_by_team':{}} for code in topics.TOPICS}
    for row in rows:
        category=categories.setdefault(row['code'],{'code':row['code'],'label':row['label'],'counts':dict.fromkeys(('easy','medium','hard'),0)})
        category['counts'][row['difficulty']]+=row['n'];categories['ALL']['counts'][row['difficulty']]+=row['n']
        entry=topic_counts[topics.SOURCE_TOPIC[row['source_topic']]]['counts_by_team']
        for team in ('ALL',row['code']):
            entry.setdefault(team,dict.fromkeys(('easy','medium','hard'),0))[row['difficulty']]+=row['n']
    mixed={'code':'ALL','label':topics.label('ALL'),'counts_by_team':{code:c['counts'] for code,c in categories.items()}}
    return {'categories':list(categories.values()),'topics':[mixed,*topic_counts.values()],
            'rules':game.RULES,'week_start':week,'resets_at':reset}


@router.get('/history')
def history(request:Request):
    with get_connection() as conn:
        user=player_identity(conn,request)
        week,reset=week_window(now_ms(conn))
        days=conn.execute('''SELECT day,array_agg(question_id ORDER BY run_id,position) question_ids
            FROM game_used_questions WHERE account_id=%s AND week_start=%s GROUP BY day ORDER BY day''',
            (user['account_id'],week)).fetchall()
    return {'week_start':week,'resets_at':reset,'days':days}


def load_deck(conn,ident,body,now,size=10,exclude=()):
    week,reset=week_window(now)
    releases=active_releases(conn)
    candidates=conn.execute('''SELECT p.question_id,p.section_name,p.question->>'topic' source_topic,d.revision_id
        FROM penalty_bank_questions p
        JOIN game_current_difficulty d USING(release_id,question_id)
        WHERE p.release_id=ANY(%s) AND d.approved AND d.difficulty=%s AND (%s='ALL' OR p.section_code=%s)
        AND p.question->>'topic'=ANY(%s)
        AND NOT EXISTS(SELECT 1 FROM game_used_questions h
            WHERE h.account_id=%s AND h.week_start=%s AND h.question_id=p.question_id)
        ORDER BY p.question_id''',
        (releases,body.difficulty,body.category,body.category,topics.sources(body.topic),ident,week)).fetchall()
    candidates=[r for r in candidates if str(r['question_id']) not in exclude]
    rows=topics.balanced_sample(candidates,body.topic,size=size)
    if len(rows)!=size:
        raise HTTPException(409,f'No new shootout is available for this selection right now. Try a different difficulty or wait for the weekly reset: {reset:%Y-%m-%d %H:%M} UTC.')
    snapshots={r['question_id']:r for r in conn.execute('''SELECT question_id,release_id,question
        FROM penalty_bank_questions WHERE release_id=ANY(%s) AND question_id=ANY(%s)''',
        (releases,[r['question_id'] for r in rows])).fetchall()}
    deck=[]
    for row in rows:
        snapshot=snapshots[row['question_id']]
        q=refresh_numeric_choices(snapshot['question']);answer=next(o for o in q['options'] if o['id']==q['correct'])
        secrets.SystemRandom().shuffle(q['options'])
        for i,o in enumerate(q['options']):
            o['id']=str(i)
            if o is answer:q['correct']=str(i)
        q.update(release_id=str(snapshot['release_id']),question_id=str(row['question_id']),difficulty_revision=row['revision_id'],allocated_at=now)
        deck.append(q)
    return deck,{'code':body.category,'label':'All clubs' if body.category=='ALL' else rows[0]['section_name'],
                 'topic_code':body.topic,'topic_label':topics.label(body.topic)}


def persist(conn,row):
    s=row['state'];ident=row['account_id'];run=row['run_id']
    conn.execute('UPDATE game_solo_runs SET state=%s WHERE run_id=%s',(Jsonb(s),run))
    for answer in s['history']:
        q=s['deck'][answer['position']-1]
        conn.execute('''INSERT INTO game_solo_answers(run_id,position,request_id,release_id,question_id,difficulty_revision,
            option_id,correct,elapsed_ms,answered_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,to_timestamp(%s/1000.0))
            ON CONFLICT(run_id,position) DO NOTHING''',
            (run,answer['position'],answer['request_id'],q['release_id'],q['question_id'],q['difficulty_revision'],
             answer['option_id'],answer['correct'],answer['elapsed_ms'],answer['answered_at']))
        if answer['correct'] and not row['is_trial']:
            conn.execute("INSERT INTO game_xp_ledger VALUES(%s,%s,%s,%s,'correct_answer',DEFAULT) ON CONFLICT DO NOTHING",
                         (ident,run,answer['position'],s['rules']['xp_per_correct']))
    reward=game.rewards(s)
    if reward['bonus_xp'] and not row['is_trial']:
        reason='win_bonus' if s['rules'].get('bonus_mode')=='win' else 'perfect_bonus'
        conn.execute("INSERT INTO game_xp_ledger VALUES(%s,%s,0,%s,%s,DEFAULT) ON CONFLICT DO NOTHING",(ident,run,reward['bonus_xp'],reason))
    if reward['streak_eligible'] and not row['is_trial']:
        day=datetime.fromtimestamp(s['finished_at']/1000,timezone.utc).date()
        conn.execute('INSERT INTO game_daily_activity VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(ident,day,run))


def public(row,now):
    result={**game.view(row['state'],now),'run_id':str(row['run_id']),'is_trial':row['is_trial'],'xp_saved':not row['is_trial']}
    if row['is_trial']:result['streak_eligible']=False
    return result


def player_identity(conn,request):
    if request.cookies.get(ACCOUNT_COOKIE):return account(conn,request,lock=True)
    user=trial_player(conn,request,lock=True)
    if not user:raise HTTPException(401,'Start your free trial or sign in')
    return user


@router.post('/runs',dependencies=[Depends(same_origin)],status_code=201)
def start(body:Start,request:Request,response:Response):
    rate_limit(request,'solo-start',20)
    with get_connection() as conn:
        user=account(conn,request,lock=True) if request.cookies.get(ACCOUNT_COOKIE) else trial_player(conn,request,create=True,response=response,lock=True)
        ident=user['account_id'];now=now_ms(conn)
        row=conn.execute('SELECT * FROM game_solo_runs WHERE account_id=%s AND start_request_id=%s',(ident,body.request_id)).fetchone()
        if row:
            if (row['state']['category']['code']!=body.category or row['state']['difficulty']!=body.difficulty
                or row['state']['category'].get('topic_code','ALL')!=body.topic):
                raise HTTPException(409,'Request ID already used for another quiz')
            game.tick(row['state'],now);persist(conn,row);return public(row,now)
        active=conn.execute("SELECT * FROM game_solo_runs WHERE account_id=%s AND state->>'phase' NOT IN ('FINISHED','ABANDONED') FOR UPDATE",(ident,)).fetchone()
        if active:
            game.tick(active['state'],now);persist(conn,active)
            if active['state']['phase'] not in ('FINISHED','ABANDONED'):
                if active['state']['category'].get('topic_code','ALL')!=body.topic:
                    raise HTTPException(409,'Finish or end your active quiz before changing category.')
                return public(active,now)
        if conn.execute('SELECT 1 FROM game_mode_members WHERE account_id=%s AND active',(ident,)).fetchone():
            raise HTTPException(409,'Finish or leave your Daily Challenge or Friend Duel first.')
        deck,category=load_deck(conn,None if user['is_guest'] else ident,body,now)
        state=game.create(deck,body.difficulty,category,now)
        row=conn.execute('INSERT INTO game_solo_runs(run_id,account_id,start_request_id,state,is_trial) VALUES(%s,%s,%s,%s,%s) RETURNING *',
                         (uuid4(),ident,body.request_id,Jsonb(state),user['is_guest'])).fetchone()
        return public(row,now)


@router.get('/active')
def active(request:Request):
    with get_connection() as conn:
        if not request.cookies.get(ACCOUNT_COOKIE):
            user=trial_player(conn,request,lock=True)
            if not user:return {'run':None,'trial_available':True}
            row=conn.execute("SELECT * FROM game_solo_runs WHERE account_id=%s AND state->>'phase' NOT IN ('FINISHED','ABANDONED') FOR UPDATE",(user['account_id'],)).fetchone()
            if not row:return {'run':None,'trial_available':True}
            now=now_ms(conn);game.tick(row['state'],now);persist(conn,row)
            return {'run':public(row,now) if row['state']['phase'] not in ('FINISHED','ABANDONED') else None,'trial_available':True}
        user=account(conn,request,lock=True)
        row=conn.execute("SELECT * FROM game_solo_runs WHERE account_id=%s AND state->>'phase' NOT IN ('FINISHED','ABANDONED') FOR UPDATE",(user['account_id'],)).fetchone()
        if not row:return {'run':None}
        now=now_ms(conn);game.tick(row['state'],now);persist(conn,row)
        return {'run':public(row,now)}


def action(run_id,request,command='view',body=None):
    failure=None
    with get_connection() as conn:
        user=player_identity(conn,request)
        row=conn.execute('SELECT * FROM game_solo_runs WHERE run_id=%s AND account_id=%s FOR UPDATE',(run_id,user['account_id'])).fetchone()
        if not row:raise HTTPException(404,'Quiz not found')
        now=now_ms(conn);s=row['state'];game.tick(s,now)
        try:
            if command=='answer':game.answer(s,body.position,body.option_id,str(body.request_id),now)
            if command=='next':
                # Both locks are held: repeated clicks cannot allocate or score a pair twice.
                if (game.is_shootout(s) and s['phase']=='REVIEW' and
                    body.previous==s['position']==len(s['deck'])):
                    selection=Start(category=s['category']['code'],topic=s['category'].get('topic_code','ALL'),
                                    difficulty=s['difficulty'],request_id=uuid4())
                    try:
                        extra,_=load_deck(conn,None if user['is_guest'] else user['account_id'],selection,now,size=2,
                                         exclude={q['question_id'] for q in s['deck']})
                        s['deck'].extend(extra)
                    except HTTPException as exc:
                        if exc.status_code!=409:raise
                        # A finite approved pool cannot support infinitely many unique questions.
                        # Never fabricate a winner or substitute a different subject.
                        s.update(phase='ABANDONED',finished_at=now,end_reason='question_pool_exhausted')
                if s['phase']!='ABANDONED':game.advance(s,body.previous,now)
            if command=='leave' and s['phase'] not in ('FINISHED','ABANDONED'):s.update(phase='ABANDONED',finished_at=now)
        except game.SoloError as error:failure=str(error)
        persist(conn,row);result=public(row,now)
        # Terminal summary and XP balance share the award transaction. The UI
        # never estimates levels or races a second request against XP commits.
        if s['phase'] in ('FINISHED','ABANDONED') and not row['is_trial']:
            p=profile(conn,user)
            result['player_progress']={key:p[key] for key in ('total_xp','level','level_xp','next_level_xp')}
            result['xp_transition']=xp_transition(conn,user['account_id'],run_id,result['player_progress'])
    if failure:raise HTTPException(409,failure)
    return result


@router.get('/runs/{run_id}')
def get_run(run_id:UUID,request:Request):return action(run_id,request)


@router.post('/runs/{run_id}/answers',dependencies=[Depends(same_origin)])
def answer(run_id:UUID,body:Answer,request:Request):
    rate_limit(request,'solo-answer',120)
    return action(run_id,request,'answer',body)


@router.post('/runs/{run_id}/next',dependencies=[Depends(same_origin)])
def next_question(run_id:UUID,body:Next,request:Request):
    rate_limit(request,'solo-next',120)
    return action(run_id,request,'next',body)


@router.post('/runs/{run_id}/leave',dependencies=[Depends(same_origin)])
def leave(run_id:UUID,request:Request):return action(run_id,request,'leave')
