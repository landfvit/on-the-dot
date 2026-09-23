"""Explicitly enable an audited bank for solo; difficulty estimates are not calibration."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import re
from uuid import UUID

from api.database import get_connection
from api.penalty_bank import eligible,option_key
from api.solo_routes import latest_release

POLICY='solo-bank-v1'
REVIEWER='owner-authorized:'+POLICY
EASY_TOPICS={'Managers','Stadiums','Awards'}
MEDIUM_TOPICS={
    'Kit manufacturers','Scoring leaders','Golden Boot','Hat-tricks','Player totals',
    'Captains','Shirt sponsors','Sleeve sponsors','Player comparisons','Goalkeepers',
    'Discipline','Assists','Match details','Four-goal games','Transfers','Loans','Appearances',
    'Statement away wins','Memorable defeats','Identify the opponent','Title-race arithmetic',
}
HARD_TOPICS={
    'Conditional win rates','Club records across the window','Home, away and score patterns',
    'Two-match fingerprints','Mini-leagues','Season head-to-head patterns','Only-one opponent',
    'Multi-season head-to-head','Multi-season Big Six','Unusual season counts',
    'Against the title contenders','League-wide statistical records','Scoreline frequency',
    'Season ratios','League-wide patterns','Unusual score distributions','Head-to-head records',
    'Unique season anomalies','Table-position paradoxes','Big Six mini-leagues','Ten-season records',
}


def estimate(question):
    topic=question.get('topic');text=question['text'].lower()
    if topic in EASY_TOPICS:
        level,reason='easy','Single-fact manager, home-ground or headline award recognition.'
        if topic=='Managers' and any(word in text for word in ('caretaker','interim')):
            level,reason='medium','Historical caretaker or interim appointment rather than a long-term manager.'
    elif topic in MEDIUM_TOPICS:
        level,reason='medium','One season or match, named player, kit supplier or a specific numerical total.'
    elif topic=='Kits and design':
        level='medium' if 'main colour' in text else 'hard'
        reason='Main kit colour recall.' if level=='medium' else 'Specific kit detail, collaborator or design inspiration.'
    elif topic in HARD_TOPICS:
        level,reason='hard','Filtered statistics, unusual patterns, opponent combinations or multi-season comparisons.'
    else:
        raise ValueError('Unreviewed topic: '+str(topic))
    # Reading burden and close decimal alternatives matter in a ten-second quiz.
    if len(question['text'].split())>50 or any(re.fullmatch(r'-?\d+\.\d+%',o['text']) for o in question['options']):
        level,reason='hard','Long or compound wording, or close decimal-percentage alternatives.'
    return level,f'{POLICY}: {reason} Provisional rule-based estimate; not individually reviewed or empirically calibrated.'


def blockers(row):
    q=row['question'];source=row['content'];audit=row['audit'] or {};latest=row['latest_audit']
    issues=[]
    for label,check in [('release',audit),('latest',latest)]:
        if not check or check.get('status') not in {'matched','incomplete','unsupported','ambiguous'} or not eligible(check):
            issues.append(label+' audit is missing, conflicting or ambiguous')
    if q.get('text')!=source.get('question') or not isinstance(q.get('text'),str) or not q['text'].strip():
        issues.append('Question does not match the source')
    if not isinstance(q.get('explanation'),str) or not q['explanation'].strip():issues.append('Missing explanation')
    if not q.get('source',{}).get('references'):issues.append('Missing source references')
    if q.get('source',{}).get('question_id')!=str(row['question_id']):issues.append('Question identity mismatch')
    if q.get('source',{}).get('external_id')!=source.get('id'):issues.append('Source ID mismatch')
    if q.get('validation_status')!=audit.get('status'):issues.append('Frozen audit status mismatch')
    expected_authority='database_matched' if audit.get('status')=='matched' else 'user_attested'
    if q.get('authority')!=expected_authority:issues.append('Frozen answer authority mismatch')
    options=q.get('options')
    if not isinstance(options,list) or not 2<=len(options)<=4 or any(
        not isinstance(o,dict) or not isinstance(o.get('text'),str) or not o['text'].strip() for o in options
    ):
        return issues+['Two to four nonempty options are required']
    if {o.get('id') for o in options}!={str(i) for i in range(len(options))}:issues.append('Invalid option IDs')
    if len({option_key(o['text']) for o in options})!=len(options):issues.append('Duplicate or equivalent options')
    correct=[o for o in options if o.get('id')==q.get('correct')]
    if len(correct)!=1 or correct[0]['text']!=source.get('answer'):issues.append('Canonical answer mismatch')
    aliases={option_key(a) for a in [source.get('answer',''),*audit.get('accepted',[]),*(latest or {}).get('accepted',[])]}
    if any(o.get('id')!=q.get('correct') and option_key(o['text']) in aliases for o in options):
        issues.append('Distractor is an accepted answer alias')
    return issues


def release(conn,release_id,apply=False):
    if apply:
        conn.execute('SELECT pg_advisory_xact_lock(84424324)')
        conn.execute('LOCK TABLE game_question_difficulty IN SHARE ROW EXCLUSIVE MODE')
    published=conn.execute('SELECT * FROM penalty_bank_releases WHERE release_id=%s',(release_id,)).fetchone()
    if not published or not published['reference_answers_approved']:raise ValueError('Owner-approved bank release required')
    rows=conn.execute('''SELECT p.question_id,p.section_code,p.section_name,p.question,q.content,
            c.result audit,latest.result latest_audit,d.revision_id,d.difficulty,d.approved,d.reviewed_by
        FROM penalty_bank_questions p JOIN trivia_bank_questions q USING(question_id)
        JOIN trivia_bank_checks c ON c.question_id=p.question_id AND c.run_id=%s
        LEFT JOIN game_current_difficulty d ON d.release_id=p.release_id AND d.question_id=p.question_id
        LEFT JOIN LATERAL (
            SELECT checks.result FROM trivia_bank_checks checks
            JOIN trivia_bank_validation_runs runs ON runs.run_id=checks.run_id
            WHERE checks.question_id=p.question_id ORDER BY runs.created_at DESC,runs.run_id DESC LIMIT 1
        ) latest ON true
        WHERE p.release_id=%s ORDER BY q.external_id''',(published['validation_run_id'],release_id)).fetchall()
    if len(rows)!=published['question_count']:raise ValueError('Incomplete published bank or audit')
    counts=Counter();levels=Counter();authorities=Counter();sections=defaultdict(Counter);questions=[]
    for row in rows:
        issues=blockers(row);level=row['difficulty'];reason='Existing editorial assessment retained.'
        proposed=None;proposal=''
        if not issues:
            try:
                proposed,proposal=estimate(row['question'])
            except ValueError as error:
                proposal=str(error);issues.append(proposal)
        # Only untouched initial suggestions can be promoted. Explicit holds stay private.
        pending=not row['approved'] and (row['revision_id'] is None or row['reviewed_by']=='initial-editorial-v1')
        action='blocked' if issues else 'add' if pending else 'keep' if row['approved'] else 'editor_hold'
        if action=='add':level,reason=proposed,proposal
        if action=='blocked':reason='; '.join(issues)
        counts[action]+=1
        if action in {'add','keep'}:
            levels[level]+=1;sections[row['section_code']][level]+=1;authorities[row['question']['authority']]+=1
        questions.append({'id':row['content']['id'],'question_id':str(row['question_id']),'action':action,
                          'difficulty':level,'reason':reason,'authority':row['question']['authority'],'issues':issues})
    # Do not partially publish a batch whose already-active questions fail validation.
    if apply and any(item['action']=='blocked' and row['approved'] for item,row in zip(questions,rows)):
        raise ValueError('An already-approved question failed checks; review the dry-run report before publishing')
    if apply:
        for item in questions:
            if item['action']=='add':
                conn.execute('''INSERT INTO game_question_difficulty(release_id,question_id,difficulty,approved,reason,reviewed_by)
                    VALUES(%s,%s,%s,true,%s,%s)''',(release_id,item['question_id'],item['difficulty'],item['reason'],REVIEWER))
    return {'policy':POLICY,'release_id':str(release_id),'applied':apply,'total':len(rows),
            'actions':dict(counts),'available_by_difficulty':dict(levels),'answer_authority':dict(authorities),
            'categories':dict(sections),'questions':questions}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',type=UUID,help='Pinned release required when applying')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--confirm-user-attested',action='store_true')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    if args.apply and (not args.release or not args.confirm_user_attested):
        parser.error('--apply requires --release and --confirm-user-attested')
    with get_connection() as conn:
        result=release(conn,args.release or latest_release(conn),args.apply)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'questions','categories'}},indent=2))


if __name__=='__main__':main()
