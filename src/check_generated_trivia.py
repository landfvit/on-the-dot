"""Independent second calculation using SQL over provider fixtures, not snapshot answers."""

BASE='''WITH scope AS (
    SELECT fixture_id,match_date,home_team_id=%(team)s is_home,
        CASE WHEN home_team_id=%(team)s THEN home_goals ELSE away_goals END gf,
        CASE WHEN home_team_id=%(team)s THEN away_goals ELSE home_goals END ga,
        CASE WHEN home_team_id=%(team)s THEN away_team_id ELSE home_team_id END opponent
    FROM fixtures WHERE league_id=%(league)s AND season=%(season)s
      AND (home_team_id=%(team)s OR away_team_id=%(team)s)
), ordered AS (
    SELECT *,row_number() OVER(ORDER BY match_date,fixture_id) n,
        row_number() OVER(PARTITION BY is_home ORDER BY match_date,fixture_id) venue_n,
        lag(gf-ga) OVER(ORDER BY match_date,fixture_id) previous_margin,
        lag(ga) OVER(ORDER BY match_date,fixture_id) previous_ga,
        lag(fixture_id) OVER(ORDER BY match_date,fixture_id) previous_fixture,
        CASE WHEN gf>ga THEN 3 WHEN gf=ga THEN 1 ELSE 0 END points
    FROM scope
)'''

STREAKS={'streak_wins':'gf>ga','streak_unbeaten':'gf>=ga','streak_scoring':'gf>0',
         'streak_clean_sheets':'ga=0','streak_winless':'gf<=ga'}
SUBSETS={'opening_points':('n<=6','points'),'closing_points':('n>32','points'),
         'opening_goals':('n<=6','gf'),'closing_goals':('n>32','gf'),
         'home_opening_points':('is_home AND venue_n<=5','points'),
         'away_closing_points':('NOT is_home AND venue_n>14','points')}
PAIRS={'wins_after_loss':'previous_margin<0 AND gf>ga','wins_after_draw':'previous_margin=0 AND gf>ga',
       'draws_after_win':'previous_margin>0 AND gf=ga','clean_sheet_pairs':'previous_ga=0 AND ga=0'}
OPPONENTS={'first_win_opponent':('gf>ga','n ASC'), 'last_win_opponent':('gf>ga','n DESC'),
           'last_clean_sheet_opponent':('ga=0','n DESC'),
           'biggest_home_win_opponent':('is_home AND gf>ga','gf-ga DESC'),
           'biggest_away_win_opponent':('NOT is_home AND gf>ga','gf-ga DESC')}


def independent_answer(conn,key,team,season,league=39):
    params={'team':team,'season':season,'league':league}
    if key in STREAKS:
        query=BASE+f''', marked AS (SELECT *,({STREAKS[key]}) qualifies,
            sum(CASE WHEN {STREAKS[key]} THEN 0 ELSE 1 END) OVER(ORDER BY n) island FROM ordered),
            runs AS (SELECT island,count(*) length FROM marked WHERE qualifies GROUP BY island),
            peak AS (SELECT COALESCE(max(length),0) value FROM runs)
            SELECT peak.value,ARRAY(SELECT fixture_id FROM marked WHERE qualifies AND island IN
                (SELECT island FROM runs WHERE length=peak.value) ORDER BY fixture_id) evidence FROM peak'''
    elif key in SUBSETS:
        predicate,metric=SUBSETS[key]
        query=BASE+f''' SELECT COALESCE(sum({metric}),0) value,
            COALESCE(array_agg(fixture_id ORDER BY fixture_id),'{{}}'::bigint[]) evidence FROM ordered WHERE {predicate}'''
    elif key in PAIRS:
        query=BASE+f''', matched AS (SELECT * FROM ordered WHERE {PAIRS[key]})
            SELECT count(*) value, ARRAY(SELECT fixture_id FROM matched UNION SELECT previous_fixture FROM matched ORDER BY 1) evidence FROM matched'''
    elif key in OPPONENTS:
        predicate,order=OPPONENTS[key]
        query=BASE+f''', ranked AS (SELECT *,dense_rank() OVER(ORDER BY {order}) place FROM ordered WHERE {predicate})
            SELECT min(opponent) value,count(*) winners,array_agg(fixture_id ORDER BY fixture_id) evidence FROM ranked WHERE place=1'''
    else:raise ValueError('Unknown independent check')
    result=conn.execute(query,params).fetchone()
    if result.get('winners',1)!=1:raise ValueError('Independent query has no unique answer')
    return {'value':int(result['value']),'evidence_fixture_ids':result['evidence'] or [],'query':query,'parameters':params}


def review(conn,document):
    """Recheck a saved export. Supplied values never enter the SQL calculation."""
    from api.trivia_generation_experiment import wording
    results=[];identities=set()
    for q in document['questions']:
        spec=q['specification'];issues=[]
        identity=(spec['plan'],spec['team_id'],tuple(spec['seasons']))
        if identity in identities:issues.append('Repeated semantic scope')
        identities.add(identity)
        if len(spec['seasons'])!=1 or spec['league_id']!=39:
            results.append({'id':q['id'],'status':'flagged','issues':['Unsupported scope']});continue
        team=spec['team_id'];season=spec['seasons'][0]
        scope=conn.execute('''SELECT fixture_id,match_date,status,home_goals,away_goals,home_team_id,away_team_id
            FROM fixtures WHERE league_id=39 AND season=%s AND (home_team_id=%s OR away_team_id=%s)
            ORDER BY match_date,fixture_id''',(season,team,team)).fetchall()
        if len(scope)!=38 or len({r['fixture_id'] for r in scope})!=38 or len({r['match_date'] for r in scope})!=38:
            issues.append('Incomplete or ambiguous season chronology')
        if sum(r['home_team_id']==team for r in scope)!=19 or sum(r['away_team_id']==team for r in scope)!=19:
            issues.append('Expected 19 home and 19 away fixtures')
        if any(r['status']!='FT' or r['home_goals'] is None or r['away_goals'] is None or min(r['home_goals'],r['away_goals'])<0 for r in scope):
            issues.append('Invalid or unfinished fixture')
        actual_name=conn.execute('SELECT team_name FROM teams WHERE team_id=%s',(team,)).fetchone()
        if not actual_name or actual_name['team_name']!=spec['team_name']:issues.append('Question team label does not match team ID')
        if q['question']!=wording(spec['plan'],spec['team_name'],season):issues.append('Wording differs from the audited plan')
        if [r['fixture_id'] for r in scope]!=q['answer']['scope_fixture_ids']:issues.append('Fixture scope differs from generated question')
        try:
            actual=independent_answer(conn,spec['plan'],team,season)
            if actual['value']!=q['answer']['value']:issues.append('Answer value mismatch')
            if actual['evidence_fixture_ids']!=q['answer']['evidence_fixture_ids']:issues.append('Evidence mismatch')
            if q['answer']['unit']=='club':
                opponent=conn.execute('SELECT team_name FROM teams WHERE team_id=%s',(actual['value'],)).fetchone()
                if not opponent or opponent['team_name']!=q['answer_text']:issues.append('Answer label does not match winning club ID')
            elif str(actual['value'])!=q['answer_text']:issues.append('Displayed answer differs from calculated value')
        except ValueError as error:
            actual={'value':None};issues.append(str(error))
        results.append({'id':q['id'],'status':'matched' if not issues else 'flagged','issues':issues,'independent_answer':actual['value']})
    return results


if __name__=='__main__':
    import argparse
    from datetime import datetime,timezone
    import hashlib
    import json
    from pathlib import Path
    from collections import Counter
    from api.database import get_connection

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('questions',type=Path)
    args=parser.parse_args();raw=args.questions.read_bytes();document=json.loads(raw)
    with get_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        results=review(conn,document)
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'input_sha256':hashlib.sha256(raw).hexdigest(),
            'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'summary':dict(Counter(r['status'] for r in results)),'results':results}
    target=args.questions.with_name('independent-review.json')
    target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(target),'summary':report['summary']},indent=2))
    if any(r['status']!='matched' for r in results):raise SystemExit(1)
