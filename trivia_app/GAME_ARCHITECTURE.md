# Player progression: first implementation

## Boundaries

- `/penalties` retains the original unranked guest mode and rules. No historical
  match is rewritten and no penalty XP is inferred from guest scores.
- `/solo` offers one browser-bound trial, then account-authenticated ten-question quizzes.
- `/account` registers/signs in players and edits their public bio/colour.
- `/u/{username}` exposes only public profile fields and aggregate progress, without
  colliding with football-player routes in the separate analytics application.
- `/internal/trivia/difficulty` remains editor-only. Player login never grants
  editor access. The original `/quizzes`, query engine and authoring APIs stay private.
- All current deployment remains localhost; this does not publish a service.

## Accounts

New accounts require a unique, normalized email address and a public username.
Email addresses are syntactically validated and case-folded; provider-specific
dot/plus alias rewriting is not performed. Email is included only in authenticated
account responses, never public profiles. Sign-in accepts either email or username
with the account password. Both identifiers ignore case and surrounding spaces;
passwords remain case-sensitive and are never trimmed. Legacy accounts without email
can also add email in Profile, with current-password confirmation. Changing sign-in email
revokes previous sessions and rotates the current session.

Case-insensitive ASCII usernames (3-24 letters, digits or underscores) are unique
and cannot yet be renamed. Passwords (8-128 characters) use salted scrypt
N=32768, r=8, p=1, versioned hashes and constant-time digest comparison.
Thirty-day random sessions are stored as SHA-256 token hashes; HttpOnly,
SameSite=Strict cookies are Secure on HTTPS or with TRIVIA_HTTPS_ONLY=1.
Registration and authentication have PostgreSQL-backed IP rate limits.
Email ownership verification, password recovery, account deletion UI and OAuth are
not yet implemented. Email is a login identifier, not proof of verified ownership.
No confirmation message is sent or claimed. Google/Apple sign-in needs registered
provider clients, credentials and callback URLs; no nonfunctional social buttons
are displayed. A mail delivery service must be configured before verification and
recovery can be enabled. This remains a local MVP, not production-ready identity.
Before internet deployment: HTTPS, verified recovery, abuse monitoring, backup and
restore drills, deletion/privacy policy and a dedicated security review are needed.

## Solo rules v2

- Exactly ten distinct, approved questions at the selected category and difficulty.
- Server starts a 15-second deadline when a question is explicitly opened. A page
  reload, second browser tab or retry never resets that deadline.
- Correct answer: Easy 10 XP, Medium 20 XP, Hard 30 XP immediately, including in a
  later abandoned registered-player quiz.
- Wrong answer or timeout: zero XP. Timeout is not a submitted answer.
- Only 10/10 at completion earns the whole-quiz multiplier: easy x1, medium x2,
  hard x3, or 100/400/900 XP. Otherwise each correct answer retains its difficulty rate.
- Each run freezes its scalar XP rate and multiplier rules. Existing v1 runs still
  pay 10 XP per correct answer and 100/200/300 XP for a perfect result. Migration
  never recalculates or rewrites historical XP or an already-started quiz.
- Daily streak requires completion with all ten answers actually submitted.
  Correctness is irrelevant. Activity is unique per account and UTC completion day.
- Current streak survives until the end of the next UTC day; longest streak is
  retained. There are no streak freezes or timezone preferences in this version.
- One active quiz per account; a 30-minute expiry bounds unfinished attempts.
  Deadlines are resolved lazily on the next read/command, using the original
  persisted deadline, not the time of reconnect. No background client is required
  for correctness; unattended runs are reconciled when accessed again.
- Level thresholds are rows in game_levels. Initial configurable curve:
  minimum XP = 100 * level * (level - 1), levels 1-100. This is a tuning default,
  not a permanent product decision. Cosmetic unlocks are not yet implemented.

## One free quiz

Before registration, the server creates an opaque guest identity, not a public
profile. Its random session capability is hashed in PostgreSQL and stored in a
separate HttpOnly, SameSite=Strict trial cookie, valid for one year. A unique
database index permits exactly one trial run for that identity, even across tabs
and concurrent requests. Reloads resume the same quiz and retain its deadlines.
Starting the trial consumes the allowance; abandoning it does not grant another.
Unusable categories do not consume an attempt.

The same grading engine displays trial XP, clearly marked as not saved. No trial
XP ledger or daily activity is written, and database guards prohibit either.
Registration creates a separate real account; trial XP is not transferred.
Guest identities cannot authenticate as accounts or appear in public profiles.
One trial per browser is a best-effort onboarding limit, not person identification:
clearing cookies, another browser or a new device can create a new guest identity.
IP rate limits constrain abuse but cannot solve that limitation without login.
Existing unranked guest penalty games are unaffected.

## Persistence and concurrency

game_accounts and game_sessions own identity. game_solo_runs freezes ten question
snapshots, their answer choices, difficulty revision IDs and rules. Normalized,
immutable game_solo_answers retain first-hand timing and scoring evidence.
game_xp_ledger is append-only, keyed by quiz and question position; slot zero is
the perfect bonus. Database guards reject unsupported rewards and streak credit.
game_daily_activity records the qualifying quiz for each UTC day.

Commands lock account before run, in the same order across creation, answering
and completion. State, answer, XP and streak changes commit in one transaction.
Start requests and answer submissions have idempotency IDs. A rejected late
answer still commits the timeout. Public views never serialize a future question
or unrevealed correct answer. User-supplied XP/correctness fields are rejected.

## Weekly question history

Every new solo quiz atomically reserves all ten question IDs in
`game_question_history`, including unopened questions and abandoned attempts.
The history stores the account, UTC allocation day, Monday week-start, exact
release, run and position. A database trigger writes allocations with the run;
the unique (account, week, question) key prevents concurrent duplicates even
outside the API. Immutable history cannot be cleared to redraw questions.
`GET /api/solo/history` returns only the authenticated player's current-week
question IDs grouped by day, without answers or question contents.

Selection excludes those IDs across categories, difficulty changes and releases.
The personalized catalog counts only unused approved questions. Fewer than ten
means the quiz is unavailable: no repeats, smaller decks or difficulty fallback.
The UI refreshes availability when returning to selection and at the reset.
The initial 30-question sample has been expanded by an explicit owner-authorized
bank release (see Difficulty and rollout). Weekly capacity depends on the chosen
category and difficulty, not just the total library size.

Eligibility resets on Monday at 00:00 UTC by selecting a new weekly window;
there is no destructive cleanup or scheduler. Daily audit records, XP, levels
and streaks remain intact. A quiz crossing midnight or the weekly boundary
keeps its original deck and allocation week. Legacy decks are backfilled using
their creation date; legacy repeats retain the first allocation of each ID in
each week, while complete run snapshots remain untouched.

The server filters eligible IDs, samples across available topics, then SystemRandom
independently shuffles the ten questions and each question's answer options before
freezing the deck. Ten distinct questions permit 10! = 3,628,800 orders. Randomness does
not guarantee a globally unique order between accounts or weeks. Reloads and
idempotent retries preserve the order, correct answers and deadlines.
This is casual progression, not an anti-cheat or prize competition.

## Categories and selection

Category now means a subject, not a club. `api/solo_topics.py` explicitly maps all
46 source topics into nine disjoint categories: Players & transfers, Managers,
Stadiums, Kits & sponsors, Matches & scorelines, Head-to-head & mini-leagues,
Season records & tables, Win rates & percentages, and Cards & discipline.
Team / scope independently selects All clubs, General or a specific club.
Difficulty is the third independent filter. No question is made easier simply
to fill an empty category, and no content/answer authority is rewritten.

The catalog exposes a subject/team/difficulty availability matrix after weekly
exclusions. Each difficulty shows its actual remaining count. Starting a quiz
requires ten questions at the exact intersection; shortages never pull from
another topic, club or difficulty. Cards & discipline currently has only seven
questions, so cannot yet be started on its own. Unknown future source topics
are excluded until the explicit taxonomy is extended.

Mixed topics samples round-robin across the eligible broad categories instead
of weighting by inventory size. Within a selected category, its source subtopics
are sampled round-robin. Each bucket and each selection round is shuffled, as is
the final ten-question order. Scarce buckets may empty, so balance is best-effort
over available questions, not a promise of ten different subjects. Easy still
contains mostly managers/stadiums; additional easy content needs to be authored.

The API retains `category` as the legacy club/scope code and adds a strict `topic`
enum, defaulting to ALL for older clients. Topic code and label are frozen inside
the existing immutable run category object. No database migration is needed.
An active run in another subject cannot silently satisfy a new start request;
the player must finish/end it first. Older runs retain their original decks and
display as Mixed topics. Question-ID exclusions apply across mixed and topic play.

## Difficulty and rollout

Difficulty is independent of category and answer authority. The exact released
multiple-choice version is assessed, including its distractors. Assessments are
append-only; approving, changing or retiring one creates a new revision and
never changes a running quiz. The latest assessment controls new quiz eligibility.

Run `src/seed_solo_difficulty.py` explicitly after migrations. It is idempotent
and never overwrites existing editorial decisions. The first reviewed sample is
30 questions: 10 recognizable managers/stadiums, 10 Golden Boot questions and
10 Big Six mini-league questions. These are initial editorial estimates, not
measured difficulty. All clubs supports each difficulty; General initially has
Medium and Hard only. Individual club packs need more approved questions.
The seed still leaves the remaining questions unpublished. On 2026-09-21 the owner
explicitly requested enabling the rest of the existing bank for solo. Policy
`solo-bank-v1` adds 1,920 versioned approvals and retains the initial 30, yielding
1,950 questions: 38 Easy, 404 Medium and 1,508 Hard. This niche-statistics source is
not artificially balanced. Categories remain General and the original 34 clubs.
Some category/difficulty combinations still contain fewer than ten questions.

These are provisional rule-based estimates, not individual human reviews or
empirically calibrated difficulty. Direct manager, stadium and headline award
recognition is Easy; caretaker appointments, player/season totals, specific match
recall and suppliers are Medium; filtered aggregates, multi-season patterns and
kit-design details are Hard. Long wording and decimal-percentage alternatives
raise difficulty. Existing assessments always take precedence over the rules.

The release rechecks all four distinct alternatives, the single original answer,
accepted aliases, provenance, frozen authority and both the pinned and latest
database audit. Conflicts and genuinely ambiguous winners are blocked. The six
existing player-name alias warnings retain owner-attested status, not verified
identity. In total 1,736 answers are database-matched and 214 owner-attested.
Approval does not change answer authority, source records or existing run decks.
Penalty packs, XP, weekly reservations and completed answers are unchanged.

`src.release_solo_bank` defaults to a read-only dry run. Applying requires a pinned
release and explicit acceptance of owner-attested answers. Only untouched initial
suggestions are promoted; manual holds and classifications are preserved. The
operation locks assessment writes, adds immutable revisions and is idempotent.
Future imports are not automatically enabled. Review/tune approved questions in
the private difficulty screen with the pending-only filter unchecked.

```sh
.venv/bin/python -m src.release_solo_bank --report reports/trivia-bank/solo-bank-preview.json
.venv/bin/python -m src.release_solo_bank --release RELEASE_UUID --apply --confirm-user-attested --report reports/trivia-bank/solo-bank-release.json
```

The local `reports/trivia-bank/solo-bank-v1-release.json` records the action,
classification rationale and validation issues for each question.

## Calibration and later stages

Answer records carry account, exact question release, assessment revision, timing,
correctness and timeout evidence. A future calibration report must select only
the first encounter per player/question version and require at least 100 distinct
players. Starting bands are >=75% Easy, 45-74% Medium and <45% Hard. Around/below
25% for four choices flags ambiguity or flawed alternatives for review.
Adjusting for player skill, confidence intervals and category fan bias is not
implemented; raw rates must not auto-reclassify questions or be called calibrated.

Ranked matchmaking, online leaderboards, Elo/rating policy, PvP seasons and
disconnect sanctions are a later stage. XP and rating must remain separate.
Cosmetic inventories/unlocks and achievements are also intentionally deferred.

## Verification

`TRIVIA_DB_TEST=1 .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`
`node --test tests/*.cjs`

New integration tests create disposable schemas and read published questions
without modifying football facts or production quiz history. They cover reward
idempotency, concurrent submissions, strict deadlines, ownership, CSRF, immutable
history, profile privacy, streak eligibility and all three multipliers.
