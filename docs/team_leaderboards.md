# Player and team leaderboards

`/leaderboard` switches between players and teams. Player metrics are XP, current
streak, wins and win rate. Teams also have Levels, the sum of members' levels.
The existing read-only `/api/community/leaderboard` endpoint accepts
`board=players|teams`, `metric=xp|streak|wins|win_rate|level` and
`period=today|week|all`. Legacy player-level API queries remain valid.

## Metric definitions

- Player XP and wins use the selected UTC period. All time includes the whole
  saved history. Guests and deleted accounts are excluded from both boards.
- A current streak is the consecutive daily activity ending today or yesterday.
  Future activity is ignored. An earlier gap ends the current sequence.
- Levels and current streaks always use all history; their period controls are
  disabled. Streak values are days, not the longest historical streak.
- Team XP, levels, wins and current streaks are summed over current members.
  Removing or moving a member changes totals immediately, including historical
  period totals. This is not an immutable record of XP earned while in that club.
- Team win rate is the arithmetic mean of member win percentages, not the ratio
  of total team wins to total matches. Members with no result in the selected
  period are excluded; no eligible members yields NULL (displayed as a dash).
  Abandonments and expired shootouts count as losses via `game_match_results`.
- All clubs remain visible in team rankings, including empty clubs. Empty clubs
  have zero sums and no win rate. Equal values share a rank; names stabilize pages.

Ranking, own position, member aggregates and XP distribution use one SQL
statement snapshot. No account IDs, emails or membership timestamps are exposed
by either leaderboard. Detailed account data remains owner-authenticated.

## Membership cooldown and rollout

Apply `046_team_membership` before deploying the new account UI/API:

```sh
.venv/bin/python -m tools.migrate_account_settings --migration 046_team_membership
.venv/bin/python -m tools.migrate_account_settings --render --migration 046_team_membership
```

The second command prompts privately for the Render External Database URL,
requires `MIGRATE`, and creates a private database backup before migrating.
The schema and migration marker commit together under the existing advisory
lock. A repeated invocation is safe. Existing code tolerates the additive column.

Joining, switching and leaving a club each begin a 72-hour wait. Existing
memberships start with no timestamp so their first change is allowed immediately.
Submitting the same club is a no-op and never resets the cooldown. Account-row
locking serializes requests; a database trigger also prevents bypass through a
direct update or by clearing the timestamp. Account deletion is exempt so erasure
is never blocked. The private profile exposes `team_change.next_change_at` for
display; the database remains authoritative.

## Verification

```sh
TRIVIA_DB_TEST=1 .venv/bin/python -m unittest tests.test_team_leaderboard_database tests.test_solo_database tests.test_account_settings
node --test tests/test_solo.cjs tests/test_community.cjs
node tests/test_team_leaderboard_browser.cjs
node tests/test_mobile_layout.cjs
```

The dedicated database tests refuse remote hosts and use disposable schemas.
Browser tests use a local preview on port 8013 with mocked APIs, including the
difficulty-only selection, hidden counts, team switching and all ranking tabs.
These are functional tests, not stress tests.
