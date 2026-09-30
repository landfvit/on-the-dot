from pathlib import Path
from contextlib import asynccontextmanager
import os
import secrets
import json
import time
import re
from threading import Lock

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from api.trivia import router as questions
from api.trivia_quizzes import router as quizzes, same_origin
from api.trivia_access import require_editor, credential_tag, basic
from api.sports_query_routes import router as sports_query
from api.query_training import router as query_training
from api.trivia_bank_routes import router as trivia_bank
from api.player_accounts import router as player_accounts, account, COOKIE as ACCOUNT_COOKIE
from api.database import get_connection, start_pool, close_pool
from psycopg_pool import PoolTimeout, TooManyRequests
from starlette.concurrency import run_in_threadpool
from api.solo_routes import router as solo
from api.solo_difficulty import router as solo_difficulty
from api.trivia_writer import router as trivia_writer
from api.game_community import router as game_community
from api.challenge_routes import router as challenges
from api.social_routes import router as social
from api.developer_dashboard import router as developer_dashboard
from api.result_shares import router as result_shares, shared_result, public_origin
from trivia_app.game_guide import guide_context


ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(app):
    start_pool()
    try:
        yield
    finally:
        await run_in_threadpool(close_pool)


app = FastAPI(title='ON THE DOT. Trivia', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.state.session_secret = os.getenv('TRIVIA_SESSION_SECRET') or secrets.token_urlsafe(48)
app.add_middleware(SessionMiddleware, secret_key=app.state.session_secret, session_cookie='points_editor',
                   max_age=8*3600, same_site='strict', https_only=os.getenv('TRIVIA_HTTPS_ONLY') == '1')
templates = Jinja2Templates(directory=[str(ROOT / 'trivia_app' / 'templates'), str(ROOT / 'web' / 'templates')])
public_metadata=json.loads((ROOT/'trivia_app'/'static'/'public_metadata.json').read_text())
templates.env.globals['public_metadata']=public_metadata
templates.env.globals['public_origin']=public_origin


class TriviaAssets(StaticFiles):
    def __init__(self, *args, public_files=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.public_files=frozenset(public_files)

    async def get_response(self,path,scope):
        # A failed ES-module dependency remains cached for the page lifetime in
        # Safari. A retry namespace gives the entire relative import graph fresh
        # URLs, including vendored Three.js, while keeping the same allowlist.
        if path.startswith('_retry/'):
            match=re.fullmatch(r'_retry/[1-9][0-9]{0,5}/(.+)',path)
            if not match or match[1] not in self.public_files:
                raise HTTPException(404,'Asset not found')
            path=match[1]
        if path not in self.public_files:
            request=Request(scope)
            require_editor(request,await basic(request))
        return await super().get_response(path,scope)


app.mount('/assets', TriviaAssets(directory=ROOT / 'web' / 'static'), name='assets')
app.mount('/trivia-assets', TriviaAssets(directory=ROOT / 'trivia_app' / 'static',
    public_files=('app.css','penalties.css','penalty_scene.js','solo.css','solo.js',
                  'stadium.css','stadium_inline.css','stadium_intro.js','stadium_scene.js','stadium_config.js','stadium_v6_world.js','stadium_motion.js','crowd_reaction.js','penalty_shots.js','points_theme.css','redesign.css','home.css','home.js','theme.js','dark_mode.css','icons/sun.svg','icons/moon.svg',
                  'community.css','community.js','shell.js','shootout.css','result_share.js','solo_mobile.css','solo_mobile.js','solo_results.css','friends.js','game_modes.css',
                  'account_settings.css','account_settings.js','profile.css','xp_progress.css','xp_progress.js','public_ui.css','public_ui.js','question_text.js','social.css','social.js','mode_intro.js',
                  'player_kit.css','player_kit.js','kit_pixels.js','player-kits/catalog.json',
                  'audio.css','audio.js','icons/volume-2.svg','icons/volume-x.svg','icons/monitor.svg','icons/monitor-off.svg',
                  'game_guide.css','game_guide.js','guide/shooter.png','guide/keeper.png','icons/circle-help.svg',
                  'guide/kit-home.png','guide/kit-away.png','guide/kit-third.png','guide/kit-number.png',
                  'brand/logo.png','brand/mark.png','brand/favicon.png','brand/favicon.svg','brand/logo-transparent.png','brand/logo.svg','brand/icon-180.png',
                  'icons/eye.svg','icons/eye-off.svg',
                  *(f'clubs/{club["team_id"]}.png' for club in public_metadata['clubs']),
                  'icons/menu.svg','icons/x.svg','icons/user-round.svg','icons/trophy.svg','icons/history.svg',
                  'icons/arrow-right.svg','icons/share-2.svg','icons/football.svg','icons/football-outline.svg','icons/copy.svg','icons/download.svg','icons/LICENSE',
                  'sounds/crowd-cheer.wav','sounds/crowd-groan.wav','sounds/LICENSE.md',
                  'vendor/three/three.module.min.js','vendor/three/three.core.min.js','vendor/three/LICENSE')), name='trivia-assets')
app.include_router(questions,dependencies=[Depends(require_editor)])
app.include_router(quizzes,dependencies=[Depends(require_editor)])
app.include_router(sports_query)
app.include_router(query_training)
app.include_router(trivia_bank)
app.include_router(player_accounts)
app.include_router(solo)
app.include_router(solo_difficulty)
app.include_router(trivia_writer)
app.include_router(game_community)
app.include_router(challenges)
app.include_router(social)
app.include_router(result_shares)
app.include_router(developer_dashboard)


@app.get('/s/{token}',response_class=HTMLResponse)
def shared_result_page(token:str,request:Request):
    data=shared_result(token)
    return templates.TemplateResponse(request=request,name='shared_result.html',
        context={'result':data,'share_url':public_origin()+'/s/'+token,'active_page':'shared'},
        headers={'Cache-Control':'public, max-age=300'})


@app.middleware('http')
async def privacy_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(('/api/', '/internal/', '/login', '/logout', '/assets/', '/trivia-assets/')) or request.url.path in ('/trivia','/quizzes'):
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


@app.exception_handler(HTTPException)
async def errors(request, exc):
    if exc.status_code == 401 and request.url.path == '/internal/dashboard':
        return RedirectResponse('/login?next=/internal/dashboard', status_code=303)
    if exc.status_code == 401 and (request.url.path.startswith('/internal/trivia') or request.url.path in ('/trivia','/quizzes')):
        return RedirectResponse('/login', status_code=303)
    return JSONResponse({'detail': exc.detail}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(PoolTimeout)
@app.exception_handler(TooManyRequests)
async def database_busy(request, exc):
    # Never include connection strings or driver diagnostics in public errors.
    return JSONResponse({'detail': 'The game is busy. Please try again shortly.'},
                        status_code=503, headers={'Retry-After': '2', 'Cache-Control': 'no-store'})


@app.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    if not os.getenv('TRIVIA_EDITOR_USERNAME') or len(os.getenv('TRIVIA_EDITOR_PASSWORD', '')) < 16:
        raise HTTPException(404, 'Editor is not configured')
    destination = '/internal/dashboard' if request.query_params.get('next') == '/internal/dashboard' else '/internal/trivia'
    return templates.TemplateResponse(request=request, name='login.html', context={'destination': destination})


login_failures = {}
login_lock = Lock()


@app.post('/login', dependencies=[Depends(same_origin)])
def login(request: Request, username: str = Form(max_length=200), password: str = Form(max_length=512), next: str = Form('/internal/trivia', max_length=200)):
    destination = '/internal/dashboard' if next == '/internal/dashboard' else '/internal/trivia'
    expected_user, expected_password = os.getenv('TRIVIA_EDITOR_USERNAME', ''), os.getenv('TRIVIA_EDITOR_PASSWORD', '')
    if not expected_user or len(expected_password) < 16:
        raise HTTPException(404, 'Editor is not configured')
    now, key = time.monotonic(), request.client.host if request.client else 'local'
    with login_lock:
        for address in list(login_failures):
            if now - login_failures[address][0] > 300:
                del login_failures[address]
        if len(login_failures) >= 1000 or login_failures.get(key, (now, 0))[1] >= 5:
            raise HTTPException(429, 'Too many attempts. Try again in five minutes.', headers={'Retry-After': '300'})
        valid_user = secrets.compare_digest(username.encode(), expected_user.encode())
        valid_password = secrets.compare_digest(password.encode(), expected_password.encode())
        if not (valid_user and valid_password):
            start, count = login_failures.get(key, (now, 0)); login_failures[key] = (start, count + 1)
            return templates.TemplateResponse(request=request, name='login.html', context={'error': 'Invalid username or password.', 'destination': destination}, status_code=401)
        login_failures.pop(key, None)
    request.session.clear()
    request.session.update({'editor': username, 'credential_tag': credential_tag(request)})
    return RedirectResponse(destination, status_code=303)


@app.post('/logout', dependencies=[Depends(same_origin)])
def logout(request: Request):
    request.session.clear()
    return RedirectResponse('/login', status_code=303)


@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    # The same lightweight mode selector for guests and signed-in players.
    # Authentication, active games and eligibility remain on their game routes.
    response = templates.TemplateResponse(request=request, name='home.html', context={'active_page':'home'})
    # Preserve the public shell's no-store contract across account transitions.
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@app.get('/favicon.ico', include_in_schema=False)
def favicon():
    return RedirectResponse('/trivia-assets/brand/favicon.png?v=5', status_code=307,
                            headers={'Cache-Control':'no-cache'})


@app.get('/quizzes', response_class=HTMLResponse, dependencies=[Depends(require_editor)])
def quizzes_page(request: Request):
    return templates.TemplateResponse(request=request, name='quizzes.html', context={'active_page': 'play','private_navigation':True})


@app.get('/trivia', response_class=HTMLResponse, dependencies=[Depends(require_editor)])
def practice(request: Request):
    return templates.TemplateResponse(request=request, name='trivia_play.html',
        context={'base_template': 'trivia_base.html', 'active_page': 'practice','private_navigation':True})


@app.get('/penalties',response_class=HTMLResponse)
def penalties_page(request:Request):
    return templates.TemplateResponse(request=request,name='solo.html',context={'active_page':'penalties'})


@app.get('/solo',response_class=HTMLResponse)
def solo_page(request:Request):
    return RedirectResponse('/penalties',status_code=307)


@app.get('/daily',response_class=HTMLResponse)
def daily_page(request:Request):
    return templates.TemplateResponse(request=request,name='solo.html',context={'active_page':'daily','game_mode':'daily'})


@app.get('/friends',response_class=HTMLResponse)
@app.get('/friends/{code}',response_class=HTMLResponse)
def friends_page(request:Request,code:str=''):
    return templates.TemplateResponse(request=request,name='solo.html',context={'active_page':'friends','game_mode':'friend','invite_code':code})


@app.get('/account',response_class=HTMLResponse)
def account_page(request:Request):
    return templates.TemplateResponse(request=request,name='account.html',context={'active_page':'account'})


@app.get('/how-to-play',response_class=HTMLResponse)
def game_guide_page(request:Request):
    return templates.TemplateResponse(request=request,name='game_guide.html',context=guide_context())


@app.get('/leaderboard',response_class=HTMLResponse)
def leaderboard_page(request:Request):
    return templates.TemplateResponse(request=request,name='community.html',context={'active_page':'leaderboard'})


@app.get('/history',response_class=HTMLResponse)
def history_page(request:Request):
    return templates.TemplateResponse(request=request,name='community.html',context={'active_page':'history'})


@app.get('/u/{username}',response_class=HTMLResponse)
def player_page(username:str,request:Request):
    return templates.TemplateResponse(request=request,name='account.html',context={'active_page':'account','profile_username':username})


@app.get('/internal/trivia/difficulty',response_class=HTMLResponse,dependencies=[Depends(require_editor)])
def difficulty_page(request:Request):
    return templates.TemplateResponse(request=request,name='difficulty.html',context={'active_page':'difficulty','private_navigation':True})


@app.get('/internal/dashboard',response_class=HTMLResponse,dependencies=[Depends(require_editor)])
def dashboard_page(request:Request):
    return templates.TemplateResponse(request=request,name='developer_dashboard.html')


@app.get('/internal/trivia', response_class=HTMLResponse, dependencies=[Depends(require_editor)])
def editor(request: Request):
    return templates.TemplateResponse(request=request, name='trivia.html',
        context={'base_template': 'trivia_base.html', 'standalone': True, 'active_page': 'editor','private_navigation':True})


@app.get('/internal/trivia/bank', response_class=HTMLResponse, dependencies=[Depends(require_editor)])
def bank_page(request: Request):
    return templates.TemplateResponse(request=request, name='bank.html', context={'active_page': 'bank','private_navigation':True})
