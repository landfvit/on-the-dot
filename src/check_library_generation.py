"""Independent raw-fixture SQL checks for the library experiment's new-scope jobs.

This intentionally does not call BankEvaluator or its metric helpers. Unsupported
operators abstain instead of claiming independent verification.
"""
import argparse
import json
from pathlib import Path

from api.database import get_connection
from api.trivia_bank_engine import canonical
from src.trivia_llm import dump, read_jsonl, verify_bundle


SIDES = '''WITH sides AS (
    SELECT f.fixture_id, v.team_id, v.opponent_id, v.home, v.gf, v.ga,
           CASE WHEN v.gf>v.ga THEN 3 WHEN v.gf=v.ga THEN 1 ELSE 0 END AS pts
    FROM fixtures f CROSS JOIN LATERAL (
        VALUES (home_team_id,away_team_id,true,home_goals,away_goals),
               (away_team_id,home_team_id,false,away_goals,home_goals)
    ) AS v(team_id,opponent_id,home,gf,ga)
    WHERE f.league_id=39 AND f.season=%s AND f.status='FT'
), totals AS (
    SELECT team_id, sum(gf) scored, sum(ga) conceded,
           count(*) FILTER(WHERE gf=ga) draws,
           sum(pts) FILTER(WHERE home) hp, sum(pts) FILTER(WHERE NOT home) ap,
           count(*) FILTER(WHERE NOT home AND ga=0) acs
    FROM sides GROUP BY team_id
)
'''
BIG_SIX = '(33,40,42,47,49,50)'


def independent(conn, query):
    op, p = query['op'], query['params']
    if 'season' not in p:
        raise NotImplementedError('Only explicit single-season checks are implemented')
    season = p['season']

    def rows(sql, params=()):
        return conn.execute(SIDES + sql, (season, *params)).fetchall()

    def one(sql, params=()):
        found = rows(sql, params)
        if len(found) != 1 or found[0]['answer'] is None:
            raise ValueError('Raw SQL did not find exactly one non-null answer')
        return str(found[0]['answer'])

    def winner(sql, params=()):
        candidates = rows(sql, params)
        if not candidates:
            raise ValueError('No raw SQL candidates')
        best = max(row['value'] for row in candidates)
        winners = [row['team_id'] for row in candidates if row['value'] == best]
        if len(winners) != 1:
            raise ValueError('Raw SQL candidates tied')
        return f'club:{winners[0]}'

    def rate(where, params):
        return one("SELECT round(100.0*count(*) FILTER(WHERE gf>ga)/nullif(count(*),0),1)::text || '%%' answer FROM sides WHERE " + where, params)

    predicates = {
        'count_away_clean_sheets': 'NOT home AND ga=0',
        'count_away_draws': 'NOT home AND gf=ga',
        'count_away_wins': 'NOT home AND gf>ga',
        'count_both_teams_scored': 'gf>0 AND ga>0',
        'count_failed_to_score': 'gf=0',
        'count_five_plus_total_goals': 'gf+ga>=5',
        'count_goalless_draws': 'gf=0 AND ga=0',
        'count_home_clean_sheets': 'home AND ga=0',
        'count_home_draws': 'home AND gf=ga',
        'count_one_goal_wins': 'gf-ga=1',
    }
    if op in predicates:
        return one('SELECT count(*) answer FROM sides WHERE team_id=%s AND ' + predicates[op], (p['team'],))
    if op == 'conditional_win_rate':
        condition = {'the team kept a clean sheet': 'ga=0', 'both teams scored': 'gf>0 AND ga>0',
                     'the team scored exactly two goals': 'gf=2', 'the team conceded exactly one goal': 'ga=1',
                     'at least four goals were scored in total': 'gf+ga>=4'}[p['condition']]
        return rate('team_id=%s AND ' + condition, (p['team'],))
    if op in {'win_rate_opponent_group', 'win_rate_opponent_group_venue', 'points_opponent_group'} and p['group'] == 'big six clubs':
        where = f'team_id=%s AND opponent_id IN {BIG_SIX}'
        if op.endswith('_venue'):
            where += ' AND home' if p['location'] == 'at home' else ' AND NOT home'
        if op == 'points_opponent_group':
            return one('SELECT sum(pts) answer FROM sides WHERE ' + where, (p['team'],))
        return rate(where, (p['team'],))
    if op == 'big_six_points_leader':
        return winner(f'SELECT team_id,sum(pts) value FROM sides WHERE team_id IN {BIG_SIX} AND opponent_id IN {BIG_SIX} GROUP BY team_id')
    if op == 'count_clubs_condition' and p['team_condition'] == 'earned more points away from home than at home':
        return one('SELECT count(*) answer FROM totals WHERE ap>hp')
    if op == 'unique_club_condition' and p['team_condition'] == 'kept at least ten clean sheets away from home':
        return one("SELECT 'club:' || team_id answer FROM totals WHERE acs>=10")
    if op in {'count_head_to_head_opponents', 'unique_head_to_head_opponent'}:
        condition = {'avoid defeat against in both league meetings': 'gf>=ga',
                     'draw against both home and away': 'gf=ga',
                     'beat both home and away': 'gf>ga',
                     'beat both home and away without conceding in either match': 'gf>0 AND ga=0'}[p['pair_condition']]
        candidates = rows('SELECT opponent_id FROM sides WHERE team_id=%s GROUP BY opponent_id HAVING count(*)=2 AND bool_and(' + condition + ')', (p['team'],))
        if op.startswith('count_'):
            return str(len(candidates))
        if len(candidates) != 1:
            raise ValueError('Opponent not unique')
        return f"club:{candidates[0]['opponent_id']}"
    if op == 'defeat_score':
        return one("SELECT gf::text || '-' || ga::text answer FROM sides WHERE team_id=%s AND opponent_id=%s AND home=%s AND gf<ga",
                   (p['team'], p['opponent'], p['venue'] == 'home'))
    if op == 'final_points_gap':
        return one('SELECT a.points-b.points answer FROM season_standings a JOIN season_standings b USING(league_id,season) WHERE a.league_id=39 AND a.season=%s AND a.team_id=%s AND b.team_id=%s',
                   (season, p['team'], p['opponent']))
    if op == 'half_table_goals_leader':
        metric = 'scored' if p['direction'] == 'scored' else 'conceded'
        return winner('SELECT t.team_id,t.' + metric + ' value FROM totals t JOIN season_standings s ON s.team_id=t.team_id AND s.league_id=39 AND s.season=%s WHERE (s.league_rank<=10)=%s', (season, p['half'] == 'top'))
    if op == 'home_minus_away_points':
        return one('SELECT hp-ap answer FROM totals WHERE team_id=%s', (p['team'],))
    if op == 'home_share_of_wins':
        return one("SELECT round(100.0*count(*) FILTER(WHERE home AND gf>ga)/nullif(count(*) FILTER(WHERE gf>ga),0),1)::text || '%%' answer FROM sides WHERE team_id=%s", (p['team'],))
    if op == 'league_club_largest_difference' and p['metric'] == 'away-minus-home points difference':
        return winner('SELECT team_id,ap-hp value FROM totals')
    if op == 'league_club_record' and p['metric'] == 'draws':
        return winner('SELECT team_id,draws value FROM totals')
    if op in {'league_exact_total_goals_matches', 'league_goalless_matches'}:
        return one('SELECT count(*) answer FROM sides WHERE home AND gf+ga=%s', (p.get('goals', 0),))
    if op == 'most_frequent_score':
        found = rows('SELECT gf,ga,count(*) n FROM sides WHERE team_id=%s AND home=%s GROUP BY gf,ga', (p['team'], p['venue'] == 'home'))
        top = max(r['n'] for r in found)
        scores = [f"{r['gf']}-{r['ga']}" for r in found if r['n'] == top]
        if len(scores) != 1:
            raise ValueError('Most frequent score tied')
        return scores[0]
    if op == 'opponent_most_goals_conceded':
        return winner('SELECT opponent_id team_id,sum(gf) value FROM sides WHERE team_id=%s GROUP BY opponent_id', (p['team'],))
    if op == 'runner_up':
        return one("SELECT 'club:' || team_id answer FROM season_standings WHERE league_id=39 AND season=%s AND league_rank=2", (season,))
    if op == 'sum_home_goals':
        return one('SELECT sum(gf) answer FROM sides WHERE team_id=%s AND home', (p['team'],))
    raise NotImplementedError('No independent implementation for this query')


def audit(bundle):
    verify_bundle(bundle)
    output = []
    with get_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        for job in read_jsonl(bundle / 'jobs.jsonl'):
            if job['kind'] != 'new_scope':
                continue
            try:
                answer = independent(conn, job['query'])
                output.append({'id': job['id'], 'answer': answer, 'expected': job['expected']['answer'],
                               'matched': canonical(answer) == canonical(job['expected']['answer'])})
            except (NotImplementedError, ValueError) as exc:
                output.append({'id': job['id'], 'matched': False, 'reason': str(exc)})
    result = {'method': 'Independent SQL over raw fixtures and final standings; same provider.',
              'matched': sum(r['matched'] for r in output), 'total': len(output), 'questions': output}
    dump(bundle / 'independent-sql-check.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    print(json.dumps(audit(parser.parse_args().bundle), indent=2))
