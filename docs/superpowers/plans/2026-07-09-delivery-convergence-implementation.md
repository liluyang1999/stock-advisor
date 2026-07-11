# 股市锦囊 Delivery Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the current `股市锦囊` desktop application to a user-deliverable convergence state by auditing and fixing only delivery-blocking behavior, then doing a restrained UI polish pass and final global verification.

**Architecture:** Preserve the existing Python stdlib-only Tkinter architecture. Keep pure logic modules independent from tkinter and network access, keep `data_provider.py` as the only network module, keep `workflow.py` as the orchestration boundary, and keep `app.py` focused on UI/thread/render coordination. This plan prioritizes evidence-based audit first; code changes are made only when a current blocker or clear user-facing defect is reproduced by a failing test.

**Tech Stack:** Python standard library, tkinter, unittest, PyInstaller as the only build dependency, project-local `build/` and `dist/` artifacts.

---

## File Structure

- Modify only if an audit finds a blocker:
  - `src/stock_advisor/app.py` for UI state, thread polling, dialog, copy/export, monitor, and layout behavior.
  - `src/stock_advisor/workflow.py` for provider-to-UI orchestration errors.
  - `src/stock_advisor/data_provider.py` only for parser robustness or explicit error reporting.
  - Pure logic modules under `src/stock_advisor/` only if their existing tests reveal a boundary bug.
- Add or modify tests near the failing behavior:
  - `tests/test_gui_layout.py` for headless UI interaction, state, dialog, and threading behavior.
  - `tests/test_ui_polish.py` for layout, sizing, visual-density, and UI naming invariants.
  - `tests/test_store.py`, `tests/test_provider.py`, `tests/test_workflow.py`, or pure module tests when the failure is below the UI layer.
- Update docs only if verification discovers an inaccurate README/manual statement:
  - `README.md`
  - `src/stock_advisor/manual.py`
- Do not add runtime dependencies.
- Do not move build output outside `build/` or `dist/`.
- Do not commit automatically in this dirty worktree; stage/commit only if the user explicitly asks after reviewing the final diff.

---

### Task 1: Establish Current Evidence Baseline

**Files:**
- Read: `AGENTS.md`
- Read: `docs/superpowers/specs/2026-07-09-delivery-convergence-design.md`
- Read: `README.md`
- Read: `build_exe.py`
- Output: terminal evidence only

- [ ] **Step 1: Verify repository constraints**

Run:

```powershell
Get-Content -Encoding UTF8 AGENTS.md
Get-Content -Encoding UTF8 docs\superpowers\specs\2026-07-09-delivery-convergence-design.md
```

Expected: The constraints confirm Python stdlib-only runtime, PyInstaller-only build dependency, `dist\股市锦囊.exe`, `dist\使用说明.html`, no external build output, and phase order A then C then final review.

- [ ] **Step 2: Verify current worktree shape**

Run:

```powershell
git status --short
```

Expected: Dirty worktree is allowed, but do not revert unrelated changes. Note any new files created by the current plan.

- [ ] **Step 3: Run full unit test baseline**

Run:

```powershell
python -m unittest discover -s tests
```

Expected: `OK`. If it fails, stop and treat the first failing test as the current Phase A blocker.

- [ ] **Step 4: Run syntax baseline**

Run:

```powershell
$files = @('main.py', 'build_exe.py') + (Get-ChildItem -Path 'src\stock_advisor' -Filter '*.py' | ForEach-Object { $_.FullName }); python -m py_compile @files
```

Expected: exit code 0 with no syntax errors.

---

### Task 2: Phase A Audit - Runtime State and Thread Closure

**Files:**
- Inspect: `src/stock_advisor/app.py`
- Inspect tests: `tests/test_gui_layout.py`
- Modify only if a gap is found: `src/stock_advisor/app.py`
- Test: `tests/test_gui_layout.py`

- [ ] **Step 1: Confirm coverage for running, stop, clear, close, and monitor state**

Run:

```powershell
rg -n "test_.*(running|stop|clear|close|monitor|worker|poll|stale|idle)" tests\test_gui_layout.py
rg -n "def stop|def clear|def close|def _poll_queue|def _monitor_tick|def _poll_monitor|_set_running" src\stock_advisor\app.py
```

Expected: Tests cover idle stop as no-op, clear discarding late results, close canceling background work, stale monitor callbacks, worker exception handling, and running-state input tool protection.

- [ ] **Step 2: Run the state/monitor subset**

Run:

```powershell
python -m unittest tests.test_gui_layout.GuiLayoutTests.test_stop_while_idle_is_noop tests.test_gui_layout.GuiLayoutTests.test_clear_during_running_discards_late_analysis_results tests.test_gui_layout.GuiLayoutTests.test_clear_during_screening_discards_late_recommendation_rows tests.test_gui_layout.GuiLayoutTests.test_close_cancels_running_work_and_monitoring tests.test_gui_layout.GuiLayoutTests.test_closing_poll_callbacks_do_not_reschedule tests.test_gui_layout.GuiLayoutTests.test_stale_monitor_timer_does_not_schedule_after_reenable tests.test_gui_layout.GuiLayoutTests.test_running_state_disables_input_tools tests.test_gui_layout.GuiLayoutTests.test_input_tools_do_not_mutate_input_while_running
```

Expected: `OK`.

- [ ] **Step 3: If a runtime state blocker is found, write the failing test first**

Add a focused test to `tests/test_gui_layout.py`. Example pattern for a late callback blocker:

```python
def test_late_callback_after_close_does_not_mutate_ui(self):
    self.app._closing = True
    before = self.app.status_var.get()

    self.app._poll_queue()

    self.assertEqual(self.app.status_var.get(), before)
```

Run:

```powershell
python -m unittest tests.test_gui_layout.GuiLayoutTests.test_late_callback_after_close_does_not_mutate_ui
```

Expected before implementation: `FAIL` for the specific reproduced blocker. If the test passes immediately, remove or revise it because it is not proving a current defect.

- [ ] **Step 4: Implement only the minimal runtime-state fix**

Change only the relevant guard or state reset in `src/stock_advisor/app.py`. Use existing local patterns such as:

```python
if self._closing:
    return
```

or:

```python
if not self.busy:
    return
```

Do not refactor unrelated UI construction.

- [ ] **Step 5: Verify the runtime-state fix**

Run the failing test from Step 3, then run:

```powershell
python -m unittest tests.test_gui_layout tests.test_ui_polish tests.test_app_helpers
```

Expected: all selected tests pass.

---

### Task 3: Phase A Audit - User-Visible Error Handling and Persistence

**Files:**
- Inspect: `src/stock_advisor/app.py`
- Inspect: `src/stock_advisor/store.py`
- Inspect: `src/stock_advisor/workflow.py`
- Test: `tests/test_gui_layout.py`
- Test: `tests/test_store.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Confirm existing coverage for copy/export/config/provider errors**

Run:

```powershell
rg -n "test_.*(save|persist|config|copy|export|clipboard|failure|error|worker|provider|fund_flow)" tests
rg -n "messagebox\.showerror|messagebox\.showinfo|filedialog|clipboard|_save_persisted|_report_config_save_failure|except Exception" src\stock_advisor\app.py src\stock_advisor\store.py src\stock_advisor\workflow.py
```

Expected: Tests exist for save failure feedback, clipboard failure, export write failure, worker exceptions, screen worker exceptions, fund-flow callback after closed window, and config read/write fallback.

- [ ] **Step 2: Run the error-handling subset**

Run:

```powershell
python -m unittest tests.test_gui_layout tests.test_store tests.test_workflow tests.test_fund_flow
```

Expected: `OK`.

- [ ] **Step 3: If a user-visible error path lacks coverage, write a failing test first**

Add the test in the closest existing test file. For a concrete UI write-failure path, use this pattern in `tests/test_gui_layout.py`:

```python
def test_export_csv_reports_oserror_without_crashing(self):
    from stock_advisor import app as app_module

    self._inject_sample()
    errors = []
    original_dialog = app_module.filedialog.asksaveasfilename
    original_showerror = app_module.messagebox.showerror
    original_open = app_module.open
    app_module.filedialog.asksaveasfilename = lambda **_kwargs: str(Path(self._cfg_dir) / "blocked.csv")
    app_module.messagebox.showerror = lambda *args, **kwargs: errors.append((args, kwargs))
    app_module.open = lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("blocked"))
    try:
        self.app.export_csv()
    finally:
        app_module.filedialog.asksaveasfilename = original_dialog
        app_module.messagebox.showerror = original_showerror
        app_module.open = original_open

    self.assertTrue(errors)
    self.assertEqual(self.app.status_var.get(), "导出失败")
```

Run the single test and confirm it fails for the missing behavior before modifying production code. If this exact behavior is already covered, do not add a duplicate test; inspect the next uncovered user-visible path and write the same level of concrete test against its real method and real UI state.

- [ ] **Step 4: Implement only explicit feedback or exception containment**

Use existing patterns:

```python
try:
    ...
except tk.TclError as exc:
    self.status_var.set("复制失败")
    messagebox.showerror(title, f"剪贴板暂不可用：{exc}")
    return
```

or:

```python
if not self._save_persisted():
    self._report_config_save_failure(action_text)
```

Do not silently swallow user-visible failures unless the operation is a background best-effort path that already has a safe UI fallback.

- [ ] **Step 5: Verify the error-handling fix**

Run the new single test, then:

```powershell
python -m unittest tests.test_gui_layout tests.test_store tests.test_workflow tests.test_fund_flow
```

Expected: all selected tests pass.

---

### Task 4: Phase A Audit - Data Robustness and No Fabricated Results

**Files:**
- Inspect: `src/stock_advisor/data_provider.py`
- Inspect: `src/stock_advisor/engine.py`
- Inspect: `src/stock_advisor/screener.py`
- Inspect: `src/stock_advisor/policy.py`
- Inspect: `src/stock_advisor/chart.py`
- Inspect: `src/stock_advisor/alerts.py`
- Test: `tests/test_provider.py`
- Test: `tests/test_engine.py`
- Test: `tests/test_screener.py`
- Test: `tests/test_policy.py`
- Test: `tests/test_chart.py`
- Test: `tests/test_alerts.py`

- [ ] **Step 1: Confirm pure module robustness coverage**

Run:

```powershell
rg -n "nan|inf|missing|empty|invalid|MarketDataError|缺失|无效|失败" tests\test_provider.py tests\test_engine.py tests\test_screener.py tests\test_policy.py tests\test_chart.py tests\test_alerts.py
```

Expected: Tests cover NaN/Inf, missing fields, invalid quote/history values, empty candidates, and alert finite-value checks.

- [ ] **Step 2: Run pure module robustness tests**

Run:

```powershell
python -m unittest tests.test_provider tests.test_engine tests.test_screener tests.test_policy tests.test_chart tests.test_alerts
```

Expected: `OK`.

- [ ] **Step 3: If robustness gap is found, add a failing pure test first**

Example for parser robustness in `tests/test_provider.py`:

```python
def test_parse_snapshot_rejects_nonfinite_required_price(self):
    payload = {"data": {"diff": [clist_item(code="600001", price=float("inf"))]}}

    rows = parse_market_snapshot_payload(json.dumps(payload))

    self.assertEqual(rows, [])
```

Run the single test and confirm it fails before modifying parser code. Adjust function names and fixture helpers to existing test utilities in the file.

- [ ] **Step 4: Implement the smallest pure-function fix**

Use existing finite helpers such as `_optional_float`, `_safe_float`, `_finite_number`, or module-local equivalents. Keep the module free of tkinter and network side effects.

- [ ] **Step 5: Verify robustness fix**

Run the single test, then:

```powershell
python -m unittest tests.test_provider tests.test_engine tests.test_screener tests.test_policy tests.test_chart tests.test_alerts
```

Expected: all selected tests pass.

---

### Task 5: Phase C UI Visual and Layout Review

**Files:**
- Inspect: `src/stock_advisor/app.py`
- Inspect: `tests/test_ui_polish.py`
- Inspect: `tests/test_gui_layout.py`
- Output: `build/ui-screenshot.png` or a new timestamped screenshot inside `build/`

- [ ] **Step 1: Confirm UI invariant tests**

Run:

```powershell
python -m unittest tests.test_ui_polish tests.test_gui_layout
```

Expected: `OK`.

- [ ] **Step 2: Capture a real desktop screenshot**

Run a PowerShell screenshot command from the project root. If GUI launch requires approval, request escalation. The command must write only inside `build/`, for example `build\ui-screenshot.png`.

Expected: screenshot file exists and shows the `股市锦囊` main window.

- [ ] **Step 3: Visually inspect the screenshot**

Check:

- Window title and first-screen product name are `股市锦囊`.
- Primary workspace is visible without a marketing/landing page.
- Controls are dense but readable.
- No obvious overlap or clipped text in first viewport.
- Buttons, menus, table, summary metrics, chart panels, and scrollbars look coordinated.
- No decorative components that do not support the workflow.

- [ ] **Step 4: If a visible UI blocker is found, write a layout test first**

Add the test to `tests/test_ui_polish.py` or `tests/test_gui_layout.py`. Example for title/name invariance:

```python
def test_main_window_uses_product_name(self):
    self.assertEqual(self.root.title(), "股市锦囊")
```

Run the single test and confirm it fails before modifying UI code.

- [ ] **Step 5: Implement the smallest UI polish fix**

Modify only named constants, layout packing/grid options, or text labels directly related to the visible blocker. Keep the existing restrained desktop-tool style. Do not add new image assets, gradients, animations, or broad page redesigns.

- [ ] **Step 6: Verify UI polish fix**

Run:

```powershell
python -m unittest tests.test_ui_polish tests.test_gui_layout
```

Expected: `OK`, then refresh the screenshot if the fix changed visible layout.

---

### Task 6: Final Delivery Gate

**Files:**
- Build output: `build/`
- Final output: `dist/股市锦囊.exe`
- Final output: `dist/使用说明.html`
- Optional evidence: `build/self-test.out`, `build/self-test.err`, `build/ui-screenshot.png`

- [ ] **Step 1: Run full tests**

Run:

```powershell
python -m unittest discover -s tests
```

Expected: `OK`.

- [ ] **Step 2: Run syntax check**

Run:

```powershell
$files = @('main.py', 'build_exe.py') + (Get-ChildItem -Path 'src\stock_advisor' -Filter '*.py' | ForEach-Object { $_.FullName }); python -m py_compile @files
```

Expected: exit code 0.

- [ ] **Step 3: Run whitespace diff check**

Run:

```powershell
git diff --check
```

Expected: exit code 0. Existing LF/CRLF warnings are acceptable if there are no whitespace errors.

- [ ] **Step 4: Build final deliverables**

Run:

```powershell
python build_exe.py
```

Expected: exit code 0; `dist\股市锦囊.exe` and `dist\使用说明.html` exist.

- [ ] **Step 5: Run packaged self-test**

Run:

```powershell
cmd /c ""dist\股市锦囊.exe" --self-test > "build\self-test.out" 2> "build\self-test.err" & echo exit=%ERRORLEVEL% & type "build\self-test.out" & type "build\self-test.err""
```

Expected: `exit=0` and output contains `SELF_TEST_OK`.

- [ ] **Step 6: Confirm final artifact names**

Run:

```powershell
Get-ChildItem -LiteralPath dist | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
```

Expected: only final deliverables relevant to the app are `股市锦囊.exe` and `使用说明.html`.

---

### Task 7: Final Global Review

**Files:**
- Read: `docs/superpowers/specs/2026-07-09-delivery-convergence-design.md`
- Read: `docs/superpowers/plans/2026-07-09-delivery-convergence-implementation.md`
- Inspect: `src/stock_advisor/`
- Inspect: `tests/`
- Inspect: `dist/`

- [ ] **Step 1: Create a requirement-to-evidence checklist in the final response draft**

Checklist items:

- Phase A blockers: runtime state, error handling, data robustness, packaging.
- Phase C UI: product name, layout constraints, component density, screenshot review.
- Project constraints: stdlib runtime, PyInstaller build, output paths, config path isolation, no fabricated行情.
- Verification gates: tests, compile, diff check, build, self-test, artifacts.

- [ ] **Step 2: Inspect evidence for each checklist item**

Use the outputs from Tasks 1-6. If any evidence is missing or indirect, run the relevant command before claiming completion.

- [ ] **Step 3: Decide completion status**

Only mark the goal complete if every explicit requirement has direct current evidence. If any item is not proven, keep the goal active and continue with the next concrete audit/fix.

- [ ] **Step 4: Report concise final status**

Include:

- What was audited or fixed.
- Which commands passed with counts where available.
- Deliverable paths.
- Any residual risk that does not block normal user delivery.
