# Question Recognition Training

This is actual offline LoRA fitting on Qwen3 4B for **user text -> typed query**,
not a keyword classifier or the existing query-to-question writing adapter.
The training set deliberately includes questions whose answers need not exist
in the database. Supervision labels their meaning, never their football answers.

The first contract includes player goals, assists and appearances, league winners,
runners-up and top scorers, and team wins. Time scopes are `season`, `career`, and
`unspecified`. Unsupported filters and operations have a null query target.
Named entities are copied from user text; only the database resolves internal IDs.

## Runs

- First run: 186 unique training questions, 22 validation questions, 43 test
  questions. Exact query match improved from 16/43 to 20/43. Not selected for use:
  it rejected too many valid paraphrases.
- Second corpus: 426 unique training questions, 22 validation questions, 42 fresh
  test questions. The inspected previous 43 tests are retained separately as
  development examples, not added to training. Template wording and entity/season
  combinations are split apart. All labels are assistant-authored, not human-reviewed.
  Exact match improved from 30/42 to 37/42; the remaining five errors and runtime
  limitations are documented in [the measured report](../reports/query-recognition-20260922.md).
- Each run uses one shuffled epoch from the pinned base model, four LoRA layers,
  batch size one, and a fixed final checkpoint. Test records are never loaded by
  the training worker. No automatic model promotion or quiz publication occurs.

Examples of learned meanings:

```json
{"query":{"operation":"player_goals","player":"Marcus Rashford","team":null,"league_id":39,"time_scope":"career","season":null}}
```

```json
{"query":{"operation":"league_champion","player":null,"team":null,"league_id":39,"time_scope":"season","season":2025}}
```

Those are examples, not fixed season defaults. The season comes from user text;
future or unavailable seasons are still recognizable independently of answer data.

## Reproduce

```sh
.venv/bin/python -m src.trivia_intent_training prepare
.venv/bin/python -m src.trivia_intent_training baseline --bundle <printed-path>
.venv/bin/python -m src.trivia_intent_training train --bundle <printed-path>
.venv/bin/python -m src.trivia_intent_training evaluate --bundle <printed-path>
```

Artifacts are private under `data/private/llm/intent-bundles/<run-id>/`:
frozen train/valid/test/development JSONL, labels, prompts, raw predictions, exact
per-question comparisons, training logs, actual adapter weights and hashes.
`ACTIVE_BUNDLE` in `api/trivia_intent_runtime.py` is a manual selection, not a
pointer changed by training. The generator adapter is left untouched.

## Runtime Limits

Predictions must pass strict JSON/schema checks and grounded entity/time-scope
checks. Missing time scopes ask for clarification. The editor requires confirmation
of neural interpretations. Some recognized operations do not yet have an executor;
they display that limitation explicitly. Partial career counts cannot become
verified quiz answers. Sealed database quality gates remain authoritative.

This synthetic English benchmark does not measure arbitrary natural-language
understanding, calibration, spelling correction, or football answer correctness.
Any inspected benchmark becomes development material for subsequent iteration;
future model selection needs another fresh, preferably human-reviewed holdout.
