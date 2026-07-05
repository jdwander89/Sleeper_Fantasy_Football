# Build Plan

This project should be built incrementally. Accuracy and inspectability are higher priorities than speed of initial development.

## Phase 0: Foundation

Status: complete

Create repository documentation and configuration only.

Files:

- `README.md`
- `.gitignore`
- `config/league_config.json`
- `docs/DATA_SCHEMA.md`
- `docs/BUILD_PLAN.md`

No API calls yet.
No generated Sleeper data yet.
No GitHub Actions workflow yet.

## Phase 1: Minimal snapshot script

Status: initial implementation complete; first real snapshot run and review still pending

Created `scripts/sleeper_snapshot.py`.

Initial scope:

- read `config/league_config.json`
- fetch NFL state
- fetch league metadata
- fetch league users
- fetch rosters
- collect required player IDs from rosters
- cache full Sleeper NFL player database locally if missing or stale
- emit compact player lookup for rostered players
- write:
  - `data/current/manifest.json`
  - `data/current/league_context.json`
  - `data/current/teams.json`
  - `data/current/rosters.json`
  - `data/current/player_lookup_compact.json`
  - `data/current/player_id_index.json`
  - `data/current/chatgpt_bundle.json`

Validation goal: confirm that current teams, owners, rosters, and player names are accurate.

Manual command for local testing:

```bash
python scripts/sleeper_snapshot.py
```

Optional player-cache refresh:

```bash
python scripts/sleeper_snapshot.py --force-refresh-players
```

## Phase 2: Validation script

Create `scripts/validate_snapshot.py`.

Validation checks:

- required files exist
- JSON files parse correctly
- league ID matches config
- each roster has a roster ID
- each roster owner can be mapped to a user when available
- each referenced player ID is resolved or reported as missing
- manifest counts match generated files

## Phase 3: Matchups

Add season-to-date weekly matchup export.

Logic:

- determine included weeks from NFL state
- fetch matchups for each included week
- group teams by matchup ID
- infer bench as players minus starters
- preserve point maps when available
- add matchup summaries to bundle

Validation goal: enable weekly matchup previews and prior-week recaps.

## Phase 4: Transactions

Add season-to-date transaction export.

Logic:

- fetch transactions by week
- normalize trades, waivers, and free-agent moves
- collect player IDs from adds and drops
- collect draft-pick movement from transactions
- enrich summaries with team labels and player display names

Validation goal: enable trade, waiver, and roster-movement analysis.

## Phase 5: Drafts and traded picks

Add draft and pick context.

Logic:

- fetch all league drafts
- fetch each draft's picks
- fetch each draft's traded picks
- fetch league traded future picks
- normalize draft assets by roster

Validation goal: support dynasty, keeper, draft-result, and pick-value analysis.

## Phase 6: GitHub Actions workflow

Add `.github/workflows/sleeper_snapshot.yml`.

Recommended triggers:

- manual `workflow_dispatch`
- daily schedule around 6:17 AM Central

The workflow should:

- install Python
- run the snapshot script
- validate the snapshot
- commit changed files under `data/current/` when there are actual changes

## Phase 7: Refinement after first real snapshot

Review generated data for:

- file size
- missing fields
- missing player IDs
- unnecessary fields
- bundle readability
- analysis quality

Refine schema and script based on actual output.

## Non-goals for initial build

- date-stamped historical snapshots
- committing full raw Sleeper endpoint dumps
- hourly automation
- writing to Sleeper API
- storing secrets or API tokens
