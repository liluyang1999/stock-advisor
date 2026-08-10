# Foundation Hardening Implementation Plan (Plan 1 of 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `loop/` control plane self-check the invariants it currently only asserts in prose, and close the 13 evidenced defects — so future drift is caught by the gates, not by humans.

**Architecture:** Strengthen the two stdlib control scripts (`validate_loop.py`, `check_traceability.py`) and tighten the JSON schemas, pairing each new check with the data fix it demands (TDD red→green). Because `control_plane_digest()` pins the tree via `EVD-LOOP-003`, Task 1 first makes the plane able to evolve (exempt superseded evidence), and the final task re-baselines a fresh integrity record.

**Tech Stack:** Python 3.12+ standard library only (no third-party deps in `loop/scripts`); `unittest` for `loop/tests`; JSON / JSONL / CSV machine files under `loop/`.

## Global Constraints

- Writes limited to `loop/` (this plan touches no `src/`, `tests/`, `docs/`, or tooling config).
- `loop/scripts/*` and `loop/tests/*` remain **standard-library only** — no imports outside stdlib.
- Every task ends with the six control gates green: `validate_loop.py`, `check_traceability.py`, `render_status.py --check`, `render_backlog.py --check`, `check_core_boundaries.py`, `python -m unittest discover -s loop/tests`.
- Product baseline stays green and untouched: `python -m unittest discover -s tests` (449) and `python main.py --self-test`.
- No lowering of a gate to pass: fix the cause. New checks must be added with a failing test first.
- Timezone for machine timestamps stays the developer-local tz already used by `update_state.py`; the market-timezone fix (Task 8) is a `config.json` data field, not a script clock change.

---

## File Structure

Files created or modified by this plan (all under `loop/`):

- `scripts/validate_loop.py` — add: register de-dup, `risk_ids` cross-check, `REQUIRED_FILES` completeness + clean error, superseded-evidence digest exemption.
- `scripts/check_traceability.py` — add: REQ↔WI edge agreement, optional `acceptance_criteria` column handling.
- `tests/test_loop_tooling.py` — one new failing test per new invariant.
- `registers/experiments.jsonl` — fix duplicate `EXP-003` → `EXP-004`.
- `planning/work-items.json` — add `REQ-024` to the owning WIs; register `WI-026` (this hardening).
- `planning/milestones.json` — add `WI-026` to `MS-00`; add `MS-01 depends_on MS-00` if absent for the MS-02 fix; MS-02 `depends_on` MS-01.
- `planning/dependency-graph.json` — regenerate edges to match `depends_on`.
- `quality/traceability.csv` — add `acceptance_criteria` column; add `WI-026` row wiring; align `REQ-024`.
- `quality/test-catalog.json` — add `TEST-LOOP-002` (the hardening's test id).
- `product/ACCEPTANCE_CRITERIA.md` — fix the line-16 cross-reference to the CSV.
- `config.json` — add `market_timezone`.
- `LOOP_PROTOCOL.md` — define or remove the dangling `RECOVER` state.
- `decisions/0001-adopt-pyside6.md` + `governance/SCOPE_AND_AUTHORITY.md` — reconcile HG-ARCH status.
- `schemas/*.json` — `additionalProperties:false` on closed records; pin `schema_version`; add per-register JSONL schemas.
- `schemas/register-entry.schema.json` — wire it (or per-register schemas) into `validate_loop`.
- `state/evidence-index.json` + `evidence/baselines/*` — fix `cwd` spelling; mark `EVD-LOOP-001/002/003` superseded lineage; add `EVD-LOOP-004`.
- `state/current.json`, `state/metrics.json`, `STATUS.md` — updated by the re-baseline task via the existing scripts.

---

## Task 1: Enable control-plane evolution (digest exemption for superseded evidence)

**Files:**
- Modify: `loop/scripts/validate_loop.py:345`
- Modify: `loop/tests/test_loop_tooling.py`
- Modify: `loop/state/evidence-index.json` (mark `EVD-LOOP-003` superseded lineage)

**Interfaces:**
- Produces: the invariant "a v2 evidence record with a `superseded_by` value is exempt from the current-tree digest equality check; a non-superseded v2 record must still match." Consumed by every later task that edits `loop/`.

- [ ] **Step 1: Write the failing test**

Add to `loop/tests/test_loop_tooling.py` inside `LoopToolingTests`:

```python
def test_superseded_v2_evidence_is_exempt_from_digest(self) -> None:
    record = {
        "id": "EVD-TEST",
        "record_version": "2.0.0",
        "control_plane_sha256": "0" * 64,  # deliberately wrong
        "superseded_by": "EVD-NEXT",
    }
    self.assertTrue(validate_loop._digest_ok(record))
    record_current = dict(record)
    record_current.pop("superseded_by")
    self.assertFalse(validate_loop._digest_ok(record_current))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest loop.tests.test_loop_tooling.LoopToolingTests.test_superseded_v2_evidence_is_exempt_from_digest -v`
Expected: FAIL with `AttributeError: module 'validate_loop' has no attribute '_digest_ok'`

- [ ] **Step 3: Extract the digest check into a testable helper and apply the exemption**

In `loop/scripts/validate_loop.py`, add near the other helpers (after `_expected_backlog`):

```python
def _digest_ok(record: dict[str, Any]) -> bool:
    """A v2 evidence record matches the tree, or is exempt because it is superseded."""
    if record.get("superseded_by"):
        return True
    return record.get("control_plane_sha256") == control_plane_digest()
```

Then replace the inline check (currently the `if record.get("control_plane_sha256") != control_plane_digest():` block inside the `record_version == "2.0.0"` branch) with:

```python
            if not _digest_ok(record):
                errors.append(f"{record.get('id')} control-plane digest differs from the current tree")
```

- [ ] **Step 4: Mark EVD-LOOP-003 as superseded so edits below don't break validation**

In `loop/state/evidence-index.json`, add `"superseded_by": "EVD-LOOP-004"` to the `EVD-LOOP-003` record. (Editing `state/evidence-index.json` does not change `control_plane_digest()` — that path is excluded — so this is safe.) Also add `"superseded_by": "EVD-LOOP-003"` to `EVD-LOOP-001` and `EVD-LOOP-002` (closes defect D12's supersession half).

- [ ] **Step 5: Run the full control gates**

Run: `python loop/scripts/validate_loop.py && python -m unittest discover -s loop/tests`
Expected: `LOOP_VALIDATION_OK ...` (exit 0) and `OK`. `EVD-LOOP-004` does not exist yet; with `EVD-LOOP-003` superseded there is no current v2 baseline, so no digest is enforced during the rest of Plan 1 (restored in Task 9).

- [ ] **Step 6: Commit**

```bash
git add loop/scripts/validate_loop.py loop/tests/test_loop_tooling.py loop/state/evidence-index.json
git commit -m "loop: exempt superseded evidence from control-plane digest check"
```

---

## Task 2: Register ID uniqueness (catches the EXP-003 duplicate)

**Files:**
- Modify: `loop/scripts/validate_loop.py` (extend duplicate checks to the JSONL registers)
- Modify: `loop/tests/test_loop_tooling.py`
- Modify: `loop/registers/experiments.jsonl`

**Interfaces:**
- Consumes: `_duplicates()` (already defined in `validate_loop.py:69`) and `parse_jsonl()` (from `_common`).
- Produces: the invariant "every register with an `id` field has unique ids."

- [ ] **Step 1: Write the failing test**

```python
def test_registers_reject_duplicate_ids(self) -> None:
    errors = validate_loop.validate()
    self.assertEqual(errors, [], errors)  # after fix, EXP-003 dup is gone
    # guard: the helper flags an injected duplicate
    self.assertTrue(validate_loop._duplicates(["X", "X"]))
```

- [ ] **Step 2: Run and confirm it fails**

Run: `python -m unittest loop.tests.test_loop_tooling.LoopToolingTests.test_registers_reject_duplicate_ids -v`
Expected: FAIL — `validate()` currently returns `[]` (it never checked experiments), but after Step 3 adds the check it returns the `EXP-003` duplicate error until Step 4 fixes the data. (Run order: add check first, watch it flag, then fix.)

- [ ] **Step 3: Add register de-dup to `validate()`**

In `loop/scripts/validate_loop.py`, after the JSONL parse loop (around line 192), add:

```python
    for register in ("experiments", "assumptions", "changes", "decisions", "waivers", "risks"):
        suffix = "json" if register in {"risks"} else "jsonl"
        path = LOOP_ROOT / "registers" / f"{register}.{suffix}"
        if not path.exists():
            continue
        if suffix == "jsonl":
            rows = parse_jsonl(path)
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get(register, []) if isinstance(payload, dict) else []
        register_ids = [row.get("id", "") for row in rows if isinstance(row, dict)]
        if duplicate_ids := _duplicates(register_ids):
            errors.append(f"duplicate {register} ids: {sorted(duplicate_ids)}")
```

- [ ] **Step 4: Fix the duplicate — renumber the K-line experiment to EXP-004**

In `loop/registers/experiments.jsonl`, change the fourth record's `"id":"EXP-003"` (the `QPainter K-line performance` one, `work_item_id` `WI-022`) to `"id":"EXP-004"`. Then grep for stale references: `git grep -n "EXP-003"` — update any that meant the K-line experiment (the QNAM adapter one keeps `EXP-003`).

- [ ] **Step 5: Run gates green**

Run: `python loop/scripts/validate_loop.py && python -m unittest discover -s loop/tests`
Expected: exit 0, `OK`.

- [ ] **Step 6: Commit**

```bash
git add loop/scripts/validate_loop.py loop/tests/test_loop_tooling.py loop/registers/experiments.jsonl
git commit -m "loop: enforce register id uniqueness; fix duplicate EXP-003"
```

---

## Task 3: REQ↔WI edge agreement (catches the REQ-024 orphan)

**Files:**
- Modify: `loop/scripts/check_traceability.py`
- Modify: `loop/tests/test_loop_tooling.py`
- Modify: `loop/planning/work-items.json`

**Interfaces:**
- Consumes: `load_json("planning/work-items.json")`, the CSV rows already parsed in `check()`.
- Produces: the invariant "for every traceability row, each `work_item_ids` entry lists this REQ in its `requirements[]`, and vice-versa." Closes D1/D9.

- [ ] **Step 1: Write the failing test**

```python
def test_traceability_edges_agree_with_work_items(self) -> None:
    self.assertEqual(check_traceability.check(release=False), [])
```

- [ ] **Step 2: Run and confirm it fails (REQ-024 mismatch)**

Run: `python -m unittest loop.tests.test_loop_tooling.LoopToolingTests.test_traceability_edges_agree_with_work_items -v`
Expected: after Step 3 the check reports `REQ-024 <-> WI-008 edge disagrees` (traceability says WI-008;WI-020 own REQ-024 but those WIs don't list it) until Step 4.

- [ ] **Step 3: Add the edge-agreement check to `check_traceability.check()`**

In `loop/scripts/check_traceability.py`, build a REQ→WI map from work-items and compare. After `test_ids = {...}` (line 36) add:

```python
    work_rows = load_json("planning/work-items.json")["work_items"]
    wi_requirements = {row["id"]: set(row.get("requirements", [])) for row in work_rows}
```

Then inside the per-row loop, after the `work_item_ids` existence check, add:

```python
        for work_id in _split(row["work_item_ids"]):
            if work_id in wi_requirements and req_id not in wi_requirements[work_id]:
                errors.append(f"{req_id} trace row names {work_id} but that work item does not list {req_id}")
    # reverse direction: every WI requirement must appear in that REQ's trace row
    row_by_req = {r["requirement_id"].strip(): r for r in rows}
    for work_id, reqs in wi_requirements.items():
        for req in reqs:
            trace_row = row_by_req.get(req)
            if trace_row and work_id not in _split(trace_row["work_item_ids"]):
                errors.append(f"{req} is owned by {work_id} in work-items.json but its trace row omits {work_id}")
```

- [ ] **Step 4: Fix REQ-024 ownership in work-items.json**

In `loop/planning/work-items.json`, add `"REQ-024"` to the `requirements` arrays of `WI-008` and `WI-020` (the anti-fabrication numeric and network-fault items), matching `traceability.csv:25`. Re-run `git grep -n "REQ-024"` to confirm the CSV row and both WIs now agree.

- [ ] **Step 5: Run gates green**

Run: `python loop/scripts/check_traceability.py && python loop/scripts/validate_loop.py && python -m unittest discover -s loop/tests`
Expected: `TRACEABILITY_OK 30/30`, `LOOP_VALIDATION_OK ...`, `OK`.

- [ ] **Step 6: Commit**

```bash
git add loop/scripts/check_traceability.py loop/tests/test_loop_tooling.py loop/planning/work-items.json
git commit -m "loop: verify REQ<->WI edge agreement; assign REQ-024 to its owning work items"
```

---

## Task 4: Add the acceptance-criteria column to traceability (closes D3)

**Files:**
- Modify: `loop/scripts/check_traceability.py` (accept + validate the new column)
- Modify: `loop/quality/traceability.csv` (add column + values)
- Modify: `loop/product/ACCEPTANCE_CRITERIA.md` (fix line-16 cross-reference)
- Modify: `loop/tests/test_loop_tooling.py`

**Interfaces:**
- Consumes: the AC ids from `product/ACCEPTANCE_CRITERIA.md` (regex `AC-\d{3}`).
- Produces: `AC-000..AC-011` are now traced in the canonical CSV, making `ACCEPTANCE_CRITERIA.md:16` true.

- [ ] **Step 1: Write the failing test**

```python
def test_every_acceptance_criterion_is_traced(self) -> None:
    self.assertEqual(check_traceability.check(release=False), [])
    self.assertIn("acceptance_criteria", check_traceability.REQUIRED_COLUMNS)
```

- [ ] **Step 2: Run and confirm it fails**

Run: `python -m unittest loop.tests.test_loop_tooling.LoopToolingTests.test_every_acceptance_criterion_is_traced -v`
Expected: FAIL — `acceptance_criteria` is not yet a required column.

- [ ] **Step 3: Add the column and its coverage check**

In `loop/scripts/check_traceability.py`, add `"acceptance_criteria"` to `REQUIRED_COLUMNS`. Read AC ids and assert full coverage; after the row loop add:

```python
    acceptance_text = (LOOP_ROOT / "product/ACCEPTANCE_CRITERIA.md").read_text(encoding="utf-8")
    acceptance_ids = set(re.findall(r"\bAC-\d{3}\b", acceptance_text))
    traced_acceptance = {ac for row in rows for ac in _split(row.get("acceptance_criteria", ""))}
    if missing := acceptance_ids - traced_acceptance:
        errors.append(f"acceptance criteria not traced: {sorted(missing)}")
    for row in rows:
        for ac in _split(row.get("acceptance_criteria", "")):
            if ac not in acceptance_ids:
                errors.append(f"{row['requirement_id'].strip()} references unknown acceptance {ac}")
```

- [ ] **Step 4: Populate the column in the CSV**

In `loop/quality/traceability.csv`, add an `acceptance_criteria` header and fill each REQ row with the `AC-*` it satisfies (source of truth: each WI's `acceptance[]` in `work-items.json` joined by REQ). Ensure every `AC-000..AC-011` appears in at least one row.

- [ ] **Step 5: Fix the ACCEPTANCE_CRITERIA.md cross-reference**

`loop/product/ACCEPTANCE_CRITERIA.md` line 16 currently says the mapping lives in `traceability.csv`; keep the sentence but it is now accurate. If wording implies a per-AC row, adjust to "见 `../quality/traceability.csv` 的 `acceptance_criteria` 列".

- [ ] **Step 6: Run gates green + commit**

Run: `python loop/scripts/check_traceability.py && python -m unittest discover -s loop/tests`
Expected: `TRACEABILITY_OK 30/30`, `OK`.

```bash
git add loop/scripts/check_traceability.py loop/quality/traceability.csv loop/product/ACCEPTANCE_CRITERIA.md loop/tests/test_loop_tooling.py
git commit -m "loop: trace acceptance criteria in the canonical traceability file"
```

---

## Task 5: Cross-check `state.risk_ids` against the risk register (closes D10)

**Files:**
- Modify: `loop/scripts/validate_loop.py`
- Modify: `loop/tests/test_loop_tooling.py`

**Interfaces:**
- Consumes: `state/current.json.risk_ids`, `registers/risks.json`. Data is already consistent (RISK-001..010 on both sides), so this is check-only.

- [ ] **Step 1: Write the failing test**

```python
def test_state_risk_ids_match_register(self) -> None:
    self.assertEqual(validate_loop.validate(), [], validate_loop.validate())
```

(This passes today; the guard is that after Step 2 the new check still yields `[]` because the data agrees — the value is regression protection. To prove the check bites, temporarily add a fake id to `risk_ids` locally and confirm an error, then revert.)

- [ ] **Step 2: Add the cross-check**

In `loop/scripts/validate_loop.py`, after the risk-score loop (around line 309):

```python
    register_risk_ids = {risk.get("id") for risk in risks_payload.get("risks", [])}
    state_risk_ids = set(current.get("risk_ids", []))
    if unknown := state_risk_ids - register_risk_ids:
        errors.append(f"state/current.json risk_ids not in register: {sorted(unknown)}")
```

- [ ] **Step 3: Run gates green + commit**

Run: `python loop/scripts/validate_loop.py && python -m unittest discover -s loop/tests`
Expected: exit 0, `OK`.

```bash
git add loop/scripts/validate_loop.py loop/tests/test_loop_tooling.py
git commit -m "loop: cross-check current-state risk ids against the risk register"
```

---

## Task 6: `REQUIRED_FILES` completeness + clean missing-file error (closes D11)

**Files:**
- Modify: `loop/scripts/validate_loop.py`
- Modify: `loop/tests/test_loop_tooling.py`

**Interfaces:**
- Produces: `quality/test-catalog.json` and `planning/dependency-graph.json` are required and their absence yields a clean `missing required file:` error instead of a traceback.

- [ ] **Step 1: Write the failing test**

```python
def test_dereferenced_files_are_declared_required(self) -> None:
    for needed in ("quality/test-catalog.json", "planning/dependency-graph.json"):
        self.assertIn(needed, validate_loop.REQUIRED_FILES, needed)
```

- [ ] **Step 2: Run and confirm it fails**

Run: `python -m unittest loop.tests.test_loop_tooling.LoopToolingTests.test_dereferenced_files_are_declared_required -v`
Expected: FAIL — neither path is in `REQUIRED_FILES` today.

- [ ] **Step 3: Add both paths to `REQUIRED_FILES`**

In `loop/scripts/validate_loop.py`, add `"quality/test-catalog.json",` and `"planning/dependency-graph.json",` to the `REQUIRED_FILES` tuple. (The existing early loop then reports a clean `missing required file:` before the unconditional `load_json` at lines 195/243 is reached.)

- [ ] **Step 4: Run gates green + commit**

Run: `python loop/scripts/validate_loop.py && python -m unittest discover -s loop/tests`
Expected: exit 0, `OK`.

```bash
git add loop/scripts/validate_loop.py loop/tests/test_loop_tooling.py
git commit -m "loop: declare test-catalog and dependency-graph as required files"
```

---

## Task 7: Close the remaining data defects (D4, D7, D8, D13)

**Files:**
- Modify: `loop/config.json` (D4 market timezone)
- Modify: `loop/LOOP_PROTOCOL.md` (D7 RECOVER)
- Modify: `loop/decisions/0001-adopt-pyside6.md` and/or `loop/governance/SCOPE_AND_AUTHORITY.md` (D8 HG-ARCH)
- Modify: `loop/planning/milestones.json` + `loop/planning/dependency-graph.json` (D13 MS edge)

**Interfaces:**
- Produces: consistent, buildable specs; no dangling protocol state; acyclic milestone graph consistent with `depends_on`.

- [ ] **Step 1 (D4): Add an explicit market timezone**

In `loop/config.json` under `project`, add `"market_timezone": "Asia/Shanghai"` (keep `timezone: Asia/Tokyo` as the local display/log tz, or rename it to `local_timezone` and update `render_status`/`update_state` references — the minimal edit is to add `market_timezone` and note the split in a comment field). Add a validator assertion in `validate_loop.py`:

```python
    if config.get("project", {}).get("market_timezone") != "Asia/Shanghai":
        errors.append("config market_timezone must be Asia/Shanghai for A-share sessions")
```

with a matching test asserting `validate()==[]`.

- [ ] **Step 2 (D7): Resolve the dangling RECOVER state**

In `loop/LOOP_PROTOCOL.md §3`, add a `### RECOVER` subsection (inputs: failed step + persisted state; outputs: safe state + diagnosis; exit: state re-stabilised, resume at OBSERVE) and an arrow back to OBSERVE; OR remove RECOVER from the diagram. Prefer defining it. Keep README's 9-stage list in sync.

- [ ] **Step 3 (D8): Reconcile HG-ARCH status**

Make `decisions/0001-adopt-pyside6.md` and `governance/SCOPE_AND_AUTHORITY.md` agree: ADR-0001 is `accepted` (the architecture decision is made), while `HG-ARCH` remains an open human gate bound to `WI-001` (repository alignment not yet executed). Edit whichever doc conflates the two so the ADR being accepted does not read as the gate being cleared.

- [ ] **Step 4 (D13): Add the MS-02→MS-01 dependency**

In `loop/planning/milestones.json`, add `MS-01` to `MS-02.depends_on` (WI-009∈MS-02 depends on WI-003∈MS-01). If a milestone dependency graph is derived, regenerate it.

- [ ] **Step 5: Run gates green + commit**

Run: `python loop/scripts/validate_loop.py && python loop/scripts/check_traceability.py && python -m unittest discover -s loop/tests`
Expected: all exit 0.

```bash
git add loop/config.json loop/LOOP_PROTOCOL.md loop/decisions/0001-adopt-pyside6.md loop/governance/SCOPE_AND_AUTHORITY.md loop/planning/milestones.json
git commit -m "loop: fix market timezone, RECOVER state, HG-ARCH status, MS-02 dependency"
```

---

## Task 8: Tighten schemas (closes D6) + wire JSONL register schemas

**Files:**
- Modify: `loop/schemas/*.json` (closed-record schemas)
- Modify: `loop/scripts/validate_loop.py` (validate each JSONL line against a per-register schema)
- Modify: `loop/tests/test_loop_tooling.py`

**Interfaces:**
- Produces: unknown/typo'd fields are rejected on closed records; `schema_version` is pinned; JSONL registers are line-validated. The validator already supports `additionalProperties:false` and `const` (`_common.validate_against_schema`).

- [ ] **Step 1: Write the failing test**

```python
def test_closed_schemas_reject_unknown_fields_and_pin_version(self) -> None:
    import json as _json
    from pathlib import Path as _Path
    closed = ["state", "loop", "config", "work-items", "quality-gates",
              "risk", "evidence", "metrics", "backlog", "milestones"]
    root = _Path(validate_loop.LOOP_ROOT) / "schemas"
    for name in closed:
        schema = _json.loads((root / f"{name}.schema.json").read_text(encoding="utf-8"))
        self.assertIs(schema.get("additionalProperties"), False, name)
        sv = schema.get("properties", {}).get("schema_version", {})
        self.assertTrue("const" in sv or "pattern" in sv, name)
```

- [ ] **Step 2: Run and confirm it fails**

Run: `python -m unittest loop.tests.test_loop_tooling.LoopToolingTests.test_closed_schemas_reject_unknown_fields_and_pin_version -v`
Expected: FAIL — root `additionalProperties` is `true` and `schema_version` is unpinned.

- [ ] **Step 3: Tighten the closed-record schemas**

For each schema in the `closed` list (and any other single-object closed record), at the root object set `"additionalProperties": false` and change the `schema_version` property to `{"type": "string", "const": "1.0.0"}`. Leave genuinely open/extensible schemas (e.g. free-form note maps) as `true` and document why in a `description`. Run `python loop/scripts/validate_loop.py` after each file to catch any real unknown field the tightening exposes (fix by adding the field to the schema, not by loosening).

- [ ] **Step 4: Add per-register JSONL line schemas**

Create `loop/schemas/experiment.schema.json`, `assumption.schema.json`, `change.schema.json`, `decision.schema.json`, `waiver.schema.json` (each a closed object with `id` pattern + required fields matching current records). In `validate_loop.py`, in the JSONL parse loop, validate each parsed object against its register schema via `validate_against_schema`. Retire the orphan `register-entry.schema.json` or repurpose it as the shared base.

- [ ] **Step 5: Update the schema count assertion**

`test_status_mentions_authoritative_state` asserts `Loop schemas: \`20\``. After adding schemas, update `state/metrics.json.control_plane.schema_documents_validated` and re-render STATUS (done in Task 9); adjust the test's literal to the new count.

- [ ] **Step 6: Run gates green + commit**

Run: `python loop/scripts/validate_loop.py && python -m unittest discover -s loop/tests`
Expected: exit 0, `OK`.

```bash
git add loop/schemas loop/scripts/validate_loop.py loop/tests/test_loop_tooling.py
git commit -m "loop: close record schemas, pin schema_version, validate JSONL registers"
```

---

## Task 9: Fix evidence spelling, re-baseline the control plane, re-render state

**Files:**
- Modify: `loop/evidence/baselines/*.txt` + `loop/state/evidence-index.json` (D12 `cwd` spelling)
- Modify: `loop/planning/work-items.json`, `loop/planning/milestones.json`, `loop/planning/dependency-graph.json`, `loop/quality/traceability.csv`, `loop/quality/test-catalog.json` (register `WI-026` + `TEST-LOOP-002`)
- Create: `loop/evidence/baselines/EVD-LOOP-004-hardening.txt` + index entry
- Modify: `loop/state/current.json`, `loop/state/metrics.json`, `loop/STATUS.md` (via scripts)

**Interfaces:**
- Consumes: `control_plane_digest()` of the fully hardened tree.
- Produces: `EVD-LOOP-004` as the new current v2 baseline (so digest enforcement is restored), `EVD-LOOP-003` superseded, all counts re-rendered.

- [ ] **Step 1: Fix the `cwd` spelling (D12)**

In every `loop/evidence/baselines/*.txt` and their `state/evidence-index.json` entries, replace `stock-adviser` → `stock-advisor`. Because these `.txt` artifacts are hashed in the index, recompute each artifact's `sha256` and update the index (`python -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('loop/evidence/baselines/EVD-BASE-001-unittest.txt').read_bytes()).hexdigest())"`). These files are under `evidence/`, excluded from the control-plane digest, so this does not perturb Task 9's re-baseline.

- [ ] **Step 2: Register the hardening as WI-026**

Add `WI-026` to `loop/planning/work-items.json` (title "Loop 控制面加固与自检强化", milestone `MS-00`, status `accepted`, `requirements` `["REQ-027","REQ-028"]`, `acceptance` `["AC-000"]`, `tests` `["TEST-LOOP-002"]`, `evidence_ids` `["EVD-LOOP-004"]`). Add `TEST-LOOP-002` to `quality/test-catalog.json`. Add `WI-026` to `MS-00` in `milestones.json`. Add its rows/edges to `traceability.csv` and regenerate `planning/dependency-graph.json`.

- [ ] **Step 3: Capture the new baseline evidence**

Run the control gates and write their combined output to `loop/evidence/baselines/EVD-LOOP-004-hardening.txt` (commands + exit codes, mirroring `EVD-LOOP-003`'s format). Compute the digest:

```bash
python -c "import sys; sys.path.insert(0,'loop/scripts'); import _common; print(_common.control_plane_digest())"
```

Add an `EVD-LOOP-004` record to `state/evidence-index.json` (`record_version` `2.0.0`, `control_plane_sha256` = that digest, `implemented_by` ≠ `verified_by`, `work_item_id` `WI-026`, artifact path + its sha256). Confirm `EVD-LOOP-003.superseded_by == "EVD-LOOP-004"` (set in Task 1).

- [ ] **Step 4: Re-render state, status, metrics**

Update `state/metrics.json` (`schema_documents_validated`, tool-test counts) and `state/current.json` (`latest_gate_run_id`, `completed_ids` include `WI-026`), then:

```bash
python loop/scripts/render_status.py --write
python loop/scripts/render_backlog.py --write
```

- [ ] **Step 5: Full green run**

Run:
```bash
python loop/scripts/validate_loop.py && \
python loop/scripts/check_traceability.py && \
python loop/scripts/render_status.py --check && \
python loop/scripts/render_backlog.py --check && \
python loop/scripts/check_core_boundaries.py && \
python -m unittest discover -s loop/tests && \
python -m unittest discover -s tests && \
python main.py --self-test
```
Expected: every command exit 0; `LOOP_VALIDATION_OK`, `TRACEABILITY_OK 30/30` (or the new row count), `STATUS_OK`, `BACKLOG_OK`, `CORE_BOUNDARY_OK`, `OK`, `SELF_TEST_OK`. The re-baseline restores full digest enforcement against the hardened tree.

- [ ] **Step 6: Record progress + commit**

```bash
python loop/scripts/record_progress.py --work-item WI-026 --action "loop hardening" \
  --result "checks/schemas strengthened; 13 defects closed; re-baselined" \
  --next "proceed to Plan 2 (src package restructuring)" --evidence EVD-LOOP-004
git add loop
git commit -m "loop: re-baseline control plane after hardening (EVD-LOOP-004, WI-026)"
```

---

## Self-Review

- **Spec coverage:** Plan covers WS-1 (Tasks 1,2,3,5,6,8 — checker/schema hardening) and WS-2 (Tasks 2,3,4,7,9 — the 13 defects D1–D13). The gate-invariant (D5) is intentionally deferred to Plan 5/WS-8, where the empty gates gain commands and owning WIs; noted so it is not silently dropped.
- **Placeholder scan:** every code step shows real code or an exact edit; data edits name the file and the field.
- **Type consistency:** `_digest_ok(record)` (Task 1) and `_duplicates(list)` (Task 2, pre-existing) are the only new helpers; both used consistently.
- **Ordering:** Task 1 unblocks all `loop/` edits; Task 9 restores digest enforcement. Intermediate tasks are green because no non-superseded v2 baseline exists between Task 1 and Task 9.
