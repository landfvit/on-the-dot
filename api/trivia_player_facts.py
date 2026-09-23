"""Snapshot player identities and event evidence without inferring bench appearances."""
from collections import defaultdict


def clock_key(event):
    minute, extra = event.get('elapsed_minute'), event.get('extra_minute') or 0
    if not isinstance(minute, int) or not isinstance(extra, int):
        return None
    if not 0 <= minute <= 90 or not 0 <= extra <= 30 or (extra and minute not in (45, 90)):
        return None
    return minute * 1000 + extra


def identity(player_id, raw_name, identities):
    player = identities.get(player_id, {})
    name = player.get('player_name') or raw_name or f'Player {player_id}'
    first, last = player.get('first_name') or '', player.get('last_name') or ''
    names = {name, raw_name}
    if first and last:
        names.update([f'{first} {last}', f'{first.split()[0]} {last}'])
    if first and '. ' in name and name.split('. ', 1)[0].casefold() == first[0].casefold():
        names.add(f"{first.split()[0]} {name.split('. ', 1)[1]}")
    return name, sorted(n for n in names if n)


def player_facts(fixture, events, lineups, statistics, identities, timeline_valid):
    teams = {fixture['home_team_id'], fixture['away_team_id']}
    starters, bench = defaultdict(set), defaultdict(set)
    for row in lineups:
        if row['team_id'] in teams and row.get('player_id'):
            target = starters if row['lineup_type'] == 'start_xi' else bench
            target[row['team_id']].add(row['player_id'])
    entries = defaultdict(list)
    for event in events:
        if event['event_type'] == 'subst' and event.get('assist_player_id') and clock_key(event) is not None:
            entries[(event['team_id'], event['assist_player_id'])].append(clock_key(event))
    stats = {(r['team_id'], r['player_id']): r for r in statistics if r['team_id'] in teams}
    memberships = defaultdict(set)
    for row in [*lineups, *statistics]:
        if row.get('player_id') and row['team_id'] in teams:
            memberships[row['player_id']].add(row['team_id'])

    def role(team, player, goal_time=None):
        if len(memberships[player]) > 1 or player in starters[team] & bench[team]:
            return None
        if player in starters[team]:
            return None if entries.get((team, player)) else 'starter'
        times = entries.get((team, player), [])
        # Equal-minute entry and goal are consistent, but not second-precision evidence.
        if len(times) == 1 and (goal_time is None or times[0] <= goal_time):
            return 'substitute'
        return None

    player_rows = []
    keys = set(stats) | {(r['team_id'], r['player_id']) for r in lineups if r.get('player_id') and r['team_id'] in teams}
    keys |= {key for key in entries if key[0] in teams}
    keys |= {(e['team_id'], e['player_id']) for e in events if e.get('player_id') and e['team_id'] in teams
             and e['event_type'] == 'Goal' and e.get('event_detail') in ('Normal Goal', 'Penalty')}
    raw_names = {(r['team_id'], r['player_id']): r.get('player_name') for r in [*events, *lineups] if r.get('player_id')}
    for team, player in sorted(keys):
        stat = stats.get((team, player), {})
        name, aliases = identity(player, stat.get('player_name') or raw_names.get((team, player)), identities)
        player_role = role(team, player)
        scored = timeline_valid and any(e.get('player_id') == player and e['team_id'] == team
            and e['event_type'] == 'Goal' and e.get('event_detail') in ('Normal Goal', 'Penalty') for e in events)
        appeared = player_role is not None or (stat.get('minutes') or 0) > 0 or scored
        metrics = {k: stat.get(k) for k in ('minutes', 'goals', 'assists', 'shots_total', 'shots_on_goal',
                   'passes_total', 'key_passes', 'tackles_total', 'interceptions', 'yellow_cards',
                   'yellow_red_cards', 'red_cards', 'rating')}
        if metrics['rating'] is not None:
            metrics['rating'] = float(metrics['rating'])
        player_rows.append(dict(team_id=team, player_id=player, player_name=name, aliases=aliases,
                                appeared=appeared, role=player_role, statistics=metrics))

    reasons, substitute_reasons, event_rows = set(), set(), []
    if not timeline_valid:
        reasons.add('invalid_goal_timeline')
    for event in events:
        player, team, key = event.get('player_id'), event.get('team_id'), clock_key(event)
        name, aliases = identity(player, event.get('player_name'), identities) if player else (None, [])
        scorer_role = None
        if event['event_type'] == 'Goal' and event.get('event_detail') in ('Normal Goal', 'Penalty'):
            if not player or not name or name.startswith('Player '):
                reasons.add('missing_scorer_identity')
            elif memberships[player] and memberships[player] != {team}:
                reasons.add('scorer_team_conflict')
            if key is not None:
                scorer_role = role(team, player, key)
            if scorer_role is None:
                substitute_reasons.add('unverified_scorer_role')
        event_rows.append(dict(source_order=event['source_order'], team_id=team, player_id=player,
            assist_player_id=event.get('assist_player_id'), player_name=name, aliases=aliases,
            clock_key=key, event_type=event['event_type'], event_detail=event.get('event_detail'), scorer_role=scorer_role))
    return {'players': player_rows, 'events': event_rows, 'scorers_valid': not reasons,
            'substitutes_valid': not reasons and not substitute_reasons,
            'reasons': sorted(reasons), 'substitute_reasons': sorted(substitute_reasons)}
