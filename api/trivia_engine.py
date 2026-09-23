"""Deterministic football facts; minute labels are not second-precision clocks."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

ENGINE_VERSION = 'events-v2'
END_KEY = 100000
SCORING_DETAILS = {'Normal Goal', 'Penalty', 'Own Goal'}


def reconstruct(fixture, events, imported):
    reasons = []
    score = (fixture['home_goals'], fixture['away_goals'])
    result_valid = fixture['status'] == 'FT' and all(isinstance(n, int) and n >= 0 for n in score)
    if not result_valid:
        reasons.append('unfinished_or_invalid_result')
    fulltime = (fixture.get('fulltime_home'), fixture.get('fulltime_away'))
    if result_valid and all(n is not None for n in fulltime) and score != fulltime:
        result_valid = False
        reasons.append('fulltime_score_conflict')
    if not imported or not events:
        reasons.append('missing_event_feed')
    home, away = fixture['home_team_id'], fixture['away_team_id']
    changes = defaultdict(lambda: [0, 0])
    seen = set()
    for event in events:
        kind, detail = event.get('event_type'), event.get('event_detail')
        if kind == 'Var' and detail in ('Goal cancelled', None):
            reasons.append('unresolved_var_review')
        if kind != 'Goal':
            continue
        if detail == 'Missed Penalty':
            continue
        if detail not in SCORING_DETAILS:
            reasons.append('unknown_goal_type')
            continue
        minute, extra = event.get('elapsed_minute'), event.get('extra_minute') or 0
        if not isinstance(minute, int) or not 0 <= minute <= 90 or not 0 <= extra <= 30 or (extra and minute not in (45, 90)):
            reasons.append('invalid_goal_time')
            continue
        team = event.get('team_id')
        if team not in (home, away):
            reasons.append('unknown_scoring_team')
            continue
        identity = (minute, extra, team, detail, event.get('player_id'))
        if identity in seen:
            reasons.append('ambiguous_duplicate_goal')
        seen.add(identity)
        # API-Football event.team is the beneficiary, including own goals.
        changes[minute * 1000 + extra][0 if team == home else 1] += 1
    final = tuple(sum(change[i] for change in changes.values()) for i in (0, 1))
    halftime = tuple(sum(change[i] for key, change in changes.items() if key < 46000) for i in (0, 1))
    if final != score:
        reasons.append('goal_total_mismatch')
    if None in (fixture.get('halftime_home'), fixture.get('halftime_away')):
        reasons.append('missing_halftime_score')
    elif halftime != (fixture['halftime_home'], fixture['halftime_away']):
        reasons.append('halftime_score_mismatch')
    timeline_valid = result_valid and not reasons
    intervals = []
    if timeline_valid:
        start, totals = 0, [0, 0]
        for key, change in sorted(changes.items()):
            if key > start:
                intervals.append((start, key, *totals))
            totals = [a + b for a, b in zip(totals, change)]
            start = key
        intervals.append((start, END_KEY, *totals))
    return {'result_valid': result_valid, 'timeline_valid': timeline_valid,
            'reasons': sorted(set(reasons)), 'intervals': intervals}


def aggregate(spec, rows):
    evidence, matches = [], []
    timeline = spec.template == 'conditional_win_rate'
    exclusions = defaultdict(int)
    for row in rows:
        item = dict(row)
        item.pop('result_valid', None)
        item.pop('timeline_valid', None)
        valid = row['timeline_valid'] if timeline else row['result_valid']
        if timeline and row.get('checkpoint_for') is None:
            valid = False
        if not valid:
            item['disposition'] = 'excluded'
            item['reasons'] = row['reasons'] or ['missing_checkpoint']
            for reason in item['reasons']:
                exclusions[reason] += 1
        else:
            item['reasons'] = []
            included = row.get('weather_matches', True)
            if timeline:
                difference = row['checkpoint_for'] - row['checkpoint_against']
                condition = spec.condition
                included = included and {'eq': difference == condition.goal_difference,
                            'lte': difference <= condition.goal_difference,
                            'gte': difference >= condition.goal_difference}[condition.operator]
            item['disposition'] = 'matched' if included else 'not_matched'
            if included:
                matches.append(row)
        evidence.append(item)
    n = len(matches)
    wins = sum(row['result'] == 'W' for row in matches)
    draws = sum(row['result'] == 'D' for row in matches)
    losses = sum(row['result'] == 'L' for row in matches)
    goals = sum(row['goals_for'] for row in matches)
    conceded = sum(row['goals_against'] for row in matches)
    sheets = sum(row['goals_against'] == 0 for row in matches)
    percentage = spec.template in ('conditional_win_rate', 'win_rate', 'loss_rate', 'draw_rate')
    average = spec.template in ('goals_per_game', 'points_per_game')
    numerator = {'total_goals': goals, 'goals_per_game': goals, 'goals_conceded': conceded,
                 'clean_sheets': sheets, 'points_per_game': 3 * wins + draws,
                 'loss_rate': losses, 'draw_rate': draws}.get(spec.template, wins)
    decimals = 1 if percentage else 2 if average else 0
    value = (float((Decimal(numerator) * (100 if percentage else 1) / Decimal(n)).quantize(
        Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)) if (percentage or average) and n else numerator if n else None)
    excluded_count = sum(item['disposition'] == 'excluded' for item in evidence)
    warnings = []
    if excluded_count:
        warnings.append('incomplete_coverage')
    if 0 < n < spec.minimum_sample:
        warnings.append('small_sample')
    if not n:
        warnings.append('empty_sample')
    return {'answer': {'value': value, 'kind': 'percentage' if percentage else 'decimal' if average else 'integer',
                       'numerator': numerator, 'denominator': n if percentage or average else None,
                       'sample_size': n, 'rounding_decimals': decimals},
            'summary': {'played': n, 'wins': wins, 'draws': draws, 'losses': losses,
                        'goals_for': goals, 'goals_against': conceded, 'points': 3 * wins + draws, 'clean_sheets': sheets},
            'coverage': {'requested_matches': len(rows), 'eligible_matches': len(rows) - excluded_count,
                         'matched_matches': n, 'excluded_matches': excluded_count,
                         'exclusions': dict(exclusions), 'warnings': warnings,
                         'publishable': not warnings}, 'evidence': evidence}
