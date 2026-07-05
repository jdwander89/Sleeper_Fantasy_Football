#!/usr/bin/env python3
"""Run the full Sleeper current snapshot pipeline."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence


ROOT = Path(__file__).resolve().parents[1]


def run_step(command: List[str]) -> None:
    print(f"\n$ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run all Sleeper snapshot exporters and validators.")
    parser.add_argument(
        "--force-refresh-players",
        action="store_true",
        help="Force refresh of the local Sleeper NFL player cache during exporter steps.",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Run exporters and finalization only; skip validation scripts.",
    )
    args = parser.parse_args(argv)

    python = sys.executable
    refresh_flag = ["--force-refresh-players"] if args.force_refresh_players else []

    steps = [
        [python, "scripts/sleeper_snapshot.py", *refresh_flag],
        [python, "scripts/sleeper_transactions.py", *refresh_flag],
        [python, "scripts/sleeper_drafts.py", *refresh_flag],
        [python, "scripts/finalize_snapshot.py"],
    ]

    if not args.skip_validation:
        steps.extend(
            [
                [python, "scripts/validate_snapshot.py"],
                [python, "scripts/validate_transactions.py"],
                [python, "scripts/validate_drafts.py"],
            ]
        )

    try:
        for step in steps:
            run_step(step)
    except subprocess.CalledProcessError as exc:
        print(f"\nPipeline failed during: {' '.join(exc.cmd)}", file=sys.stderr)
        return exc.returncode or 1

    print("\nSleeper snapshot pipeline completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
