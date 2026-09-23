"""Controlled team-query grammar. Parsing never executes SQL or guesses an entity."""
import re
import unicodedata
from functools import lru_cache
from typing import Literal
from uuid import UUID

from lark import Lark, UnexpectedInput
from pydantic import Field, model_validator
from rapidfuzz import fuzz, process

from api.trivia_models import OpponentFilter, SeasonSelection, StrictModel, TriviaSpec

PARSER_VERSION = 'team-query-v1'
Metric = Literal['win_rate', 'loss_rate', 'draw_rate', 'total_wins', 'total_goals',
                 'goals_conceded', 'goals_per_game', 'points_per_game', 'clean_sheets']
METRICS = {
    'win rate': 'win_rate', 'win percentage': 'win_rate', 'percentage of games won': 'win_rate',
    'loss rate': 'loss_rate', 'loss percentage': 'loss_rate', 'draw rate': 'draw_rate',
    'draw percentage': 'draw_rate', 'wins': 'total_wins', 'total wins': 'total_wins',
    'goals scored': 'total_goals', 'total goals': 'total_goals', 'goals conceded': 'goals_conceded',
    'goals per game': 'goals_per_game', 'goals per match': 'goals_per_game', 'average goals': 'goals_per_game',
    'points per game': 'points_per_game', 'points per match': 'points_per_game', 'clean sheets': 'clean_sheets',
}
DEFINITIONS = {
    'win_rate': 'Wins / eligible matches x 100; one decimal place.',
    'loss_rate': 'Losses / eligible matches x 100; one decimal place.',
    'draw_rate': 'Draws / eligible matches x 100; one decimal place.',
    'total_wins': 'Number of eligible matches won.',
    'total_goals': 'Team goals, including own goals credited to the team.',
    'goals_conceded': 'Opponent goals in eligible matches.',
    'goals_per_game': 'Team goals / eligible matches; two decimal places.',
    'points_per_game': '(3 x wins + draws) / eligible matches, before deductions; two decimal places.',
    'clean_sheets': 'Eligible matches with zero goals conceded, including 0-0 draws.',
}


class QueryFilters(StrictModel):
    venue: Literal['all', 'home', 'away'] = 'all'
    opponents: OpponentFilter | None = None


class SportsQuery(StrictModel):
    schema_version: Literal['team-query-v1'] = PARSER_VERSION
    dataset_id: UUID
    entity_type: Literal['team'] = 'team'
    entity_id: int = Field(gt=0)
    competition_id: int = Field(gt=0)
    metric: Metric
    filters: QueryFilters = Field(default_factory=QueryFilters)
    timeframe: SeasonSelection
    minimum_sample: int = Field(default=10, ge=1, le=1000)

    @model_validator(mode='after')
    def compatible(self):
        self.specification()
        return self

    def specification(self):
        return TriviaSpec(template=self.metric, league_id=self.competition_id, team_id=self.entity_id,
            period=self.timeframe, venue=self.filters.venue, opponents=self.filters.opponents,
            minimum_sample=self.minimum_sample, query_version=self.schema_version)


class ParseRequest(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    competition_id: int = Field(gt=0)
    dataset_id: UUID | None = None
    minimum_sample: int = Field(default=10, ge=1, le=1000)


def normalize(text):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                           if not unicodedata.combining(c)).split()).removesuffix('?').strip()


def terminal(names):
    # Values come from the catalogue, never grammar operators from user input.
    return '/(?:' + '|'.join(re.escape(n).replace('/', r'\/') for n in sorted(set(names), key=lambda n: (-len(n), n))) + r')(?!\w)/'


@lru_cache(maxsize=16)
def grammar(teams, competitions):
    return Lark(r'''
        start: entity metric clause*
        entity: TEAM
        metric: METRIC
        ?clause: opponent | home | away | competition | season | last | since | between | all_time
        opponent: ("against" | "vs" | "versus") ["the"] (group | entity)
        group: ("big 6" | "big six") ["teams" | "clubs"]
        home: "at home" | "home"
        away: "away" | "away from home"
        competition: "in" ["the"] COMPETITION
        season: ["in" | "during"] SEASON
        last: ["in"] ["the"] "last" [INT] ["completed"] ("season" | "seasons")
        since: "since" YEAR
        between: "between" YEAR "and" YEAR
        all_time: "all time"
        SEASON.3: /[12][0-9]{3}\/(?:[12][0-9]{3}|[0-9]{2})(?!\w)/
        YEAR.2: /[12][0-9]{3}(?!\w)/
        INT: /[0-9]{1,3}(?!\w)/
        %import common.WS
        %ignore WS
    ''' + '\nTEAM: ' + terminal(teams) + '\nCOMPETITION: ' + terminal(competitions) +
        '\nMETRIC: ' + terminal(METRICS), parser='lalr', maybe_placeholders=False)


class QueryIssue(ValueError):
    def __init__(self, message, suggestions=None):
        super().__init__(message)
        self.suggestions = suggestions or []


def resolve_period(kind, values, catalogue):
    available = sorted(s['season'] for s in catalogue['seasons'])
    completed = [s['season'] for s in catalogue['seasons'] if s['fixtures'] and s['finished'] == s['fixtures']]
    latest = max(completed) if completed else None
    if kind == 'season':
        start, end = values[0].split('/')
        start = int(start)
        if end != str(start + 1) and end != str(start + 1)[-2:]:
            raise QueryIssue('A season must span consecutive years, for example 2017/18.')
        seasons, definition = [start], 'Explicit season.'
    elif kind in ('last', 'since'):
        if latest is None:
            raise QueryIssue('No completed season exists in this snapshot.')
        if kind == 'last':
            count = int(values[0]) if values else 1
            if not 1 <= count <= 100:
                raise QueryIssue('Choose between 1 and 100 seasons.')
            start = latest - count + 1
        else:
            start = int(values[0])
        seasons = list(range(start, latest + 1))
        definition = ('Consecutive seasons through the latest completed season in this snapshot. '
                      'Since YEAR means season starting YEAR, not January 1. Missing seasons are never skipped.')
    elif kind == 'between':
        seasons = list(range(int(values[0]), int(values[1]) + 1))
        definition = 'Inclusive range of season start years.'
    else:
        seasons = available
        definition = 'All seasons in this snapshot only, including unfinished seasons; not all football history.'
    if not seasons or len(seasons) > 100:
        raise QueryIssue('The period is empty, reversed or longer than 100 seasons.')
    missing = set(seasons) - set(available)
    if missing:
        raise QueryIssue('Requested seasons are missing: ' + ', '.join(map(str, sorted(missing))) + '. The range was not reduced.')
    return seasons, definition


def parse_query(request, catalogue):
    text = normalize(request.text)
    aliases = {}
    names = {t['team_id']: t['team_name'] for t in catalogue['teams']}
    for team in catalogue['teams']:
        for alias in [team['team_name'], *team.get('aliases', [])]:
            aliases.setdefault(normalize(alias), set()).add(team['team_id'])
    recognized = {}

    def entity(token):
        ids = sorted(aliases[str(token)])
        if len(ids) != 1:
            raise QueryIssue(f'Ambiguous team: {token}. Choose a full club name.',
                             [{'name': names[i], 'team_id': i} for i in ids])
        return ids[0]

    try:
        tree = grammar(tuple(sorted(aliases)), tuple(catalogue['competition_aliases'])).parse(text)
        team = entity(tree.children[0].children[0])
        recognized['team'] = names[team]
        metric = METRICS[str(tree.children[1].children[0])]
        recognized['metric'] = metric
        filters, timeframe, period_definition, seen = {}, None, None, set()
        for clause in tree.children[2:]:
            kind = str(clause.data)
            category = 'venue' if kind in ('home', 'away') else 'period' if kind in ('season', 'last', 'since', 'between', 'all_time') else kind
            if category in seen:
                raise QueryIssue(f'Multiple {category} clauses. Choose one explicitly.')
            seen.add(category)
            if kind in ('home', 'away'):
                filters['venue'] = kind
                recognized['venue'] = kind
            elif kind == 'opponent':
                target = clause.children[0]
                if target.data == 'group':
                    groups = [g for g in catalogue['groups'] if g['group_key'] == 'big_6']
                    if not groups:
                        raise QueryIssue('Big 6 is not defined for this competition.')
                    group = max(groups, key=lambda g: g['version'])
                    ids = sorted(set(group['team_ids']) - {team})
                    if set(ids) - set(names):
                        raise QueryIssue('The group contains clubs missing from this snapshot.')
                    filters['opponents'] = {'team_ids': ids, 'group_key': group['group_key'], 'group_version': group['version']}
                    recognized['group'] = f"{group['label']} v{group['version']} (queried team excluded)"
                else:
                    ids = [entity(target.children[0])]
                    if ids == [team]:
                        raise QueryIssue('A team cannot be its own opponent.')
                    filters['opponents'] = {'team_ids': ids}
                recognized['opponents'] = [names[i] for i in ids]
            elif kind == 'competition':
                recognized['competition'] = catalogue['competition_name']
            else:
                seasons, period_definition = resolve_period(kind, [str(c) for c in clause.children], catalogue)
                timeframe = {'mode': 'seasons', 'seasons': seasons}
                recognized['seasons'] = seasons
        if timeframe is None:
            raise QueryIssue('Choose a time period, for example last 5 seasons or 2017/18.')
        query = SportsQuery(dataset_id=catalogue['dataset_id'], competition_id=request.competition_id,
            entity_id=team, metric=metric, filters=filters, timeframe=timeframe, minimum_sample=request.minimum_sample)
        query.specification()
        return {'ok': True, 'parser_version': PARSER_VERSION, 'normalized': text, 'recognized': recognized,
                'query': query.model_dump(mode='json'), 'issues': [], 'suggestions': [],
                'definitions': {'metric': DEFINITIONS[metric], 'period': period_definition},
                'snapshot_date': catalogue['snapshot_date'], 'competition': catalogue['competition_name']}
    except UnexpectedInput as error:
        # Prefix recognition is diagnostic only. No partial parse can be executed.
        prefix = next((a for a in sorted(aliases, key=len, reverse=True) if text.startswith(a + ' ')), None)
        if prefix:
            recognized['team_candidates'] = [names[i] for i in sorted(aliases[prefix])]
        metric_match = next((m for m in sorted(METRICS, key=len, reverse=True) if re.search(r'\b' + re.escape(m) + r'\b', text)), None)
        suggestions = []
        if metric_match:
            recognized['metric'] = METRICS[metric_match]
            candidate = text.split(metric_match, 1)[0].strip()
            if candidate not in aliases:
                seen_ids = set()
                for alias, score, _ in process.extract(candidate, sorted(aliases), scorer=fuzz.ratio, limit=8, score_cutoff=65):
                    for ident in sorted(aliases[alias]):
                        if ident not in seen_ids:
                            seen_ids.add(ident)
                            suggestions.append({'name': names[ident], 'team_id': ident, 'similarity': round(score, 1),
                                                'query_text': names[ident] + ' ' + text[len(candidate):].strip()})
        position = max(0, getattr(error, 'pos_in_stream', 0) or 0)
        issue = 'Unrecognized or incomplete expression: ' + (text[position:] or '(end of query)')
        return {'ok': False, 'parser_version': PARSER_VERSION, 'normalized': text, 'recognized': recognized,
                'issues': [issue], 'suggestions': suggestions[:3], 'query': None}
    except QueryIssue as error:
        return {'ok': False, 'parser_version': PARSER_VERSION, 'normalized': text, 'recognized': recognized,
                'issues': [str(error)], 'suggestions': error.suggestions, 'query': None}
