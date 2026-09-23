# User-Written Questions

The private Studio editor now starts with **Question & answer**. The editor writes
the question, clicks **Find answer**, reviews a model interpretation when needed,
and receives a calculated database answer. Clickable examples fill the text
field without submitting it. The original user text is never replaced.

URL: `http://127.0.0.1:8002/internal/trivia#question-writer`.

## Recognition and Answers

- Exact supported bank wording is evaluated directly, without a model call.
- Common league-wide phrases (champion, runner-up, supported club records and
  goalless-match totals) normalize to approved calculations without requiring a
  team or player name. Final standings must be complete; missing data never
  triggers a guessed champion. Additional filters prevent a simple phrase match.
- Other wording retrieves up to eight distinct, database-verified syntax families
  from the imported library. TF-IDF retrieval is not an answer generator.
  League-wide prompts exclude patterns that need a named subject club, and
  zero-similarity patterns are not supplied to the model.
- The local Qwen3 library adapter proposes a supported interpretation. It receives
  no reference answers and cannot submit SQL or an answer value.
- A separate text-to-query adapter can recognize player career scopes, missing
  time scopes, player statistics and league-wide questions. Its output contains
  typed slots, not an answer, SQL, or a model-invented player ID. See
  [recognition training](QUERY_RECOGNITION.md).
- Season-scoped questions accept both `2017/18` and `2017/2018`.
  Explicit career questions have no season restriction and include every club.
  A missing time scope is not silently interpreted as career or the latest season.
  Recognized clubs, seasons and explicit numeric thresholds must survive interpretation unchanged.
- Model interpretations must be confirmed before their calculated answer is shown.
  This is essential because club/season agreement alone does not prove that every
  condition in a free-form question was understood correctly.
- The bank evaluator rejects incomplete coverage, ambiguous winners and unsupported
  calculations. Recognized incomplete questions are not sent to a model to invent
  an answer. This first text editor covers Premier League questions only.
- For scorer questions, the result includes the scorer's goal total. The displayed
  matches checked describe data coverage, not the player's number of appearances.
- Career goals resolve a player to their database ID and count Premier League
  normal/penalty goal events, excluding own goals. Recorded and quality-checked
  totals are separate, with a season/club breakdown and supplementary provider
  season totals. Full career coverage is not yet certified: these partial results
  cannot be saved as verified answers. Provider rows may be newer than the sealed
  event dataset; they are comparison data, never substituted as verified evidence.
- Recognition support is not calculation support. Recognized operations without
  a verified executor display that limitation instead of a fabricated answer.

The 1,725-question adapter was trained in the **query-to-question** direction.
Using it to interpret paraphrases is a new, experimental workflow with retrieved
patterns. The earlier 32/32 writing benchmark is **not** evidence of equivalent
free-text recognition accuracy. Confirming the displayed meaning remains necessary.

## Drafts and Access

`Save draft` preserves the user's original wording plus the interpreted question,
calculated answer, snapshot, method, and adapter identity in existing bank-draft
provenance. It does not publish anything. Drafts appear under Question bank >
New question > Saved drafts.

Changing the input clears the answer, confirmation token and save eligibility.
Out-of-order responses cannot restore a stale answer. Server-signed tokens bind
the original question, interpretation and snapshot, expire after 30 minutes, and
must carry confirmation for model-derived drafts. Save rechecks the calculation.

All endpoints and static assets require existing Studio authentication and
same-origin write requests. Public penalties and account flows are unchanged.
GPU editor work is bounded by a cross-process non-blocking lock and a 150-second timeout.
The worker is offline, receives no database credentials, and uses the completed
adapter without silently falling back to another model. Temporary inference files
are removed when the request completes.

## Verification

```sh
.venv/bin/python -m unittest tests.test_trivia_writer
node --test tests/test_trivia_writer.cjs
.venv/bin/python -m unittest tests.test_trivia_intent
```

`src/verify_trivia_writer.cjs` is an opt-in Playwright test against the running
server and installed Chrome. It needs `TRIVIA_EDITOR_USERNAME` and
`TRIVIA_EDITOR_PASSWORD` in its environment and the Playwright package available.
It signs in using the normal login endpoint, does not save or publish a draft,
checks original wording preservation, Lukaku's 16 goals, stale-answer removal,
missing-season errors, desktop/mobile layouts and browser exceptions. Screenshots
are private under `data/private/writer-ui-check/`.

`src/verify_trivia_intent.cjs` checks the real trained career recognition,
confirmation, database player identity, partial-result save restrictions,
league winner query, original text, and desktop/mobile layouts. It performs no writes.
