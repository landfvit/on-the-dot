"""Local browser fixture. All player writes go to a disposable schema."""
import uvicorn
import os
from tests.test_challenge_database import ChallengeDatabaseTests

if __name__=='__main__':
    os.environ['PUBLIC_SITE_URL']='http://127.0.0.1:8015'
    fixture=ChallengeDatabaseTests('test_daily_pool_is_shared_exact_and_private')
    try:
        fixture.setUp()
        uvicorn.run('trivia_app.main:app',host='127.0.0.1',port=8015,log_level='warning')
    finally:
        fixture.doCleanups()
