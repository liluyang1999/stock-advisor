# ADR-0010：测试框架迁移——unittest → pytest/pytest-qt 作为运行器

- 状态：accepted
- 日期：2026-07-13

## 背景

REQ-028 要求测试门禁可复现；`config.json.target_stack.test_runner` 现状字面量是 `"unittest initially; additional dev tools require approval"`——当前唯一被采纳的运行器是标准库 `unittest`（449 个产品测试与 `loop/tests` 全部用 `python -m unittest discover` 驱动，`config.json.commands.baseline_tests`/`commands.loop_tests` 均是如此），但同一份文件的 `candidate_versions` 已经给 `pytest`（9.1.1）与 `pytest-qt`（4.5.0）打了候选版本桩，`status` 标记为 `unverified_until_WI-003`。

PySide6 迁移（ADR-0001）和 Qt 并发边界（ADR-0003）落地后，测试矩阵会新增大量需要驱动真实 `QApplication`/`QWidget`/信号槽的用例（例如 WI-011 的 `QAbstractItemModelTester`、WI-019 的取消/迟到/竞态套件、WI-021 的可访问性检查）。标准库 `unittest` 没有官方的 Qt fixture 生态；`pytest-qt` 提供 `qtbot`、信号等待、异常捕获等专门支持 Qt 测试的 fixture，是这类测试的事实标准工具，仅靠 `unittest` 自建这些能力属于重复造轮子且缺乏社区验证。

## 决策

- 测试运行器迁移到 **pytest**（含 **pytest-qt** 插件承载 Qt/GUI 用例），作为项目统一的测试执行入口。
- 现有 449 个 `unittest.TestCase` 测试**不重写**：pytest 原生支持发现和运行 `unittest.TestCase` 子类，迁移只更换"用什么命令跑测试"，不要求把已经验证过的 449 个用例改写成 pytest 风格的函数式测试。
- 新增的 Qt/属性类/参数化测试（尤其是需要 `qtbot`，或与 `hypothesis` 等第三方 pytest 插件集成的用例）用 pytest 原生写法编写。
- `loop/tests`（本控制面自身的测试）保持 `unittest discover` 不变：`loop/` 脚本刻意保持标准库-only（`AGENTS.md` 与 ADR-0008 的开发工具链决策均要求 loop 脚本零第三方依赖），迁移到 pytest 只针对 `tests/`（产品测试）和未来的 Qt 测试，不涉及 `loop/tests`。
- 迁移生效前，`config.json.commands.baseline_tests` 仍是 `python -m unittest discover -s tests` 且继续可用（pytest 本身不要求删除 unittest 入口）；把 `commands.baseline_tests`/CI 入口实际切换成 pytest 调用，以及把 `target_stack.test_runner` 的描述性文字从"unittest initially"更新为迁移后状态，是具体迁移工作项的执行内容。本 ADR 只批准迁移方向和终态选型，不在本次治理中直接改写 `config.json` 或 `quality-gates.json` 的现行命令——那些改动需要伴随实际的 pytest 依赖锁定和一次完整测试重跑，属于 WS-8 或专门迁移工作项范围。

## 替代方案

1. **继续只用标准库 `unittest`，不引入 pytest（拒绝）**：零新增依赖，`loop/` 已经证明 unittest 完全够用；但 Qt 测试（`qtbot`、信号等待、offscreen 平台夹具）在 unittest 下需要自建等价能力，PySide6 迁移里多个工作项（WI-011/WI-019/WI-021 等）都需要这类夹具，自建的维护和正确性成本会持续叠加到每一个后续 Qt 测试工作项上。
2. **迁移到 pytest 但要求把全部 449 个 unittest 用例重写为 pytest 风格（拒绝）**：能获得更符合"pytest 原生风格"的一致性（例如用 fixture 替代 `setUp`），但这是与"保持行为不变"的迁移纪律相悖的大规模重写；449 个测试本身就是当前唯一的行为保持 oracle，重写测试代码会带来"测试的测试"验证负担。pytest 原生支持直接 collect `unittest.TestCase`，使得这种重写没有必要。
3. **只为新 Qt 测试引入 pytest-qt，运行器整体仍是 unittest（拒绝）**：pytest-qt 是 pytest 插件，不能独立于 pytest 运行，"只要 pytest-qt、不要 pytest"在技术上不成立。
4. **（采用）运行器整体迁移到 pytest（含 pytest-qt），保留现有 449 个 unittest.TestCase 不重写，`loop/tests` 继续用标准库 unittest discover**：见"决策"。

## 后果

正面：

- 449 个现有产品测试的通过状态直接延续（pytest 原生 collect `unittest.TestCase`），迁移不产生"重写测试导致行为保持证据链断裂"的风险。
- 后续所有 Qt/GUI 相关工作项（WI-011、WI-019、WI-021 等）获得 `pytest-qt` 现成的 `qtbot`/信号断言/offscreen 平台集成能力，不需要每个工作项各自实现。
- `loop/tests` 保持标准库-only，维持 `loop/` 控制面"零第三方依赖"的既有边界，与 ADR-0002 的纯核心边界精神一致。

负面/成本：

- 项目从"零第三方测试依赖"变为需要锁定并审查 pytest、pytest-qt 及其间接依赖的版本和许可证（呼应 REQ-029），这是本 ADR 显式接受的新增开发期依赖面。
- 迁移期间存在两处并行的测试入口描述（`config.json.commands.baseline_tests` 的字面命令与 `target_stack.test_runner` 的描述性文字），在本 ADR accepted 之后仍暂时保持 unittest 现状，直到实际迁移工作项把命令和文字都切换为 pytest 调用；这段"决策已批准、命令尚未切换"的间隔是刻意的执行顺序（先锁定版本、迁移生效并重跑全部测试确认零回归，再切换 `commands.baseline_tests`），不是遗漏。
- `pytest-qt` 的 offscreen/平台相关行为需要在目标 CI/开发环境验证（`QT_QPA_PLATFORM=offscreen`，`quality-gates.json` 的 `G-QT-GUI` 已经预留了这个环境变量），验证本身是 WI-019 等具体工作项的范围。

## 回滚

若 pytest/pytest-qt 迁移在具体执行中出现无法在合理时间内解决的 collect 失败或 Qt 夹具不稳定，回滚路径是保持 `commands.baseline_tests`/`commands.loop_tests` 都用 `unittest discover`（迁移前状态本就如此，回滚等于不切换命令），449 个 `unittest.TestCase` 本身不需要任何改动即可继续用 unittest 直接运行；已经用 pytest 原生写法编写的新 Qt 测试则需要评估是否用 `unittest.TestCase` 包装或暂缓该类测试，直到迁移问题解决。停止条件：若迁移后任何一次全量测试重跑无法达到与迁移前 449/449 通过完全一致的结果，禁止切换 `config.json.commands.baseline_tests` 到 pytest 调用，必须先定位差异原因。

## 重访触发

- WI-003 完成依赖 spike（`candidate_versions.status` 从 `unverified_until_WI-003` 解除）后，若实测 pytest/pytest-qt 版本与 PySide6 目标版本不兼容，需要重新评审版本选型。
- 实际迁移工作项执行时，若 pytest collect 449 个 unittest.TestCase 出现任何行为差异（而非纯粹的运行器切换），需要暂停迁移并重新评估"零重写"这一决策前提是否仍然成立。

## 关联

REQ-028、AC-007、ADR-0008、WI-000、EVD-LOOP-004。
