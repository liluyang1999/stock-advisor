# 版本与变更控制

本文件是分支模型、提交规范、应用版本号（两段式 大版本.小版本）和变更日志义务的唯一权威定义。`ENGINEERING_RULES.md`、`DEFINITION_OF_DONE.md`、`LOOP_PROTOCOL.md` 中涉及"如何提交/如何发版"的表述都以本文件为准，不得各自定义冲突规则。

## 分支模型

- `main` 是唯一长期分支，也是随时可展示当前真实状态（含未完成迁移）的主线；不存在第二条 `develop`/`release` 长期分支。
- 常规产品变更（触及 `src/`、`tests/`、`main.py`、`scripts/build_exe.py` 的行为性修改）使用短生命周期主题分支，经审查后合并回 `main`；分支随合并删除，不长期保留。
- **当前例外**：`loop/` 工程治理加固（本文件所属的 Plan 1-4 系列）按用户明确的整合请求直接在 `main` 上提交，不开分支——因为这些改动只触及 `loop/` 文档与机器文件、不触碰产品代码，且每个任务都以本文件同级的六项控制面门禁 + 449 产品测试 + `--self-test` 作为绿色标准，回滚成本等价于 `git revert` 单个提交。这是一次性授权的例外，不是分支模型的一般规则；一旦工作恢复触及产品代码（`planning/work-items.json` 中任一 `WI-0*` 从 `ready` 进入 `in_progress` 并开始编辑 `src/`），必须回到"主题分支 + 审查 + 合并"的默认流程。
- 任何合并到 `main` 的动作仍受 `SCOPE_AND_AUTHORITY.md`"永不自动扩张的权限"约束：推送、合并远程、发布仍需人工门禁；本文件只定义本地分支与提交结构，不授予这些权限。

## 提交信息

- 每个提交是一个原子、可独立回滚的变更；不得在一次提交里混合无关模块的修改（对应 `ENGINEERING_RULES.md`"变更只解决当前工作项"）。
- 提交信息第一行使用祈使语气（"add/fix/reconcile/quantify..."或对应中文动词开头，不用过去式或名词短语），格式为 `<type>: <summary>`；仓库当前实际在用的 `type` 前缀（按 `git log` 实证，非新发明）：
  - `loop:` —— `loop/` 控制面（治理、需求、架构、质量、工作项等）的新增或调整。
  - `docs:` —— 面向人类阅读的说明性文档变更（含 `docs/superpowers/plans/` 下的计划文件本身）。
  - `refactor:` —— 行为保持的产品代码结构调整（如 `14cfdd8` 的 src 子包重排)。
  - `chore:` —— 不改变行为的仓库杂务（如 `06879fc` 的 line-ending 归一化）。
  - 需要时可扩展 `fix:`（缺陷修复，必须先有复现测试）、`test:`（只新增/调整测试）；新增前缀须在本文件登记，不得静默发明未登记前缀。
- 摘要行不省略受影响的关键对象（"loop: fix X"优于"loop: update"）；正文（如需要）引用相关 `REQ-*`/`WI-*`/`ADR-*`/`EVD-*` id，便于 `git log` 反查追溯链路。
- 本文件与 `ENGINEERING_RULES.md`"每项实现必须关联 REQ/AC/WI"呼应：提交信息是这条关联规则在版本控制历史里的落地形式。

## 应用版本号（大版本.小版本）

- `src/version.py::__version__` 是应用对外版本号的唯一权威字段（ADR-0015 扫平 `src/` 包根后，原 `stock_advisor/__init__.py` 迁至此；无顶层 `src/__init__.py`），采用**两段式 `MAJOR.MINOR`（大版本.小版本）**，不使用三段式 PATCH 位（当前 `1.0`，见 `CHANGELOG.md`）。这是从 SemVer 裁剪出的两段方案：保留"破坏性=大版本、兼容变更=小版本"的判据，把原 PATCH 级改动并入小版本。
- **为什么真源是包而不是 `pyproject.toml`。** PEP 621 的 `[project].version` 是通行做法，前提是这个项目会被安装——运行期靠 `importlib.metadata.version()` 读回来。本项目没有 `[build-system]`，从不被 pip 安装，因此没有 dist-info，该调用在开发期和冻结后的 EXE 里都抛 `PackageNotFoundError`（实测）。运行期唯一取得到的版本号只能来自被 import 的模块，所以真源必须是模块。`pyproject.toml` 用 PEP 621 的 `dynamic = ["version"]` 声明"版本不静态写在这里"——这是标准里专为此准备的表达，而不是再抄一份字面量。
- **不允许出现第二处版本号字面量。** `tests/test_version_single_source.py` 机器强制：`pyproject.toml` 不得有静态 `[project].version`、`src/` 下 `__version__` 只能被赋值一次、发布清单与 SBOM 报告的版本必须等于运行期的值、`loop/CHANGELOG.md` 必须存在（且根目录不得再有第二份副本）且其发布标题同样是两段式。曾经的写法是 `pyproject.toml` 抄一份并在注释里写 "mirrors ..."，靠人手同步——那种约定不会报错，只会某天悄悄对不上。
- **MAJOR（大版本）**：破坏用户可观察的行为合同或持久化兼容性——例如移除/重命名一个现有功能页面、`AppConfig.schema_version`（`ADR-0009`）发生不兼容跃迁且旧配置文件无法被 `parse_config()` 隐式兼容解析、或 EXE 命令行/`--self-test` 合同发生不兼容变化。
- **MINOR（小版本）**：其余所有面向用户的发布——新增向后兼容的用户可见能力（新增一个 `REQ-*`、新增一个筛选预设、新增一个工作台模块），以及缺陷修复、用户可感知的性能/可观测性改进，均不破坏任何既有行为。三段式里原属 PATCH 的修复类改动，在两段式下并入小版本。
- 纯内部、用户不可观察的改动（行为保持的重构、不改变任何用户合同的内部优化）**不单独触发**应用版本变化，随下一个小版本一并发布，仅记录在 `registers/changes.jsonl`。
- 应用版本号与项目内多个独立的 `schema_version`（`config.schema.json`、`product/app-config.schema.json`、`ADR-0009` 的 `ui_state.json`、`loop/` 各机器文件自带的 `schema_version`）是不同的版本轴，互相独立演进；那些**数据格式版本仍沿用其自身既定格式（如三段式 `1.0.0`），不受本两段式约束**。一次 `AppConfig.schema_version` 的兼容性新增字段不必然触发应用小版本变化，但一次不兼容的 `schema_version` 跃迁必然要求应用大版本变化（因为它破坏了持久化兼容性，定义见上）。
- `loop/` 控制面自身的加固（本任务这类文档/机器文件变更）不改变 `src/`，因此不触发应用版本号变化；它们只记录在 `registers/changes.jsonl`（机器可读变更账本），不进入面向用户的 `CHANGELOG.md`。

## 变更日志义务

- 变更日志的唯一位置是 `CHANGELOG.md`（与本文件同在 `loop/` 下）。它原先位于仓库根目录，为把工程治理文档收拢到 `loop/` 而迁入，根目录不再保留副本——两份并存正是此前口径漂移的来源，`tests/test_version_single_source.py` 现同时强制"新位置存在"与"根目录无残留"。
- 任何改变 `src/` 用户可观察行为的已接受工作项，在标记 `accepted` 前必须在 `CHANGELOG.md` 追加一条对应条目（`[Unreleased]` 或对应版本号下），采用 Added/Changed/Fixed/Deprecated/Removed/Security 分节，并引用触发它的 `REQ-*`/`WI-*`/`ADR-*` id。
- 缺少 `CHANGELOG.md` 条目的行为性变更视为 `DEFINITION_OF_DONE.md`"设计与代码"一节的缺口，工作项状态最多停在 `verifying`。
- `CHANGELOG.md` 是面向人类的发布说明；`registers/changes.jsonl` 是机器可读、逐次追加、带 `evidence_ids` 的变更账本。两者记录同一类事实的不同粒度——一次"breaking": true 的 `changes.jsonl` 行必须对应 `CHANGELOG.md` 里同一变更的一条 Changed/Removed 记录且版本号符合上面的 MAJOR 规则；反之，`loop/` 内部文档加固可以只出现在 `changes.jsonl`（如需要）而不出现在面向用户的 `CHANGELOG.md`。

## 关联

`ENGINEERING_RULES.md`（提交与跳过规则的落地参照）、`DEFINITION_OF_DONE.md`（变更日志作为完成条件的一部分）、`ADR-0009`（schema_version 版本轴）、`registers/changes.jsonl`、`CHANGELOG.md`（本目录下）。
