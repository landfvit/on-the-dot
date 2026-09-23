"""Build 100 unpublished, model-assisted drafts and independently check every answer.

The local classifier does not generate language. The assistant authored PLANS;
this runner binds explicit seasons/clubs, calculates, deduplicates and audits.
"""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import csv
import hashlib
import json
from pathlib import Path
import random
from uuid import uuid4

from api.database import get_connection
from api.trivia_bank_engine import BankEvaluator
from api.trivia_generation_experiment import PLANS,NoveltyIndex,snapshot_answer,wording
from src.check_generated_trivia import independent_answer
from src.trivia_bank_model import suggest

ROOT=Path(__file__).resolve().parents[1]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()


def generate(seasons,output,seed=20260921):
    if not seasons or len(seasons)!=len(set(seasons)):raise ValueError('Choose explicit, distinct seasons')
    rng=random.Random(seed);questions=[];rejected=[];team_uses=Counter();season_uses=Counter();used=set()
    with get_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        dataset=conn.execute('SELECT * FROM trivia_datasets WHERE sealed_at IS NOT NULL ORDER BY created_at DESC LIMIT 1').fetchone()
        model=conn.execute('SELECT * FROM trivia_bank_models ORDER BY created_at DESC LIMIT 1').fetchone()
        if not dataset or not model:raise ValueError('Need a sealed dataset and a trained local recognition model')
        facts=conn.execute('''SELECT f.*,q.result_valid FROM trivia_match_team_facts f
            JOIN trivia_match_data_quality q USING(dataset_id,fixture_id)
            WHERE dataset_id=%s AND league_id=39 AND season=ANY(%s) ORDER BY season,match_date,fixture_id,team_id''',
            (dataset['dataset_id'],seasons)).fetchall()
        raw=conn.execute('''SELECT fixture_id,season,match_date,status,home_team_id,away_team_id,home_goals,away_goals
            FROM fixtures WHERE league_id=39 AND season=ANY(%s) ORDER BY season,match_date,fixture_id''',(seasons,)).fetchall()
        groups=defaultdict(list);by_season=defaultdict(list)
        for row in facts:groups[row['team_id'],row['season']].append(row);by_season[row['season']].append(row)
        for season in seasons:
            failure=BankEvaluator.audit_season(by_season[season])
            if failure:raise ValueError(f'Season {season} is not complete: {failure}')
        live={r['fixture_id']:r for r in raw};home_facts=[r for r in facts if r['is_home']]
        if len(live)!=380*len(seasons) or set(live)!={r['fixture_id'] for r in home_facts}:
            raise ValueError('Raw fixtures and sealed snapshot cover different matches')
        for r in home_facts:
            f=live[r['fixture_id']]
            if (f['season'],f['match_date'],f['home_team_id'],f['away_team_id'],f['home_goals'],f['away_goals'],f['status']) != (
                r['season'],r['match_date'],r['team_id'],r['opponent_id'],r['goals_for'],r['goals_against'],r['status']):
                raise ValueError('Provider fixtures changed since sealing; rebuild/audit the dataset')
        existing=[{'id':r['external_id'],'question':r['text']} for r in conn.execute(
            "SELECT external_id,content->>'question' text FROM trivia_bank_questions ORDER BY question_id")]
        existing += [{'id':str(r['version_id']),'question':r['question_text']} for r in conn.execute(
            'SELECT version_id,question_text FROM trivia_question_versions ORDER BY version_id')]
        existing += [{'id':str(r['draft_id']),'question':r['question_text']} for r in conn.execute(
            'SELECT draft_id,question_text FROM trivia_bank_authored_drafts ORDER BY draft_id')]
        # Previous experiment outputs count as existing questions too, not only published banks.
        for path in sorted(Path(output).glob('*/questions.json')):
            previous=json.loads(path.read_text())
            existing += [{'id':q['id'],'question':q['question']} for q in previous['questions']]
        index=NoveltyIndex(existing);combos=list(groups);rng.shuffle(combos)
        tie_order={combo:n for n,combo in enumerate(combos)}
        for round_number in range(5):
            plans=list(PLANS);rng.shuffle(plans)
            for plan in plans:
                ordered=sorted(combos,key=lambda c:(team_uses[c[0]],season_uses[c[1]],tie_order[c]))
                for team,season in ordered:
                    if (team,season) in used or team_uses[team]>=5:continue
                    rows=groups[team,season];name=rows[0]['team_name'];text=wording(plan.key,name,season)
                    novelty=index.check(plan.key,team,season,text)
                    if not novelty['accepted']:
                        rejected.append({'plan':plan.key,'team':team,'season':season,'reason':novelty['reason']});continue
                    try:
                        answer=snapshot_answer(plan.key,rows)
                        if plan.key.startswith('streak_') and answer['value']<2:raise ValueError('Uninteresting one-match streak')
                        verification=independent_answer(conn,plan.key,team,season)
                    except ValueError as error:
                        rejected.append({'plan':plan.key,'team':team,'season':season,'reason':str(error)});continue
                    if answer['value']!=verification['value'] or answer['evidence_fixture_ids']!=verification['evidence_fixture_ids']:
                        raise ValueError(f'Independent answer/evidence disagreement: {plan.key}, {team}, {season}')
                    question={'id':f'EXP-{len(questions)+1:03}','question':text,
                        'specification':{'schema_version':'generation-experiment-v1','plan':plan.key,'team_id':team,'team_name':name,
                                         'league_id':39,'seasons':[season],'ordering':'actual kickoff then fixture ID; league matches only'},
                        'answer':answer,'answer_text':answer['details'].get('opponent_name',str(answer['value'])),
                        'novelty':novelty,'independent_verification':{'status':'matched',**verification},
                        'evidence':[{'fixture_id':r['fixture_id'],'date':r['match_date'],'opponent':r['opponent_name'],
                                     'venue':'home' if r['is_home'] else 'away','goals_for':r['goals_for'],'goals_against':r['goals_against']}
                                    for r in rows if r['fixture_id'] in answer['evidence_fixture_ids']],
                        'state':'unpublished_review_draft'}
                    questions.append(question);used.add((team,season));team_uses[team]+=1;season_uses[season]+=1
                    break
                else:raise ValueError(f'Cannot find enough novel, unambiguous questions for {plan.key}; no partial output saved')
            print(f'Calculated and independently verified {len(questions)}/100',flush=True)
        for n,q in enumerate(questions,1):
            q['recognition']=suggest(model['artifact'],model['corpus'],q['question'],limit=3)
            if n%20==0:print(f'Local model reviewed {n}/100',flush=True)
        sources=['api/trivia_generation_experiment.py','src/check_generated_trivia.py','src/generate_trivia_experiment.py','src/trivia_bank_model.py']
        report={'experiment_id':str(uuid4()),'created_at':datetime.now(timezone.utc),'dataset_id':dataset['dataset_id'],
            'dataset_source_hash':dataset['source_hash'],'model_id':model['model_id'],'seasons':seasons,'seed':seed,
            'generation_method':'Assistant LLM authored 20 new question plans; deterministic binding creates five distinct club-season questions per plan.',
            'local_model_role':'Topic recognition and nearest training examples only. NOT autonomous language generation or answer prediction.',
            'verification_method':'Python over sealed facts versus independent SQL over provider fixtures; values AND evidence IDs must agree.',
            'verification_limit':'Both database representations originate from the same football provider; this is not external-source fact checking.',
            'source_drift_check':'All scoped raw fixture scores, dates, clubs and statuses equal the sealed snapshot.',
            'question_count':len(questions),'existing_questions_checked':len(existing),'existing_questions_sha256':fingerprint(existing),
            'raw_fixtures_sha256':fingerprint(raw),'snapshot_facts_sha256':fingerprint(facts),
            'code_sha256':{s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources},
            'verification_counts':dict(Counter(q['independent_verification']['status'] for q in questions)),
            'per_plan':dict(Counter(q['specification']['plan'] for q in questions)),
            'teams':dict(team_uses),'season_counts':dict(season_uses),'rejected_candidates':rejected,'questions':questions}
    destination=Path(output)/report['experiment_id'];destination.mkdir(parents=True,exist_ok=False)
    (destination/'questions.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n')
    with (destination/'questions.csv').open('w',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(['id','question','answer','unit','team','season','plan','independent_check','nearest_existing_similarity','model_topic'])
        for q in questions:
            s=q['specification'];writer.writerow([q['id'],q['question'],q['answer_text'],q['answer']['unit'],s['team_name'],s['seasons'][0],s['plan'],'matched',q['novelty']['nearest_similarity'],q['recognition']['topic']])
    lines=['# 100 New Trivia Questions: Independent Database Check','',
        'Status: unpublished review drafts. No game questions or production records were changed.',
        '',report['generation_method'],report['local_model_role'],'',
        f"Dataset: `{report['dataset_id']}`. Model: `{report['model_id']}`.",
        f"Compared with {len(existing)} existing questions; 100 distinct club-season scopes, 20 new plans.",
        report['verification_method'],report['verification_limit'],'',
        '## Reading Rules','',
        'All ordering is actual kickoff order, not the nominal matchweek. Runs never cross season boundaries.',
        'Only Premier League matches count; cup matches do not interrupt runs. Points are earned on the pitch before deductions.',
        'Overlapping adjacent pairs count separately. Biggest-win questions require a unique winning margin.',
        'Near-duplicate detection is an explicit heuristic, not a claim of universal semantic equivalence detection.',
        '', '## Questions','']
    for q in questions:
        a=q['answer'];v=q['independent_verification']
        unit={'transitions':'times'}.get(a['unit'],a['unit'])
        if a['value']==1:unit={'times':'time','matches':'match','goals':'goal','points':'point','pairs':'pair'}.get(unit,unit)
        lines += [f"### {q['id']}",q['question'],'',f"**Answer:** {q['answer_text']}"+(f" {unit}" if unit!='club' else ''),
                  f"**Check:** MATCHED. Python: `{a['value']}`; independent SQL: `{v['value']}`.",
                  f"**Evidence:** {', '.join(str(i) for i in a['evidence_fixture_ids']) or 'No qualifying matches'}.",
                  f"**Model topic suggestion:** {q['recognition']['topic']} (not an answer verifier).",'']
    (destination/'review.md').write_text('\n'.join(lines)+'\n')
    return {'output':str(destination),'question_count':len(questions),'verified':report['verification_counts'],
            'team_count':len(team_uses),'season_counts':dict(season_uses),'rejected_candidates':len(rejected)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seasons',type=int,nargs='+',required=True,help='Explicit season start years; no implicit last-N window')
    parser.add_argument('--output',type=Path,default=ROOT/'reports'/'generated-trivia')
    parser.add_argument('--seed',type=int,default=20260921)
    args=parser.parse_args()
    print(json.dumps(generate(args.seasons,args.output,args.seed),indent=2,default=str))
