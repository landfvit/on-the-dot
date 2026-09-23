# Library Generator

This offline generative experiment uses the imported question library, not the
old 65-example pilot or the TF-IDF topic classifier. It does not change the public
game, Studio registry, or any published question.

The completed 1,725-step run and actual generated questions are in the
[training report](../reports/library-generator-1725-20260921.md). The candidate
passed 32/32 new-scope checks and 2/16 held-out-family checks. This is a strict
wording-contract metric, not general semantic accuracy; the model is not promoted.

## Data

The 2026-09-21 snapshot contains 3,950 imported questions. Every reference answer
is checked again with the deterministic bank evaluator before selection. The
new wording compiler maps 2,387 verified questions into a closed semantic query
vocabulary. Another 49 database-matched questions (48 player questions and one
scoreline record) are not mapped by this writer yet. Unsupported, incomplete, ambiguous and conflicting questions are
excluded, not silently treated as verified facts.

| Split | Unique Questions | Grouped Families |
|---|---:|---:|
| Training | 1,725 | 58 |
| Validation | 322 | 8 |
| Test references | 340 | 12 |

Training spans 26 source topics. Club names, season labels and numbers are masked
before grouping. Near-identical families (90% similarity) are joined transitively;
no family crosses splits. Some operators are consequently entirely unseen during
training. Training membership is frozen before any model run.

The corpus includes only seasons explicitly mentioned in selected source questions.
The generation benchmark has its own explicit season parameters, recorded in each
job. These are experiment fixtures, not a hard-coded live quiz season policy.

## Contract

Input: a semantic operator, typed parameters, and a dictionary of referenced club
names. The source question, answer and evidence are **not** in the prompt.

Output: JSON containing only `question`. The model learns question wording from
real library examples; it is not taught to memorize the answer. A supported
question must compile back to exactly the supplied query, including venue,
condition, scope, and score perspective. The database then calculates its answer.

This version is a **query-to-question writer**, not an autonomous inventor of
database operations. A scheduler supplies factual queries; the model writes their
questions. The old pilot's operation-selection contract remains separate.

The strict compiler abstains on unsupported paraphrases. Therefore automatic pass
rates measure conformance to the approved wording grammar plus database agreement,
not general semantic accuracy. The original model text is retained, never replaced
with a rendered template to improve the reported score. New-scope tasks are new
facts within the imported bank, not claims of entirely new linguistic templates.

## Training

The local Qwen3 4B model starts from its pinned base weights, not the overfitted
240-update pilot adapter. One epoch means exactly 1,725 batch-one optimizer steps.
MLX shuffles a complete permutation of all row indices, so every selected training
row is used once. Gradient accumulation is the default one step. The worker checks
that the requested iteration count equals the training row count.

Four LoRA layers, learning rate 0.00005, 1,024-token ceiling, gradient checkpointing,
fixed seed 42, offline execution and a two-hour timeout are used. Training cannot
truncate targets. The old pilot remains capped at 200 steps per invocation; the
library protocol is capped at 2,500 and cannot resume an incompatible adapter.

Only training and validation files are loaded by the training worker. Validation
loss is sampled on 25 validation batches at the beginning/end. The fixed final
checkpoint is not selected using test results. The generation benchmark evaluates
16 held-out-family tasks and 32 new-scope tasks, not all 340 test references.

## Reproduce

Run from the repository root with the existing local model/runtime installed:

```sh
.venv/bin/python -m src.trivia_library_llm prepare
```

Use the new bundle directory printed by that command:

```sh
BUNDLE=data/private/llm/library-bundles/<new-bundle-id>
.venv/bin/python -m src.trivia_library_llm infer --bundle "$BUNDLE" --label baseline
.venv/bin/python -m src.trivia_library_llm train --bundle "$BUNDLE"
.venv/bin/python -m src.trivia_library_llm infer --bundle "$BUNDLE" \
  --label library-one-epoch --adapter "$BUNDLE/adapter-one-epoch"
```

Existing runs and adapters are never overwritten. The recorded bundle is:
`data/private/llm/library-bundles/ddea4313-8ed2-449c-94d0-65c2c2026513`.

Artifacts:

- `manifest.json`: source count, topic/operator counts, splits and file hashes.
- `provenance.json`: source IDs, original wording, reference and computed answers.
- `excluded.json`: each exclusion and its fresh database status.
- `source.json`, `inputs.json`: frozen source and standings provenance.
- `adapter-one-epoch/training.log`: actual loss, steps and memory usage.
- `adapter-one-epoch/completion.json`: completed steps and adapter checksum.
- `runs/*/raw.jsonl`: original model output, seed and model/adapter identity.
- `runs/*/review.md`: every output, automatic check and computed answer where approved.
- `independent-sql-check.json`: a second calculation for all 32 new-scope jobs,
  using raw fixtures and final standings without the bank evaluator's helpers.

All artifacts are local and ignored by Git, outside public static directories.
No cloud service is called and no question is published automatically. Snapshot
scores are reconciled with raw fixtures, but both originate from the same football
provider: this is not independent external-source verification.

## Tests

```sh
.venv/bin/python -m unittest tests.test_trivia_library_llm tests.test_trivia_llm
TRIVIA_LIBRARY_BUNDLE="$BUNDLE" TRIVIA_DB_TESTS=1 \
  .venv/bin/python -m unittest tests.test_trivia_library_llm
.venv/bin/python -m src.check_library_generation --bundle "$BUNDLE"
```

The integration suite checks every selected source/target pair, exact query
round trips, zero family overlap, unique new-scope queries and fresh database
recalculation of all 2,387 selected answers. Database access is read-only.
