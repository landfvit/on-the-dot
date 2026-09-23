"""Isolated browser fixture, never writes to the app DB or uses player cookies.

Run: .venv/bin/python -m tests.community_preview
Only bound to loopback on 8013. Stop after visual QA; not a production route.
"""
import time
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from api import solo_engine
from trivia_app.main import templates, app as real_app

app=FastAPI()
assets=next(r for r in real_app.routes if getattr(r,'path',None)=='/trivia-assets')
app.mount('/trivia-assets',assets.app)
state=None
club=None
now=lambda:int(time.time()*1000)


@app.middleware('http')
async def no_cache(request,call_next):
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    return response


@app.get('/stadium-fade',response_class=HTMLResponse)
def stadium_fade():
    return Path(__file__).with_name('stadium_fade.html').read_text()


@app.get('/shootout-scene',response_class=HTMLResponse)
def shootout_scene():
    return Path(__file__).with_name('shootout_scene.html').read_text()


def player():
    xp=220+(solo_engine.rewards(state)['total_xp'] if state else 0)
    return {'username':'preview_player','email':'preview@example.com','club':club,'stats':{'wins':12,'losses':8,'played':20,'win_rate':60},'level':2,'total_xp':xp,'level_xp':200,'next_level_xp':600,
            'bio':'','accent':'green','streak':{'current':3,'longest':5},'completed_quizzes':4}


def view():
    result={**solo_engine.view(state,now()),'run_id':'preview-run','is_trial':False,'xp_saved':True}
    if state['phase'] in ('FINISHED','ABANDONED'):
        result['player_progress']={k:player()[k] for k in ('level','total_xp','level_xp','next_level_xp')}
    return result


@app.get('/penalties',response_class=HTMLResponse)
def page(request:Request,qa:bool=False):
    response=templates.TemplateResponse(request=request,name='solo.html',context={'active_page':'penalties'})
    if qa:
        # Preview-only telemetry, using the actual page, wrapper and stylesheet
        # cascade. Never injected into the standalone app or player sessions.
        script=Path(__file__).with_name('stadium_browser_checks.js').read_text()
        return HTMLResponse(response.body.decode().replace('</body>',f'<script>{script}</script></body>'))
    return response


@app.get('/api/players/me')
def me():return player()


@app.get('/account',response_class=HTMLResponse)
def profile_page(request:Request):
    return templates.TemplateResponse(request=request,name='account.html',context={'active_page':'account'})


@app.get('/leaderboard',response_class=HTMLResponse)
def leaderboard_page(request:Request):
    return templates.TemplateResponse(request=request,name='community.html',context={'active_page':'leaderboard'})


@app.get('/api/players/teams')
def teams():return {'teams':[{'team_id':33,'name':'Manchester United','season':2025},{'team_id':42,'name':'Arsenal','season':2025}]}


@app.put('/api/players/me/team')
async def team(request:Request):
    global club
    data=await request.json();club=next((t for t in teams()['teams'] if t['team_id']==data['team_id']),None)
    return player()


@app.get('/api/community/leaderboard')
def leaderboard(metric:str='level',period:str='all'):
    entries=[dict(player(),rank=1,xp=220,wins=12,losses=8,played=20,win_rate=60),
             {'rank':2,'username':'another_player','club':None,'level':1,'total_xp':100,'xp':100,'wins':2,'losses':4,'played':6,'win_rate':33.3}]
    return {'entries':entries,'me':entries[0],'participants':2,'signed_in':True,'metric':metric,'period':period,
            'since':None,'as_of':'2026-09-22T12:00:00Z','distribution':[{'label':'<100','count':0},{'label':'100-249','count':2}]}


@app.get('/api/solo/catalog')
def catalog():
    counts={'easy':100,'medium':100,'hard':100}
    return {'categories':[{'code':'ALL','label':'All clubs','counts':counts}],
            'topics':[{'code':'ALL','label':'Mixed topics','counts_by_team':{'ALL':counts}}],
            'rules':solo_engine.RULES}


@app.get('/api/solo/active')
def active():return {'run':view() if state and state['phase'] not in ('FINISHED','ABANDONED') else None,'trial_available':False}


@app.post('/api/solo/runs')
async def start(request:Request):
    global state
    body=await request.json()
    deck=[{'key':str(i),'text':'Which club won the 2017/18 Premier League?',
           'options':[{'id':str(n),'text':name} for n,name in enumerate(['Manchester City','Manchester United','Chelsea','Liverpool'])],
           'correct':'0','explanation':'Manchester City finished with 100 points.','authority':'preview'} for i in range(10)]
    state=solo_engine.create(deck,body['difficulty'],{'code':'ALL','label':'All clubs','topic_label':'Mixed topics'},now())
    return view()


@app.get('/api/solo/runs/{run_id}')
def get(run_id:str):
    if state is None:raise HTTPException(404,'Preview run not found')
    solo_engine.tick(state,now());return view()


@app.post('/api/solo/runs/{run_id}/{command}')
async def action(run_id:str,command:str,request:Request):
    body=await request.json();solo_engine.tick(state,now())
    if command=='next':solo_engine.advance(state,body['previous'],now())
    elif command=='answers':solo_engine.answer(state,body['position'],body['option_id'],body['request_id'],now())
    elif command=='leave':state.update(phase='ABANDONED',finished_at=now())
    return view()


if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8013)
