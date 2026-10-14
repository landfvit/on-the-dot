"""Explicit solo taxonomy, independent of club and difficulty."""
from collections import defaultdict
import secrets
from typing import Literal

TopicCode=Literal['ALL','players','managers','stadiums','kits','matches','head_to_head','season_records','win_rates','discipline','club_identity','cups']
TOPICS={
    'players':('Players & transfers',{
        'Scoring leaders','Golden Boot','Awards','Hat-tricks','Player totals','Captains',
        'Player comparisons','Goalkeepers','Assists','Match details',
        'Four-goal games','Transfers','Loans','Appearances','International identity','Player roles',
        'Shirt-number recognition','Transfers and loans','Club scoring leaders','Player awards',
        'Golden Glove','Assists and playmakers','Who played for whom?','Player milestones',
    }),
    'managers':('Managers',{'Managers','Title-winning managers'}),
    'stadiums':('Stadiums',{'Stadiums','Home grounds'}),
    'kits':('Kits & sponsors',{'Kit manufacturers','Shirt sponsors','Sleeve sponsors','Kits and design','Home colours','Equipment'}),
    'matches':('Matches & scorelines',{
        'Home, away and score patterns','Identify the opponent','Unusual season counts',
        'Scoreline frequency','Memorable defeats','Statement away wins','Unusual score distributions',
        'Match recognition','Big-score memories','Comebacks',
    }),
    'head_to_head':('Head-to-head & mini-leagues',{
        'Two-match fingerprints','Mini-leagues','Season head-to-head patterns','Only-one opponent',
        'Multi-season head-to-head','Multi-season Big Six','Against the title contenders',
        'Head-to-head records','Big Six mini-leagues',
    }),
    'season_records':('Season records & tables',{
        'Club records across the window','League-wide statistical records','League-wide patterns',
        'Unique season anomalies','Table-position paradoxes','Title-race arithmetic','Ten-season records',
        'Champions','Title races','Promotion','Landmark seasons','League changes','Premier League arrivals','Season comparison',
    }),
    'win_rates':('Win rates & percentages',{'Conditional win rates','Season ratios'}),
    'discipline':('Cards & discipline',{'Discipline'}),
    'club_identity':('Club identity & traditions',{'Club identity','Badges and traditions','Name the club'}),
    'cups':('Cups & international football',{'Domestic cups','International context','Cup history'}),
}
SOURCE_TOPIC={source:code for code,(_,sources) in TOPICS.items() for source in sources}


def sources(code):
    return sorted(SOURCE_TOPIC if code=='ALL' else TOPICS[code][1])


def label(code):
    return 'Mixed topics' if code=='ALL' else TOPICS[code][0]


def balanced_sample(rows,topic='ALL',size=10,rng=None,recent=()):
    """Mix available formats, falling back to topics for older bank metadata."""
    rng=rng or secrets.SystemRandom()
    eligible=[r for r in rows if SOURCE_TOPIC.get(r['source_topic']) is not None
              and (topic=='ALL' or SOURCE_TOPIC[r['source_topic']]==topic)]
    if any(r.get('family') for r in eligible):
        from api.question_mix import sample
        return sample(eligible,size=size,rng=rng,recent=recent)
    buckets=defaultdict(list)
    for row in eligible:
        code=SOURCE_TOPIC.get(row['source_topic'])
        if code is not None and (topic=='ALL' or code==topic):
            buckets[code if topic=='ALL' else row['source_topic']].append(row)
    for bucket in buckets.values():rng.shuffle(bucket)
    selected=[]
    while buckets and len(selected)<size:
        keys=list(buckets);rng.shuffle(keys)
        for key in keys:
            selected.append(buckets[key].pop())
            if not buckets[key]:del buckets[key]
            if len(selected)==size:break
    rng.shuffle(selected)
    return selected
