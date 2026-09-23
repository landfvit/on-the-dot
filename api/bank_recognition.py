"""Answer-independent recognition templates for the easy/medium bank."""
import re


def calculate(evaluator,question):
    from api.trivia_bank_engine import CannotCheck,CLUBS,question_tokens,season_label,VERSION
    q=question_tokens(question)
    season_pattern=r'(20\d{2})/(\d{2})'
    patterns={
        'comparison':rf'in the {season_pattern} premier league, which team (finished higher|finished with more league points|scored more league goals|conceded fewer league goals): club(\d+) or club(\d+)\?',
        'champion':rf'which club finished as premier league champions in {season_pattern}\?',
        'runner':rf'which club finished second in the {season_pattern} premier league table\?',
        'outcome':rf"what was the outcome of club(\d+)'s home premier league meeting with club(\d+) in {season_pattern}: a club\d+ win, a draw, or a club\d+ win\?",
        'btts':rf'did both teams score when club(\d+) hosted club(\d+) in the {season_pattern} premier league\?',
        'score':rf"with the home team's goals first, which was the score when club(\d+) hosted club(\d+) in {season_pattern}: \d+-\d+ or \d+-\d+\?",
        'scorer':rf"which club(\d+) player led the club's premier league scoring in {season_pattern}, with (\d+) goals\?",
    }
    selected=next(((key,m) for key,p in patterns.items() if (m:=re.fullmatch(p,q))),None)
    if selected is None:return None
    kind,m=selected
    season_match=re.search(season_pattern,q);season=int(season_match[1])
    if int(season_match[2])!=(season+1)%100:raise CannotCheck('Invalid explicit season')
    if season not in evaluator.seasons or evaluator.coverage[season]:
        raise CannotCheck(season_label(season)+': '+(evaluator.coverage.get(season) or 'Missing season'),'incomplete')
    rows=evaluator.seasons[season];details={};accepted=[]
    if kind in {'comparison','champion','runner'}:
        table=evaluator.final_table(season)
        if kind=='comparison':
            left,right=int(m[4]),int(m[5])
            if left==right or left not in table or right not in table:raise CannotCheck('Comparison needs two clubs in this season','ambiguous')
            field,lower={'finished higher':('league_rank',True),'finished with more league points':('points',False),
                         'scored more league goals':('goals_for_total',False),'conceded fewer league goals':('goals_against_total',True)}[m[3]]
            a,b=table[left][field],table[right][field]
            if a is None or b is None:raise CannotCheck('Missing table metric','incomplete')
            if a==b:raise CannotCheck('Comparison is tied','ambiguous')
            answer=CLUBS[left if (a<b)==lower else right];details={'metric':field,'left':a,'right':b}
        else:
            rank=1 if kind=='champion' else 2
            answer=next(CLUBS[t] for t,r in table.items() if r['league_rank']==rank)
            details={'rank':rank}
    elif kind=='scorer':
        team=int(m[1]);st=season_label(season)
        result=evaluator.calculate(f'Who finished as the sole leading Premier League goalscorer for {CLUBS[team]} in {st}?')
        if result['details']['goals']!=int(m[4]):raise CannotCheck('Leading scorer goal-total premise disagrees with database','conflict')
        return result
    else:
        home,away=int(m[1]),int(m[2])
        matches=[r for r in rows if r['is_home'] and r['team_id']==home and r['opponent_id']==away]
        if len(matches)!=1:raise CannotCheck('Fixture is missing or not unique','incomplete')
        r=matches[0];rows=matches
        if kind=='outcome':
            mentioned=[int(i) for i in re.findall(r'club(\d+)',q)]
            if mentioned!=[home,away,home,away]:raise CannotCheck('Answer choices do not match the fixture','conflict')
            answer='Draw' if r['result']=='D' else CLUBS[home if r['result']=='W' else away]
        elif kind=='btts':answer='Yes' if min(r['goals_for'],r['goals_against'])>0 else 'No'
        else:answer=f"{r['goals_for']}-{r['goals_against']}"
        details={'home_team':home,'away_team':away,'home_goals':r['goals_for'],'away_goals':r['goals_against']}
    return {'answer':str(answer),'accepted':accepted,'details':details,'seasons':[season],'checked_seasons':[season],
            'evidence_fixture_ids':sorted({r['fixture_id'] for r in rows}),'validator_version':VERSION}
