# Sleeper Fantasy Football Snapshot Exporter

This repository is designed to store the latest current-state snapshot of a Sleeper fantasy football league in a format that is efficient for ChatGPT to read and analyze.

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

## Intended output files

Generated files will eventually be written to:

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

The primary ChatGPT-facing file will be:

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

## Build status

Current phase: repository foundation.

No data-pull script has been added yet. See `docs/BUILD_PLAN.md` for the incremental build sequence.