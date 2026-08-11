# 股市锦囊 Loop Engineering 控制面

`loop/` 是本项目唯一的长期工程控制目录：它把目标、需求、验收、工作项、架构决定、风险、质量门、运行状态和验证证据外置为可审计文件。产品运行代码和用户数据不存放在这里。

本目录按 **Trigger → Goal → Work item → Verification → Review → Memory → Stop** 运行；文件数量不代表完成，只有追溯矩阵、门禁证据和命名终态一致时才能推进状态。

## 唯一权威源

| 信息 | 权威文件 | 说明 |
|---|---|---|
| Loop 契约 | `loop.json` | 触发器、目标、循环阶段、角色、记忆、终态和人工门禁 |
| 项目目标配置 | `config.json` | PySide6、微软雅黑、网络预算、命令、质量政策和路径 |
| 当前状态 | `state/current.json` | 唯一可写的当前运行状态 |
| 当前状态摘要 | `STATUS.md` | 由 `render_status.py` 从当前状态渲染，不可手工漂移 |
| 工作队列 | `planning/work-items.json` | 唯一工作项真源；`state/backlog.json` 只是投影 |
| 需求与验收 | `product/REQUIREMENTS.md`、`product/ACCEPTANCE_CRITERIA.md` | REQ/AC 权威定义 |
| 质量门 | `quality/quality-gates.json` | 唯一门禁机器定义 |
| 测试目录 | `quality/test-catalog.json` | TEST 标识和预期证据 |
| 追溯 | `quality/traceability.csv` | REQ → AC → WI → TEST → EVD |
| 证据索引 | `state/evidence-index.json` | EVD 元数据；原始小型证据在 `evidence/` |
| 风险 | `registers/risks.json` | 风险分值、缓解、负责人和状态 |
| 决定 | `decisions/` | ADR 权威记录 |
| 进度记忆 | `state/progress.jsonl` | 只追加的迭代事实 |
| 不可妥协原则（INVARIANTS） | `governance/CHARTER.md` | 唯一权威列表；本文件下方"不可妥协原则"与 `AGENTS.md`"不得违反"只做摘要式引用，不独立维护 |
| 文档卫生政策 | `governance/DOCUMENTATION_HYGIENE.md` | `loop/` / `../docs/` / 根 README 三者的分工、新设计文档去向、淘汰材料清理规则；本文件下方"文档卫生"只做摘要式引用，不独立维护 |

根目录不再保留第二套 `state.json`、`backlog.json`、`loop.yaml` 或重复质量配置。任何工具和协作者都必须读取上表路径。

`loop.json.status` 表示控制契约生命周期；`state/current.json.status` 表示当前运行生命周期。控制契约完成初始化后保持 `active`，产品迁移在没有发布证据前仍保持运行态 `active/verifying`，两者不得相互冒充。

## 首次阅读顺序

1. `AGENTS.md`
2. `LOOP_PROTOCOL.md`
3. `loop.json` 与 `config.json`
4. `state/current.json` 与 `STATUS.md`
5. 活动工作项及其 REQ/AC/TEST
6. 对应 ADR、架构规范、风险和质量门

## 目录地图

```text
loop/
  loop.json, config.json, LOOP_PROTOCOL.md, STATUS.md
  governance/     章程、范围、工程规则、完成定义、安全与依赖政策、文档卫生
  baseline/       当前仓库、模块、依赖、测试和差距基线
  product/        愿景、需求、验收、信息架构和 UI 设计系统
  architecture/   目标架构、计算模型、网络、并发、数据、持久化、打包
  decisions/      ADR
  planning/       路线图、里程碑、工作项、依赖图和回滚/发布计划
  quality/        测试、门禁、追溯、视觉、性能、可靠性和收敛指标
  state/          当前状态、队列投影、进度、检查点、指标和证据索引
  registers/      风险、假设、决定、变更、实验、缺陷和豁免
  evidence/       可重放命令输出、截图、包与发布证据
  schemas/        机器文件 schema
  templates/      工作项、ADR、测试、证据、风险、缺陷和发布模板
  scripts/, tests/标准库控制脚本及其测试
```

## 每轮流程

`OBSERVE → SPECIFY → DECIDE → PLAN → IMPLEMENT → VERIFY → REVIEW → LEARN → ADVANCE`

- 每轮只推进一个主要 WI。
- 实现者和验证者结论分离；高风险门保留人工批准。
- 失败不能通过降门槛、删测试、伪造行情或伪造证据收敛。
- 工作树出现无法解释的并行修改时停止写入，先稳定并统一真源。

## 必跑控制面门禁

```powershell
python loop/scripts/validate_loop.py
python loop/scripts/check_traceability.py
python loop/scripts/render_status.py --check
python loop/scripts/render_backlog.py --check
python loop/scripts/check_core_boundaries.py
python -m unittest discover -s loop/tests
```

当前产品基线：

```powershell
python -m unittest discover -s tests
python main.py --self-test
python -m compileall -q main.py scripts src
```

PySide6、pytest-qt、Ruff、pyright、覆盖率、Qt GUI 与打包门在工具链工作项完成前保持未启用/未验证，不能提前声称通过。

## 不可妥协原则（INVARIANTS）

唯一权威列表见 `governance/CHARTER.md`"不可妥协原则"一节（9 条，编号固定）；本节不重复独立维护，只给首次阅读者一个不需要跳转就能看到的摘要，措辞、条目增减与编号均以 CHARTER.md 为准：

- 生产 GUI 是 **PySide6 Qt Widgets**（ADR-0001 迁移由 WI-023 完成，Tkinter 生产层已删除）；核心领域保持无 Qt、无网络、无文件系统依赖。
- 所有应用可控制文字统一 **Microsoft YaHei（微软雅黑）**；原生 Windows 标题栏是系统控制的唯一例外。
- 科学计算必须可复现、可解释、防前视、显式处理缺失/极值，并区分工程正确性与策略有效性。
- 网络和长计算不得阻塞 GUI；请求有总 deadline、有限重试、取消、来源、完整度与降级状态。
- 没有可信数据时明确失败，绝不伪造行情、资金流、结论、收益、测试或完成状态；完成声明必须先有证据。
- 不构成投资建议；用户数据和未提交修改必须被保护。

## 文档卫生 / Documentation hygiene

唯一权威定义见 `governance/DOCUMENTATION_HYGIENE.md`；本节只给首次阅读者一个摘要，不独立维护规则：

- `loop/` 是唯一权威源；`planning/archive/`（`specs/`、`plans/`）只保存推动 `loop/` 演进的叙事性设计说明与实现计划，`../docs/` 只放教学材料——两者与 `loop/` 分歧时以 `loop/` 为准。
- 新设计工作写入 `loop/planning/archive/specs/`（设计说明）或 `loop/planning/archive/plans/`（实现计划），不要散落到别处；其中长期有价值的内容仍需落到 `loop/` 对应文件。
- 被 `loop/`（或新设计文档）取代且独有价值已提炼的旧文档要删除，不留着腐烂；删除前用 `git grep` 排查悬挂引用，并在提交信息/就近索引文档里留一个 git 历史定位点（如本仓库的基线提交 `61b3cde`），保证内容仍可通过 `git log --all --full-history` 找回。
