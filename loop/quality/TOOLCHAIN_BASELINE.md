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

## Product `src/` — measured adoption debt (remediation deferred to the product-code phase)

Owner: the **dev-tooling work item** (see the `G-FORMAT`/`G-LINT`/`G-TYPE`/`G-COVERAGE` owner in
`loop/quality/quality-gates.json`); those four gates stay `enabled:false` until this debt is cleared.

| Check | Command | Current | Target |
|---|---|---|---|
| ruff lint | `python -m ruff check src main.py build_exe.py` | **68** findings (55 auto-fixable: F401 unused-import, I import-order, UP, B; incl. 7 E402 intentional `sys.path`/grouped imports needing per-site triage) | 0 (or approved per-file-ignore) |
| ruff format | `python -m ruff format --check .` | **24** files would reformat | 0 diff |
| pyright (basic) | `python -m pyright` | **51 errors**, 0 warnings (predominantly `src/ui` Tkinter dynamic-attribute assignments — `reportAttributeAccessIssue`; not runtime bugs) | 0 (annotate / typed holder / justified ignore) |
| coverage (branch) | `coverage run -m unittest discover -s tests` + `coverage report` | **86.3%** total — **already ≥ the 85% branch floor** | overall stmt ≥90/branch ≥85; core stmt ≥95/branch ≥90 (`quality/convergence.json`) |

### Remediation guidance (product-code phase)

- **ruff:** `ruff check --fix` clears the 55 auto-fixable; hand-triage the 7 E402 (`# noqa: E402`
  where the `sys.path` bootstrap is intentional — e.g. `main.py:12`, `src/stock_advisor/ui/app.py`);
  then `ruff format` the tree in one reviewable, behavior-preserving commit.
- **pyright:** the `src/ui` dynamic-attribute errors come from attaching custom attributes to Tk
  widgets; prefer typed containers or explicit holders (natural to revisit during the ADR-0001
  PySide6 migration).

## Test-runner note (refines ADR-0010)

pytest is adopted as the framework and runs the domain/data/service suites + the 33 loop tests
cleanly. The **legacy Tkinter GUI suite** (`tests/test_gui_layout.py`, 116 tests) is **flaky under
pytest** — intermittent `_tkinter.TclError: Can't find a usable init.tcl` from rapid `tk.Tk()`
create/destroy cycles under pytest's execution model (the tests have correct `tearDown` and pass
deterministically under `unittest discover`). Therefore:

- `unittest discover -s tests` remains the **authoritative gate runner** (`G-CORE`); coverage runs
  via `coverage run -m unittest discover -s tests` (`G-COVERAGE`), not `-m pytest`.
- **Fast-follow:** add a pytest `conftest.py` Tk-lifecycle fixture (forced root destruction + GC, or
  a session-scoped root) so the GUI suite runs green under pytest, then complete the ADR-0010 runner
  migration. Until then pytest is for new/non-GUI tests.

## Environment note

The project runs on the repo's Python (tests, gates, self-test); `.venv/` is a PyInstaller build
sandbox (git-ignored), not the dev environment. CI provisions a fresh interpreter and installs the
`dev` group. A single managed virtual environment holding all deps is a reasonable future
convergence, but is out of scope for WS-8 (it would disturb the working run/build flow).
