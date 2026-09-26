"""Opt-in rich links: scores come from persisted games, never from the client."""
import json
import os
import secrets
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from PIL import Image, ImageDraw, ImageFont
from psycopg.types.json import Jsonb
from api.database import get_connection
from api.player_accounts import account, COOKIE as ACCOUNT_COOKIE
from api.solo_trials import trial_player
from api.penalty_routes import rate_limit
from api.trivia_models import StrictModel
from api.trivia_quizzes import same_origin
from api import solo_engine, challenge_engine

router=APIRouter(tags=['result links'])
ROOT=Path(__file__).resolve().parents[1]


def public_origin():
    # Do not build public links from an untrusted Host/X-Forwarded-Host header.
    value=(os.getenv('PUBLIC_SITE_URL') or 'https://onthedot.gg').rstrip('/')
    parsed=urlsplit(value)
    if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.path or parsed.query or parsed.fragment:
        raise RuntimeError('PUBLIC_SITE_URL must be an absolute site origin')
    return value


class Publish(StrictModel):
    mode:Literal['solo','daily','friend']='solo'
    run_id:UUID


def snapshot(conn,body,user):
    ident=user['account_id']
    if body.mode=='solo':
        row=conn.execute('SELECT state FROM game_solo_runs WHERE run_id=%s AND account_id=%s',(body.run_id,ident)).fetchone()
    else:
        row=conn.execute('''SELECT r.state,m.seat FROM game_mode_runs r JOIN game_mode_members m USING(run_id)
            WHERE r.run_id=%s AND r.mode=%s AND m.account_id=%s''',(body.run_id,body.mode,ident)).fetchone()
    if not row:raise HTTPException(404,'Result not found')
    s=row['state']
    if s['phase'] not in ('FINISHED','ABANDONED'):raise HTTPException(409,'Finish the game before sharing')
    player='Guest' if user['is_guest'] else user['username']
    opponent='Opponent';attempts=[[],[]]
    if body.mode=='friend':
        me=row['seat'];other=1-me
        opponent=s['players'][other]['name'] if len(s['players'])>other else 'Friend'
        score=[s['score'][me],s['score'][other]];correct=s['stats'][me]['correct'];xp=0
        won=s['winner']==me
        for r in s['history']:
            if r['outcome']!='replay':attempts[0 if r['shooter']==me else 1].append(r['outcome']=='goal')
    else:
        result=challenge_engine.daily_view(s,s['finished_at']) if body.mode=='daily' else solo_engine.view(s,s['finished_at'])
        sh=result.get('shootout',{})
        score=[sh.get('player',0),sh.get('opponent',0)];correct=result['correct'];xp=result['total_xp'];won=result['won']
        for a in sh.get('attempts',[]):attempts[0 if a['side']=='player' else 1].append(a['goal'])
    status='Won' if won else 'Ended' if s['phase']=='ABANDONED' else 'Lost'
    if body.mode=='friend' and s['winner'] is None:status='Ended'
    reason={'resigned':'Forfeit','disconnect_forfeit':'Connection forfeit','inactivity':'Inactivity',
            'daily_pool_exhausted':'Daily pool completed','daily_reset':'Daily reset',
            'question_pool_exhausted':'Question pool exhausted','time_limit':'Session expired'}.get(s.get('reason') or s.get('end_reason'),'')
    label={'solo':'Solo penalties','daily':'Daily Challenge','friend':'Friend Duel'}[body.mode]
    if body.mode=='daily' and challenge_engine.daily_survival(s):
        ranked=s['rules']['ranked']
        return dict(player=player,opponent='',score=[correct,0],correct=correct,total=len(s['history']),
            xp=xp,guest=False,mode='daily',format='daily_survival',ranked=ranked,difficulty=s['difficulty'],
            status='Daily score' if ranked else 'Practice',label='Daily Challenge',reason=reason,
            attempts=[[],[]],title=f'{player}: {correct} goals | ON THE DOT.',
            description=f'Daily Challenge · {correct} goals · {len(s["history"])-correct} lives lost'+(' · Practice (not ranked)' if not ranked else ''))
    # Explicit allowlist. The persisted question deck and answer history must
    # never enter a public snapshot, HTML response or social crawler image.
    return dict(player=player,opponent=opponent,score=score,correct=correct,total=len(s['history']),
        xp=xp,guest=bool(user['is_guest']),mode=body.mode,difficulty=s['difficulty'],status=status,
        label=label,reason=reason,attempts=attempts,title=f'{player} {score[0]} : {score[1]} {opponent} | ON THE DOT.',
        description=f'{label} · {status}{" · "+reason if reason else ""} · {correct}/{len(s["history"])} correct answers')


@router.post('/api/shares/results',dependencies=[Depends(same_origin)])
def publish(body:Publish,request:Request):
    rate_limit(request,'share-result',20)
    with get_connection() as conn:
        user=account(conn,request) if request.cookies.get(ACCOUNT_COOKIE) else trial_player(conn,request)
        if not user:raise HTTPException(401,'Your game session is required')
        data=snapshot(conn,body,user)
        token=secrets.token_urlsafe(24)
        conn.execute('''INSERT INTO game_result_shares(token,mode,run_id,owner_id,snapshot)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(mode,run_id,owner_id) DO NOTHING''',
            (token,body.mode,body.run_id,user['account_id'],Jsonb(data)))
        row=conn.execute('SELECT token,snapshot FROM game_result_shares WHERE mode=%s AND run_id=%s AND owner_id=%s',
            (body.mode,body.run_id,user['account_id'])).fetchone()
    url=public_origin()+'/s/'+row['token']
    return {'url':url,'image_url':url+'/image.png','title':row['snapshot']['title']}


def shared_result(token):
    if len(token)!=32 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in token):
        raise HTTPException(404,'Result not found')
    with get_connection() as conn:
        row=conn.execute('''SELECT s.snapshot FROM game_result_shares s JOIN game_accounts a ON a.account_id=s.owner_id
            WHERE s.token=%s AND a.deleted_at IS NULL''',(token,)).fetchone()
    if not row:raise HTTPException(404,'Result not found')
    return row['snapshot']


@lru_cache(maxsize=128)
def card_image(serialized=''):
    """One 1200x630 social preview. Adjust palette/spacing here, not in JS.

    PNG is the crawler's preview format, not an attachment sent by the player.
    The shared item is always the clickable URL to its HTML result page.
    """
    data=json.loads(serialized) if serialized else None
    bg='#f6f3eb';fg='#111111';green='#88b04b';blue='#615f58';coral='#a52c27'
    canvas=Image.new('RGB',(1200,630),bg);draw=ImageDraw.Draw(canvas)
    def text(value,xy,size=30,fill=fg,anchor='mm',width=1080):
        value=str(value)
        while size>12:
            font=ImageFont.load_default(size=size)
            if draw.textlength(value,font=font)<=width:break
            size-=1
        draw.text(xy,value,font=font,fill=fill,anchor=anchor)
    logo=Image.open(ROOT/'trivia_app/static/brand/favicon.png').convert('RGBA')
    logo.thumbnail((92,92));canvas.paste(logo,(48,34),logo)
    text('ON THE DOT.',(164,78),40,anchor='lm')
    if not data:
        brand=Image.open(ROOT/'trivia_app/static/brand/logo-transparent.png').convert('RGBA')
        brand.thumbnail((390,390));canvas.paste(brand,((1200-brand.width)//2,125),brand)
        text('FOOTBALL TRIVIA',(600,522),22,blue)
    else:
        text(data['label'].upper(),(1150,78),24,blue,'rm',440)
        text((data['status']+(' / '+data['reason'] if data.get('reason') else '')).upper(),(600,162),28,green)
        if data.get('format')=='daily_survival':
            text(data['player'],(600,220),32,width=800)
            text(f"{data['correct']} GOALS",(600,290),74,width=950)
        else:
            text(data['player'],(256,240),32,width=380)
            text(data['opponent'],(944,240),32,width=380)
            text(f"{data['score'][0]} : {data['score'][1]}",(600,285),90,width=300)
        for side,shots in enumerate(data['attempts']):
            # Long sudden death keeps the five opening kicks and latest pair.
            visible=shots if len(shots)<=7 else shots[:5]+shots[-2:]
            for i,goal in enumerate(visible):
                x=(256 if side==0 else 944)+(i-(len(visible)-1)/2)*38;y=315
                ball=Image.open(ROOT/'trivia_app/static/icons/football.png').convert('RGBA').resize((28,28),Image.Resampling.LANCZOS)
                if not goal:
                    from PIL import ImageChops
                    alpha=ball.getchannel('A');ball=ImageChops.multiply(ball,Image.new('RGBA',ball.size,'#ff6f61'));ball.putalpha(alpha)
                canvas.paste(ball,(round(x-14),round(y-14)),ball)
        draw.line((48,380,1152,380),fill=fg,width=4)
        text(f"{data['correct']} / {data['total']}",(315,440),42)
        text('CORRECT ANSWERS',(315,486),20,blue)
        text('Friendly' if data['mode']=='friend' else f"{data['xp']} XP",(885,440),42)
        text('NO XP OR RATING' if data['mode']=='friend' else 'GUEST XP' if data['guest'] else 'XP EARNED',(885,486),20,blue)
    draw.line((48,550,1152,550),fill=fg,width=4)
    text('onthedot.gg',(48,592),24,fg,'lm')
    text('PLAY PENALTIES',(1152,592),24,fg,'rm')
    out=BytesIO();canvas.save(out,format='PNG',optimize=True);return out.getvalue()


@router.get('/share/brand.png')
def brand_image():
    return Response(card_image(),media_type='image/png',headers={'Cache-Control':'public, max-age=86400'})


@router.get('/s/{token}/image.png')
def result_image(token:str):
    # Check that the owner still exists even when the image is in our LRU cache.
    data=shared_result(token)
    return Response(card_image(json.dumps(data,sort_keys=True)),media_type='image/png',headers={'Cache-Control':'public, max-age=300'})
