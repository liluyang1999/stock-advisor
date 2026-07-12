# Plans · Requirements · Test-Goals Hardening Plan (Plan 3 of 6 · WS-3 + WS-4 + WS-6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the loop control plane's **test expected-goals measurable**, the **requirements complete** (add missing NFRs + machine-readable UI tokens + REQ↔AC linkage), and the **planning richer** (per-WI estimates/DoD, human-gate wiring, split oversized WIs) — all while the Plan-1 checkers (edge-agreement, AC-coverage, ADR triangle, digest) stay green.

**Architecture:** Everything is `loop/` machine files + docs; no product code. Because the strengthened `validate_loop`/`check_traceability` enforce REQ↔WI↔AC↔TEST consistency, every requirement/test/plan change is a *vertical slice* that keeps the traceability chain green at each commit; the six control gates are the oracle. A final task re-baselines the digest.

**Tech Stack:** JSON/JSONL/CSV/Markdown under `loop/`; the stdlib control scripts as validators.

## Global Constraints

- Writes only inside `loop/`. No product code, no `src/`, `tests/`, `main.py`, `build_exe.py`.
- Every task ends with all six control gates green (`validate_loop`, `check_traceability`, `render_status --check`, `render_backlog --check`, `check_core_boundaries`, `unittest discover -s loop/tests`) plus product `unittest discover -s tests` (449) and `main.py --self-test` still green (unaffected, but confirm).
- Keep counts consistent: if a task changes `requirements_total`/`acceptance_total`/test count, update `state/metrics.json` + re-render `STATUS.md` in the same task, and update the `Loop schemas: N` / traceability literals in `loop/tests/test_loop_tooling.py` if they move.
- `loop/**` is pinned to LF — the Write tool already emits LF; do not fight it.
- No check may be weakened to pass; reconcile the data.
- **Deferred to fast-follow (do NOT do here):** renumber-splitting compound REQ-004/008/023/025 (mass traceability churn, low value); F3 negative tests; F4 EVD back-link. Task 3 instead sharpens their AC granularity in place.

## Reference: current state (verified)
- 30 REQ (`product/REQUIREMENTS.md`), 12 AC (`product/ACCEPTANCE_CRITERIA.md`), 26 WI, 32 TEST (`quality/test-catalog.json` — bare `{id,scope,level}`), 8 MS.
- `quality/test-catalog.schema.json` was closed (`additionalProperties:false`) in Plan-1 Task 8 → Task 1 must re-open it for the new per-test fields.
- Verification ladder ids: `V0_assumption V1_static V2_unit V3_integration V4_system V5_release` (from `loop.json.verification_ladder`).
- UI hex present for page `#F6F4EF`/panel `#FFFFFF`/ink `#122B3D`/interactive `#17456F`; **missing** for A股红/绿/琥珀 + state tokens; no `tokens.json`.

---

## Task 1: Make test expected-goals measurable (WS-3 core)

**Files:** `loop/schemas/test-catalog.schema.json`, `loop/quality/test-catalog.json`, `loop/tests/test_loop_tooling.py`.

**Interfaces:** Produces per-test fields consumed by future evidence capture: `expected_goal`, `evidence_level`, `owning_work_item`, `expected_artifact` (+ optional `tolerance`).

- [ ] **Step 1: Re-open the schema for the new fields.** In `test-catalog.schema.json`, change the test-item object so it still `required` `["id","scope","level"]` and adds these OPTIONAL properties with an `enum` on `evidence_level` = the six V-levels, keeping `additionalProperties:false` (add the new keys to `properties`): `expected_goal` (string), `evidence_level` ({"enum":["V0_assumption","V1_static","V2_unit","V3_integration","V4_system","V5_release"]}), `owning_work_item` (string, pattern `^WI-\d{3}$`), `expected_artifact` (string), `tolerance` (string). Also set root `additionalProperties:false` if not already.

- [ ] **Step 2: Write the failing test** in `loop/tests/test_loop_tooling.py`:
```python
    def test_every_catalog_test_has_measurable_goal(self) -> None:
        import json as _json
        cat = _json.loads((LOOP_ROOT / "quality/test-catalog.json").read_text(encoding="utf-8"))
        work_ids = {w["id"] for w in _json.loads((LOOP_ROOT / "planning/work-items.json").read_text(encoding="utf-8"))["work_items"]}
        for t in cat["tests"]:
            self.assertTrue(t.get("expected_goal"), t["id"])
            self.assertIn(t.get("evidence_level"), {"V0_assumption","V1_static","V2_unit","V3_integration","V4_system","V5_release"}, t["id"])
            self.assertRegex(t.get("owning_work_item",""), r"^WI-\d{3}$", t["id"])
            self.assertIn(t["owning_work_item"], work_ids, t["id"])
            self.assertTrue(t.get("expected_artifact"), t["id"])
        self.assertEqual(validate_loop.validate(), [])
```
Run it → FAIL (fields absent).

- [ ] **Step 3: Populate all 32 tests.** For each test in `test-catalog.json`, add `expected_goal` (a one-sentence measurable pass condition derived from its `scope` — e.g. TEST-NUM-001 → "golden vectors match independent hand-calcs within tolerance; all finite; range/determinism invariants hold"), `evidence_level` (map `level`→V: unit→V2_unit, static→V1_static, property→V2_unit, integration→V3_integration, gui→V3_integration, system→V4_system, performance→V4_system, release→V5_release), `owning_work_item` (the WI whose `tests[]` lists this test — derive from `work-items.json`; every catalog test is referenced by exactly one WI), and `expected_artifact` (e.g. "pytest report", "offscreen Qt run log", "screenshot matrix", "benchmark json", "human gate record"). Add `tolerance` on the numeric tests (TEST-NUM-001, TEST-BT-001) referencing the tolerance convention.

- [ ] **Step 4: Run all gates green; commit.**
```bash
python loop/scripts/validate_loop.py && python -m unittest discover -s loop/tests && python loop/scripts/check_traceability.py
git add loop/schemas/test-catalog.schema.json loop/quality/test-catalog.json loop/tests/test_loop_tooling.py
git commit -m "loop: give every catalog test a measurable goal, evidence level, owning WI and artifact"
```

---

## Task 2: Coverage policy + measurable perf/reliability budgets + tk-contract schema (WS-3 rest)

**Files:** `loop/quality/convergence.json` or a new coverage stanza, `loop/quality/quality-gates.json` (add `G-COVERAGE` + `owning_work_item` per gate), `loop/quality/performance-budgets.json`, `loop/quality/reliability-targets.json`, `loop/quality/tk-contract-mapping.csv` + a new `loop/schemas/tk-contract-mapping`… (CSV has no schema; add a header/columns contract check instead), `loop/planning/work-items.json` (owning WI for coverage), `loop/tests/test_loop_tooling.py`.

- [ ] **Step 1: Coverage policy.** Add a `G-COVERAGE` gate to `quality-gates.json` (order after G-CORE, `enabled:false`, `required_for_release:true`, command `[["coverage","run","-m","pytest"],["coverage","report","--fail-under=…"]]` — use the existing convergence targets: overall 90/85, core 95/90), and add `owning_work_item` to EVERY gate object (the WI that turns it on — the tooling WIs from Task/Plan 4 for the dev-tool gates; `WI-000`/existing for the already-on ones). Add a validator rule (in `validate_loop.py`) — but ONLY if it stays green now — that `required_for_release ⇒ enabled OR owning_work_item present` (so no gate is silently un-owned). Add a test asserting every gate has an `owning_work_item`.

- [ ] **Step 2: Measurable budgets.** In `performance-budgets.json` and `reliability-targets.json`, add to each entry `method` (how measured), `scenario` (the workload), and `owning_test` (a TEST-* id). Give REL-009 (`shutdown_within_deadline`) a numeric millisecond deadline. Keep the existing numbers; this makes them measurable, not arbitrary.

- [ ] **Step 3: tk-contract-mapping contract.** `tk-contract-mapping.csv` is a stub. Add its column contract as a `check_traceability`/`validate_loop` assertion (header must be `contract_id,area,disposition,replacement_test_id,notes`; `disposition ∈ {pure_preserved,qt_replaced,approved_retired}`; `qt_replaced` rows require a `replacement_test_id`). Do NOT enumerate all 187 rows here (that is WI-002); assert the header + disposition enum + a documented `expected_row_count=187` note.

- [ ] **Step 4: Gates green; commit** (`git commit -m "loop: coverage gate + owning-WI per gate; measurable perf/reliability budgets; tk-contract column contract"`).

---

## Task 3: NFR requirements + REQ↔AC linkage + AC-005 alignment (WS-4 requirements)

**Files:** `loop/product/REQUIREMENTS.md`, `loop/product/ACCEPTANCE_CRITERIA.md`, `loop/quality/traceability.csv`, `loop/quality/test-catalog.json`, `loop/planning/work-items.json`, `loop/state/metrics.json`, `loop/STATUS.md`, `loop/tests/test_loop_tooling.py`.

Add these missing NFR requirements as **full vertical slices** (each: a `REQ-0NN` line + a mapped `AC-0NN` + an owning WI's `requirements[]`/`acceptance[]` + a `TEST-*` + a `traceability.csv` row + count bumps). Assign to the most fitting existing WIs (do not invent milestones):
- **REQ-031 常驻免责声明**: every result view + HTML manual + CSV export carries the non-advice disclaimer. AC-031, owner WI-018 (help/export) + WI-011 (results), test TEST-DISC-001 (static: disclaimer present in each surface).
- **REQ-032 导出注入安全**: CSV/clipboard export neutralizes formula-injection (`= + - @` lead) and path traversal. AC-032, owner WI-018, test TEST-SEC-001.
- **REQ-033 字体缺失回退**: if Microsoft YaHei is absent, fail visibly / documented fallback, never silent wrong font. AC-033, owner WI-004, test TEST-FONT-003.
- **REQ-034 性能预算**: batch-of-30 analysis, 5000-row scroll, cold start, idle RSS meet the numeric budgets in `performance-budgets.json`. AC-034, owner WI-022, test TEST-PERF-001 (already exists).

Steps:
- [ ] **Step 1:** Add REQ-031..034 to `REQUIREMENTS.md` (new "非功能与安全需求" section). Add AC-031..034 to `ACCEPTANCE_CRITERIA.md` (measurable). Add `acceptance_criteria` values already exist per row — ensure the new REQ rows carry them. Add a REQ↔AC linkage: since `traceability.csv` already has an `acceptance_criteria` column (Plan-1 Task-4), populate the new rows there; that IS the REQ↔AC link.
- [ ] **Step 2:** Add `TEST-DISC-001`, `TEST-SEC-001`, `TEST-FONT-003` to `test-catalog.json` WITH the measurable fields from Task 1 (goal/level/owning_WI/artifact). Add each new REQ to its owning WI's `requirements[]` and the WI's `acceptance[]` where needed; add the new tests to those WIs' `tests[]`.
- [ ] **Step 3:** Add the four `traceability.csv` rows (REQ-031..034) with priority, statement, design_refs (`SECURITY_THREAT_MODEL.md`/`UI_DESIGN_SYSTEM.md`), adr_refs, work_item_ids, acceptance_criteria, test_ids, status `planned`, owner `project`. Fix **AC-005** in `ACCEPTANCE_CRITERIA.md`: change "正文/控件不低于 10pt" → "不低于 10.5pt" (align to the token).
- [ ] **Step 4:** Bump `state/metrics.json` `engineering.requirements_total` (30→34), `acceptance_total` (12→16), and `control_plane.requirements_traced`; re-render STATUS (`render_status.py --write`); update the `requirements=30`/`Traceability: 30/30` expectations in `test_loop_tooling.py` to the new counts. Run ALL gates green (edge-agreement + AC-coverage must pass for the new slices). Commit.

---

## Task 4: Machine-readable UI tokens + color hex + UX per-page states (WS-4 UI)

**Files:** new `loop/product/tokens.json` (+ `loop/schemas/tokens.schema.json`), `loop/product/UI_DESIGN_SYSTEM.md`, `loop/product/UX_INFORMATION_ARCHITECTURE.md`.

- [ ] **Step 1:** Create `loop/product/tokens.json` (with `$schema` + `schema_version`) capturing the machine-readable design tokens from `config.json.ui_tokens` PLUS colors: `page:#F6F4EF, panel:#FFFFFF, ink:#122B3D, interactive:#17456F`, and ADD hex for `up_red`, `down_green`, `amber` (pick accessible A-share-convention values meeting the ≥4.5:1 body / ≥3:1 large contrast target against page/panel — document the measured ratios), plus state tokens `hover/pressed/disabled/selected_row/gridline/focus_ring`, and `border_radius`. Add `loop/schemas/tokens.schema.json` (closed) and wire it via the file's `$schema` so `validate_loop` validates it (schema_documents count will rise by 1 → update metrics + STATUS + the `Loop schemas: N` test literal).
- [ ] **Step 2:** In `UI_DESIGN_SYSTEM.md`, add the hex for A股红/绿/琥珀 + the state tokens (referencing `tokens.json` as the machine source), and note `tokens.json` is authoritative for WI-005.
- [ ] **Step 3:** In `UX_INFORMATION_ARCHITECTURE.md`, replace the enumerated 7-state list with a per-page state spec table (individual / screener / portfolio / alerts / fund-flow pages × {empty, loading, partial, error, degraded, stopped, all-failed} → copy + affordance).
- [ ] **Step 4:** Gates green (incl. the new schema doc counted); commit.

---

## Task 5: Planning enrichment (WS-6) + K1 fix

**Files:** `loop/planning/work-items.json`, `loop/planning/milestones.json`, `loop/planning/ROADMAP.md`, `loop/planning/dependency-graph.json`, `loop/quality/quality-gates.json`, `loop/schemas/work-items.schema.json`, `loop/quality/traceability.csv`, `loop/tests/test_loop_tooling.py`.

- [ ] **Step 1: Per-WI size + DoD.** Add to `work-items.schema.json` optional `size` ({"enum":["S","M","L","XL"]}) and `scope_out` (array). Add a `size` and a short `definition_of_done`/`scope_out` to each of the 26 WIs in `work-items.json` (rough T-shirt; DoD = its acceptance restated as a checkable exit). Add a test asserting every WI has a `size`.
- [ ] **Step 2: Human-gate wiring.** Add `human_gate` (nullable) to `work-items.schema.json`; set `WI-001.human_gate="HG-ARCH"`, `WI-003="HG-DEPS"`, `WI-024="HG-PACKAGING"` (WI-025 already implies HG-LICENSE/HG-RELEASE). Add gate objects for HG-ARCH/HG-DEPS/HG-PACKAGING to `quality-gates.json` if a human-gate registry is expected, or document them in the WI field only — keep `validate_loop` green.
- [ ] **Step 3: Split oversized WIs.** Split `WI-011` (extract a candlestick-widget WI), `WI-018` (extract export-security — now REQ-032's owner), `WI-009` (separate the QNAM spike from the urllib adapter). Add the new WIs (WI-026/027/028…) with full fields, wire their REQ/AC/TEST + `traceability.csv` rows + `dependency-graph.json` edges + milestone membership; keep the dependency graph acyclic and consistent (the Plan-1 checker enforces this).
- [ ] **Step 4: K1 fix + ROADMAP.** Update the stale `implementation_paths` for WI-009 (`data/data_provider.py`), WI-018 (`ui/manual.py`), WI-023 (`ui/app.py`). (WI-007 was already fixed separately in commit `53676f6` per a user follow-up — do NOT re-touch it.) Add per-milestone exit-criteria detail to `ROADMAP.md` to match `milestones.json`.
- [ ] **Step 5:** Bump counts (work_items_total) in metrics + STATUS + test literals; ALL gates green; commit.

---

## Task 6: Re-baseline

**Files:** `loop/state/evidence-index.json` (+ artifact), `loop/state/progress.jsonl`.

- [ ] **Step 1:** Append a `record_progress.py --work-item WI-000` line summarizing Plan 3 (BEFORE computing the digest — progress.jsonl is digest-included).
- [ ] **Step 2:** Recompute `control_plane_digest()`; re-run the full gate set + 449 + self-test and overwrite the `EVD-LOOP-004` artifact; update `EVD-LOOP-004.control_plane_sha256` + `sha256` + `summary` (note Plan 3). Confirm `validate_loop` `LOOP_VALIDATION_OK` (live baseline matches).
- [ ] **Step 3:** Commit (`git commit -m "loop: re-baseline after Plan 3 (test goals, NFR requirements, UI tokens, planning enrichment)"`).

---

## Self-Review

- **Spec coverage:** Task 1-2 = WS-3 (measurable test goals, coverage, budgets, tk-contract); Task 3-4 = WS-4 (NFR REQs, REQ↔AC via the traceability AC column, AC-005, tokens.json + hex, UX states); Task 5 = WS-6 (size/DoD, human-gate wiring, split oversized WIs, ROADMAP, K1). The high-churn compound-REQ renumber is explicitly deferred with rationale.
- **Placeholder scan:** the schema deltas, the new REQ/AC/TEST ids and their owners, and the metric-count bumps are all concrete; per-test goal derivation is rule-based from `scope`.
- **Consistency:** every new requirement is a full vertical slice (REQ+AC+WI+TEST+trace row) so the Plan-1 edge-agreement/AC-coverage checkers stay green; count bumps + STATUS re-render + test-literal updates are called out in each task that moves a count.
- **Ordering:** measurable-tests (1-2) and requirements (3-4) before planning (5) so WI additions can reference the new tests/REQs; re-baseline (6) last, once the tree is final.
- **Risk:** the main risk is a count/trace mismatch tripping a checker mid-task → caught immediately by `validate_loop`/`check_traceability`; each task re-runs them before commit.
