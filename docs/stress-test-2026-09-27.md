# Capacity assessment: ON THE DOT.

Date: 2026-09-27. Target: 50-100 simultaneously playing people.
Application revision: `89206ea5535e9810dd48b722eba3d14bbde1a910`.

This is the pre-optimization baseline. Follow-up changes and measured results
are in [the optimization report](optimization-2026-09-27.md).

## Conclusion

Do not advertise 100-player production capacity yet. Mixed traffic worked at
50 simulated players locally, but 100 players delayed polling substantially.
An all-Daily workload saturated the application earlier and produced failed
requests at 100 players. A database upgrade alone will not resolve this.

Recommended database for the next paid staging/production validation:
Render Postgres `1c-2g`, 1 CPU, 2 GB RAM, 10 GB storage, internal networking
in the same region as the web service. This is a conservative configuration
recommendation, NOT a measured Render capacity guarantee.

Fix the Daily state/locking path, redundant Solo writes, and ranking aggregation
before buying substantially larger infrastructure to compensate for them.

## Method and safety

- Real HTTP against the existing FastAPI application and real PostgreSQL.
- One Uvicorn worker, no production route patches, SQL constraints/triggers and
  database-backed rate limits enabled. No mocked API responses.
- A NEW randomly named local database for each suite. Only the established
  game-data export allowlist was copied: no existing accounts or match history.
- 5,910 question-release rows copied; this is not a count of unique questions.
- Each suite started with 1,000 synthetic registered users and 10,000 completed
  historical Solo matches, generated through the existing game engine and
  persistence logic. Repeated fixtures used different historical weeks so the
  weekly no-repeat constraints remained enabled. These are synthetic distributions,
  not a claim to reproduce real players' win rates or answer distribution.
- Each load stage used fresh synthetic users. Registered session setup was
  seeded outside the timed workload; password hashing and registration bursts
  were NOT benchmarked.
- Clients attempted one update per second, answered after about five seconds,
  waited two seconds between Solo/Daily questions and replayed completed games.
  Answers were selected from the available options, not from a supplied answer key.
- Mixed traffic: approximately 60% Solo, 20% Daily, 20% friend-duel participants.
  Integer rounding gave 16/5/4 participants at the 25-player stage.
- One additional ranking browser requested a different metric every two seconds.
- Mixed stages: 90 seconds each. Daily-only stages: 60 seconds each.
  In-flight requests were allowed to drain; reported RPS uses actual elapsed time.
- Per-request timeout: 10 seconds. Missed one-second ticks are counted explicitly;
  reported throughput is achieved throughput, not an unlimited arrival-rate claim.
- Each simulated user normally had a separate test source IP through a
  loopback-only trusted proxy. A separate shared-IP probe tested the NAT case.
- All test servers stopped and both disposable databases were removed.
  Production data, plans, configuration and deployed code were not changed.

Host: macOS arm64, 10 logical CPUs. PostgreSQL 18.6, max_connections=100,
shared_buffers=128 MiB, work_mem=4 MiB. Client, server and database ran on the
same machine, without Render CPU quotas, TLS or real internet latency.
This is a short local capacity/bottleneck test, not a long soak, cloud staging
certification, GPU/animation benchmark, or complete public-traffic simulation.

## Results

P95 means 95% of measured requests completed within the stated duration.
Latency summaries include failed requests, not just successful responses.

| Workload | Players | Requests | Requests/s | P95 | P99 | Failed requests | Missed ticks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mixed | 10 | 818 | 8.99 | 124 ms | 673 ms | 0 | 0 |
| Mixed | 25 | 1,964 | 21.54 | 110 ms | 627 ms | 0 | 0 |
| Mixed | 50 | 3,939 | 42.59 | 221 ms | 589 ms | 0 | 0 |
| Mixed | 100 | 7,475 | 82.15 | 1,253 ms | 2,338 ms | 0 | 236 |
| Daily only | 50 | 2,281 | 35.64 | 1,728 ms | 2,601 ms | 0 | 144 |
| Daily only | 100 | 3,300 | 52.21 | 5,146 ms | 8,569 ms | 43 (1.30%) | 1,533 |

Total: 19,777 measured workload requests, excluding smoke/integrity probes.
100-player Daily failures: 38 answer HTTP 409 responses, 3 poll read errors,
2 start read timeouts. The response bodies were not retained in this run;
expired answer windows under queueing are a plausible explanation for the
409s, not a proven classification of every conflict. There were no recorded
Uvicorn ERROR lines or PostgreSQL deadlocks in these runs.

Worst observed application RSS was 644 MiB (Daily 50); mixed 100 peaked at
325 MiB. These are macOS measurements, not an exact Linux RSS prediction, but
they make a 512 MB production web instance a poor choice for this workload.
Peak sampled database connections: 39 in mixed 100, 41 in Daily. The 100-connection
ceiling was not reached. Up to 39 connections were observed waiting on locks
in the Daily 100 stage. Connection/lock peaks are sampled once a second.

At mixed 100, P95 answer latency was 988 ms for Solo and 1,856 ms for Daily.
The XP ranking endpoint reached P95 6,984 ms, though only a small number of
ranking requests were made at each stage. At Daily 100, P95 answer latency
was 6,946 ms and P95 starting a run was 8,932 ms.

## Integrity and targeted probes

- Two simultaneous POSTs with the same answer request ID both succeeded,
  with one saved answer and no duplicate reward. Completing six correct Easy
  answers produced six answer rows and exactly 120 XP, including the win bonus.
- Five unchanged Solo polls preserved the state digest but changed the row's
  `xmin`, proving an unnecessary database row rewrite.
- A sampled Solo state was 11,661 bytes of JSON / 4,430 stored bytes.
- A sampled Daily state held 999 questions: 1,127,442 bytes of JSON / 340,158
  stored bytes. Personal exclusions explain why it was below the 1,000 pool.
  This is server/database state, NOT a claim that hidden answers reach browsers.
- 25 fresh accounts starting Solo from the same IP produced 20 accepted starts
  and five HTTP 429 responses. The current shared-IP limit can block groups
  playing from a school, office or the same Wi-Fi.
- Five unit tests cover loopback-only source validation and latency/error math.

## Prioritized improvements

1. **Daily pool locks and state size.** `api/challenge_routes.py:76` takes the
   global daily advisory lock even for an already-created immutable pool and
   keeps it for the personal-start transaction. Use a read fast path, lock and
   recheck only for pool creation. Validate this under concurrent midnight starts.
   Store immutable question snapshots separately from mutable run state so
   polling does not deserialize a full 1,000-question deck and send it back
   twice as UPDATE parameters (`api/challenge_routes.py:117`). Preserve frozen
   evidence and weekly no-repeat semantics; do not silently shrink the pool.
2. **Read-only unchanged Solo polls.** `api/solo_routes.py:123` rewrites the row
   and retries inserts for all historical answers on each poll. Persist only
   actual changes/new events, preserving timeout processing and atomic XP.
3. **Ranking summaries/cache.** `api/game_community.py:20` aggregates ledgers and
   evaluates match outcomes over historical JSON on each request. Prefer
   transactionally maintained compact match summaries plus a short-lived
   aggregate cache. Moderation/team changes must invalidate relevant results;
   never leak a cached signed-in player's `me` field to another visitor.
4. **Connection reuse and bounds.** `api/database.py:11` opens a fresh connection
   for each operation; write requests also run a separate rate-limit transaction.
   Add a bounded application pool with a starting range of 2-10 connections per
   worker, a short acquisition timeout and observability. Validate before deploy.
   Keep aggregate limits below the DB cap, including deploy overlap/admin headroom.
5. **Fair limits behind NAT.** `api/penalty_routes.py:57` keys gameplay limits by
   IP. Use authenticated account/trial identity plus a separate, higher IP abuse
   ceiling. Keep stricter login/registration protection; do not remove throttling.

## Paid Render configuration

Prices checked 2026-09-27 against the official
[Render pricing page](https://render.com/pricing). USD/month, excluding taxes,
traffic overages, optional workspace subscription and temporary staging costs.

| Component | Proposed specification | Monthly compute/storage |
| --- | --- | ---: |
| Recommended Postgres | `1c-2g`: 1 CPU, 2 GB RAM | $40 |
| Database storage | 10 GB at $0.30/GB | $3 |
| Web after optimization, to validate | `1c-2g`: 1 CPU, 2 GB RAM | $25 |
| Total for optimized paid pilot | Database + storage + web | **$68** |
| Larger web candidate if needed | `2c-4g`: 2 CPU, 4 GB RAM | $85 |
| Total with larger web | Same database + larger web | **$128** |

Do not promise 100 players on the $68 configuration before the changes above
and a staging retest. The $128 option provides more web headroom but is also
NOT certified here and does not fix lock serialization or shared-IP throttling.

A cheaper database candidate is `0.5c-1g` (0.5 CPU, 1 GB RAM, $19) with 5 GB
storage ($1.50), but treat it as a small optimized pilot, not a guaranteed
100-player configuration. The 256 MB tier is not the recommended launch target.

The baseline game copy used about 35 MiB; with synthetic history it used about
196 MiB. Mixed load ended at 356 MiB; the Daily suite ended at 722 MiB. These
include dead tuples, indexes, TOAST and allocation overhead and must NOT be
extrapolated linearly as durable per-match storage. Ten GB is initial growth
headroom; measure retention and bloat after normal operation.

- Put web and database in the same Render region and use the internal URL.
- Start with one web worker, retest changes to worker/pool counts together.
- Consider Render's integrated PgBouncer for short-lived connection bursts.
  It is available on paid databases without an additional pooling charge.
  Activation restarts the database; use a maintenance window. Keep migrations,
  exporters using session advisory locks, and other session-bound tooling on
  the direct connection. See
  [Render connection pooling](https://render.com/docs/postgresql-connection-pooling).
- Paid databases offer PITR: three days on a Hobby workspace, seven on Pro or
  higher. Arrange independent retained backups and a restore drill as well.
  See [Render recovery and backups](https://render.com/docs/postgresql-backups).
- A connection limit is not a player limit. See
  [Render PostgreSQL connection limits](https://render.com/docs/postgresql-creating-connecting#connection-limits).

## Validation gate before a 100-player launch

Repeat the mixed, all-Daily, shared-network and retry tests on an isolated
Render staging database with the actual proposed paid resources. Use a separate
load-generator host, realistic account/session lifetimes, a gradual ramp, a
synchronized start burst and at least 30 minutes at 100 active players.

Suggested acceptance goals: gameplay P95 below 500 ms, starts P95 below 1.5 s,
rankings below 1 s, no normal-play 409/429s or duplicate XP, no sustained missed
polls, and no timeout/5xx failures. Watch application and database CPU, memory,
connection acquisition, lock waits, storage/TOAST growth and deadlocks. Leave
roughly 30% sustained resource headroom. Validate another step above the target
before publishing a capacity claim.

## Reproduce locally

From the On The Dot. project, with local PostgreSQL and its existing `.env`:

```sh
.venv/bin/python -m unittest tests.test_stress_game
.venv/bin/python -m tools.stress_game --concurrency 10,25,50,100 --seconds 90 --history-players 1000 --history-runs 10000 --output reports/stress/mixed-new.json
.venv/bin/python -m tools.stress_game --scenario daily --concurrency 50,100 --seconds 60 --history-players 1000 --history-runs 10000 --output reports/stress/daily-new.json
```

The tool refuses non-loopback database hosts and existing output paths. It
uses an ephemeral local HTTP port; it cannot be pointed at onthedot.gg. It
automatically stops escalating load above a 5% failure rate. Completion of the
script means measurements were collected, not that latency goals passed.

Raw reports (ignored by Git, retained locally):

- `reports/stress/2026-09-27-mixed.json`
- `reports/stress/2026-09-27-daily.json`

The mixed run preceded the addition of the extra integrity/NAT probe; the
Daily report contains that probe. Both used the same unchanged application
revision. No measured report values were replaced with estimates.
