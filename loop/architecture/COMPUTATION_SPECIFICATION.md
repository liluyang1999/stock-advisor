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

### 指标窗口（对照 `domain/engine.py` 逐项复现）

| 指标 | 窗口 / 参数 | 精确定义 | 函数 |
|---|---|---|---|
| MA5 / MA20 / MA60 | 5 / 20 / 60 日 | 收盘价简单算术平均；样本不足（`len(values)<window`）返回 `None` | `moving_average` |
| RSI14 | 14 期（15 个收盘价） | **简单算术平均**涨跌幅之比——`avg_gain`/`avg_loss` 为最近 14 个日涨跌的算术平均（**非** Wilder 指数平滑）；`avg_gain=avg_loss=0→50`，`avg_loss=0→100`，`avg_gain=0→0`，否则 `100-(100/(1+avg_gain/avg_loss))` | `rsi` |
| MACD | 快线 EMA12 / 慢线 EMA26 / 信号线 EMA9 | 至少需要 35 个收盘价（26+9）才输出，否则 `None`；EMA 平滑系数为 `2/(period+1)`，起始值取前 `period` 个值的算术平均，随后逐值递推；`histogram=macd_line-signal` | `macd_snapshot` / `_ema_series` |
| 布林带位置 | 20 日、±2 倍标准差 | 标准差为**总体标准差**（`statistics.pstdev`，分母 N，非样本标准差 N-1）；标准差为 0 时位置记为中性 `0.5`；位置 `=(last-lower)/(upper-lower)`，可能 `<0` 或 `>1`（价格在轨道外） | `bollinger_position` |
| ATR%（真实波幅百分比） | 14 日 | `mean(true_range_1..14) / 现价 × 100`；`true_range=max(H-L, \|H-C_prev\|, \|L-C_prev\|)`；结果是"现价的百分比"，不是原始点数 ATR | `average_true_range_percent` |
| 支撑 / 压力 | 20 日 | 支撑 = 区间内最低价（low）的最小值；压力 = 区间内最高价（high）的最大值 | `support_resistance` |
| 近5日胜率 | 最近 5 个交易日（6 个收盘价） | 5 次逐日环比涨跌中"上涨"的比例（`current>previous`） | `_five_day_win_rate` |
| 20日最大回撤 | 最近 20 个收盘点（`closes[-20:]`） | 区间内任意在先峰值到其后最低点的最大跌幅 %；至少需 2 个点 | `_max_drawdown` |
| 量比 | 最近 20 日（≥5 个有效样本） | 当日成交量 / 近20日成交量算术平均 | `_volume_ratio` |
| confidence 数据量增益归一窗口 | 90 个交易日封顶 | 见下文 confidence 公式的 `history_bonus` | `_confidence` |

日内位置 `(last-low)/(high-low)` 使用当日 Quote 的高低区间（非历史窗口），跨度非正时记为 `None`。

### 八个因子

| 因子 | 最大绝对分（`FactorScore.max_abs_score`） | 当前逻辑摘要 |
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

### 八个因子——逐条精确规则

下列分支与 `domain/engine.py` 一一对应；每个因子的 `score` 字段只会取列出的这些离散值（`max_abs_score` 是随 `FactorScore` 一起返回的展示型元数据字段，见下方标注的两处例外，它并不总是等于该因子实际可达的最大分值）。

**均线结构**（`_score_moving_averages`）
- 中间量：`price_vs_ma20=(last-ma20)/max(|last|,0.01)×100`（分母是**现价**）；`ma_spread=(ma5-ma20)/max(|ma20|,0.01)×100`（分母是 **MA20**）。
- MA5 或 MA20 缺失 → `0`（样本不足）。
- `last>ma5>ma20` 且 `price_vs_ma20>0.5` 且 `ma_spread>0.2` 且（MA60 缺失或 `ma20>ma60`）→ **`+28`**。
- `last<ma5<ma20` 且 `price_vs_ma20<-0.5` 且 `ma_spread<-0.2` 且（MA60 缺失或 `ma20<ma60`）→ **`-28`**。
- 上两条都不满足但 `price_vs_ma20>0.35` → **`+8`**。
- `price_vs_ma20<-0.35` → **`-8`**。
- 其余 → `0`。
- 可达范围 `{-28,-8,0,8,28}`，与 `max_abs_score=28` 一致。

**趋势质量**（`_score_trend`，四个子项相加）
- 5日斜率子项（需 `len(closes)≥25`）：`slope=(MA5(closes)-MA5(closes[-25:-5]))/max(|MA5(closes[-25:-5])|,0.01)×100`；`slope>2→+12`；`slope<-2→-12`。
- 20日斜率子项（需 `len(closes)≥40`）：`slope=(MA20(closes)-MA20(closes[-40:-20]))/max(|MA20(closes[-40:-20])|,0.01)×100`；`slope>1→+8`；`slope<-1→-8`。
- 胜率子项：`win_rate≥0.7→+5`；`win_rate≤0.3→-5`。
- 回撤子项：20日最大回撤 `>8%→-4`（只罚不奖，无对称正项）。
- verdict：`score>6`→偏多，`score<-6`→偏空，否则中性。
- **例外标注**：四项相加的真实可达范围是 `-29..+25`（正向三项之和 `12+8+5=25` 与标注一致；负向额外多出回撤子项的 `-4`，达到 `-29`），负向已超出 `max_abs_score=25` 这一展示值。

**动量指标**（`_score_momentum`，两个子项相加）
- RSI 子项：`52≤RSI14≤68→+8`；`32≤RSI14<45→-8`；`RSI14>76→-6`（同时记入风险提示而非机会提示）；`RSI14<24→-4`（同时记入风险提示）；RSI14 缺失→记入风险提示、子项不计分；其余区间（`45≤RSI14<52`、`68<RSI14≤76`、`24≤RSI14<32`）→ `0`。
- MACD 子项（MACD 缺失→记入风险提示、子项不计分）：`histogram=macd_line-signal`。若 `|histogram|/max(|macd_line|,0.01)<0.08` 或 `|histogram|<0.001` → **`+0`**（信号强度不足，不确认方向）；否则 `macd_line>signal`（等价于 `histogram>0`）→ **`+10`**；`macd_line<signal`（`histogram<0`）→ **`-10`**。
- verdict：`score>6`→偏多，`score<-6`→偏空，否则中性。
- 可达范围 `{-18,...,18}`（RSI 子项 `±8` 为其最大幅度、MACD 子项 `±10`），与 `max_abs_score=18` 一致。

**量能确认**（`_score_volume`；`volume_ratio` 缺失→`0`）
- `change_pct>0.5` 且 `volume_ratio≥1.5` → **`+14`**。
- `change_pct<-0.5` 且 `volume_ratio≥1.3` → **`-14`**。
- `volume_ratio<0.65` → **`-4`**。
- 其余 → `0`。
- 可达范围 `{-14,-4,0,14}`，与 `max_abs_score=14` 一致。

**日内位置**（`_score_intraday`；`position=(last-low)/(high-low)` 缺失→`0`）
- `change_pct≥0.8` 且 `position≥0.72` → **`+12`**。
- `change_pct≤-0.8` 且 `position≤0.28` → **`-12`**。
- `position<0.2` → **`-5`**。
- `position>0.85` → **`+4`**。
- 其余 → `0`。
- 可达范围 `{-12,-5,0,4,12}`，与 `max_abs_score=12` 一致。

**布林位置**（`_score_bollinger`；缺失→`0`）
- `0.55≤position≤0.9` → **`+6`**。
- `position>1.05`（突破上轨较多）→ **`-6`**。
- `position<-0.05`（跌破下轨）→ **`-6`**。
- `position<0.25` → **`-3`**。
- 其余 → `0`。
- **例外标注**：可达范围是 `{-6,-3,0,6}`——`FactorScore.max_abs_score` 传入的字面量是 `8`，但 `score` 在任何分支都不会取到 `±8`；`8` 只是展示型上限元数据，不是该因子实际可达的分值。

**支撑压力**（`_score_support_resistance`；支撑/压力缺失或 `last≤0`→`0`）
- `last≥resistance×1.005` → **`+8`**。
- `last≤support×1.01` → **`-8`**。
- 否则比较 `upper_room=(resistance-last)/last×100` 与 `lower_room=(last-support)/last×100`：`upper_room>lower_room×1.5→+3`；`lower_room>upper_room×1.5→-3`；否则 `0`。
- 可达范围 `{-8,-3,0,3,8}`，与 `max_abs_score=8` 一致。

**波动风险**（`_score_volatility`；`atr_percent` 缺失→`0`）
- `atr_percent>6` → **`-10`**。
- `atr_percent>3.5` → **`-4`**。
- 其余（含 `atr_percent≤3.5`）→ **`+4`**。
- **例外标注**：可达范围是 `{-10,-4,4}`（外加缺失时的 `0`）——负向 `-10` 与 `max_abs_score=10` 一致，但正向永远不会超过 `+4`；`10` 对正向而言不是可达值。

八个因子 `max_abs_score` 字面量之和为 `28+25+18+14+12+8+8+10=123`；结合上面两类"展示值不等于可达值"的例外（趋势质量负向可至 `-29`、布林位置和波动风险的正/负向达不到标注的 `±8`/`±10`），`base_factor_sum` 的真实理论区间比 `-123..+123` 更窄且不对称，最终仍由 `objective_score` 的 clamp（见下）收口到 `-100..100`——因此以上口径差异不影响 `objective_score` 的可复现性，只影响"单个因子距离满分还有多远"这类展示语义。

### 风控扣分

三个子项彼此独立、可同时触发（不是互斥分支），故 `risk_penalty` 的可达范围是 `-18..0`：

- 高开 `(open-previous_close)/previous_close×100 > 4%` → **`-8`**；`< -4%` → **`-6`**（两者互斥，同一 elif 链）。
- 当日振幅 `(high-low)/low×100 > 7%` → **`-6`**（独立判断，可与高低开子项叠加）。
- 当前价低于近20日高点（`max(bar.high for bar in history[-20:])`）的 `88%` → **`-4`**（独立判断，可与前两者叠加）。

`objective_raw = base_factor_sum + risk_penalty`。历史样本 <30 时乘 0.75 并四舍五入。最终 `objective_score = clamp(round(value), -100, 100)`。

### 当前"confidence"

完整公式（`_confidence`，输入为 `objective_score`、清洗后的 `history`、`IndicatorSnapshot`）：

```
base                       = 42 + min(|objective_score| × 0.42, 32)
                             # 42..74；|objective_score| ≥ 76.19 时 32 分封顶
history_bonus              = min(history_len, 90) / 90 × 12
                             # 0..12；history_len（清洗后历史条数）达 90 即拿满 12 分，线性折算
available_indicator_bonus  = 2 × N
                             # 0..12；N = 以下 6 项指标中非 None 的个数：
                             #   volume_ratio、ma60、macd_histogram、bollinger_position、atr_percent、support
high_atr_penalty           = 6（仅当 atr_percent > 6 时触发；否则为 0）
                             # 固定值，非按比例、非按超出幅度分级

confidence = clamp(round(base + history_bonus + available_indicator_bonus − high_atr_penalty), 35, 92)
```

`base+history_bonus+available_indicator_bonus-high_atr_penalty` 的理论下界为 `42+0+0-6=36`，已高于 `35` 这个 clamp 下限——`35` 是防御性下界，正常路径不会被触发（只有在未来任何一项计算越出这里描述的范围时才起作用）。

它不是经统计校准的成功概率。目标 UI 应优先改称"证据强度/数据把握"，或在完成校准研究前明确说明其启发式性质。

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

## 7. 回测重放合同（`domain/backtest.py::backtest_signals`）

事后信号复盘，用于展示"可信度回测"而非预测：默认 `horizon=5`（持有天数）、`warmup=30`（预热样本数）、`cost_pct=0.13`（单边成本%）。样本不足（`len(clean_history)<warmup+horizon+1`）或参数非法（非有限、≤0、成本为负）返回 `ok=False` 并说明原因，不伪造回测结果。

无未来泄漏：第 `t` 日信号只使用 `history[:t+1]`（含当日）经 `measure()+decide()` 生成；未来收益 `(close[t+horizon]-close[t])/close[t]×100−cost_pct` 仅作事后度量，不回流进第 `t` 日的信号计算。胜率口径：BUY/HOLD 以未来收益为正记胜，SELL 以未来收益为负记胜（卖出信号"对"意味着随后下跌）。报告同时给出买入持有基线收益、样本量与"仅用当日及之前数据，不预示未来"的诚实说明。

来源：已归档/删除的遗留设计 `docs/superpowers/specs/2026-06-24-decision-strength-and-modules-design.md`（2026-06-24，可从 git 历史恢复）§8，默认参数已于 2026-07-13 对照 `src/domain/backtest.py::backtest_signals` 签名核对仍然准确。
