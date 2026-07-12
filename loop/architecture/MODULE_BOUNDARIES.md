# 模块边界

纯核心的机器权威清单为 `core-module-manifest.json`；Markdown 只解释原则，不能另建一份容易漂移的模块列表。

`src/stock_advisor/` 按层拆成 4 个子包（ADR-0007）：`domain/`（12，纯核心，机器清单保护对象）、`data/`、`services/`、`ui/`。`core-module-manifest.json` 的 `forbidden_internal_modules` 是这非纯三者加 `qt_app`（PySide6 迁移后的界面子包）——`domain/` 模块的相对导入一旦跨出本包，检查器只看目标路径的第一级分量，因此禁止名单按子包而非逐模块列举。完整模块到子包的映射见 `module-map.json`。

## 允许依赖

```text
qt_app -> application/workflow -> domain
qt_app -> infrastructure ports/adapters
infrastructure -> domain models
domain -> Python 标准库 only
```

## 禁止依赖

- domain → PySide6/tkinter/urllib/file dialog。
- data_provider → QWidget/session state。
- table model → provider 网络调用。
- worker → QWidget 方法。
- store parser → QSettings/Qt 类型。
- chart geometry → QPainter。

## 端口

- `MarketDataProvider`：quote/history/market_snapshot/fund_flow。
- `ConfigStore`：load/save，返回结构化错误而非弹窗。
- `Clock`：当前时间/交易日判断，测试可替换。
- `TaskScheduler`：提交、取消、进度和完成信号。
- `NotificationSink`：UI 横幅/声音；领域预警只返回事件。

## 跨边界数据

- 使用 frozen dataclass、tuple、Mapping 或明确 DTO。
- 不跨线程传递 QWidget、QPixmap、QPainter 或可变共享容器。
- 仅有 `@dataclass(frozen=True)` 不代表深度不可变；内部 list/dict 必须在边界冻结或防御性复制。
- 大历史数据可只读共享或复制摘要；所有权必须记录。

## 架构检查

- 依据机器清单静态扫描核心模块，不得出现 `PySide6`、`tkinter`、`urllib`、文件系统或进程 API。
- 测试中 provider 使用 FakeProvider，不访问公网。
- UI 层网络调用计数必须为 0。
- QAbstractItemModel 只读数据来自 SessionState/presenter。
