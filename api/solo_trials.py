"""A browser-bound trial identity is not a registered or publicly visible account."""
import hashlib
import os
import secrets
from uuid import uuid4

from fastapi import HTTPException

COOKIE='points_trial'


def trial_player(conn,request,*,create=False,response=None,lock=False):
    token=request.cookies.get(COOKIE)
    if token:
        if len(token)>100:token=''
        row=conn.execute('''SELECT a.* FROM game_accounts a JOIN game_sessions s USING(account_id)
            WHERE s.token_hash=%s AND s.expires_at>clock_timestamp() AND a.is_guest''',
            (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if row:
            if lock:conn.execute('SELECT 1 FROM game_accounts WHERE account_id=%s FOR UPDATE',(row['account_id'],))
            return row
    if not create:return None
    ident=uuid4();token=secrets.token_urlsafe(32)
    row=conn.execute('''INSERT INTO game_accounts(account_id,username,password_hash,is_guest)
        VALUES(%s,%s,'!',true) RETURNING *''',(ident,'trial_'+uuid4().hex[:18])).fetchone()
    conn.execute("INSERT INTO game_sessions(token_hash,account_id,expires_at) VALUES(%s,%s,clock_timestamp()+INTERVAL '365 days')",
                 (hashlib.sha256(token.encode()).hexdigest(),ident))
    response.set_cookie(COOKIE,token,max_age=365*86400,httponly=True,samesite='strict',path='/',
                        secure=request.url.scheme=='https' or os.getenv('TRIVIA_HTTPS_ONLY')=='1')
    return row
