# Kit Colours and Historical Weather

Both are available in Studio's **Editor**, without training a language model.
The Sports Query free-text grammar is still restricted to its existing result
metrics; these new context options are explicit structured editor fields.

## Frozen Sources

```sh
.venv/bin/python src/trivia_migrate.py
.venv/bin/python src/trivia_context_build.py
```

This freezes a new context snapshot against the latest sealed football dataset.
It reuses local Commons artwork and existing fixture_weather rows; it does not
import football results or call a weather API. Missing body patterns can be
downloaded for explicitly selected seasons only:

```sh
.venv/bin/python src/trivia_context_build.py --fetch-kit-seasons 2024
```

Years denote season starts, so 2024 is 2024/25. No season is hardcoded in the
question specification. Unchanged content reuses its previous context ID.
Download failures or rate limits stop further network requests for that run;
already cached artwork is retained and missing records remain unavailable.
Context payloads are immutable in PostgreSQL; their hashes, source URLs and
timestamps are retained. Every context question requires an explicit context_id
belonging to the selected football dataset. Old questions keep their own snapshot.
Kit evidence is stored in analysis.context_evidence, not as a fake football match.
Publication recomputes the answer and compares all analysis and match evidence.

## Kit Colour

Select **Kit shirt colour**, competition, team, exactly one selected season, and
Home / Away / Third. Match filters do not apply and the sample is one kit record.
The answer is a broad colour family of the **shirt body**, not shorts or socks.

The source body artwork is composited using its declared background colour.
Algorithm shirt-torso-colours-v1 counts colour families in the interior rectangle
(3,12)-(35,54) of the standard 38x59 Commons shirt body. This excludes the collar,
outline and exterior canvas. HSV boundaries define a deliberately coarse palette,
not an official manufacturer's colour name or a calibrated perceptual classifier.
At least 60% of pixels and a 20-percentage-point lead over the next family are
required. Otherwise the record is marked multicolour and publication is blocked.
Missing artwork is unavailable, never substituted from another season or set.

The result includes palette proportions, a swatch, source torso image and Commons
revision link. Artwork hashes and algorithm version are frozen. Clear algorithmic
dominance is not independent verification of the real product; the question
explicitly identifies its artwork basis. Change the method version if boundaries,
mask, colour aliases or thresholds change. Image filenames are content-addressed.
Answers accept English and Czech colour names, with accents normalized by the
existing text-answer grader. Kit identity must never imply it was worn in a
particular fixture; that would need a separately sourced match-kit assignment.

### Combined Colours

The current research export uses shirt-torso-colours-v3. It retains a single
colour when the original dominance test passes. Otherwise, two colours each need
at least 25% and a combined 75%; three each need at least 20% and a combined 85%.
Ambiguous blue/navy and black/grey/white tonal mixtures require review instead of
being promoted as a confident combination. Other unclassified cases remain blocked.
V2, retained only for reproducibility of its immutable experimental snapshot,
tested combinations before the single-colour rule. V1 and V2 remain available;
no saved question is migrated in place.

```sh
.venv/bin/python src/trivia_context_build.py --colour-version v3
.venv/bin/python src/kit_colour_report.py --offline
```

New combination answers have the frozen colour-set-v2 grading policy. All listed
colours are required, in either order, with English/Czech aliases and separators
`and`, `a`, `&`, `+`, comma or slash. Missing, extra and repeated colours fail.
Each component gets its own swatch. The MD/CSV/JSON report in `reports/kits/`
separates measured colours, unverified base-colour hints, absent sets and source
layout ambiguities. Galleries go back to 1999/2000 in the observed category,
but not every gallery has all club headings or all kits. Older reports are research
only and do not silently expand the football dataset's supported seasons.

### Validation And Bounded Imports

Run a small explicit download batch, then freeze the cached colours and validate:

```sh
.venv/bin/python src/kit_colour_report.py --download-limit 20 --download-delay 10
.venv/bin/python src/trivia_context_build.py --colour-version v3
.venv/bin/python src/validate_kit_colours.py
```

Downloads stop on the first HTTP failure; the report records the status and
Retry-After header. Respect that delay before a later manual batch. There is no
automatic retry loop or scheduled background import. Already cached images are
reused. `--offline` rebuilds reports without network requests.

`reports/kits/validation_100.md` and `.json` contain the actual outcome of each
of 100 named checks and a hash of the source report. They cover 28 seasonal
inventories, 13 solid colours, 12 two-colour patterns, 8 boundary cases, 24 answer
forms, 10 invalid query specifications and 5 import safeguards. The first run
found an uncorrected Tottenham spelling in 2008/09; its correction is retained
in the source-specific alias file and checked on subsequent runs.

This is engineering validation, not independent verification of 100 real kits.
Synthetic colours have explicit expected results; seasonal tests check integrity
and CSV/JSON consistency. Unknown kits remain unavailable, not validated facts.
The test runner does not publish questions, train a model or write to the DB.

## Weather Filters

Supported on team result metrics and conditional win rate: temperature (C) or
precipitation (mm), with an explicit gt/gte/lt/lte threshold. Selection takes place
after result/timeline quality checks; a missing weather row is excluded rather
than treated as zero, dry weather or a non-match. Any missing coverage blocks
publication. Opponent, venue, season and checkpoint conditions intersect.

Only ERA5 historical reanalysis in verified units is eligible. The frozen source
must match fixture kickoff and venue at build time; the sample must be within
30 minutes of kickoff. Temperature is the nearest hourly sample. Precipitation is
the TOTAL in the hour preceding that sample, including snow: it is not evidence
that rain fell during the match. Values are finite and range-checked. Match-level
evidence retains sampled time, source URL, model, coordinates and retrieval date.
Sources: [Open-Meteo historical API](https://open-meteo.com/en/docs/historical-weather-api).

The pre-existing importer can explicitly extend weather coverage; see
`src/match_context_import.py`. A new context snapshot must then be built. No
scheduled synchronization, cloud service or paid API is enabled here.

## Training Scope

New annotations may use kit_colour and historical_weather. Existing verified
annotations and model artifacts are not relabelled or retrained automatically.
The original pilot's shirt-colour example was labelled unsupported under its old
metric-only scope; that does not mean historical kit questions are unsupported
by the editor now. Review taxonomy changes as new annotation revisions, preserving
family splits. A future weather forecast remains different from historical data.
Probe diagnostics flag exact kit phrases as outside the old model's classes.
