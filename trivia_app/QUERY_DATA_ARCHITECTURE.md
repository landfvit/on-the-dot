# Query Interpretation and Data Updates

Architecture addendum, 2026-09-21. Based on the supplied
`sports_query_vlastni_model_a_aktualizace_dat.md` (version 1.0).
This records project requirements and implementation gates, not a deployed
scheduler, trained model, provider SLA or approval of a data licence.

## Non-negotiable Boundaries

1. No external LLM API, including fallback for an unrecognized query.
2. The parser interprets text. PostgreSQL holds facts. The query engine computes
   answers. New match results never trigger model training.
3. Web requests read prepared local data; they never start provider backfills.
4. Any future local model returns the same strict, allowlisted query contract.
   It cannot supply an answer, executable SQL or silently discard a condition.
5. Published question and quiz revisions retain their snapshot and answer.
   Provider corrections require explicit new revisions or retirement, never a
   silent change to the answer of an existing attempt.

This supersedes the earlier proposal's optional external-LLM translation phase.
The licensed sports provider is a separate data source, not an LLM dependency.

## Current Implementation Versus Planned Work

| Area | Present now | Not yet implemented |
|---|---|---|
| Text interpretation | Local grammar and strict SportsQuery; separate private metric-phrase annotation, local baseline training and experiment registry | A deployed ML full-query parser |
| Computation | Parameterized queries over sealed facts, explicit seasons and Big 6 version | Cup result-basis options, additional competition formats |
| Evidence | Match-level evidence, coverage gates, frozen answer and source hash | Correction review workflow for affected published content |
| Updates | Existing provider import scripts and a separate snapshot builder | Managed incremental daily worker, durable targets, leases, budgets and monitoring |
| Freshness | Snapshot creation timestamp | Reliable successful provider-check time per competition/resource |
| Query logging | Failed submissions, private access, bounded text; explicit private annotation and verification | Public collection consent/information and automated retention |
| Deployment | Existing local FastAPI and PostgreSQL setup | Cloud scheduler, restricted database roles and verified network-egress policy |

Keep the existing FastAPI application and PostgreSQL. Django, Celery, Redis, a GPU
and a separate repository are not prerequisites. Nothing in this document enables
a background schedule or spends provider/cloud quota.

## Query Semantics

`last N seasons` currently resolves to an explicit list ending at the latest
completed season present in the chosen snapshot. The selected competition and
actual season list are visible. Missing seasons are not skipped. An ongoing
season is not included by this expression; `all time` includes all available
snapshot seasons and is subject to coverage/publication checks.

Do not equate a decade with ten seasons, `top six` with Big 6, or a W/D/L record
with a win percentage. These expressions are unsupported until their distinct
semantics and schema are implemented. Negations such as `without player X`
must cause refusal, not removal of the condition.

FT results currently support the league-oriented engine. Do not advertise cup
coverage based on the same logic: regulation time, extra time, a penalty shootout
and progression require separate validated result bases and metric versions.

## First Daily Worker Contract

Proposed next implementation: one explicitly configured competition, no live
polling, a separate command invoked by one server-side scheduler. Do not install
a local-thread reminder as a substitute for a production import worker.

The worker should reuse audited portions of `src/history_import.py` after checking
their replacement/null handling. Existing broad import commands are not, by
themselves, a resumable daily scheduler. Scope seasons and competitions explicitly;
do not hardcode the query user's period in an import example.

Persist target identity `(provider, competition, scope, resource_type)`, due time,
last attempt, last successful check, retry count, error category, lease token and
lease expiry. Track match state, component availability and verification separately.
Also persist run scope, request count, changed records and committed checkpoint.

Execution requirements:

1. Claim only due work atomically and reserve its request budget. A reclaimed
   lease receives a new fencing token; an old worker cannot commit after expiry.
2. Fetch outside long database transactions. Validate status, provider errors,
   identifiers, nullable values and every required page before promotion.
3. In one short transaction verify lease ownership, upsert canonical records,
   append correction metadata and enqueue snapshot refresh. Advance checkpoints
   only after all records in the unit have been stored successfully.
4. Retry transient failures with bounded backoff/jitter; respect provider quota
   guidance. Authentication, invalid parameters and unsupported resources need
   intervention rather than infinite retries.
5. Recover missed days from the committed checkpoint with overlap. Continue
   schedule checks even on days with no locally known fixtures.

Suggested initial policy, subject to explicit configuration: daily near-term
schedule refresh and a seven-day reconciliation window; a wider weekly correction
window. Backfill has its own lower-priority budget and must not run every night.
Provider IDs, rights, actual quotas, supported resources, server destination and
operating timezone must be confirmed before enabling scheduled API calls.

A kickoff timer only makes a status check due. It cannot mark a postponed,
abandoned or delayed match as finished. Older responses must not overwrite newer
versions; without a trustworthy source version, serialize the component and
quarantine conflicting corrections. Missing fields cannot become zero.

## Snapshot Promotion and Freshness

`src/trivia_build.py` reads a repeatable-read transaction, fingerprints normalized
facts and creates a new sealed dataset when content changes. Unchanged content
reuses the previous dataset. It does not fetch provider data.

Consequently, snapshot `created_at` is NOT a provider freshness timestamp. A
successful check that finds no changes must still advance separate sync metadata.
Rebuilding yesterday's imported facts does not make them freshly checked.

Track `fetched_at`, `last_successful_check_at` and, only where trustworthy,
`source_updated_at` per resource/scope. A query's freshness must cover its selected
competition, seasons and required components. Unknown checks remain unknown;
checking one resource cannot refresh all resources. Never mutate a sealed dataset
to update a "last checked" badge.

Snapshot rebuilding remains an initial whole-dataset operation, not an incremental
metric-refresh implementation. Failed promotion must leave existing snapshots
usable. Future result caches must include the resolved scope, dataset identity,
calculation/metric version and coverage policy. Published answers use their saved
revision regardless of which snapshot becomes the latest.

## Human-Verified Examples and Local Models

Failed-query logs are diagnostics, not training labels. A future annotation record
should contain the text, reviewer-confirmed interpretation or explicit rejection,
unsupported spans, schema/parser version, reviewer, review time and dataset version.
Never automatically label parser/model output as `human_verified`.

Set access, user information and retention before expanding collection. Training
exports should exclude credentials, personal data and unrelated user records.
Keep paraphrase/template families in one split, and hold out unseen entity names
and filter combinations. Measure full-query correctness, unsupported-query refusal
and especially incorrect execution, not only metric classification accuracy.

First compare a local TF-IDF/linear baseline with rules on an independent test set.
Do not deploy a model until a human approves measured improvement. Store dataset
version, split manifest, config, dependencies, output schema, evaluation results,
artifact hash and previous approved version. A result import never retrains it.
New entities update the catalogue without automatically changing model weights.

Any future encoder must have a reviewed licence and run from locally provisioned
artifacts. Test both offline operation and actual deployment egress restrictions;
unit tests alone are not a network-security boundary.

## Release Gates

- Duplicate jobs, stale leases, crash before commit and multi-day recovery.
- Incomplete pagination, quota exhaustion, invalid credentials and provider outage.
- Postponements, changed kickoff, UTC boundaries and daylight-saving changes.
- Corrections, removed fixtures and partial results without zero overwrites.
- Unrecognized/negated filters, ambiguous clubs, empty samples and missing seasons.
- Provider-check freshness independent of snapshot creation, including no changes.
- Existing question evidence and attempt grading remain unchanged after promotion.
- No external LLM calls; future local-model rejection and rollback tested offline.
- Explicit per-query database timeouts and least-privilege roles before production.

Daily synchronization and annotation/model work are separate implementation
milestones, neither a prerequisite for manually reviewing the current trivia pack.
The initial metric-only annotation/training milestone is now implemented; see
[TRAINING.md](TRAINING.md). It does not enable full-query model execution.
