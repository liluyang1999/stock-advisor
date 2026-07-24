# 文档卫生 / Documentation Hygiene

本文件是 `loop/` 与 `docs/` 权威关系、新设计文档去向、以及淘汰文档清理规则的唯一权威定义。`loop/README.md`"文档卫生"一节只做摘要式引用，不重复独立维护。

## 权威关系

- `loop/` 是本仓库唯一的长期工程控制权威源（见 `loop/README.md`"唯一权威源"一节）：当前目标、需求、验收、架构决定、风险、质量门和验证证据均以 `loop/` 为准。
- `docs/` 不是第二套权威源。它保存推动 `loop/` 演进的叙事性规划材料——带日期的设计说明与实现计划（`docs/superpowers/specs/`、`docs/superpowers/plans/`），主要供智能体按任务逐步执行；`docs/README.md` 是其索引，列出当前仍权威的设计/计划文档。
- `docs/` 与 `loop/` 内容出现分歧时，以 `loop/` 为准；发现分歧应更新/提炼进 `loop/`，而不是在 `docs/` 里另开一份并行真源。

## 新设计工作去向

- 新的设计说明写入 `docs/superpowers/specs/<YYYY-MM-DD>-<slug>-design.md`；新的实现计划写入 `docs/superpowers/plans/<YYYY-MM-DD>-<slug>.md`，沿用仓库既有命名（日期前缀 + 短横线 slug）。
- 计划执行过程中产出的、需要长期保留的内容（不可妥协原则、架构决定、需求、验收标准、追溯关系、验证证据）必须落到 `loop/` 对应文件里；`docs/superpowers/plans/` 下的计划文件本身是执行记录，不作为这些内容的长期第二真源。

## 淘汰材料的清理

- 一份 `docs/superpowers/` 文档一旦被 `loop/`（或取代它的新设计文档）取代，且其独有价值已经提炼进 `loop/` 或已在 `src/` 中实现，就应当删除，不得无限期堆积在当前文档旁边"腐烂"。
- 删除前必须依次确认：
  1. 独有内容已提炼到 `loop/` 的对应文件，或已确认在 `src/` 中实现（不是靠记忆判断，而是实际读过、grep 过）。
  2. 用 `git grep` 排查仓库内（不含本文件与相关计划文件本身）是否还有指向该文件的悬挂引用，并修复真实引用。
  3. 在提交信息和/或就近的索引文档（如 `docs/README.md`）里留下一个 git 历史定位点（基线提交哈希或等效指引），使内容仍可通过 `git log --all --full-history -- <path>` 或 `git show <commit>:<path>` 找回。
- 删除使用正常的 `git rm` + 提交，不使用 `--no-verify` 或历史重写；因此"删除"不等于"丢失"——仍可从 git 历史完整恢复。
- 本政策的首次落地是 WS-9 文档整理（Plan 5）：15 个 pre-2026-07-11 Tkinter 时代的 `specs`/`plans` 文档在提炼后被删除，`docs/README.md` 记录了它们的检索方式（含初始基线提交 `61b3cde`）。今后任何被 `loop/` 或新设计文档取代的 `docs/` 材料都遵循同一流程。

## 关联

`docs/README.md`（面向人类的 `docs/` 索引，含当前保留文档清单与淘汰文档检索方式）、`governance/VERSION_AND_CHANGE_CONTROL.md`（提交信息与分支规则，含 `docs:`/`loop:` 提交前缀定义）、`ADR-0001`（`decisions/0001-adopt-pyside6.md`，取代 Tkinter 时代设计文档的技术前提）。
