# 计算规范（模型版本 M-2026.07-baseline）

## 1. 范围与版本纪律

本文件记录当前算法合同，供 PySide6 迁移保持行为。迁移阶段不得改变阈值、权重或公式。任何改动必须产生新模型版本、ADR、黄金向量和独立验证报告。

## 2. 输入合同

### Quote

- last/open/high/low/previous_close：有限且 >0，否则失败。
- high 修正为 `max(high, open, last)`；low 修正为 `min(low, open, last)`。
- volume/amount/turnover：非有限时置 0，负值钳制为 0。
- change_pct 非有限时由 `(last-previous_close)/previous_close*100` 重算。

### DailyBar

- OHLC 必须有限且 >0；volume/amount/turnover 必须有限且 ≥0，否则整行丢弃。
- high/low 修正为包含 open/close 的合法包络。
- pct_change 非有限时置 0。
- 输入应按日期升序、去重；当前实现需补显式契约测试和异常标记。

### 时间与复权

- 所有日线必须标明交易日、时区、复权方式和来源。
- 不同来源混用前必须完成价格连续性检查。
- 腾讯前复权与普通日线 fallback 的差异必须进入 provenance；不可静默等价。

## 3. 客观 Measurement

`measure(quote, history)` 与档位无关，计算：MA5/20/60、RSI14、MACD、布林位置、ATR%、20日支撑压力、近5日上涨占比、20日最大回撤、量比和日内位置。

### 八个因子

| 因子 | 最大绝对分 | 当前逻辑摘要 |
|---|---:|---|
| 均线结构 | 28 | 价格/MA5/MA20/MA60 顺序、距 MA20 和短中均线差 |
| 趋势质量 | 25 | 5日/20日斜率、近5日上涨占比、20日回撤 |
| 动量指标 | 18 | RSI14 区间 + MACD 快慢线/柱线 |
| 量能确认 | 14 | 涨跌与近20日量比共同确认 |
| 日内位置 | 12 | `(last-low)/(high-low)` 与当日涨跌 |
| 布林位置 | 8 | 价格在布林通道中的相对位置 |
| 支撑压力 | 8 | 20日支撑/压力突破与上下空间 |
| 波动风险 | 10 | ATR% 可控/中高/高波动 |

`base_factor_sum = Σ factor.score`。

### 风控扣分

- 高开 >4%：-8；低开 <-4%：-6。
- 当日振幅 >7%：-6。
- 当前价低于近20日高点的 88%：-4。

`objective_raw = base_factor_sum + risk_penalty`。历史样本 <30 时乘 0.75 并四舍五入。最终 `objective_score = clamp(round(value), -100, 100)`。

### 当前“confidence”

当前实现：`42 + min(abs(score)*0.42, 32) + history_bonus + available_indicator_bonus - high_atr_penalty`，最终钳制 35..92。

它不是经统计校准的成功概率。目标 UI 应优先改称“证据强度/数据把握”，或在完成校准研究前明确说明其启发式性质。

### 预期波动

优先 ATR%，否则当日振幅；钳制 0.8%..12%。它是常态波动参考，不是价格预测区间。

## 4. 五档策略

| 档位 | 买入线 | 卖出线 | 风控权重 | 证据门槛 | 风险预算 | 仓位上限 | 盈亏比 |
|---|---:|---:|---:|---:|---:|---:|---:|
| L1 稳健 | 40 | -15 | 1.6 | 70 | 0.50% | 30% | 2.5 |
| L2 稳进 | 33 | -19 | 1.3 | 60 | 0.75% | 45% | 2.2 |
| L3 标准 | 25 | -25 | 1.0 | 无额外门槛 | 1.00% | 60% | 2.0 |
| L4 积极 | 18 | -33 | 0.8 | 无额外门槛 | 1.50% | 75% | 1.7 |
| L5 激进 | 12 | -42 | 0.6 | 无额外门槛 | 2.00% | 90% | 1.5 |

`policy_score = base_factor_sum + risk_penalty * risk_weight`；样本 <30 同样乘 0.75；钳制 -100..100。L3 必须等于 objective_score。

- score ≥ buy threshold 且满足证据门槛：BUY。
- score ≤ sell threshold：SELL。
- 其余：HOLD。

## 5. 仓位与风控

- 止损百分比：`clamp(1.8 * ATR%, 2%, 12%)`；ATR 缺失回退 expected_move 或 3%。
- 仅 BUY 建议新多头仓位。
- strength：`clamp(abs(score)/55, 0.4, 1.0)`。
- evidence factor：`clamp(confidence/100, 0.5, 1.0)`。
- 初始比例：`risk_budget / stop_fraction * strength * evidence_factor`。
- 最终比例不超过 position_cap。
- 股数：`floor(capital*fraction/entry/100)*100`。
- 止损价：`entry*(1-stop_pct)`；目标：`entry*(1+stop_pct*reward_risk)`。
- 最大计划亏损：`shares*(entry-stop_price)`。

必须验证股数非负、100 整数倍、成本不超本金和上限；一手取整允许风险低于预算，不允许超过预算加明确容差。

## 6. 防御不变量

- 公共输出不含 NaN/Inf。
- 无效本金/价格/证据强度返回零仓位和原因。
- 样本不足返回 None/降权，不补造指标。
- 同输入、同模型、同数据顺序产生确定相同结果。
- 任何 clamp、fallback 和丢弃行都可由日志/quality metadata 解释。
- 展示舍入不反馈进计算。

