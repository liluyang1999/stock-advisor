# 设计：Loop 控制面加固 + 现代工具链落地（迁移前）

- **日期**：2026-07-11
- **状态**：current（本文件为当前权威设计；不属于 WS-9 待清理的历史文档）
- **主题**：在不改动产品业务逻辑的前提下，把 `loop/` 工程控制面与开发工具链打磨到现代软件工程最佳状态，为后续 Tkinter→PySide6 迁移（OBJ-001）铺好可审计的地基。
- **范围边界**：只改 `loop/`、`docs/`、根级开发工具配置（`pyproject.toml`、`.pre-commit-config.yaml`、`.github/workflows/`、门禁运行器脚本）。**不改 `src/stock_advisor/` 的算法/行为**，现有 449 个测试保持全绿。

---

## 1. 背景与现状

股市锦囊是一个 Windows 桌面 A 股分析工具，当前实现为 Python 标准库 + Tkinter，打包为单文件 EXE，定位为"可解释的辅助判断工具，不构成投资建议"。

`loop/` 是一套已相当成熟的"loop engineering"工程控制面（Trigger→Goal→Work item→Verification→Review→Memory→Stop；单轮 OBSERVE→SPECIFY→DECIDE→PLAN→IMPLEMENT→VERIFY→REVIEW→LEARN→ADVANCE）。当前状态：

- 阶段 `foundation_ready`；目标 `OBJ-001` = 在保留纯领域核心与现有功能/交付合同前提下迁移到 PySide6，并把计算/网络/并发/字体/测试/打包/发布提升到可审计现代标准。
- 133 个 loop 文件、20 schema、追溯 30/30；产品测试 449/449、loop 工具测试 13/13；六个控制脚本实机验证退出 0。
- 仓库尚无任何 git commit（248 文件 staged）；产品迁移代码**尚未开始**。

一次跨七大集群的并行审计（治理/产品/架构/规划/质量/机器层/基线与旧文档）确认：框架整体高水准，但存在一批可实证的客观缺陷，以及一批"断言于文档却未被机器强制"的一致性缺口。本设计据此收敛为一个**迁移前的加固计划**。

## 2. 目标（本轮）

1. 修复全部已实证缺陷（见 §5）。
2. **把纪律变成机器可执行**：强化校验脚本与 schema，使同类缺陷未来自动被门禁抓住。
3. 把阶段性计划、工程准则、测试预期目标补齐到可度量、可追溯、best-practice 的状态。
4. 落地标准现代 Python 工具链（ruff + pyright + pytest + coverage + pre-commit）与 CI，接通已定义但空缺的质量门。
5. 归并新旧文档，确立 `loop/` 为单一真源。

**非目标**：任何产品业务逻辑/行为变更；产品源码迁移；触发依赖/许可/发布等人工门所约束的不可逆动作。

## 3. 护栏与不变量（本轮绝不改变）

1. **不动产品业务逻辑**：`src/stock_advisor/*.py` 算法与行为零改动；449 测试全绿。
2. **写边界**：仅 `loop/`、`docs/`、根级开发工具配置。不写 `build/`、`dist/`、`%APPDATA%`。
3. **运行时依赖边界的显式演进**：当前"运行期零第三方"是 Tk 基线；按 ADR-0001 演进为"运行时 = 标准库 + PySide6（已批准）"。ruff/pyright/pytest/coverage 等**仅 dev/CI 用，绝不进 EXE**。该措辞同步进 `AGENTS.md`/`DEPENDENCY_POLICY`，消除"既称零依赖又用 PySide6"的表述矛盾。
4. **工具链以"棘轮"方式接入**：在**当前代码即通过**的基线上启用（pyright 从 basic 起步、ruff 规则集/`per-file-ignores` 校准到现状通过、coverage 门阈值先设为当前实测基线）；对新增/改动代码强制全规则；收紧（含 `src/` 一次性格式规范化、pyright strict、coverage 提标）排期为独立 WI，**本轮不因此改动 `src/`**。
5. **删除只在"抽取 + 基线提交"之后**：旧文档先入 git 历史再删，零信息损失。

## 4. 已确认的关键决策

| 决策 | 选择 |
|---|---|
| 改造范围 | 控制面加固（§6 WS-1..7、WS-9）＋ 落地现代开发工具链（WS-8） |
| 静态类型检查 | **pyright**（非 mypy）；dev-only，pip 管理；可选 `basedpyright` 求更强可复现 |
| 工具链构成 | ruff（格式+lint）+ pyright + pytest/pytest-qt + coverage + pre-commit |
| 工具配置位置 | 统一进 `pyproject.toml` 的 `[tool.*]`；例外：`.pre-commit-config.yaml`、`.github/workflows/ci.yml`；不建 `pyrightconfig.json`（避免覆盖 `[tool.pyright]`） |
| pytest 深度 | 只作运行器跑现有 449 unittest（不改写）；新增 Qt/性质/黄金测试用 pytest 风格 |
| CI 落地 | 本地门禁运行器脚本 + GitHub Actions workflow（Windows + Python 3.12/3.14 矩阵） |
| 旧文档处置 | 抽取仍有价值内容 → 汇总成新文档 → 删除旧文档（先基线提交入历史） |
| 市场时区 | `config.json` 显式 `market_timezone = Asia/Shanghai`，与本地显示/日志时区分离 |
| pyright↔"无 Node"冲突 | 记为 dev-only 明确豁免：约束本意针对产品运行时/交付物；写入 dev-toolchain ADR |
| 初始提交 | 先做基线提交（含旧文档）作安全网，再分逻辑提交做加固与清理 |

## 5. 已实证缺陷清单（均经一手核对）

| # | 缺陷 | 证据 | 归属 WS |
|---|---|---|---|
| D1 | REQ-024（P0 防伪造）无 WI 认领 | `traceability.csv:25` 记 WI-008;WI-020，但 `work-items.json` 中二者 `requirements[]` 均无 REQ-024 | WS-2 |
| D2 | EXP-003 主键重复 | `experiments.jsonl` 第 3、4 行两条不同实验同 ID | WS-2 |
| D3 | AC 未进追溯表 | `ACCEPTANCE_CRITERIA.md:16` 称映射见 `traceability.csv`，但该表仅按 REQ 索引、无 AC 列 | WS-2/WS-1 |
| D4 | 时区错配 | `config.json:8` = `Asia/Tokyo`，A 股应为 `Asia/Shanghai`（影响交易日边界/盘中 stale/t 日防前视） | WS-2 |
| D5 | 必需发布门禁可静默跳过 | `G-FORMAT/LINT/TYPE/SECURITY` 标 `required_for_release` 却 `commands:[]`、无 owning WI、无不变式 | WS-1/WS-8 |
| D6 | schema 普遍不封闭 | 21 schema 根部 `additionalProperties:true`（25 处）；`schema_version` 未 const/pattern 锁定 | WS-1 |
| D7 | RECOVER 悬空 | `LOOP_PROTOCOL.md §3` 状态图有 RECOVER，无定义/出边；README 九阶段流程亦无 | WS-2 |
| D8 | HG-ARCH 状态矛盾 | ADR-0001 称"已批准" vs `SCOPE_AND_AUTHORITY` 列为未决门 | WS-2 |
| D9 | REQ↔WI 双向不一致被漏过 | `check_traceability` 只验 REQ 覆盖、不验边一致，故多处 WI 不一致仍报 30/30 | WS-1 |
| D10 | `state.risk_ids` 未校验 | 不在 `state.schema.json`、未与 `registers/risks.json` 交叉校验 | WS-1 |
| D11 | `REQUIRED_FILES` 不全 | 漏 `test-catalog.json`/`dependency-graph.json`，缺文件抛裸 traceback | WS-1 |
| D12 | 证据小瑕 | `cwd` 拼成 `stock-adviser`；EVD-LOOP-001/002 被 003 取代未标 `superseded_by` | WS-2 |
| D13 | MS-02→MS-01 依赖边缺失 | `milestones.json` MS-02 `depends_on` 未含 MS-01，而 WI-009∈MS-02 依赖 WI-003∈MS-01 | WS-2/WS-6 |

## 6. 工作流分解

> 每条改动遵循 TDD：强化后的校验/新门即"先失败的测试"，数据/文档修复使其转绿。每改一处机器文件即跑 `validate_loop` + `check_traceability` 保持一致。

### WS-0 基线安全网
- **目的**：为后续删改建立可恢复点。
- **改动**：对当前工作树做**首个 git commit**（含全部旧文档）；随后加固/清理按 WS 分逻辑提交。
- **验证**：`git log` 存在初始提交；工作树干净可回溯。

### WS-1 校验与 schema 加固（最高杠杆）
- **`check_traceability.py`**：新增 (a) REQ↔WI **边一致**（`work-items.json.requirements[]` 与 `traceability.csv.work_item_ids` 双向一致）；(b) AC 覆盖（每个 AC 被 ≥1 WI/TEST 追踪）；(c) `work_item.tests ⊆ 其 REQ 的 test_ids`。
- **`validate_loop.py`**：新增 (a) 寄存器 ID 去重（risks/assumptions/experiments/changes/decisions）；(b) `state.risk_ids` ↔ `registers/risks.json` 交叉校验；(c) `REQUIRED_FILES` 补 `test-catalog.json`/`dependency-graph.json` 且缺文件干净报错；(d) 门禁不变式 `required_for_release ⇒ enabled ∧ (commands≠[] ∨ evidence_type=human_gate)`。
- **schemas**：封闭记录根部 `additionalProperties:false`；`schema_version` 用 `const`/`pattern` 锁定；为 5 个 JSONL 寄存器建逐行 schema 并接入 `validate`；新增 schema 元校验测试（每个 `schemas/*.json` 可加载、结构正确、被引用或标记通用）。
- **测试**：先在 `loop/tests/test_loop_tooling.py` 加会失败的用例，再改脚本。
- **验证**：新用例先红后绿；六脚本全绿。

### WS-2 修复已实证缺陷
- 逐条修复 D1–D4、D7、D8、D12、D13：REQ-024 并入相关 WI 的 `requirements[]` 并与追溯表对齐；EXP-003 第二条改 EXP-004（同步 `MIGRATION_PLAN`/ADR-0003 引用）；`traceability.csv` 增 AC 列/行并修正 `ACCEPTANCE_CRITERIA.md:16`；`config.json` 引入 `market_timezone=Asia/Shanghai` 与显示/日志 tz 分离；补 RECOVER 定义与出入边（或从图移除并说明）；统一 HG-ARCH 状态；修证据 `cwd` 与 `superseded_by`；补 MS-02→MS-01 依赖边。
- **验证**：WS-1 强化后的校验器全绿即证明缺陷闭合。

### WS-3 测试预期目标可度量
- **`test-catalog.json`**：每条补 `expected_goal`/断言、`evidence_level`(V0–V5)、`owning_work_item`、`expected_artifact`、数值容差引用；放宽其 schema 容纳新字段。
- **覆盖率**：接入 `coverage`（`coverage run -m pytest` 或 `pytest --cov`），新增 `G-COVERAGE` 门、指派 owning WI；阈值先设当前实测基线，目标 90/85·核心 95/90 排期收紧。
- **`performance-budgets.json`/`reliability-targets.json`**：每项补 `method`/`scenario`/`harness`/`owning_test`；REL-009 补数值 deadline。
- **`tk-contract-mapping.csv`**：定 schema（`disposition ∈ {pure_preserved,qt_replaced,approved_retired}`，`qt_replaced` 需 `replacement_test_id`）并断言 count=187（逐行枚举留给 WI-002）。
- **验证**：`test-catalog` 通过新 schema；门禁与追溯全绿。

### WS-4 需求与验收补强
- 拆非原子 REQ（004/008/023/025）为原子 REQ，保持 ID 稳定并登记变更。
- 补一级 NFR 的 REQ+AC：性能预算、常驻免责声明、导出注入安全、对比度（≥4.5:1/3:1）、字体缺失回退。
- 建 REQ↔AC 直接连接（REQ 增 `acceptance` 列或 REQ×AC 矩阵）。
- UI：产出机器可读 `tokens.json`（供 WI-005），补核心颜色 hex（A 股红/绿/琥珀）与状态 token（hover/pressed/disabled/selected-row/gridline/focus-ring）；AC-005 字号阈值对齐 10.5pt。
- UX 七态（空/加载/部分/错误/降级/停止/全失败）逐页规格化（文案 + 交互）。
- **验证**：新增 REQ/AC 全部进追溯并被 WI/TEST 覆盖（WS-1 校验器强制）。

### WS-5 架构规格与 ADR 合规
- 量化 `COMPUTATION_SPECIFICATION`：`history_bonus`/`available_indicator_bonus`/`high_atr_penalty` 等给出数值，补 MACD(如 12/26/9)、Bollinger(周期/σ)、ATR 窗口参数。
- `DATA_QUALITY` 的 stale TTL 数值进 `config.json`。
- 定义产品 `AppConfig` 基线 schema + `schema_version`。
- `OBSERVABILITY`：明确日志 sink/位置/轮转/格式 + `error_class` 分类法。
- 6 个 ADR 补齐模板（关联 REQ/AC/WI/RISK/EVD、背景、≥2 备选、后果、回滚、revisit 触发）；HG-ARCH 状态与 WS-2 一致。
- 新增 ADR：**dev-toolchain**（ruff/pyright/pytest，含 pyright↔"无 Node" dev-only 豁免）、ADR-0007（config 版本化 & Qt 布局持久化）、测试框架 unittest→pytest、日志/可观测、市场时区/交易日历。
- **验证**：ADR 模板合规可由一个轻量检查断言（可选纳入 WS-1）。

### WS-6 规划补强
- 每个 WI 加尺寸/工作量估计（T-shirt）→ 可算关键路径；补逐 WI DoD/scope-in-out 与回滚锚点。
- 人工门禁接线：`work-items.json`/`quality-gates.json` 增 `human_gate` 字段，绑 HG-ARCH↔WI-001、HG-DEPS↔WI-003、HG-PACKAGING↔WI-024。
- 拆过大 WI：WI-011（拆出 K 线 widget）、WI-018（拆出导出安全）、WI-009（spike 与实现分离）。
- `ROADMAP.md` 每个里程碑补退出标准（现仅 MS-00 有）。
- 新增登记工具链落地的 WI（ruff/pyright/pytest/coverage/pre-commit/CI 各有 owning WI 与门启用）。
- **验证**：依赖图仍无环且与 `depends_on` 一致；里程碑双向一致。

### WS-7 治理与常规工程底线
- 新增 `governance/VERSION_AND_CHANGE_CONTROL.md`：分支模型、原子祈使式提交信息、应用 SemVer、changelog 义务；新增根 `CHANGELOG.md`。
- 统一"跳过测试"→ `registers/waivers.jsonl`（owner+expiry），使 `ENGINEERING_RULES` 与 `DEFINITION_OF_DONE` 一致。
- 落地实现者/验证者独立机制（新上下文子代理复跑 ≥ 必需门，不看实现者自述）。
- 核验 `SOURCES.md` 引用（疑似未来日期的 arXiv/URL）→ 核验并记录，或降级为"启发而非引用"。
- `GLOSSARY.md` 补 ID 分类法（REQ/AC/WI/TEST/EVD/ADR/RISK/HG/G、V0–V5、终态、角色），统一"Loop"两处不一致定义。
- EXE 代码签名/SmartScreen provenance 与 Qt LGPL NOTICE/归属计划（进 `SECURITY_THREAT_MODEL`/`PACKAGING_AND_DEPLOYMENT` + ADR 或明确 deferral）。
- 单一 `INVARIANTS` 权威列表，消除四处不一致重述。

### WS-8 开发工具链落地（dev-only 依赖）
- `pyproject.toml`：项目元数据 + dev 依赖组（ruff/pyright/pytest/pytest-qt/coverage）+ `[tool.ruff]`/`[tool.pyright]`/`[tool.pytest.ini_options]`/`[tool.coverage.*]`。**运行时仍不引入这些**。
- ruff：格式 + lint 配置，棘轮校准到现状通过；填 `G-FORMAT`/`G-LINT` 命令。
- pyright：basic 起步、当前树通过；填 `G-TYPE` 命令；收紧排期为 WI。
- pytest/pytest-qt：作运行器跑现有 449 unittest（不改写）；更新命令；`config.json.test_runner` 改为"pytest（兼容 unittest）"。
- coverage：配置 + `G-COVERAGE`（阈值先设基线）。
- `.pre-commit-config.yaml`：ruff + `validate_loop` + `render_* --check` + `check_traceability`。
- **门禁运行器**：`loop/scripts/run_gates.py`（或根级脚本）串起 G-LOOP + G-CORE + 新门，本地/任意 CI 可调；`.github/workflows/ci.yml`（`windows-latest` + Python 3.12/3.14 矩阵）。
- 更新 `DEPENDENCY_POLICY`（记录已批准 dev 依赖与 pyright/Node 豁免）、`AGENTS.md`（依赖边界演进）、`state/metrics.json.tooling`（ci/ruff/pyright/coverage=true，使其诚实）。
- **验证**：新门在当前树全绿；`run_gates` 一键全绿；CI workflow 语法有效。

### WS-9 新旧文档归并（抽取 → 汇总 → 删除）
- 逐一审阅 `docs/superpowers/` 15 文档，抽取仍有效有价值内容——重点 `specs/2026-06-22-market-screener-and-ui-design.md` 的**六预设参数表 + 东方财富 f2–f25/`fs`/920xxx 字段合同** → 汇入 `loop/architecture/DATA_FLOW.md`/`DATA_QUALITY.md`；逐项确认 `plans/2026-07-10-ui-overhaul-p4-functional-gaps.md` 的功能修复已在 `src/` 落实，未落实者抽为 WI。
- 汇总成一份"产品能力与历史决策"归并文档 + `docs/README.md` 索引（映射旧→新/`loop/` 后继）。
- 写 ADR 记录旧 Tk UI-overhaul 方案被 ADR-0001 取代。
- **删除**旧的 `docs/superpowers/plans/*` 与 `specs/*`（已在 WS-0 入历史）；**保留本设计规格**与 `docs/ui-concepts/` 图。
- 新增 `governance` 归档/文档卫生政策（`loop/` 为 SSOT）。
- **验证**：删除前把每文件抽取结论列给用户过目（可选门）；删除后无悬挂引用（grep 校验）。

## 7. 执行顺序与验证策略

- **顺序**：WS-0 → WS-1 → WS-2 →（WS-3、WS-4、WS-5、WS-6、WS-7 内容补强，彼此可穿插，每步即时校验）→ WS-8 → WS-9。
- **分支**：基线提交落在 `main`（仓库首个提交）；WS-1 起的加固实现走独立特性分支/worktree。
- **收尾全绿门禁**：`validate_loop`、`check_traceability`（含新边一致）、`render_* --check`、`check_core_boundaries`、`loop/tests`、根 `pytest`(449)、`ruff`、`pyright`、`coverage`、`main.py --self-test`、`run_gates` 一键。
- **提交**：按 WS 分逻辑提交，祈使式信息说明"为什么"；提交信息尾行附 Co-Authored-By。

## 8. 交付物

1. 强化后的 `loop/` 控制面（校验器/schema/追溯/门禁/计划/准则/测试目标全部达标且机器自检）。
2. 一套可跑的现代 Python 工具链（ruff + pyright + pytest + coverage + pre-commit）+ 本地门禁运行器 + CI workflow。
3. 一份归并后的"产品能力与历史决策"文档 + `docs` 索引；旧文档清理完毕。
4. 本设计规格与配套 ADR/变更登记。
5. 产品迁移代码不在本轮交付，已登记为受门禁约束的 WIs。

## 9. 风险与回滚

- **R1 工具链在当前代码报错逼迫改产品**：以棘轮基线接入（当前树即通过），杜绝本轮改 `src/`；收紧排期为 WI。
- **R2 强化校验器一次性暴露大量不一致**：按 D1–D13 逐条闭合，TDD 红→绿；必要时用 `waivers.jsonl`（带 expiry）临时挂账并登记，不降门槛。
- **R3 删除旧文档丢信息**：WS-0 基线提交 + 抽取先行 + 删前清单过目；git 历史可完全恢复。
- **R4 pyright/Node 与"无 Node"约束**：记为 dev-only 豁免 ADR；不影响 EXE；可切 basedpyright。
- **回滚**：任一 WS 的提交可独立 revert；基线提交为总恢复点。

## 10. 附：标准 Python 工程工具链约定（本项目据此确立）

- **格式 + lint**：ruff（`ruff format` + `ruff check`），配置于 `[tool.ruff]`。
- **类型检查**：pyright（dev-only，pip 管理），配置于 `[tool.pyright]`；不建 `pyrightconfig.json`。
- **测试**：pytest / pytest-qt，配置于 `[tool.pytest.ini_options]`；兼容既有 unittest 用例。
- **覆盖率**：coverage，配置于 `[tool.coverage.*]`。
- **git 钩子**：pre-commit，独立 `.pre-commit-config.yaml`（不读 pyproject）。
- **CI**：GitHub Actions（`.github/workflows/ci.yml`）+ 本地 `run_gates` 脚本，二者跑同一组门禁命令。
- **统一原则**：除 pre-commit 与 CI 两处必须独立成文件外，工具配置一律集中在 `pyproject.toml`。
