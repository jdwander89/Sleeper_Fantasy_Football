#!/usr/bin/env python3
"""
Sleeper Fantasy Football current snapshot exporter.

Phase 1 scope:
- Read config/league_config.json.
- Fetch NFL state.
- Fetch league metadata.
- Fetch league users.
- Fetch league rosters.
- Collect required player IDs from current rosters.
- Cache the full Sleeper NFL player database locally.
- Write compact ChatGPT-readable current snapshot files.

This script intentionally uses only the Python standard library so it can run
inside GitHub Actions without installing third-party dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


BASE_URL = "https://api.sleeper.app/v1"
DEFAULT_CONFIG_PATH = Path("config/league_config.json")


JsonObject = Dict[str, Any]


class SnapshotError(RuntimeError):
    """Raised when the snapshot cannot be generated safely."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any, *, pretty: bool = True, sort_keys: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        if pretty:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=sort_keys)
            f.write("\n")
        else:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"), sort_keys=sort_keys)
            f.write("\n")


def http_get_json(url: str, *, timeout: int = 30, retries: int = 3, backoff_seconds: float = 1.25) -> Any:
    headers = {
        "Accept": "application/json",
        "User-Agent": "Sleeper-Fantasy-Football-Snapshot/1.0",
    }
    last_error: Optional[BaseException] = None

    for attempt in range(1, retries + 1):
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                if status < 200 or status >= 300:
                    raise SnapshotError(f"GET {url} returned HTTP {status}")
                data = response.read()
                return json.loads(data.decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(backoff_seconds * attempt)

    raise SnapshotError(f"Failed to fetch JSON from {url}: {last_error}") from last_error


def endpoint(path: str) -> str:
    return f"{BASE_URL}{path}"


def load_config(path: Path) -> JsonObject:
    if not path.exists():
        raise SnapshotError(f"Config file not found: {path}")
    config = read_json(path)
    if not isinstance(config, dict):
        raise SnapshotError(f"Config file must contain a JSON object: {path}")
    return config


def get_nested(config: JsonObject, keys: Sequence[str], default: Any = None) -> Any:
    value: Any = config
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def normalize_player_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    value_str = str(value).strip()
    return value_str or None


def add_player_ids(target: Set[str], values: Any) -> None:
    if isinstance(values, list):
        for value in values:
            player_id = normalize_player_id(value)
            if player_id:
                target.add(player_id)
    elif isinstance(values, dict):
        for key in values.keys():
            player_id = normalize_player_id(key)
            if player_id:
                target.add(player_id)


def collect_required_player_ids_from_rosters(rosters: Sequence[JsonObject]) -> Set[str]:
    required: Set[str] = set()

    for roster in rosters:
        for field in ("players", "starters", "reserve", "taxi"):
            add_player_ids(required, roster.get(field))

        metadata = roster.get("metadata")
        if isinstance(metadata, dict):
            # Defensive: some Sleeper metadata fields may reference player IDs.
            for key, value in metadata.items():
                lowered_key = str(key).lower()
                if "player" in lowered_key and isinstance(value, (str, int)):
                    player_id = normalize_player_id(value)
                    if player_id:
                        required.add(player_id)

    return required


def file_age_hours(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    age_seconds = time.time() - path.stat().st_mtime
    return age_seconds / 3600


def load_or_fetch_full_players(
    *,
    cache_dir: Path,
    cache_filename: str,
    max_age_hours: int,
    force_refresh: bool,
    warnings: List[str],
) -> Tuple[JsonObject, JsonObject]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / cache_filename
    meta_path = cache_dir / "players_nfl_cache_meta.json"

    age_hours = file_age_hours(cache_path)
    cache_is_usable = (
        cache_path.exists()
        and not force_refresh
        and age_hours is not None
        and age_hours <= max_age_hours
    )

    if cache_is_usable:
        players = read_json(cache_path)
        meta = read_json(meta_path) if meta_path.exists() else {}
        if not isinstance(players, dict):
            raise SnapshotError(f"Player cache is not a JSON object: {cache_path}")
        meta.update(
            {
                "source": "cache",
                "cache_path": str(cache_path),
                "cache_age_hours": round(age_hours or 0, 3),
                "max_age_hours": max_age_hours,
                "full_cache_committed": False,
            }
        )
        return players, meta

    try:
        players = http_get_json(endpoint("/players/nfl"), timeout=90, retries=3)
        if not isinstance(players, dict):
            raise SnapshotError("Sleeper /players/nfl did not return a JSON object")

        meta = {
            "source": "fresh_fetch",
            "endpoint": endpoint("/players/nfl"),
            "fetched_at": iso_now(),
            "cache_path": str(cache_path),
            "max_age_hours": max_age_hours,
            "full_cache_committed": False,
            "player_count": len(players),
        }

        write_json(cache_path, players, pretty=False)
        write_json(meta_path, meta, pretty=True)
        return players, meta

    except Exception as exc:
        if cache_path.exists():
            stale_players = read_json(cache_path)
            if not isinstance(stale_players, dict):
                raise SnapshotError(f"Stale player cache is not usable: {cache_path}") from exc

            stale_age = file_age_hours(cache_path)
            warnings.append(
                "Could not refresh full Sleeper player cache; using stale local cache "
                f"at {cache_path} with age {round(stale_age or 0, 3)} hours. Error: {exc}"
            )
            meta = read_json(meta_path) if meta_path.exists() else {}
            meta.update(
                {
                    "source": "stale_cache_after_refresh_failure",
                    "cache_path": str(cache_path),
                    "cache_age_hours": round(stale_age or 0, 3),
                    "max_age_hours": max_age_hours,
                    "full_cache_committed": False,
                    "refresh_error": str(exc),
                }
            )
            return stale_players, meta

        raise


def compact_player(player_id: str, player: Optional[JsonObject]) -> JsonObject:
    if not player:
        # Sleeper commonly represents team defenses by abbreviation. The players endpoint
        # usually includes DEF entries, but this fallback keeps snapshots readable if an
        # abbreviation is missing from the cache.
        if player_id.isalpha() and 2 <= len(player_id) <= 4:
            return {
                "player_id": player_id,
                "name": f"{player_id} Defense",
                "first_name": player_id,
                "last_name": "Defense",
                "team": player_id,
                "position": "DEF",
                "fantasy_positions": ["DEF"],
                "status": None,
                "injury_status": None,
                "years_exp": None,
                "age": None,
                "depth_chart_position": None,
                "search_rank": None,
                "missing_from_full_cache": True,
            }

        return {
            "player_id": player_id,
            "name": f"Unknown Player {player_id}",
            "first_name": None,
            "last_name": None,
            "team": None,
            "position": None,
            "fantasy_positions": [],
            "status": None,
            "injury_status": None,
            "years_exp": None,
            "age": None,
            "depth_chart_position": None,
            "search_rank": None,
            "missing_from_full_cache": True,
        }

    first_name = player.get("first_name")
    last_name = player.get("last_name")
    full_name = player.get("full_name")

    if not full_name:
        name_parts = [str(part).strip() for part in (first_name, last_name) if part]
        full_name = " ".join(name_parts).strip() or str(player.get("search_full_name") or player_id)

    return {
        "player_id": str(player.get("player_id") or player_id),
        "name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "team": player.get("team"),
        "position": player.get("position"),
        "fantasy_positions": player.get("fantasy_positions") or [],
        "status": player.get("status"),
        "injury_status": player.get("injury_status"),
        "years_exp": player.get("years_exp"),
        "age": player.get("age"),
        "depth_chart_position": player.get("depth_chart_position"),
        "search_rank": player.get("search_rank"),
    }


def build_compact_player_lookup(required_ids: Iterable[str], full_players: JsonObject) -> Tuple[JsonObject, List[str]]:
    compact: JsonObject = {}
    missing: List[str] = []

    for player_id in sorted(set(required_ids), key=lambda item: (not item.isalpha(), item)):
        player = full_players.get(player_id)
        compacted = compact_player(player_id, player if isinstance(player, dict) else None)
        compact[player_id] = compacted
        if compacted.get("missing_from_full_cache") and not (
            player_id.isalpha() and compacted.get("position") == "DEF"
        ):
            missing.append(player_id)

    return compact, missing


def normalize_name_key(name: Any) -> Optional[str]:
    if not name:
        return None
    return " ".join(str(name).lower().strip().split()) or None


def build_player_id_index(
    *,
    compact_players: JsonObject,
    required_player_ids: Set[str],
    missing_player_ids: List[str],
    cache_meta: JsonObject,
) -> JsonObject:
    by_name: Dict[str, str] = {}
    by_team: Dict[str, List[str]] = {}
    by_position: Dict[str, List[str]] = {}

    for player_id, player in compact_players.items():
        if not isinstance(player, dict):
            continue

        name_key = normalize_name_key(player.get("name"))
        if name_key and name_key not in by_name:
            by_name[name_key] = player_id

        for name_field in ("first_name", "last_name"):
            partial_key = normalize_name_key(player.get(name_field))
            if partial_key and partial_key not in by_name:
                by_name[partial_key] = player_id

        team = player.get("team")
        if team:
            by_team.setdefault(str(team), []).append(player_id)

        position = player.get("position")
        if position:
            by_position.setdefault(str(position), []).append(player_id)

    return {
        "generated_at": iso_now(),
        "player_cache": cache_meta,
        "counts": {
            "required_player_ids": len(required_player_ids),
            "resolved_player_ids": len(required_player_ids) - len(missing_player_ids),
            "missing_player_ids": len(missing_player_ids),
            "defense_ids": sum(
                1
                for player in compact_players.values()
                if isinstance(player, dict) and player.get("position") == "DEF"
            ),
        },
        "indexes": {
            "by_name": dict(sorted(by_name.items())),
            "by_team": {key: sorted(value) for key, value in sorted(by_team.items())},
            "by_position": {key: sorted(value) for key, value in sorted(by_position.items())},
        },
        "missing_ids": sorted(missing_player_ids),
    }


def sleeper_points(settings: JsonObject, base_key: str, decimal_key: str) -> Optional[float]:
    base = settings.get(base_key)
    decimal = settings.get(decimal_key)

    if base is None and decimal is None:
        return None

    try:
        base_value = float(base or 0)
    except (TypeError, ValueError):
        base_value = 0.0

    try:
        decimal_value = float(decimal or 0) / 100.0
    except (TypeError, ValueError):
        decimal_value = 0.0

    return round(base_value + decimal_value, 2)


def user_team_name(user: Optional[JsonObject]) -> Optional[str]:
    if not user:
        return None

    metadata = user.get("metadata") if isinstance(user.get("metadata"), dict) else {}
    for key in ("team_name", "team_name_update", "display_name"):
        value = metadata.get(key)
        if value:
            value_str = str(value).strip()
            if value_str:
                return value_str

    return None


def user_display_label(user: Optional[JsonObject], roster_id: Any) -> str:
    if user:
        team_name = user_team_name(user)
        if team_name:
            return team_name

        display_name = user.get("display_name")
        if display_name:
            return str(display_name)

        username = user.get("username")
        if username:
            return str(username)

    return f"Roster {roster_id}"


def normalize_user(user: JsonObject) -> JsonObject:
    metadata = user.get("metadata") if isinstance(user.get("metadata"), dict) else {}

    return {
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "display_name": user.get("display_name"),
        "team_name": user_team_name(user),
        "is_owner": user.get("is_owner"),
        "metadata": metadata,
    }


def build_teams(rosters: Sequence[JsonObject], users_by_id: Dict[str, JsonObject]) -> List[JsonObject]:
    teams: List[JsonObject] = []

    for roster in sorted(rosters, key=lambda item: item.get("roster_id") or 0):
        roster_id = roster.get("roster_id")
        owner_id = roster.get("owner_id")
        user = users_by_id.get(str(owner_id)) if owner_id is not None else None
        settings = roster.get("settings") if isinstance(roster.get("settings"), dict) else {}

        teams.append(
            {
                "roster_id": roster_id,
                "owner_user_id": owner_id,
                "team_name": user_team_name(user),
                "display_label": user_display_label(user, roster_id),
                "owner": normalize_user(user) if user else None,
                "record": {
                    "wins": settings.get("wins"),
                    "losses": settings.get("losses"),
                    "ties": settings.get("ties"),
                },
                "points": {
                    "points_for": sleeper_points(settings, "fpts", "fpts_decimal"),
                    "points_against": sleeper_points(settings, "fpts_against", "fpts_against_decimal"),
                    "raw_fpts": settings.get("fpts"),
                    "raw_fpts_decimal": settings.get("fpts_decimal"),
                    "raw_fpts_against": settings.get("fpts_against"),
                    "raw_fpts_against_decimal": settings.get("fpts_against_decimal"),
                },
                "waivers": {
                    "waiver_position": settings.get("waiver_position"),
                    "waiver_budget_used": settings.get("waiver_budget_used"),
                },
                "activity": {
                    "total_moves": settings.get("total_moves"),
                },
                "settings": settings,
                "metadata": roster.get("metadata") if isinstance(roster.get("metadata"), dict) else {},
            }
        )

    return teams


def player_name(player_id: str, compact_players: JsonObject) -> str:
    player = compact_players.get(str(player_id))
    if isinstance(player, dict) and player.get("name"):
        return str(player["name"])
    return str(player_id)


def unique_ordered(values: Iterable[Any]) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for value in values:
        player_id = normalize_player_id(value)
        if player_id and player_id not in seen:
            seen.add(player_id)
            result.append(player_id)
    return result


def infer_bench(players: Sequence[str], starters: Sequence[str], reserve: Sequence[str], taxi: Sequence[str]) -> List[str]:
    unavailable = set(starters) | set(reserve) | set(taxi)
    return [player_id for player_id in players if player_id not in unavailable]


def build_roster_snapshots(rosters: Sequence[JsonObject], compact_players: JsonObject) -> List[JsonObject]:
    snapshots: List[JsonObject] = []

    for roster in sorted(rosters, key=lambda item: item.get("roster_id") or 0):
        players = unique_ordered(roster.get("players") or [])
        starters = unique_ordered(roster.get("starters") or [])
        reserve = unique_ordered(roster.get("reserve") or [])
        taxi = unique_ordered(roster.get("taxi") or [])
        bench = infer_bench(players, starters, reserve, taxi)

        snapshots.append(
            {
                "roster_id": roster.get("roster_id"),
                "owner_user_id": roster.get("owner_id"),
                "players": players,
                "starters": starters,
                "bench": bench,
                "reserve": reserve,
                "taxi": taxi,
                "player_count": len(players),
                "starter_count": len(starters),
                "bench_count": len(bench),
                "reserve_count": len(reserve),
                "taxi_count": len(taxi),
                "display": {
                    "players": [player_name(pid, compact_players) for pid in players],
                    "starters": [player_name(pid, compact_players) for pid in starters],
                    "bench": [player_name(pid, compact_players) for pid in bench],
                    "reserve": [player_name(pid, compact_players) for pid in reserve],
                    "taxi": [player_name(pid, compact_players) for pid in taxi],
                },
                "settings": roster.get("settings") if isinstance(roster.get("settings"), dict) else {},
                "metadata": roster.get("metadata") if isinstance(roster.get("metadata"), dict) else {},
            }
        )

    return snapshots


def build_league_context(league: JsonObject, nfl_state: JsonObject) -> JsonObject:
    return {
        "league_id": league.get("league_id"),
        "name": league.get("name"),
        "sport": league.get("sport"),
        "season": league.get("season"),
        "season_type": league.get("season_type"),
        "status": league.get("status"),
        "total_rosters": league.get("total_rosters"),
        "draft_id": league.get("draft_id"),
        "previous_league_id": league.get("previous_league_id"),
        "roster_positions": league.get("roster_positions") or [],
        "settings": league.get("settings") or {},
        "scoring_settings": league.get("scoring_settings") or {},
        "nfl_state": nfl_state,
    }


def build_analysis_indexes(teams: Sequence[JsonObject], compact_players: JsonObject) -> JsonObject:
    roster_id_to_team: Dict[str, JsonObject] = {}
    team_name_to_roster_id: Dict[str, Any] = {}
    owner_name_to_roster_id: Dict[str, Any] = {}
    player_name_to_player_id: Dict[str, str] = {}

    for team in teams:
        roster_id = team.get("roster_id")
        roster_key = str(roster_id)
        roster_id_to_team[roster_key] = {
            "roster_id": roster_id,
            "display_label": team.get("display_label"),
            "owner_user_id": team.get("owner_user_id"),
        }

        for value in (team.get("team_name"), team.get("display_label")):
            key = normalize_name_key(value)
            if key and key not in team_name_to_roster_id:
                team_name_to_roster_id[key] = roster_id

        owner = team.get("owner")
        if isinstance(owner, dict):
            for value in (owner.get("display_name"), owner.get("username")):
                key = normalize_name_key(value)
                if key and key not in owner_name_to_roster_id:
                    owner_name_to_roster_id[key] = roster_id

    for player_id, player in compact_players.items():
        if not isinstance(player, dict):
            continue
        key = normalize_name_key(player.get("name"))
        if key and key not in player_name_to_player_id:
            player_name_to_player_id[key] = player_id

    return {
        "roster_id_to_team": roster_id_to_team,
        "team_name_to_roster_id": dict(sorted(team_name_to_roster_id.items())),
        "owner_name_to_roster_id": dict(sorted(owner_name_to_roster_id.items())),
        "player_name_to_player_id": dict(sorted(player_name_to_player_id.items())),
    }


def build_manifest(
    *,
    config: JsonObject,
    league: JsonObject,
    nfl_state: JsonObject,
    users_count: int,
    rosters_count: int,
    required_player_ids: Set[str],
    compact_players: JsonObject,
    missing_player_ids: List[str],
    output_files: Sequence[Path],
    warnings: List[str],
    errors: List[str],
) -> JsonObject:
    return {
        "schema_version": get_nested(config, ["schema_version"], "1.0.0"),
        "generated_at": iso_now(),
        "league_id": str(get_nested(config, ["league", "league_id"])),
        "sport": get_nested(config, ["league", "sport"], "nfl"),
        "season": league.get("season") or nfl_state.get("league_season") or nfl_state.get("season"),
        "season_type": league.get("season_type") or nfl_state.get("season_type"),
        "snapshot_mode": get_nested(config, ["snapshot", "mode"], "current_only"),
        "nfl_state": nfl_state,
        "included_weeks": [],
        "phase": "phase_1_minimal_roster_snapshot",
        "files": [
            {
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
            }
            for path in output_files
        ],
        "counts": {
            "users": users_count,
            "rosters": rosters_count,
            "required_player_ids": len(required_player_ids),
            "compact_player_lookup": len(compact_players),
            "missing_player_ids": len(missing_player_ids),
        },
        "data_quality": {
            "warnings": warnings,
            "errors": errors,
            "missing_player_ids": sorted(missing_player_ids),
        },
    }


def snapshot(config_path: Path, *, force_refresh_players: bool = False) -> None:
    config = load_config(config_path)

    league_id = str(get_nested(config, ["league", "league_id"], "")).strip()
    sport = str(get_nested(config, ["league", "sport"], "nfl")).strip() or "nfl"
    if not league_id:
        raise SnapshotError("Missing league.league_id in config")

    output_dir = Path(get_nested(config, ["snapshot", "output_dir"], "data/current"))
    raw_cache_dir = Path(get_nested(config, ["raw_cache", "directory"], "raw_cache"))
    pretty_json = bool(get_nested(config, ["export", "outputs", "pretty_json"], True))
    sort_keys = bool(get_nested(config, ["export", "outputs", "sort_keys"], False))

    warnings: List[str] = []
    errors: List[str] = []

    nfl_state = http_get_json(endpoint(f"/state/{sport}"))
    league = http_get_json(endpoint(f"/league/{league_id}"))
    users = http_get_json(endpoint(f"/league/{league_id}/users"))
    rosters = http_get_json(endpoint(f"/league/{league_id}/rosters"))

    if not isinstance(nfl_state, dict):
        raise SnapshotError("NFL state response was not a JSON object")
    if not isinstance(league, dict):
        raise SnapshotError("League response was not a JSON object")
    if not isinstance(users, list):
        raise SnapshotError("Users response was not a JSON array")
    if not isinstance(rosters, list):
        raise SnapshotError("Rosters response was not a JSON array")

    roster_objects = [roster for roster in rosters if isinstance(roster, dict)]
    user_objects = [user for user in users if isinstance(user, dict)]
    users_by_id: Dict[str, JsonObject] = {
        str(user.get("user_id")): user for user in user_objects if user.get("user_id") is not None
    }

    required_player_ids = collect_required_player_ids_from_rosters(roster_objects)

    player_cache_config = get_nested(config, ["player_cache"], {})
    max_age_hours = int(player_cache_config.get("max_age_hours", 24)) if isinstance(player_cache_config, dict) else 24
    cache_filename = (
        str(player_cache_config.get("full_cache_filename", "players_nfl_full.json"))
        if isinstance(player_cache_config, dict)
        else "players_nfl_full.json"
    )

    full_players, player_cache_meta = load_or_fetch_full_players(
        cache_dir=raw_cache_dir,
        cache_filename=cache_filename,
        max_age_hours=max_age_hours,
        force_refresh=force_refresh_players,
        warnings=warnings,
    )

    compact_players, missing_player_ids = build_compact_player_lookup(required_player_ids, full_players)

    league_context = build_league_context(league, nfl_state)
    teams = build_teams(roster_objects, users_by_id)
    roster_snapshots = build_roster_snapshots(roster_objects, compact_players)
    player_id_index = build_player_id_index(
        compact_players=compact_players,
        required_player_ids=required_player_ids,
        missing_player_ids=missing_player_ids,
        cache_meta=player_cache_meta,
    )
    analysis_indexes = build_analysis_indexes(teams, compact_players)

    metadata = {
        "schema_version": get_nested(config, ["schema_version"], "1.0.0"),
        "generated_at": iso_now(),
        "league_id": league_id,
        "sport": sport,
        "phase": "phase_1_minimal_roster_snapshot",
    }

    chatgpt_bundle = {
        "metadata": metadata,
        "league": league_context,
        "teams": teams,
        "rosters": roster_snapshots,
        "players": {
            "by_id": compact_players,
        },
        "matchups": {
            "by_week": {},
            "status": "not_included_until_phase_3",
        },
        "transactions": {
            "by_week": {},
            "trades": [],
            "waivers": [],
            "free_agent_moves": [],
            "status": "not_included_until_phase_4",
        },
        "drafts": [],
        "traded_picks": [],
        "analysis_indexes": analysis_indexes,
    }

    output_paths = {
        "league_context": output_dir / "league_context.json",
        "teams": output_dir / "teams.json",
        "rosters": output_dir / "rosters.json",
        "player_lookup_compact": output_dir / "player_lookup_compact.json",
        "player_id_index": output_dir / "player_id_index.json",
        "chatgpt_bundle": output_dir / "chatgpt_bundle.json",
    }

    # Write topic files before manifest so the manifest can include accurate file sizes.
    write_json(output_paths["league_context"], league_context, pretty=pretty_json, sort_keys=sort_keys)
    write_json(output_paths["teams"], teams, pretty=pretty_json, sort_keys=sort_keys)
    write_json(output_paths["rosters"], roster_snapshots, pretty=pretty_json, sort_keys=sort_keys)
    write_json(output_paths["player_lookup_compact"], compact_players, pretty=pretty_json, sort_keys=sort_keys)
    write_json(output_paths["player_id_index"], player_id_index, pretty=pretty_json, sort_keys=sort_keys)
    write_json(output_paths["chatgpt_bundle"], chatgpt_bundle, pretty=pretty_json, sort_keys=sort_keys)

    manifest_path = output_dir / "manifest.json"
    manifest = build_manifest(
        config=config,
        league=league,
        nfl_state=nfl_state,
        users_count=len(user_objects),
        rosters_count=len(roster_objects),
        required_player_ids=required_player_ids,
        compact_players=compact_players,
        missing_player_ids=missing_player_ids,
        output_files=[manifest_path, *output_paths.values()],
        warnings=warnings,
        errors=errors,
    )

    write_json(manifest_path, manifest, pretty=pretty_json, sort_keys=sort_keys)

    print(f"Wrote Sleeper current snapshot for league {league_id} to {output_dir}")
    print(f"Users: {len(user_objects)} | Rosters: {len(roster_objects)} | Required player IDs: {len(required_player_ids)}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export current Sleeper league snapshot for ChatGPT analysis.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to league config JSON. Default: {DEFAULT_CONFIG_PATH}",
    )
    parser.add_argument(
        "--force-refresh-players",
        action="store_true",
        help="Refresh the full Sleeper NFL player cache even if the local cache is still fresh.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        snapshot(Path(args.config), force_refresh_players=args.force_refresh_players)
        return 0
    except SnapshotError as exc:
        print(f"Snapshot failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Snapshot interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
