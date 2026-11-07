#!/usr/bin/env python3
"""Read-only CLI for the EduShield Excel-derived backlog. stdlib only."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "backlog" / "features.csv"
GAPS = ROOT / "backlog" / "gap_assessment.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def all_rows() -> list[dict[str, str]]:
    features = read_csv(FEATURES)
    gaps = {r["id"]: r for r in read_csv(GAPS)}
    return [
        {**r, **{k: v for k, v in gaps.get(r["id"], {}).items() if k not in ("id", "priority")}}
        for r in features
    ]


def show(id_: str) -> int:
    match = next((r for r in all_rows() if r["id"].upper() == id_.upper()), None)
    if not match:
        print(f"Unknown ID: {id_}")
        return 2
    for key, val in match.items():
        print(f"{key}: {val}")
    return 0


def list_rows(priority: str | None, assessment: str | None, module: str | None) -> int:
    rows = all_rows()
    if priority:
        rows = [r for r in rows if r["priority"] == priority]
    if assessment:
        rows = [r for r in rows if r["initial_assessment"] == assessment]
    if module:
        rows = [r for r in rows if module.casefold() in r["module"].casefold()]
    for r in rows:
        print(f"{r['id']:9s} {r['priority']:2s} {r['initial_assessment']:17s} {r['source_title']}")
    print(f"Rows: {len(rows)}")
    return 0


def stats() -> int:
    rows = all_rows()
    for name, col in (
        ("Priority", "priority"),
        ("Initial report assessment", "initial_assessment"),
        ("Verified status", "verified_status"),
    ):
        print(name)
        for label, n in sorted(Counter((r.get(col) or "(not audited)") for r in rows).items()):
            print(f"  {label}: {n}")
    print(f"Total IDs: {len(rows)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Query EduShield feature catalog (read-only)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("stats", help="Count priorities and provisional statuses")
    p_show = commands.add_parser("show", help="Detail one feature")
    p_show.add_argument("id")
    p_list = commands.add_parser("list", help="Filter feature catalog")
    p_list.add_argument("--priority", choices=("P0", "P1", "P2"))
    p_list.add_argument(
        "--assessment",
        choices=("reported_present", "reported_partial", "not_reported", "stack_mismatch"),
    )
    p_list.add_argument("--module", help="Substring filter")
    args = parser.parse_args()
    if args.command == "stats":
        return stats()
    if args.command == "show":
        return show(args.id)
    return list_rows(args.priority, args.assessment, args.module)


if __name__ == "__main__":
    raise SystemExit(main())
