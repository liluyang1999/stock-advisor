"""Assert test coverage per dimension against ``quality/convergence.json``.

``coverage report --fail-under=N`` floors coverage.py's *combined* statement+branch total:
one blended number. The project's actual coverage policy is four separate floors -- overall
statement/branch and core(domain) statement/branch -- so the combined total can clear
``--fail-under`` while individual dimensions sit below their floor. That is not theoretical:
measured 2026-07-15 the combined total was 86.8% (passing ``--fail-under=85``) while all four
documented thresholds failed. A gate wired that way certifies a green it never checked.

This checker asserts each dimension separately, so G-COVERAGE proves exactly what its
``pass_condition`` claims.

Input is the JSON emitted by ``coverage json`` (per-file statement/branch counters).
Thresholds are read from ``quality/convergence.json`` and are never duplicated here: that
document stays the single source of truth for the policy.

Definitions (kept identical to coverage.py's own totals):

* ``statement% = (sum(num_statements) - sum(missing_lines)) / sum(num_statements)``
* ``branch%    = (sum(num_branches)   - sum(missing_branches)) / sum(num_branches)``
* ``overall``  = every file in the report; ``core`` = files inside a ``domain`` package.

Exit codes: ``0`` every measured dimension passes; ``1`` at least one dimension is below its
floor; ``2`` the report or the thresholds could not be read (an operator error, not a
coverage regression -- the two are worth telling apart).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple

from _common import LOOP_ROOT, PROJECT_ROOT, load_json

DEFAULT_REPORT = "build/coverage.json"
CONVERGENCE = "quality/convergence.json"

# The protected core (architecture/core-module-manifest.json): pure domain logic, held to a
# higher floor than the codebase average.
CORE_DIRECTORY = "domain"

# Dimension name -> the key that carries its floor in convergence.json's `coverage` object.
# Values there are fractions in [0,1]. No threshold is ever written as a literal in this file.
THRESHOLD_KEYS = {
    "overall_statement": "overall_statement_min",
    "overall_branch": "overall_branch_min",
    "core_statement": "core_statement_min",
    "core_branch": "core_branch_min",
}

# convergence.json also declares qt_controller_statement_min / qt_controller_branch_min.
# ADR-0001's Tkinter->PySide6 migration has not landed, so no Qt controller exists and no file
# can be attributed to that dimension. It is printed as an explicit SKIP every run rather than
# silently dropped -- and it is never counted as a pass.
UNMEASURABLE = ("qt_controller_statement", "qt_controller_branch")
UNMEASURABLE_REASON = "no Qt controller exists yet -- ADR-0001 PySide6 migration pending"

# Width of the dimension column: the longest name printed, measured or skipped.
_NAME_WIDTH = max(len(name) for name in (*THRESHOLD_KEYS, *UNMEASURABLE))

# (scope, statement/branch) -> the report counters the ratio is built from.
_RATIOS = (
    ("statement", "num_statements", "missing_lines"),
    ("branch", "num_branches", "missing_branches"),
)
_COUNTERS = ("num_statements", "missing_lines", "num_branches", "missing_branches")


class CoverageError(Exception):
    """An input the checker cannot honestly measure from. Reported, never raised at a user."""


class Dimension(NamedTuple):
    name: str
    measured: float
    threshold: float
    covered: int
    total: int

    @property
    def passed(self) -> bool:
        # Compare the exact ratio, never the rounded display value: 0.8996 renders as "90.0%"
        # at coverage.py's configured precision but must still fail a 0.90 floor.
        return self.measured >= self.threshold


def normalize(name: str) -> str:
    """coverage.py keys paths with the host separator; on Windows that is a backslash."""

    return name.replace("\\", "/")


def load_thresholds(path: Path | None = None) -> dict[str, float]:
    """Read the four coverage floors from ``quality/convergence.json``.

    ``path`` exists so tests can prove the numbers really do come from the document -- tamper
    a copy, watch the verdict move. Production callers pass nothing and always get the
    control-plane file. This is deliberately *not* a CLI flag: a gate run must not be
    redirectable at a laxer policy.
    """

    source = LOOP_ROOT / CONVERGENCE if path is None else path
    try:
        document = (
            load_json(CONVERGENCE) if path is None else json.loads(path.read_text(encoding="utf-8"))
        )
    except OSError as exc:
        raise CoverageError(f"cannot read thresholds from {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CoverageError(f"thresholds file {source} is not valid JSON: {exc}") from exc

    section = document.get("coverage") if isinstance(document, dict) else None
    if not isinstance(section, dict):
        raise CoverageError(f"{source} has no 'coverage' object")
    thresholds: dict[str, float] = {}
    for name, key in THRESHOLD_KEYS.items():
        value = section.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise CoverageError(
                f"{source} coverage.{key} must be a fraction in [0,1], got {value!r}"
            )
        thresholds[name] = float(value)
    return thresholds


def load_files(report: Path) -> dict[str, Any]:
    """Load the per-file section of a ``coverage json`` report."""

    resolved = report if report.is_absolute() else PROJECT_ROOT / report
    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CoverageError(
            f"coverage report not found: {resolved} -- generate it with "
            f"'python -m coverage run -m unittest discover -s tests' then "
            f"'python -m coverage json -q -o {DEFAULT_REPORT}'"
        ) from exc
    except OSError as exc:
        raise CoverageError(f"cannot read coverage report {resolved}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CoverageError(f"coverage report {resolved} is not valid JSON: {exc}") from exc

    files = document.get("files") if isinstance(document, dict) else None
    if not isinstance(files, dict) or not files:
        raise CoverageError(
            f"coverage report {resolved} has no non-empty 'files' object "
            "-- it is not a 'coverage json' report, or it measured nothing"
        )
    return files


def core_files(files: dict[str, Any]) -> list[str]:
    """Report keys that live inside a ``domain`` package directory.

    Matches a path *component*, not a substring: a hypothetical ``services/domain_rules.py``
    is not core, and must not be able to inflate the core numbers by name alone.
    """

    return sorted(name for name in files if CORE_DIRECTORY in normalize(name).split("/")[:-1])


def _totals(files: dict[str, Any], selected: list[str]) -> dict[str, int]:
    totals: dict[str, int] = {counter: 0 for counter in _COUNTERS}
    for name in selected:
        entry = files[name]
        summary = entry.get("summary") if isinstance(entry, dict) else None
        if not isinstance(summary, dict):
            raise CoverageError(f"coverage report entry {name!r} has no 'summary' object")
        for counter in _COUNTERS:
            value = summary.get(counter)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CoverageError(
                    f"coverage report entry {name!r} has an invalid {counter}: {value!r}"
                )
            totals[counter] += value
    return totals


def evaluate(files: dict[str, Any], thresholds: dict[str, float]) -> list[Dimension]:
    """Measure every threshold-backed dimension. Raises CoverageError if one cannot be measured."""

    core = core_files(files)
    if not core:
        raise CoverageError(
            f"coverage report contains no '{CORE_DIRECTORY}/' files: the core dimensions "
            "cannot be measured, so this report cannot certify the coverage policy"
        )
    dimensions: list[Dimension] = []
    for scope, selected in (("overall", sorted(files)), ("core", core)):
        totals = _totals(files, selected)
        for kind, total_key, missing_key in _RATIOS:
            total = totals[total_key]
            if total == 0:
                raise CoverageError(
                    f"{scope}_{kind}: the report counts zero {kind}s"
                    + (
                        " -- branch coverage needs [tool.coverage.run] branch = true"
                        if kind == "branch"
                        else ""
                    )
                )
            covered = total - totals[missing_key]
            name = f"{scope}_{kind}"
            dimensions.append(Dimension(name, covered / total, thresholds[name], covered, total))
    return dimensions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assert coverage per dimension against quality/convergence.json thresholds."
    )
    parser.add_argument(
        "report",
        nargs="?",
        default=DEFAULT_REPORT,
        help=f"the 'coverage json' report to check (default: {DEFAULT_REPORT}, "
        "relative paths resolve against the project root)",
    )
    args = parser.parse_args(argv)

    try:
        files = load_files(Path(args.report))
        dimensions = evaluate(files, load_thresholds())
    except CoverageError as exc:
        print(f"COVERAGE_ERROR {exc}", file=sys.stderr)
        return 2

    for dimension in dimensions:
        verdict = "PASS" if dimension.passed else "FAIL"
        print(
            f"{dimension.name:<{_NAME_WIDTH}} {dimension.measured:8.2%} >= "
            f"{dimension.threshold:7.2%}  {verdict}  ({dimension.covered}/{dimension.total})"
        )
    for name in UNMEASURABLE:
        print(f"{name:<{_NAME_WIDTH}} {'-':>8}    {'-':>7}  SKIP  {UNMEASURABLE_REASON}")

    failures = [dimension for dimension in dimensions if not dimension.passed]
    if failures:
        for dimension in failures:
            print(
                f"COVERAGE_ERROR {dimension.name} {dimension.measured:.2%} is below the required "
                f"{dimension.threshold:.2%} ({dimension.covered}/{dimension.total} covered; "
                f"floor from {CONVERGENCE} coverage.{THRESHOLD_KEYS[dimension.name]})",
                file=sys.stderr,
            )
        return 1

    measured = " ".join(
        f"{dimension.name}={dimension.measured:.2%}/{dimension.threshold:.0%}"
        for dimension in dimensions
    )
    print(
        f"COVERAGE_OK {measured} files={len(files)} core_files={len(core_files(files))} "
        f"skipped={','.join(UNMEASURABLE)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
