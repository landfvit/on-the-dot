"""Generate evidence-linked trivia drafts, never publish or invent missing facts.

Run with an explicit season scope. A quota is not permission to relax quality
gates. The companion checker independently reads the referenced source rows.
"""
import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
import json
from itertools import combinations
from pathlib import Path
import random
import re
import unicodedata

from api.database import get_connection

VERSION='curated-football-v1'
BIG={33,40,42,47,49,50}
TRANSFER_POOLS=[
    ['Sevilla','Valencia','Villarreal','Real Betis','Real Sociedad','Athletic Club','Atletico Madrid','Real Madrid','Barcelona'],
    ['Lyon','Marseille','Lille','Monaco','Rennes','Bordeaux','Nice','Toulouse','Montpellier','Paris Saint Germain'],
    ['Bayern Munich','Borussia Dortmund','Bayer Leverkusen','RB Leipzig','Wolfsburg','Schalke 04','Werder Bremen','Borussia Monchengladbach'],
    ['Roma','Lazio','Napoli','Juventus','AC Milan','Inter','Fiorentina','Atalanta','Torino','Sampdoria','Bologna'],
    ['Ajax','PSV Eindhoven','Feyenoord','AZ Alkmaar','Twente','Vitesse'],
    ['FC Porto','Porto','Benfica','Sporting CP','Sporting Lisbon','SC Braga'],
    ['Santos','Flamengo','Corinthians','Gremio','Palmeiras','Sao Paulo','Fluminense'],
]
TOPICS={'brace':'Player milestones','hat_trick':'Player milestones','season_goals':'Player milestones',
        'scoring_club':'Player milestones','club_scorer':'Player milestones','transfer':'Transfers and loans',
        'nationality':'Club identity','comeback':'Match recognition','big_win':'Match recognition',
        'teammates':'Player milestones','club_trail':'Transfers and loans'}


def key(text):
    return re.sub(r'[^a-z0-9]+',' ',unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().lower()).strip()


def club_key(text):
    normalized=key(text)
    for a,b in {'fc porto':'porto','sporting lisbon':'sporting cp','newcastle united':'newcastle',
                'blackburn rovers':'blackburn','tottenham hotspur':'tottenham','west ham united':'west ham',
                'swansea city':'swansea','leicester city':'leicester','norwich city':'norwich',
                'huddersfield town':'huddersfield','brighton hove albion':'brighton',
                'ipswich town':'ipswich','sheffield united':'sheffield utd'}.items():
        if normalized==a:return b
    return normalized


def name(player):
    short=player['player_name']
    known={172:'Dele Alli',67971:'Marc Guehi',2935:'Harry Maguire',18908:'Joe Hart',
           19497:'Bruno Martins Indi',19144:'Boaz Myhill',37146:'Cuco Martina',136723:'Noni Madueke',
           51199:'Nedum Onuoha',2771:'Ola Aina',2769:'Semi Ajayi',13109:'Sone Aluko',19145:'Tosin Adarabioyo',31032:'Gervinho',18816:'Arthur Masuaku',892:'Chris Smalling',
           18955:'Danny Ings',19366:'Ollie Watkins'}
    if player['player_id'] in known:return known[player['player_id']]
    if re.match(r'^[A-Z]\. ',short) and player['first_name']:
        first=next((word for word in player['first_name'].split() if key(word).startswith(key(short[0]))),None)
        return first+' '+short.split('. ',1)[1] if first else short
    return short


def season_label(n):return f'{n}/{(n+1)%100:02d}'


def choices(answer,pool,rng):
    alternatives=sorted(set(str(p) for p in pool if key(str(p))!=key(str(answer))))
    if len(alternatives)<3:return None
    options=[str(answer),*rng.sample(alternatives,3)];rng.shuffle(options);return options


def load(conn,seasons):
    dataset=conn.execute('SELECT dataset_id FROM trivia_datasets WHERE sealed_at IS NOT NULL ORDER BY created_at DESC LIMIT 1').fetchone()['dataset_id']
    players={r['player_id']:r for r in conn.execute('SELECT player_id,player_name,first_name,nationality FROM players')}
    teams={r['team_id']:r['team_name'] for r in conn.execute('SELECT team_id,team_name FROM teams')}
    fixtures={r['fixture_id']:r for r in conn.execute("SELECT * FROM fixtures WHERE league_id=39 AND season=ANY(%s) AND status='FT'",(seasons,))}
    complete=[s for s in seasons if sum(f['season']==s for f in fixtures.values())==380]
    fixtures={i:f for i,f in fixtures.items() if f['season'] in complete}
    stats=conn.execute('SELECT player_id,team_id,season,appearances,goals_total,assists FROM player_season_statistics WHERE league_id=39 AND season=ANY(%s) ORDER BY season,team_id,player_id',(complete,)).fetchall()
    quality={r['fixture_id'] for r in conn.execute('SELECT fixture_id FROM trivia_player_data_quality WHERE dataset_id=%s AND scorers_valid',(dataset,))}
    events=conn.execute("SELECT fixture_id,team_id,player_id FROM trivia_event_facts WHERE dataset_id=%s AND event_type='Goal' AND event_detail IN ('Normal Goal','Penalty')",(dataset,)).fetchall()
    goals=Counter((e['fixture_id'],e['team_id'],e['player_id']) for e in events if e['fixture_id'] in fixtures and e['fixture_id'] in quality and e['player_id'])
    transfers=conn.execute('SELECT * FROM player_transfers WHERE extract(year from transfer_date) BETWEEN %s AND %s',(min(complete),max(complete)+1)).fetchall()
    existing=[r['content'] for r in conn.execute('SELECT content FROM trivia_bank_questions')]
    return dataset,players,teams,fixtures,stats,goals,quality,transfers,existing


def generate(conn,seasons,target=1000):
    rng=random.Random(77331)
    dataset,players,teams,fixtures,stats,goals,quality,transfers,existing=load(conn,seasons)
    candidates=[];rejected=Counter();apps=Counter();totals=Counter();club_players=defaultdict(set)
    for s in stats:
        apps[s['player_id']]+=s['appearances'] or 0
        if (s['appearances'] or 0)>=10 and (s['goals_total'] or 0)>=2:club_players[s['team_id'],s['season']].add(s['player_id'])
    for (fixture,team,player),count in goals.items():totals[fixtures[fixture]['season'],team,player]+=count
    scoring_clues=defaultdict(set)
    incomplete_clues=set()
    for f in fixtures.values():
        if f['fixture_id'] in quality:continue
        for a,b in (('home','away'),('away','home')):
            incomplete_clues.add((f['season'],f[a+'_team_id'],f[b+'_team_id'],f[a+'_goals'],f[b+'_goals']))
    for (ident,team,player),count in goals.items():
        f=fixtures[ident];home=f['home_team_id']==team
        gf=f['home_goals'] if home else f['away_goals'];ga=f['away_goals'] if home else f['home_goals'];opp=f['away_team_id'] if home else f['home_team_id']
        scoring_clues[f['season'],team,opp,gf,ga,count].add(player)
    popular={p for p,n in apps.items() if n>=100}
    # Players famous before the first covered season must not become "Hard"
    # merely because only the tail of their career is in this dataset.
    legacy={'john terry','florent malouda','didier drogba','frank lampard','steven gerrard','ryan giggs',
            'paul scholes','rio ferdinand','nemanja vidic','petr cech','edwin van der sar','thierry henry',
            'nicolas anelka','dimitar berbatov','michael owen','fernando torres','rafael van der vaart'}
    prominence={p:max(n,300 if p in players and key(name(players[p])) in legacy else 0) for p,n in apps.items()}
    countries=[players[p]['nationality'] for p in popular if p in players and players[p]['nationality']]
    club_pool=[teams[t] for t in {f[k] for f in fixtures.values() for k in ('home_team_id','away_team_id')}]
    old_by_answer=defaultdict(list)
    for q in existing:old_by_answer[key(q['answer'])].append(key(q['question']))

    def add(family,difficulty,question,answer,pool,fact,subject,evidence):
        if len(question)>240 or not answer:return
        clean=key(question)
        # Comparing within the same answer catches changed wording as well as
        # literal duplicates without discarding unrelated player questions.
        for old in old_by_answer[key(str(answer))]:
            if SequenceMatcher(None,clean,old).ratio()>.73:
                rejected['existing_near_duplicate']+=1;return
        opts=choices(answer,pool,rng)
        if not opts:return
        candidates.append({'family':family,'difficulty':difficulty,'question':question,'answer':str(answer),
            'options':opts,'correct':opts.index(str(answer)),'topic':TOPICS[family],'fact_key':fact,'subject':subject,
            'evidence':{'status':'matched','method':'local_source_crosscheck','dataset_id':str(dataset),'family':family,**evidence}})

    # Whole-season scoring numbers must agree with complete goal-event coverage.
    verified=[]
    for s in stats:
        player=s['player_id'];team=s['team_id'];year=s['season'];g=s['goals_total'] or 0
        if player not in players or g<8 or apps[player]<60:continue
        matches=[f for f in fixtures.values() if f['season']==year and team in (f['home_team_id'],f['away_team_id'])]
        if len(matches)!=38 or any(f['fixture_id'] not in quality for f in matches) or totals[year,team,player]!=g:
            rejected['season_scoring_coverage_or_disagreement']+=1;continue
        verified.append(s);person=name(players[player]);label=season_label(year);club=teams[team]
        fact=f'player-season:{year}:{team}:{player}'
        evidence={'season':year,'team_id':team,'player_id':player,'goals':g}
        add('scoring_club','easy' if apps[player]>=150 else 'medium',f'For which club did {person} score {g} Premier League goals in {label}?',club,club_pool,fact,f'p:{player}',evidence)
        nums=[n for n in range(max(1,g-15),g+16) if n==g or abs(n-g)>=4]
        # Fixed four-goal spacing makes a numeric answer a football question,
        # not a guessing contest between near-identical values.
        base=max(1,g-4*rng.randrange(4));nums=list(range(base,base+16,4))
        if g not in nums:nums=[g,g+4,g+8,g+12]
        add('season_goals','hard' if g<15 else 'medium',f'How many Premier League goals did {person} score for {club} in {label}?',str(g),nums,fact,f'p:{player}',evidence)
    groups=defaultdict(list)
    for s in stats:groups[s['team_id'],s['season']].append(s)
    for (team,year),rows in groups.items():
        ordered=sorted(rows,key=lambda s:s['goals_total'] or 0,reverse=True)
        first=ordered[0]
        if first not in verified or len(ordered)<2 or first['goals_total']==ordered[1]['goals_total']:continue
        p=first['player_id'];pool=[name(players[s['player_id']]) for s in rows if s['player_id'] in players and (s['appearances'] or 0)>=12 and (s['goals_total'] or 0)>=2]
        add('club_scorer','easy' if team in BIG and first['goals_total']>=15 else 'medium',
            f'Who led {teams[team]} in Premier League goals in {season_label(year)}?',name(players[p]),pool,
            f'club-scorer:{team}:{year}',f'p:{p}',{'season':year,'team_id':team,'player_id':p,'goals':first['goals_total']})
    # Match facts focus on braces, hat-tricks, major wins and comebacks.
    for (ident,team,player),count in goals.items():
        if count<2 or player not in players or apps[player]<60:continue
        f=fixtures[ident];home=f['home_team_id']==team;gf=f['home_goals'] if home else f['away_goals'];ga=f['away_goals'] if home else f['home_goals'];opp=f['away_team_id'] if home else f['home_team_id']
        if gf<=ga or sum(t==team and i==ident and n==count for (i,t,p),n in goals.items())!=1:continue
        if (f['season'],team,opp,gf,ga) in incomplete_clues:
            rejected['ambiguous_match_coverage']+=1;continue
        if scoring_clues[f['season'],team,opp,gf,ga,count]!={player}:continue
        person=name(players[player]);label=season_label(f['season']);club=teams[team]
        pool=[name(players[p]) for p in club_players[team,f['season']] if p in players and p!=player]
        number={2:'twice',3:'a hat-trick',4:'four goals',5:'five goals'}.get(count)
        if not number:continue
        family='hat_trick' if count>=3 else 'brace'
        diff='easy' if count>=3 and apps[player]>=150 else 'medium' if team in BIG else 'hard'
        add(family,diff,f'Who scored {number} in {club}\'s {gf}-{ga} Premier League win over {teams[opp]} in {label}?',person,pool,
            f'match-scorer:{ident}:{player}',f'p:{player}',{'fixture_id':ident,'player_id':player,'team_id':team,'goals':count,'season':f['season']})
    for ident,f in fixtures.items():
        home=f['home_goals']>f['away_goals'];team=f['home_team_id'] if home else f['away_team_id'];opp=f['away_team_id'] if home else f['home_team_id']
        gf=f['home_goals'] if home else f['away_goals'];ga=f['away_goals'] if home else f['home_goals'];label=season_label(f['season'])
        if gf<=ga:continue
        hf=f['halftime_home'] if home else f['halftime_away'];ha=f['halftime_away'] if home else f['halftime_home']
        ev={'fixture_id':ident,'team_id':team,'season':f['season']}
        similar=[]
        for other in fixtures.values():
            if other['season']!=f['season']:continue
            for a,b in (('home','away'),('away','home')):
                if other[b+'_team_id']==opp and other[a+'_goals']==gf and other[b+'_goals']==ga:
                    similar.append((other[a+'_team_id'],other['halftime_'+a],other['halftime_'+b]))
        if hf is not None and ha is not None and ha-hf>=1 and gf>=3 and {t for t,h,a in similar if (h,a)==(hf,ha)}=={team}:
            add('comeback','medium' if team in BIG else 'hard',f'Which club came from {hf}-{ha} down at half-time to beat {teams[opp]} {gf}-{ga} in the {label} Premier League?',teams[team],club_pool,f'match-result:{ident}',f't:{team}',ev)
        if gf>=4 and opp in BIG and {t for t,h,a in similar}=={team}:
            add('big_win','easy' if gf-ga>=4 else 'hard',f'Which club beat {teams[opp]} {gf}-{ga} in the {label} Premier League?',teams[team],club_pool,f'match-result:{ident}',f't:{team}',ev)
    # Incoming transfers require actual PL appearances for the destination.
    transfer_groups=defaultdict(list)
    for t in transfers:
        year=t['transfer_date'].year;pid=t['player_id'];dest=t['team_in_id']
        if pid in players and apps[pid]>=60 and any(s['player_id']==pid and s['team_id']==dest and year-1<=s['season']<=year+1 and (s['appearances'] or 0)>=10 for s in stats):
            if 'loan' not in (t['transfer_type'] or '').lower() and t['team_out_name'] and t['team_out_id']!=dest:transfer_groups[pid,dest,year].append(t)
    for (pid,dest,year),rows in transfer_groups.items():
        if len({r['team_out_id'] for r in rows})!=1:continue
        t=rows[0];person=name(players[pid]);club=teams.get(dest,t['team_in_name']);answer=t['team_out_name']
        regional=next((group for group in TRANSFER_POOLS if club_key(answer) in {club_key(n) for n in group}),None)
        if regional is None and club_key(answer) in {club_key(n) for n in club_pool}:regional=club_pool
        pool=list({club_key(n):n for n in (regional or [*club_pool,*TRANSFER_POOLS[0],*TRANSFER_POOLS[1]])
                   if club_key(n) not in (club_key(answer),club_key(club))}.values())
        add('transfer','easy' if apps[pid]>=150 and dest in BIG else 'medium' if apps[pid]>=150 else 'hard',
            f'From which club did {club} sign {person} in {year}?',answer,pool,f'transfer:{pid}:{dest}:{year}',f'p:{pid}',
            {'transfer_id':t['transfer_id'],'player_id':pid,'team_id':dest,'year':year})
    for pid in popular:
        p=players.get(pid)
        if not p or not p['nationality'] or apps[pid]<150:continue
        add('nationality','easy',f'What is {name(p)}\'s football nationality?',p['nationality'],countries,
            f'nationality:{pid}',f'p:{pid}',{'player_id':pid})
    memberships=defaultdict(set);career=defaultdict(dict)
    for s in stats:
        if (s['appearances'] or 0)>=15 and s['player_id'] in players:
            memberships[s['player_id'],s['season']].add(s['team_id'])
            career[s['player_id']].setdefault(s['team_id'],s['season'])
    for (team,year),group in groups.items():
        eligible=sorted({s['player_id'] for s in group if (s['appearances'] or 0)>=15 and s['player_id'] in players and apps[s['player_id']]>=60},key=lambda p:-apps[p])
        pairs=list(combinations(eligible,2));rng.shuffle(pairs)
        per_level=Counter()
        for a,b in pairs:
            shared=memberships[a,year]&memberships[b,year]
            if shared!={team}:continue
            diff='easy' if min(prominence[a],prominence[b])>=180 else 'medium' if min(prominence[a],prominence[b])>=100 else 'hard'
            if per_level[diff]>=2:continue
            per_level[diff]+=1
            add('teammates',diff,f'Which Premier League club had both {name(players[a])} and {name(players[b])} in {season_label(year)}?',teams[team],club_pool,
                f'teammates:{min(a,b)}:{max(a,b)}',f'pair:{min(a,b)}:{max(a,b)}',{'season':year,'team_id':team,'players':[a,b]})
    for pid,clubs in career.items():
        if len(clubs)<3 or apps[pid]<60:continue
        trail=sorted(clubs.items(),key=lambda x:(x[1],x[0]))[:3]
        matching={p for p in players if all(t in memberships[p,y] for t,y in trail)}
        if matching!={pid}:continue
        clue=', '.join(f'{teams[t]} in {season_label(y)}' for t,y in trail)
        pool=[name(players[p]) for p in popular if p in players and p not in matching]
        add('club_trail','medium' if apps[pid]>=250 else 'hard',f'Who played Premier League football for {clue}?',name(players[pid]),pool,
            f'club-trail:{pid}',f'p:{pid}',{'player_id':pid,'trail':trail})
    # Round-robin family selection plus caps prevents a bank of one template.
    queues=defaultdict(list)
    rng.shuffle(candidates)
    for q in candidates:queues[q['difficulty'],q['family']].append(q)
    picked=[];facts=set();texts=set();subjects=Counter();families=Counter();counts=Counter()
    for diff in ('easy','medium','hard'):
        while counts[diff]<target:
            progress=False
            for family in TOPICS:
                queue=queues[diff,family]
                while queue:
                    q=queue.pop()
                    if q['fact_key'] in facts or key(q['question']) in texts or subjects[q['subject']]>=12 or families[diff,family]>=300:continue
                    picked.append(q);facts.add(q['fact_key']);texts.add(key(q['question']));subjects[q['subject']]+=1;families[diff,family]+=1;counts[diff]+=1;progress=True;break
                if counts[diff]>=target:break
            if not progress:break
    for n,q in enumerate(picked,1):
        e=q['evidence'];endpoint='fixtures/events?fixture='+str(e['fixture_id']) if 'fixture_id' in e else 'transfers?player='+str(e['player_id']) if q['family']=='transfer' else 'players?league=39&season='+str(e.get('season',max(seasons)))+'&id='+str(e.get('player_id',(e.get('players') or [0])[0]))
        q.update(id=f'CURATED-{n:05d}-GEN-001',section='General',check='Answer recomputed from the referenced local source records.',
                 sources=[{'title':'API-Football source endpoint. Requires provider access.','url':'https://v3.football.api-sports.io/'+endpoint}])
    return picked,{'version':VERSION,'dataset_id':str(dataset),'seasons':seasons,'requested_per_difficulty':target,
        'created':dict(counts),'shortfall':{d:target-counts[d] for d in ('easy','medium','hard')},
        'families':{f'{d}/{f}':n for (d,f),n in families.items()},'rejected':dict(rejected),'candidate_count':len(candidates),
        'publication':'draft_only','external_fact_check':False,'difficulty':'editorial heuristic, not calibrated from player performance'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--seasons',type=int,nargs='+',required=True);p.add_argument('--target',type=int,default=1000);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    with get_connection() as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        questions,report=generate(conn,args.seasons,args.target)
    args.output.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(questions,ensure_ascii=False,indent=2);report['sha256']=hashlib.sha256(raw.encode()).hexdigest()
    (args.output/'questions.json').write_text(raw)
    (args.output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
