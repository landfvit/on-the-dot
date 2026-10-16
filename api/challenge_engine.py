"""Daily and friend rules. Database transactions own time and serialize commands."""
from copy import deepcopy
from api import solo_engine as solo
from api import penalty_engine as penalty

XP={'easy':10,'medium':20,'hard':30}
TERMINAL=('FINISHED','ABANDONED')
# Match the inter-penalty playback ratio in stadium_config.js. Frozen rules in
# already-started duels keep their original waits and 15-second answer windows.
BETWEEN_SHOT_SPEED=1.3


def daily_create(deck,now,expires_at,ranked=True):
    if not deck or len({q['question_id'] for q in deck})!=len(deck):
        raise solo.SoloError('A daily challenge needs unused questions')
    rules={**deepcopy(solo.RULES),'version':'daily-survival-v2','format':'daily_survival',
           'lives':3,'ranked':ranked,'xp_per_correct':10,'bonus_mode':'none',
           'win_multipliers':{'mixed':1},'perfect_multipliers':{'mixed':1},'questions':len(deck)}
    return {'deck':deepcopy(deck),'difficulty':'mixed','category':{'code':'ALL','label':'Daily Challenge','topic_label':'All clubs'},
            'rules':rules,'phase':'READY','position':0,'deadline':None,'opened_at':None,
            'created_at':now,'expires_at':expires_at,'finished_at':None,'history':[]}


def daily_tick(s,now):
    if s['phase'] in TERMINAL:return
    if now>=s['expires_at']:
        s.update(phase='ABANDONED',finished_at=s['expires_at'],end_reason='daily_reset');return
    if daily_survival(s):
        if s['phase']=='ANSWERING' and now>=s['deadline']:
            daily_resolve(s,None,None,s['deadline'])
    else:solo.tick(s,now)
    daily_exhaust(s,now)


def daily_survival(s):
    return s['rules'].get('format')=='daily_survival'


def daily_resolve(s,option,request_id,now):
    q=s['deck'][s['position']-1]
    correct=option is not None and option==q['correct']
    s['history'].append(dict(position=s['position'],option_id=option,request_id=request_id,
        correct=correct,elapsed_ms=min(s['rules']['answer_ms'],max(0,now-s['opened_at'])),
        answered_at=now,role='shooter',outcome='goal' if correct else 'miss' if option is None else 'save'))
    s['phase']='REVIEW'
    if sum(not a['correct'] for a in s['history'])>=s['rules']['lives']:
        s.update(phase='FINISHED',finished_at=now,end_reason='lives_exhausted')
    daily_exhaust(s,now)


def daily_answer(s,position,option,request_id,now):
    # Legacy, already-started games retain their frozen shootout rules.
    if not daily_survival(s):
        solo.answer(s,position,option,request_id,now);daily_exhaust(s,now);return
    for entry in s['history']:
        if entry['request_id']==request_id:
            if entry['position']==position and entry['option_id']==option:return
            raise solo.SoloError('Request ID already used for another answer')
    if s['phase']!='ANSWERING' or position!=s['position'] or not s['opened_at']<=now<s['deadline']:
        raise solo.SoloError('The answer window is closed')
    if option not in {o['id'] for o in s['deck'][position-1]['options']}:
        raise solo.SoloError('Unknown answer option')
    daily_resolve(s,option,request_id,now)


def daily_exhaust(s,now):
    # Evaluate the sporting result first. Running out never changes an already
    # decided loss, and an empty pre-game pool can never grant a win.
    if s['phase']=='REVIEW' and len(s['history'])==len(s['deck']) and s['history']:
        s.update(phase='FINISHED',finished_at=now,end_reason='daily_pool_exhausted')


def daily_view(s,now):
    result=solo.view(s,now)
    correct=sum(a['correct'] for a in s['history'])
    total=sum(XP[s['deck'][a['position']-1]['difficulty']] for a in s['history'] if a['correct'])
    if daily_survival(s):
        mistakes=len(s['history'])-correct
        result.update(role='shooter',answered=len(s['history']),survival={
            'goals':correct,'mistakes':mistakes,'lives':max(0,s['rules']['lives']-mistakes),
            'max_lives':s['rules']['lives'],'ranked':s['rules']['ranked'],
            'next_role':'shooter','attempts':[{'goal':a['correct'],'number':a['position']} for a in s['history']]})
    elif s.get('end_reason')=='daily_pool_exhausted':result['shootout']['winner']='player'
    result.update(correct=correct,base_xp=total,total_xp=total,bonus_xp=0,multiplier=1,
                  won=not daily_survival(s) and s['phase']=='FINISHED' and result['shootout']['winner']=='player',mode='daily')
    if s['position']:result['rules']['xp_per_correct']=XP[s['deck'][s['position']-1]['difficulty']]
    for a in result['review']:a['xp']=XP[s['deck'][a['position']-1]['difficulty']] if a['is_correct'] else 0
    return result


def friend_create(player,name,difficulty,now):
    s=penalty.create('pvp',player,name,[],now,0)
    s['rules'].update(version='friend-shootout-v2',initial_kicks=5,answer_ms=15000,
                      countdown_ms=round(4000/BETWEEN_SHOT_SPEED),result_ms=round(5500/BETWEEN_SHOT_SPEED),
                      reconnect_ms=30000,tie_ms=150)
    s.update(difficulty=difficulty,finished_at=None)
    return s


def friend_finish(s,now,reason,winner=None):
    penalty.finish(s,'FINISHED' if winner is not None else 'ABANDONED',reason,winner)
    s['finished_at']=now


def friend_custom_finish(s,now):
    """A finite custom deck can end in a draw without adding/repeating questions."""
    winner=None if s['score'][0]==s['score'][1] else int(s['score'][1]>s['score'][0])
    penalty.finish(s,'FINISHED','custom_questions_complete',winner)
    s['finished_at']=now


def sporting_winner(scores,kicks):
    if max(kicks)<=5:
        for side in (0,1):
            if scores[side]>scores[1-side]+5-kicks[1-side]:return side
    elif kicks[0]==kicks[1] and scores[0]!=scores[1]:return int(scores[1]>scores[0])
    return None


def friend_outcome(shot,keeper,tie_ms):
    if not (shot and shot['correct']) and not (keeper and keeper['correct']):return 'replay'
    return penalty.outcome(shot,keeper,tie_ms)


def friend_resolve(s,now):
    r=s['round'];shooter=r['shooter'];answers=r['answers']
    shot=answers.get(s['players'][shooter]['id']);keeper=answers.get(s['players'][1-shooter]['id'])
    result=friend_outcome(shot,keeper,s['rules']['tie_ms'])
    r.update(outcome=result,resolved_at=now,next_at=now+s['rules']['result_ms'])
    for i,p in enumerate(s['players']):
        answer=answers.get(p['id']);stats=s['stats'][i]
        stats['answered']+=int(answer is not None);stats['correct']+=int(bool(answer and answer['correct']))
        stats['timeouts']+=int(answer is None)
        stats['idle']=0 if answer else stats.get('idle',0)+1
    if result=='goal':s['score'][shooter]+=1
    if result=='save':s['stats'][1-shooter]['saves']+=1
    if result!='replay':
        s['attempts'][shooter]+=1;s['shooter']=1-shooter;s['slot']=1-s['slot']
        if not s['slot']:s['pair']+=1
    s['history'].append(deepcopy(r));s['phase']='RESOLVED';s['version']+=1
    winner=sporting_winner(s['score'],s['attempts'])
    if winner is not None:friend_finish(s,now,'shootout_complete',winner)
    else:
        idle=[i for i,stats in enumerate(s['stats']) if stats.get('idle',0)>=2]
        if idle:friend_finish(s,now,'inactivity',1-idle[0] if len(idle)==1 else None)


def friend_tick(s,now):
    if s['phase'] in TERMINAL:return
    if now-s['created_at']>=s['rules']['max_match_ms']:
        friend_finish(s,now,'time_limit');return
    # Closing the page normally sends /leave. A lost connection or killed
    # browser cannot always deliver it, including while waiting in the lobby.
    offline=[i for i,p in enumerate(s['players']) if now-p['seen']>s['rules']['reconnect_ms']]
    if offline:
        remaining=[i for i in range(len(s['players'])) if i not in offline]
        friend_finish(s,now,'disconnect_forfeit',remaining[0] if len(remaining)==1 else None)
        return
    if s['phase']=='COUNTDOWN' and now>=s['round']['opens_at']:
        s['phase']='ANSWERING';s['version']+=1
    if s['phase']=='ANSWERING' and now>=s['round']['deadline']:
        friend_resolve(s,s['round']['deadline'])
    # Next questions are scheduled by the route after checking both players'
    # connection state and replenishing a finite approved question deck.


def friend_submit(s,player,round_id,option,request_id,now):
    # Idempotency also covers retries after a later round has opened.
    for r in [*s['history'],*([s['round']] if s['round'] else [])]:
        old=r['answers'].get(player)
        if old and old['request_id']==request_id:
            if r['id']==round_id and old['option_id']==option:return
            raise penalty.GameError('Request ID already used for another answer')
    r=s['round']
    if not r or r['id']!=round_id or s['phase']!='ANSWERING' or not r['opens_at']<=now<r['deadline']:
        raise penalty.GameError('The answer window is closed')
    if player in r['answers']:raise penalty.GameError('Your answer is already locked')
    q=s['deck'][r['question_index']]
    if option not in {o['id'] for o in q['options']}:raise penalty.GameError('Unknown answer')
    r['answers'][player]={'option_id':option,'request_id':request_id,'received_at':now,
                         'elapsed_ms':now-r['opens_at'],'correct':option==q['correct']}
    s['version']+=1
    if len(r['answers'])==2:friend_resolve(s,now)
