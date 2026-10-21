# Toolchain Adoption Baseline (WS-8 / Plan 6)

Measured state of the codebase against the dev toolchain adopted in **ADR-0008**
(`0008-dev-toolchain.md`: ruff + pyright + pytest + coverage + pre-commit), as of **2026-07-13**
(Python 3.14.4, Windows 11). This is the honest bridge between "the toolchain is wired" and "the
product code is fully compliant": the **control-plane Python** (`loop/scripts/**`, `loop/tests/**`)
is brought clean now; the **product `src/**`** carries measured *adoption debt* whose remediation is
a separate, deliberate product-code phase (product logic/code changes are explicitly deferred).

## Tool versions (pinned in `pyproject.toml` `[dependency-groups].dev`)

| Tool | Version | Role |
|---|---|---|
| ruff | 0.15.21 | format + lint |
| pyright | 1.1.410 | static type check (dev-only; needs Node, never in the EXE) |
| pytest | 9.1.1 | test framework (new + non-GUI + loop suites) |
| coverage | 7.15.1 | coverage measurement |
| pre-commit | 4.6.0 | local pre-commit hooks |

## Control-plane Python — CLEAN (enforced now)

`python -m ruff check loop/scripts loop/tests` → 0; `python -m ruff format --check` → 0. Achieved
2026-07-13 (8 lint fixes + formatting at line-length 100; behavior-preserving — the six control
gates + 33 loop tests + product 449 + self-test are green after). New control-plane code MUST stay
clean.

## Product `src/` — adoption debt CLEARED (all four gates enforced since 2026-07-16)

Owner: the **dev-tooling work item** (see the `G-FORMAT`/`G-LINT`/`G-TYPE`/`G-COVERAGE` owner in
`loop/quality/quality-gates.json`). Those four gates waited on the debt below; it is now paid and
they are `enabled:true`, so this table is enforced by CI rather than aspirational.

> **CI 必须用 `run_gates.py --strict`。** 门禁运行器把「工具没装成」降级为 `SKIP` 并仍然退出 0——
> 那是给新检出的人留的便利，放在 CI 里却是**毫无根据的绿**：一个装不上的 pyright 会让 `G-TYPE`
> 悄悄消失而流水线照常通过。`--strict` 把 SKIP 计为失败，确保这张表里的每一项在 CI 里都真的跑过。

| Check | Command | Baseline (2026-07-13) | Now (2026-07-16) |
|---|---|---|---|
| ruff lint | `python -m ruff check .` | **68** findings (F401, I, UP, B; incl. 7 E402) | **0** — enforced by `G-LINT` |
| ruff format | `python -m ruff format --check .` | **24** files would reformat | **0 diff** (81 files) — enforced by `G-FORMAT` |
| pyright (basic) | `python -m pyright` | **51 errors** (mostly `src/ui` Tk dynamic attributes) | **0 errors** — enforced by `G-TYPE` |
| coverage | `coverage run -m unittest discover -s tests` + `check_coverage.py` | **86.3%** blended (the four real thresholds were *not* met) | overall stmt **92.99%**/branch **87.84%**, core stmt **99.75%**/branch **99.26%** — all four floors met, enforced per dimension by `G-COVERAGE` |

### How the debt was paid (for the record)

- **ruff:** `--fix` cleared the auto-fixable; the intentional `sys.path` bootstraps got per-file
  `# ruff: noqa: E402`; the tree was formatted in behavior-preserving commits.
- **pyright:** the `src/ui` dynamic-attribute errors were the Tk god-class's symptom, resolved by the
  ADR-0014 mixin decomposition + the `TYPE_CHECKING`-only `AppMembers` base (and `StatefulToplevel`
  for dialog attributes). The last repo-wide error was the annotated function-attribute form
  `check.stats: dict[str, int] = {}` — a statement Python does not support annotating; both
  `check_traceability.check()` and `check_core_boundaries.check()` now return `(errors, stats)`.
  `validate_loop.validate()` deliberately keeps its function attribute + `# type: ignore`: its
  `== []` contract has a dozen callers, so changing the signature costs more than the debt.
- **coverage:** the blended `--fail-under=85` never asserted the four documented thresholds; it was
  replaced by `loop/scripts/check_coverage.py`, which reads them from `quality/convergence.json` and
  asserts each dimension separately. Measurement omits `ui/_app_members.py` (ADR-0014 type-only base,
  never imported at runtime — its 310 unexecutable declarations distorted the total to 82.7%).

## Test-runner note (refines ADR-0010)

pytest runs the domain/data/service **and Qt** suites + the loop tooling tests cleanly (Qt tests
need a platform plugin — run them with `QT_QPA_PLATFORM=offscreen`). The reason `unittest discover`
stays authoritative is now **historical**: the legacy Tkinter GUI suite (`tests/test_gui_layout.py`)
was flaky under pytest (intermittent `_tkinter.TclError` from rapid `tk.Tk()` create/destroy) and
was **deleted together with the Tk production layer (WI-023)**, so that flakiness no longer exists.
Therefore:

- `unittest discover -s tests` remains the **authoritative gate runner** (`G-CORE`); coverage runs
  via `coverage run -m unittest discover -s tests` (`G-COVERAGE`), not `-m pytest`. This is now a
  deliberate choice — `run_gates.py` and CI are written against the unittest runner — not a
  workaround for the (removed) Tk suite.

## Environment note

The project runs under Python 3.14.4. Developers can use `.venv/` with the complete
`requirements/dev-windows.lock`; CI installs this hash-locked set in a fresh Windows interpreter.
Packaging always creates a separate disposable `build/package-env-*` environment from
`requirements/build-windows.lock`, then removes it. It never reuses or edits a developer's `.venv/`.
See `docs/10-packaging.html` for the teaching walkthrough and `scripts/package_app.py` for the entry point.
