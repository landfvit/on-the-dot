# Imported Question Bank

Private editor page: `/internal/trivia/bank` (same editor login as Studio).

The supplied bank is imported unchanged with one canonical reference answer per
question. Its answers are **user-attested**, not automatically human-reviewed
database facts. Import does not publish questions to ranked games or alter any
provider football records, previous query annotations or deployed query model.

The owner subsequently authorized the supplied reference answers for unranked
penalties. A separate immutable penalty release now serves these questions in
General, club and mixed packs. This does not relabel unverified answers as
database-verified or change the audit. Future bank imports do not auto-publish.

## Validation

- `matched`: the deterministic calculation agrees with the reference answer.
- `conflict`: a computed value or a checked factual premise disagrees.
- `incomplete`: required seasons, final standings, player identity or scorer
  coverage are unavailable. Partial totals are never compared as full answers.
- `ambiguous`: tied/non-unique result, empty denominator, or a reference player
  name absent from the registered aliases. A nickname difference is not proof of
  a wrong football fact.
- `unsupported`: wording or fact type needs source/editorial review. This currently
  includes kit manufacturers, sponsorship, captaincy, management and assists.

All input questions are checked. Unsupported ones remain visible, not silently
omitted. The current evaluator recognizes exact approved English templates;
arbitrary paraphrases abstain. It never uses the supplied answer or check note as
calculation input. Player goals exclude own goals and require complete scorer
quality for the selected fixtures. Final-table opponent groups use stored final
positions, while points earned are calculated as `3W+D` before deductions.

Each checked season requires 20 teams, 380 fixtures, two consistent perspectives
per fixture, complete home/away pairings, and valid results. Percentages use
decimal half-up rounding. `only`/`most` questions reject ties. Multi-season queries
never silently drop missing seasons. Full-season audits and supporting fixture
IDs are retained; supporting scope includes non-matching fixtures.

Imports are SHA-256 deduplicated. Questions, validation runs, model runs and
drafts are append-only. Each audit pins the immutable football dataset plus a
copy/hash of the standings and a validator source hash. New imports or audits
never overwrite earlier evidence. Sources are preserved as citations, but the
importer does **not** independently visit or certify every referenced website.

## Local Authoring Model

Training runs on this machine with scikit-learn: TF-IDF + logistic regression,
plus similar-question retrieval. All 1,950 **question texts and topic labels**
are used for the final suggestion artifact. Answers are not model inputs or
training targets. Conflicting/unverified answers therefore cannot become learned
football facts. The original metric-phrase classifier is left untouched.

This is **not generative LLM fine-tuning** and does not establish open-ended
question understanding. The model suggests topics and existing question patterns.
In **New question**, enter a question or select an example, edit the club/season,
then **Check question**. A strict deterministic evaluator computes the answer;
the model cannot write SQL or authorize a result. **Save draft** recalculates on
the server and is available only for a complete, unique answer. Drafts remain
private and are listed below the authoring form. Unsupported wording shows
example questions rather than inventing an answer.

Club, season and number variants share a family; templates with >=90% character
similarity are grouped transitively. Entire families are held out for validation
and testing. The reported accuracy is **topic classification only**, not answer
accuracy. Rare topics can be absent from training or evaluation, explicitly
recorded in the model report. After evaluation, a separate suggestion artifact
is refit on all texts. The complete split assignments and predictions are stored
in PostgreSQL. No external model/API calls, paid training or cloud upload occur.

## Commands

```sh
.venv/bin/python -m src.trivia_migrate
.venv/bin/python -m src.import_trivia_bank /absolute/path/questions.md --train
.venv/bin/python -m unittest discover -s tests -p 'test_trivia_bank.py' -v
TRIVIA_DB_TEST=1 .venv/bin/python -m unittest discover -s tests -p 'test_trivia_bank_database.py' -v
```

The import command creates a new audit, even when reusing a content-identical
batch. `--train` registers a new local authoring model tied to that audit.
Reports are written to `reports/trivia-bank/<validation-run-id>/` as JSON, CSV and
Markdown. Database integration tests require the imported bank and editor
credentials; writes are rolled back. Tests include 100 synthetic count scenarios,
all-bank recalculation, deliberate answer disagreement, missing coverage, ties,
rounding, aliases, split leakage, access control and immutability.
