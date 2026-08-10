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

Dated `2026-07-11` or later. These 7 files are the only docs under `docs/superpowers/` still
considered current; everything older there is legacy (see below).

| Doc | One-line description |
|---|---|
| `docs/superpowers/specs/2026-07-11-loop-hardening-and-tooling-design.md` | Design spec for hardening the `loop/` control plane and landing a modern dev toolchain, ahead of the Tkinter→PySide6 migration. |
| `docs/superpowers/plans/2026-07-11-01-foundation-hardening.md` | Plan 1/6: make `loop/`'s own validators self-check invariants they previously only asserted in prose, and close 13 evidenced control-plane defects. |
| `docs/superpowers/plans/2026-07-12-02-src-package-restructure.md` | Plan 2/6 (WS-R): behavior-preserving reorganization of `src/stock_advisor/` into `domain/`, `data/`, `services/`, `ui/` subpackages. |
| `docs/superpowers/plans/2026-07-12-03-plans-requirements-testgoals.md` | Plan 3/6 (WS-3+WS-4+WS-6): measurable test expected-goals, completed requirements (missing NFRs, UI tokens, REQ↔AC linkage), and richer per-work-item planning. |
| `docs/superpowers/plans/2026-07-13-04-architecture-governance.md` | Plan 4/6 (WS-5+WS-7): quantify the architecture/computation specs, bring every ADR to the project template, add missing ADRs, and lay the governance floor (version control, waivers, SOURCES verification, glossary, invariants, distribution security). |
| `docs/superpowers/plans/2026-07-13-05-doc-reconciliation.md` | Plan 5/6 (WS-9): extract remaining unique value from the legacy pre-2026-07-11 docs into `loop/`, add this index and the doc-hygiene policy, then delete the legacy docs. |
| `docs/superpowers/plans/2026-07-13-06-dev-toolchain-and-ci.md` | Plan 6/6 (WS-8): the unified `pyproject.toml` (ruff/pyright/pytest/coverage config + pinned dev group), local gate runner, pre-commit, and GitHub Actions CI; wires the `G-FORMAT`/`G-LINT`/`G-TYPE`/`G-COVERAGE` quality gates to real commands with a real owning work item. |

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
present from the initial baseline commit `61b3cde` ("chore: initial baseline snapshot") onward:

```bash
git ls-tree -r --name-only 61b3cde -- docs/superpowers      # list the legacy files as of the baseline
git show 61b3cde:docs/superpowers/specs/<name>.md           # recover one file's content at that commit
git log --all --full-history -- docs/superpowers/<specs-or-plans>/<name>.md   # full history of one file
```

## Also under `docs/` (unaffected by this reconciliation)

- `docs/ui-concepts/` — UI concept mockups (`r2/`, `r3/`: Tkinter-era rounds; `pyside6-r1/`,
  `pyside6-r2/`: PySide6 rounds).

## 教学材料已迁往 `knowledge/`

面向读者的**教学性**内容不再放在 `docs/` 下，统一收拢到仓库根目录的 **`knowledge/`**：

| 页面 | 内容 |
|---|---|
| `knowledge/index.html` | 知识库入口：阅读路径、技术栈速览、与其它文档的关系 |
| `knowledge/01-architecture.html` | 分层架构、纯领域内核、端口与适配器、信封模式 |
| `knowledge/02-domain-algorithms.html` | 技术指标、五档决策强度、仓位测算、回测与选股 |
| `knowledge/03-qt-ui.html` | PySide6 模型/视图、设计 token、空态与失败态、可访问性（含真实截图） |
| `knowledge/04-concurrency.html` | 线程边界、世代守卫、协作取消与总 deadline |
| `knowledge/05-data-quality.html` | 多源回退、零伪造、分页完整度、Decimal/int/float 三分法 |
| `knowledge/06-engineering.html` | TDD、八道质量门禁、loop 控制平面、CI 的坑、打包与发布 |
| `knowledge/07-technical-stack-report.html` | 原 `docs/stock_advisor_technical_stack_report.html`，迁入后保留为通读长文 |

`docs/` 自此只留**过程性记录**（设计规格、实施计划、界面概念稿），不再承载教学材料。

## Documentation hygiene

`loop/` is authoritative; new design work is drafted under `docs/superpowers/specs/` and
`docs/superpowers/plans/`, not scattered elsewhere. Superseded material is removed once its value
is extracted, not left to rot next to the current docs. Full policy:
`loop/governance/DOCUMENTATION_HYGIENE.md`.
