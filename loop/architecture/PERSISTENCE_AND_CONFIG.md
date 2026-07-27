# 持久化与配置

## 现有合同

配置继续位于 `%APPDATA%\StockAdvisor\config.json`；测试用 `STOCK_ADVISOR_CONFIG` 指向临时路径。

## 目标规则

- 领域 `AppConfig` 和纯解析/序列化不依赖 Qt。
- 保存：同目录临时文件 → flush（必要时 fsync）→ `os.replace`。
- 读取损坏/缺失/不可读：回退默认并返回诊断，不崩溃。
- 写失败：保留内存状态和旧文件，UI 明确提示。
- 配置引入 `schema_version`，迁移函数逐版本、可重复、可回滚。
- 未知字段保留或按明确策略处理，不静默破坏未来兼容。

## AppConfig 基线 schema

`product/app-config.schema.json`（其结构由 `schemas/app-config.schema.json` 校验）是持久化 `AppConfig` 的基线 schema：`watchlist`（≤100，`{code,cost,shares}`）、`capital`（>0）、`level`（1..5）、`preset`（字符串，运行时对照 `PRESETS` 动态校验）、`alerts`（≤100，`{code,field∈{price,change_pct,score},op∈{>=,<=},threshold,enabled}`）与新增的 `schema_version`。字段与持久化形状分别取自 `domain/models.py::AppConfig`（+`WatchItem`/`AlertRule`）和 `services/store.py::config_to_dict()`。

**迁移与向后兼容（现状说明）**：截至本次治理，`services/store.py::config_to_dict()` 尚未写出 `schema_version` 字段——上表 schema 里的 `schema_version` 是 ADR-0009 将要落地的前瞻契约，不是当前已实现的行为。在该字段真正开始写出之前及之后，都必须满足：

1. `parse_config()` 对**缺失** `schema_version` 的既有文件（即今天所有已写出的 `config.json`）必须继续正常解析，不得因为"schema 要求该字段"而拒绝加载或清空其余合法字段——`parse_config()` 现有的"每个字段独立校验、非法值一律回退默认"式健壮解析已经满足这一半兼容性，缺失 `schema_version` 只需在实现时视为隐式的"无版本"形状（等价于当前形状），不额外报错。
2. 一旦 `store.py` 开始写出 `schema_version="1.0.0"`，写出的文件即符合本 schema；后续任何破坏性字段变更（改名、改类型、删字段）必须递增 `schema_version`、新增对应版本的迁移函数（逐版本、幂等、可重复应用），并且迁移必须可回滚到上一版本形状，不能只支持单向升级。
3. 未知/额外字段（例如更早或更晚版本引入、当前版本不识别的字段）遵循上面"目标规则"的既有承诺：保留或按明确策略处理，不静默丢弃，也不能仅因为字段未知就使整份配置失效。

## Qt 布局状态

窗口 geometry、dock state 是独立版本化 UI state；不得覆盖业务 JSON。ADR-0009 已决定采用独立 JSON 文件（而非 QSettings）承载该状态：复用与 `config.json` 相同的原子写入流程（同目录临时文件→flush→`os.replace`），拥有自己独立的 `schema_version`（与 `AppConfig.schema_version` 分属不同版本轴），具体取舍与拒绝理由见该 ADR。默认布局始终可恢复。

## 限制

- 自选和预警现有限制 100 条，迁移保持。
- 测试绝不写真实 APPDATA。
- 日志不泄露完整用户持仓。

