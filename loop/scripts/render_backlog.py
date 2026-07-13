from __future__ import annotations

import argparse
import json
import sys

from _common import LOOP_ROOT, atomic_write_json, load_json

STATUS_ORDER = (
    "in_progress",
    "verifying",
    "ready",
    "proposed",
    "accepted",
    "blocked",
    "deferred",
    "cancelled",
)


def project() -> dict[str, object]:
    rows = load_json("planning/work-items.json")["work_items"]
    counts = {status: 0 for status in STATUS_ORDER}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    summary = {
        status: count
        for status, count in counts.items()
        if count or status in {"verifying", "ready", "proposed", "accepted", "blocked"}
    }
    next_ready = next((row["id"] for row in rows if row["status"] == "ready"), None)
    return {
        "$schema": "../schemas/backlog.schema.json",
        "schema_version": "1.0.0",
        "source": "../planning/work-items.json",
        "summary": summary,
        "ordered_ids": [row["id"] for row in rows],
        "next_ready": next_ready,
        "note": "planning/work-items.json is authoritative; this file is a queue projection",
    }


def check_backlog() -> list[str]:
    actual = load_json("state/backlog.json")
    if actual == project():
        return []
    return [
        "state/backlog.json differs from planning/work-items.json; run render_backlog.py --write"
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render or check the work-item queue projection.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        errors = check_backlog()
        if errors:
            for error in errors:
                print(f"BACKLOG_ERROR {error}", file=sys.stderr)
            return 1
        print("BACKLOG_OK")
        return 0
    payload = project()
    if args.write:
        atomic_write_json(LOOP_ROOT / "state/backlog.json", payload)
        print("BACKLOG_WRITTEN")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
