# Data Schema

This document defines the intended current-snapshot data model for the Sleeper Fantasy Football Snapshot Exporter.

## Scope

The exporter is intended to create the latest current-state snapshot of Sleeper league `1312581067286282240`.

Each run overwrites the generated files in `data/current/`. Prior script runs are not intentionally retained in the working tree.

## Source API areas

The exporter is expected to use these Sleeper API data areas:

- NFL state
- League metadata
- League users
- League rosters
- Weekly matchups
- Weekly transactions
- Winners playoff bracket
- Losers playoff bracket
- League traded future picks
- League drafts
- Draft picks
- Draft traded picks
- Full NFL player database as a cache source only
- Optional trending adds/drops

## Generated files

### `data/current/manifest.json`

Purpose: summarize freshness, completeness, file outputs, and data quality.

Expected top-level structure:

```json
{
  "schema_version": "1.0.0",
  "generated_at": "ISO-8601 timestamp",
  "league_id": "1312581067286282240",
  "sport": "nfl",
  "season": "string",
  "season_type": "regular",
  "nfl_state": {},
  "included_weeks": [],
  "files": [],
  "counts": {},
  "data_quality": {
    "warnings": [],
    "errors": [],
    "missing_player_ids": []
  }
}
```

### `data/current/league_context.json`

Purpose: preserve league configuration needed for scoring and roster analysis.

Expected content:

- league ID
- league name
- season
- status
- total rosters
- roster positions
- league settings
- scoring settings
- playoff settings when available
- draft ID when available

### `data/current/teams.json`

Purpose: normalize users and rosters into team-level records.

Expected content per team:

- roster ID
- owner user ID
- owner display name
- Sleeper username
- team name from user metadata when available
- co-owner or metadata notes when available
- wins, losses, ties
- fantasy points for and against
- waiver position
- FAAB / waiver budget usage when available
- total moves

### `data/current/rosters.json`

Purpose: describe current roster construction without duplicating full player objects.

Expected content per roster:

- roster ID
- owner user ID
- starters as player IDs
- bench as player IDs
- all players as player IDs
- reserve / IR as player IDs
- taxi as player IDs when available
- metadata/settings retained where useful
- optional display names for readability

Full player details should be resolved through `player_lookup_compact.json`.

### `data/current/matchups.json`

Purpose: preserve season-to-date matchup records by week.

Expected content:

- week
- matchup ID
- roster IDs involved
- starters
- bench inferred from players minus starters
- points
- custom points
- player point maps when available
- starter point maps when available

### `data/current/transactions.json`

Purpose: preserve season-to-date movement of players, picks, and FAAB.

Expected content:

- week / leg
- transaction ID
- type
- status
- created timestamp
- updated timestamp
- roster IDs involved
- adds
- drops
- draft picks included in transaction
- waiver budget movement
- creator user ID
- consenter roster IDs
- normalized summaries for trades, waivers, and free-agent moves

### `data/current/drafts.json`

Purpose: preserve league draft context and picks.

Expected content:

- draft metadata
- draft settings
- draft order
- slot-to-roster mappings when available
- picks by round
- picks by roster
- keeper flags when available
- draft traded picks

### `data/current/traded_picks.json`

Purpose: preserve current future-pick ownership.

Expected content:

- season
- round
- original roster ID
- previous owner roster ID
- current owner roster ID
- normalized display labels for teams

### `data/current/player_lookup_compact.json`

Purpose: provide a compact player-ID lookup for every player/team defense referenced in the current snapshot.

Expected object shape:

```json
{
  "player_id": {
    "player_id": "string",
    "name": "string",
    "first_name": "string",
    "last_name": "string",
    "team": "string",
    "position": "string",
    "fantasy_positions": [],
    "status": "string",
    "injury_status": "string or null",
    "years_exp": 0,
    "age": 0,
    "depth_chart_position": 0,
    "search_rank": 0
  }
}
```

Do not commit the full `/players/nfl` response.

### `data/current/player_id_index.json`

Purpose: make player lookup faster and easier to inspect.

Expected content:

- cache metadata
- count of required player IDs
- count of resolved player IDs
- missing player IDs
- index by normalized player name
- index by team
- index by position

### `data/current/chatgpt_bundle.json`

Purpose: all-in-one file optimized for direct ChatGPT analysis.

Expected top-level structure:

```json
{
  "metadata": {},
  "league": {},
  "teams": [],
  "rosters": [],
  "players": {
    "by_id": {}
  },
  "matchups": {
    "by_week": {}
  },
  "transactions": {
    "by_week": {},
    "trades": [],
    "waivers": [],
    "free_agent_moves": []
  },
  "drafts": [],
  "traded_picks": [],
  "analysis_indexes": {}
}
```

## Player ID strategy

The exporter should first collect all player IDs referenced by league data, then resolve only those IDs through the cached full player database.

Required player IDs should be gathered from:

- roster players
- roster starters
- reserve / IR
- taxi
- matchup players
- matchup starters
- matchup point maps
- transaction adds
- transaction drops
- draft picks
- traded picks where player IDs appear
- optional trending players

## Excluded player fields

The compact committed player lookup should exclude data that adds size without improving league analysis:

- birth date
- high school
- hometown
- physical attributes
- athletic testing
- headshots and visuals
- avatars and media

## Current-only policy

The repository should not keep date-stamped data folders by default.

The generated files in `data/current/` should be overwritten each time the exporter runs. This keeps the working tree focused on the latest usable league state.

Important note: even overwritten committed files remain in Git history, so generated files should remain compact.
