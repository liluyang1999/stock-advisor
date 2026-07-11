# 数据质量合同

## 质量维度

- Validity：类型、范围、OHLC 关系。
- Completeness：必需字段、页数、样本长度。
- Timeliness：获取时间、交易时段、stale TTL。
- Consistency：代码/市场、来源间价格差、复权连续性。
- Uniqueness：日期和代码去重。
- Provenance：来源、端点版本、fallback 链。

## 质量等级

- `complete`：核心与历史满足合同。
- `degraded_history`：quote 有效，history 不足/失败，使用保守判断。
- `partial_market`：市场分页不完整；默认不允许当成全市场结果。
- `stale`：超过场景 TTL，结果可查看但不可伪装为最新。
- `invalid`：核心字段不满足，禁止分析。

## 数值规则

- 价格 >0 且有限。
- 成交量/额/换手 ≥0 且有限。
- PE 可负；缺失为 None。
- 筛选设置边界时缺失值判不通过。
- 时间序列按交易日升序、同日唯一。
- 任何清洗、丢弃或回退都计数并可见。

## UI

状态栏/结果必须显示来源、更新时间、完整度和降级。导出文件包含模型版本和数据时间。错误不得只出现在日志中。

