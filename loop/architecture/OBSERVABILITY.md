# 可观测性

## 结构化事件

每个任务记录：correlation_id、task_id、generation、operation、source、attempt、duration_ms、outcome、error_class、degraded、cancelled。

## 日志级别

- INFO：任务开始/结束、来源 fallback、配置保存结果。
- WARNING：降级、stale、分页不完整、重试、字体 fallback。
- ERROR：核心失败、解析合同破坏、持久化失败、未捕获异常。

禁止记录原始敏感 payload、完整自选/持仓、凭据。开发调试 payload 也要截断和脱敏。

## 指标

- 网络成功率、按源 fallback 率、429/5xx/timeout。
- 数据完整度、stale 率、清洗丢弃行数。
- 任务 P50/P95/P99、取消延迟、迟到丢弃数。
- GUI event handler 延迟、启动、RSS、表格排序。
- 门禁通过率、返工次数、缺陷逃逸和豁免年龄。

## 用户可见状态

QStatusBar 是状态真源的投影：任务、来源、时间、完整度、监控。关键降级同时用行内信息条，不只写日志。

