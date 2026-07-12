# 可观测性

## 日志 sink

- 标准错误（stderr）：始终附加，从控制台/终端运行时（开发环境、`main.py --self-test`）可见。
- 可选的 rotating file：`%APPDATA%\股市锦囊\logs\stock_advisor.log`（与 `services/store.py::config_path()` 的 `%APPDATA%\股市锦囊\` 同根，新增 `logs\` 子目录，不与 `config.json` 混放）；测试环境沿用 `STOCK_ADVISOR_CONFIG` 覆盖同一基目录的约定，不写真实 APPDATA。
- 打包为无控制台窗口的 GUI EXE（`PACKAGING_AND_DEPLOYMENT.md`）时用户看不到 stderr，因此 rotating file 是生产环境唯一对用户可诊断的持久 sink；两个 sink 共享同一 Formatter，内容一致，只是可见性不同。
- 只使用标准库 `logging`（含 `logging.handlers.RotatingFileHandler`）与 `json`，不引入第三方结构化日志依赖。

## 结构化格式

- 每条日志是一行 JSON（JSON Lines / NDJSON），两个 sink 使用同一个自定义 `Formatter`，禁止两个 sink 出现不同措辞或字段集合漂移。
- 字段：标准字段（`timestamp`、`level`、`logger`、`message`）+ 任务字段：`correlation_id`、`task_id`、`generation`、`operation`、`source`、`attempt`、`duration_ms`、`outcome`、`error_class`、`degraded`、`cancelled`。
- 禁止记录原始敏感 payload、完整自选/持仓、凭据；开发调试 payload 也要截断和脱敏（这是硬约束，不因 sink 是本地文件而放松）。

## 轮转策略

- `RotatingFileHandler(maxBytes=5_242_880, backupCount=5)`：单文件上限 5 MiB，保留最近 5 个轮转文件（`stock_advisor.log` + `.1`..`.5`），总占用上限约 30 MiB。
- 达到上限时按 stdlib 默认行为轮转（当前文件更名为 `.1`，依次后移，最旧的 `.5` 被丢弃），不需要额外的清理任务。
- 轮转是尺寸驱动而非时间驱动：不因为"跨天"就轮转，避免在低频使用时产生大量几乎空的日志文件。

## 日志级别

- INFO：任务开始/结束、来源 fallback、配置保存结果。
- WARNING：降级、stale、分页不完整、重试、字体 fallback。
- ERROR：核心失败、解析合同破坏、持久化失败、未捕获异常。

stderr handler 阈值为 WARNING（避免交互式控制台被 INFO 淹没）；rotating file handler 阈值为 INFO（保留完整诊断轨迹供事后排查）；两个 handler 共享同一 root logger，阈值差异只体现在 handler 级别，不体现在 logger 级别。

## 错误分类（error_class）

`error_class` 是"结构化格式"里每条任务事件必带的枚举字段，取值固定为以下 7 类之一；`NETWORK_RESILIENCE.md`（故障矩阵）与 `DATA_QUALITY.md`（清洗/丢弃/回退）引用本节作为其错误如何归类的唯一权威来源：

| error_class | 定义 | 典型来源 |
|---|---|---|
| `network` | 连接建立、TLS、超时、HTTP 状态、响应体超限、熔断打开 | DNS/连接/读取超时、429/5xx、TLS 校验失败、`response_limits_bytes` 超限 |
| `parse` | 已连通但响应内容不满足数据契约 | JSON 无法解析、HTML 冒充 JSON、截断响应、必需字段缺失/类型不符、分页计数不一致 |
| `validation` | 用户输入或领域不变量校验失败（非来源 payload 问题） | 非法股票代码、非有限/非正价格、本金 ≤0、筛选条件区间无效 |
| `persistence` | 配置读写失败 | `config.json` 损坏/不可解析、`os.replace` 失败、目录不可写、磁盘满 |
| `gui` | Qt/界面层未捕获异常或渲染失败 | 槽函数抛出未捕获异常、布局/绘制错误、字体 fallback 触发 |
| `packaging` | 打包运行时问题，只出现在 PyInstaller EXE 环境 | 冻结路径解析失败、资源/Qt 插件缺失、DLL 加载失败 |
| `unknown` | 无法归入以上 6 类的兜底分类 | 理论上不应被正常路径触发；出现即视为分类体系本身需要修订的信号 |

分类之间互斥（一条事件只归入一类）；`degraded`/`cancelled` 是独立的布尔字段，描述"结果状态"而非"错误原因"，与 `error_class` 正交（例如一次因 `network` 超时触发的降级读，`error_class=network` 且 `degraded=true`）。

## 指标

- 网络成功率、按源 fallback 率、429/5xx/timeout。
- 数据完整度、stale 率、清洗丢弃行数。
- 任务 P50/P95/P99、取消延迟、迟到丢弃数。
- GUI event handler 延迟、启动、RSS、表格排序。
- 门禁通过率、返工次数、缺陷逃逸和豁免年龄。

## 用户可见状态

QStatusBar 是状态真源的投影：任务、来源、时间、完整度、监控。关键降级同时用行内信息条，不只写日志。

