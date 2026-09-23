# Solo Shootout

New games use frozen `solo-shootout-v5` rules. Existing games retain their
original rules and can still be opened from history.

## Rules

- Player shoots first, then defends. Correct means a goal when shooting and
  a save when defending. A timeout is an unsuccessful answer.
- Five kicks per side, with early victory once the other side cannot catch up.
- At level scores after five each, continue in pairs. A lead after only the
  first kick in a sudden-death pair does not decide the game. There is no draw.
- Each question has 15 seconds, starting only after the player presses Next.
  Camera travel does not consume that time.
- Correct answers earn 10/20/30 XP. Winning multiplies actual base XP by
  2/3/4 (easy/medium/hard), even with incorrect answers. Six correct hard
  answers win 3:0 and earn 720 XP. A loss/early exit earns only base XP.
  A completed game without timeouts earns daily streak credit.
- The server reserves ten distinct questions initially and two more per extra
  round. Category, difficulty and weekly exclusions stay enforced. A depleted
  pool or expired 30-minute session is abandoned, never recorded as a draw or
  fabricated victory. It counts as a loss. Earned answer XP remains; no win bonus
  or streak. Expired runs count as losses even before the player returns.

## Data Safety

Migration `043_solo_shootout.sql` permits append-only sudden-death allocation.
Earlier deck entries, frozen rules and completed results remain immutable.
Account/run locks serialize requests; answer/reward idempotency is unchanged.
New allocations use their actual UTC day, including across the weekly reset.

Migration `044_solo_community.sql` adds separate `win_bonus` ledger entries,
public win/loss statistics, and a club ID referencing the local PL catalogue
(20 clubs from the latest fixture season at migration time). The schema can
later aggregate results by club without depending on names or profile images.
Win rate is wins / (wins + losses), shown as a percentage; no games means null.
Legacy ten-question quizzes retain XP but do not invent sporting wins/losses.
PvP routes, socket registration, clock worker and public links are disabled.

## Visual Editing

- `trivia_app/static/stadium_config.js`: scene colours, geometry, camera,
  `roleChangeMs`, `runUpMs`, `outroMs`, and shot physics.
- `stadium_scene.js`: camera paths and background-only blur. Foreground players,
  goal and ball stay sharp. The outro restores detail, flies above midfield,
  then drives both canvas opacity and the result panel from the same progress.
  Keeper eyes follow the physical dive. Forearms and gloves are rendered into
  the free gameplay rectangle, with the held ball visible on a successful save.
  `keeperPOV`, `keeperHoldMs` and `backgroundBlur` are the visual tuning controls.
- `stadium_v6_world.js`: striker/keeper geometry and articulated kicking leg.
- `shootout.css`: TV score placement, goal/miss colours and result panel.
  A white football is a goal, red football a miss, hollow circle an unplayed kick.
- `solo.js`: waits for the final shot before the outro; the server owns outcomes.

## Verification

`tests/test_shootout.py` exhaustively checks the 1,024 initial binary answer
sequences against an independent reference and exercises extended sudden death.
`tests/test_shootout_database.py` checks atomic allocation and rewards in isolated
PostgreSQL schemas. `tests/test_solo.cjs` checks score icons, keeper outcomes,
animation ordering, result sharing and legacy behaviour.
