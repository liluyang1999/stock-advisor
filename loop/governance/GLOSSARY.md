# 术语

- **Measurement**：与决策档位无关的客观测量结果。
- **Decision**：按 L1–L5 策略将 Measurement 翻译为买/持/卖与仓位。
- **证据强度**：基于数据完整度和因子一致性的内部分数；未经校准不得称统计概率。
- **降级**：数据不足时明确降低能力并暴露状态，而非伪造结果。
- **工作项**：一个有范围、依赖、验收和证据合同的可交付单位。
- **门禁**：状态推进前必须通过的自动或人工检查。
- **证据**：可复现命令、退出码、报告、截图、哈希或签署记录。
- **Loop**：本项目对"Loop"只有一份调和后的定义（见下方"`Loop` 定义的调和"），不是两处各自表述、可能漂移的说法。
- **终态**：明确命名的停止结果，而非无限循环（完整列表见下方"终态"）。
- **Qt 主线程**：创建和更新 QWidget 的 GUI 线程。
- **迟到结果**：任务已取消、替换或页面销毁后返回的旧异步结果。

## `Loop` 定义的调和

`SOURCES.md` 引用的两份 Loop Engineering 外部资料使用了不同词汇描述"什么是一个 Loop"：一份用 trigger/goal/verification/stopping rule/memory 五要素描述"loop specification"的结构；另一份用 discovery/handoff/verification/persistence/scheduling 五个动作描述"loop"的运行过程。本目录此前在 `LOOP_PROTOCOL.md`、`README.md` 和本文件里分别引用了其中一份而不互相对照，产生了两处可能读出不同含义的"Loop"表述。以下是唯一权威定义，其余文件里的措辞都必须与之一致，不一致时以本条为准并修正措辞（而不是反过来）：

> **Loop** 是一个有界、可复用的工程活动单元，由 trigger（触发）、goal（目标）、verification（验证）、stop rule（停止规则）、memory（记忆）五个结构要素定义"它是什么"（即 loop specification），并通过 discovery（发现）、handoff（交接）、verification（验证）、persistence（持久化）、scheduling（再调度）五个动作描述"它如何运行"。两者共享同一个 verification 概念，不是相互竞争的两套定义，而是同一件事的"结构"与"过程"两个视角。

本项目把上述通用定义具体实例化为 `loop.json.cycle` 定义的九阶段状态机——`observe → specify → decide → plan → implement → verify → review → learn → advance`（完整机制见 `LOOP_PROTOCOL.md` §3）——以及 `LOOP_PROTOCOL.md` §2 的六要素表（在通用五要素之外新增了本项目自定义的 `authority`，因为发布/依赖许可/不可逆操作的人工门禁在本项目里是一等公民，不能隐含在别处）。`README.md` 开头的 "Trigger → Goal → Work item → Verification → Review → Memory → Stop" 是这份九阶段状态机的极简复述，不是第三套定义；如果它与 `LOOP_PROTOCOL.md` §2/§3 的正式表述不一致，以 `LOOP_PROTOCOL.md` 为准。

## ID 与状态分类法

本项目所有可追溯对象都通过一个带前缀的 ID 引用；下表是权威、完整的前缀表——出现在任何文件里的 ID 都应能在此对上号，新增前缀必须先在此登记。

| 前缀 | 含义 | 定义位置 | 生成/校验 |
|---|---|---|---|
| `REQ-NNN` | 需求 | `product/REQUIREMENTS.md` | `validate_loop.py`/`check_traceability.py` 从正文提取 |
| `AC-NNN` | 验收条件 | `product/ACCEPTANCE_CRITERIA.md` | 同上，且必须被至少一个 `WI-*` 覆盖 |
| `WI-NNN` | 工作项 | `planning/work-items.json`（唯一真源，`state/backlog.json` 只是投影） | `work-items.schema.json` |
| `TEST-<AREA>-NNN` | 测试目录条目 | `quality/test-catalog.json` | `test-catalog.schema.json`；`evidence_level` 字段取值即下方 V0-V5 |
| `EVD-<AREA>-NNN` | 证据记录 | `state/evidence-index.json` | `evidence.schema.json`；`record_version:"2.0.0"` 起需要 `implemented_by`/`verified_by` |
| `ADR-NNNN` | 架构决策记录 | `decisions/NNNN-*.md` + `registers/decisions.jsonl` | 两处状态必须一致（"ADR 三角"，`validate_loop.py` 强制） |
| `RISK-NNN` | 风险 | `registers/risks.json` | `risk.schema.json`；`score = probability × impact` 强制校验 |
| `HG-<NAME>` | 人工门禁 | `governance/SCOPE_AND_AUTHORITY.md`；机器列表见 `loop.json.human_gates` | 无自动校验，人工批准记录进相关证据/决策 |
| `G-<NAME>` | 质量门禁 | `quality/quality-gates.json` | `quality-gates.schema.json`；`required_for_release` ⇒ `enabled` 或有 `owning_work_item` |

以下前缀同样在用，未在本次任务范围内展开，但读者遇到时应能查到定义位置：`ASM-`（假设，`registers/assumptions.jsonl`）、`CHG-`（变更账本，`registers/changes.jsonl`）、`EXP-`（实验，`registers/experiments.jsonl`）、`WVR-`（豁免，`registers/waivers.jsonl`，见 `governance/ENGINEERING_RULES.md`"测试与证据"）、`DEF-`（缺陷，`registers/defects.json`）、`MS-NN`（里程碑，`planning/milestones.json`）、`OBJ-`（目标，`loop.json.goal.objective_id`）、`RUN-`（运行实例，`state/current.json.run_id`）。

### 验证阶梯 V0-V5

机器可读短形式（`loop.json.verification_ladder`，同一取值集合被 `test-catalog.schema.json.evidence_level` 复用）对应 `LOOP_PROTOCOL.md` §4 的完整定义：

| 短 ID | 等级 | 证据 | 可支撑的声明 |
|---|---|---|---|
| `V0_assumption` | V0 | 无证据/主观判断 | 只能记为假设 |
| `V1_static` | V1 | 静态检查、文件存在 | 结构已创建 |
| `V2_unit` | V2 | 单元测试、schema、类型/格式门禁 | 局部合同成立 |
| `V3_integration` | V3 | 集成、故障注入、Qt offscreen | 子系统协同成立 |
| `V4_system` | V4 | Windows 真机、打包 EXE、自检、性能/视觉矩阵 | 发布候选成立 |
| `V5_release` | V5 | 独立复核 + 人工发布门禁 + 可追溯产物 | 可发布/已接受 |

不得用低等级证据支持高等级声明（如用 Qt offscreen 测试证明 Windows 真机渲染无误）。

### 终态（Terminal states）

`loop.json.terminal_states`，完整语义见 `LOOP_PROTOCOL.md` §5：`success`（目标与证据全部满足）、`needs_human`（存在产品/许可/发布/不可逆决策）、`changes_requested`（验证失败但可继续修复）、`blocked_external`（外部阻塞且替代检查不足）、`no_safe_progress`（当前权限内无法继续且不能合理假设）、`cancelled`（用户或已批准计划取消）、`superseded`（目标被新决策替代）、`failed`（本轮异常终止且状态已安全持久化）。

### 角色（Roles）

`loop.json.roles`，与 `LOOP_PROTOCOL.md` §7 及"独立性的具体机制"一致：

- **implementer（实现者）**：在有界工作项范围内修改代码与测试。
- **verifier（验证者）**：独立核查需求、差异、测试与失败模式；机制细节（fresh context / 独立 subagent、必须复跑的最低门禁集合）见 `LOOP_PROTOCOL.md` §7。
- **integrator（集成者）**：调和证据并推进状态。
- **human（人类）**：批准架构、依赖/许可证、发布与不可逆门禁（即 `HG-*`）。
