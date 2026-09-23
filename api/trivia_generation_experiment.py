"""LLM-authored question plans with deterministic answers; never a generative local model.

This isolated experiment does not publish questions or relax production guards.
"""
from dataclasses import dataclass
from itertools import groupby
import re

from rapidfuzz import fuzz,process
from api.trivia_bank_engine import question_tokens,season_label


@dataclass(frozen=True)
class Plan:
    key:str
    text:str
    unit:str
    concept:str


PLANS=[
    Plan('streak_wins','What was the longest winning streak, in consecutive league matches, for {team} in the {season} Premier League?','matches','winning streak|consecutive.*win|wins.*row'),
    Plan('streak_unbeaten','How many consecutive league matches made up {team}\'s longest unbeaten run in the {season} Premier League?','matches','unbeaten|without (?:a )?los'),
    Plan('streak_scoring','What was the longest run of consecutive league matches in which {team} scored at least once in the {season} Premier League?','matches','consecutive.*scor|scor.*consecutive'),
    Plan('streak_clean_sheets','How many consecutive league matches made up {team}\'s longest clean-sheet streak in the {season} Premier League?','matches','(?:consecutive|streak|run).*clean.sheet|clean.sheet.*(?:streak|run|consecutive)'),
    Plan('streak_winless','What was the longest run of consecutive league matches without a win for {team} in the {season} Premier League?','matches','winless|without (?:a )?win'),
    Plan('opening_points','How many points did {team} earn on the pitch in their first six matches of the {season} Premier League season?','points','(?:first|opening) (?:six|6).*point|point.*(?:first|opening) (?:six|6)'),
    Plan('closing_points','How many points did {team} earn on the pitch in their final six matches of the {season} Premier League season?','points','(?:last|final|closing) (?:six|6).*point|point.*(?:last|final|closing) (?:six|6)'),
    Plan('opening_goals','How many goals did {team} score across their first six matches of the {season} Premier League season?','goals','(?:first|opening) (?:six|6).*goal|goal.*(?:first|opening) (?:six|6)'),
    Plan('closing_goals','How many goals did {team} score across their final six matches of the {season} Premier League season?','goals','(?:last|final|closing) (?:six|6).*goal|goal.*(?:last|final|closing) (?:six|6)'),
    Plan('home_opening_points','How many points did {team} earn on the pitch in their first five home games of the {season} Premier League season?','points','(?:first|opening) (?:five|5).*home|home.*(?:first|opening) (?:five|5)'),
    Plan('away_closing_points','How many points did {team} earn on the pitch in their final five away games of the {season} Premier League season?','points','(?:final|last|closing) (?:five|5).*away|away.*(?:final|last|closing) (?:five|5)'),
    Plan('wins_after_loss','How many times did {team} win a league match immediately after losing their previous league match within the {season} Premier League season?','transitions','win.*(?:after|following).*los|win.*(?:after|following).*defeat'),
    Plan('wins_after_draw','How many times did {team} follow a league draw with a win in their very next league match within the {season} Premier League season?','transitions','draw.*(?:next|follow).*win|(?:next|follow).*draw.*win'),
    Plan('clean_sheet_pairs','How many adjacent pairs of league matches both ended with a {team} clean sheet in the {season} Premier League? Count overlapping pairs separately.','pairs','(?:pairs|back.to.back).*clean.sheet|clean.sheet.*(?:pairs|back.to.back)'),
    Plan('draws_after_win','How many times did {team} draw a league match immediately after winning their previous league match within the {season} Premier League season?','transitions','draw.*(?:after|following).*win|win.*follow.*draw'),
    Plan('first_win_opponent','Which opponent did {team} beat for their first league win of the {season} Premier League season?','club','first.*(?:league |premier league )?win|first.*victory'),
    Plan('last_win_opponent','Which opponent did {team} beat for their last league win of the {season} Premier League season?','club','(?:last|final).*league win|(?:last|final).*victory'),
    Plan('last_clean_sheet_opponent','Against which opponent did {team} keep their last league clean sheet of the {season} Premier League season?','club','(?:last|final).*clean.sheet'),
    Plan('biggest_home_win_opponent','Which opponent suffered {team}\'s biggest home league win by goal margin in the {season} Premier League?','club','(?:biggest|largest|highest).*home.*win|(?:biggest|largest).*home.*victory'),
    Plan('biggest_away_win_opponent','Which opponent suffered {team}\'s biggest away league win by goal margin in the {season} Premier League?','club','(?:biggest|largest|highest).*away.*win|(?:biggest|largest).*away.*victory'),
]
BY_KEY={p.key:p for p in PLANS}


def snapshot_answer(key,rows):
    """First calculation: ordinary Python over sealed per-team match facts."""
    if key not in BY_KEY:raise ValueError('Unknown question plan')
    rows=sorted(rows,key=lambda r:(r['match_date'],r['fixture_id']))
    if len(rows)!=38 or len({r['fixture_id'] for r in rows})!=38:raise ValueError('Need a complete 38-match club season')
    if len({r['match_date'] for r in rows})!=38:raise ValueError('Ambiguous chronological ordering')
    if len({(r['team_id'],r['season']) for r in rows})!=1:raise ValueError('Mixed club/season scope')
    if any(not r['result_valid'] or min(r['goals_for'],r['goals_against'])<0 for r in rows):raise ValueError('Invalid result')
    details={};selected=[]
    if key.startswith('streak_'):
        predicate={'streak_wins':lambda r:r['result']=='W','streak_unbeaten':lambda r:r['result']!='L',
                   'streak_scoring':lambda r:r['goals_for']>0,'streak_clean_sheets':lambda r:r['goals_against']==0,
                   'streak_winless':lambda r:r['result']!='W'}[key]
        runs=[list(g) for flag,g in groupby(rows,key=predicate) if flag]
        answer=max(map(len,runs),default=0)
        best=[run for run in runs if len(run)==answer]
        selected=[r for run in best for r in run]
        details['longest_runs']=[[r['fixture_id'] for r in run] for run in best]
    elif key in {'opening_points','closing_points','opening_goals','closing_goals','home_opening_points','away_closing_points'}:
        if key=='home_opening_points':selected=[r for r in rows if r['is_home']][:5]
        elif key=='away_closing_points':selected=[r for r in rows if not r['is_home']][-5:]
        else:selected=rows[:6] if key.startswith('opening') else rows[-6:]
        answer=sum(r['goals_for'] if key.endswith('goals') else {'W':3,'D':1,'L':0}[r['result']] for r in selected)
    elif key in {'wins_after_loss','wins_after_draw','clean_sheet_pairs','draws_after_win'}:
        predicate={'wins_after_loss':lambda a,b:a['result']=='L' and b['result']=='W',
                   'wins_after_draw':lambda a,b:a['result']=='D' and b['result']=='W',
                   'draws_after_win':lambda a,b:a['result']=='W' and b['result']=='D',
                   'clean_sheet_pairs':lambda a,b:a['goals_against']==b['goals_against']==0}[key]
        pairs=[(a,b) for a,b in zip(rows,rows[1:]) if predicate(a,b)]
        answer=len(pairs);selected=[r for pair in pairs for r in pair]
        details['pairs']=[[a['fixture_id'],b['fixture_id']] for a,b in pairs]
    else:
        candidates=[r for r in rows if r['goals_against']==0] if key=='last_clean_sheet_opponent' else [r for r in rows if r['result']=='W']
        if key.startswith('biggest_'):
            candidates=[r for r in candidates if r['is_home']==('home' in key)]
            margin=max((r['goals_for']-r['goals_against'] for r in candidates),default=0)
            candidates=[r for r in candidates if r['goals_for']-r['goals_against']==margin]
            if len(candidates)!=1:raise ValueError('No unique largest winning margin')
            selected=candidates;details['winning_margin']=margin
        else:selected=candidates[:1] if key=='first_win_opponent' else candidates[-1:]
        if not selected:raise ValueError('No qualifying opponent')
        answer=selected[0]['opponent_id'];details['opponent_name']=selected[0]['opponent_name']
    return {'value':answer,'unit':BY_KEY[key].unit,'evidence_fixture_ids':sorted({r['fixture_id'] for r in selected}),
            'scope_fixture_ids':[r['fixture_id'] for r in rows],'details':details}


def wording(key,team,season):
    return BY_KEY[key].text.format(team=team,season=season_label(season))


class NoveltyIndex:
    def __init__(self,existing):
        self.existing=existing
        self.texts=[question_tokens(r['question']) for r in existing]

    def check(self,key,team,season,text):
        tokens=question_tokens(text)
        nearest=process.extractOne(tokens,self.texts,scorer=fuzz.ratio)
        score=round(nearest[1],2) if nearest else 0
        match=self.existing[nearest[2]] if nearest else None
        reason='exact_duplicate' if score==100 else 'near_duplicate' if score>=90 else None
        for row,existing in zip(self.existing,self.texts):
            if re.search(rf'\bclub{team}\b',existing) and season_label(season) in existing and re.search(BY_KEY[key].concept,existing):
                reason='same_concept_team_season';match=row;break
        return {'accepted':reason is None,'reason':reason,'nearest_similarity':score,
                'nearest':match,'method':'alias-normalized exact/90% lexical check plus same-concept club/season exclusion'}
