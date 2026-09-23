# POINTS Trivia

A separately runnable, trivia-only application in the existing repository. The
football frontend remains at port 8001; this application runs on port 8002 and
does not mount football pages. It deliberately shares the existing PostgreSQL
database and trivia engine, not a copied dataset or a second implementation.
The `trivia_*` tables own content, evidence and attempts. This is an application
boundary, not a physically separate database or an independently installable repo.

## Run locally

From the repository root:

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/trivia_migrate.py
.venv/bin/python -m uvicorn trivia_app.main:app --host 127.0.0.1 --port 8002
```

Existing `DB_*` and `TRIVIA_EDITOR_*` settings are read from the ignored root
`.env`. Editor passwords must contain at least 16 characters. No default password
is embedded in code. `/login` authenticates the private `/internal/trivia` editor.
The original application can still use HTTP Basic authentication.

Starlette signed, HttpOnly, SameSite=Strict session cookies last eight hours.
Without `TRIVIA_SESSION_SECRET`, a random signing key is generated on startup,
so a restart signs editors out. A random, persistent secret can be configured
for stable sessions. Changing the editor credentials invalidates existing logins.
Editor login failures have a process-local five-per-five-minute limit. This
single-editor login is separate from the new database-backed player accounts.

## Current workflow

Public visitors enter **Penalties** at `/` or `/penalties`. Account-based solo
quizzes are available at `/solo`, registration and profiles at `/account`, and
public player profiles at `/u/{username}`. Authoring pages and their APIs
still require editor authentication. See [GAME_ARCHITECTURE.md](GAME_ARCHITECTURE.md)
for XP, streak, difficulty review and the deliberately deferred ranked PvP work. Quiz previews
remain at `/quizzes` for signed-in editors. This restriction applies to the
standalone trivia service on port 8002; it does not deploy or expose either local
service on the internet, or change the separate analytics application on 8001.

Solo offers one free browser-bound trial before registration. New player accounts
require email, public username and a password of at least eight characters.
Email verification and Google/Apple OAuth are not connected yet; there are no
pretend provider buttons or verification emails. Old username-only accounts can
add their email after signing in. New solo XP rates are 10/20/30 for
Easy/Medium/Hard; a perfect quiz retains the x1/x2/x3 multipliers (100/400/900 XP).
Old quiz rewards keep their original frozen rules.

Solo records assigned question IDs by UTC day and excludes repeats for that
account until Monday 00:00 UTC. All ten IDs are reserved when a quiz starts;
abandoning it does not release them. Question order and answer options are
shuffled independently, then frozen for reloads. The selection screen reports
unused approved questions and the next reset; fewer than ten blocks that selection.
The owner-authorized solo pool now includes all 1,950 bank questions: 38 Easy,
404 Medium and 1,508 Hard. Difficulty is a provisional rule-based estimate;
1,736 answers are database-matched and 214 retain owner-attested authority.
New imports still require explicit approval; manual reviews are available at
`/internal/trivia/difficulty` (uncheck pending-only to review active questions).
See `GAME_ARCHITECTURE.md` for the audited, idempotent bulk-release command.
Solo selection separates **Category**, **Team / scope** and **Difficulty**.
The nine subject categories are strictly filtered, with remaining counts per
difficulty. Mixed topics balances the available subjects instead of favoring
the largest pool. Fewer than ten matching questions blocks that combination;
the game never substitutes another subject or difficulty.
Migration 040 backfills existing decks without modifying progress or answers.

Penalty packs include General (250 questions), 34 club packs (50 each), and a mix
of all 1,950 source questions. See [PENALTIES.md](PENALTIES.md) for release rules.

The imported research library and locally trained authoring assistant are available
at `/internal/trivia/bank`. See [QUESTION_BANK.md](QUESTION_BANK.md) for audit states,
training scope, import commands and the draft workflow. Imported reference answers
remain separate from verified published game questions.

A separate [local generative model pilot](LOCAL_GENERATOR.md) now generates
question/query proposals with MLX and supports LoRA training and independent DB
checks. It is an offline CLI workflow, not yet a Studio control or public feature.

1. Select a metric, competition, team/player and an explicit period in Studio.
2. Calculate. Inspect the answer, its unit, rankings and per-match evidence.
3. Click a ranking row's Evidence action to see that candidate's contributions.
4. Inspect Source and verification, and the Data quality tab for season coverage.
5. Save a draft; publish only when the quality checks pass. Publication recomputes
   the answer and checks the frozen evidence fingerprint.
6. In Quizzes, select verified published questions, order them, save and publish.
7. Preview quizzes at `/quizzes` while signed in. Attempts survive reloads in the
   same browser for 14 days. `/trivia` remains editor-only unscored practice.

There is no automatic seeding or publication on startup, and no implicit question
period. An opt-in review-pack publisher is available; see SPORTS_QUERY.md.
Old drafts predating the new quality policy must be recalculated into new revisions.

## Correctness and persistence

- Answers come from allowlisted typed computations, never client-supplied answers,
  arbitrary SQL, a language model, or scraped text.
- Provider fixture results, goal timelines, scorer identities and substitute roles
  are checked independently where possible. These are internal consistency checks
  on API-Football, not confirmation by an independent provider.
- Competition rules verify the full fixture catalogue: club count, fixture count,
  unique directed pairings and return fixtures. The current verified format is
  20-club Premier League, seasons 1995 through 2026. Other formats fail closed until
  an explicit rule is added. These rules do not select a user's question period.
- Whole-season questions cannot publish from unfinished seasons. Date-bounded
  questions can use completed matches from an ongoing season, provided its fixture
  catalogue and every selected match pass the relevant checks.
- Missing/ambiguous data produces a provisional answer and blocks publication;
  missing values are not quietly converted into zero. VAR cancellation ambiguity
  remains deliberately quarantined, even if a plausible total could be produced.
- Snapshots are sealed after building. PostgreSQL triggers reject changes to their
  facts and content revisions. Re-imports create new snapshots; never edit old ones.
- A revision freezes the specification, answer, unit, leaderboard, coverage,
  source hash, engine/policy version and all match evidence. Publishing records the
  editor identity and verification timestamp. Revisions do not overwrite history.
- Quizzes reference exact question revisions. Attempts reference exact quiz
  revisions, so subsequent editing does not change an in-progress game's answers.
- Attempts use hashed random capabilities in PostgreSQL and HttpOnly cookies.
  A UUID alone grants no access. The browser stores only its last attempt ID.
- The server locks the attempt while accepting answers, enforces order and grades
  against the frozen answer. Identical retries are idempotent; changing a submitted
  answer is rejected. Scores are derived from persisted answers, not client totals.
- Foreign keys tie each submitted answer to its attempt, quiz and ordered question.
  A unique key prevents double scoring. Completion requires all answers.
- The initial game response contains no answer or ranking. Each answer is revealed
  after submission; the final review shows the complete result. This is casual
  trivia, not an anti-cheating competition with prizes.

## Data operations

After correcting/importing provider records, run `src/trivia_build.py` to create a
new sealed snapshot. Do not relax publication checks simply to make a draft publish.
`src/trivia_migrate.py` serializes migrations with a PostgreSQL advisory lock and
records applied versions. Review SQL before applying it in another environment.

Use PostgreSQL `pg_dump --format=custom` for backups of the whole database, with
credentials supplied through libpq environment variables or a protected service
file. Use `pg_restore --list` to inspect an archive and periodically restore into a
separate disposable database. Never use `--clean` against the active database.
Production needs automated encrypted backups, off-machine retention and tested
restores; neither scheduling nor point-in-time recovery is configured here.

## Verify

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
TRIVIA_DB_TEST=1 .venv/bin/python -m unittest discover -s tests -p 'test_trivia*.py'
node --test tests/test_trivia_play.cjs
```

Database integration tests roll back every question, quiz and attempt. For browser
QA with a temporary two-question quiz, run `tests/trivia_preview.py --port 8003`.
That server holds one uncommitted transaction and rolls it back on shutdown; it is
only a single-user QA tool, never a deployment entry point.

## Deferred from the supplied MVP plan

Public accounts/auth providers, multiple choice and additional game formats,
user-generated content, moderation/reporting, daily challenges, XP/streaks,
leaderboards, product analytics, email, advertisements and production deployment
are not implemented. The current milestone is reliable data-backed authoring and
persisted quiz play. Continue with moderation and content curation before expanding
public creation. Keep the editor private until a proper roles/permissions model.

Before internet exposure: HTTPS with `TRIVIA_HTTPS_ONLY=1`, a persistent random
session secret, reverse-proxy rate limits for Basic Auth and public attempt creation,
least-privilege database roles (separate importer/editor/runtime), monitoring,
backup/restore drills, a dedicated test database, and a licensed data-display policy.
# Sports Query Extension

See [SPORTS_QUERY.md](SPORTS_QUERY.md) for the private text-query editor, exact time
and group semantics, API contracts, verification and the opt-in review-pack publisher.

See [QUERY_DATA_ARCHITECTURE.md](QUERY_DATA_ARCHITECTURE.md) for the follow-on
architecture: no external LLM dependency, an independently scheduled data worker,
resource-level freshness, human-verified training examples and explicit release
gates. Cloud imports and a deployed full-query ML parser remain planned capabilities.

The [Training workspace](TRAINING.md) now supports private human annotations and
a local CPU training command. It starts with unverified pilot drafts; models are
offline experiments and never automatically replace the deterministic parser.
