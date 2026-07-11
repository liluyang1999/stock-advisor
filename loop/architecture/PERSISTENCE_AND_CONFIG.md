# 持久化与配置

## 现有合同

配置继续位于 `%APPDATA%\股市锦囊\config.json`；测试用 `STOCK_ADVISOR_CONFIG` 指向临时路径。

## 目标规则

- 领域 `AppConfig` 和纯解析/序列化不依赖 Qt。
- 保存：同目录临时文件 → flush（必要时 fsync）→ `os.replace`。
- 读取损坏/缺失/不可读：回退默认并返回诊断，不崩溃。
- 写失败：保留内存状态和旧文件，UI 明确提示。
- 配置引入 `schema_version`，迁移函数逐版本、可重复、可回滚。
- 未知字段保留或按明确策略处理，不静默破坏未来兼容。

## Qt 布局状态

窗口 geometry、dock state 可作为独立版本化 UI state；不得覆盖业务 JSON。可使用 QSettings 或独立文件，但必须另立 ADR、检查 status/sync 和原子性。默认布局始终可恢复。

## 限制

- 自选和预警现有限制 100 条，迁移保持。
- 测试绝不写真实 APPDATA。
- 日志不泄露完整用户持仓。

