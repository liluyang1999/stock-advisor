# src Package Restructure Implementation Plan (Plan 2 of 6 · WS-R)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the flat 23-module `src/stock_advisor/` package into functional subpackages (`domain/`, `data/`, `services/`, `ui/`) — a **behavior-preserving** move (relocate files + update imports), with the 449 product tests staying green and no logic changed.

**Architecture:** Move each module into its layer subpackage, then rewrite imports: `domain/` is self-contained (its internal `from .x` imports are untouched); `data/`, `services/`, `ui/` get their cross-layer relative imports rewritten to `from ..<layer>.<mod>`; tests/`main.py`/`build_exe.py` get their absolute `from stock_advisor.<mod>` rewritten to `from stock_advisor.<layer>.<mod>`. The loop control plane's core-module manifest and boundary check are updated to the new paths in a second task.

**Tech Stack:** Python 3.12+ standard library (product runtime unchanged); `unittest` (449 tests) as the behavior-preservation oracle; `git mv` for history-preserving moves.

## Global Constraints

- **No logic changes.** Only file locations and `import` statements change. Every one of the 449 product tests must still pass, `python main.py --self-test` must print `SELF_TEST_OK`, and `python -m compileall -q main.py build_exe.py src/stock_advisor` must be clean.
- Product runtime stays standard-library only; the pure core stays pure (no Qt/network/filesystem in `domain/`).
- Keep module **filenames unchanged** (only their directory changes) and use `git mv` so history follows.
- Do not reorder or rewrite code inside the moved files beyond the `import` lines.
- Two-phase: Task 1 touches only product files (`src/`, `tests/`, `main.py`, `build_exe.py`); Task 2 touches only `loop/`. Between them, `check_core_boundaries` is expected RED (stale manifest) — that is normal and Task 2 fixes it.

## Module → subpackage map (authoritative)

```
domain/   (12, pure core — self-contained): models symbols engine policy backtest
          screener presets compare alerts chart input_validate formatting
data/     (2):  data_provider  sample_data
services/ (2):  workflow  store
ui/       (6):  app  layout  theme  view_text  view_format  manual
```

## Target File Structure

```
src/stock_advisor/
  __init__.py                 (existing; keep as-is unless it imports moved modules)
  domain/__init__.py          (new, empty)
    models.py symbols.py engine.py policy.py backtest.py screener.py
    presets.py compare.py alerts.py chart.py input_validate.py formatting.py
  data/__init__.py            (new, empty)
    data_provider.py sample_data.py
  services/__init__.py        (new, empty)
    workflow.py store.py
  ui/__init__.py              (new, empty)
    app.py layout.py theme.py view_text.py view_format.py manual.py
```

## Cross-subpackage import rewrites (the ONLY import edits inside `src/`)

`domain/` modules: **no changes** (verified — every domain module imports only sibling domain modules; `from .models`, `from .policy`, `from .engine`, `from .formatting` all stay).

`data/data_provider.py`: `from .models` → `from ..domain.models`
`data/sample_data.py`: `from .engine` → `from ..domain.engine`; `from .models` → `from ..domain.models`; `from .symbols` → `from ..domain.symbols`

`services/workflow.py`: `from .data_provider` → `from ..data.data_provider`; `from .engine|.models|.policy|.screener|.symbols` → `from ..domain.<mod>`
`services/store.py`: `from .alerts|.models|.symbols` → `from ..domain.<mod>`

`ui/app.py`: `from . import store` → `from ..services import store`; `from .workflow` → `from ..services.workflow`; `from .data_provider` → `from ..data.data_provider`; `from .sample_data` → `from ..data.sample_data`; `from .alerts|.backtest|.chart|.compare|.engine|.models|.policy|.presets|.screener|.symbols|.formatting|.input_validate` → `from ..domain.<mod>`; `from .theme|.view_text|.view_format|.layout` → **unchanged** (ui siblings)
`ui/manual.py`: `from .app` → unchanged (ui sibling); `from .presets` → `from ..domain.presets`; `from .screener` → `from ..domain.screener`
`ui/view_format.py`: `from .formatting|.models|.symbols` → `from ..domain.<mod>`; `from .theme` → unchanged
`ui/view_text.py`: `from .formatting|.models|.policy|.symbols` → `from ..domain.<mod>`; `from .theme` → unchanged
`ui/theme.py`, `ui/layout.py`: no relative imports (stdlib only) — no changes.

---

## Task 1: Move product modules into subpackages + rewrite imports

**Files:** `git mv` all 22 modules into the 4 subpackages (map above); create 4 `__init__.py`; edit imports in `data/*`, `services/*`, `ui/*` (rules above); edit absolute imports in every `tests/*.py` that imports `stock_advisor`, plus `main.py` and `build_exe.py`.

**Interfaces:** Produces the new import paths `stock_advisor.domain.*`, `stock_advisor.data.*`, `stock_advisor.services.*`, `stock_advisor.ui.*`. External consumers (tests/main/build_exe) must use these.

- [ ] **Step 1: Baseline green** — run `python -m unittest discover -s tests 2>&1 | tail -2` (expect `OK`, 449) and `python main.py --self-test` (expect `SELF_TEST_OK`). Record the counts.

- [ ] **Step 2: Create subpackages and move files with `git mv`**

```bash
cd src/stock_advisor
for d in domain data services ui; do mkdir -p $d; : > $d/__init__.py; git add $d/__init__.py; done
# domain (12)
for m in models symbols engine policy backtest screener presets compare alerts chart input_validate formatting; do git mv $m.py domain/$m.py; done
# data (2)
for m in data_provider sample_data; do git mv $m.py data/$m.py; done
# services (2)
for m in workflow store; do git mv $m.py services/$m.py; done
# ui (6)
for m in app layout theme view_text view_format manual; do git mv $m.py ui/$m.py; done
```

- [ ] **Step 3: Rewrite intra-`src` imports** per the "Cross-subpackage import rewrites" section. `domain/` files need NO edits. Edit `data/data_provider.py`, `data/sample_data.py`, `services/workflow.py`, `services/store.py`, `ui/app.py`, `ui/manual.py`, `ui/view_format.py`, `ui/view_text.py` exactly as listed. Then run `python -m compileall -q src/stock_advisor` and fix any `ImportError`/`ModuleNotFoundError` it surfaces (the compiler + tests are the oracle — iterate until clean).

- [ ] **Step 4: Rewrite absolute imports in tests/main/build_exe.** In every `tests/*.py`, `main.py`, and `build_exe.py`, replace `from stock_advisor.<mod> import …` and `import stock_advisor.<mod>` with the `<layer>` inserted per the module→subpackage map (e.g. `from stock_advisor.models` → `from stock_advisor.domain.models`; `from stock_advisor.workflow` → `from stock_advisor.services.workflow`; `from stock_advisor.app` → `from stock_advisor.ui.app`). A mechanical way to find every site: `git grep -n "stock_advisor\.\(models\|symbols\|engine\|policy\|backtest\|screener\|presets\|compare\|alerts\|chart\|input_validate\|formatting\|data_provider\|sample_data\|workflow\|store\|app\|layout\|theme\|view_text\|view_format\|manual\)\b" -- tests main.py build_exe.py`. Rewrite each with its layer. If `src/stock_advisor/__init__.py` imports any moved module, fix it too.

- [ ] **Step 5: Verify behavior preserved (the oracle)**

```bash
python -m compileall -q main.py build_exe.py src/stock_advisor; echo "compile=$?"
python -m unittest discover -s tests 2>&1 | tail -3
python main.py --self-test 2>&1 | tail -1
```
Expected: compile exit 0; `OK` with the SAME 449 count as Step 1; `SELF_TEST_OK`. Iterate Steps 3-4 until all three pass. (`loop/scripts/check_core_boundaries.py` will now report modules missing — that is EXPECTED and fixed in Task 2; do not "fix" it here.)

- [ ] **Step 6: Commit**

```bash
git add -A src tests main.py build_exe.py
git commit -m "refactor: reorganize src/stock_advisor into domain/data/services/ui subpackages (behavior-preserving)"
```

---

## Task 2: Sync the loop control plane to the new layout + ADR + re-baseline

**Files:** `loop/architecture/core-module-manifest.json`, `loop/architecture/MODULE_BOUNDARIES.md`, `loop/baseline/module-map.json`, `loop/baseline/REPOSITORY_INVENTORY.md` (if it lists module paths), root `AGENTS.md` + `README.md` (directory tree sections), new `loop/decisions/0007-source-package-layering.md` + `loop/registers/decisions.jsonl` entry, and the re-baseline of `loop/state/evidence-index.json` (`EVD-LOOP-004`).

**Interfaces:** Consumes Task 1's new paths. Produces a green `check_core_boundaries` and a re-baselined control plane.

- [ ] **Step 1: Update the core-module manifest.** In `loop/architecture/core-module-manifest.json`: change each `modules[].path` from `<mod>.py` to `domain/<mod>.py` (all 12 are domain). Change `forbidden_internal_modules` from the old module-name list to the impure **subpackage** names: `["data","services","ui","qt_app"]` (rationale: with the layered layout, a pure `domain/` module importing an impure layer resolves to `from ..data.…`/`..services.…`/`..ui.…`, whose first path component the boundary checker inspects). Leave `forbidden_import_roots`, `source_root`, `package_name` unchanged. Run `python loop/scripts/check_core_boundaries.py` — expect `CORE_BOUNDARY_OK modules=12 …`. If it flags a domain module importing `data`/`services`/`ui`, that is a REAL boundary break introduced in Task 1 — go fix the import, don't loosen the manifest.

- [ ] **Step 2: Update the boundary/architecture docs.** In `loop/architecture/MODULE_BOUNDARIES.md`, `loop/baseline/module-map.json`, and `loop/baseline/REPOSITORY_INVENTORY.md`, update every module path/reference to the new subpackage layout (keep the counts: 12 domain / 2 data / 2 services / 6 ui / 22 total product modules + `__init__` files). In root `AGENTS.md` and `README.md`, update the `src/stock_advisor/` directory-structure block to show the subpackages.

- [ ] **Step 3: Write the layering ADR.** Create `loop/decisions/0007-source-package-layering.md` following `loop/templates/ADR.md` (状态：accepted; 背景; 决策; ≥2 备选考虑incl. flat-package and feature-based; 后果; 关联 REQ-011/ADR-0002; revisit-trigger; rollback = git revert of the move commit). Add the matching `{"id":"ADR-0007","status":"accepted",…}` line to `loop/registers/decisions.jsonl` so `validate_loop`'s ADR triangle stays consistent (accepted ⇒ not in `current.json.pending_decision_ids`).

- [ ] **Step 4: Re-baseline (loop/ content changed → digest changed).** Recompute and update, exactly as in Plan 1 Task 9/10: 
```bash
python -c "import sys;sys.path.insert(0,'loop/scripts');import _common;print(_common.control_plane_digest())"
```
Update `EVD-LOOP-004.control_plane_sha256` in `loop/state/evidence-index.json` to this value (evidence-index is excluded from the digest, so the write does not re-change it). Optionally append a `record_progress.py --work-item WI-000` line BEFORE recomputing if you want a progress entry (progress.jsonl is digest-included, so it must precede the digest computation).

- [ ] **Step 5: Full green verification**
```bash
python loop/scripts/validate_loop.py && python loop/scripts/check_traceability.py && \
python loop/scripts/render_status.py --check && python loop/scripts/render_backlog.py --check && \
python loop/scripts/check_core_boundaries.py && python -m unittest discover -s loop/tests && \
python -m unittest discover -s tests && python main.py --self-test
```
Every command exit 0; `CORE_BOUNDARY_OK modules=12`; product 449 `OK`; `SELF_TEST_OK`.

- [ ] **Step 6: Commit**
```bash
git add loop AGENTS.md README.md
git commit -m "loop: sync control plane to src subpackage layout; ADR-0007 source layering; re-baseline"
```

---

## Self-Review

- **Spec coverage (WS-R):** Task 1 delivers the `domain/data/services/ui` restructure with imports rewritten and 449 tests green; Task 2 syncs `core-module-manifest.json`/`MODULE_BOUNDARIES`/`module-map`/`AGENTS`/`README`, writes the ADR, and re-baselines — matching the spec's WS-R change list.
- **Placeholder scan:** the import rewrites are enumerated per-file from the actual dependency graph; the module→subpackage map is explicit; `git mv` loops are concrete.
- **Type/behavior consistency:** no code logic changes; the 449-test suite + `--self-test` are the behavior oracle at Step 5 of each task. `domain/` verified self-contained (zero internal import edits), so the pure-core boundary is preserved by construction and re-checked by `check_core_boundaries`.
- **Ordering:** Task 1 is product-only (loop `check_core_boundaries` intentionally RED between tasks); Task 2 restores loop green and re-baselines. Both end with the full gate set green.
- **Risk:** the one real risk is a missed import site → caught immediately by `compileall`/tests. Mitigation: the `git grep` in Step 4 enumerates every external site mechanically.
