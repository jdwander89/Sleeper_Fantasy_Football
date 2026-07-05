#!/usr/bin/env python3
"""
Validate generated Sleeper current snapshot files.

Phase 2 scope:
- Confirm required generated JSON files exist and parse.
- Confirm league IDs match config.
- Confirm teams, rosters, player lookup, indexes, and bundle are internally consistent.
- Report missing player IDs and malformed records before later phases add more data.

This script intentionally uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


DEFAULT_CONFIG_PATH = Path("config/league_config.json")
DEFAULT_REQUIRED_FILES = [
    "manifest.json",
    "league_context.json",
    "teams.json",
    "rosters.json",
    "player_lookup_compact.json",
    "player_id_index.json",
    "chatgpt_bundle.json",
]


JsonObject = Dict[str, Any]


@dataclass
class ValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors


def read_json(path: Path, result: ValidationResult) -> Any:
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


def get_nested(payload: Any, keys: Sequence[str], default: Any = None) -> Any:
    value = payload
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def require_type(
    payload: Any,
    expected_type: type,
    label: str,
    result: ValidationResult,
) -> bool:
    if not isinstance(payload, expected_type):
        result.error(f"{label} must be {expected_type.__name__}; got {type(payload).__name__}")
        return False
    return True


def load_config(config_path: Path, result: ValidationResult) -> Optional[JsonObject]:
    config = read_json(config_path, result)
    if config is None:
        return None
    if not require_type(config, dict, str(config_path), result):
        return None
    return config


def collect_roster_player_ids(rosters: Iterable[JsonObject]) -> Set[str]:
    player_ids: Set[str] = set()
    for roster in rosters:
        if not isinstance(roster, dict):
            continue
        for field_name in ("players", "starters", "bench", "reserve", "taxi"):
            values = roster.get(field_name)
            if isinstance(values, list):
                for value in values:
                    player_id = as_str(value)
                    if player_id:
                        player_ids.add(player_id)
    return player_ids


def validate_required_files(snapshot_dir: Path, result: ValidationResult) -> Dict[str, Any]:
    loaded: Dict[str, Any] = {}

    for filename in DEFAULT_REQUIRED_FILES:
        path = snapshot_dir / filename
        if not path.exists():
            result.error(f"Missing required snapshot file: {path}")
            continue
        loaded[filename] = read_json(path, result)

    return loaded


def validate_league_ids(config: JsonObject, loaded: Dict[str, Any], result: ValidationResult) -> None:
    expected_league_id = as_str(get_nested(config, ["league", "league_id"]))

    if not expected_league_id:
        result.error("config league.league_id is missing")
        return

    comparisons = [
        ("manifest.json league_id", get_nested(loaded.get("manifest.json"), ["league_id"])),
        ("league_context.json league_id", get_nested(loaded.get("league_context.json"), ["league_id"])),
        ("chatgpt_bundle.json metadata.league_id", get_nested(loaded.get("chatgpt_bundle.json"), ["metadata", "league_id"])),
        ("chatgpt_bundle.json league.league_id", get_nested(loaded.get("chatgpt_bundle.json"), ["league", "league_id"])),
    ]

    for label, actual in comparisons:
        actual_str = as_str(actual)
        if actual_str != expected_league_id:
            result.error(f"{label} mismatch: expected {expected_league_id!r}, got {actual_str!r}")


def validate_manifest(snapshot_dir: Path, loaded: Dict[str, Any], result: ValidationResult) -> None:
    manifest = loaded.get("manifest.json")
    if not require_type(manifest, dict, "manifest.json", result):
        return

    required_keys = ["schema_version", "generated_at", "league_id", "sport", "snapshot_mode", "files", "counts", "data_quality"]
    for key in required_keys:
        if key not in manifest:
            result.error(f"manifest.json missing required key: {key}")

    files = manifest.get("files")
    if isinstance(files, list):
        manifest_paths = {as_str(item.get("path")) for item in files if isinstance(item, dict)}
        for filename in DEFAULT_REQUIRED_FILES:
            expected_path = str(snapshot_dir / filename)
            if expected_path not in manifest_paths:
                result.warning(f"manifest.json files list does not include {expected_path}")
    else:
        result.error("manifest.json files must be a list")

    data_quality = manifest.get("data_quality")
    if isinstance(data_quality, dict):
        manifest_errors = data_quality.get("errors")
        if manifest_errors:
            result.error(f"manifest.json data_quality.errors is not empty: {manifest_errors}")
    else:
        result.error("manifest.json data_quality must be an object")


def validate_teams_and_rosters(loaded: Dict[str, Any], result: ValidationResult) -> Tuple[Set[str], Set[str]]:
    teams = loaded.get("teams.json")
    rosters = loaded.get("rosters.json")

    team_roster_ids: Set[str] = set()
    roster_ids: Set[str] = set()

    if require_type(teams, list, "teams.json", result):
        for index, team in enumerate(teams):
            if not isinstance(team, dict):
                result.error(f"teams.json item {index} must be an object")
                continue

            roster_id = as_str(team.get("roster_id"))
            if not roster_id:
                result.error(f"teams.json item {index} missing roster_id")
                continue

            if roster_id in team_roster_ids:
                result.error(f"Duplicate team roster_id in teams.json: {roster_id}")
            team_roster_ids.add(roster_id)

            if not team.get("display_label"):
                result.warning(f"Team roster_id {roster_id} has no display_label")

    if require_type(rosters, list, "rosters.json", result):
        for index, roster in enumerate(rosters):
            if not isinstance(roster, dict):
                result.error(f"rosters.json item {index} must be an object")
                continue

            roster_id = as_str(roster.get("roster_id"))
            if not roster_id:
                result.error(f"rosters.json item {index} missing roster_id")
                continue

            if roster_id in roster_ids:
                result.error(f"Duplicate roster_id in rosters.json: {roster_id}")
            roster_ids.add(roster_id)

            players = roster.get("players")
            starters = roster.get("starters")
            bench = roster.get("bench")
            reserve = roster.get("reserve")
            taxi = roster.get("taxi")

            for field_name, value in [
                ("players", players),
                ("starters", starters),
                ("bench", bench),
                ("reserve", reserve),
                ("taxi", taxi),
            ]:
                if not isinstance(value, list):
                    result.error(f"Roster {roster_id} field {field_name} must be a list")

            if isinstance(players, list) and isinstance(starters, list):
                player_set = {as_str(player_id) for player_id in players}
                starter_set = {as_str(player_id) for player_id in starters}
                missing_starters = sorted(pid for pid in starter_set - player_set if pid)
                if missing_starters:
                    result.warning(f"Roster {roster_id} has starters not listed in players: {missing_starters}")

            if isinstance(players, list) and isinstance(bench, list) and isinstance(starters, list):
                player_set = {as_str(player_id) for player_id in players if as_str(player_id)}
                grouped = set()
                for group in (starters, bench, reserve if isinstance(reserve, list) else [], taxi if isinstance(taxi, list) else []):
                    for player_id in group:
                        player_id_str = as_str(player_id)
                        if player_id_str:
                            grouped.add(player_id_str)

                ungrouped = sorted(player_set - grouped)
                if ungrouped:
                    result.warning(f"Roster {roster_id} has players not classified as starter/bench/reserve/taxi: {ungrouped}")

    if team_roster_ids and roster_ids:
        missing_teams = sorted(roster_ids - team_roster_ids)
        extra_teams = sorted(team_roster_ids - roster_ids)
        if missing_teams:
            result.error(f"Rosters without matching teams: {missing_teams}")
        if extra_teams:
            result.error(f"Teams without matching rosters: {extra_teams}")

    return team_roster_ids, roster_ids


def validate_players(loaded: Dict[str, Any], result: ValidationResult) -> Set[str]:
    rosters = loaded.get("rosters.json")
    player_lookup = loaded.get("player_lookup_compact.json")
    player_id_index = loaded.get("player_id_index.json")

    referenced_ids = collect_roster_player_ids(rosters if isinstance(rosters, list) else [])

    if not require_type(player_lookup, dict, "player_lookup_compact.json", result):
        return referenced_ids

    lookup_ids = set(str(player_id) for player_id in player_lookup.keys())

    missing_from_lookup = sorted(referenced_ids - lookup_ids)
    if missing_from_lookup:
        result.error(f"Referenced roster player IDs missing from player_lookup_compact.json: {missing_from_lookup}")

    empty_names = []
    for player_id, player in player_lookup.items():
        if not isinstance(player, dict):
            result.error(f"player_lookup_compact.json player {player_id} must be an object")
            continue

        if as_str(player.get("player_id")) != str(player_id):
            result.error(f"player_lookup_compact.json key/player_id mismatch for key {player_id}")

        if not as_str(player.get("name")):
            empty_names.append(str(player_id))

    if empty_names:
        result.warning(f"Player lookup entries without names: {empty_names}")

    if require_type(player_id_index, dict, "player_id_index.json", result):
        counts = player_id_index.get("counts")
        if isinstance(counts, dict):
            expected_required = len(referenced_ids)
            actual_required = counts.get("required_player_ids")
            if actual_required != expected_required:
                result.warning(
                    "player_id_index.json counts.required_player_ids mismatch: "
                    f"expected {expected_required}, got {actual_required}"
                )
        else:
            result.error("player_id_index.json counts must be an object")

        missing_ids = player_id_index.get("missing_ids")
        if not isinstance(missing_ids, list):
            result.error("player_id_index.json missing_ids must be a list")

    return referenced_ids


def validate_chatgpt_bundle(
    loaded: Dict[str, Any],
    roster_ids: Set[str],
    referenced_player_ids: Set[str],
    result: ValidationResult,
) -> None:
    bundle = loaded.get("chatgpt_bundle.json")
    if not require_type(bundle, dict, "chatgpt_bundle.json", result):
        return

    for key in ["metadata", "league", "teams", "rosters", "players", "matchups", "transactions", "drafts", "traded_picks", "analysis_indexes"]:
        if key not in bundle:
            result.error(f"chatgpt_bundle.json missing top-level key: {key}")

    bundle_teams = bundle.get("teams")
    bundle_rosters = bundle.get("rosters")
    bundle_players = get_nested(bundle, ["players", "by_id"])

    if isinstance(bundle_teams, list):
        if len(bundle_teams) != len(loaded.get("teams.json") or []):
            result.warning("chatgpt_bundle.json teams count differs from teams.json")
    else:
        result.error("chatgpt_bundle.json teams must be a list")

    if isinstance(bundle_rosters, list):
        bundle_roster_ids = {as_str(roster.get("roster_id")) for roster in bundle_rosters if isinstance(roster, dict)}
        bundle_roster_ids = {roster_id for roster_id in bundle_roster_ids if roster_id}
        if bundle_roster_ids != roster_ids:
            result.error(
                "chatgpt_bundle.json roster IDs do not match rosters.json: "
                f"bundle={sorted(bundle_roster_ids)}, rosters={sorted(roster_ids)}"
            )
    else:
        result.error("chatgpt_bundle.json rosters must be a list")

    if isinstance(bundle_players, dict):
        missing_from_bundle = sorted(referenced_player_ids - set(str(player_id) for player_id in bundle_players.keys()))
        if missing_from_bundle:
            result.error(f"Referenced player IDs missing from chatgpt_bundle players.by_id: {missing_from_bundle}")
    else:
        result.error("chatgpt_bundle.json players.by_id must be an object")

    indexes = bundle.get("analysis_indexes")
    if isinstance(indexes, dict):
        roster_index = indexes.get("roster_id_to_team")
        if isinstance(roster_index, dict):
            missing_roster_index = sorted(roster_ids - set(str(key) for key in roster_index.keys()))
            if missing_roster_index:
                result.warning(f"analysis_indexes.roster_id_to_team missing roster IDs: {missing_roster_index}")
        else:
            result.warning("analysis_indexes.roster_id_to_team missing or not an object")
    else:
        result.error("chatgpt_bundle.json analysis_indexes must be an object")


def validate_counts(loaded: Dict[str, Any], result: ValidationResult) -> None:
    manifest = loaded.get("manifest.json")
    rosters = loaded.get("rosters.json")
    player_lookup = loaded.get("player_lookup_compact.json")

    if not isinstance(manifest, dict):
        return

    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        result.error("manifest.json counts must be an object")
        return

    comparisons = [
        ("rosters", len(rosters) if isinstance(rosters, list) else None),
        ("compact_player_lookup", len(player_lookup) if isinstance(player_lookup, dict) else None),
    ]

    for key, expected in comparisons:
        actual = counts.get(key)
        if expected is not None and actual != expected:
            result.warning(f"manifest.json counts.{key} mismatch: expected {expected}, got {actual}")

    users_count = counts.get("users")
    if not isinstance(users_count, int):
        result.warning("manifest.json counts.users should be an integer")


def validate_snapshot(config_path: Path, snapshot_dir_override: Optional[Path]) -> ValidationResult:
    result = ValidationResult()
    config = load_config(config_path, result)
    if config is None:
        return result

    snapshot_dir = snapshot_dir_override or Path(get_nested(config, ["snapshot", "output_dir"], "data/current"))

    loaded = validate_required_files(snapshot_dir, result)

    # Continue with any parsed files so validation returns as many actionable issues as possible.
    validate_league_ids(config, loaded, result)
    validate_manifest(snapshot_dir, loaded, result)
    _, roster_ids = validate_teams_and_rosters(loaded, result)
    referenced_player_ids = validate_players(loaded, result)
    validate_chatgpt_bundle(loaded, roster_ids, referenced_player_ids, result)
    validate_counts(loaded, result)

    return result


def print_result(result: ValidationResult) -> None:
    if result.errors:
        print("Snapshot validation failed.")
        print("\nErrors:")
        for error in result.errors:
            print(f"- {error}")
    else:
        print("Snapshot validation passed.")

    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"- {warning}")

    print(f"\nSummary: {len(result.errors)} error(s), {len(result.warnings)} warning(s)")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated Sleeper current snapshot files.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to league config JSON. Default: {DEFAULT_CONFIG_PATH}",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=None,
        help="Override generated snapshot directory. Default comes from config snapshot.output_dir.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    snapshot_dir = Path(args.snapshot_dir) if args.snapshot_dir else None

    result = validate_snapshot(Path(args.config), snapshot_dir)
    print_result(result)

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
