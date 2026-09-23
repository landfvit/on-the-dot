"""Closed query vocabulary for learning wording from the verified question bank.

The model receives a semantic query, never the source question or its answer.
Answers are calculated by the existing bank evaluator. Generated wording must
compile back to exactly the requested query before it can pass the audit.
"""
import json
import re
from string import Formatter

from api.trivia_bank_engine import CLUBS, question_tokens, season_label


FIELDS = {
    'team': r'club\d+', 'opponent': r'club\d+', 'left': r'club\d+', 'right': r'club\d+',
    'season': r'20\d{2}/\d{2}', 'start': r'20\d{2}/\d{2}', 'end': r'20\d{2}/\d{2}',
    'venue': r'home|away', 'location': r'at home|away from home',
    'group': r'big six clubs|clubs that finished in the top four|clubs that finished in the bottom three',
    'condition': r'both teams scored|the team kept a clean sheet|the team scored exactly two goals|the team conceded exactly one goal|at least four goals were scored in total',
    'metric': r'[a-z -]+', 'score': r'\d+-\d+', 'score2': r'\d+-\d+',
    'goals': r'\d+', 'position': r'champions|runners-up', 'half': r'bottom|top',
    'direction': r'scored|conceded',
    'comparison': r'finished higher|finished with more league points|scored more league goals|conceded fewer league goals',
    'pair_condition': r'avoid defeat against in both league meetings|draw against both home and away|beat both home and away without conceding in either match|beat both home and away',
    'team_condition': r'completed the season without a goalless draw|conceded at least 80 goals|scored at least 70 goals|earned more points away from home than at home|kept at least ten clean sheets away from home|won more away matches than home matches|finished with a negative goal difference despite ending in the top half',
}
CLUB_FIELDS = {'team', 'opponent', 'left', 'right'}
SEASON_FIELDS = {'season', 'start', 'end'}

# Each operator has one approved rendering, but the inference prompt contains
# only the operator name and typed parameters, not these question templates.
TEMPLATES = {
    'compare_final_table': 'in the {season} premier league, which team {comparison}: {left} or {right}?',
    'champion': 'which club finished as premier league champions in {season}?',
    'runner_up': 'which club finished second in the {season} premier league table?',
    'fixture_outcome': "what was the outcome of {team}'s home premier league meeting with {opponent} in {season}: a {team} win, a draw, or a {opponent} win?",
    'fixture_both_teams_scored': 'did both teams score when {team} hosted {opponent} in the {season} premier league?',
    'fixture_score_choices': "with the home team's goals first, which was the score when {team} hosted {opponent} in {season}: {score} or {score2}?",
    'win_rate_opponent_group': 'what was the win rate of {team} against {group} in the {season} premier league, rounded to one decimal place?',
    'win_rate_opponent_group_venue': 'what was the win rate of {team} {location} against {group} in the {season} premier league, rounded to one decimal place?',
    'win_rate_big_six_window': 'across {start}-{end}, what was the {venue} premier league win rate of {team} against the other clubs in the fixed big six group, rounded to one decimal place?',
    'points_opponent_group': 'how many premier league points did {team} earn against {group} in {season}?',
    'conditional_win_rate': 'what was the win rate of {team} in {season} premier league matches in which {condition}, rounded to one decimal place?',
    'head_to_head_clean_sheets': 'how many premier league clean sheets did {team} keep against {opponent} across {start}-{end}?',
    'head_to_head_win_rate': 'what was the premier league win rate of {team} against {opponent} across {start}-{end}, rounded to one decimal place?',
    'home_share_of_wins': 'what percentage of the premier league wins recorded by {team} in {season} came at home, rounded to one decimal place?',
    'away_share_of_goals': 'what percentage of the premier league goals scored by {team} in {season} came away from home, rounded to one decimal place?',
    'most_frequent_score': 'what was the single most frequent {venue} premier league scoreline for {team} in {season}, writing their goals first?',
    'identify_defeated_opponent': 'which club did {team} beat {score} {location} in the {season} premier league?',
    'identify_away_winner': 'which club won {score} away at {team} in the {season} premier league?',
    'defeat_score': "what was the final score of the {venue} premier league defeat for {team} against {opponent} in {season}, with {team}'s goals first?",
    'two_match_fingerprint': "against which club did {team} record a {score} home result and a {score2} away result in the {season} premier league, with {team}'s score written first?",
    'opponent_most_goals_conceded': 'which opponent conceded the most goals to {team} across their two premier league meetings in {season}?',
    'unique_head_to_head_opponent': 'which was the only opponent that {team} managed to {pair_condition} in the {season} premier league?',
    'count_head_to_head_opponents': 'how many different opponents did {team} {pair_condition} in the {season} premier league?',
    'club_peak_season': 'in which season within {start}-{end} did {team} record their most {metric} in the premier league?',
    'club_peak_goal_difference': 'in which season within {start}-{end} did {team} record their highest goal difference in the premier league?',
    'league_club_record': 'which club recorded the most {metric} in the {season} premier league?',
    'league_club_largest_difference': 'which club recorded the largest {metric} in the {season} premier league?',
    'big_six_points_leader': 'which club earned the most points in the big six head-to-head mini-league in the {season} premier league?',
    'points_against_title_contender': 'how many premier league points did {team} take from the eventual {position}, {opponent}, in {season}?',
    'half_table_goals_leader': 'among clubs finishing in the {half} half, which {direction} the most goals in the {season} premier league?',
    'unique_club_condition': 'which was the only club that {team_condition} in the {season} premier league?',
    'count_clubs_condition': 'how many clubs {team_condition} in the {season} premier league?',
    'league_goalless_matches': 'how many matches in the {season} premier league finished with no goals?',
    'league_exact_total_goals_matches': 'how many matches in the {season} premier league finished with exactly {goals} total goals?',
    'league_peak_season': 'which premier league season within {start}-{end} had the most {metric}?',
    'final_points_gap': 'by how many points did {team} finish above {opponent} in the {season} premier league title race?',
    'champion_away_dropped_points': 'how many premier league points did champions {team} drop away from home in {season}?',
    'count_failed_to_score': 'in how many premier league matches in {season} did {team} fail to score?',
    'count_goalless_draws': 'how many of the premier league draws recorded by {team} in {season} were goalless?',
    'count_five_plus_total_goals': 'how many premier league matches involving {team} in {season} produced at least five total goals?',
    'count_one_goal_wins': 'how many premier league wins did {team} achieve by exactly one goal in {season}?',
    'count_three_plus_goal_wins': 'how many premier league wins did {team} achieve by a margin of at least three goals in {season}?',
    'sum_home_goals': 'how many of the premier league goals scored by {team} in {season} came at home?',
    'sum_away_goals_conceded': 'how many premier league goals did {team} concede away from home in {season}?',
    'count_away_clean_sheets': 'how many away premier league clean sheets did {team} keep in {season}?',
    'count_home_clean_sheets': 'how many home premier league clean sheets did {team} keep in {season}?',
    'count_away_wins': 'how many away premier league wins did {team} record in {season}?',
    'count_home_wins': 'how many of the 19 home premier league matches did {team} win in {season}?',
    'count_both_teams_scored': 'in how many premier league matches involving {team} in {season} did both teams score?',
    'count_one_goal_defeats': 'how many premier league defeats did {team} suffer by exactly one goal in {season}?',
    'count_wins_without_conceding': 'how many premier league wins did {team} record without conceding a goal in {season}?',
    'count_one_total_goal': 'how many premier league matches involving {team} in {season} contained exactly one goal in total?',
    'count_home_draws': 'how many home premier league draws did {team} record in {season}?',
    'count_away_draws': 'how many away premier league draws did {team} record in {season}?',
    'count_defeats_with_goal': 'in how many premier league defeats in {season} did {team} still score at least one goal?',
    'count_four_plus_conceded': 'in how many premier league matches in {season} did {team} concede at least four goals?',
    'count_exactly_two_scored': 'in how many premier league matches in {season} did {team} score exactly two goals?',
    'home_minus_away_points': 'what was the difference between home and away premier league points earned by {team} in {season}, calculated as home minus away?',
}


def pattern(template):
    parts, seen = [], set()
    for literal, name, _, _ in Formatter().parse(template):
        parts.append(re.escape(literal))
        if name:
            parts.append(f'(?P={name})' if name in seen else f'(?P<{name}>{FIELDS[name]})')
            seen.add(name)
    return re.compile(''.join(parts))


PATTERNS = {key: pattern(value) for key, value in TEMPLATES.items()}


def compile_question(text):
    text = question_tokens(text)
    for op, regex in PATTERNS.items():
        if match := regex.fullmatch(text):
            params = match.groupdict()
            for key, value in params.items():
                if key in CLUB_FIELDS:
                    params[key] = int(value[4:])
                    if params[key] not in CLUBS:
                        raise ValueError('Unknown club')
                elif key in SEASON_FIELDS:
                    params[key] = int(value[:4])
                    if value != season_label(params[key]):
                        raise ValueError('Invalid season')
                elif key == 'goals':
                    params[key] = int(value)
            return {'op': op, 'params': params}
    raise ValueError('No supported semantic query for this wording')


def render(query):
    if set(query) != {'op', 'params'} or query['op'] not in TEMPLATES:
        raise ValueError('Unknown query operator or fields')
    params = query['params']
    fields = {field for _, field, _, _ in Formatter().parse(TEMPLATES[query['op']]) if field}
    if set(params) != fields:
        raise ValueError('Query parameters do not match operator')
    values = {}
    for key, value in params.items():
        if key in CLUB_FIELDS | SEASON_FIELDS | {'goals'} and type(value) is not int:
            raise ValueError('Integer parameter required')
        values[key] = CLUBS[value] if key in CLUB_FIELDS else season_label(value) if key in SEASON_FIELDS else str(value)
    text = TEMPLATES[query['op']].format(**values)
    if compile_question(text) != query:
        raise ValueError('Query did not round-trip')
    return text


def messages(query):
    render(query)
    clubs = {str(value): CLUBS[value] for key, value in query['params'].items() if key in CLUB_FIELDS}
    return [
        {'role': 'system', 'content': 'Write one precise English Premier League trivia question for the supplied query. Preserve every condition, club, venue, score perspective and explicit season. Season numbers are starting years; 2017 means 2017/18. Percentages must request rounding to one decimal place. Return only JSON with one string field: question. Do not answer the question.'},
        {'role': 'user', 'content': json.dumps({'query': query, 'clubs': clubs}, ensure_ascii=False)},
    ]


def parse_output(raw, query):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON field')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique_pairs)
    if not isinstance(value, dict) or set(value) != {'question'} or not isinstance(value['question'], str):
        raise ValueError('Expected one question string')
    if len(value['question']) > 1200 or compile_question(value['question']) != query:
        raise ValueError('Generated wording does not compile to the requested query')
    return value['question']
