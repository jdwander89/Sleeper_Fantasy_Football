#!/usr/bin/env python3
"""Finalize generated current snapshot files before validation/commit."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

CFG = Path("config/league_config.json")
INVALID_PLAYER_IDS = {"", "0", "off", "none", "null", "undefined"}
SNAPSHOT_FILES = [
    "manifest.json",
    "league_context.json",
    "teams.json",
    "rosters.json",
    "matchups.json",
    "transactions.json",
    "drafts.json",
    "traded_picks.json",
    "player_lookup_compact.json",
    "player_id_index.json",
    "chatgpt_bundle.json",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def get_nested(payload: Any, keys: list[str], default: Any = None) -> Any:
    value = payload
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def is_invalid_player_id(value: Any) -> bool:
    return str(value).strip().lower() in INVALID_PLAYER_IDS


def filter_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for value in values:
        if value is not None and not is_invalid_player_id(value):
            text = str(value)
            if text not in out:
                out.append(text)
    return out


def clean_point_map(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if not is_invalid_player_id(k)}


def player_name(player_id: str, lookup: Dict[str, Any]) -> str:
    player = lookup.get(str(player_id))
    if isinstance(player, dict) and player.get("name"):
        return str(player["name"])
    return str(player_id)


def clean_lookup(lookup: Any) -> Dict[str, Any]:
    if not isinstance(lookup, dict):
        return {}
    return {str(k): v for k, v in lookup.items() if not is_invalid_player_id(k) and isinstance(v, dict)}


def clean_rosters(rosters: Any, lookup: Dict[str, Any]) -> Any:
    if not isinstance(rosters, list):
        return rosters
    for roster in rosters:
        if not isinstance(roster, dict):
            continue
        for key in ("players", "starters", "bench", "reserve", "taxi"):
            roster[key] = filter_ids(roster.get(key))
        roster["display"] = {
            "players": [player_name(pid, lookup) for pid in roster["players"]],
            "starters": [player_name(pid, lookup) for pid in roster["starters"]],
            "bench": [player_name(pid, lookup) for pid in roster["bench"]],
            "reserve": [player_name(pid, lookup) for pid in roster["reserve"]],
            "taxi": [player_name(pid, lookup) for pid in roster["taxi"]],
        }
    return rosters


def clean_matchups(matchups: Any, lookup: Dict[str, Any]) -> Any:
    if not isinstance(matchups, dict):
        return matchups
    by_week = matchups.get("by_week")
    if not isinstance(by_week, dict):
        return matchups
    for week in by_week.values():
        if not isinstance(week, dict):
            continue
        for result in week.get("roster_results", []):
            if not isinstance(result, dict):
                continue
            for key in ("players", "starters", "bench"):
                result[key] = filter_ids(result.get(key))
            result["players_points"] = clean_point_map(result.get("players_points"))
            result["starters_points"] = clean_point_map(result.get("starters_points"))
            result["display"] = {
                "players": [player_name(pid, lookup) for pid in result["players"]],
                "starters": [player_name(pid, lookup) for pid in result["starters"]],
                "bench": [player_name(pid, lookup) for pid in result["bench"]],
            }
    return matchups


def clean_transactions(transactions: Any) -> Any:
    if not isinstance(transactions, dict):
        return transactions
    by_week = transactions.get("by_week")
    if not isinstance(by_week, dict):
        return transactions
    for week in by_week.values():
        if not isinstance(week, dict):
            continue
        for transaction in week.get("transactions", []):
            if not isinstance(transaction, dict):
                continue
            for side in ("adds", "drops"):
                moves = transaction.get(side)
                if isinstance(moves, list):
                    transaction[side] = [m for m in moves if not (isinstance(m, dict) and is_invalid_player_id(m.get("player_id")))]
    transactions["all"] = [tx for week in by_week.values() if isinstance(week, dict) for tx in week.get("transactions", [])]
    transactions["trades"] = [tx for tx in transactions["all"] if tx.get("type") == "trade"]
    transactions["waivers"] = [tx for tx in transactions["all"] if tx.get("type") == "waiver"]
    transactions["free_agent_moves"] = [tx for tx in transactions["all"] if tx.get("type") == "free_agent"]
    transactions["counts"] = {
        **(transactions.get("counts") if isinstance(transactions.get("counts"), dict) else {}),
        "weeks": len(by_week),
        "transactions": len(transactions["all"]),
        "trades": len(transactions["trades"]),
        "waivers": len(transactions["waivers"]),
        "free_agent_moves": len(transactions["free_agent_moves"]),
    }
    return transactions


def clean_drafts(drafts_payload: Any, lookup: Dict[str, Any]) -> Any:
    if not isinstance(drafts_payload, dict):
        return drafts_payload
    drafts = drafts_payload.get("drafts")
    if not isinstance(drafts, list):
        return drafts_payload
    total_picks = 0
    total_traded = 0
    for draft in drafts:
        if not isinstance(draft, dict):
            continue
        picks = draft.get("picks") if isinstance(draft.get("picks"), list) else []
        for pick in picks:
            if not isinstance(pick, dict):
                continue
            if pick.get("player_id") is not None and is_invalid_player_id(pick.get("player_id")):
                pick["player_id"] = None
                pick["player_name"] = None
            elif pick.get("player_id") is not None:
                pick["player_name"] = player_name(str(pick["player_id"]), lookup)
        draft["picks"] = picks
        draft["counts"] = {"picks": len(picks), "traded_picks": len(draft.get("traded_picks") or [])}
        total_picks += len(picks)
        total_traded += len(draft.get("traded_picks") or [])
    drafts_payload["counts"] = {"drafts": len(drafts), "draft_picks": total_picks, "draft_traded_picks": total_traded}
    return drafts_payload


def build_player_index(lookup: Dict[str, Any]) -> Dict[str, Any]:
    by_name: Dict[str, str] = {}
    by_team: Dict[str, list[str]] = {}
    by_position: Dict[str, list[str]] = {}
    missing: list[str] = []
    for pid, player in lookup.items():
        if player.get("missing_from_full_cache"):
            missing.append(pid)
        name = player.get("name")
        if name:
            by_name[str(name).lower()] = pid
        if player.get("team"):
            by_team.setdefault(str(player["team"]), []).append(pid)
        if player.get("position"):
            by_position.setdefault(str(player["position"]), []).append(pid)
    return {
        "generated_at": now(),
        "counts": {
            "required_player_ids": len(lookup),
            "resolved_player_ids": len(lookup) - len(missing),
            "missing_player_ids": len(missing),
            "defense_ids": sum(1 for p in lookup.values() if p.get("position") == "DEF"),
        },
        "indexes": {
            "by_name": dict(sorted(by_name.items())),
            "by_team": {k: sorted(v) for k, v in sorted(by_team.items())},
            "by_position": {k: sorted(v) for k, v in sorted(by_position.items())},
        },
        "missing_ids": sorted(missing),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean and finalize current Sleeper snapshot files.")
    parser.add_argument("--config", default=str(CFG))
    args = parser.parse_args()
    config = read_json(Path(args.config), {})
    out = Path(get_nested(config, ["snapshot", "output_dir"], "data/current"))

    lookup = clean_lookup(read_json(out / "player_lookup_compact.json", {}))
    rosters = clean_rosters(read_json(out / "rosters.json", []), lookup)
    matchups = clean_matchups(read_json(out / "matchups.json", {}), lookup)
    transactions = clean_transactions(read_json(out / "transactions.json", {}))
    drafts_payload = clean_drafts(read_json(out / "drafts.json", {}), lookup)
    traded_picks = read_json(out / "traded_picks.json", {})
    bundle = read_json(out / "chatgpt_bundle.json", {})
    manifest = read_json(out / "manifest.json", {})

    player_index = build_player_index(lookup)

    if isinstance(bundle, dict):
        bundle.setdefault("players", {})["by_id"] = lookup
        bundle["rosters"] = rosters
        bundle["matchups"] = matchups
        bundle["transactions"] = transactions
        bundle["drafts"] = drafts_payload.get("drafts", []) if isinstance(drafts_payload, dict) else []
        bundle["traded_picks"] = traded_picks

    if isinstance(manifest, dict):
        manifest["phase"] = "finalized_current_snapshot"
        manifest.setdefault("counts", {}).update(
            {
                "required_player_ids": len(lookup),
                "compact_player_lookup": len(lookup),
                "missing_player_ids": len(player_index["missing_ids"]),
                "transactions": get_nested(transactions, ["counts", "transactions"], 0),
                "trades": get_nested(transactions, ["counts", "trades"], 0),
                "waivers": get_nested(transactions, ["counts", "waivers"], 0),
                "free_agent_moves": get_nested(transactions, ["counts", "free_agent_moves"], 0),
                "drafts": get_nested(drafts_payload, ["counts", "drafts"], 0),
                "draft_picks": get_nested(drafts_payload, ["counts", "draft_picks"], 0),
                "draft_traded_picks": get_nested(drafts_payload, ["counts", "draft_traded_picks"], 0),
                "league_traded_picks": get_nested(traded_picks, ["counts", "league_traded_picks"], 0),
            }
        )
        manifest.setdefault("data_quality", {})["missing_player_ids"] = player_index["missing_ids"]
        manifest.setdefault("data_quality", {}).setdefault("errors", [])

    write_json(out / "player_lookup_compact.json", lookup)
    write_json(out / "player_id_index.json", player_index)
    write_json(out / "rosters.json", rosters)
    write_json(out / "matchups.json", matchups)
    write_json(out / "transactions.json", transactions)
    write_json(out / "drafts.json", drafts_payload)
    write_json(out / "chatgpt_bundle.json", bundle)

    if isinstance(manifest, dict):
        manifest["files"] = []
        for filename in SNAPSHOT_FILES:
            path = out / filename
            manifest["files"].append({"path": str(path), "exists": path.exists(), "size_bytes": path.stat().st_size if path.exists() else 0})
        write_json(out / "manifest.json", manifest)

    print("Finalized current snapshot files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
