# Sports Query v1

Private **Sports query** tab: http://127.0.0.1:8002/internal/trivia.
Public practice: http://127.0.0.1:8002/trivia. Quiz library: http://127.0.0.1:8002/.

## Supported Scope

Phase 1 of the deterministic-engine proposal is implemented: team result metrics,
competition context, home/away, one opponent or the versioned Big 6 group, and explicit periods.
The text interface uses controlled English, not arbitrary natural language or an LLM.
Existing player, scorer and match-state questions remain available in the structured editor.

The [query/data architecture addendum](QUERY_DATA_ARCHITECTURE.md) fixes the future
direction: no external LLM fallback, separate data updates and model training,
and explicit snapshot/correction boundaries. The private [annotation and local
metric-model workflow](TRAINING.md) is available as an offline experiment.
Daily sync and a deployed ML query parser are not implemented.

Examples:

```text
Manchester United win rate against the big 6 teams in the last 10 seasons
MUFC win percentage vs Arsenal since 2020
Arsenal points per game away 2024/25
Liverpool goals per game in Premier League between 2020 and 2024
Chelsea clean sheets last season
```

Metrics: win/loss/draw rate, total wins, goals scored/conceded, goals per game,
points per game and clean sheets. Formula definitions accompany every parsed query.
Percentages round half-up to one decimal, averages to two. Points are 3W+D,
before administrative deductions. Clean sheets include scoreless draws.

Players, assists, shots, possession, managers, comparisons and free-form prose are
not implemented in the text parser. It refuses unsupported text rather than
returning an answer to a reduced or guessed question.

## Architecture

- `api/sports_query.py`: Lark grammar, normalization, exact aliases, RapidFuzz
  suggestions, period resolution, strict versioned SportsQuery schema.
- `api/sports_query_routes.py`: authenticated catalogue, parse and execute endpoints.
- Existing `TriviaSpec` and `trivia.evaluate`: parameterized snapshot queries,
  sample/coverage audit, source hashes and match evidence, save/publish verification.
- `028_sports_query.sql`: alias registry, immutable versioned opponent groups,
  bounded-length failed-query log, new metric templates.

`POST /api/query/parse` accepts text, competition_id, optional dataset_id and
minimum_sample. Returns `ok`, recognized fields, issues, suggestions and a typed
query only on a complete successful parse. It never executes a statistic.
`POST /api/query/evaluate` accepts only SportsQuery, including an explicit snapshot
UUID and season list. Raw SQL, extra fields and unsupported operators are rejected.
`GET /api/query/catalogue?competition_id=39` supplies autocomplete and definitions.
All three endpoints require the existing editor authentication.

Query input is limited to 1000 characters. Unknown text and ambiguous names such
as United require clarification. Fuzzy scores are similarity scores, not calibrated
confidence probabilities, and never cause automatic execution.

## Period and Group Semantics

Seasons are never hardcoded in the query engine. `last N seasons` means N consecutive
seasons ending with the latest completed season present in the chosen snapshot.
Completion means all catalogued fixtures have FT status; publication additionally
requires the existing full fixture-catalogue and result checks. Invalid or missing
seasons are never skipped to obtain N seasons. The UI shows all resolved years and
the snapshot timestamp before execution.

This timestamp is the snapshot's creation time, not proof of a recent provider
check. Resource-level successful synchronization timestamps are not yet tracked
by this query interface. `last decade`, `top six`, `record against` and unsupported
negative conditions are deliberately not mapped to similar supported expressions.

`since YEAR` starts with that season's start year, not January 1. `between A and B`
includes both season start years. `all time` means all available snapshot seasons,
including unfinished seasons, not all football history. Missing periods are errors.
Specific seasons accept 2017/18 or 2017/2018 and require consecutive years.

Big 6 v1 is Arsenal, Chelsea, Liverpool, Manchester City, Manchester United and
Tottenham, with the queried team removed. Saved specs retain both explicit IDs
and group version. Execution validates membership against the immutable definition.
Alias edits cannot reinterpret saved questions, whose entity IDs and periods are fixed.

Question wording always names the actual seasons, venue and opponent scope.
New query revisions also freeze the W/D/L summary and calculation version in analysis.
Legacy answer/analysis structures remain unchanged; old published revisions are not edited.

Scorer rankings also have an explicit name-matching policy. New editor questions
accept an unambiguous surname derived from the provider's initialled display name
(R. Lukaku -> Lukaku; E. Smith Rowe -> Smith Rowe). Ownership is checked against
goal events and all player facts in selected fixtures, including non-scorers.
Ambiguous surnames are not accepted. Accepted aliases are frozen into each answer;
legacy revisions retain exact-source-name matching. The review pack upgrades its
scorer question and quiz through new revisions, never edits existing answers.

## Operations and Verification

```sh
.venv/bin/pip install -r requirements.txt
.venv/bin/python src/trivia_migrate.py
TRIVIA_DB_TEST=1 .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
node --test tests/test_trivia_play.cjs
.venv/bin/python src/trivia_examples.py
.venv/bin/python src/trivia_examples.py --publish
```

The example publisher is opt-in, transactional and idempotent for the same
snapshot/specifications. It publishes eight checked questions and one ordered
quiz. Example seasons are just editable sample content, never engine defaults.
It aborts publication if any example fails the normal quality gates. Tests use
rollback-only transactions and never leave published fixtures or quiz attempts.

Failed parse submissions are stored locally in `trivia_unrecognized_queries`, with
snapshot, parser version, recognized fields and issues. No IP, password, session,
keystroke stream or external analytics is recorded. Log access is database-admin
only; avoid entering personal information in queries. Retention is currently manual,
not an automated deletion policy.

No Redis or aggregate cache is introduced yet. The bounded compiled grammar cache
contains no answers. Any future result cache must key on snapshot, complete resolved
scope, metric/calculation version and quality policy, not just raw text.

Results are internally verified against the API-Football snapshot, not independently
verified with another provider. Bad coverage or a small sample remains visible and
blocks publication, even if a provisional numeric result exists.
