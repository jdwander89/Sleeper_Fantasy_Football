# Build Plan

This project should be built incrementally. Accuracy and inspectability are higher priorities than speed of initial development.

## Phase 0: Foundation

Status: complete

Created repository documentation and configuration:

- `README.md`
- `.gitignore`
- `config/league_config.json`
- `docs/DATA_SCHEMA.md`
- `docs/BUILD_PLAN.md`

## Phase 1: Minimal snapshot script

Status: implemented; first real snapshot run and review still pending

Created `scripts/sleeper_snapshot.py`.

Implemented scope:

- read `config/league_config.json`
- fetch NFL state
- fetch league metadata
- fetch league users
- fetch rosters
- collect required player IDs from rosters
- cache full Sleeper NFL player database locally if missing or stale
- emit compact player lookup for referenced players
- write core current snapshot files under `data/current/`

Manual command:

```bash
python scripts/sleeper_snapshot.py
```

## Phase 2: Validation script

Status: implemented; first validation run still pending

Created `scripts/validate_snapshot.py`.

Validation checks:

- required core files exist
- JSON files parse correctly
- league ID matches config
- each roster has a roster ID
- each roster has a matching team record
- each referenced roster or matchup player ID exists in `player_lookup_compact.json`
- `matchups.json` has the expected structure
- `chatgpt_bundle.json` matches topic-file roster, matchup, and player references
- manifest counts match generated files where applicable

Manual command:

```bash
python scripts/validate_snapshot.py
```

## Phase 3: Matchups

Status: implemented; first real snapshot run and review still pending

Added season-to-date weekly matchup export to `scripts/sleeper_snapshot.py`.

Implemented logic:

- determine included weeks from NFL state with config fallback
- fetch matchups for each included week
- group teams by matchup ID
- infer matchup bench as players minus starters
- preserve player point maps and starter point maps when available
- collect required player IDs from matchup players and point maps before compact player lookup is generated
- write `data/current/matchups.json`
- add matchup summaries to `data/current/chatgpt_bundle.json`
- include matchup counts and included weeks in `data/current/manifest.json`

## Phase 4: Transactions

Status: implemented as a post-snapshot extension; first real run and review still pending

Created:

- `scripts/sleeper_transactions.py`
- `scripts/validate_transactions.py`

Implemented logic:

- read `data/current/manifest.json` to reuse included weeks
- fetch transactions for each included week
- normalize trades, waivers, free-agent moves, commissioner moves, waiver budget, and draft-pick movement embedded in transactions
- collect player IDs from adds and drops
- use the same local full-player cache strategy to resolve newly referenced transaction players
- write `data/current/transactions.json`
- update `data/current/player_lookup_compact.json`
- update `data/current/chatgpt_bundle.json`
- update transaction counts in `data/current/manifest.json`

## Phase 5: Drafts and traded picks

Status: implemented as a post-snapshot extension; first real run and review still pending

Created:

- `scripts/sleeper_drafts.py`
- `scripts/validate_drafts.py`

Implemented logic:

- fetch all league drafts
- fetch each draft's picks
- fetch each draft's traded picks
- fetch league traded future picks
- normalize draft assets by roster/team label
- collect player IDs from draft picks
- use the same local full-player cache strategy to resolve newly referenced drafted players
- write `data/current/drafts.json`
- write `data/current/traded_picks.json`
- update `data/current/player_lookup_compact.json`
- update `data/current/chatgpt_bundle.json`
- update draft and traded-pick counts in `data/current/manifest.json`

Current full manual command sequence:

```bash
python scripts/sleeper_snapshot.py
python scripts/sleeper_transactions.py
python scripts/sleeper_drafts.py
python scripts/validate_snapshot.py
python scripts/validate_transactions.py
python scripts/validate_drafts.py
```

Validation goal: support dynasty, keeper, draft-result, pick-asset, and trade-value analysis.

## Phase 6: GitHub Actions workflow

Add `.github/workflows/sleeper_snapshot.yml`.

Recommended triggers:

- manual `workflow_dispatch`
- daily schedule around 6:17 AM Central

The workflow should:

- install Python
- run the snapshot script
- run the transaction extension
- run the draft/traded-pick extension
- validate the snapshot
- validate transactions
- validate drafts/traded picks
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
