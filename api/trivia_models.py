from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SeasonSelection(StrictModel):
    mode: Literal['seasons']
    seasons: list[Annotated[int, Field(ge=1800, le=2200)]] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.seasons)) != len(self.seasons):
            raise ValueError('Select each season once')
        return self


class SeasonRange(StrictModel):
    mode: Literal['season_range']
    start: int = Field(ge=1800, le=2200)
    end: int = Field(ge=1800, le=2200)

    @model_validator(mode='after')
    def ordered(self):
        if self.end < self.start or self.end - self.start > 99:
            raise ValueError('Invalid season range')
        return self


class DateRange(StrictModel):
    mode: Literal['dates']
    start: date
    end: date

    @model_validator(mode='after')
    def ordered(self):
        if self.end < self.start or self.start.year < 1800 or self.end.year > 2200:
            raise ValueError('End date must follow start date')
        return self


class AllSeasons(StrictModel):
    mode: Literal['all']


class ScoreCondition(StrictModel):
    minute: int = Field(ge=1, le=90)
    extra: int = Field(default=0, ge=0, le=30)
    operator: Literal['eq', 'lte', 'gte'] = 'eq'
    goal_difference: int = Field(ge=-20, le=20)
    clock: Literal['after_recorded_minute'] = 'after_recorded_minute'

    @model_validator(mode='after')
    def stoppage(self):
        if self.extra and self.minute not in (45, 90):
            raise ValueError('Stoppage time is only supported at 45 or 90 minutes')
        return self


class GoalFilter(StrictModel):
    after_minute: int | None = Field(default=None, ge=0, le=90)
    extra: int = Field(default=0, ge=0, le=30)
    role: Literal['all', 'substitute'] = 'all'
    count: Literal['goals', 'scoring_matches'] = 'goals'

    @model_validator(mode='after')
    def stoppage(self):
        if self.extra and self.after_minute not in (45, 90):
            raise ValueError('Added time requires a threshold at minute 45 or 90')
        return self


class OpponentFilter(StrictModel):
    team_ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=100)
    group_key: Literal['big_6'] | None = None
    group_version: int | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def valid_members(self):
        if len(set(self.team_ids)) != len(self.team_ids):
            raise ValueError('Select each opponent once')
        if (self.group_key is None) != (self.group_version is None):
            raise ValueError('Group key and version must be provided together')
        return self


class WeatherFilter(StrictModel):
    metric: Literal['temperature_c', 'precipitation_mm']
    operator: Literal['gte', 'lte', 'gt', 'lt']
    value: float = Field(allow_inf_nan=False, ge=-100, le=1000)

    @model_validator(mode='after')
    def bounds(self):
        if self.metric == 'precipitation_mm' and self.value < 0:
            raise ValueError('Precipitation cannot be negative')
        if self.metric == 'temperature_c' and self.value > 60:
            raise ValueError('Temperature threshold must not exceed 60 C')
        return self


class TriviaSpec(StrictModel):
    template: Literal['conditional_win_rate', 'win_rate', 'total_wins', 'total_goals',
                      'player_goals', 'top_scorer', 'comeback_wins', 'most_comeback_wins',
                      'loss_rate', 'draw_rate', 'goals_per_game', 'points_per_game', 'goals_conceded', 'clean_sheets', 'kit_colour']
    league_id: int = Field(gt=0)
    team_id: int | None = Field(default=None, gt=0)
    player_id: int | None = Field(default=None, gt=0)
    goal_filter: GoalFilter | None = None
    period: Annotated[SeasonSelection | SeasonRange | DateRange | AllSeasons, Field(discriminator='mode')]
    venue: Literal['all', 'home', 'away'] = 'all'
    condition: ScoreCondition | None = None
    minimum_sample: int = Field(default=10, ge=1, le=1000)
    opponents: OpponentFilter | None = None
    query_version: Literal['team-query-v1'] | None = None
    name_policy: Literal['exact-v1', 'unique-surname-v1'] = 'exact-v1'
    context_id: UUID | None = None
    kit_type: Literal['home', 'away', 'third'] | None = None
    weather: WeatherFilter | None = None

    @model_validator(mode='after')
    def compatible(self):
        if self.template == 'kit_colour':
            if self.kit_type is None or self.period.mode != 'seasons' or len(self.period.seasons) != 1:
                raise ValueError('Kit colour requires a kit type and exactly one explicit season')
            if self.venue != 'all' or self.opponents or self.weather or self.minimum_sample != 1:
                raise ValueError('Kit colour uses one kit record, not match filters; minimum sample must be 1')
        elif self.kit_type is not None:
            raise ValueError('Kit type is only supported for kit colour questions')
        if self.weather and self.template not in ('win_rate','loss_rate','draw_rate','total_wins','total_goals',
                'goals_conceded','goals_per_game','points_per_game','clean_sheets','conditional_win_rate'):
            raise ValueError('Weather filters support team result metrics only')
        if (self.template == 'kit_colour' or self.weather is not None) != (self.context_id is not None):
            raise ValueError('Kit and weather questions require an explicit context snapshot; other questions do not')
        if (self.template == 'conditional_win_rate') != (self.condition is not None):
            raise ValueError('Only conditional win rate requires a score condition')
        if self.template not in ('player_goals', 'top_scorer', 'most_comeback_wins') and self.team_id is None:
            raise ValueError('This question requires a team')
        if (self.template == 'player_goals') != (self.player_id is not None):
            raise ValueError('Only player goal questions require a player')
        if self.template not in ('player_goals', 'top_scorer') and self.goal_filter is not None:
            raise ValueError('Goal filters are only available for scorer questions')
        if self.template == 'most_comeback_wins' and self.team_id is not None:
            raise ValueError('Team ranking must include all teams')
        if self.name_policy != 'exact-v1' and self.template != 'top_scorer':
            raise ValueError('Surname matching is available only for scorer rankings')
        if self.opponents:
            if self.template in ('player_goals', 'top_scorer', 'comeback_wins', 'most_comeback_wins'):
                raise ValueError('Opponent filters currently support result metrics and conditional win rate only')
            if self.team_id in self.opponents.team_ids:
                raise ValueError('A team cannot be its own opponent')
        return self


class EvaluationRequest(StrictModel):
    specification: TriviaSpec
    dataset_id: UUID | None = None


class SaveQuestion(EvaluationRequest):
    question_id: UUID | None = None


class GradeAnswer(StrictModel):
    value: float | None = Field(default=None, allow_inf_nan=False, ge=-1e12, le=1e12)
    text: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode='after')
    def one_answer(self):
        if (self.value is None) == (self.text is None) or (self.text is not None and not self.text.strip()):
            raise ValueError('Provide either a numeric answer or a nonempty name')
        return self
