# Player Questions and Curated Bank

## Local entry points

- `/my-questions` is the registered player's library and editor.
- `/internal/trivia/community-questions` is the admin review queue.
- `/internal/trivia/bank` shows the latest imported non-community bank.

The editor takes a question, four distinct answers, one correct answer,
difficulty, topic and an optional reviewer note. No source link is requested.
Drafts can be used in a private duel immediately. Submission does not publish.
Approval needs an explicit fact and answer-choice check and a review note.
Rejection retains the note; the author must save a new revision to resubmit.
Approved revisions and review records are immutable.

## Custom duels

The host selects 1 to 100 owned questions. The invitation freezes their text,
choices and correct answer, independently of future edits. Questions and options
are shuffled. Answers stay server-side until the round is resolved.

Only custom questions are used by default. When they run out, the score decides
the winner or the game ends in a draw. The optional bank checkbox continues with
unused ON THE DOT questions at the selected difficulty. Both players see this
setting before playing. Neither mode grants XP, rating or Solo statistics.
Guests can join; creating and storing a question library requires an account.

## Curated set

Local bundle `data/trivia/curated-pl-3000-v1` contains JSON, CSV and audit reports.
It is intentionally excluded from Git along with other answer-bank data.
The set covers completed Premier League seasons 2010/11 through 2025/26.
The generator requires an explicit season scope and never fills a missing quota
by removing its quality gates. Difficulty uses editorial heuristics and should
later be calibrated against actual answer rates.

Families include hat-tricks, braces, scoring landmarks, club scorers, transfers,
football nationalities, comebacks, major wins, teammates and club career clues.
Game selection balances these formats, not only their broad topic labels.
Scoreline memories (including braces, hat-tricks and comebacks) share a limit
of two per rolling ten questions; nationality gets one. Other formats rotate
and repeated players/clubs are avoided when an alternative exists. Caps relax
only when the eligible pool has too little variety to fill the request.
Solo sudden death carries the previous window forward. Bank-backed Friend
Duels use the same selection, and Daily attempts reorder their fixed eligible
pool by format without changing its contents or the scoring rules. Answer
choices still shuffle independently. Custom authors' questions stay separate.
Whole-season scoring requires full event coverage and matching season totals.
The independent checker reads source tables, reconstructs prompts, checks
one-answer ambiguity and rejects changed answers or mismatched wording.
This is a database consistency audit, not external verification of every fact.
Provider mistakes can still exist. A small external spot-check used the official
[Manchester City match report](https://www.mancity.com/news/mens/manchester-city-v-spurs-pl-match-report-19-jan-2023-63809757)
and [Tottenham transfer history](https://www.tottenhamhotspur.com/news/994637/wanyama-to-montreal-impact-agreed).

## Deployment

Required migrations are `055_community_questions` and `056_bank_retirement`.
They add tables and guards only. Apply both before deploying to Render.

```sh
.venv/bin/python -m tools.migrate_account_settings --render --migration 055_community_questions
.venv/bin/python -m tools.migrate_account_settings --render --migration 056_bank_retirement
```

Question content is not a schema migration and is not uploaded by a Git push.
After checking the local CSV, run the separate append-only publisher locally.
It audits all 3,000 items against the local football database, requests the
Render URL in a hidden prompt, backs up Render and requires typed confirmation.
It does not replace player accounts, existing releases or game history.
An identical rerun reuses the same release.

```sh
.venv/bin/python -m tools.publish_curated_render data/trivia/curated-pl-3000-v1/questions.json --replace-old
```

Deploy the code and updated season footer only after the migration and bank
publication succeed. No Render operation is performed by local generation.

The replacement retires previous source batches and leaves only the new 3,000
questions playable. Subsequent approved player submissions can still be added.
Old packs cannot be selected even with a previously saved pack ID. Solo, Friend
Duels, practice and new Daily attempts share the retirement policy. An already
created daily pool gets a new shared replacement snapshot, without changing
previous attempts, scores or the one-ranked-attempt-per-day rule.
Started games keep their frozen questions until they finish. Historical question
records remain solely to preserve referential integrity and game evidence.

For the local database only, after importing the replacement:

```sh
.venv/bin/python -m tools.retain_curated_bank
```

## Verification

```sh
TRIVIA_DB_TEST=1 .venv/bin/python -m unittest tests.test_community_questions tests.test_curated_questions
```

Community tests roll back all records. Bank tests are read-only, cover every
answer and reject 100 intentionally changed questions or answers. Browser tests
mock writes and cover mobile/desktop layouts in light and dark themes.
