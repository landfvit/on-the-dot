# Pixel Kits

Deterministic pixel illustrations built from sourced colors and patterns. No AI
fabric renders are used by the website.

## Build the Website Assets

```sh
.venv/bin/python -m kits.main --season 2026
.venv/bin/python -m kits.main --season 2026 --team-id 33
.venv/bin/python -m kits.main --all-seasons
.venv/bin/python -m kits.audit --season 2026
.venv/bin/python src/kit_coverage_audit.py
```

The build reads `data/enrichment/team_kits.json`, which keeps exact seasons and
permanent Wikimedia Commons source revisions. PNG layers are cached in
`data/kits/source_cache`. Their original coordinates, RGB colors and alpha are
composited without interpolation, then equal pixel runs are merged into SVG
rectangles. PNG exports use nearest-neighbor scaling.

The offline audit reconstructs every SVG rectangle and compares all pixels with
the cached source composition, then verifies the full-resolution PNG export.

Outputs live in `web/static/kits/<season>/<team_id>/`. The atomic manifest in
`data/kits/catalog.json` records a hash of every source layer definition. The API
serves a local render only when it matches the requested season and current source
signature. Missing or changed assets fall back to the original source layers;
missing kits remain unavailable. A third kit is never inferred from a home kit.
Historical source layers use the same responsive pixel scale even before a local
export is built. The source importer checks club coverage against each season's
fixture participants and ignores hidden layout spacers in Commons kit labels.
The coverage audit reports fixture counts, missing or unexpected clubs, and
unavailable individual sets separately from the local-export pixel audit.

The UI links to the original file pages for creator/license information. Every
SVG also includes these URLs in its metadata. These are sourced illustrations,
not official product photography. Historical club colors alone do not establish
the colors of a particular season's away or third kit.

## Historical Colour Audit

`src/kit_colour_report.py` discovers the Commons Premier League gallery category,
caches source revisions, handles both club-first and kit-type-first layouts, and
exports `reports/kits/pl_kit_colours.md`, `.csv` and `.json`. `--offline` reuses
cached gallery pages and the original local season catalogue. `--download-limit N`
opts into a bounded number of missing shirt-body downloads. Requests stop on a
provider error/rate limit; cached assets remain available. Base colours alone are
not promoted to verified dominant colours. Explicit source-backed roster corrections
live in `data/kits/research/roster_corrections.json` and never supply kit colours.

Colour combinations use the versioned policy documented in `trivia_app/CONTEXT.md`.
Missing third sets mean not listed in this source, not necessarily nonexistent.

## Interactive Wikipedia Import

The existing `python kits/main.py` flow remains available. It reads the current
club infobox and writes to `data/kits/rendered/<team>/`. It is deliberately NOT
published automatically because a current infobox does not prove a historical
season. Bases retain their white exterior masks; requested missing patterns or
invalid colors fail explicitly instead of producing an inaccurate white kit.

## Player Coverage

`src/current_squads_import.py --season 2026` imports `/players/squads` only after
the provider confirms that the requested season is current. It preserves prior
season memberships and does not manufacture statistical records. Its report is
`data/audits/squad_integrity_2026.json`; missing values that the provider cannot
supply remain explicitly unavailable.
