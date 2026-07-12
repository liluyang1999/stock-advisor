# ADR-0008：开发工具链——ruff + pyright + pytest/pytest-qt + coverage + pre-commit（仅开发期）

- 状态：accepted
- 日期：2026-07-13

## 背景

REQ-028 要求格式、lint、类型、测试、覆盖率、GUI、性能、构建和 EXE 自检门禁可复现。`quality/quality-gates.json` 已经声明 `G-FORMAT`（`ruff format --check .`）、`G-LINT`（`ruff check .`）、`G-TYPE`（当前命令字面量是 `mypy --strict src`）、`G-COVERAGE`（`coverage run -m pytest` + `coverage report --fail-under=85`）四个门禁，但全部 `enabled:false`，`owning_work_item` 暂记为 `WI-000` 占位，`note` 明确写着"真正 owner 是 WS-8（Plan 5）尚未创建的开发工具链工作项"。也就是说，四个禁用门禁的具体命令字符串目前只是历史占位符，尚无一份 ADR 对"类型检查器到底用什么、测试运行器到底批准迁移到哪里"做出正式决策——本 ADR 补上这个决策空白，在 WS-8 真正把这些门禁 `enabled` 之前，先把目标工具链钉死成一条可审查、可引用的记录，而不是让 WS-8 落地时才第一次讨论选型。

`config.json.target_stack` 已经把 `test_runner` 记为 `"unittest initially; additional dev tools require approval"`，同时 `candidate_versions` 已经给 `pytest`（9.1.1）、`pytest-qt`（4.5.0）打了候选版本桩（`status: unverified_until_WI-003`）——即"需要 approval"的那个入口，本 ADR 与 ADR-0010（测试框架迁移细节）一起构成这份 approval。

## 决策

- 采用 **ruff** 同时承担格式化（替代 black/isort/autopep8）与 lint（替代 flake8 及其插件生态），对应 `quality-gates.json` 现有的 `G-FORMAT`/`G-LINT` 命令。
- 采用 **pyright** 作为类型检查器（不是 mypy）。
- 测试运行器批准迁移到 **pytest + pytest-qt**；迁移策略和"是否重写现有测试"由 ADR-0010 承接，本 ADR 只记录"选它"这一决策本身。
- 采用 **coverage.py** 驱动覆盖率门禁，对应 `G-COVERAGE` 已声明的命令。
- 采用 **pre-commit** 在提交前本地跑 ruff（format+lint）子集，作为 CI 门禁之前的早期反馈，不引入 CI 未覆盖的独立规则。
- 全部五个工具都是**仅开发期**（dev-only）依赖：绝不出现在 `build_exe.py` 打包收集的模块里，也绝不是最终 `股市锦囊.exe` 的运行时依赖。
- **pyright↔"无 Node"豁免**：pyright 底层实现依赖 Node.js 运行时，不同于纯 Python 的 ruff/pytest/coverage；项目对**产品运行时**的"无 Node"约束（EXE 不得依赖或打包 Node）继续适用且不受影响，因为 pyright 只以 dev 依赖身份运行在开发者机器/CI 上，从不进入 `build_exe.py` 收集的文件或最终 EXE。若需要更强的可复现性（避免首次运行时联网下载 Node 版 pyright 二进制），可改用 basedpyright（自带固定版本、无首次联网下载）；两者都遵守同一条"仅开发期、绝不进 EXE"豁免规则，具体选用哪一个是实现细节，不改变本决策。

## 替代方案

1. **继续裸 `unittest`、不引入任何格式化/lint/类型工具（现状，拒绝）**：零新增依赖，但 REQ-028 要求的 format/lint/type/coverage 门禁已经在 `quality-gates.json` 中声明却永远没有具体工具落地；四个禁用门禁会无限期停留在"没有实现路径"的状态。
2. **mypy 作为类型检查器（拒绝）**：`quality-gates.json` 当前 `G-TYPE` 命令字面量就是 `mypy --strict src`，是历史遗留占位符；mypy 是纯 Python 实现、无 Node 依赖，天然满足"无 Node"约束，表面上更简单。拒绝原因：项目标准工具链选型是 pyright；"无 Node"顾虑已经用更通用的"仅开发期依赖"规则解决，不需要为了规避一个开发期工具的 Node 依赖而放弃选型。
3. **black + isort + flake8 组合（拒绝）**：多工具意味着多份配置、多套版本锁定和潜在规则冲突（例如 isort 与 import-order 类 flake8 插件的先后顺序）；ruff 用单一二进制复现两者行为且显著更快，`quality-gates.json` 现有 `G-FORMAT`/`G-LINT` 命令已经指向 ruff 而非 black/flake8，本 ADR 只是把这一既成事实正式记录为决策。
4. **（采用）ruff（格式+lint）+ pyright（类型）+ pytest/pytest-qt（测试，见 ADR-0010）+ coverage（覆盖率）+ pre-commit（提交前早期反馈）**：见"决策"。

## 后果

正面：

- REQ-028 的 format/lint/type/test/coverage 五类门禁第一次有了明确、可引用的工具选型决策；WS-8 的开发工具链工作项落地时不需要重新讨论选型，只需要执行安装、锁定版本，并把 `quality-gates.json` 四个占位门禁的 `enabled` 翻转为 `true`。
- `pytest`/`pytest-qt` 已经在 `config.json.candidate_versions` 里有版本候选，本 ADR 与 ADR-0010 一起构成 `config.json` 里"additional dev tools require approval"这句话所等待的正式批准。

负面/成本：

- 本 ADR 只记录决策本身，不改变任何现有文件的执行状态：`quality-gates.json` 的 `G-TYPE` 命令字面量、`quality/QUALITY_GATES.md`、`README.md`、`baseline/dependency-baseline.json` 以及 `state/metrics.json.tooling.mypy` 里提到的 "mypy" 仍然原样保留，不会因为本 ADR accepted 而被同步改写为 pyright；这是刻意的范围控制（本次治理只新增决策记录，不改动这些既有文件），但意味着在 WS-8 开发工具链工作项把这些占位符实际替换为 pyright/pytest 之前，仓库里会持续存在"决策已 accepted、占位文本尚未跟上"的可见落差——WS-8 工作项的 definition_of_done 必须包含把这些占位字符串替换为本 ADR/ADR-0010 实际采用的工具名，作为已知的后续收尾项，不是被本 ADR 忽略的问题。
- pyright 需要 Node.js 运行时；开发者/CI 机器必须能够运行 Node（或改用自带 Node 的 basedpyright），这是本 ADR 显式接受的开发期依赖面，不影响产品 EXE。
- 五个工具都需要精确版本锁定和许可证审查（呼应 REQ-029 对开发依赖锁定与许可证的要求），具体锁定和审查是 WS-8 工作项的执行内容，不在本 ADR 范围。

## 回滚

若 pyright 被证明不适合本项目（例如 PySide6 stub 覆盖不足导致大量误报、或 Node 依赖在目标 CI 环境不可用且无法用 basedpyright 替代），回滚到 mypy 只需要更新 `quality-gates.json` 的 `G-TYPE` 命令字符串和相关类型检查配置，不影响 ruff/pytest/coverage/pre-commit 的选型，也不影响任何已经落地的产品类型标注（标注语法两者通用）。停止条件：若 WS-8 实际接入 pyright 后连续多次门禁运行出现工具自身崩溃或无法在目标 CI 环境稳定安装（而非代码本身的类型错误），必须停止把 `G-TYPE` 标记为 `required_for_release` 强制项，先回退到 mypy 或暂时保持 `G-TYPE` 禁用，不得为了"门禁能跑"而放宽类型检查严格度。

## 重访触发

- WS-8 开发工具链工作项创建并开始执行时，需要重新核对本 ADR 的候选版本和 pre-commit hook 清单是否仍然适用。
- 若 basedpyright 或未来的 pyright 官方发行版改变了"是否需要 Node"这一前提，需要重新评估"仅开发期依赖"这条豁免是否还需要专门记录。
- 若 pyright 严格模式在实际接入后对 PySide6 的类型 stub 产生大量无法消除的误报，需要重新评审是否退回 mypy 或调整严格度。

## 关联

REQ-028、REQ-029、ADR-0010、WI-000、EVD-LOOP-004。
