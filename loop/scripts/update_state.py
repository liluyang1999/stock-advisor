from __future__ import annotations

import argparse
from datetime import datetime

from _common import LOOP_ROOT, atomic_write_json, load_json


VALID_STATUSES = {"initialized", "active", "verifying", "needs_human", "blocked", "complete", "failed"}
NON_TERMINAL_STATUSES = {"initialized", "active", "verifying"}
TERMINAL_STATUS_MAP = {
    "needs_human": {"needs_human"},
    "blocked": {"blocked_external", "no_safe_progress"},
    "complete": {"success"},
    "failed": {"changes_requested", "cancelled", "superseded", "failed"},
}


def validate_transition(state: dict[str, object], status: str, terminal_state: str | None) -> list[str]:
    errors: list[str] = []
    allowed_terminal_states = set(load_json("loop.json")["terminal_states"])
    if terminal_state is not None and terminal_state not in allowed_terminal_states:
        errors.append(f"unknown terminal state: {terminal_state}")
    if status in NON_TERMINAL_STATUSES and terminal_state is not None:
        errors.append("non-terminal status requires terminal_state=null")
    if status in TERMINAL_STATUS_MAP and terminal_state not in TERMINAL_STATUS_MAP[status]:
        errors.append(f"status {status} requires one of {sorted(TERMINAL_STATUS_MAP[status])}")
    if status == "complete":
        metrics = load_json("state/metrics.json")
        required_streak = load_json("config.json")["quality_policy"]["consecutive_full_green_runs_for_release"]
        if not state.get("release_candidate") or not metrics["release"]["ready"]:
            errors.append("success requires release_candidate=true and release.ready=true")
        if metrics["release"]["full_green_streak"] < required_streak:
            errors.append("success requires the configured consecutive full-green streak")
        if state.get("blocker_ids") or state.get("pending_decision_ids"):
            errors.append("success requires zero blockers and pending decisions")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atomically update selected loop state fields.")
    parser.add_argument("--status", choices=sorted(VALID_STATUSES))
    parser.add_argument("--phase")
    parser.add_argument("--active-milestone")
    parser.add_argument("--active-work-item")
    parser.add_argument("--next", action="append", dest="next_actions")
    parser.add_argument("--terminal-state")
    parser.add_argument("--clear-terminal-state", action="store_true")
    args = parser.parse_args(argv)

    state = load_json("state/current.json")
    target_status = args.status or state["status"]
    target_terminal = None if args.clear_terminal_state else state.get("terminal_state")
    if args.terminal_state is not None:
        target_terminal = args.terminal_state
    if errors := validate_transition(state, target_status, target_terminal):
        parser.error("; ".join(errors))
    state["status"] = target_status
    if args.phase:
        state["phase"] = args.phase
    if args.active_milestone:
        state["active_milestone_id"] = args.active_milestone
    if args.active_work_item:
        state["active_work_item_id"] = args.active_work_item
    if args.next_actions is not None:
        state["next_actions"] = args.next_actions
    state["terminal_state"] = target_terminal
    state["last_updated"] = datetime.now().astimezone().isoformat(timespec="seconds")
    atomic_write_json(LOOP_ROOT / "state/current.json", state)
    print("STATE_UPDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
