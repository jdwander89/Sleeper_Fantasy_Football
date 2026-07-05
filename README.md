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
└─ chatgpt_bundle.json
```

The primary ChatGPT-facing file is:

```text
data/current/chatgpt_bundle.json
```

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

Run the full exporter, finalizer, and validator pipeline:

```bash
python scripts/run_all.py
```

Force a refresh of the local Sleeper NFL player cache:

```bash
python scripts/run_all.py --force-refresh-players
```

Run exporters and finalization only, then skip validation:

```bash
python scripts/run_all.py --skip-validation
```

## Run individual steps

```bash
python scripts/sleeper_snapshot.py
python scripts/sleeper_transactions.py
python scripts/sleeper_drafts.py
python scripts/finalize_snapshot.py
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
- validators
- one-command local runner
- GitHub Actions workflow

Next step: run the workflow again after the finalizer change, then review the refreshed `data/current/` files for file size, missing fields, player resolution, and ChatGPT readability.
