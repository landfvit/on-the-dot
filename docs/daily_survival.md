# Daily survival (v2)

## Rules

- Registered accounts only. Shoot every penalty; never switch to goalkeeper.
- Correct answer = goal; wrong answer or 15-second timeout = one life lost.
- Three lives. End on the third mistake, running out of unused questions,
  leaving, or 00:00 UTC. No opponent score, shootout clinch, win or multiplier.
- The first start each UTC day reserves the sole ranked attempt, including
  zero-answer exits. Retrying the same start request returns that same run.
- Later starts use random unused questions in practice mode. Practice can earn
  existing 10/20/30 XP, but cannot write a ranked score.
- The global daily snapshot contains up to 1,000 approved questions. Practice
  samples from the full approved bank, not just that daily snapshot. All modes
  still exclude each account's previously opened/reserved questions for the week.
- Pool exhaustion records actual goals only; no invented completion reward.
- The leaderboard uses MAX(goals) across ranked runs for all time. Team scores
  sum current members' personal bests. Equal scores share ranks.

## Persistence and rollout

Migration `049_daily_survival.sql` is required BEFORE the new application code.
It adds first-attempt reservations and append-only scores, with database guards
that validate owner, mode, frozen rules and the correct-answer history. A score
cannot be written for a practice run or changed after recording. Existing Solo,
Friend and legacy Daily results remain unchanged.

Existing daily pools can be extended once from v1 to v2, retaining the complete
original prefix. After that they are frozen. Already-open v1 Daily runs finish
under their original rules. This is intentionally not a rewrite of old scores.

Local:
`./.venv/bin/python -m tools.migrate_account_settings --migration 049_daily_survival`

Render (prompts privately for its external database URL and creates a backup):
`./.venv/bin/python -m tools.migrate_account_settings --migration 049_daily_survival --render`

Apply to Render before pushing/deploying the application. No remote migration
or deployment is part of the local implementation task.

## Visuals and audio

- Goal frame and net use `V6_WORLD.colors.goal`, independent from stadium ink
  and theme. `V6_WORLD.structure.goalOutline` sets the thin black silhouette
  around the white frame (metres, default 0.008). Pitch paint remains white.
  Geometry blur is unchanged.
- `icons/football.svg` is an original vector icon, not the watermarked stock
  preview. The classic 3D ball uses the same black/white panels and bold seams.
  `football.png` is a 128px raster export of this SVG for Pillow share cards.
- Crowd reactions are short public-domain recordings served locally. There is
  no crowd synthesizer or ambient loop. See `static/sounds/LICENSE.md`.
- Goal while shooting / save while defending: cheer on this device. Opposite
  result: groan. Replay has no audience reaction. Mute and volume apply to all.
- The favicon symbol appears only in the page's active top-left header, never
  as a second How to Play illustration. Supplied homepage copy is preserved.

## Verification

- `python -m unittest tests.test_challenge_engine`
- `TRIVIA_DB_TEST=1 python -m unittest tests.test_challenge_database.ChallengeDatabaseTests`
- `node --test tests/test_audio.cjs tests/test_solo.cjs tests/test_crowd_reaction.cjs`
- Run `python -m tests.challenge_preview`, then
  `node tests/test_daily_survival_browser.cjs` and `node tests/test_challenge_browser.cjs`.
  Browser writes go only to that disposable local schema. Stop the preview
  normally so its cleanup drops the test schema.
