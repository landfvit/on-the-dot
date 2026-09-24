"""Player accounts are separate from guest penalty identities and editor access."""
from datetime import datetime,timezone,timedelta
import hashlib
import hmac
import os
import secrets
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import Field,field_validator,EmailStr
from psycopg.errors import UniqueViolation

from api.database import get_connection
from api.penalty_routes import rate_limit
from api.solo_engine import streak
from api.trivia_models import StrictModel
from api.trivia_quizzes import same_origin
from api import account_email

router=APIRouter(prefix='/api/players',tags=['player accounts'])
COOKIE='points_account'


def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=32768,r=8,p=1,maxmem=64*1024*1024).hex()
    return 'scrypt-v1$'+salt+'$'+digest


def verify_password(password,stored):
    try:
        version,salt,_=stored.split('$')
        return version=='scrypt-v1' and hmac.compare_digest(password_hash(password,salt),stored)
    except (ValueError,TypeError):return False


DUMMY_HASH=password_hash('not-a-real-account-password')


class Credentials(StrictModel):
    username:str=Field(min_length=3,max_length=24,pattern=r'^[A-Za-z0-9_]+$')
    password:str=Field(min_length=8,max_length=128)

    @field_validator('username')
    @classmethod
    def normalized(cls,value):return value.lower()


class Registration(Credentials):
    email:EmailStr=Field(max_length=254)

    @field_validator('email')
    @classmethod
    def normalize_email(cls,value):return value.lower()


class Login(StrictModel):
    identifier:str=Field(min_length=3,max_length=254)
    password:str=Field(min_length=1,max_length=128)

    @field_validator('identifier')
    @classmethod
    def normalize_identifier(cls,value):return value.strip().lower()


class EmailUpdate(StrictModel):
    email:EmailStr=Field(max_length=254)
    password:str=Field(min_length=1,max_length=128)

    @field_validator('email')
    @classmethod
    def normalize_email(cls,value):return value.lower()


class ProfileEdit(StrictModel):
    bio:str=Field(default='',max_length=160)
    accent:Literal['green','pink','blue','gold']='green'
    username:str|None=Field(default=None,min_length=3,max_length=24,pattern=r'^[A-Za-z0-9_]+$')


class PasswordChange(StrictModel):
    current_password:str=Field(min_length=1,max_length=128)
    new_password:str=Field(min_length=8,max_length=128)


class AccountDeletion(StrictModel):
    password:str=Field(min_length=1,max_length=128)
    confirmation:Literal['DELETE']


class Preferences(StrictModel):
    animations:bool=True
    reduced_motion:bool=False


class ResetRequest(StrictModel):
    email:EmailStr=Field(max_length=254)


class ResetPassword(StrictModel):
    token:str=Field(min_length=43,max_length=43,pattern=r'^[A-Za-z0-9_-]+$')
    new_password:str=Field(min_length=8,max_length=128)


def check_username(username):
    username=username.lower()
    if username in {'admin','administrator','support','points','editor','system'} or username.startswith(('deleted_','trial_')):
        raise HTTPException(409,'This username is unavailable')
    return username


def private_profile(conn,row):
    now=conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
    next_change=row.get('club_changed_at')
    if next_change:next_change+=timedelta(hours=72)
    return {**profile(conn,row),'email':row['email'],
            'team_change':{'can_change':next_change is None or now>=next_change,'next_change_at':next_change},
            'preferences':{'animations':row['animations'],'reduced_motion':row['reduced_motion']}}


class ClubEdit(StrictModel):
    team_id:int|None=Field(default=None,gt=0)


def account(conn,request,lock=False):
    token=request.cookies.get(COOKIE,'')
    if not token or len(token)>100:raise HTTPException(401,'Sign in to play')
    row=conn.execute('''SELECT a.* FROM game_accounts a JOIN game_sessions s USING(account_id)
        WHERE s.token_hash=%s AND s.expires_at>clock_timestamp() AND NOT a.is_guest AND a.deleted_at IS NULL''',
        (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not row:raise HTTPException(401,'Your session has expired. Sign in again.')
    if lock:
        row=conn.execute('SELECT * FROM game_accounts WHERE account_id=%s AND deleted_at IS NULL FOR UPDATE',(row['account_id'],)).fetchone()
        if not row:raise HTTPException(401,'Your session has expired. Sign in again.')
        # Password changes revoke sessions while holding the same account lock.
        if not conn.execute('SELECT 1 FROM game_sessions WHERE token_hash=%s AND expires_at>clock_timestamp()',
                            (hashlib.sha256(token.encode()).hexdigest(),)).fetchone():
            raise HTTPException(401,'Your session has expired. Sign in again.')
    return row


def new_session(conn,ident,request,response):
    old=request.cookies.get(COOKIE)
    if old:conn.execute('DELETE FROM game_sessions WHERE token_hash=%s',(hashlib.sha256(old.encode()).hexdigest(),))
    token=secrets.token_urlsafe(32)
    conn.execute('DELETE FROM game_sessions WHERE expires_at<=clock_timestamp()')
    conn.execute('INSERT INTO game_sessions(token_hash,account_id) VALUES(%s,%s)',(hashlib.sha256(token.encode()).hexdigest(),ident))
    response.set_cookie(COOKIE,token,max_age=30*86400,httponly=True,samesite='strict',path='/',
                        secure=request.url.scheme=='https' or os.getenv('TRIVIA_HTTPS_ONLY')=='1')


def profile(conn,row):
    ident=row['account_id']
    total=conn.execute('SELECT COALESCE(sum(amount),0) xp FROM game_all_xp WHERE account_id=%s',(ident,)).fetchone()['xp']
    level=conn.execute('SELECT level,minimum_xp FROM game_levels WHERE minimum_xp<=%s ORDER BY minimum_xp DESC LIMIT 1',(total,)).fetchone()
    next_level=conn.execute('SELECT minimum_xp FROM game_levels WHERE minimum_xp>%s ORDER BY minimum_xp LIMIT 1',(total,)).fetchone()
    days=[r['day'] for r in conn.execute('SELECT day FROM game_all_activity WHERE account_id=%s ORDER BY day',(ident,)).fetchall()]
    now=conn.execute('SELECT clock_timestamp() AS now').fetchone()['now'].astimezone(timezone.utc)
    completed=conn.execute("SELECT count(*) n FROM game_solo_runs WHERE account_id=%s AND state->>'phase'='FINISHED'",(ident,)).fetchone()['n']
    club=conn.execute('SELECT team_id,name,season FROM game_clubs WHERE team_id=%s',(row.get('club_id'),)).fetchone()
    stats=conn.execute('''SELECT count(*) FILTER(WHERE won) wins,count(*) FILTER(WHERE NOT won) losses,
        count(*) played,round(100.0*count(*) FILTER(WHERE won)/NULLIF(count(*),0),1) win_rate
        FROM game_match_results WHERE account_id=%s''',(ident,)).fetchone()
    return {'username':row['username'],'bio':row['bio'],'accent':row['accent'],'total_xp':total,'club':club,'stats':stats,
            'level':level['level'],'level_xp':level['minimum_xp'],'next_level_xp':next_level['minimum_xp'] if next_level else None,
            'completed_quizzes':completed,'streak':streak(days,now.date()),
            'daily_reset':datetime.combine(now.date()+timedelta(days=1),datetime.min.time(),timezone.utc)}


@router.post('/register',dependencies=[Depends(same_origin)],status_code=201)
def register(body:Registration,request:Request,response:Response):
    rate_limit(request,'account-register',5)
    check_username(body.username)
    hashed=password_hash(body.password)
    try:
        with get_connection() as conn:
            row=conn.execute('INSERT INTO game_accounts(account_id,username,password_hash,email) VALUES(%s,%s,%s,%s) RETURNING *',
                             (uuid4(),body.username,hashed,body.email)).fetchone()
            new_session(conn,row['account_id'],request,response)
            return private_profile(conn,row)
    except UniqueViolation:raise HTTPException(409,'This username or email is unavailable')


@router.post('/login',dependencies=[Depends(same_origin)])
def login(body:Login,request:Request,response:Response):
    rate_limit(request,'account-login',8)
    with get_connection() as conn:
        row=conn.execute('''SELECT * FROM game_accounts WHERE NOT is_guest AND deleted_at IS NULL AND
            (email=%s OR (email IS NULL AND username=%s)) FOR UPDATE''',(body.identifier,body.identifier)).fetchone()
        valid=verify_password(body.password,row['password_hash'] if row else DUMMY_HASH)
        if not row or not valid:raise HTTPException(401,'Invalid email or password')
        new_session(conn,row['account_id'],request,response)
        return private_profile(conn,row)


@router.post('/logout',dependencies=[Depends(same_origin)])
def logout(request:Request,response:Response):
    with get_connection() as conn:
        conn.execute('DELETE FROM game_sessions WHERE token_hash=%s',(hashlib.sha256(request.cookies.get(COOKIE,'').encode()).hexdigest(),))
    response.delete_cookie(COOKIE,path='/');return {'signed_out':True}


@router.get('/me')
def me(request:Request):
    with get_connection() as conn:
        row=account(conn,request);return private_profile(conn,row)


@router.get('/teams')
def clubs():
    with get_connection() as conn:
        return {'teams':conn.execute('SELECT team_id,name,season FROM game_clubs ORDER BY name').fetchall()}


@router.put('/me/team',dependencies=[Depends(same_origin)])
def join_club(body:ClubEdit,request:Request):
    rate_limit(request,'account-team',20)
    with get_connection() as conn:
        row=account(conn,request,lock=True)
        if body.team_id is not None and not conn.execute('SELECT 1 FROM game_clubs WHERE team_id=%s',(body.team_id,)).fetchone():
            raise HTTPException(422,'Select a Premier League team from the list')
        if body.team_id==row['club_id']:
            return private_profile(conn,row)
        now=conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
        next_change=row.get('club_changed_at')
        if next_change and now<next_change+timedelta(hours=72):
            available=(next_change+timedelta(hours=72)).astimezone(timezone.utc)
            raise HTTPException(409,f'You can change teams again on {available:%d %b %Y at %H:%M} UTC.')
        row=conn.execute('UPDATE game_accounts SET club_id=%s WHERE account_id=%s RETURNING *',(body.team_id,row['account_id'])).fetchone()
        return private_profile(conn,row)


@router.patch('/me',dependencies=[Depends(same_origin)])
def edit_profile(body:ProfileEdit,request:Request):
    rate_limit(request,'account-edit',20)
    try:
        with get_connection() as conn:
            row=account(conn,request,lock=True)
            username=check_username(body.username) if body.username is not None else row['username']
            row=conn.execute('UPDATE game_accounts SET bio=%s,accent=%s,username=%s WHERE account_id=%s RETURNING *',
                             (body.bio.strip(),body.accent,username,row['account_id'])).fetchone()
            return private_profile(conn,row)
    except UniqueViolation:raise HTTPException(409,'This username is unavailable')


@router.put('/email',dependencies=[Depends(same_origin)])
def update_email(body:EmailUpdate,request:Request,response:Response):
    rate_limit(request,'account-email',5)
    try:
        with get_connection() as conn:
            row=account(conn,request,lock=True)
            # Re-read under the account lock before changing a login identity.
            row=conn.execute('SELECT * FROM game_accounts WHERE account_id=%s',(row['account_id'],)).fetchone()
            if not verify_password(body.password,row['password_hash']):raise HTTPException(401,'Incorrect password')
            row=conn.execute('UPDATE game_accounts SET email=%s WHERE account_id=%s RETURNING *',(body.email,row['account_id'])).fetchone()
            conn.execute('DELETE FROM game_sessions WHERE account_id=%s',(row['account_id'],))
            conn.execute('DELETE FROM game_password_resets WHERE account_id=%s',(row['account_id'],))
            new_session(conn,row['account_id'],request,response)
            return private_profile(conn,row)
    except UniqueViolation:raise HTTPException(409,'This email is unavailable')


@router.get('/profiles/{username}')
def public_profile(username:str):
    if len(username)>24:raise HTTPException(404,'Player not found')
    with get_connection() as conn:
        row=conn.execute('SELECT * FROM game_accounts WHERE username=%s AND NOT is_guest AND deleted_at IS NULL',(username.lower(),)).fetchone()
        if not row:raise HTTPException(404,'Player not found')
        return profile(conn,row)


@router.get('/settings')
def settings():
    return {'password_reset_available':account_email.reset_enabled()}


@router.put('/password',dependencies=[Depends(same_origin)])
def change_password(body:PasswordChange,request:Request,response:Response):
    rate_limit(request,'account-password',5)
    with get_connection() as conn:
        row=account(conn,request,lock=True)
        if not verify_password(body.current_password,row['password_hash']):raise HTTPException(401,'Incorrect current password')
        conn.execute('UPDATE game_accounts SET password_hash=%s WHERE account_id=%s',(password_hash(body.new_password),row['account_id']))
        conn.execute('DELETE FROM game_sessions WHERE account_id=%s',(row['account_id'],))
        conn.execute('DELETE FROM game_password_resets WHERE account_id=%s',(row['account_id'],))
        new_session(conn,row['account_id'],request,response)
    return {'changed':True}


@router.put('/preferences',dependencies=[Depends(same_origin)])
def preferences(body:Preferences,request:Request):
    rate_limit(request,'account-preferences',30)
    with get_connection() as conn:
        row=account(conn,request,lock=True)
        conn.execute('UPDATE game_accounts SET animations=%s,reduced_motion=%s WHERE account_id=%s',
                     (body.animations,body.reduced_motion,row['account_id']))
    return body.model_dump()


@router.delete('/me',dependencies=[Depends(same_origin)])
def delete_account(body:AccountDeletion,request:Request,response:Response):
    rate_limit(request,'account-delete',5)
    with get_connection() as conn:
        row=account(conn,request,lock=True)
        if not verify_password(body.password,row['password_hash']):raise HTTPException(401,'Incorrect password')
        conn.execute('DELETE FROM game_sessions WHERE account_id=%s',(row['account_id'],))
        conn.execute('DELETE FROM game_password_resets WHERE account_id=%s',(row['account_id'],))
        conn.execute("""UPDATE game_accounts SET username=%s,email=NULL,password_hash='!',bio='',club_id=NULL,
            accent='green',animations=true,reduced_motion=false,deleted_at=clock_timestamp() WHERE account_id=%s""",
            ('deleted_'+secrets.token_hex(8),row['account_id']))
    response.delete_cookie(COOKIE,path='/')
    return {'deleted':True}


@router.post('/password-reset/request',dependencies=[Depends(same_origin)],status_code=202)
def request_reset(body:ResetRequest,request:Request):
    rate_limit(request,'password-reset-request',5)
    if not account_email.reset_enabled():raise HTTPException(503,'Password recovery is not available yet')
    message={'message':'If an account uses this email, a reset link will arrive shortly.'}
    token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
    with get_connection() as conn:
        row=conn.execute('SELECT * FROM game_accounts WHERE email=%s AND NOT is_guest AND deleted_at IS NULL FOR UPDATE',
                         (str(body.email).lower(),)).fetchone()
        if not row:return message
        if conn.execute("SELECT 1 FROM game_password_resets WHERE account_id=%s AND created_at>clock_timestamp()-INTERVAL '1 minute'",(row['account_id'],)).fetchone():return message
        conn.execute('DELETE FROM game_password_resets WHERE account_id=%s',(row['account_id'],))
        conn.execute('INSERT INTO game_password_resets(token_hash,account_id) VALUES(%s,%s)',(digest,row['account_id']))
    try:account_email.send_reset(row['email'],token)
    except (RuntimeError,account_email.requests.RequestException):
        with get_connection() as conn:conn.execute('DELETE FROM game_password_resets WHERE token_hash=%s',(digest,))
        # Same response for unknown addresses and delivery failures; no tokens
        # or recipient addresses in logs. Monitor aggregate failures only.
        import logging
        logging.getLogger(__name__).warning('Password reset delivery failed')
    return message


@router.post('/password-reset/confirm',dependencies=[Depends(same_origin)])
def confirm_reset(body:ResetPassword,request:Request,response:Response):
    rate_limit(request,'password-reset-confirm',10)
    digest=hashlib.sha256(body.token.encode()).hexdigest()
    with get_connection() as conn:
        reset=conn.execute('SELECT account_id FROM game_password_resets WHERE token_hash=%s',(digest,)).fetchone()
        if not reset:raise HTTPException(400,'Reset link is invalid or expired')
        # Account first, then reset token: consistent lock ordering with change,
        # email edits and deletion, and only one concurrent reset can succeed.
        row=conn.execute('SELECT * FROM game_accounts WHERE account_id=%s AND deleted_at IS NULL AND NOT is_guest FOR UPDATE',
                         (reset['account_id'],)).fetchone()
        valid=conn.execute('SELECT 1 FROM game_password_resets WHERE token_hash=%s AND expires_at>clock_timestamp() FOR UPDATE',(digest,)).fetchone()
        if not row or not valid:raise HTTPException(400,'Reset link is invalid or expired')
        conn.execute('UPDATE game_accounts SET password_hash=%s WHERE account_id=%s',(password_hash(body.new_password),row['account_id']))
        conn.execute('DELETE FROM game_password_resets WHERE account_id=%s',(row['account_id'],))
        conn.execute('DELETE FROM game_sessions WHERE account_id=%s',(row['account_id'],))
    response.delete_cookie(COOKIE,path='/')
    return {'changed':True}
