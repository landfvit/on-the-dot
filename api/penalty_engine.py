"""Deterministic penalty rules. All times are server epoch milliseconds."""
from copy import deepcopy

RULES={'version':'penalties-v1','target':10,'countdown_ms':3000,'answer_ms':12000,
       'tie_ms':150,'result_ms':2500,'reconnect_ms':20000,'max_match_ms':1800000,'solo_shots':10,'solo_manual_next':True}


class GameError(ValueError):pass


def outcome(shooter,keeper,tie_ms=150):
    if shooter and shooter['correct']:
        if not keeper or not keeper['correct']:return 'goal'
        difference=shooter['elapsed_ms']-keeper['elapsed_ms']
        if abs(difference)<tie_ms:return 'replay'
        return 'goal' if difference<0 else 'save'
    return 'save' if keeper and keeper['correct'] else 'miss'


def create(mode,player,name,deck,now,first=0):
    rules=dict(RULES)
    if mode=='solo':rules['solo_shots']=min(rules['solo_shots'],len(deck))
    return {'mode':mode,'phase':'LOBBY','version':1,'rules':rules,'created_at':now,
        'started_at':None,'last_tick':now,'players':[{'id':player,'name':name,'ready':False,'seen':now}],
        'score':[0,0],'attempts':[0,0],'stats':[{'correct':0,'answered':0,'timeouts':0,'saves':0} for _ in range(2)],
        'first':first,'shooter':first if mode=='pvp' else 0,'slot':0,'pair':1,
        'deck':deepcopy(deck),'cursor':0,'round':None,'history':[],'winner':None,'reason':None}


def finish(state,phase,reason,winner=None):
    state.update(phase=phase,reason=reason,winner=winner)
    state['version']+=1


def schedule(state,now):
    if state['cursor']>=len(state['deck']):
        finish(state,'ABANDONED','question_pool_exhausted');return
    index=state['cursor'];state['cursor']+=1
    previous=state['round']
    state['round']={'id':index+1,'question_index':index,'answers':{},'outcome':None,
        'replay_of':previous['id'] if previous and previous['outcome']=='replay' else None,
        'shooter':state['shooter'],'pair':state['pair'],'slot':state['slot'],
        'opens_at':now+state['rules']['countdown_ms'],
        'deadline':now+state['rules']['countdown_ms']+state['rules']['answer_ms']}
    state['phase']='COUNTDOWN';state['version']+=1


def join(state,player,name,now):
    if any(p['id']==player for p in state['players']):return
    if state['mode']!='pvp' or state['phase']!='LOBBY' or len(state['players'])>=2:
        raise GameError('Room is full or already started')
    state['players'].append({'id':player,'name':name,'ready':False,'seen':now});state['version']+=1


def ready(state,player,now):
    if state['phase']!='LOBBY':return
    next(p for p in state['players'] if p['id']==player)['ready']=True
    state['version']+=1
    required=1 if state['mode']=='solo' else 2
    if len(state['players'])==required and all(p['ready'] for p in state['players']):
        state['started_at']=now;schedule(state,now)


def resolve(state,now):
    round_=state['round'];shooter=round_['shooter'];answers=round_['answers']
    shot=answers.get(state['players'][shooter]['id'])
    keeper=answers.get(state['players'][1-shooter]['id']) if state['mode']=='pvp' else None
    result=outcome(shot,keeper,state['rules']['tie_ms'])
    round_['outcome']=result;round_['resolved_at']=now
    round_['next_at']=now+state['rules']['result_ms']
    for i,p in enumerate(state['players']):
        a=answers.get(p['id']);stats=state['stats'][i]
        stats['answered']+=int(a is not None);stats['correct']+=int(bool(a and a['correct']))
        stats['timeouts']+=int(a is None)
    if result=='goal':state['score'][shooter]+=1
    if result=='save':state['stats'][1-shooter]['saves']+=1
    if result!='replay':
        state['attempts'][shooter]+=1
        if state['mode']=='pvp':
            state['shooter']=1-shooter;state['slot']=1-state['slot']
            if state['slot']==0:state['pair']+=1
    state['history'].append(deepcopy(round_));state['phase']='RESOLVED';state['version']+=1
    if state['mode']=='solo' and state['attempts'][0]>=state['rules']['solo_shots']:
        finish(state,'FINISHED','solo_complete',0)
    elif state['mode']=='pvp' and result!='replay' and state['slot']==0:
        a,b=state['score']
        if max(a,b)>=state['rules']['target'] and a!=b:
            finish(state,'FINISHED','target_reached',0 if a>b else 1)


def tick(state,now):
    if state['phase'] in ('FINISHED','ABANDONED'):return
    if now-(state['started_at'] if state['started_at'] is not None else state['created_at'])>state['rules']['max_match_ms']:
        finish(state,'ABANDONED','time_limit');return
    if state['phase']!='LOBBY' and now-state['last_tick']>25000:
        finish(state,'ABANDONED','technical_interruption');return
    state['last_tick']=now
    if state['phase']=='COUNTDOWN' and now>=state['round']['opens_at']:
        state['phase']='ANSWERING';state['version']+=1
    if state['phase']=='ANSWERING' and now>=state['round']['deadline']:resolve(state,now)
    if state['phase']=='RESOLVED' and now>=state['round']['next_at']:
        if state['mode']=='solo' and state['rules'].get('solo_manual_next'):return
        offline=[i for i,p in enumerate(state['players']) if now-p['seen']>state['rules']['reconnect_ms']]
        if offline:
            if state['mode']=='pvp' and len(offline)==1:
                finish(state,'FINISHED','disconnect_forfeit',1-offline[0])
            else:finish(state,'ABANDONED','players_disconnected')
        elif any(now-p['seen']>3000 for p in state['players']):return
        else:schedule(state,now)


def submit(state,player,round_id,option,request_id,now):
    if player not in {p['id'] for p in state['players']}:raise GameError('Not a room participant')
    round_=state['round']
    if not round_ or round_['id']!=round_id:raise GameError('This penalty is no longer current')
    existing=round_['answers'].get(player)
    if existing:
        if existing['option_id']==option and existing['request_id']==request_id:return False
        raise GameError('Your answer is already locked')
    if state['phase']!='ANSWERING' or not round_['opens_at']<=now<round_['deadline']:
        raise GameError('The answer window is closed')
    question=state['deck'][round_['question_index']]
    if option not in {o['id'] for o in question['options']}:raise GameError('Unknown answer option')
    round_['answers'][player]={'option_id':option,'request_id':request_id,
        'received_at':now,'elapsed_ms':now-round_['opens_at'],'correct':option==question['correct']}
    state['version']+=1
    if len(round_['answers'])==len(state['players']):resolve(state,now)
    return True


def view(state,player,now):
    me=next(i for i,p in enumerate(state['players']) if p['id']==player)
    public={k:deepcopy(state[k]) for k in ('mode','phase','version','rules','score','attempts','stats','winner','reason')}
    # Running statistics must not reveal correctness before the penalty resolves.
    public.update(me=me,server_now=now,players=[{k:p[k] for k in ('name','ready')} for p in state['players']],
        round=None,question=None,history=[{'outcome':r['outcome'],'shooter':r['shooter']} for r in state['history']])
    # The lobby intro needs the server-assigned opening role before Ready.
    # Revealing this role does not expose the question, correct answer or deck.
    public['initial_shooter'] = state['first'] if state['mode'] == 'pvp' else 0
    round_=state['round']
    if round_:
        public['round']={k:round_[k] for k in ('id','shooter','pair','slot','opens_at','deadline')}
        own=round_['answers'].get(player)
        public['round']['own_option']=own['option_id'] if own else None
        if state['phase']!='COUNTDOWN' and now>=round_['opens_at']:
            question=state['deck'][round_['question_index']]
            public['question']={k:deepcopy(question[k]) for k in ('text','options')}
            if round_['outcome']:
                public['round'].update(outcome=round_['outcome'],next_at=round_['next_at'],
                    answers=[{k:a[k] for k in ('option_id','correct','elapsed_ms')} if
                        (a:=round_['answers'].get(p['id'])) else None for p in state['players']])
                public['question'].update(correct=question['correct'],explanation=question['explanation'])
                if 'authority' in question:
                    public['question'].update(authority=question['authority'],validation_status=question['validation_status'])
    return public
