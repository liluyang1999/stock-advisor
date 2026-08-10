# Documentation Reconciliation Plan (Plan 5 of 6 · WS-9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Establish `loop/` as the single source of truth by extracting the still-valuable content out of the 15 **legacy** `docs/superpowers/` docs (pre-`2026-07-11`, Tkinter-era), consolidating it where it belongs, adding a docs index + archive policy, and then deleting the legacy files (recoverable from git history).

**Architecture:** Extraction into `loop/` re-baselines (F1); the docs index + deletions are outside `loop/` (no digest change). Executed **directly on `main`**. The oracle is the six control gates + product 449 + self-test, plus a grep sweep proving no dangling references to deleted files.

**Tech Stack:** Markdown under `docs/` and `loop/`; the stdlib control scripts as validators.

## Global Constraints

- Writes/deletes limited to `loop/` and `docs/`. No product code. **Stay on branch `main`.**
- **KEEP (do NOT delete)** the 5 CURRENT design/plan docs (dated `2026-07-11` and later): `specs/2026-07-11-loop-hardening-and-tooling-design.md`, `plans/2026-07-11-01-foundation-hardening.md`, `plans/2026-07-12-02-src-package-restructure.md`, `plans/2026-07-12-03-plans-requirements-testgoals.md`, `plans/2026-07-13-04-architecture-governance.md`, and this file. Also KEEP `docs/ui-concepts/` and `docs/stock_advisor_technical_stack_report.html` unless a step says otherwise.
- **DELETE (legacy, pre-2026-07-11)** exactly these 15: `specs/2026-06-21-stock-advisor-design.md`, `specs/2026-06-22-market-screener-and-ui-design.md`, `specs/2026-06-24-alerts-design.md`, `specs/2026-06-24-decision-strength-and-modules-design.md`, `specs/2026-06-24-watchlist-compare-hover-design.md`, `specs/2026-07-09-delivery-convergence-design.md`, `specs/2026-07-09-ui-overhaul-and-completeness-design.md`, `plans/2026-06-21-stock-advisor-implementation.md`, `plans/2026-06-24-decision-strength-and-modules.md`, `plans/2026-06-24-watchlist-compare-hover.md`, `plans/2026-07-09-delivery-convergence-implementation.md`, `plans/2026-07-09-ui-overhaul-foundation.md`, `plans/2026-07-09-ui-overhaul-p2-geometry-rendering.md`, `plans/2026-07-09-ui-overhaul-p3-layout-visual.md`, `plans/2026-07-10-ui-overhaul-p4-functional-gaps.md`.
- Extraction into `loop/` → re-baseline that task. Docs-only tasks (index, deletion) do NOT touch the loop digest → no re-baseline.
- Nothing valuable is lost: everything deleted must either already exist in `loop/`/`src/` or be extracted first.

## Task 1: Extract still-valuable content into loop/ (before deleting anything)

**Files:** `loop/architecture/DATA_FLOW.md` and/or `loop/architecture/DATA_QUALITY.md` (Eastmoney field contract), possibly `loop/product/REQUIREMENTS.md`/a new `loop/product/PRODUCT_CAPABILITIES.md`; read the 15 legacy docs + `src/`.

- [ ] **Step 1 — Screener/Eastmoney contract.** Read `docs/superpowers/specs/2026-06-22-market-screener-and-ui-design.md`. Extract the unique, still-authoritative content NOT already in `loop/`: the six screener-preset parameter table and the Eastmoney clist field contract (`f2`–`f25`, `fs` market selectors, `secid`/`f13` market number, `920xxx` Beijing exchange codes). Add it to `loop/architecture/DATA_FLOW.md` (or `DATA_QUALITY.md`), citing it as the market-data field contract. (Cross-check against `AGENTS.md`'s existing 行情数据约定 to avoid duplication — add only what's missing.)
- [ ] **Step 2 — P4 functional-fix audit.** Read `docs/superpowers/plans/2026-07-10-ui-overhaul-p4-functional-gaps.md`. For each functional fix it describes (bound-cross validation, L3==objective rounding, single disclaimer, alert FIELD_LABELS, fund-flow threading), CONFIRM it is already present in `src/stock_advisor/` (grep the domain/ui modules). List any that are NOT present as a fast-follow in the report — do NOT implement them here (product code out of scope).
- [ ] **Step 3 — Other unique knowledge.** Skim the remaining 13 legacy docs; anything uniquely valuable and not in `loop/` (a domain rule, a rationale) gets a one-line capture in the appropriate `loop/` doc. Most will already be covered by `loop/product`/`architecture` + `src/` — note "already covered" per file.
- [ ] **Step 4 — Re-baseline (loop/ touched) + gates green; commit** `loop: extract legacy screener/Eastmoney field contract + capabilities into loop architecture`.

## Task 2: Docs index + archive/hygiene policy

**Files:** new `docs/README.md`; `loop/governance/` (a short doc-hygiene policy — this touches loop/ → re-baseline).

- [ ] **Step 1 — Docs index.** Create `docs/README.md`: state that `loop/` is the single source of truth; list the current design spec + plans (the 5 kept files) with one-line descriptions; note that the pre-2026-07-11 Tk-era `docs/superpowers/` material has been superseded by `loop/` + ADR-0001 (PySide6) and removed (recoverable from git history, e.g. commit range / the baseline `61b3cde`).
- [ ] **Step 2 — Hygiene policy.** Add a short "documentation hygiene" note to `loop/governance/` (or `loop/README.md`): `loop/` is authoritative; new design work goes to `docs/superpowers/specs|plans/`; superseded material is removed, not left to rot, with a git-history pointer. (loop/ edit → re-baseline this task.)
- [ ] **Step 2b — Re-baseline + gates green; commit** `docs: add docs index; loop: doc-hygiene policy (loop as SSOT)`.

## Task 3: Delete the 15 legacy docs

**Files:** the 15 legacy `docs/superpowers/{specs,plans}/*.md` listed in Global Constraints.

- [ ] **Step 1 — Delete** with `git rm` exactly the 15 legacy files (double-check each date is < 2026-07-11 and it is NOT one of the 5 kept files).
- [ ] **Step 2 — No dangling references.** `git grep -n` for each deleted filename across the repo (excluding git history); the only remaining mentions may be in THIS plan and `docs/README.md`'s note. Fix any real dangling link. Confirm the 5 kept design/plan docs are still present.
- [ ] **Step 3 — Gates + product green (docs-only, no re-baseline needed, but confirm)**; commit `docs: remove superseded pre-2026-07-11 Tk-era superpowers docs (extracted into loop; recoverable from git history)`.

## Task 4: Close-out

- [ ] Append a `record_progress.py --work-item WI-000` line summarizing Plan 5 (WS-9); recompute the digest and update `EVD-LOOP-004`; run the FULL gate set + 449 + self-test; commit `loop: record Plan 5 (doc reconciliation) progress + final re-baseline`.

## Self-Review

- **Spec coverage (WS-9):** Task 1 extracts the named-valuable content (screener/Eastmoney contract) + audits P4 fixes before any deletion; Task 2 adds the docs index + SSOT policy; Task 3 deletes exactly the 15 legacy files with a dangling-reference sweep; Task 4 closes out. The KEEP/DELETE lists are explicit so no current plan/spec is lost.
- **Placeholder scan:** file lists are exhaustive and dated; extraction targets are concrete (`DATA_FLOW`/`DATA_QUALITY`).
- **Safety:** nothing is deleted before its value is extracted or confirmed present in `loop/`/`src/`; everything is git-recoverable; the grep sweep proves no broken links.
- **Ordering:** extract (1) → index/policy (2) → delete (3) → close-out (4). Re-baseline only on the loop/-touching tasks (1, 2, 4).
