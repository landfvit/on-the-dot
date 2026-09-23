# Penalty Trivia Pilot

Open `/penalties` on the trivia-only app (default `http://127.0.0.1:8002`).
Existing quiz, practice and editor data is retained, but those features now require
editor authentication. The separate football analytics service is unchanged.

## Playing

- Solo: up to ten shots (a smaller approved pack gives a shorter series); a correct answer scores one goal. Results wait for the Next shot button, which can also skip the animation.
- Private PvP: create a room, share its link/code, and both confirm ready.
  Each player needs a separate browser profile/session. Two tabs in the same
  profile intentionally represent the same player, not two opponents.
- Both answer the same question with identical option order. Roles alternate
  after a completed shot. Correctness wins before speed; two correct answers
  less than 150 ms apart replay with a new question and the same roles.
- First to ten goals, checked only after both players have had their attempt.
  10:10 continues for another complete pair. Saves do not score goals.
- Countdown 3 s; answer window 12 s; result display 2.5 s; reconnect grace 20 s.
  The 30-minute cap or an exhausted question pack ends without a winner.
- Rematch creates one shared new room, reserves both players and resets ready.
  Refresh retains identity, current question, submitted answer and deadline.

## Content

The default pack is General from the explicitly released research bank (see
Public Packs And Access below). The optional training pack contains 80 distinct, deterministically checked arithmetic
questions explicitly labelled **model examples**, not historical club facts.
Questions are paired by arithmetic category before pair shuffling. Replays can
interrupt those pairs; comparable difficulty is a pilot heuristic, not a guarantee.

The separate POINTS library option uses only numeric, verified, published
question versions. It does not invent entity distractors or quietly publish
drafts. Packs need at least 1 question for solo and 40 for PvP. A shortage is
visible and blocks creation. No question repeats during one match. All content,
option order and correct answers are frozen in the private match snapshot.
The arithmetic pack is not added to the user's public football question library.

## Authority And Storage

FastAPI and PostgreSQL remain the stack. Guest identities are authenticated by
a random HttpOnly, SameSite=Strict cookie; only its SHA-256 hash is stored.
Room membership is checked separately from possession of the room code.
POST requests enforce same-origin; WebSocket handshakes require exact Origin.
Payload schemas reject claimed correctness, scores and client timing.

Commands use HTTP; WebSockets deliver committed snapshots. They do not stream
animation frames. A server clock task also resolves expired rounds without
connected clients. Each mutation takes the match row lock. An answer, resolution,
score and audit record commit together. Database unique constraints prevent
duplicate answers/request IDs; triggers protect recorded answers, resolved
penalties and frozen match packs/rules. Repeated requests with identical IDs
return the current snapshot without scoring again.

The accepted timestamp is PostgreSQL's clock after acquiring the match lock.
This measures server processing receipt, including network/queue delay, not pure
human reaction speed. Inputs at or beyond the deadline are rejected. Clients do
not receive a question during countdown or correctness until resolution.
Short restarts recover the saved deadline; gaps over 25 s conservatively mark
the match technically abandoned. They do not fabricate a player's defeat.

Tables: `pvp_players`, `pvp_matches`, `pvp_answers`, `pvp_penalties`,
`pvp_rate_limits`. Content versions are embedded in the immutable match pack;
historical questions retain their original POINTS version ID internally.

## Run And Test

```sh
.venv/bin/python src/trivia_migrate.py
.venv/bin/python -m uvicorn trivia_app.main:app --host 127.0.0.1 --port 8002
TRIVIA_DB_TEST=1 .venv/bin/python -m unittest discover -s tests -p 'test_penalty*.py'
node --test tests/test_penalty_scene.cjs
```

Database integration tests create uniquely named `test_penalty_*` schemas and
remove only those schemas afterwards. They exercise real concurrent connections,
timeout races, duplicate delivery, frozen content, outsider access, Origin checks,
no premature answer leakage, timer-only resolution and shared rematches.

## Before Public Deployment

This is a local unranked pilot, not a production matchmaking service. The current
loopback URL is reachable only on this computer. Do not expose the development
server to the internet; deploy behind HTTPS/WSS with a trusted proxy/Host setup.
Use two profiles on this computer to try PvP; real-device/network testing still
requires a shared, properly secured deployment.

The snapshot loop polls PostgreSQL (up to 100 active rooms per sweep). Multi-worker
locks are safe, but throughput has not been load-tested. Add a pool and event
fan-out before scaling; apply proxy connection/message limits and monitoring.
IP rate limits currently use the direct peer address; configure trusted proxy
handling before deployment. Guest names are not registered account identities.
External assistance and users who already know a public question cannot be
prevented by this pilot. No ranked ratings, chat, spectators or public matchmaking.

Animations retain the supplied SVG field/goal/ball design, add a keeper and
respect both system reduced-motion preferences and the local animation toggle.
No LLM, payment, cloud service or scheduled automation is enabled.

## Public Packs And Access

`/` and `/penalties` are the only public trivia game pages. Other pages, quiz and
practice APIs, the question bank and editor assets require editor authentication.
Public API responses expose pack metadata and only the current room question;
answers and validation authority are revealed after resolution, never beforehand.
The separate analytics app on port 8001 is unchanged; only expose the trivia
service when deploying penalties.

The owner-approved research bank is frozen in `penalty_bank_releases` and
`penalty_bank_questions`: General (250), 34 clubs (50 each), and an all-bank mix
(1,950). Each question has four distinct choices with exactly one original
canonical answer. Alternatives are selected by answer type, never by an LLM.
Names/club aliases and related colour names are excluded as duplicate answers.
Hard database disagreements and ambiguous multi-winner questions are excluded.
Unverified owner-approved answers are explicitly labelled as reference answers
after resolution, not as database-confirmed facts. These remain unranked games.

A room pins its release, section, option order and answers. Up to 120 randomly
selected distinct questions are copied per match; club packs retain all 50.
Rematches keep the same release and section but reshuffle questions and options.
Existing maths/library rooms continue working. New imports and audits never
automatically become public packs. Explicit owner authorization is required:

```sh
.venv/bin/python -m src.trivia_migrate
.venv/bin/python -m src.publish_penalty_bank --run VALIDATION_RUN_UUID --confirm-user-attested
```

The command is idempotent for the audit and choice-policy version. Database
guards freeze releases and answers and reject incomplete releases, foreign
questions, changed reference answers and conflicting audit results.
