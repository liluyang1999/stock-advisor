from __future__ import annotations

import argparse
import sys

from _common import LOOP_ROOT, load_json


def check_status() -> list[str]:
    actual = (LOOP_ROOT / "STATUS.md").read_text(encoding="utf-8")
    expected = render()
    if actual == expected:
        return []
    return ["STATUS.md differs from the authoritative machine render; run render_status.py --write"]


def render() -> str:
    state = load_json("state/current.json")
    metrics = load_json("state/metrics.json")
    config = load_json("config.json")
    work_items = {
        row["id"]: row for row in load_json("planning/work-items.json")["work_items"]
    }
    control_plane = metrics["control_plane"]
    active = work_items[state["active_work_item_id"]]
    lines = [
        "# Loop 状态（机器渲染）",
        "",
        f"- Objective: `{state['objective_id']}`",
        f"- Phase: `{state['phase']}`",
        f"- Status: `{state['status']}`",
        f"- Milestone: `{state['active_milestone_id']}`",
        f"- Selected work item: `{active['id']}` — {active['title']} (`{active['status']}`)",
        f"- Baseline: `{state['baseline_commit']}`",
        f"- Dirty worktree: `{str(state['dirty_worktree']).lower()}`",
        f"- Current GUI / target GUI: `Tkinter / {config['target_stack']['gui']}`",
        f"- Runtime font target: `{config['target_stack']['runtime_font']}`",
        f"- Tests: `{metrics['tests']['passed']}/{metrics['tests']['methods']}`",
        f"- Loop tooling tests: `{control_plane['tool_tests_passed']}/{control_plane['tool_tests_total']}`",
        f"- Loop schemas: `{control_plane['schema_documents_validated']}`",
        f"- Traceability: `{control_plane['requirements_traced']}/{metrics['engineering']['requirements_total']}`",
        f"- Coverage: `{metrics['coverage']['statement']}`",
        f"- Release candidate: `{str(state['release_candidate']).lower()}`",
        f"- Latest gate run: `{state['latest_gate_run_id']}`",
        "",
        "## Next actions",
        "",
    ]
    lines.extend(f"- {action}" for action in state["next_actions"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render or check loop status.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        errors = check_status()
        if errors:
            for error in errors:
                print(f"STATUS_ERROR {error}", file=sys.stderr)
            return 1
        print("STATUS_OK")
        return 0
    content = render()
    if args.write:
        path = LOOP_ROOT / "STATUS.md"
        temp = path.with_name(".STATUS.md.tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)
        print(f"STATUS_WRITTEN {path}")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
