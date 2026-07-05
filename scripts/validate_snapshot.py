#!/usr/bin/env python3
"""
Validate generated Sleeper current snapshot files.

This validator is intentionally dependency-free and focused on current snapshot
integrity across required topic files and the ChatGPT bundle.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set


DEFAULT_CONFIG_PATH = Path("config/league_config.json")
REQUIRED_FILES = [
    "manifest.json",
    "league_context.json",
    "teams.json",
    "rosters.json",
    "matchups.json",
    "player_lookup_compact.json",
    "player_id_index.json",
    "chatgpt_bundle.json",
]


@dataclass
class Result:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, text: str) -> None:
        self.errors.append(text)

    def warning(self, text: str) -> None:
        self.warnings.append(text)


def as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def nested(payload: Any, keys: Sequence[str], default: Any = None) -> Any:
    value = payload
    for key in keys:
        if not isinstance(value, dict):
            return default
        value = value.get(key, default)
    return value


def read_json(path: Path, result: Result) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        result.error(f"Missing file: {path}")
    except json.JSONDecodeError as exc:
        result.error(f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}")
    except OSError as exc:
        result.error(f"Could not read {path}: {exc}")
    return None


def collect_ids_from_list(values: Any) -> Set[str]:
    if not isinstance(values, list):
        return set()
    return {text for text in (as_str(value) for value in values) if text}


def collect_roster_player_ids(rosters: Any) -> Set[str]:
    ids: Set[str] = set()
    if not isinstance(rosters, list):
        return ids
    for roster in rosters:
        if not isinstance(roster, dict):
            continue
        for key in ("players", "starters", "bench", "reserve", "taxi"):
            ids.update(collect_ids_from_list(roster.get(key)))
    return ids


def collect_matchup_player_ids(matchups: Any) -> Set[str]:
    ids: Set[str] = set()
    by_week = nested(matchups, ["by_week"], {})
    if not isinstance(by_week, dict):
        return ids
    for week_payload in by_week.values():
        if not isinstance(week_payload, dict):
            continue
        for result in week_payload.get("roster_results", []):
            if not isinstance(result, dict):
                continue
            for key in ("players", "starters", "bench"):
                ids.update(collect_ids_from_list(result.get(key)))
            for key in ("players_points", "starters_points"):
                point_map = result.get(key)
                if isinstance(point_map, dict):
                    ids.update(str(player_id) for player_id in point_map.keys())
    return ids


def validate(config_path: Path, snapshot_dir_override: Optional[Path]) -> Result:
    result = Result()
    config = read_json(config_path, result)
    if not isinstance(config, dict):
        result.error(f"Config must be a JSON object: {config_path}")
        return result

    snapshot_dir = snapshot_dir_override or Path(nested(config, ["snapshot", "output_dir"], "data/current"))
    loaded: Dict[str, Any] = {}
    for filename in REQUIRED_FILES:
        loaded[filename] = read_json(snapshot_dir / filename, result)

    expected_league_id = as_str(nested(config, ["league", "league_id"]))
    for label, value in [
        ("manifest.json league_id", nested(loaded["manifest.json"], ["league_id"])),
        ("league_context.json league_id", nested(loaded["league_context.json"], ["league_id"])),
        ("chatgpt_bundle.json metadata.league_id", nested(loaded["chatgpt_bundle.json"], ["metadata", "league_id"])),
        ("chatgpt_bundle.json league.league_id", nested(loaded["chatgpt_bundle.json"], ["league", "league_id"])),
    ]:
        if as_str(value) != expected_league_id:
            result.error(f"{label} mismatch: expected {expected_league_id!r}, got {as_str(value)!r}")

    manifest = loaded["manifest.json"]
    if isinstance(manifest, dict):
        for key in ("schema_version", "generated_at", "league_id", "included_weeks", "files", "counts", "data_quality"):
            if key not in manifest:
                result.error(f"manifest.json missing key: {key}")
        if nested(manifest, ["data_quality", "errors"], []):
            result.error(f"manifest.json data_quality.errors is not empty: {nested(manifest, ['data_quality', 'errors'])}")
    else:
        result.error("manifest.json must be an object")

    teams = loaded["teams.json"]
    rosters = loaded["rosters.json"]
    team_roster_ids = {as_str(team.get("roster_id")) for team in teams if isinstance(team, dict)} if isinstance(teams, list) else set()
    roster_ids = {as_str(roster.get("roster_id")) for roster in rosters if isinstance(roster, dict)} if isinstance(rosters, list) else set()
    team_roster_ids.discard(None)
    roster_ids.discard(None)

    if not isinstance(teams, list):
        result.error("teams.json must be a list")
    if not isinstance(rosters, list):
        result.error("rosters.json must be a list")
    if roster_ids and team_roster_ids and roster_ids != team_roster_ids:
        result.error(f"Roster/team ID mismatch: teams={sorted(team_roster_ids)}, rosters={sorted(roster_ids)}")

    if isinstance(rosters, list):
        for roster in rosters:
            if not isinstance(roster, dict):
                result.error("rosters.json contains a non-object item")
                continue
            roster_id = as_str(roster.get("roster_id"))
            for key in ("players", "starters", "bench", "reserve", "taxi"):
                if not isinstance(roster.get(key), list):
                    result.error(f"Roster {roster_id} field {key} must be a list")

    matchups = loaded["matchups.json"]
    if isinstance(matchups, dict):
        if not isinstance(matchups.get("included_weeks"), list):
            result.error("matchups.json included_weeks must be a list")
        by_week = matchups.get("by_week")
        if not isinstance(by_week, dict):
            result.error("matchups.json by_week must be an object")
        else:
            for week, week_payload in by_week.items():
                if not isinstance(week_payload, dict):
                    result.error(f"matchups.json week {week} must be an object")
                    continue
                for key in ("matchups", "roster_results", "counts"):
                    if key not in week_payload:
                        result.error(f"matchups.json week {week} missing {key}")
    else:
        result.error("matchups.json must be an object")

    referenced_player_ids = collect_roster_player_ids(rosters) | collect_matchup_player_ids(matchups)
    player_lookup = loaded["player_lookup_compact.json"]
    if isinstance(player_lookup, dict):
        missing_ids = sorted(referenced_player_ids - set(str(player_id) for player_id in player_lookup.keys()))
        if missing_ids:
            result.error(f"Referenced player IDs missing from player_lookup_compact.json: {missing_ids}")
        for key, player in player_lookup.items():
            if not isinstance(player, dict):
                result.error(f"Player lookup entry {key} must be an object")
            elif as_str(player.get("player_id")) != str(key):
                result.error(f"Player lookup key/player_id mismatch for {key}")
    else:
        result.error("player_lookup_compact.json must be an object")

    bundle = loaded["chatgpt_bundle.json"]
    if isinstance(bundle, dict):
        for key in ("metadata", "league", "teams", "rosters", "players", "matchups", "transactions", "drafts", "traded_picks", "analysis_indexes"):
            if key not in bundle:
                result.error(f"chatgpt_bundle.json missing key: {key}")
        bundle_player_lookup = nested(bundle, ["players", "by_id"], {})
        if isinstance(bundle_player_lookup, dict):
            missing_bundle_ids = sorted(referenced_player_ids - set(str(player_id) for player_id in bundle_player_lookup.keys()))
            if missing_bundle_ids:
                result.error(f"Referenced player IDs missing from chatgpt_bundle players.by_id: {missing_bundle_ids}")
        else:
            result.error("chatgpt_bundle.json players.by_id must be an object")
        if nested(bundle, ["matchups", "counts"]) != nested(matchups, ["counts"]):
            result.warning("chatgpt_bundle.json matchups.counts differs from matchups.json")
    else:
        result.error("chatgpt_bundle.json must be an object")

    counts = nested(manifest, ["counts"], {})
    if isinstance(counts, dict):
        comparisons = [
            ("rosters", len(rosters) if isinstance(rosters, list) else None),
            ("compact_player_lookup", len(player_lookup) if isinstance(player_lookup, dict) else None),
            ("matchups", nested(matchups, ["counts", "matchups"])),
            ("matchup_roster_results", nested(matchups, ["counts", "roster_results"])),
        ]
        for key, expected in comparisons:
            if expected is not None and counts.get(key) != expected:
                result.warning(f"manifest.json counts.{key} mismatch: expected {expected}, got {counts.get(key)}")
    else:
        result.error("manifest.json counts must be an object")

    return result


def print_result(result: Result) -> None:
    print("Snapshot validation passed." if result.ok else "Snapshot validation failed.")
    if result.errors:
        print("\nErrors:")
        for error in result.errors:
            print(f"- {error}")
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    print(f"\nSummary: {len(result.errors)} error(s), {len(result.warnings)} warning(s)")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated Sleeper current snapshot files.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help=f"Path to config JSON. Default: {DEFAULT_CONFIG_PATH}")
    parser.add_argument("--snapshot-dir", default=None, help="Override generated snapshot directory.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    snapshot_dir = Path(args.snapshot_dir) if args.snapshot_dir else None
    result = validate(Path(args.config), snapshot_dir)
    print_result(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
