# Daily Challenge and Friend Duel

## Deployment

Apply `047_daily_friends` before deploying the application. It adds tables and
views without changing existing Solo rows. The existing migration command takes
a private Render URL, makes a backup, and commits the schema and marker together:

```sh
.venv/bin/python -m tools.migrate_account_settings --render --migration 047_daily_friends
```

Do not roll back by deleting game tables. The previous application can run with
this additive schema while retaining all new records for a later redeployment.

## Daily

- Registered accounts only; lazy, transaction-locked global daily pool.
- Exactly 50 distinct approved questions: 10 Easy, 20 Medium, 20 Hard.
- New pool at 00:00 UTC; previous pools in the same week are not reused.
- Existing five-kick Solo rules, including early clinch and paired sudden death.
- An undecided game exhausting its remaining nonempty deck wins. A decided loss
  cannot turn into a win; starting with no unused questions is refused.
- At most one win per account and UTC day, enforced by the database.
- Correct answers give 10/20/30 XP based on each frozen question, with no bonus.
- Completed runs with every question answered count for daily activity/streaks.
- Only actually opened questions enter weekly exclusion, including wrong,
  timed-out or abandoned questions. Unopened deck entries are not reserved.
- Old Solo allocation history and new opened history form `game_used_questions`.
- Daily wins have their own player/team leaderboard metric. They do not change
  Solo wins, losses or win rate. XP and activity are combined through views.

## Friend Duel

- Two registered accounts, opaque invitation token, no ranked matchmaking.
- No XP, bonus, rating, streak activity or Solo statistics. Database trigger
  rejects Friend Duel XP, not just the UI.
- Both participants explicitly join/ready, then share a server opening timestamp.
- Same question and answer order, 15 seconds, server-receipt elapsed times.
- One correct answer beats one incorrect/missing answer. Both wrong replay.
- Both correct: faster wins; difference below 150 ms replays. This is a network
  tolerance, not full latency compensation. Replay retains shooter and kick count.
- Five kicks each; clinch early; sudden death requires equal kick counts.
- Leaving forfeits. Two consecutive unanswered questions forfeit. Between kicks,
  disconnect over 30 seconds forfeits. Both absent, empty approved pool or 30-minute
  session limit abandon without a sporting winner. These are not ranked draws.
- GET polling restores state, resolves expired timers, and renews presence at
  most every four seconds. Unchanged decks are not rewritten on every poll.
- Poll immediately at the countdown deadline to reduce delivery skew. Answers
  and correctness stay private until both submit or the answer window closes.
- One active Solo/Daily/Friend game per account. Finish/leave the indicated mode
  before switching; revisiting an expired game releases its active membership.
- Question IDs enter the same weekly exclusion for both participants when opened.

## Integrity and Tests

Match/account locks serialize concurrent commands. Answer request UUIDs are
idempotent. Resolved history, question snapshots and completed results are frozen.
The UTC clock, difficulty, correctness, score and rewards are server-owned.

`tests/test_challenge_engine.py` covers pure rules and exhaustive first-five
score combinations. `tests/test_challenge_database.py` uses disposable schemas,
including concurrent answers/start, private results, no-repeat history, reset,
one-win/XP idempotency and forbidden Friend XP. No production test users are made.

For a real two-browser integration check, start `python -m tests.challenge_preview`
then run `node tests/test_challenge_browser.cjs` with Playwright on `NODE_PATH`.
The fixture listens only on 127.0.0.1:8015 and deletes its schema on shutdown.
