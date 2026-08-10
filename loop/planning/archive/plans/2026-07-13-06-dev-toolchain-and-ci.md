# Dev Toolchain & CI Plan (Plan 6 of 6 · WS-8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make ADR-0008's dev-toolchain decision *real*: create the unified `pyproject.toml` (ruff + pyright + pytest + coverage config in one place), pin the dev dependencies, add a local gate runner, pre-commit hooks, and a GitHub Actions CI workflow, and wire the four placeholder quality gates (`G-FORMAT`, `G-LINT`, `G-TYPE`, `G-COVERAGE`) to their real commands with a real owning work item. This is the last of the six control-plane hardening plans.

**Architecture:** `pyproject.toml`, `.pre-commit-config.yaml`, and `.github/workflows/ci.yml` are **root** files (outside `loop/`) → they do NOT change the control-plane digest. The gate wiring, the local gate runner (`loop/scripts/run_gates.py`), the new work item, and any baseline doc live in `loop/` → those tasks end with a paired `EVD-LOOP-004` re-baseline (Plan-1 F1 invariant). Executed **directly on `main`**. The oracle is the six control gates + product 449 + self-test, now also exercised through the new runner.

**Tech Stack:** Python 3.14, `ruff` (format + lint), `pyright` (type, dev-only, already installed with Node), `pytest` (runner; runs the existing unittest-style suites natively), `coverage`, `pre-commit`; GitHub Actions on `windows-latest`. Dev dependencies declared in `pyproject.toml` `[dependency-groups].dev` (PEP 735; the app is not pip-published — it ships as a PyInstaller EXE — so no `[build-system]` is required).

## Global Constraints

- **Do NOT modify product logic or mass-edit product code.** The product-code phase (reformat/lint-fix under the new toolchain) is a *separate, deliberate* phase the user has not started. Plan 6 delivers the toolchain **infrastructure + gates + CI** and **measures** the current product-code state as tracked *adoption debt* — it does not clear it.
- The **control-plane Python I own** (`loop/scripts/**`, `loop/tests/**`) MAY be brought to toolchain-clean (ruff format + `--fix`) because it is behavior-preserving and in scope; each such edit re-baselines. Current state: 1 lint issue + 9 files unformatted (low effort).
- **Stay on branch `main`.** No branch creation/switching.
- Every task ends green: `validate_loop`, `check_traceability` (34/34), `render_status --check`, `render_backlog --check`, `check_core_boundaries`, `unittest discover -s loop/tests`; product `unittest discover -s tests` (449) + `main.py --self-test` unaffected but confirm.
- **Per-task re-baseline** for `loop/`-touching tasks only: recompute `control_plane_digest()` and surgically (byte-level, single line) replace `EVD-LOOP-004.control_plane_sha256` in `state/evidence-index.json`. Root-file-only tasks do NOT re-baseline.
- Gate commands must be **portable**: use `python -m ruff`, `python -m pyright`, `python -m coverage`, `python -m pytest` (bare `ruff`/`coverage` are not on PATH here).
- **pytest-qt / PySide6 are deferred.** The product is currently **Tkinter** (ADR-0001 PySide6 migration is pending); a Qt test binding is premature. Declare it only as a documented future `gui` group tied to the PySide6 migration — do not install it now.
- No check weakened; reconcile data to pass. No new third-party **runtime** dependency (Tkinter is stdlib; PyInstaller stays build-only in `requirements-build.txt`).

## Reference: current state (measured 2026-07-13)

- Installed: `pyright 1.1.410`, Node `v24.14.1`, `pip 26.1.2`, `ruff 0.15.21` (just installed). Missing: `pytest`, `coverage`, `pre-commit`.
- `__version__ = "1.0.0"` (`src/stock_advisor/__init__.py`). No `pyproject.toml`, no git remote, no `.github/`.
- Product ruff baseline: **35 lint** (28 F401 unused-import auto-fixable + 7 E402 import-not-at-top) and **23/29 files would reformat**. Control-plane ruff: **1 lint + 9 files**.
- Gates (`loop/quality/quality-gates.json`): `G-FORMAT`/`G-LINT`/`G-TYPE`/`G-COVERAGE` are `enabled:false`, `owning_work_item:"WI-000"` placeholder, note "real owner is a dev-tooling work item scheduled in WS-8". `G-TYPE` command is the **stale `mypy --strict src`** (must become pyright). ADR-0008 = `loop/decisions/0008-dev-toolchain.md`, 关联 REQ-028.

---

## Task 1: Unified `pyproject.toml` + pinned dev dependencies

**Files:** new `pyproject.toml` (root).

- [ ] **Step 1 — `[project]` + dev group.** `[project]`: `name="stock-advisor"`, `version="1.0.0"` (mirror `__init__.py`), `requires-python=">=3.14"`, `description`, no runtime `dependencies` (Tkinter is stdlib). Add `[dependency-groups]` `dev = [...]` with the tools pinned to the versions actually installed in Task 2 (`ruff`, `pytest`, `coverage[toml]`, `pre-commit`, `pyright`). Add a commented `# gui = ["PySide6", "pytest-qt"]  # activate with the ADR-0001 PySide6 migration` note. No `[build-system]` (app is not pip-installed).
- [ ] **Step 2 — `[tool.ruff]`.** `line-length=100` (or match the codebase), `target-version="py314"`, `[tool.ruff.lint]` `select = ["E","F","I","UP","B"]`, `[tool.ruff.lint.per-file-ignores]` grandfathering the known intentional `E402` sites (record which, with a comment) so the *config itself* is honest about the current exceptions. `[tool.ruff.format]` defaults.
- [ ] **Step 3 — `[tool.pyright]`.** `include = ["src","loop/scripts","main.py","build_exe.py"]`, `pythonVersion="3.14"`, `typeCheckingMode="basic"`, `reportMissingImports` handling for the src/ layout (`extraPaths=["src"]` or `executionEnvironments`). Keep it runnable-clean or record the residual count as debt (do not chase strict on product code now).
- [ ] **Step 4 — `[tool.pytest.ini_options]` + `[tool.coverage.*]`.** `testpaths=["tests","loop/tests"]`, sensible `addopts`. `[tool.coverage.run]` `source=["src"]`, `branch=true`; `[tool.coverage.report]` matching the `quality/convergence.json` thresholds referenced by G-COVERAGE.
- [ ] **Step 5 — Validate the TOML parses** (`python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"`) and `python -m ruff check --show-settings` picks up the config. Root-only → **no re-baseline**. Commit `build: add unified pyproject.toml (ruff/pyright/pytest/coverage config + pinned dev group)`.

## Task 2: Install + validate the toolchain; clean control-plane Python; record product baseline

**Files:** `loop/scripts/**` + `loop/tests/**` (control-plane clean-up), new `loop/quality/TOOLCHAIN_BASELINE.md` (adoption-debt record), `pyproject.toml` (fill exact pins).

- [ ] **Step 1 — Install** the dev group (`python -m pip install --group dev`, or fall back to explicit pinned installs if `--group` is unsupported) and record exact resolved versions back into `[dependency-groups].dev`.
- [ ] **Step 2 — Validate each tool runs** on the config: `python -m ruff format --check .` and `python -m ruff check .` (capture the product baseline counts), `python -m pyright` (capture status), `python -m pytest tests -q` (**must collect + pass all 449** — parity with `unittest discover`), `python -m pytest loop/tests -q` (33), `python -m coverage run -m pytest tests` + `python -m coverage report` (capture %). If pytest parity fails, diagnose (do not change product logic) before proceeding.
- [ ] **Step 3 — Clean the control-plane Python only.** `python -m ruff check --fix loop/scripts loop/tests` + `python -m ruff format loop/scripts loop/tests`. Re-run the six loop gates + confirm loop tests still pass (behavior-preserving). Do **not** touch `src/`.
- [ ] **Step 4 — Record the product adoption debt.** New `loop/quality/TOOLCHAIN_BASELINE.md`: the measured product `ruff`/`pyright`/coverage numbers, the statement "product-code remediation is deferred to the product-code phase, owned by WI-<dev-tooling>", and the enablement criteria for the four gates. This is the honest bridge between "toolchain ready" and "product not yet compliant".
- [ ] **Step 5 — Re-baseline** (loop/ touched) + gates green; commit `loop: adopt toolchain on control-plane Python + record product adoption baseline`.

## Task 3: Wire the four quality gates to real commands + a real owning work item

**Files:** `loop/quality/quality-gates.json`, `loop/planning/work-items.json` (+ its trace/register rows), `loop/quality/QUALITY_GATES.md`, back-ref in `loop/decisions/0008-dev-toolchain.md`.

- [ ] **Step 1 — Dev-tooling work item.** Add `WI-0NN "dev toolchain & CI"` (next free id) under REQ-028 (the toolchain requirement ADR-0008 already cites), with the traceability row + any register entry the checkers require (mirror an existing WI so `check_traceability` stays 34/34 and `validate_loop` passes). Point `G-FORMAT/G-LINT/G-TYPE/G-COVERAGE.owning_work_item` at it; drop the WI-000-placeholder `note`.
- [ ] **Step 2 — Correct the commands.** `G-FORMAT` → `["python","-m","ruff","format","--check","."]`; `G-LINT` → `["python","-m","ruff","check","."]`; `G-TYPE` → replace `mypy --strict src` with `["python","-m","pyright"]`; `G-COVERAGE` → `["python","-m","coverage","run","-m","pytest"]` + `["python","-m","coverage","report","--fail-under=85"]`. Keep them `enabled:false` with a precise `enablement_criteria` field/note: "enable once product adoption debt in `TOOLCHAIN_BASELINE.md` is cleared (product-code phase)". If the schema rejects a new field, put it in the existing `note`.
- [ ] **Step 3 — ADR + docs.** Add a `关联` back-ref to the new WI in ADR-0008; update `QUALITY_GATES.md` to describe the four gates' commands, their deferred-enablement status, and the runner (Task 4). Fix the stale "WS-8 (Plan 5)" wording to "WS-8 (Plan 6)".
- [ ] **Step 4 — Re-baseline** + gates green (incl. traceability 34/34 with the new WI); commit `loop: wire G-FORMAT/LINT/TYPE/COVERAGE to real commands + dev-tooling work item`.

## Task 4: Local gate runner + pre-commit + GitHub Actions CI

**Files:** new `loop/scripts/run_gates.py` (+ a loop test), new `.pre-commit-config.yaml` (root), new `.github/workflows/ci.yml` (root).

- [ ] **Step 1 — Local gate runner.** `loop/scripts/run_gates.py`: read `loop/quality/quality-gates.json`, run each `enabled` gate's `commands` in `order`, honor per-gate `environment`, **degrade gracefully** when a tool is missing (report `SKIPPED: <tool> not installed` rather than crashing), append a run summary to `loop/state/gate-runs.jsonl`, print a `RUN_GATES_OK`/`RUN_GATES_FAIL` line, exit non-zero on any failure. Add `--include-disabled`/`--report-only` to exercise the four deferred gates in report mode. A focused loop test covers parse + a stub run.
- [ ] **Step 2 — pre-commit.** `.pre-commit-config.yaml`: `ruff` (format) + `ruff` (check) hooks pinned to the ruff version; a local hook for `validate_loop.py` is optional. Document `pre-commit install` in the runner/README (do not auto-install the git hook — that mutates `.git/`).
- [ ] **Step 3 — GitHub Actions CI.** `.github/workflows/ci.yml`: `runs-on: windows-latest` (Tkinter works headless on Windows; matches the target), `python-version: "3.14"`, install the dev group, then run `ruff format --check`, `ruff check`, `pyright`, `pytest tests loop/tests`, `coverage`, and `python loop/scripts/run_gates.py`. Note in a comment that it activates when a remote is added.
- [ ] **Step 4 — Re-baseline** (run_gates.py + its test are in `loop/`; pre-commit + CI are root, same commit) + gates green; run `run_gates.py` itself and confirm `RUN_GATES_OK`. Commit `loop: local gate runner; ci: pre-commit + GitHub Actions (windows) toolchain workflow`.

## Task 5: Close-out

- [ ] Append a `record_progress.py --work-item WI-000` line summarizing Plan 6 (WS-8); recompute the digest and update `EVD-LOOP-004`; run the FULL gate set + the new `run_gates.py` + 449 + self-test; commit `loop: record Plan 6 (dev toolchain & CI) progress + final re-baseline`. This completes 6/6 plans.

## Self-Review

- **Spec coverage (WS-8):** Task 1 = the unified pyproject config the user asked for; Task 2 = install + validate (real evidence the config works) + honest product baseline; Task 3 = wire the four placeholder gates + real owner + the mypy→pyright correction; Task 4 = runner + pre-commit + CI; Task 5 = close-out. ADR-0008 is realized, not just documented.
- **Constraint safety:** product logic/code is untouched — only the control-plane Python I own is formatted, and only tool *config/wiring* is added. The product's ruff/pyright debt is measured and explicitly deferred with an owner, not silently ignored or force-fixed.
- **Green-ness:** the four gates stay `enabled:false` (they would fail on the un-remediated product code); enabling is gated on the documented adoption-debt cleanup. The enabled gates (G-LOOP/G-CORE/G-TRACE) and product 449 + self-test remain green throughout; pytest parity with unittest is verified before relying on it.
- **Ordering & re-baseline:** config (1, root) → install/validate/clean (2, loop) → gate wiring (3, loop) → runner/CI (4, loop+root) → close-out (5, loop). Re-baseline on 2/3/4/5; Task 1 is root-only.
- **Platform reality:** CI is `windows-latest` and pytest-qt/PySide6 are deferred because the product is Tkinter today (ADR-0001 migration pending) — the toolchain matches the *actual* stack, with the Qt path documented for the migration.
