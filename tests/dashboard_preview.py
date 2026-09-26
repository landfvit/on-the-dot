"""Disposable admin browser fixture; never use production player data."""
import os
from uuid import uuid4
import uvicorn
from tests.test_developer_dashboard import DashboardDatabaseTests

if __name__=='__main__':
    os.environ['PUBLIC_SITE_URL']='http://127.0.0.1:8015'
    fixture=DashboardDatabaseTests('test_reporting_empty_then_solo_daily_friend')
    try:
        fixture.setUp()
        f=fixture.fixture
        solo=f.start('easy');f.client.post('/api/solo/runs/'+solo['run_id']+'/leave',json={})
        daily=f.daily();path='/api/daily/runs/'+daily['run_id']
        f.client.post(path+'/next',json={'previous':0})
        answer=f.mode_row(daily['run_id'])['state']['deck'][0]['correct']
        f.client.post(path+'/answers',json={'position':1,'option_id':answer,'request_id':str(uuid4())})
        f.client.post(path+'/leave',json={})
        f.duel()
        f.client.patch('/api/players/me',json={'bio':'<img src=x onerror=alert(1)> Test profile'})
        uvicorn.run('trivia_app.main:app',host='127.0.0.1',port=8015,log_level='warning')
    finally:
        fixture.doCleanups()
