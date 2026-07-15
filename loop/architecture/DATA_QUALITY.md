# 数据质量合同

## 质量维度

- Validity：类型、范围、OHLC 关系。
- Completeness：必需字段、页数、样本长度。
- Timeliness：获取时间、交易时段、stale TTL（数值见下方"Stale TTL"一节，权威来源 `config.json.data_freshness`）。
- Consistency：代码/市场、来源间价格差、复权连续性。
- Uniqueness：日期和代码去重。
- Provenance：来源、端点版本、fallback 链。

## 质量等级

- `complete`：核心与历史满足合同。
- `degraded_history`：quote 有效，history 不足/失败，使用保守判断。
- `partial_market`：市场分页不完整；默认不允许当成全市场结果。
- `stale`：数据年龄超过对应操作的 stale TTL（见下方"Stale TTL"一节），结果可查看但不可伪装为最新。
- `invalid`：核心字段不满足，禁止分析。

## Stale TTL

按操作区分的新鲜度阈值（秒），权威机器配置为 `config.json.data_freshness.stale_ttl_seconds`，本节只解释语义：

| 操作 | TTL（秒） | 语义与取值理由 |
|---|---:|---|
| quote（实时报价） | 30 | 按钮触发式拉取而非逐笔推送；30 秒内视为"当前价"，超过则必须提示用户结果可能滞后于盘口。 |
| history（历史日线） | 21600（6 小时） | 日线颗粒度在同一交易日内不变；6 小时覆盖单个交易时段（A股连续交易约4小时+间隔），跨交易日必然触发重新拉取。 |
| market_snapshot（全市场快照） | 120（2 分钟） | 全市场批量抓取成本高（响应体上限 32 MiB，见 `NETWORK_RESILIENCE.md`），2 分钟在"筛选结果不过时"与"避免频繁全量拉取"之间取折中。 |
| fund_flow（资金流） | 180（3 分钟） | 资金流为独立、可失败、不进入核心客观分的辅助通道（见 `NETWORK_RESILIENCE.md` 数据源策略），新鲜度要求低于 quote/market_snapshot。 |

- TTL 以"距上次成功获取的秒数"计算；超过 TTL 的数据仍可展示，但必须标记为 `stale` 质量等级并在 UI 呈现获取时间，不得静默当作最新数据参与决策叙述。
- 这些数值是本轮治理新增的起始策略，不是历史已验证的产品行为；后续如需调整，走正常的 `config.json` 变更流程（`registers/changes.jsonl`），无需 ADR（不涉及架构决策，只是策略数值）。
- 与 `network_policy.operation_deadlines_seconds`（同名 4 个操作的**请求超时预算**）是两个不同的概念：deadline 控制"一次网络请求最多等多久"，TTL 控制"拿到的数据还能被当作新鲜数据用多久"；两者数值不需要相等，也确实不相等。

## 数值规则

- **数值表示（ADR-0013，全工程单一约定）**：金额与报价用 `Decimal`，量化到 2 位小数、`ROUND_HALF_UP`（工具见 `domain/money.py`）；数量用 `int`；比率/百分比/评分/统计指标（MA/MACD/RSI/ATR/布林）用 `float`（安全解析器见 `domain/numeric.py`）；成交额、市值、资金流净额等**仅供展示（按亿/万舍入）与区间过滤**的大额聚合量保持 `float`，不汇入用户金额的精确运算。边界：入口把东方财富的整数标度价精确解析为 Decimal（不经 float）；指标层仅在喂给 `mean`/`pstdev`/EMA 等统计函数处一次性转 float，且不回流成金额；持久化把金额写为 JSON **字符串**（JSON 无 Decimal 类型，写成 float 即放弃精度）。
- 价格 >0 且有限。
- 成交量/额/换手 ≥0 且有限。
- PE 可负；缺失为 None。
- 筛选设置边界时缺失值判不通过。
- 时间序列按交易日升序、同日唯一。
- 任何清洗、丢弃或回退都计数并可见；由此产生的错误归入 `error_class=validation`，`parse`（来源 payload 结构/字段不满足契约）或 `network`（获取失败）分类见 `OBSERVABILITY.md` 的错误分类法。

## UI

状态栏/结果必须显示来源、更新时间、完整度和降级。导出文件包含模型版本和数据时间。错误不得只出现在日志中。

