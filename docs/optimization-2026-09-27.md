# Game backend optimization

Date: 2026-09-27. Target: 50-100 simultaneous players.
Changes are a local working-tree patch on top of
`89206ea5535e9810dd48b722eba3d14bbde1a910`, not a deployed release.
The baseline is documented in [the original stress report](stress-test-2026-09-27.md).

## Implementation

- Solo and Daily skip state writes on unchanged polls and identical command
  retries. Persist only newly resolved answers/XP; timeouts still commit even
  when a late answer returns HTTP 409. Rewards remain in the state transaction.
- Daily polling/actions load only answered questions, the current question and
  one lookahead from PostgreSQL. `QuestionWindow` retains the real deck length,
  so neither exhaustion nor next-question rules change. The complete frozen
  deck stays in the database. It is not cached in worker memory or sent to players.
- Changed Daily/Friend progress is sent separately from an unchanged deck.
  Friend decks can still grow for sudden death; extensions use the full guarded
  write. No questions or approved snapshots are removed to reduce memory use.
- Existing daily pools use a lock-free read fast path. Creation and legacy
  upgrades still use the database advisory lock and recheck after acquiring it.
- Migration `052_game_performance` keeps compact, generated Solo result fields
  and a covering index. `game_match_results` preserves its public contract,
  including expired unpolled games counting as losses. Rankings no longer
  calculate winners from every historical JSON document on every request.
- The same migration speeds up the frozen-state trigger: compare unchanged
  arrays once; inspect their prefixes only when appending. SQL guards still
  reject editing questions, resolved history or terminal results.
- Web workers use the official `psycopg-pool==3.3.3`, opened/closed by FastAPI's
  lifespan. Defaults: 2-10 connections per worker, 5-second acquisition/connect
  timeouts, at most 100 queued acquisitions. Broken idle sessions are checked
  before use. Saturation returns a generic 503 with Retry-After, never credentials.
- CLI tools and migrations retain direct connections. They do not reuse
  session-scoped search paths or advisory locks through the web pool.

No UI, user-written copy, difficulty, scoring, moderation, weekly history,
registration, login or rate-limit policy changes are included. Shared-IP limits
remain a known limitation pending an explicit decision.

## Verification

147 unit/integration tests pass, including real PostgreSQL pool tests, all
three game modes, legacy quizzes, concurrent answer retries, timeout commits,
snapshot guards, daily high scores, moderation, accounts and team rankings.
The only outdated assertion found expected the already-removed menu drawer;
the test now checks the existing top navigation without changing the UI.

New checks include:

- Unchanged polls/retried answers preserve the row's `xmin` and frozen deck.
- Partial and full Daily decks produce identical transitions and public views.
- Reading an existing pool works even while another session holds its creation lock.
- Pool reuse rolls back failed requests, respects its connection ceiling and
  replaces an idle connection killed by the database.
- Generated match results agree with the old view and cannot be manually forged.

## Daily Load Results

Same local harness and workload as the baseline: one web worker, 1,000 fake
accounts and 10,000 historical matches, 60 seconds per stage, real HTTP/SQL.
No database tests ran concurrently with the timed load stages.

| Daily players | Baseline P95 | Optimized P95 | Baseline errors | Optimized errors | Missed ticks before / after |
| --- | ---: | ---: | ---: | ---: | ---: |
| 50 | 1,728 ms | 387 ms | 0 | 0 | 144 / 0 |
| 100 | 5,146 ms | 1,748 ms | 43 / 3,300 | 0 / 4,687 | 1,533 / 231 |

At 100 Daily players, answer P95 dropped from 6,946 ms to 704 ms; new-game P95
from 8,932 ms to 3,328 ms. Median polling was 16 ms. Synchronized game starts
and immediate replays still cause queuing, so this is not a claim of universally
sub-second responses at 100 players.

Peak app RSS at Daily 100: 596 MiB before, 345 MiB after. Total sampled database
connections peaked at 11 after optimization (the web pool itself is capped at
10; the sampler also counts non-web database sessions). Peak sampled lock
waiters fell from 39 to 3. No failed workload requests were observed.

Integrity probes still produced exactly six saved answers and 120 XP for a
six-correct Easy win with a concurrent duplicate answer. Idle Solo polls no
longer rewrote state. The shared-IP probe still returned 20 successful starts
and five 429s, because its rate policy was intentionally not changed.

## Mixed Load Results

Same 90-second stages and approximate 60% Solo / 20% Daily / 20% Friend mix
as the baseline, plus one ranking browser. No other database tests ran during
these timed stages.

| Players | Requests | Baseline P95 | Optimized P95 | Optimized P99 | Errors | Missed ticks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 824 | 124 ms | 65 ms | 137 ms | 0 | 0 |
| 25 | 1,969 | 110 ms | 52 ms | 74 ms | 0 | 0 |
| 50 | 3,945 | 221 ms | 54 ms | 111 ms | 0 | 0 |
| 100 | 7,865 | 1,253 ms | 90 ms | 391 ms | 0 | 0 |

At mixed 100, Solo answer P95 fell from 988 ms to 45 ms, Daily answers from
1,856 ms to 115 ms, and XP ranking requests from 6,984 ms to 119 ms. The ranking
sample is small (eight requests at this stage), not a standalone ranking-capacity
test. Peak application RSS was 273 MiB versus the baseline's 325 MiB.

The final mixed and Daily suites together handled 21,813 measured workload
requests with no failures; no Uvicorn errors were recorded. All test servers
stopped and a final PostgreSQL check confirmed zero `otd_stress_*` databases.
The user's development server on port 8009 was left running.

Raw reports, ignored by Git, are under `reports/stress/`:

- `2026-09-27-optimized-daily.json`: intermediate run before question windows.
- `2026-09-27-optimized-window-daily.json`: final Daily implementation.
- `2026-09-27-optimized-mixed.json`: final mixed workload.

These are short tests on a local Mac with client/server/database sharing one
machine, not Render capacity certification, a soak test or a login/password
hashing benchmark. Random answer/deck choices vary between runs. Keep the paid
pilot recommendation from the baseline report and validate the chosen Render
web/DB instances under equivalent staging load before promising capacity.

## Animation Follow-Up

After these load measurements, inter-penalty movement was sped up to 1.3x.
The result pause is now 400 ms of real time in both views, with no additional
keeper-only hold. Friend Duel prepares the next camera view immediately after
the animation instead of waiting for the next server round. Replays keep the
same shooter. Answer windows, scoring, intro and outro remain unchanged.
New duels have shorter server presentation waits; existing frozen rules stay
valid. These presentation changes need no additional SQL migration. The load
results above precede these timing changes and have not been remeasured.

## Deployment

Local database migration 052 has been applied. Production is unchanged.
The migration is additive and compatible with the old application. Its table
rewrite/index creation takes a lock; use a quiet window and let the 5-second
lock timeout fail safely if needed. The migration tool backs up remote data
and commits the migration marker atomically with the SQL.

1. From the project directory, apply the reviewed migration to Render using
   `.venv/bin/python -m tools.migrate_account_settings --render --migration 052_game_performance`.
   Enter the external database URL only in its hidden prompt, never in Git or chat.
2. Confirm `Applied` or `already applied`, then deploy the tested code and
   requirements together. There is no schema auto-migration at web startup.
3. Start with one web worker, `DB_POOL_MIN=2`, `DB_POOL_MAX=10` (both default).
   Budget connections across all workers, rolling-deploy overlap and admin jobs.
   Pooling is not additional compute capacity and does not replace DB backups.
4. Smoke-test sign-in, each game mode, results, rankings and account moderation.

Official pool behavior: [Psycopg connection pools](https://www.psycopg.org/psycopg3/docs/advanced/pool.html).
