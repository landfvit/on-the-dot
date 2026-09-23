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

Leave `TRIVIA_EDITOR_USERNAME` and `TRIVIA_EDITOR_PASSWORD` unset. Do not upload
the local `.env`. Do not install the optional Apple Silicon MLX environment.

Render's public HTTP port is reachable through its ingress, not directly from
the internet. The forwarded-header setting above lets the app see the original
HTTPS scheme, which its same-origin checks require. Do not reuse the wildcard
setting on a server directly reachable by untrusted clients.

`DATABASE_URL` takes precedence over all local `DB_*` settings. The source
import/training scripts are local-only and some still use `DB_*` directly.

## Before Sharing the Site

A successful deployment only means the Python web process is running. The
database still needs schema and published questions, and the server must be
tested for trial play, accounts, complete shootouts, XP and leaderboard updates.
Do not run migrations or restore a full local database automatically on startup.

- Prepare and validate a game-only data import without local accounts/sessions.
- Check that the imported database fits the Free storage limit with headroom.
- Verify registration/login and same-origin POST requests over HTTPS.
- Verify internal editor routes remain inaccessible.
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
