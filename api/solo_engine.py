"""Pure solo transitions. The database owns the clock and serializes commands."""
from copy import deepcopy
from datetime import timedelta

RULES={'version':'solo-shootout-v5','format':'shootout','initial_kicks':5,'questions':10,'answer_ms':15000,'xp_by_difficulty':{'easy':10,'medium':20,'hard':30},
       'bonus_mode':'win','win_multipliers':{'easy':2,'medium':3,'hard':4},
       'perfect_multipliers':{'easy':1,'medium':2,'hard':3},'max_run_ms':1800000}


class SoloError(ValueError):pass


def is_shootout(state):
    return state['rules'].get('format')=='shootout'


def shootout(state):
    """IFAB Law 10: clinch early, then sudden death only after equal kicks."""
    score={'player':0,'opponent':0};kicks={'player':0,'opponent':0};attempts=[]
    for index,answer in enumerate(state['history']):
        side='player' if index%2==0 else 'opponent'
        goal=answer['correct'] if side=='player' else not answer['correct']
        kicks[side]+=1;score[side]+=int(goal)
        attempts.append({'side':side,'goal':goal,'number':kicks[side]})
    winner=None
    if max(kicks.values())<=5:
        for side,other in [('player','opponent'),('opponent','player')]:
            if score[side]>score[other]+5-kicks[other]:winner=side
    elif kicks['player']==kicks['opponent'] and score['player']!=score['opponent']:
        winner=max(score,key=score.get)
    return {**score,'kicks':kicks,'attempts':attempts,'winner':winner,
            'sudden_death':len(attempts)>=10,'round':len(attempts)//2+1,
            'next_role':'shooter' if len(attempts)%2==0 else 'keeper'}


def create(deck,difficulty,category,now):
    if difficulty not in RULES['perfect_multipliers'] or len(deck)!=10 or len({q['key'] for q in deck})!=10:
        raise SoloError('A quiz requires ten distinct questions of one difficulty')
    rules=deepcopy(RULES);rules['xp_per_correct']=rules['xp_by_difficulty'][difficulty]
    return {'deck':deepcopy(deck),'difficulty':difficulty,'category':category,'rules':rules,
            'phase':'READY','position':0,'deadline':None,'opened_at':None,'created_at':now,
            'finished_at':None,'history':[]}


def resolve(state,option,request_id,now):
    q=state['deck'][state['position']-1]
    state['history'].append({'position':state['position'],'option_id':option,'request_id':request_id,
        'correct':option is not None and option==q['correct'],
        'elapsed_ms':min(state['rules']['answer_ms'],max(0,now-state['opened_at'])),'answered_at':now})
    if is_shootout(state):
        entry=state['history'][-1];entry['role']='shooter' if state['position']%2 else 'keeper'
        goal=entry['correct'] if entry['role']=='shooter' else not entry['correct']
        entry['outcome']='goal' if goal else 'miss' if option is None and entry['role']=='shooter' else 'save'
        state['phase']='FINISHED' if shootout(state)['winner'] else 'REVIEW'
    else:
        state['phase']='FINISHED' if state['position']==state['rules']['questions'] else 'REVIEW'
    if state['phase']=='FINISHED':state['finished_at']=now


def tick(state,now):
    if state['phase'] in ('FINISHED','ABANDONED'):return
    if state['phase']=='ANSWERING' and now>=state['deadline']:
        resolve(state,None,None,state['deadline'])
    if state['phase']!='FINISHED' and now-state['created_at']>=state['rules']['max_run_ms']:
        state.update(phase='ABANDONED',finished_at=now)


def advance(state,previous,now):
    if state['position']==previous+1:return
    if state['position']!=previous or state['phase'] not in ('READY','REVIEW'):
        raise SoloError('This question cannot be opened')
    if previous>=len(state['deck']):raise SoloError('The next sudden-death pair has not been reserved')
    state.update(position=previous+1,phase='ANSWERING',opened_at=now,deadline=now+state['rules']['answer_ms'])


def answer(state,position,option,request_id,now):
    for entry in state['history']:
        if entry['request_id']==request_id:
            if entry['position']==position and entry['option_id']==option:return
            raise SoloError('Request ID already used for another answer')
    if state['phase']!='ANSWERING' or position!=state['position'] or not state['opened_at']<=now<state['deadline']:
        raise SoloError('The answer window is closed')
    if option not in {o['id'] for o in state['deck'][position-1]['options']}:
        raise SoloError('Unknown answer option')
    resolve(state,option,request_id,now)


def rewards(state):
    correct=sum(a['correct'] for a in state['history'])
    base=correct*state['rules']['xp_per_correct']
    total=len(state['history']) if is_shootout(state) else state['rules']['questions']
    perfect=state['phase']=='FINISHED' and correct==total and total>0
    won=is_shootout(state) and state['phase']=='FINISHED' and shootout(state)['winner']=='player'
    if state['rules'].get('bonus_mode')=='win':
        multiplier=state['rules']['win_multipliers'][state['difficulty']] if won else 1
    else:multiplier=state['rules']['perfect_multipliers'][state['difficulty']] if perfect else 1
    return {'correct':correct,'base_xp':base,'bonus_xp':base*(multiplier-1),'total_xp':base*multiplier,
            'multiplier':multiplier,'perfect':perfect,'won':won,
            'streak_eligible':state['phase']=='FINISHED' and len(state['history'])==total and all(a['option_id'] is not None for a in state['history'])}


def view(state,now):
    result={k:deepcopy(state[k]) for k in ('phase','position','difficulty','category','deadline','rules')}
    result.update(server_now=now,question=None,review=[],**rewards(state))
    result['end_reason']=state.get('end_reason')
    if is_shootout(state):
        result['shootout']=shootout(state)
        result['role']='shooter' if not state['position'] or state['position']%2 else 'keeper'
        result['answered']=len(state['history'])
    if state['position']:
        q=state['deck'][state['position']-1]
        result['question']={k:deepcopy(q[k]) for k in ('text','options')}
    for a in state['history']:
        q=state['deck'][a['position']-1]
        result['review'].append({**a,**{k:deepcopy(q[k]) for k in ('text','options','correct','explanation','authority')},'is_correct':a['correct']})
    return result


def streak(days,today):
    days=sorted(set(days));longest=current=0;previous=None
    for day in days:
        current=current+1 if previous and day==previous+timedelta(days=1) else 1
        longest=max(longest,current);previous=day
    if not previous or previous<today-timedelta(days=1):current=0
    return {'current':current,'longest':longest,'completed_today':today in days}
