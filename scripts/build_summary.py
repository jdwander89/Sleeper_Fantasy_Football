#!/usr/bin/env python3
"""Build a compact ChatGPT-first summary from current snapshot topic files."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

CFG = Path("config/league_config.json")
SUMMARY_FILE = "chatgpt_summary.json"
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
    "chatgpt_summary.json",
    "chatgpt_bundle.json",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def get(payload: Any, path: list[str], default: Any = None) -> Any:
    value = payload
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def player(pid: Any, lookup: Dict[str, Any]) -> Dict[str, Any]:
    item = lookup.get(str(pid), {}) if pid is not None else {}
    return {
        "player_id": str(pid) if pid is not None else None,
        "name": item.get("name") if isinstance(item, dict) else str(pid),
        "team": item.get("team") if isinstance(item, dict) else None,
        "position": item.get("position") if isinstance(item, dict) else None,
        "injury_status": item.get("injury_status") if isinstance(item, dict) else None,
    }


def roster_summary(roster: Dict[str, Any], team_by_roster: Dict[str, Dict[str, Any]], lookup: Dict[str, Any]) -> Dict[str, Any]:
    rid = str(roster.get("roster_id"))
    team = team_by_roster.get(rid, {})
    starters = roster.get("starters") if isinstance(roster.get("starters"), list) else []
    reserve = roster.get("reserve") if isinstance(roster.get("reserve"), list) else []
    players = roster.get("players") if isinstance(roster.get("players"), list) else []
    position_counts: Dict[str, int] = {}
    for pid in players:
        pos = get(lookup, [str(pid), "position"], "UNKNOWN") or "UNKNOWN"
        position_counts[str(pos)] = position_counts.get(str(pos), 0) + 1
    return {
        "roster_id": roster.get("roster_id"),
        "team_label": team.get("display_label"),
        "owner_user_id": roster.get("owner_user_id"),
        "record": team.get("record"),
        "points": team.get("points"),
        "counts": {
            "players": len(players),
            "starters": len(starters),
            "bench": len(roster.get("bench") or []),
            "reserve": len(reserve),
        },
        "position_counts": dict(sorted(position_counts.items())),
        "starters": [player(pid, lookup) for pid in starters],
        "reserve": [player(pid, lookup) for pid in reserve],
    }


def matchup_summary(matchups: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"included_weeks": matchups.get("included_weeks", []), "by_week": {}, "counts": matchups.get("counts", {})}
    by_week = matchups.get("by_week") if isinstance(matchups.get("by_week"), dict) else {}
    for week, payload in by_week.items():
        week_matchups = []
        for item in payload.get("matchups", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            week_matchups.append(
                {
                    "matchup_id": item.get("matchup_id"),
                    "teams": item.get("teams", []),
                    "winner": item.get("winner"),
                }
            )
        out["by_week"][str(week)] = {"week": payload.get("week", week), "matchups": week_matchups, "counts": payload.get("counts", {})}
    return out


def transaction_summary(transactions: Dict[str, Any]) -> Dict[str, Any]:
    counts_by_roster: Dict[str, Dict[str, int]] = {}
    recent = []
    for tx in transactions.get("all", []) if isinstance(transactions.get("all"), list) else []:
        if not isinstance(tx, dict):
            continue
        for rid in tx.get("roster_ids", []) if isinstance(tx.get("roster_ids"), list) else []:
            key = str(rid)
            counts_by_roster.setdefault(key, {"transactions": 0, "trades": 0, "waivers": 0, "free_agent_moves": 0})
            counts_by_roster[key]["transactions"] += 1
            if tx.get("type") == "trade":
                counts_by_roster[key]["trades"] += 1
            elif tx.get("type") == "waiver":
                counts_by_roster[key]["waivers"] += 1
            elif tx.get("type") == "free_agent":
                counts_by_roster[key]["free_agent_moves"] += 1
        recent.append(
            {
                "week": tx.get("week"),
                "transaction_id": tx.get("transaction_id"),
                "type": tx.get("type"),
                "status": tx.get("status"),
                "created_at": tx.get("created_at"),
                "team_labels": tx.get("team_labels", []),
                "adds": tx.get("adds", []),
                "drops": tx.get("drops", []),
                "draft_picks": tx.get("draft_picks", []),
            }
        )
    recent = sorted(recent, key=lambda x: str(x.get("created_at") or ""), reverse=True)[:25]
    return {"counts": transactions.get("counts", {}), "activity_by_roster_id": counts_by_roster, "recent_transactions": recent}


def draft_summary(drafts_payload: Dict[str, Any], traded_picks: Dict[str, Any]) -> Dict[str, Any]:
    drafts = []
    for draft in drafts_payload.get("drafts", []) if isinstance(drafts_payload.get("drafts"), list) else []:
        if not isinstance(draft, dict):
            continue
        picks_by_roster: Dict[str, int] = {}
        first_round = []
        for pick in draft.get("picks", []) if isinstance(draft.get("picks"), list) else []:
            if not isinstance(pick, dict):
                continue
            rid = str(pick.get("roster_id"))
            picks_by_roster[rid] = picks_by_roster.get(rid, 0) + 1
            if pick.get("round") == 1:
                first_round.append(
                    {
                        "pick_no": pick.get("pick_no"),
                        "roster_id": pick.get("roster_id"),
                        "team_label": pick.get("team_label"),
                        "player_id": pick.get("player_id"),
                        "player_name": pick.get("player_name"),
                    }
                )
        drafts.append(
            {
                "draft_id": draft.get("draft_id"),
                "status": draft.get("status"),
                "season": draft.get("season"),
                "type": draft.get("type"),
                "counts": draft.get("counts", {}),
                "first_round": first_round,
                "picks_by_roster_id": picks_by_roster,
            }
        )
    return {"counts": drafts_payload.get("counts", {}), "drafts": drafts, "traded_picks": traded_picks.get("counts", {})}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build compact ChatGPT summary from current Sleeper snapshot.")
    parser.add_argument("--config", default=str(CFG))
    args = parser.parse_args()
    config = read_json(Path(args.config), {})
    out = Path(get(config, ["snapshot", "output_dir"], "data/current"))

    manifest = read_json(out / "manifest.json", {})
    league = read_json(out / "league_context.json", {})
    teams = read_json(out / "teams.json", [])
    rosters = read_json(out / "rosters.json", [])
    matchups = read_json(out / "matchups.json", {})
    transactions = read_json(out / "transactions.json", {})
    drafts = read_json(out / "drafts.json", {})
    traded_picks = read_json(out / "traded_picks.json", {})
    lookup = read_json(out / "player_lookup_compact.json", {})

    team_by_roster = {str(team.get("roster_id")): team for team in teams if isinstance(team, dict)}
    roster_summaries = [roster_summary(r, team_by_roster, lookup) for r in rosters if isinstance(r, dict)]

    summary = {
        "metadata": {
            "generated_at": now(),
            "source_snapshot_generated_at": manifest.get("generated_at"),
            "league_id": manifest.get("league_id"),
            "season": manifest.get("season"),
            "season_type": manifest.get("season_type"),
            "purpose": "compact first-read file for ChatGPT league analysis",
        },
        "league": {
            "name": league.get("name"),
            "status": league.get("status"),
            "total_rosters": league.get("total_rosters"),
            "roster_positions": league.get("roster_positions", []),
            "settings": {
                "type": get(league, ["settings", "type"]),
                "num_teams": get(league, ["settings", "num_teams"]),
                "playoff_teams": get(league, ["settings", "playoff_teams"]),
                "trade_deadline": get(league, ["settings", "trade_deadline"]),
                "waiver_budget": get(league, ["settings", "waiver_budget"]),
                "max_keepers": get(league, ["settings", "max_keepers"]),
                "draft_rounds": get(league, ["settings", "draft_rounds"]),
            },
        },
        "counts": manifest.get("counts", {}),
        "data_quality": manifest.get("data_quality", {}),
        "teams": roster_summaries,
        "matchups": matchup_summary(matchups),
        "transactions": transaction_summary(transactions),
        "drafts": draft_summary(drafts, traded_picks),
        "file_guidance": {
            "start_here": "data/current/chatgpt_summary.json",
            "full_bundle": "data/current/chatgpt_bundle.json",
            "topic_files": [
                "data/current/teams.json",
                "data/current/rosters.json",
                "data/current/matchups.json",
                "data/current/transactions.json",
                "data/current/drafts.json",
                "data/current/traded_picks.json",
                "data/current/player_lookup_compact.json",
            ],
        },
    }

    write_json(out / SUMMARY_FILE, summary)

    manifest["summary_generated_at"] = summary["metadata"]["generated_at"]
    manifest.setdefault("counts", {})["summary_teams"] = len(roster_summaries)
    manifest["files"] = []
    for filename in SNAPSHOT_FILES:
        path = out / filename
        manifest["files"].append({"path": str(path), "exists": path.exists(), "size_bytes": path.stat().st_size if path.exists() else 0})
    write_json(out / "manifest.json", manifest)

    print(f"Wrote compact summary to {out / SUMMARY_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
