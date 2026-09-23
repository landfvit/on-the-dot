# Local Metric Model

For the separate generative language-model pilot, see [Local Generator](LOCAL_GENERATOR.md).
The model described below remains a metric classifier, not a question generator.

Private workspace: `http://127.0.0.1:8002/internal/trivia`, **Training** tab.
No external LLM calls, no provider imports, no automatic deployment.

Historical kit colours and weather are now supported as structured editor
questions/filters; see [CONTEXT.md](CONTEXT.md). New training labels exist, but old
pilot annotations and trained classes are intentionally unchanged.

## Annotation Workflow

1. Review a pilot draft, create a new example, or copy a failed query from the inbox.
2. Identify the exact metric phrase occurring once in the original query. Label
   that phrase, not the entire query. Unsupported/ambiguous labels need a reason.
3. Assign a paraphrase family and train/validation/test split. Related phrases
   belong in the same family. A family cannot cross splits.
4. Save a draft, then explicitly confirm the human-verification checkbox and
   click Verify annotation. Unsaved changes cannot be verified.
5. Run the local training command. Refresh Training to inspect the experiment.

The original text is immutable; corrections to its annotation create revisions.
Editing a verified example creates an unverified revision and excludes that
example from subsequent training until the latest revision is reviewed.
Review attribution comes from authenticated editor credentials, never JSON input.
The current app has one editor account; this is not a two-person approval system.

The 12 pilot drafts are synthetic and intentionally small, covering win_rate,
total_goals and unsupported phrases. They are NOT verified training data. Even
after review, this toy corpus does not establish production readiness. Extend it
with real language, different entities, negations and unsupported constructions.
Pilot sentences share a wrapper, which is excluded from classifier features;
only the reviewed metric phrase is used. Full-query models need different splits
and labels including roles, time and filters.

## Training and Storage

From the repository root:

```sh
.venv/bin/python src/trivia_migrate.py
.venv/bin/python src/query_training_pilot.py
.venv/bin/python src/train_query_model.py
```

The pilot command is optional and idempotent; it never verifies examples.
The training process runs locally on CPU with the installed scikit-learn version.
It does not run inside an HTTP request, start a cloud machine or download weights.
No reviewed data means an explicit error and no model, not automatic labelling.

The baseline uses character TF-IDF (2-5 grams) and balanced logistic regression.
At least two labels are needed. Each label needs two training families, one
validation family and one test family. These are mechanical minimums, not a
statistical guarantee. Vocabulary and IDF are fitted on TRAIN ONLY. Hyperparameters
are fixed; neither validation nor test data are fitted or used to select a winner.

Training refuses conflicting/exact/near-duplicate phrases crossing splits and
duplicate phrases assigned to different families. Exact duplicates within one
family/split are counted once during fitting/evaluation. The heuristic cannot
detect every paraphrase: human family review remains essential.

Each run freezes reviewed annotation IDs, revisions, text, labels, family/split,
reviewer and review time in PostgreSQL, with a deterministic dataset hash.
It stores the model, feature vocabulary, coefficients, artifact hash, manifest,
split-family list, class-level precision/recall/F1, confusion matrices and held-out
predictions. Reports compare with a simple exact-metric-dictionary baseline; that
baseline is not the full Sports Query parser. Accuracy is metric-phrase accuracy.

Local exports go to `data/private/query-models/<model-id>/`:

- `artifact.json`: vocabulary, IDF and classifier weights, no executable pickle.
- `manifest.json`: configuration, dependency/version information and hashes.
- `report.json`: validation/test outcomes and limitations.

The private directory is ignored by Git. Files are owner-readable/writable only.
The database registry is authoritative; exports are secondary copies. If export
fails after registration, the model still exists in the private registry.
Do not publish these artifacts: vocabularies can retain tokens from input phrases.

## Testing a Model

Training shows registered experiments and evaluation reports. Select a model and
test a metric phrase. Output is labelled `suggestion_only`, with uncalibrated
class scores and `executable: false`. No-feature input has no prediction.

The readable result compares the suggestion with exact phrase rules and marks
metrics missing from the trained classes. Scores are not calibrated confidence.
Nearest phrases show character TF-IDF cosine similarity to the frozen TRAIN
corpus only, not a causal explanation or evidence of football correctness.
An exact training-phrase match is explicitly marked as non-independent.
Evaluation lists each frozen validation/test phrase, its expected and predicted
labels, and correct/total counts. Technical JSON remains expandable. Refreshing
this view or testing a phrase does not train, deploy or alter any annotation.

Next, collect diverse independently reviewed training families for the desired
metrics, including realistic unsupported inputs. Do not move inspected validation
or test mistakes into training. Repeated inspection makes these sets development
benchmarks; reserve fresh independent families for a future final evaluation.
Use Sports Query for actual deterministic football answers; this pilot only
classifies metric phrases and does not yet interpret full questions.

Models are NOT connected to `/api/query/parse` or `/api/query/evaluate`, cannot
produce SQL, and cannot publish questions. A full-query model, calibrated rejection
threshold, independent evaluation and explicit deployment approval are separate
future work. New sports results do not trigger retraining.

## Access and Retention

Annotation/inbox/model APIs are private and use existing same-origin editor
authentication. No automatic harvesting of successful user queries is added.
Copying an inbox item is explicit and creates no training record until saved.
Avoid personal or sensitive information in examples. Input phrases may contain
arbitrary text; the app does not claim to automatically redact secrets.

Annotations and model runs are immutable audit records. Retention/erasure is
currently an administrative database procedure, not implemented as a public API.
Before multi-user/public collection, implement user information, retention,
redaction and dataset/model withdrawal for removed examples.

Tests perform actual CPU fitting on explicitly synthetic fixtures and roll back
database writes. They do not certify the pilot drafts as human-verified.
