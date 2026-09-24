"""Private, consent-based friendships. Guest games never create friendships."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from api.database import get_connection
from api.player_accounts import account
from api.penalty_routes import rate_limit, now_ms
from api.trivia_models import StrictModel
from api.trivia_quizzes import same_origin

router=APIRouter(prefix='/api/players/friends',tags=['friends'])


class AddFriend(StrictModel):
    username:str=Field(min_length=3,max_length=24,pattern=r'^[A-Za-z0-9_]+$')


class Invite(StrictModel):
    run_id:UUID


def pair(conn,request,username):
    user=account(conn,request)
    other=conn.execute('''SELECT account_id,username FROM game_accounts
        WHERE username=%s AND NOT is_guest AND deleted_at IS NULL''',(username.lower(),)).fetchone()
    if not other:raise HTTPException(404,'Player not found')
    if user['account_id']==other['account_id']:raise HTTPException(400,'Choose another player')
    ids=sorted([user['account_id'],other['account_id']])
    return user,other,ids


@router.get('')
def friends(request:Request):
    with get_connection() as conn:
        user=account(conn,request);ident=user['account_id'];now=now_ms(conn)
        rows=conn.execute('''SELECT f.*,a.username,r.invite,r.state
            FROM game_friendships f JOIN game_accounts a ON a.account_id=
              CASE WHEN f.account_a=%s THEN f.account_b ELSE f.account_a END
            LEFT JOIN game_mode_runs r ON r.run_id=f.invite_run
            WHERE %s IN(f.account_a,f.account_b) AND NOT a.is_guest AND a.deleted_at IS NULL
            ORDER BY f.created_at DESC''',(ident,ident)).fetchall()
        return {'friends':[{'username':r['username'],'status':r['status'],
            'incoming':r['requested_by']!=ident,
            'invite':('/friends/'+r['invite']) if r['status']=='accepted' and r['invited_by']!=ident
                and r['state'] and r['state']['phase']=='LOBBY' and len(r['state']['players'])==1
                and now-r['state']['created_at']<r['state']['rules']['max_match_ms'] else None} for r in rows]}


@router.post('',dependencies=[Depends(same_origin)])
def add_friend(body:AddFriend,request:Request):
    rate_limit(request,'add-friend',10)
    with get_connection() as conn:
        user,other,ids=pair(conn,request,body.username)
        # Sorted account locks serialize crossed requests and the list cap.
        conn.execute('SELECT account_id FROM game_accounts WHERE account_id=ANY(%s) ORDER BY account_id FOR UPDATE',(ids,)).fetchall()
        existing=conn.execute('SELECT status FROM game_friendships WHERE account_a=%s AND account_b=%s',ids).fetchone()
        if existing:return {'status':existing['status']}
        for ident in ids:
            n=conn.execute('SELECT count(*) n FROM game_friendships WHERE %s IN(account_a,account_b)',(ident,)).fetchone()['n']
            if n>=100:raise HTTPException(409,'Friend list limit reached')
        conn.execute('INSERT INTO game_friendships(account_a,account_b,requested_by) VALUES(%s,%s,%s)',(*ids,user['account_id']))
        return {'status':'pending'}


@router.post('/{username}/accept',dependencies=[Depends(same_origin)])
def accept_friend(username:str,request:Request):
    with get_connection() as conn:
        user,other,ids=pair(conn,request,username)
        row=conn.execute('SELECT * FROM game_friendships WHERE account_a=%s AND account_b=%s FOR UPDATE',ids).fetchone()
        if not row:raise HTTPException(404,'Request not found')
        if row['status']=='accepted':return {'status':'accepted'}
        if row['requested_by']==user['account_id']:raise HTTPException(403,'Only the recipient can accept')
        conn.execute("UPDATE game_friendships SET status='accepted',accepted_at=now() WHERE account_a=%s AND account_b=%s",ids)
        return {'status':'accepted'}


@router.delete('/{username}',dependencies=[Depends(same_origin)])
def remove_friend(username:str,request:Request):
    with get_connection() as conn:
        _,_,ids=pair(conn,request,username)
        conn.execute('DELETE FROM game_friendships WHERE account_a=%s AND account_b=%s',ids)
        return {'removed':True}


@router.post('/{username}/invite',dependencies=[Depends(same_origin)])
def invite_friend(username:str,body:Invite,request:Request):
    rate_limit(request,'invite-friend',15)
    with get_connection() as conn:
        user,_,ids=pair(conn,request,username)
        row=conn.execute("SELECT * FROM game_mode_runs WHERE run_id=%s AND owner_id=%s AND mode='friend' FOR UPDATE",(body.run_id,user['account_id'])).fetchone()
        if not row or row['state']['phase']!='LOBBY' or len(row['state']['players'])!=1 or now_ms(conn)-row['state']['created_at']>=row['state']['rules']['max_match_ms']:
            raise HTTPException(409,'Create a new invitation first')
        changed=conn.execute("UPDATE game_friendships SET invite_run=%s,invited_by=%s WHERE account_a=%s AND account_b=%s AND status='accepted'",(body.run_id,user['account_id'],*ids)).rowcount
        if not changed:raise HTTPException(403,'Accept the friend request first')
        return {'url':'/friends/'+row['invite']}
