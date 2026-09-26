# ON THE DOT.

Standalone local copy of the trivia application, including Penalties, accounts,
leaderboards, the private editor, deterministic queries and local ML models.

## GitHub Copy

This repository contains application code, assets, tests and SQL migrations.
The local workspace also has data, trained models and database backups, but these
are deliberately excluded from Git. Existing published questions, player accounts
and game results live in PostgreSQL; cloning the repository does not restore them.

Use `.env.example` as the configuration reference and set real credentials only
locally or in the hosting provider's secret settings. Leave editor credentials
empty on the public game server. Training and local ML models are not required
to play published penalty questions.

The setup below describes the original Mac workspace. Cloud deployment still
requires a tested Linux dependency installation, a separate PostgreSQL database,
data migration, HTTPS/proxy configuration and backup verification. Do not commit
database exports or copy the local `.env` to GitHub.

## Start

### Local Editing

Double-click `dev.command` or run `./dev.command` from this folder.
Open http://127.0.0.1:8009/ and edit the files in this same project.
Save HTML/CSS/JavaScript changes and refresh the browser; Python changes restart
the server automatically. Stop with Ctrl+C in its terminal. For another free
port, use `PORT=8010 ./dev.command`.

This launcher explicitly uses `on_the_dot` on this Mac's PostgreSQL server,
not the Render database. It disables outgoing email and uses local share/duel
links. Local accounts and results stay local. The public site only changes
after a GitHub push and deployment. Never commit `.env` or database exports.

### Regular Local Server

Double-click `start.command` in Finder, or run `./start.command` in this folder.
Open http://127.0.0.1:8004/penalties. The editor is at
http://127.0.0.1:8004/internal/trivia; existing credentials are in the private `.env`.
Stop with Ctrl+C in the server terminal. Use `PORT=8005 ./start.command` if 8004
is already occupied. PostgreSQL must be running locally.

## Included

- `trivia_app/`: public game, private Studio, 3D stadium and documentation.
- `api/`, `src/`, `kits/`: shared data/query logic, import and training tools.
- `web/`: assets and templates still used by Studio and historical kit evidence.
- `database/`: complete migration history and underlying football schema.
- `data/`, `reports/`: question sources, model weights, trained adapters, datasets,
  kit evidence and verification reports. Frozen model manifests are unchanged.
- `tests/`: application and engine regression tests.
- `backups/`: complete PostgreSQL snapshot plus per-table counts for verification.
- `.venv/`, `.venv-llm/`: rebuilt local environments using the installed packages.

The only server entry point is `trivia_app.main:app`. Shared analytics modules are
retained as dependencies; analytics pages are not mounted by this application.
No symlink to PL-Analytics is needed. Old absolute paths inside historical training
reports are provenance, not runtime dependencies; pass paths under this directory
when starting new training jobs.

## Database

The current database is selected by `DB_NAME` in `.env`. `COPY_STATUS.md` records
whether this copy uses an independent database or the original shared database.
Do not run schema migrations against the original database unintentionally.

The backup includes football facts, questions, publications, accounts, XP and
training annotations. It also contains private account data: keep `backups/`,
`.env` and `data/private/` local, out of Git and out of public uploads.

To restore the included snapshot into another NEW database, from this directory:

```sh
.venv/bin/python tools/database_snapshot.py restore --env .env \
  --archive backups/trivia-postgres.dump --name on_the_dot_restored
```

This refuses existing database names and verifies every table count before
switching `.env`. It never drops or overwrites an existing database.

## Verification

```sh
node --test tests/*.cjs
.venv/bin/python -m unittest tests.test_stadium_assets tests.test_solo_engine
.venv/bin/python -m pip check
.venv-llm/bin/python -m pip check
```

The environments use Python installed on this Mac (3.14 for web, 3.12 for MLX).
For a different computer, create fresh virtual environments and install
`requirements-local.txt` / `requirements-llm.lock.txt`. PostgreSQL and Node are system
dependencies, not copied application files. MLX requires Apple Silicon.

`trivia_app/` documentation preserves the history of the original project;
older port 8002 examples now use port 8004 in this copy.
