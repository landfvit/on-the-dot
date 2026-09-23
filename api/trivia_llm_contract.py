"""Untrusted language-model proposals, never SQL or authoritative answers."""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.trivia_generation_experiment import BY_KEY


FAMILIES = {
    'runs': ['streak_wins', 'streak_unbeaten', 'streak_scoring', 'streak_clean_sheets', 'streak_winless'],
    'windows': ['opening_points', 'closing_points', 'opening_goals', 'closing_goals',
                'home_opening_points', 'away_closing_points'],
    'transitions': ['wins_after_loss', 'wins_after_draw', 'draws_after_win'],
    'pairs': ['clean_sheet_pairs'],
    'chronology': ['first_win_opponent', 'last_win_opponent', 'last_clean_sheet_opponent'],
    'margins': ['biggest_home_win_opponent', 'biggest_away_win_opponent'],
}
SPLITS = {'runs': 'train', 'windows': 'train', 'margins': 'train',
          'pairs': 'valid', 'transitions': 'test', 'chronology': 'test'}
DEFINITIONS = {
    'streak_wins': 'Length of longest consecutive sequence of wins, measured in league matches.',
    'streak_unbeaten': 'Length of longest consecutive sequence without a defeat, in league matches.',
    'streak_scoring': 'Length of longest consecutive sequence scoring at least one goal, in league matches.',
    'streak_clean_sheets': 'Length of longest consecutive sequence conceding zero goals, in league matches.',
    'streak_winless': 'Length of longest consecutive sequence without a win, in league matches.',
    'opening_points': 'Points earned on the pitch in the first six league matches, before deductions.',
    'closing_points': 'Points earned on the pitch in the final six league matches, before deductions.',
    'opening_goals': 'Total goals scored in the first six league matches.',
    'closing_goals': 'Total goals scored in the final six league matches.',
    'home_opening_points': 'Points earned on the pitch in the first five home league matches, before deductions.',
    'away_closing_points': 'Points earned on the pitch in the final five away league matches, before deductions.',
    'wins_after_loss': 'Count adjacent league match pairs with a defeat immediately followed by a win.',
    'wins_after_draw': 'Count adjacent league match pairs with a draw immediately followed by a win.',
    'draws_after_win': 'Count adjacent league match pairs with a win immediately followed by a draw.',
    'clean_sheet_pairs': 'Count adjacent league match pairs with zero goals conceded in both; overlapping pairs count separately.',
    'first_win_opponent': 'Opponent beaten for the first league victory of the season.',
    'last_win_opponent': 'Opponent beaten for the last league victory of the season.',
    'last_clean_sheet_opponent': 'Opponent faced for the last league clean sheet of the season.',
    'biggest_home_win_opponent': 'Opponent beaten in the unique largest home league victory by goal difference.',
    'biggest_away_win_opponent': 'Opponent beaten in the unique largest away league victory by goal difference.',
}
SYSTEM = '''You author English football trivia. Choose one operation from the supplied catalogue and
write ONE precise question. Return only a JSON object with keys "question" and "query".
query has exactly: "version": "local-trivia-v1", "plan": catalogue key, "league_id": 39,
"team_id": supplied integer, "season": supplied integer start year.
Include the exact club name, Premier League and the supplied season label in the question.
Preserve every restriction of the chosen operation. Use actual kickoff order within this single
league season, never cup games or nominal matchweeks. Do not add unsupported filters or player facts.
Do not give, predict or reveal the answer. A separate database service will calculate it.
The question must stand alone without this prompt. No explanations, SQL, Markdown or extra keys.'''


class QueryProposal(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    version: Literal['local-trivia-v1']
    plan: str
    league_id: Literal[39]
    team_id: int = Field(gt=0)
    season: int = Field(ge=1900, le=2100)

    @field_validator('plan')
    @classmethod
    def known_plan(cls, value):
        if value not in BY_KEY:
            raise ValueError('Unsupported operation')
        return value


class Proposal(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question: str = Field(min_length=25, max_length=600)
    query: QueryProposal


def messages(scope, allowed_plans):
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': json.dumps({
        'task': 'Create one new trivia question; choose the operation yourself.',
        'scope': scope, 'catalogue': {key: DEFINITIONS[key] for key in allowed_plans},
    }, ensure_ascii=False)}]


def parse_proposal(raw, job):
    if len(raw) > 8000:
        raise ValueError('Oversized response')
    # Do not extract a convenient JSON substring from malformed or mixed output.
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result

    obj = json.loads(raw, object_pairs_hook=unique_keys)
    proposal = Proposal.model_validate(obj)
    query = proposal.query
    scope = job['scope']
    if (query.league_id, query.team_id, query.season) != (39, scope['team_id'], scope['season']):
        raise ValueError('Model changed the requested scope')
    if query.plan not in job['allowed_plans']:
        raise ValueError('Operation outside the requested category')
    text = proposal.question.casefold()
    if any(token.casefold() not in text for token in (scope['team_name'], scope['season_label'], 'Premier League')):
        raise ValueError('Question omitted or changed the explicit club, league or season')
    if proposal.question.count('?') != 1:
        raise ValueError('Expected one question')
    return proposal


def identity(query):
    return query['plan'], query['team_id'], query['season']
