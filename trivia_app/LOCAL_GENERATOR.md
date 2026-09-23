# Local Generative Model

The expanded real-library training pipeline is documented in
[Library Generator](LIBRARY_GENERATOR.md). The 65-example runs below are retained
as historical pilot results, not the current training corpus.

This is a separate, real language generator, not the existing TF-IDF topic classifier.
The generation experiment described here remains a command-line pilot. A separate
[user-written question editor](TEXT_ANSWERS.md) now uses the local adapter for
experimental text interpretation with explicit confirmation and database answers.
The public penalty game and existing model registries are unchanged.

## Pipeline

1. Select explicit season start years. Nothing silently selects the last N seasons.
2. Freeze a sealed dataset and require complete 380-match Premier League seasons.
3. The local model chooses one allowed operation and writes a question plus a typed query.
4. Reject malformed JSON, unknown fields/operators, changed scope and duplicates.
5. Calculate the answer in Python over sealed facts and independently in SQL over
   raw fixtures. Both answer values and evidence fixture IDs must agree.
6. Save an unpublished draft with original model wording, calculated answer,
   evidence and canonical reference meaning for review. Never replace the model's
   words with a template and call that model generation.

The 20 allowed operations currently cover runs, opening/closing windows, adjacent
results and first/last/largest-win opponents. This is a bounded capability catalogue,
not arbitrary executable SQL. The model cannot add new computations by inventing
operator names. Unsupported weather, player or kit filters fail closed.

The database check validates the **structured query**, not the free-form English.
Every accepted draft still needs a wording review. The two calculations share one
football provider, so agreement is not independent external-source fact checking.
No result is automatically published, promoted or sent to an external LLM service.

## Runtime

- Apple Silicon, Python 3.12 in `.venv-llm`; app dependencies remain in `.venv`.
- MLX LM 0.31.1, dependencies pinned in `requirements-llm.lock.txt`.
- `mlx-community/Qwen3-4B-Instruct-2507-4bit`, Apache-2.0.
- Pinned model revision: `50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b`.
- Download about 2.3 GB once; inference/training use local safetensors, offline
  flags, no remote tokenizer code and no automatic API/cloud fallback.
- The subprocess does not inherit database passwords, API keys or cloud logging
  credentials. The parent only reads the database.
- Bounded tokens, prompts, jobs, timeouts, batch size and memory. A failed adapter
  never silently falls back to the base model.
- All model/data/run artifacts live under ignored `data/private/llm/`, outside web
  static directories. This is a trusted-local CLI, not a sandbox for untrusted users.

Official references: [MLX LM](https://github.com/ml-explore/mlx-lm),
[LoRA training](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md),
[model card](https://huggingface.co/mlx-community/Qwen3-4B-Instruct-2507-4bit).

## Reproduce

Run from the repository root. First-time setup only:

```sh
uv venv --python 3.12 .venv-llm
uv pip sync --python .venv-llm/bin/python requirements-llm.lock.txt
.venv-llm/bin/python -m src.download_trivia_llm
```

Prepare a pilot from the existing 100 checked questions. Replace the seasons with
the user's chosen start years; this example is not an implicit default:

```sh
.venv/bin/python -m src.trivia_llm prepare \
  --source reports/generated-trivia/e362291e-6005-43e4-a029-04e2ba022261/questions.json \
  --seasons 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025
```

Use the printed bundle directory as `BUNDLE`:

```sh
BUNDLE=data/private/llm/bundles/516850f5-3199-4e40-944c-4da3ef222442
.venv/bin/python -m src.trivia_llm infer --bundle "$BUNDLE" --label baseline
.venv/bin/python -m src.trivia_llm train --bundle "$BUNDLE" --iterations 40 --label adapter-json
.venv/bin/python -m src.trivia_llm infer --bundle "$BUNDLE" \
  --label lora-json-40 --adapter "$BUNDLE/adapter-json"
.venv/bin/python -m src.trivia_llm compare --bundle "$BUNDLE" --candidate lora-json-40
```

Existing run labels/adapters are never overwritten. The recorded pilot already
exists at the example path: inspect it, or prepare a new bundle for a new experiment.
The same-bundle baseline/candidate comparison intentionally uses the same question
scopes. Other bundles and existing libraries count toward duplicate detection.

To continue from the corrected adapter for 100 additional updates:

```sh
.venv/bin/python -m src.trivia_llm train --bundle "$BUNDLE" \
  --iterations 100 --label adapter-json-140 --resume-adapter "$BUNDLE/adapter-json"
.venv/bin/python -m src.trivia_llm infer --bundle "$BUNDLE" \
  --label lora-json-140 --adapter "$BUNDLE/adapter-json-140"
.venv/bin/python -m src.trivia_llm compare --bundle "$BUNDLE" --candidate lora-json-140
```

Continuation keeps the learned adapter weights and starts a new Adam optimizer;
it is not a full optimizer-state checkpoint resume. It requires the same pinned
base model, frozen dataset/splits, corrected JSON target format and LoRA shape.
The parent weights and their hash are recorded, and the source adapter is never
overwritten. New adapters require a completion record before inference or further
continuation; failed or modified weights are rejected. The command above is a
bounded experiment, not continuous training, and does not add new training data.

`comparison-lora-json-40.md` contains the readable result and candidate questions.
Each run also has `raw.jsonl`, `report.json` and `review.md`; the adapter directory
has actual weights, training log and provenance. Recheck database answers with:

```sh
.venv/bin/python -m src.trivia_llm audit --bundle "$BUNDLE" --run "$BUNDLE/runs/lora-json-40"
```

## Training Data and Limits

The pilot uses **100 synthetic, assistant-authored, DB-checked examples**, not all
3930 imported questions and not 100 human-approved annotations. Training targets
contain question wording and a query, not the answer. Provenance explicitly records
`human_reviewed: false`; this does not bypass the existing human-verified query
classifier training rules or write to its registry.

Semantic families never cross splits:

| Split | Families | Examples |
|---|---|---:|
| Train | Runs, opening/closing windows, largest margins | 65 |
| Validation | Adjacent clean-sheet pairs | 5 |
| Test | Result transitions, chronological opponents | 30 |

The generation benchmark has 16 unseen club-season tasks from held-out operation
families plus four unrestricted-choice tasks. Both variants see the same catalogue,
scopes and sampling seeds. The training worker reads train/validation only; the
final 40-update checkpoint is fixed in advance, not selected by test results.
The 30 test examples are reserved references, not a reported 30-example accuracy
score. The reported generation score has denominator 20. Forty batch-one updates
do not imply every one of the 65 available examples was seen.

This small pilot measures protocol learning and limited transfer, not production
quality. Catalogue order, few families, synthetic wording and a small validation
set limit conclusions. Repeatedly inspected tests become development benchmarks;
use fresh independently reviewed families for a final evaluation.

Before broader deployment: map verified library questions to supported queries,
review those mappings, add varied paraphrases and negative examples, introduce
operation/category quotas, evaluate wording fidelity and diversity separately,
then connect a private review/approval workflow in Studio. Source-attested-only
answers must not silently become DB-verified training labels.

## Recorded Pilot: 2026-09-21

| Check | Base | Corrected 40-update LoRA |
|---|---:|---:|
| Valid JSON and requested scope | 0/20 | 20/20 |
| Novelty-filtered, DB-matched drafts | 0/20 | 8/20 |
| Median generation time | 2.70 s | 2.05 s |
| Published | 0 | 0 |

Peak training memory reported by MLX: 3.344 GB on the 16 GB M5. The candidate
selected only three operations across 20 questions. The conservative lexical
novelty filter rejected 12 similar phrasings, including different factual scopes;
these are NOT 12 proven duplicate facts. Separate factual uniqueness from desired
linguistic diversity in a future reviewed policy revision.

The initial `adapter` / `lora-40` run also scored zero: the library chat template
inserted reasoning tags into training completions. Those original artifacts are
retained. `adapter-json` fixes token packing by appending exact JSON and EOS to the
same prompt tokens used at inference. A regression test covers the boundary.
The corrected run uses unchanged prompts, split, iterations and seeds, but this
is now an inspected development benchmark, not an untouched final holdout.

See [pilot review](../reports/local-generator-pilot-20260921.md) for the assistant's
wording review and limitations. No human approval or automatic deployment occurred.

## Continuation: 140 Cumulative Updates

The corrected adapter was continued for 100 additional updates on the same frozen
65-example training split. JSON/scope compliance stayed at 20/20, selected operation
types increased from three to five, and novelty-filtered DB-checked drafts fell
from eight to six. Validation loss rose from 0.497 to 0.681. The newer adapter is
not promoted; this does not establish an overall improvement. Both versions and
all raw outputs are retained. See the [continuation review](../reports/local-generator-continuation-140.md).

## Continuation: 240 Cumulative Updates

Another 100 updates from the 140-update weights completed on the same data.
JSON/scope compliance stayed at 20/20, with five selected operation types and four
novelty-filtered DB-matched query results. Validation loss was 0.587. Assistant
review found clear question/query mismatches, including a goal-count question
paired with an opponent query. This adapter is not promoted. See the
[240-update review and questions](../reports/local-generator-continuation-240.md).
