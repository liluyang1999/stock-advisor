# Architecture & Governance Hardening Plan (Plan 4 of 6 · WS-5 + WS-7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the architecture specs *buildable* (quantify the computation contract, add missing config values, define the product config schema, specify observability), bring every ADR to the project's own template, add the missing decision records, and lay the conventional-engineering governance floor (version/change control, waivers, SOURCES verification, glossary, invariants, distribution security).

**Architecture:** All changes are `loop/` docs + machine files; no product code. Executed **directly on `main`** (per the user's consolidation request). Each `loop/`-editing task ends with a paired `EVD-LOOP-004` re-baseline (the Plan-1 F1 invariant pins the live-baseline digest, so any `loop/` edit needs it). The six control gates + product 449 + self-test are the oracle.

**Tech Stack:** Markdown + JSON under `loop/`; the stdlib control scripts as validators; ADR discipline enforced by `validate_loop`'s ADR-triangle check.

## Global Constraints

- Writes only inside `loop/` (+ nothing else). **Stay on branch `main`** — no branch creation/switching.
- Every task ends green: `validate_loop`, `check_traceability` (34/34), `render_status --check`, `render_backlog --check`, `check_core_boundaries`, `unittest discover -s loop/tests`; product `unittest discover -s tests` (449) + `main.py --self-test` unaffected but confirm.
- **Per-task re-baseline:** after edits, recompute `control_plane_digest()` and surgically replace `EVD-LOOP-004.control_plane_sha256` in `state/evidence-index.json` with the new value (evidence-index is digest-excluded).
- New ADRs must add both a `decisions/NNNN-*.md` (with `- 状态：accepted`) AND a matching `registers/decisions.jsonl` line `{"id":"ADR-NNNN","status":"accepted",...}` (accepted ⇒ NOT in `current.json.pending_decision_ids`) — the ADR triangle in `validate_loop` enforces this.
- **ADR numbering:** `ADR-0001..0007` exist (0007 = source-package-layering). New ADRs start at **`ADR-0008`**.
- Documenting product algorithm values means READING `src/stock_advisor/domain/engine.py` (and siblings) — read-only reference; do not change product code.
- No check weakened; reconcile data to pass.

## Reference: current state
- ADRs: 0001-adopt-pyside6, 0002-preserve-pure-domain-core, 0003-qt-concurrency-boundary, 0004-packaging-strategy, 0005-microsoft-yahei, 0006-chart-rendering, 0007-source-package-layering. Template: `loop/templates/ADR.md`; rules: `loop/decisions/README.md`.
- Product modules now live under `src/stock_advisor/{domain,data,services,ui}/`.
- Market timezone already added to config (`Asia/Shanghai`), RECOVER already defined, HG-ARCH already reconciled (Plan 1) — do NOT redo these.

---

## Task 1: Make the architecture specs buildable (WS-5 specs)

**Files:** `loop/architecture/COMPUTATION_SPECIFICATION.md`, `loop/architecture/DATA_QUALITY.md`, `loop/config.json`, `loop/architecture/PERSISTENCE_AND_CONFIG.md` (+ a new `loop/product/app-config.schema.json` or an inline schema block), `loop/architecture/OBSERVABILITY.md`.

- [ ] **Step 1 — Quantify the computation contract.** Read `src/stock_advisor/domain/engine.py` (and `policy.py`, `backtest.py`) and fill `COMPUTATION_SPECIFICATION.md` with the ACTUAL numeric values it uses: the `history_bonus` / `available_indicator_bonus` / `high_atr_penalty` (and any other bonus/penalty) magnitudes, and the indicator windows — MACD (fast/slow/signal), Bollinger (period/σ), ATR window, MA windows. The spec must let a reader reproduce the score without reading the code. Do not change engine.py.
- [ ] **Step 2 — Stale TTLs.** `DATA_QUALITY.md` references a stale/scenario TTL with no values. Add per-operation TTL seconds to `loop/config.json` (`network_policy` or a new `data_freshness` block): quote / history / market_snapshot / fund_flow. Cite them from `DATA_QUALITY.md`. (config.json is schema-validated — if adding a block trips `config.schema.json`, add the property there, keeping it closed.)
- [ ] **Step 3 — Product AppConfig schema.** `PERSISTENCE_AND_CONFIG.md` promises a baseline config schema. Define the product `AppConfig` fields + a `schema_version` (read `src/stock_advisor/domain/models.py`'s `AppConfig` dataclass and `services/store.py` for the persisted shape) as a `loop/product/app-config.schema.json` (with `$schema` so it's validated → schema_documents rises by 1: update `metrics.json` `schema_documents_validated` + STATUS + the test literal). Document the migration/back-compat note.
- [ ] **Step 4 — Observability.** Flesh out `OBSERVABILITY.md`: log sink (stderr + optional rotating file under `%APPDATA%`), format (structured, no PII/secrets), rotation policy, and an explicit `error_class` taxonomy (network/parse/validation/gui/packaging/…) that the network+data specs reference.
- [ ] **Step 5 — Re-baseline + gates green; commit** `loop: quantify computation spec + stale TTLs + product AppConfig schema + observability`.

---

## Task 2: Bring ADR-0001..0006 to the project template (WS-5 ADR compliance)

**Files:** `loop/decisions/0001..0006-*.md`, optionally `loop/scripts/validate_loop.py` + `loop/tests/test_loop_tooling.py` (a lightweight ADR-section check).

- [ ] **Step 1** — For each of `0001..0006`, read `loop/templates/ADR.md` + `loop/decisions/README.md` and add the missing mandated sections so each has: 背景, 决策, ≥2 备选（含被否方案）, 后果 (positive + negative/cost), 回滚, revisit 触发, and a 关联 section citing REQ/AC/WI/RISK/EVD ids. Use `0007-source-package-layering.md` as the model (it is template-complete). Do not change any ADR's `- 状态：` line or its `decisions.jsonl` entry (status is unchanged).
- [ ] **Step 2 (optional, only if it stays green)** — add a check that every `decisions/NNNN-*.md` contains a `## 关联` (or equivalent) section, with a test. If markdown-section detection is fragile, SKIP this and note it — the content fix in Step 1 is the required win.
- [ ] **Step 3 — Re-baseline + gates green; commit** `loop: bring ADR-0001..0006 to the project ADR template`.

---

## Task 3: Add the missing decision records (WS-5 new ADRs)

**Files:** new `loop/decisions/0008..0012-*.md`, `loop/registers/decisions.jsonl`, and back-references from the specs that promised them.

Add these ADRs (each `状态：accepted`, template-complete, + a `decisions.jsonl` accepted line):
- [ ] **ADR-0008 dev-toolchain** — adopt ruff (format+lint) + pyright (type) + pytest/pytest-qt + coverage + pre-commit, dev-only; record the pyright↔"no-Node" carve-out (dev-only tool, never in the EXE). 关联 REQ-028.
- [ ] **ADR-0009 config schema versioning & Qt layout persistence** — the `AppConfig` schema_version discipline (from Task 1) + how Qt window/splitter layout will persist (QSettings vs config). Resolves the PERSISTENCE promise. 关联 REQ-009.
- [ ] **ADR-0010 test-framework migration** — unittest → pytest/pytest-qt as the runner (keep existing unittest tests running; new Qt/property tests in pytest). 关联 REQ-028.
- [ ] **ADR-0011 observability/logging approach** — stdlib logging + the sink/rotation/error_class model from Task 1 Step 4. 关联 REQ-023.
- [ ] **ADR-0012 market timezone & trading calendar** — `market_timezone=Asia/Shanghai` (already in config) + trading-day/session boundary + t-day anti-look-ahead semantics. 关联 REQ-019/REQ-021.
- [ ] **Re-baseline + gates green; commit** `loop: add ADR-0008..0012 (dev-toolchain, config-versioning, test-framework, observability, market-timezone)`.

---

## Task 4: Governance floor (WS-7)

**Files:** new `loop/governance/VERSION_AND_CHANGE_CONTROL.md`, new root-adjacent `loop/CHANGELOG.md` (or `loop/governance/CHANGELOG.md`), `loop/governance/ENGINEERING_RULES.md`, `loop/governance/DEFINITION_OF_DONE.md`, `loop/registers/waivers.jsonl` (schema/example), `loop/governance/SECURITY_AND_DATA_ETHICS.md`, `loop/architecture/PACKAGING_AND_DEPLOYMENT.md`, `loop/governance/GLOSSARY.md`, `loop/LOOP_PROTOCOL.md`, `loop/README.md`, `loop/AGENTS.md`.

- [ ] **Step 1 — Version & change control.** New `VERSION_AND_CHANGE_CONTROL.md`: branch model, atomic imperative commit messages, app SemVer, changelog obligation; add a `CHANGELOG.md` seed.
- [ ] **Step 2 — Unify skip↔waiver.** Reconcile `ENGINEERING_RULES.md` ("禁止跳过") with `DEFINITION_OF_DONE.md` ("0 未批准 skip"): approved skips are recorded in `registers/waivers.jsonl` (owner + expiry); reference from both. Add a waiver record example + (if clean) a validate check that waivers have owner+expiry.
- [ ] **Step 3 — Implementer/verifier mechanism.** In `LOOP_PROTOCOL.md §7`, specify the concrete mechanism (fresh-context/separate-subagent verifier that re-runs ≥ required gates without the implementer's rationale).
- [ ] **Step 4 — SOURCES + glossary + invariants.** Verify (or downgrade to "inspiration, not citation") the `SOURCES.md` citations (arXiv/URL/version claims); add the ID taxonomy (REQ/AC/WI/TEST/EVD/ADR/RISK/HG/G, V0–V5, terminal states, roles) to `GLOSSARY.md` and reconcile the two "Loop" definitions; define ONE canonical `INVARIANTS` list (in README or governance) and have the other restatements reference it.
- [ ] **Step 5 — Distribution security.** In `SECURITY_AND_DATA_ETHICS.md`/`PACKAGING_AND_DEPLOYMENT.md`, add a Windows EXE code-signing / SmartScreen-provenance line and a Qt LGPL NOTICE/attribution plan (or an explicit deferral with rationale).
- [ ] **Step 6 — Re-baseline + gates green; commit** `loop: governance floor — version/change control, waivers, verifier mechanism, SOURCES/glossary/invariants, distribution security`.

---

## Task 5: Close-out

- [ ] Append a `record_progress.py --work-item WI-000` line summarizing Plan 4; recompute the digest and update `EVD-LOOP-004`; run the FULL gate set + 449 + self-test; commit `loop: record Plan 4 progress + final re-baseline`.

---

## Self-Review

- **Spec coverage:** Task 1 = WS-5 buildability (computation, TTL, AppConfig schema, observability); Tasks 2-3 = WS-5 ADR compliance + the 5 missing ADRs (0008-0012, correctly numbered after 0007); Task 4 = WS-7 governance floor; Task 5 = close-out. Items already done in earlier plans (RECOVER, HG-ARCH, market_timezone value) are explicitly excluded.
- **Placeholder scan:** ADR ids/topics, the config blocks, and the new files are concrete; the computation values are derived from the actual `domain/engine.py`.
- **Consistency:** each new ADR is a full triangle (md + decisions.jsonl, accepted, not pending); each `loop/` edit re-baselines; the one count-moving change (AppConfig schema doc) calls out the metrics/STATUS/test-literal bump.
- **Risk:** the ADR-template content pass is judgment-heavy — the verifier subagent + the (optional) section check are the net; the computation quantification must match engine.py exactly — the reviewer cross-checks against the code.
