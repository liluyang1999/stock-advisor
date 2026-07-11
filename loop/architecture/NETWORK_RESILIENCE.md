# 网络韧性与防御

## 边界

`data_provider.py` 继续作为唯一网络出口。UI、table model、领域计算不得构造 URL 或解析 payload。解析函数保持纯函数。

目标 Qt 传输遵循 ADR-0003：`NetworkWorker(QObject)` 驻留专用 `QThread` 事件循环，并在线程启动后创建一个 `QNetworkAccessManager`。manager、reply 与 deadline timer 同线程；命令从 controller 经 queued signal 进入。受限响应复制为 bytes 后调用纯解析器，reply 始终 `deleteLater()`。迁移期同步 urllib provider 可由 QThreadPool 有界包装，但只实现同一 port，不进入 GUI 或领域层。

## 请求预算

| 操作 | 总 deadline |
|---|---:|
| 实时报价 | 12s |
| 历史日线 | 20s |
| 全市场快照 | 30s |
| 资金流 | 12s |

deadline 覆盖所有重试和备用源，不允许每个源重新获得完整预算。连接与读取分别设置更短 timeout。

## 重试

- 只重试幂等 GET 和明确瞬时错误。
- 最多 3 次，指数/递增退避 + 20% 随机抖动。
- 尊重 `Retry-After`，但不得超过总 deadline。
- 4xx 参数/权限/解析合同错误不盲重试。
- 用户取消或 generation 过期立即停止发新请求。

## 并发、熔断与响应上限

- 每 host 同时最多 4 个请求，全局最多 8 个；用户主任务优先于预警轮询。
- 同一来源连续 5 次可恢复失败时隔离 30 秒，半开仅放行 1 个探测；资金流通道单独计数，不拖累核心行情。
- quote/history/market snapshot/fund flow 响应上限分别为 2/8/32/4 MiB；超限立即失败，不重试同一内容。
- 只重试 408、425、429、可恢复 5xx 和瞬时连接错误；TLS、校验、解析、内容超限与用户取消不重试。
- 所有数值以根 `config.json.network_policy` 为唯一机器配置，本文只解释语义。

## 验证

响应必须验证：

- HTTP 状态、Content-Type、最大长度。
- JSON 可解析、顶层结构、必需字段、数值范围。
- source、fetched_at、市场/代码一致性。
- 分页预计总数、实际条数、重复和缺页。
- `"-"`/空/负 PE/非有限的正确语义。

## 数据源策略

- 实时报价：东方财富 → 新浪。
- 历史：东方财富 → 新浪 → 腾讯前复权 → 腾讯普通。
- 全市场：东方财富 clist，对等主机 fallback；市场号以 f13 为准。
- 北交所 `920xxx` 必须有契约测试。
- 资金流为独立、按需、可失败通道。

## 完整度

统一 envelope：`source, fetched_at, complete, stale, expected_count, received_count, fallback_chain, errors`。

- 核心 quote 不完整：失败。
- history 失败：允许显式保守降级。
- market snapshot 部分页：默认失败；若未来允许部分模式，需用户明确选择。
- fund flow 失败：显示稍后重试，不污染核心分数。

## 故障矩阵

DNS、TLS、连接/读取超时、429、5xx、断连、空响应、HTML 冒充 JSON、截断 JSON、过大响应、字段漂移、乱序、重复、分页中断、迟到结果、取消。

PR 测试全部离线；定时 live canary 仅发现上游变化，不作为正确性唯一证据。

## Qt 生命周期故障合同

- manager 不得在存在活动 reply 时移动线程。
- abort、timeout、TLS/redirect 拒绝、窗口关闭与应用退出均必须释放 reply/timer。
- shutdown 顺序为拒绝新命令 → 取消/abort → `quit()` → 有限 `wait()`；禁止无限等待或 `terminate()`。
- 大响应解析不在 GUI 线程；迟到回调必须通过 task_id/generation 丢弃。
