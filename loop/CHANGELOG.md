# Changelog

本文件记录"股市锦囊"**产品**（`src/stock_advisor/`、`main.py`、`build_exe.py` 构成的可运行程序）面向用户的变更，分节习惯采用 Added/Changed/Fixed/Deprecated/Removed/Security，版本号规则见 `governance/VERSION_AND_CHANGE_CONTROL.md`（应用两段式 大版本.小版本）。

`loop/` 控制面自身的变更记录在机器可读、逐次追加的 `registers/changes.jsonl`；本文件只记录**产品**对外行为变更——一次 `loop/` 文档或治理加固不必然对应一次产品版本号变化，除非它同时改变了用户可观察的行为或交付合同（规则见 `governance/VERSION_AND_CHANGE_CONTROL.md`"变更日志义务"）。

## [Unreleased]

### Changed

- 工程治理与架构规范加固（`docs/superpowers/plans/` Plan 1-4）：需求/验收/工作项追溯补全、ADR-0001..0012 达到项目模板、新增版本与变更控制规则、豁免（waiver）机制、`SOURCES.md` 引用核验、术语表 ID 分类法、`INVARIANTS` 唯一权威列表、分发安全（代码签名/Qt LGPL 归属）规划。仅触及 `loop/` 目录，不改变 `src/stock_advisor/` 任何已发布行为，因此不触发应用版本号变化；机器可读记录见 `registers/decisions.jsonl`、`registers/changes.jsonl` 与 `state/evidence-index.json`。

## [1.0] - 2026-07-11

### Added

- 首个可自检的桌面基线（Tkinter GUI，`src/stock_advisor/__init__.py::__version__ = "1.0"`）：个股分析（实时行情 + 历史日线 + 可解释多因子模型 + 五档决策强度）、全市场选股（多套策略预设）、自选/持仓与跨会话持久化、横向对比、K 线 hover、条件预警、个股资金流按需查询、可信度回测；`main.py --self-test` 作为可复现的发布前合同；`build_exe.py` 产出 PyInstaller onefile Windows EXE。

> 本条目是对既有基线的追溯记录：`__version__` 在本文件创建前已固定为 `"1.0"`（仓库初始快照提交 `0d2fdf7` 记为 `1.0.0`，随两段式方案改记为 `1.0`），此前没有正式维护的逐次变更历史，因此不重建 1.0 之前不存在的版本间 diff，只记录该基线本身包含的能力；完整、权威的当前能力描述见根目录 `README.md` 与 `product/REQUIREMENTS.md`。
