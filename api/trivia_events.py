"""Event-based questions evaluated exclusively against an immutable trivia snapshot."""
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
import unicodedata
import re

from fastapi import HTTPException

from api.trivia_models import GoalFilter

EVENT_TEMPLATES = {'player_goals', 'top_scorer', 'comeback_wins', 'most_comeback_wins'}


def normalized_name(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                   if c.isalnum() and not unicodedata.combining(c))


def display_surname(name):
    # Preserve compound surnames: E. Smith Rowe -> Smith Rowe, never Rowe.
    match = re.match(r'^(?:[^\W\d_]\.\s*)+(.+)$', name or '')
    return match.group(1).strip() if match else None


def aggregate_events(spec, rows, events, identities=()):
    fixtures, goals = defaultdict(list), defaultdict(list)
    for row in rows:
        fixtures[row['fixture_id']].append(row)
    for event in events:
        goals[event['fixture_id']].append(event)
    scorer = spec.template in ('player_goals', 'top_scorer')
    ranking = spec.template in ('top_scorer', 'most_comeback_wins')
    filters = spec.goal_filter or GoalFilter()
    threshold = None if filters.after_minute is None else filters.after_minute * 1000 + filters.extra
    totals, names, aliases, exclusions = Counter(), {}, defaultdict(set), Counter()
    alias_owners = defaultdict(set)
    surname_policy = scorer and spec.name_policy == 'unique-surname-v1'
    for entity in [*events, *identities] if scorer else rows:
        ident = entity['player_id'] if scorer else entity['team_id']
        entity_names = [entity.get('player_name'), *entity.get('aliases', [])] if scorer else [entity['team_name']]
        if surname_policy:
            entity_names.append(display_surname(entity.get('player_name')))
        for name in entity_names:
            if name:
                alias_owners[normalized_name(name)].add(ident)
    evidence, eligible = [], 0
    for fid, teams in fixtures.items():
        first = teams[0]
        reasons = set(first['reasons'] if not first['timeline_valid'] else [])
        if not first['timeline_valid']:
            reasons.add('invalid_goal_timeline')
        if scorer and not first.get('scorers_valid'):
            reasons.update(first.get('scorer_reasons') or ['missing_scorer_snapshot'])
        if scorer and filters.role == 'substitute' and first.get('scorers_valid') and not first.get('substitutes_valid'):
            reasons.update(first.get('substitute_reasons') or ['unverified_scorer_role'])
        item = {key: first.get(key) for key in ('fixture_id', 'season', 'match_date', 'team_name',
                    'opponent_name', 'is_home', 'goals_for', 'goals_against', 'result')}
        item.update(reasons=sorted(reasons), contributions=[], match_label=(
            f"{first['team_name']} vs {first['opponent_name']}" if first['is_home'] else
            f"{first['opponent_name']} vs {first['team_name']}"))
        item['final_home'] = first['goals_for'] if first['is_home'] else first['goals_against']
        item['final_away'] = first['goals_against'] if first['is_home'] else first['goals_for']
        if not spec.team_id:
            home_won = (first['result'] == 'W') == first['is_home']
            item['result_label'] = 'Draw' if first['result'] == 'D' else 'Home win' if home_won else 'Away win'
        if reasons:
            item['disposition'] = 'excluded'
            exclusions.update(reasons)
        else:
            eligible += 1
            if scorer:
                selected_teams = {row['team_id'] for row in teams}
                per_match = Counter()
                for event in goals[fid]:
                    if event['event_type'] != 'Goal' or event['event_detail'] not in ('Normal Goal', 'Penalty'):
                        continue
                    if event['team_id'] not in selected_teams or (spec.player_id and event['player_id'] != spec.player_id):
                        continue
                    if threshold is not None and event['clock_key'] <= threshold:
                        continue
                    if filters.role == 'substitute' and event['scorer_role'] != 'substitute':
                        continue
                    pid = event['player_id']
                    names[pid] = event['player_name']
                    aliases[pid].update(event['aliases'])
                    if surname_policy and (surname := display_surname(event['player_name'])):
                        aliases[pid].add(surname)
                    per_match[pid] += 1
                    item['contributions'].append({key: event[key] for key in
                        ('player_id', 'player_name', 'team_id', 'clock_key', 'event_detail', 'scorer_role')})
                totals.update({pid: 1 if filters.count == 'scoring_matches' else n for pid, n in per_match.items()})
            else:
                for row in teams:
                    if row['was_behind'] and row['result'] == 'W':
                        tid = row['team_id']
                        totals[tid] += 1
                        names[tid] = row['team_name']
                        aliases[tid].add(row['team_name'])
                        item['contributions'].append({'team_id': tid, 'team_name': row['team_name'], 'comeback_win': True})
            item['disposition'] = 'matched' if item['contributions'] else 'not_matched'
        evidence.append(item)
    leaderboard = [{'entity_id': ident, 'name': names[ident], 'value': value}
                   for ident, value in sorted(totals.items(), key=lambda item: (-item[1], names[item[0]], item[0]))]
    maximum = leaderboard[0]['value'] if leaderboard else None
    winners = [item for item in leaderboard if item['value'] == maximum]
    excluded = sum(row['disposition'] == 'excluded' for row in evidence)
    warnings = []
    if excluded:
        warnings.append('incomplete_coverage')
    if not eligible:
        warnings.append('empty_sample')
    elif eligible < spec.minimum_sample:
        warnings.append('small_sample')
    if ranking and not winners:
        warnings.append('no_ranking_winner')
    value = (maximum if ranking else sum(totals.values())) if eligible else None
    answer = {'kind': 'entity' if ranking else 'integer', 'value': value,
              'sample_size': eligible, 'numerator': None if ranking else value,
              'denominator': None, 'rounding_decimals': 0}
    if ranking:
        winner_ids = {w['entity_id'] for w in winners}
        answer.update(entity_type='player' if scorer else 'team', label=' / '.join(w['name'] for w in winners),
                      accepted=[{**w, 'aliases': sorted(name for name in aliases[w['entity_id']] | {w['name']}
                          if alias_owners[normalized_name(name)] <= winner_ids)} for w in winners])
        if winners and not any(w['aliases'] for w in answer['accepted']):
            warnings.append('ambiguous_winner_name')
    return {'answer': answer, 'coverage': {'requested_matches': len(fixtures), 'eligible_matches': eligible,
            'matched_matches': sum(row['disposition'] == 'matched' for row in evidence),
            'excluded_matches': excluded, 'exclusions': dict(exclusions), 'warnings': warnings,
            'publishable': not warnings}, 'evidence': evidence, 'leaderboard': leaderboard}


def evaluate_events(conn, spec, data, seasons, league):
    if spec.template not in data['summary'].get('capabilities', []):
        raise HTTPException(409, 'This dataset predates event questions; build a new snapshot')
    params = [data['dataset_id'], spec.league_id]
    conditions = ['f.dataset_id=%s', 'f.league_id=%s']
    if spec.period.mode == 'dates':
        conditions.extend(['f.match_date >= %s', 'f.match_date < %s'])
        params.extend([datetime.combine(spec.period.start, time.min, timezone.utc),
                       datetime.combine(spec.period.end + timedelta(days=1), time.min, timezone.utc)])
        period_label = f'{spec.period.start} to {spec.period.end} (UTC)'
    else:
        conditions.append('f.season = ANY(%s)')
        params.append(seasons)
        period_label = ', '.join(f'{s}/{str(s + 1)[-2:]}' for s in sorted(seasons))
    team = None
    if spec.team_id:
        team = conn.execute('''SELECT team_name FROM trivia_match_team_facts
            WHERE dataset_id=%s AND league_id=%s AND team_id=%s LIMIT 1''',
            (data['dataset_id'], spec.league_id, spec.team_id)).fetchone()
        if not team:
            raise HTTPException(422, 'Team is not present in this competition')
        conditions.append('f.team_id=%s')
        params.append(spec.team_id)
    if spec.venue != 'all':
        conditions.append('f.is_home=%s')
        params.append(spec.venue == 'home')
    rows = conn.execute('''SELECT f.*, q.timeline_valid,q.reasons,
            p.scorers_valid,p.substitutes_valid,p.reasons AS scorer_reasons,p.substitute_reasons,
            EXISTS(SELECT 1 FROM trivia_match_state_intervals i
                WHERE i.dataset_id=f.dataset_id AND i.fixture_id=f.fixture_id
                AND CASE WHEN f.is_home THEN i.home_goals<i.away_goals ELSE i.away_goals<i.home_goals END) AS was_behind
        FROM trivia_match_team_facts f JOIN trivia_match_data_quality q USING(dataset_id,fixture_id)
        LEFT JOIN trivia_player_data_quality p USING(dataset_id,fixture_id)
        WHERE ''' + ' AND '.join(conditions) + ' ORDER BY f.match_date,f.fixture_id,f.is_home DESC', params).fetchall()
    player = None
    if spec.player_id:
        player = conn.execute('''SELECT p.player_name FROM trivia_match_player_facts p
            JOIN trivia_match_team_facts f USING(dataset_id,fixture_id,team_id)
            WHERE p.dataset_id=%s AND f.league_id=%s AND p.player_id=%s LIMIT 1''',
            (data['dataset_id'], spec.league_id, spec.player_id)).fetchone()
        if not player:
            raise HTTPException(422, 'Player is not present in this competition snapshot')
    events = []
    if spec.template in ('player_goals', 'top_scorer') and rows:
        events = conn.execute('''SELECT * FROM trivia_event_facts WHERE dataset_id=%s
            AND fixture_id=ANY(%s) AND event_type='Goal' ORDER BY fixture_id,source_order''',
            (data['dataset_id'], sorted({r['fixture_id'] for r in rows}))).fetchall()
    identities = []
    if spec.name_policy == 'unique-surname-v1' and rows:
        identities = conn.execute('''SELECT DISTINCT player_id,player_name,aliases FROM trivia_match_player_facts
            WHERE dataset_id=%s AND fixture_id=ANY(%s)''',
            (data['dataset_id'], sorted({r['fixture_id'] for r in rows}))).fetchall()
    result = aggregate_events(spec, rows, events, identities)
    context = f"{league['name']}, {period_label}"
    if team and spec.template in ('player_goals', 'top_scorer'):
        context += f", for {team['team_name']}"
    if spec.venue != 'all':
        context += f', {spec.venue} appearances of the scoring/winning team'
    goal_filter = spec.goal_filter or GoalFilter()
    qualifier = ' as a substitute' if goal_filter.role == 'substitute' else ''
    if goal_filter.after_minute is not None:
        clock = str(goal_filter.after_minute) + (f'+{goal_filter.extra}' if goal_filter.extra else '')
        qualifier += f' after recorded minute {clock}'
    if spec.template == 'player_goals':
        question = (f"In how many matches did {player['player_name']} score{qualifier}?" if goal_filter.count == 'scoring_matches'
                    else f"How many goals did {player['player_name']} score{qualifier}?")
    elif spec.template == 'top_scorer':
        question = (f'Which player scored in the most matches{qualifier}?' if goal_filter.count == 'scoring_matches'
                    else f'Which player scored the most goals{qualifier}?')
    elif spec.template == 'comeback_wins':
        question = f"How many matches did {team['team_name']} win after being behind at a recorded-minute checkpoint?"
    else:
        question = 'Which team won the most matches after being behind at a recorded-minute checkpoint?'
    question += f' ({context})'
    if result['answer']['kind'] == 'entity':
        question += ' Name any joint leader if tied.'
    return {**result, 'dataset_id': data['dataset_id'], 'dataset_created_at': data['created_at'],
            'engine_version': data['engine_version'], 'question_text': question,
            'resolved_seasons': sorted({row['season'] for row in rows}), 'specification': spec.model_dump(mode='json')}
