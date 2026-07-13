from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime

from _common import LOOP_ROOT, PROJECT_ROOT, load_json


def _commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append an auditable loop progress record.")
    parser.add_argument("--work-item", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--next", required=True, dest="next_action")
    parser.add_argument("--file", action="append", default=[], dest="files_changed")
    parser.add_argument("--command", action="append", default=[], dest="commands")
    parser.add_argument("--evidence", action="append", default=[], dest="evidence_ids")
    parser.add_argument("--decision", action="append", default=[], dest="decision_ids")
    parser.add_argument("--risk-change", action="append", default=[], dest="risk_changes")
    args = parser.parse_args(argv)

    state = load_json("state/current.json")
    record = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_id": state["run_id"],
        "work_item_id": args.work_item,
        "action": args.action,
        "result": args.result,
        "files_changed": args.files_changed,
        "commands": args.commands,
        "evidence_ids": args.evidence_ids,
        "decision_ids": args.decision_ids,
        "risk_changes": args.risk_changes,
        "next_action": args.next_action,
        "commit": _commit(),
    }
    path = LOOP_ROOT / "state/progress.jsonl"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print("PROGRESS_RECORDED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
