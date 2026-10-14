"""Vary question formats without changing answers, difficulty or eligibility."""
from collections import Counter,defaultdict
from math import ceil
import secrets


MATCH_FAMILIES={'brace','hat_trick','big_win','comeback'}


def group(row):
    family=row.get('family') or row.get('source_topic') or row.get('topic') or 'other'
    return 'match_memory' if family in MATCH_FAMILIES else family


def metadata(row):
    evidence=row.get('mix_evidence') or {}
    players=list(evidence.get('players') or [])
    if evidence.get('player_id'):players.append(evidence['player_id'])
    subjects={f'player:{pid}' for pid in players}
    if evidence.get('team_id'):subjects.add(f"club:{evidence['team_id']}")
    return {'family':row.get('family'),'source_topic':row.get('source_topic'),
            'mix_subjects':sorted(subjects)}


def enrich_deck(conn,deck):
    """Older frozen pools need format metadata only, never new answer content."""
    missing=[q['question_id'] for q in deck if 'family' not in q and q.get('question_id')]
    if not missing:return deck
    rows=conn.execute('''SELECT question_id,content->>'topic' source_topic,
        content->>'family' family,content->'evidence' mix_evidence
        FROM trivia_bank_questions WHERE question_id=ANY(%s::uuid[])''',(missing,)).fetchall()
    by_id={str(r['question_id']):metadata(r) for r in rows}
    return [{**q,**by_id.get(q.get('question_id'),{})} for q in deck]


def sample(rows,size=10,rng=None,recent=()):
    """Balance formats and spread repeats across a rolling ten-question window.

    Nationalities get at most one slot and scoreline memories two while other
    formats remain available. Caps relax only if the eligible pool cannot fill
    the request; they never cause repeats or a fallback to a different scope.
    """
    rng=rng or secrets.SystemRandom()
    buckets=defaultdict(lambda:defaultdict(list))
    for row in rows:
        family=row.get('family') or group(row)
        buckets[group(row)][family].append(row)
    for families in buckets.values():
        for bucket in families.values():rng.shuffle(bucket)
    default_limit=max(2,ceil(10/max(1,len(buckets))))
    limits={'nationality':1,'match_memory':2}
    selected=[];history=list(recent)[-9:]
    subject_cache={}
    def subjects(row):
        identity=id(row)
        if identity not in subject_cache:
            subject_cache[identity]=row['mix_subjects'] if 'mix_subjects' in row else metadata(row)['mix_subjects']
        return subject_cache[identity]
    while buckets and len(selected)<size:
        counts=Counter(group(r) for r in history)
        previous=group(history[-1]) if history else None
        keys=list(buckets);rng.shuffle(keys)
        key=min(keys,key=lambda k:(counts[k]>=limits.get(k,default_limit),k==previous,counts[k]))
        families=buckets[key];family_counts=Counter(r.get('family') or group(r) for r in history)
        names=list(families);rng.shuffle(names)
        family=min(names,key=lambda name:family_counts[name])
        bucket=families[family]
        recent_subjects={s for r in history for s in subjects(r)}
        # Randomized buckets break equal scores without clustering one player
        # or club just because several formats refer to the same subject.
        index=0;best=None
        for i,candidate in enumerate(bucket):
            overlap=len(recent_subjects.intersection(subjects(candidate)))
            if best is None or overlap<best:index=i;best=overlap
            if not overlap:break
        row=bucket.pop(index);selected.append(row);history=(history+[row])[-9:]
        if not bucket:del families[family]
        if not families:del buckets[key]
    return selected
