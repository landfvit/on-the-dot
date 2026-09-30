# Render Test Deployment

Use the existing Postgres database; do not create a second database or import
local accounts as part of deploying the web service. Keep this as a test until
the reviewed question import and end-to-end checks have completed.

## Web Service

- Repository: private `landfvit/on-the-dot`, branch `main`.
- Runtime: Python 3. The repository pins Python in `.python-version`.
- Region: the same as the existing database, preferably Frankfurt.
- Root directory: leave empty.
- Plan: Free for this initial test.
- Build: `pip install -r requirements.txt`
- Start: `uvicorn trivia_app.main:app --host 0.0.0.0 --port $PORT --proxy-headers`

Set these values in the web service's environment settings, never in Git:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Internal Database URL from the existing Render database |
| `PGSSLMODE` | `require` |
| `TRIVIA_HTTPS_ONLY` | `1` |
| `TRIVIA_SESSION_SECRET` | A new, strong, stable random secret, at least 32 random bytes |
| `FORWARDED_ALLOW_IPS` | `*`, only on Render behind its managed ingress |
| `WEB_CONCURRENCY` | `1` for this small initial instance |

For the private developer dashboard, set `TRIVIA_EDITOR_USERNAME` and a unique
`TRIVIA_EDITOR_PASSWORD` of at least 16 characters in Render, not Git. These
credentials also protect Studio; normal player accounts have no admin access.
Leave them unset when admin access is not needed. Never upload the local `.env`
or install the optional Apple Silicon MLX environment.

Render's public HTTP port is reachable through its ingress, not directly from
the internet. The forwarded-header setting above lets the app see the original
HTTPS scheme, which its same-origin checks require. Do not reuse the wildcard
setting on a server directly reachable by untrusted clients.

`DATABASE_URL` takes precedence over all local `DB_*` settings. The source
import/training scripts are local-only and some still use `DB_*` directly.

## Before Sharing the Site

### Initial Game Data Import

The local `tools.render_game_database` utility exports an explicit allowlist of
published questions, their audit records, difficulty revisions, levels and
clubs, plus the full schema. It does not export player accounts, sessions,
game history, trained models or football fact tables. The admin dashboard can
report on production games, but the editor cannot re-run historical football
analysis without those separate local datasets.

Create a bundle locally (choose a new directory for every export):

```sh
.venv/bin/python -m tools.render_game_database export --bundle backups/render-game-20260923
.venv/bin/python -m tools.verify_game_bundle --bundle backups/render-game-20260923
```

Verification creates and removes only a newly named temporary LOCAL database.
It checks row counts, an anonymous trial, registration, a won shootout and XP.
The bundle remains in ignored `backups/`, never GitHub or public web assets.

Restore the tested bundle from the Mac, not from the Render web process:

```sh
.venv/bin/python -m tools.render_game_database restore --bundle backups/render-game-20260923
```

Paste the Render **External Database URL** into the hidden terminal prompt.
Do not paste it into chat or put it in the shell command. Confirm the displayed
host/database and type `IMPORT`. The restore requires TLS, verifies the archive
checksum, refuses a nonempty database and restores in one transaction. It
preserves the existing empty `public` schema and never drops existing objects.
If it reports a nonempty target, stop and inspect rather than trying to clear it.
External network access must permit this Mac during import; restrict external
access again afterward while keeping the application's internal connection.

### Launch Checks

A successful deployment only means the Python web process is running. The
database still needs schema and published questions, and the server must be
tested for trial play, accounts, complete shootouts, XP and leaderboard updates.
Do not run migrations or restore a full local database automatically on startup.

- Prepare and validate a game-only data import without local accounts/sessions.
- Check that the imported database fits the Free storage limit with headroom.
- Verify registration/login and same-origin POST requests over HTTPS.
- Verify internal dashboard/editor routes and APIs reject unauthenticated users.
- Test exports and arrange an upgrade or migration before database expiry.
- Connect `onthedot.gg` only after the temporary Render URL works end to end.

Free Postgres has 1 GB storage, expires after 30 days and has no managed backups.
Free web services sleep after 15 idle minutes. This is not production readiness.

References:
- https://render.com/docs/deploy-fastapi
- https://render.com/docs/python-version
- https://render.com/docs/web-services
- https://render.com/docs/postgresql-creating-connecting
- https://render.com/docs/free

## September 26 Release

Before pushing the updated Daily Challenge and developer dashboard to `main`,
apply both additive migrations to the existing Render database, in order:

```sh
.venv/bin/python -m tools.migrate_account_settings --render --migration 049_daily_survival
.venv/bin/python -m tools.migrate_account_settings --render --migration 050_developer_dashboard
```

Each command privately prompts for the external URL and creates a backup before
the migration. An `already applied` response is safe. Never replace production
data with the local database. After deploying, check `/`, `/penalties`, `/daily`,
`/friends`, `/account`, `/leaderboard` and `/internal/dashboard`. An unauthenticated
dashboard visit must redirect to login; `/api/developer/overview` must reject it.

## September 30 Release

The compact pixelart game, profile kit picker and illustrated guide require
the additive kit migration before deploying the updated application:

```sh
.venv/bin/python -m tools.migrate_account_settings --render --migration 053_player_kits
```

The command prompts privately for the external database URL and creates a
backup first. Proceed only after `Applied 053_player_kits.` or an `already
applied` response. It adds kit selections and shirt numbers without replacing
accounts, games or team memberships. Older application code remains compatible.

After the deploy, verify the new guide images, an account's kit save and reload,
and a completed game with stable question controls. Check that the private
dashboard and editor still reject unauthenticated visitors.

## Password Recovery

Existing passwords cannot be viewed, including by an administrator. Recovery
sends a one-use link to the email already on the account. It expires after
30 minutes. Completing it changes the password and revokes all sign-in sessions;
XP, results, team and kit stay unchanged. Signup email verification is not added.

### Provider Setup

1. The owner verified `onthedot.gg` in [Resend](https://resend.com) on September
   30. Use this verified root domain for the current release, not the initially
   suggested `mail.onthedot.gg` subdomain.
2. In GoDaddy DNS, add the records exactly as Resend shows them. Do not replace
   the website's A/CNAME records or an existing root-domain mailbox MX record.
   Wait until Resend reports the domain verified.
3. Leave click tracking and open tracking disabled for recovery messages.
4. Create an API key with **Sending access**, restricted to `onthedot.gg`.
   Store it privately in Render, never in Git, chat, screenshots or shell history.

Set these environment values on the Render web service without changing other
existing settings:

| Variable | Value |
| --- | --- |
| `PUBLIC_SITE_URL` | `https://onthedot.gg` |
| `ACCOUNT_EMAIL_FROM` | `ON THE DOT. <accounts@onthedot.gg>` |
| `RESEND_API_KEY` | The private, domain-restricted sending key |

The sender must belong to the verified sending domain. Configuration presence
does not prove delivery; verify receipt with your own account before sending
recovery mail to other players. No live email is sent by automated tests.

### Release Order

Before deploying the updated admin code, apply the audit migration:

```sh
.venv/bin/python -m tools.migrate_account_settings --render --migration 054_account_recovery
```

This command prompts privately for the external database URL and backs up the
database before making changes. Proceed only after `Applied 054_account_recovery.`
or an `already applied` response. It adds a permitted audit event without
changing accounts, passwords or sessions. Existing code stays compatible.

If Render environment values were saved with **Save only**, the next deployment
activates them. Do not trigger that deployment until the migration is complete.
The admin button
stays disabled when email delivery is not configured. To test delivery, open
`/internal/dashboard`, choose Players and your own account, then **Send password
reset**. Enter the reason and exact username to confirm. Only the stored email
can receive the link; neither the token nor the link is shown in the dashboard.

Check the inbox, set a new password, sign in again and confirm that the same link
cannot be reused. The player-facing **Forgot password?** flow on `/account` uses
the same recovery mechanism. It intentionally does not reveal whether an email
exists or belongs to a blocked account. Requests for an account share a one-minute
cooldown across self-service and admin recovery. Blocked, deleted and guest
accounts cannot receive admin resets. A block or email change invalidates an
outstanding link.

Admin delivery failures are shown in the dialog. Check Resend's delivery status
and sender configuration before retrying; never paste provider responses or
reset links into public logs. A successful API request means the provider
accepted the email, not that it has reached the inbox.

References:
- [Domain verification and tracking](https://resend.com/docs/dashboard/domains/introduction)
- [Restricted sending keys](https://resend.com/docs/dashboard/api-keys/introduction)
