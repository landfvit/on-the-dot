"""Explicitly released bank questions, with typed, distinct answer alternatives."""
from collections import defaultdict
from copy import deepcopy
import re
import secrets

from fastapi import HTTPException
from api.trivia_bank_engine import CLUBS, canonical, normalized
from api.numeric_choices import options as numeric_options, refresh as refresh_numeric_choices

CHOICE_VERSION = 'bank-choices-v1'
PERSON_TOPICS = {'Assists','Scoring leaders','Player comparisons','Match details','Discipline',
                 'Appearances','Awards','Captains','Hat-tricks'}
COLOURS = ['White','Black','Blue','Green','Yellow','Orange','Pink','Purple','Maroon','Red']


def answer_kind(item):
    answer = item['answer']
    if re.fullmatch(r'-?\d+(?:\.\d+)?%', answer): return 'percentage'
    if re.fullmatch(r'-?\d+(?:\.\d+)?', answer): return 'number'
    if re.fullmatch(r'20\d{2}/\d{2}', answer): return 'season'
    if re.fullmatch(r'\d+[–-]\d+', answer): return 'score'
    if canonical(answer).startswith('club:') or item['topic'] in {'Loans','Transfers'}: return 'club'
    if item['topic'] == 'Kits and design':
        if answer in COLOURS: return 'colour'
        if answer == '100th anniversary': return 'anniversary'
        if answer == 'Liverpool street signs': return 'city_design'
        if answer == 'Ed Sheeran': return 'musician'
        if answer == 'Bob Paisley': return 'manager'
        raise ValueError('Unclassified kit answer: ' + item['id'])
    if item['topic'] in PERSON_TOPICS: return 'player'
    if item['topic'] == 'Managers': return 'manager'
    if item['topic'] == 'Stadiums': return 'stadium'
    if item['topic'] in {'Shirt sponsors','Sleeve sponsors'}: return 'sponsor'
    if item['topic'] == 'Kit manufacturers': return 'manufacturer'
    raise ValueError('No safe option family for ' + item['id'])


def option_key(text):
    return re.sub(r'[^\w%/-]', '', canonical(text))


def answer_pools(items):
    pools = defaultdict(set)
    for item in items: pools[answer_kind(item)].add(item['answer'])
    pools['club'].update(CLUBS.values())
    pools['colour'].update(COLOURS)
    pools['anniversary'].update(['50th anniversary','75th anniversary','125th anniversary','150th anniversary'])
    pools['musician'].update(['Stormzy','Dave','Sam Fender'])
    pools['city_design'].update(['Liverpool railway maps','The Liver Building clock face','Merseyside ferry routes'])
    return pools


def make_options(item, pools):
    answer, kind = item['answer'], answer_kind(item)
    if kind in {'number','percentage'}:
        return numeric_options(answer, allow_negative='difference' in normalized(item['question']), accepted=item.get('accepted', []))
    elif kind == 'season':
        year = int(answer[:4])
        candidates = [f'{s}/{str(s+1)[-2:]}' for s in range(year-3,year+4) if s != year]
    elif kind == 'score':
        gf, ga = map(int, re.split('[–-]', answer))
        candidates = [f'{a}–{b}' for a,b in [(gf+1,ga),(gf,ga+1),(gf+1,ga+1),(max(0,gf-1),ga),(gf,max(0,ga-1))]]
    else:
        candidates = sorted(pools[kind])
        if kind == 'colour':
            # Red/maroon and purple/maroon must not become competing ordinary colour equivalents.
            related = {'Red': {'Maroon'}, 'Maroon': {'Red','Purple'}, 'Purple': {'Maroon'}}
            candidates = [v for v in candidates if v not in related.get(answer,set())]
        aliases = {option_key(a) for a in item.get('accepted',[])}
        candidates = [v for v in candidates if option_key(v) not in aliases]
    unique = {option_key(v):v for v in candidates if option_key(v) != option_key(answer)}
    if len(unique) < 3: raise ValueError('Insufficient distinct alternatives for ' + item['id'])
    selected = [answer, *secrets.SystemRandom().sample(list(unique.values()),3)]
    secrets.SystemRandom().shuffle(selected)
    options = [{'id': str(i),'text': text} for i,text in enumerate(selected)]
    return options, str(selected.index(answer))


def eligible(check):
    if check.get('publication_exclusion'):return False
    if check['status'] == 'conflict': return False
    return check['status'] != 'ambiguous' or check['reason'].startswith('Database player found, but reference name')


def released_question(item, check, release_id, question_id):
    authority = 'database_matched' if check['status'] == 'matched' else 'user_attested'
    return {'key': f'bank:{release_id}:{question_id}', 'text': item['question'],
        'explanation': item['answer'] + '. ' + item['check'],
        'authority': authority, 'validation_status': check['status'],
        'source': {'question_id': str(question_id), 'external_id': item['id'], 'references': item['sources']},
        'topic': item['topic'], 'section': item['section']}


def catalog(conn):
    release = conn.execute('SELECT release_id FROM penalty_bank_releases ORDER BY created_at DESC,release_id DESC LIMIT 1').fetchone()
    if not release: return []
    rows = conn.execute('''SELECT section_code,section_name,count(*) AS count,
        count(*) FILTER(WHERE question->>'authority'='database_matched') AS verified_count
        FROM penalty_bank_questions WHERE release_id=%s GROUP BY section_code,section_name
        ORDER BY CASE WHEN section_code='GEN' THEN 0 ELSE 1 END,section_name''', (release['release_id'],)).fetchall()
    packs = [{'id':f"bank:{release['release_id']}:{row['section_code']}", 'label':row['section_name'],
              'count':row['count'], 'verified_count':row['verified_count'], 'language':'EN',
              'group':'Premier League' if row['section_code']=='GEN' else 'Teams'} for row in rows]
    if packs:
        packs.insert(1, {'id':f"bank:{release['release_id']}:ALL",'label':'Premier League · mix',
            'count':sum(r['count'] for r in rows),'verified_count':sum(r['verified_count'] for r in rows),
            'language':'EN','group':'Premier League'})
    return packs


def load_pack(conn, pack):
    from api.penalty_questions import maths_pack, library_pack
    if pack == 'maths': return pack,'Football maths · practice questions',maths_pack()
    if pack == 'library': return pack,'Verified POINTS questions',library_pack(conn)
    if pack == 'general':
        choices = catalog(conn)
        general = next((p for p in choices if p['id'].endswith(':GEN')),None)
        if not general: raise HTTPException(409,'General questions have not been released yet')
        pack = general['id']
    match = re.fullmatch(r'bank:([0-9a-f-]{36}):([A-Z]{3})',pack)
    if not match: raise HTTPException(422,'Unknown question pack')
    from uuid import UUID
    try: release_id = UUID(match[1])
    except ValueError: raise HTTPException(422,'Invalid pack release')
    params = [release_id]
    where = 'release_id=%s'
    if match[2] != 'ALL': where += ' AND section_code=%s'; params.append(match[2])
    rows = conn.execute('SELECT section_name,question FROM penalty_bank_questions WHERE '+where,params).fetchall()
    if not rows: raise HTTPException(404,'Question pack not found')
    deck = [deepcopy(r['question']) for r in rows]
    secrets.SystemRandom().shuffle(deck)
    # Freeze a bounded match pool instead of copying the entire catalogue into every room.
    deck = deck[:120]
    deck = [refresh_numeric_choices(question) for question in deck]
    for question in deck:
        correct = next(o['text'] for o in question['options'] if o['id']==question['correct'])
        secrets.SystemRandom().shuffle(question['options'])
        for i, option in enumerate(question['options']):
            option['id'] = str(i)
            if option['text'] == correct: question['correct'] = str(i)
    label = 'Premier League · mix' if match[2]=='ALL' else rows[0]['section_name']
    return pack,label,deck
