# Sleeper Fantasy Football Snapshot Exporter

This repository stores the latest current-state snapshot of a Sleeper fantasy football league in a format that is efficient for ChatGPT to read and analyze.

## League

- Sleeper League ID: `1312581067286282240`
- Sport: `nfl`
- Snapshot mode: current-only

## Design principles

1. Keep the repository focused on the latest usable league snapshot.
2. Overwrite files in `data/current/` on each pull instead of keeping dated snapshot folders.
3. Commit compact, analysis-ready JSON files.
4. Do not commit large raw API responses.
5. Cache the full Sleeper NFL player database outside version control.
6. Preserve enough IDs and indexes for accurate analysis without duplicating full objects everywhere.
7. Start most ChatGPT analysis from the compact summary, then open topic files only when needed.

## Output files

Generated files are written to:

```text
data/current/
├─ manifest.json
├─ league_context.json
├─ teams.json
├─ rosters.json
├─ matchups.json
├─ transactions.json
├─ drafts.json
├─ traded_picks.json
├─ player_lookup_compact.json
├─ player_id_index.json
├─ chatgpt_summary.json
└─ chatgpt_bundle.json
```

Recommended read order for analysis:

1. `data/current/chatgpt_summary.json`
2. relevant split topic file, such as `rosters.json`, `transactions.json`, or `drafts.json`
3. `data/current/chatgpt_bundle.json` only when broad all-in-one context is needed

The split topic files exist so specific analysis can be done without reading the full bundle every time.

## What is not committed

Large or raw files are intentionally excluded from Git:

```text
raw_cache/
data/tmp/
*.raw.json
players_nfl_full.json
```

The full Sleeper players endpoint is used as a local/cache source for compact player lookups, not as a committed data file.

## Run locally

Run the full exporter, finalizer, summary builder, and validator pipeline:

```bash
python scripts/run_all.py
```

Force a refresh of the local Sleeper NFL player cache:

```bash
python scripts/run_all.py --force-refresh-players
```

Run exporters, finalization, and summary only, then skip validation:

```bash
python scripts/run_all.py --skip-validation
```

## Run individual steps

```bash
python scripts/sleeper_snapshot.py
python scripts/sleeper_transactions.py
python scripts/sleeper_drafts.py
python scripts/finalize_snapshot.py
python scripts/build_summary.py
python scripts/validate_snapshot.py
python scripts/validate_transactions.py
python scripts/validate_drafts.py
```

## GitHub Actions

The workflow is defined at:

```text
.github/workflows/sleeper_snapshot.yml
```

It supports:

- manual `workflow_dispatch`
- daily scheduled runs
- optional manual player-cache refresh
- automatic commit of changed files under `data/current/`

The workflow uses `scripts/run_all.py` so local and automated runs follow the same sequence.

## Current build status

Implemented:

- foundation documentation/configuration
- base current snapshot exporter
- matchup export
- transaction extension
- draft and traded-pick extension
- final snapshot cleanup/finalization
- compact ChatGPT summary output
- validators
- one-command local runner
- GitHub Actions workflow

Next step: run the workflow again after the summary-builder change, then use `data/current/chatgpt_summary.json` as the first file for league analysis.
