"""Recompute draft answers from source tables, independently of generation.

This is a database consistency audit, not an independent external fact check.
No write connection or publication operation is exposed by this command.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path

from api.database import get_connection
from src.build_curated_questions import key,name,season_label,club_key


class Checker:
    def __init__(self,conn):
        self.players={r['player_id']:r for r in conn.execute('SELECT player_id,player_name,first_name,nationality FROM players')}
        self.teams={r['team_id']:r['team_name'] for r in conn.execute('SELECT team_id,team_name FROM teams')}
        self.fixtures={r['fixture_id']:r for r in conn.execute("SELECT * FROM fixtures WHERE league_id=39 AND status='FT'")}
        self.stats={(r['season'],r['team_id'],r['player_id']):r for r in conn.execute('SELECT * FROM player_season_statistics WHERE league_id=39')}
        self.transfers={r['transfer_id']:r for r in conn.execute('SELECT * FROM player_transfers')}
        self.quality=defaultdict(set)
        for r in conn.execute('SELECT dataset_id,fixture_id FROM trivia_player_data_quality WHERE scorers_valid'):
            self.quality[str(r['dataset_id'])].add(r['fixture_id'])
        self.goals=Counter();self.season_goals=Counter()
        for e in conn.execute("SELECT fixture_id,team_id,player_id FROM fixture_events WHERE event_type='Goal' AND event_detail IN ('Normal Goal','Penalty') AND player_id IS NOT NULL"):
            if e['fixture_id'] not in self.fixtures:continue
            self.goals[e['fixture_id'],e['team_id'],e['player_id']]+=1
            self.season_goals[self.fixtures[e['fixture_id']]['season'],e['team_id'],e['player_id']]+=1

    def answer(self,q):
        e=q['evidence'];family=q['family'];p=e.get('player_id');t=e.get('team_id');y=e.get('season')
        if family=='nationality':return self.players[p]['nationality']
        if family=='transfer':
            row=self.transfers[e['transfer_id']];raw=row['raw_payload'];assert row['player_id']==p and row['team_in_id']==t and row['transfer_date'].year==e['year']
            assert raw['teams']['in']['id']==t and raw['teams']['out']['id']==row['team_out_id']
            relevant=[r for r in self.transfers.values() if r['player_id']==p and r['team_in_id']==t and r['transfer_date'] and r['transfer_date'].year==e['year'] and 'loan' not in (r['transfer_type'] or '').lower()]
            assert len({r['team_out_id'] for r in relevant})==1
            return row['team_out_name']
        if family=='teammates':
            a,b=e['players'];clubs=[]
            for club in self.teams:
                sa=self.stats.get((y,club,a),{});sb=self.stats.get((y,club,b),{})
                if (sa.get('appearances') or 0)>=15 and (sb.get('appearances') or 0)>=15:clubs.append(club)
            assert clubs==[t];return self.teams[t]
        if family=='club_trail':
            matching=[pid for pid in self.players if all((self.stats.get((year,club,pid),{}).get('appearances') or 0)>=15 for club,year in e['trail'])]
            assert matching==[p];return name(self.players[p])
        if family in ('season_goals','scoring_club','club_scorer'):
            row=self.stats[y,t,p];count=self.season_goals[y,t,p]
            assert count==row['goals_total']==e['goals']
            games=[f for f in self.fixtures.values() if f['season']==y and t in (f['home_team_id'],f['away_team_id'])]
            assert len(games)==38
            assert all(f['fixture_id'] in self.quality[e['dataset_id']] for f in games)
            if family=='club_scorer':
                others=[s for (year,team,pid),s in self.stats.items() if year==y and team==t and pid!=p]
                assert all((r['goals_total'] or 0)<count for r in others)
                return name(self.players[p])
            if family=='scoring_club':assert {team for (year,team,pid),s in self.stats.items() if year==y and pid==p and s['goals_total']==count}=={t}
            return str(count) if family=='season_goals' else self.teams[t]
        f=self.fixtures[e['fixture_id']];assert f['season']==y
        home=f['home_team_id']==t;gf=f['home_goals'] if home else f['away_goals'];ga=f['away_goals'] if home else f['home_goals'];opp=f['away_team_id'] if home else f['home_team_id']
        assert gf>ga
        if family in ('brace','hat_trick'):
            assert self.goals[e['fixture_id'],t,p]==e['goals']
            matches=[pid for (i,team,pid),n in self.goals.items() if i==e['fixture_id'] and team==t and n==e['goals']]
            assert matches==[p]
            matching=set()
            for other in self.fixtures.values():
                if other['season']!=y:continue
                for a,b in (('home','away'),('away','home')):
                    if other[a+'_team_id']==t and other[b+'_team_id']==opp and other[a+'_goals']==gf and other[b+'_goals']==ga:
                        assert other['fixture_id'] in self.quality[e['dataset_id']]
                        matching.update(pid for (i,team,pid),n in self.goals.items() if i==other['fixture_id'] and team==t and n==e['goals'])
            assert matching=={p},'Multiple scorers fit the match clue'
            return name(self.players[p])
        if family in ('comeback','big_win'):
            winners=set()
            for row in self.fixtures.values():
                if row['season']!=y:continue
                for a,b in (('home','away'),('away','home')):
                    if row[b+'_team_id']!=opp or row[a+'_goals']!=gf or row[b+'_goals']!=ga:continue
                    if family=='comeback':
                        hf=f['halftime_home'] if home else f['halftime_away'];ha=f['halftime_away'] if home else f['halftime_home']
                        if row['halftime_'+a]!=hf or row['halftime_'+b]!=ha:continue
                    winners.add(row[a+'_team_id'])
            assert winners=={t},'More than one club fits this result clue'
            return self.teams[t]
        raise ValueError('Unknown evidence family')

    def prompt(self,q):
        e=q['evidence'];family=q['family'];p=e.get('player_id');t=e.get('team_id');y=e.get('season')
        person=name(self.players[p]) if p else None;club=self.teams.get(t);label=season_label(y) if y else None
        if family=='nationality':return f"What is {person}'s football nationality?"
        if family=='transfer':return f"From which club did {club} sign {person} in {e['year']}?"
        if family=='teammates':
            a,b=e['players'];return f'Which Premier League club had both {name(self.players[a])} and {name(self.players[b])} in {label}?'
        if family=='club_trail':
            clue=', '.join(f'{self.teams[t]} in {season_label(y)}' for t,y in e['trail']);return f'Who played Premier League football for {clue}?'
        if family=='scoring_club':return f"For which club did {person} score {e['goals']} Premier League goals in {label}?"
        if family=='season_goals':return f'How many Premier League goals did {person} score for {club} in {label}?'
        if family=='club_scorer':return f'Who led {club} in Premier League goals in {label}?'
        f=self.fixtures[e['fixture_id']];home=f['home_team_id']==t
        gf=f['home_goals'] if home else f['away_goals'];ga=f['away_goals'] if home else f['home_goals'];opp=self.teams[f['away_team_id'] if home else f['home_team_id']]
        if family in ('brace','hat_trick'):
            number={2:'twice',3:'a hat-trick',4:'four goals',5:'five goals'}[e['goals']]
            return f"Who scored {number} in {club}'s {gf}-{ga} Premier League win over {opp} in {label}?"
        if family=='big_win':return f'Which club beat {opp} {gf}-{ga} in the {label} Premier League?'
        hf=f['halftime_home'] if home else f['halftime_away'];ha=f['halftime_away'] if home else f['halftime_home']
        return f'Which club came from {hf}-{ha} down at half-time to beat {opp} {gf}-{ga} in the {label} Premier League?'

    def check(self,q):
        try:
            answer=str(self.answer(q));assert answer==q['answer'],'Answer conflicts with source records'
            assert q['question']==self.prompt(q),'Question wording does not match its source evidence'
            assert q['options'][q['correct']]==answer and len({key(s) for s in q['options']})==4
            if q['family'] in ('transfer','scoring_club','teammates','comeback','big_win'):assert len({club_key(s) for s in q['options']})==4
            assert len(q['question'])<=240 and q['difficulty'] in ('easy','medium','hard')
            if q['family']=='season_goals':assert min(abs(int(a)-int(b)) for i,a in enumerate(q['options']) for b in q['options'][i+1:])>=4
            return {'id':q['id'],'status':'matched','answer':answer,'method':'independent_source_recalculation'}
        except (KeyError,IndexError,AssertionError,ValueError,TypeError) as exc:
            return {'id':q.get('id'),'status':'conflict','reason':str(exc) or 'Referenced source records disagree'}


def main():
    p=argparse.ArgumentParser();p.add_argument('questions',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    raw=args.questions.read_bytes();questions=json.loads(raw)
    with get_connection() as conn:
        conn.execute('SET TRANSACTION READ ONLY');checker=Checker(conn);checks=[checker.check(q) for q in questions]
    duplicate_facts=[k for k,n in Counter(q['fact_key'] for q in questions).items() if n>1]
    report={'question_sha256':hashlib.sha256(raw).hexdigest(),'checked':len(checks),'counts':dict(Counter(c['status'] for c in checks)),
            'duplicate_fact_keys':duplicate_facts,'external_fact_check':False,'checks':checks}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2))


if __name__=='__main__':main()
