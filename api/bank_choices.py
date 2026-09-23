"""Preserve explicit two/three-choice questions; type open-answer distractors."""
from collections import defaultdict
import re
import secrets

from api.penalty_bank import answer_kind,make_options,option_key
from api.trivia_bank_engine import canonical,normalized


def closed_answers(item):
    q=item['question'];answer=item['answer']
    if canonical(answer) in {'yes','no'}:return ['Yes','No']
    outcome=re.search(r': a (.+?) win, a draw, or a (.+?) win\?$',q)
    if outcome:return [outcome[1],'Draw',outcome[2]]
    if q.endswith('a win, draw or defeat?'):return ['Win','Draw','Defeat']
    pair=re.search(r': ([^?]+?) or ([^?]+?)\?$',q)
    if pair:return [pair[1],pair[2]]
    return None


def kind(item,clubs):
    a=item['answer'];topic=item['topic'];q=normalized(item['question'])
    if canonical(a).startswith('club:') or a in clubs:return 'club'
    if re.match(r'which (?:\w+ )?club\b',q):return 'club'
    if 'which country' in q:return 'country'
    if 'singer' in q or 'musician' in q or a=='Ed Sheeran':return 'musician'
    if topic in {'International identity','International context'}:return 'country'
    if topic=='Home colours':return 'kit_palette'
    if topic=='Equipment':return 'manufacturer'
    if topic=='Home grounds':return 'stadium'
    if topic in {'Managers','Title-winning managers'} or 'manager' in q:return 'manager'
    if a.startswith('UEFA ') or a in {'FA Cup','EFL Cup','Community Shield'}:return 'competition'
    if a.startswith('River '):return 'river'
    if a=='The robot':return 'celebration'
    if topic=='Badges and traditions':
        if 'industry' in q:return 'industry'
        if 'monogram' in q:return 'monogram'
        if 'tower' in q:return 'tower'
        return 'badge_object'
    if topic in {'Player awards','Golden Boot','Golden Glove','Assists and playmakers','Shirt-number recognition',
                 'Captains','Club scoring leaders','Season landmarks','Player roles'}:return 'player'
    if topic in {'Transfers and loans','Champions','Title races','Who played for whom?','Name the club',
                 'Promotion','Domestic cups','Big-score memories','Comebacks','Premier League arrivals'}:return 'club'
    return answer_kind(item)


def palette_key(value):
    return tuple(sorted(normalized(value).replace('claret','maroon').replace('gold','yellow').split(' and ')))


def pools_for(items):
    clubs={i['answer'] for i in items if i['topic']=='Transfers and loans'}
    pools=defaultdict(set)
    for item in items:
        if closed_answers(item):continue
        pools[kind(item,clubs)].add(item['answer'])
    pools['competition'].update({'UEFA Champions League','UEFA Europa League','UEFA Conference League','FA Cup','EFL Cup'})
    pools['river'].update({'River Tees','River Thames','River Mersey','River Tyne'})
    pools['celebration'].update({'The robot','The knee slide','The backflip','The samba'})
    pools['manufacturer'].update({'Nike','adidas','Puma','Umbro'})
    pools['musician'].update({'Ed Sheeran','Stormzy','Dave','Sam Fender'})
    pools['industry'].update({'Hat-making','Pottery','Shipbuilding','Coal mining'})
    pools['monogram'].update({'FFC','FCT','CFC','FCF'})
    pools['tower'].update({"Prince Rupert's Tower",'Blackpool Tower','Victoria Tower','Spinnaker Tower'})
    pools['badge_object'].update({'A football','A crown','A star','A shield'})
    return pools,clubs


def options(item,pools,clubs):
    explicit=closed_answers(item)
    if explicit is not None:
        matches=[n for n,a in enumerate(explicit) if option_key(a)==option_key(item['answer'])]
        if len(matches)!=1:raise ValueError('Explicit choices do not contain exactly one canonical answer: '+item['id'])
        explicit[matches[0]]=item['answer'];values=explicit
    else:
        family=kind(item,clubs)
        if family in {'number','percentage','season','score'}:return make_options(item,pools)
        keys=lambda value:palette_key(value) if family=='kit_palette' else option_key(value)
        forbidden={keys(a) for a in [item['answer'],*item.get('accepted',[])]}
        alternatives={keys(v):v for v in sorted(pools[family]) if keys(v) not in forbidden}
        if len(alternatives)<3:raise ValueError('Insufficient typed alternatives: '+item['id'])
        values=[item['answer'],*secrets.SystemRandom().sample(list(alternatives.values()),3)]
    if not 2<=len(values)<=4 or len({option_key(v) for v in values})!=len(values):raise ValueError('Invalid distinct choices: '+item['id'])
    secrets.SystemRandom().shuffle(values)
    return [{'id':str(i),'text':v} for i,v in enumerate(values)],str(values.index(item['answer']))
