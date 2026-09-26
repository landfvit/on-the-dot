# Developer Dashboard

Private URL: `/internal/dashboard`. Uses the existing Studio credentials
(`TRIVIA_EDITOR_USERNAME`, `TRIVIA_EDITOR_PASSWORD`) and signed editor session.
Player accounts cannot grant themselves admin access. No public navigation link.

## Views

- Overview: 7/30/90 UTC calendar days, registrations, registered/guest activity,
  games started, recently active games, finished/abandoned games, daily chart,
  mode totals and approved question counts.
- Players: search username/email, registered/blocked/guest filters, XP/level,
  club, activity, recent games, account details and audit history.
- Games: Solo/Daily/Friend filters, lifecycle status, participants, rounds and XP.
  Friend rooms count once; participant totals count both people.
- Management: existing editor/bank/difficulty tools and immutable admin audit.

Activity is inferred from persisted game starts, question opens, submitted
answers and Friend connection timestamps. It is **not** live website traffic,
DAU based on page views, or an exact online-person count. Expired games are
classified without mutating them. Guest identities can be duplicated across
browsers. Finished/abandoned totals are for games started in the selected window.
All times are UTC. Overview refreshes every 30 seconds only in a visible tab;
it pauses while a player dialog is open. Failed refreshes mark previous data stale.

## Account Actions

Block, unblock and sign out all devices require a reason, exact username and
explicit confirmation. Requests are idempotent and audited in the same database
transaction. Blocking revokes sessions and reset tokens, prevents authentication
and authenticated gameplay, and leaves scores/XP/results unchanged. Unblocking
does not revive sessions. Guests cannot be moderated as registered accounts.
Blocking an account does not ban a person from anonymous play or from registering
another account. Existing public leaderboard/history entries are not removed.

The dashboard never exposes passwords, token hashes, invite secrets or question
decks/answers. Email addresses and audit reasons are private admin data. No
third-party analytics scripts, session recording or tracking cookies are added.

## Migration / Deployment

Apply `050_developer_dashboard` before using the dashboard. This adds one nullable
account column, an append-only audit table and two game-date indexes. Existing
accounts are not blocked automatically; no games are deleted.

Local (in the project directory, with local `.env`):

```sh
.venv/bin/python -m tools.migrate_account_settings --migration 050_developer_dashboard
```

Render, before deploying the new code:

```sh
.venv/bin/python -m tools.migrate_account_settings --render --migration 050_developer_dashboard
```

The Render helper prompts for the external database URL privately and creates a
private backup before applying the migration. Never commit credentials/backups.
Ensure editor credentials and `TRIVIA_SESSION_SECRET` are configured on Render;
the editor password must contain at least 16 characters. Use HTTPS in production.
Local and Render dashboards report on their own databases, not each other.

## Tests

`tests.test_developer_dashboard` includes authentication, CSRF, input bounds,
isolated PostgreSQL reporting, session revocation, blocked gameplay, unblocking,
concurrent retries, audit integrity, expired-run classification and privacy.
`tests.dashboard_preview` and `tests/test_developer_dashboard_browser.cjs` provide
an isolated browser fixture. They never moderate real player accounts.
