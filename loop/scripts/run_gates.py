"""Run the loop quality gates declared in ``quality/quality-gates.json``.

This is a thin, deterministic orchestrator: it reads the gate definitions, runs each gate's
commands in ``order`` from the project root, applies any per-gate environment overrides, and
reports ``PASS`` / ``FAIL`` / ``SKIP`` plus a final ``RUN_GATES_OK`` / ``RUN_GATES_FAIL`` line.

Design notes:

* It **does not** write ``state/gate-runs.jsonl``. That file is the curated, schema-validated
  evidence log tied to ``EVD-LOOP-*`` records (and is part of the control-plane digest); appending
  to it on every run would churn the digest and pollute the evidence trail. Formal gate runs are
  recorded deliberately at close-out, not by this runner.
* Missing dev tools **degrade to SKIP**, not a crash: a gate whose command needs an uninstalled
  module/executable is skipped with a clear message so the runner is usable on a fresh checkout.
  That leniency is for humans on a fresh clone — **CI must pass ``--strict``**, which counts a SKIP
  as a failure. Without it a tool that failed to install makes its gate vanish silently and the
  pipeline still goes green, which is the one failure mode a gate runner must never have.
* Release-phase gates (``G-TRACE`` runs release traceability, ``G-RELEASE`` is the human release
  gate) are **excluded by default** and included with ``--release``. Release traceability is
  intentionally red until release, so running it by default would make every dev/CI run fail.
* By default only ``enabled`` gates run and any failure exits non-zero. ``--report-only`` also
  exercises the disabled tool gates (G-FORMAT/G-LINT/G-TYPE/G-COVERAGE) informationally and never
  fails the process, which is how the deferred gates are surfaced before their product-code debt
  is cleared (see ``quality/TOOLCHAIN_BASELINE.md``).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
from typing import Any

from _common import PROJECT_ROOT, load_json

_PYTHON_NAMES = {"python", "python3", "py"}

# Gates whose green state belongs to release time, not every dev/CI run. G-TRACE runs
# `check_traceability --release` (intentionally red until release; see the loop test
# test_release_traceability_is_intentionally_not_green_yet); G-RELEASE is the human release gate.
RELEASE_PHASE = frozenset({"G-TRACE", "G-RELEASE"})


def required_tool(command: list[str]) -> tuple[str, str] | None:
    """Return ``(kind, name)`` of the external tool a command needs, or None if always available.

    ``kind`` is ``"module"`` (checked with importlib) or ``"exe"`` (checked with shutil.which).
    A ``python -m <module>`` command depends on ``<module>``; anything else depends on argv[0].
    """

    if not command:
        return None
    if command[0] in _PYTHON_NAMES and len(command) >= 3 and command[1] == "-m":
        return ("module", command[2])
    if command[0] in _PYTHON_NAMES:
        return None  # bare `python script.py` — the interpreter is running us
    return ("exe", command[0])


def _tool_available(tool: tuple[str, str]) -> bool:
    kind, name = tool
    if kind == "module":
        try:
            return importlib.util.find_spec(name) is not None
        except ImportError, ValueError:
            return False
    return shutil.which(name) is not None


def run_gate(gate: dict[str, Any]) -> tuple[str, str]:
    """Run one gate's commands. Returns ``(status, detail)`` where status is PASS/FAIL/SKIP."""

    commands = gate.get("commands") or []
    if not commands or all(not command for command in commands):
        return ("SKIP", "no command defined")
    overrides = {str(k): str(v) for k, v in gate.get("environment", {}).items()}
    env = {**os.environ, **overrides}
    for command in commands:
        if not command:
            continue
        tool = required_tool(command)
        if tool is not None and not _tool_available(tool):
            return ("SKIP", f"{tool[1]} not installed")
        try:
            result = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return ("SKIP", f"{command[0]} not found")
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
            return ("FAIL", f"{' '.join(command)} -> exit {result.returncode}: {' | '.join(tail)}")
    return ("PASS", "")


def select_gates(
    gates: list[dict[str, Any]],
    *,
    only: list[str],
    include_disabled: bool,
    report_only: bool,
    release: bool,
) -> list[dict[str, Any]]:
    """Resolve which gates to run given the CLI options (pure; unit-testable)."""

    ordered = sorted(gates, key=lambda gate: gate["order"])
    if only:
        wanted = set(only)
        return [gate for gate in ordered if gate["id"] in wanted]
    selected = []
    for gate in ordered:
        if gate["id"] in RELEASE_PHASE and not release:
            continue
        if not gate.get("enabled") and not (include_disabled or report_only):
            continue
        selected.append(gate)
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the loop quality gates.")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="also run disabled gates informationally; never fail the process",
    )
    parser.add_argument(
        "--include-disabled",
        action="store_true",
        help="run disabled gates too and let their failures count",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="include release-phase gates (G-TRACE, G-RELEASE), intentionally red until release",
    )
    parser.add_argument(
        "--gate",
        action="append",
        default=[],
        metavar="ID",
        help="run only these gate id(s), bypassing the enabled/release filters; may be repeated",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat SKIP as failure — for CI, where every declared tool must really be installed",
    )
    args = parser.parse_args(argv)

    gates = select_gates(
        load_json("quality/quality-gates.json")["gates"],
        only=args.gate,
        include_disabled=args.include_disabled,
        report_only=args.report_only,
        release=args.release,
    )

    ran = failed = skipped = 0
    for gate in gates:
        enabled = bool(gate.get("enabled"))
        status, detail = run_gate(gate)
        ran += 1
        suffix = f" ({detail})" if detail else ""
        marker = "" if enabled else " [disabled]"
        print(f"[{gate['id']:<11}] {status}{marker}{suffix}")
        counts_against_us = enabled or args.include_disabled
        if status == "FAIL" and counts_against_us:
            failed += 1
        elif status == "SKIP":
            skipped += 1
            # --strict：SKIP 意味着这一关根本没跑（工具没装成）。本地那是便利，CI 里那是
            # 「毫无根据的绿」——一个装不上的 pyright 会让 G-TYPE 悄悄消失而流水线照样通过。
            if args.strict and counts_against_us:
                failed += 1

    summary = f"ran={ran} failed={failed} skipped={skipped}"
    if failed and not args.report_only:
        print(f"RUN_GATES_FAIL {summary}")
        return 1
    print(f"RUN_GATES_OK {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
