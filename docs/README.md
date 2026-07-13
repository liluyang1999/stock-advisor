# docs/ — Documentation Index

`loop/` is this repository's single source of truth (SSOT) for engineering control: current
goals, requirements, acceptance criteria, work items, architecture decisions, the risk register,
quality gates, and verification evidence all live under `loop/` (start at `loop/README.md`). Where
anything under `docs/` seems to disagree with `loop/` about current state or requirements, `loop/`
wins.

`docs/` holds the narrative planning artifacts that feed `loop/`: dated design specs and
implementation plans, written mainly for agentic coding workers executing a plan task-by-task.
They are a historical/working record of *how* the current `loop/` state was reached, not a second
source of truth for *what* it currently is.

## Current design & plan docs (kept)

Dated `2026-07-11` or later. These 6 files are the only docs under `docs/superpowers/` still
considered current; everything older there is legacy (see below).

| Doc | One-line description |
|---|---|
| `docs/superpowers/specs/2026-07-11-loop-hardening-and-tooling-design.md` | Design spec for hardening the `loop/` control plane and landing a modern dev toolchain, ahead of the Tkinter→PySide6 migration. |
| `docs/superpowers/plans/2026-07-11-01-foundation-hardening.md` | Plan 1/6: make `loop/`'s own validators self-check invariants they previously only asserted in prose, and close 13 evidenced control-plane defects. |
| `docs/superpowers/plans/2026-07-12-02-src-package-restructure.md` | Plan 2/6 (WS-R): behavior-preserving reorganization of `src/stock_advisor/` into `domain/`, `data/`, `services/`, `ui/` subpackages. |
| `docs/superpowers/plans/2026-07-12-03-plans-requirements-testgoals.md` | Plan 3/6 (WS-3+WS-4+WS-6): measurable test expected-goals, completed requirements (missing NFRs, UI tokens, REQ↔AC linkage), and richer per-work-item planning. |
| `docs/superpowers/plans/2026-07-13-04-architecture-governance.md` | Plan 4/6 (WS-5+WS-7): quantify the architecture/computation specs, bring every ADR to the project template, add missing ADRs, and lay the governance floor (version control, waivers, SOURCES verification, glossary, invariants, distribution security). |
| `docs/superpowers/plans/2026-07-13-05-doc-reconciliation.md` | Plan 5/6 (WS-9, this plan): extract remaining unique value from the legacy pre-2026-07-11 docs into `loop/`, add this index and the doc-hygiene policy, then delete the legacy docs. |

## Legacy `docs/superpowers/` material (pre-2026-07-11, superseded)

The 15 specs and plans dated `2026-06-21` through `2026-07-10` — the original Tkinter-era product
design and its subsequent iterations (market screener/UI, alerts, decision-strength & modules,
watchlist/compare/hover, delivery convergence, and the four-part UI overhaul) — have been
superseded by `loop/` (current requirements, architecture, and decisions now live there) and by
**ADR-0001** (`loop/decisions/0001-adopt-pyside6.md`), which replaces their Tkinter-first framing
with PySide6 as the production GUI target.

Their still-valuable content (e.g. the screener/Eastmoney field contract) was extracted into
`loop/architecture/` before removal. They are being removed as part of this
documentation-reconciliation effort rather than left to rot alongside the current docs — see
"Documentation hygiene" below. Nothing is lost: every one of them is recoverable from git history,
present from the initial baseline commit `0d2fdf7` ("chore: initial baseline snapshot") onward:

```bash
git ls-tree -r --name-only 0d2fdf7 -- docs/superpowers      # list the legacy files as of the baseline
git show 0d2fdf7:docs/superpowers/specs/<name>.md           # recover one file's content at that commit
git log --all --full-history -- docs/superpowers/<specs-or-plans>/<name>.md   # full history of one file
```

## Also under `docs/` (unaffected by this reconciliation)

- `docs/ui-concepts/` — UI concept mockups (`r2/`, `r3/`: Tkinter-era rounds; `pyside6-r1/`,
  `pyside6-r2/`: PySide6 rounds).
- `docs/stock_advisor_technical_stack_report.html` — standalone "技术栈、原理与实现" (technical
  stack, principles, and implementation) teaching report.

## Documentation hygiene

`loop/` is authoritative; new design work is drafted under `docs/superpowers/specs/` and
`docs/superpowers/plans/`, not scattered elsewhere. Superseded material is removed once its value
is extracted, not left to rot next to the current docs. Full policy:
`loop/governance/DOCUMENTATION_HYGIENE.md`.
