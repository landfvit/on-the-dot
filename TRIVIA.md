# Trivia Studio

The standalone trivia-only app is now available through `trivia_app.main:app`.
See `trivia_app/README.md` for migrations, the private login, coverage policy,
versioned quizzes and persisted attempts. Run `src/trivia_migrate.py` before
starting either app. The original `/trivia` route remains casual practice.

The public question-and-answer game is available at `/trivia`. The private editor
is at `/internal/trivia`. It uses the existing local FastAPI app and
PostgreSQL database. No original fixture, event, team or player rows are changed.

## Setup and Refresh

Apply `database/022_trivia.sql` and `database/024_trivia_player_events.sql` using the
project's database connection, then run:

```sh
.venv/bin/python src/trivia_build.py
```

This creates an immutable dataset in one repeatable-read transaction. The builder
keeps the previous dataset on failure and reuses an unchanged source fingerprint.
Rebuild after importing or correcting football data. Saved questions remain tied
to their original dataset and engine version. There is no automatic season filter.

## Supported Question Families

- Conditional win rate at a recorded score checkpoint.
- Overall win rate.
- Number of wins.
- Goals scored.
- Player goal totals, optionally restricted to a club, minute threshold and substitute role.
- Leading scorer under those same conditions, counting either goals or matches with a goal.
- Number of wins after being behind at any verified recorded score state.
- Team with the most such comeback wins.

The user must explicitly choose selected seasons, a season range, inclusive UTC
dates, or all available seasons. Missing requested seasons fail validation; they
are not silently dropped. All-season selection is frozen through the dataset ID.
The competition, team, home/away filter and minimum sample are configurable.

## Clock and Quality Contract

Goal checkpoints mean the score after all source events at a given minute label,
not a precise second. Keys are `elapsed_minute * 1000 + extra_minute`. Thus 45+7
precedes minute 46. Minute 45 with extra=0 excludes first-half stoppage time;
minute 90 with extra=0 excludes second-half stoppage time. Equal-minute goals are
grouped and intervals are half-open `[start_key, end_key)`.

Only completed regulation-time FT matches are eligible in this first version.
The source's own-goal event team receives the goal. Missed penalties do not count.
The goal totals must reconcile with the final and half-time scores. Missing feeds,
unknown goal types/teams, invalid timestamps, duplicate-like goals and unresolved
VAR cancellations are quarantined. A nonempty, imported event feed is required
even for 0-0; empty events are not proof of a scoreless timeline. Reconciliation
is a consistency check, not independent verification of every source timestamp.

Unknown results and non-finished fixtures are excluded from simple questions too.
Every excluded fixture and reason is returned. Partial coverage and insufficient
samples can be explored/saved as drafts, but cannot be published. No matching
sample yields null, not 0%. Percentage answers retain integer numerators and
denominators and use decimal half-up rounding to one decimal place.

## Storage and API

`trivia_datasets`, `trivia_match_data_quality`, `trivia_match_team_facts` and
`trivia_match_state_intervals` form the analytical snapshot. Template definitions
are in `trivia_templates`. The server uses a typed, allowlisted specification,
not arbitrary SQL or client-provided answers.

`POST /api/trivia/evaluate` returns the answer, coverage and evidence.
`POST /api/trivia/questions` recomputes and saves a draft plus all match evidence.
Providing a `question_id` creates a new revision without modifying old content.
`POST /api/trivia/questions/{version_id}/publish` enforces quality gates.
`POST /api/trivia/questions/{version_id}/grade` checks a numeric answer against
the published version. GET metadata/library/version endpoints support the editor.

`GET /api/trivia/play/questions` returns only the latest published version per
question, its wording and answer kind, never answers, evidence or draft data.
Pagination uses `limit` (1-100) and `offset`; `next_offset` is null on the last page.
The existing grading POST accepts published versions only and reveals the answer
after submission. The game is casual practice, not an anti-cheating competition.

The editor page and all authoring/answer-bearing GET endpoints require HTTP Basic
authentication. Set `TRIVIA_EDITOR_USERNAME` and `TRIVIA_EDITOR_PASSWORD` (at least
16 characters) in the local environment or ignored `.env`, then restart the app.
There is no default password: unconfigured/short credentials keep these routes
closed with 404. Cross-origin browser writes are rejected and trivia API responses
are not cached. Raw templates are not served through the legacy static mount.
Use HTTPS and reverse-proxy login rate limits before exposing the editor beyond
localhost. General site accounts/roles are not implemented by this change.
No production hosting or public deployment is configured.

No demo questions or default seasons are seeded. The public game remains empty
until an editor explicitly selects a period and publishes a verified question.

Player scoring questions are now implemented; red-card conditions, other player-stat questions,
streaks, multiple-choice distractors and AI wording remain future work.

## Player and Event Snapshots

The `events-v2` builder adds indexed `trivia_match_player_facts`,
`trivia_event_facts` and `trivia_player_data_quality` tables. Each player-match row
preserves the team at the time of the match, names/aliases and nullable match
statistics, not the player's current club. Event rows retain source order, player,
assist/incoming-substitute ID, team, event detail and minute key. No source tables
are overwritten. Queries use these immutable snapshots, not live source joins.
The source fingerprint includes player identities, statistics and lineup-derived
roles; changing them creates a new dataset. Old datasets/questions remain valid.
New question types cannot be evaluated against a pre-extension dataset.

`player_goals` requires `player_id`; `team_id` is optional for this template and
`top_scorer`. `comeback_wins` requires a team; `most_comeback_wins` ranks all teams.
The optional `goal_filter` accepts `after_minute`, `extra`, `role` (`all` or
`substitute`), and `count` (`goals` or `scoring_matches`). A threshold is strictly
after the recorded label: after 85 excludes 85, but includes 86 and 90+5. After
90+3 excludes 90+3. No threshold means the whole regulation match. An optional
home/away scope refers to the scoring/winning team's venue, not the opponent's.

For example, an editor can compose this specification without embedding seasons
in the template:

```js
const specification = {
    template: 'top_scorer',
    league_id: selectedCompetitionId,
    period: userSelectedPeriod,
    goal_filter: {after_minute: 85, extra: 0, role: 'substitute', count: 'goals'},
    minimum_sample: selectedMinimumSample,
};
```

Only normal goals and scored penalties credit a player. Own goals credit the
beneficiary in the score timeline, never the individual goalscorer ranking.
Substitute scoring requires an incoming-substitution event no later than the goal
and no conflicting starting-XI evidence. An unused bench place or zero-minute
statistics row is not sufficient. Same-minute substitution/goal ordering is only
consistent at minute precision; no second-level accuracy is claimed. Missing
scorer identities, conflicting teams or unknown roles block the relevant family.
Role uncertainty does not block ordinary goals when scorer identity is verified.

Leaderboards aggregate by stable player/team IDs. A transfer does not split one
player into two candidates. Multiple goals in one match count once with
`scoring_matches`. Evidence and coverage count unique fixtures, not two team rows
per match. The sample is the eligible match universe in the selected scope, not
the number of scoring appearances. No qualifying scorer/comeback yields no
ranking winner, not an arbitrary zero-valued winner. A fully verified numeric
player total can be zero. Partial results stay drafts and cannot be published.

Ranked questions use `answer.kind = entity`, retain every joint leader, and ask
players to name any one of them. `POST .../grade` accepts either `{text: name}` or
`{value: number}`, never both. Names are compared against frozen source aliases,
ignoring case, accents, spacing and punctuation. Ambiguous aliases shared with a
nonwinner are not accepted; there is no fuzzy matching or arbitrary surname-only
matching. The public question feed still exposes only wording, ID and answer kind.
Winning names and values are revealed only after submission.

The private editor supports these templates and controls. The public game remains
question/answer only, with a name input for entity questions. No question, period
selection, or publication is created by a dataset build.

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
TRIVIA_DB_TEST=1 .venv/bin/python -m unittest discover -s tests -p 'test_trivia_database.py'
```

The optional database tests use existing datasets but roll back all test questions,
publications and evidence. They do not add demo questions to the user's library.
