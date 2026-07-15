# ADR-0013：金额与价格的表示——Decimal（精确 2 位）与 int/float 的职责边界

- 状态：accepted
- 日期：2026-07-15

## 背景

REQ-019 要求所有公式、单位、范围、样本要求、缺失处理可追溯；`governance/ENGINEERING_RULES.md` 第 23 条已经写明"中间计算保留精度，展示层才舍入"。但在本决策之前，产品的金额与报价一律用二进制 `float` 存储与运算，这条规则实际上无法被满足——`float` 根本无法精确表示两位小数（`10.10` 在 IEEE-754 下是 `10.0999999999999996447…`），"保留精度"在源头就不成立。

这不是理论问题，代码里存在可复现的真实缺陷：

1. **浮动盈亏金额**：`domain/compare.py` 的 `pl_amount = (last - cost) * shares`，在 `last=10.10, cost=10.00, shares=100` 时得到 `9.999999999999964` 而非 `10.00`。
2. **仓位整手取整**：`domain/policy.py::position_plan` 的 `capital * frac / entry // 100` 用 float 运算，误差可使整手取整发生 off-by-one（本该 300 股却算成 299→200 股）。
3. **持久化往返**：`services/store.py` 把成本/本金以 float 写入 JSON，存进去的本就不是用户输入的那个两位小数，读回再参与运算会持续放大。
4. **入口即失真**：东方财富 clist/quote 返回的是**整数**标度价（如 `f43` = 价格×100），本是精确值，却在解析入口就被除成 float。

同时，产品里绝大多数数值**不是**金额：涨跌幅、换手率、振幅、评分、置信度、仓位比例，以及 MA/MACD/RSI/ATR/布林等统计指标——后者本就要喂给 `statistics.mean`/`pstdev`/EMA 这类统计函数，用 Decimal 既无必要也不合适（统计量的"精确到分"没有语义）。因此需要一条明确的边界规则，而不是"全部改成 Decimal"或"维持全 float"。

## 决策

1. **金额与报价用 `decimal.Decimal`，量化到 2 位小数、`ROUND_HALF_UP`**（金额习惯的四舍五入，而非 Python 默认的银行家舍入）。唯一权威工具是 `src/stock_advisor/domain/money.py`：`to_money` / `parse_money` / `positive_money` / `scaled_price` / `quantize_money`，常量 `CENT` / `ZERO_MONEY`。适用字段：报价（`Quote`/`DailyBar` 的 `last`/`open`/`high`/`low`/`close`/`previous_close`、`MarketSnapshot.price`/`change`）、用户金额（`WatchItem.cost`、`AppConfig.capital`）、盈亏金额（`ComparisonRow.pl_amount`）、仓位计划的价格与金额（`PositionPlan` 的 `entry`/`stop_price`/`target_price`/`cost`/`max_loss`）、`Measurement`/`AnalysisResult.last`。
2. **数量用 `int`**（股数、手数、成交量）。
3. **比率／百分比／评分／统计指标用 `float`**，安全解析器统一收敛在 `domain/numeric.py`（`finite_float` 等）。
4. **大额、仅供展示与区间过滤的市场聚合量保持 `float`**：成交额 `amount`、市值 `total_cap`/`float_cap`、资金流净额。理由：它们按"亿/万"舍入展示、只参与区间筛选，从不汇入用户金额的精确运算；对 800 亿这种量级谈"精确到分"没有语义，且强行 Decimal 化会把 Decimal/float 混用引入选股筛选与展示换算。该边界在 `models.py` 字段注释与 `money.py` 模块文档中就地标注。
5. **边界规则（不可绕过）**：
   - 入口：`data/data_provider.py` 用 `money.scaled_price` / `money.parse_money` 解析；东财整数标度价 → Decimal 除法 → 精确两位，不经过 float。
   - 指标：`domain/engine.py::measure` 在**喂给统计函数处一次性** `float(price)`（`float(quote.last)`、`[float(bar.close) …]`）；Decimal 不得流入 `mean`/`pstdev`/EMA，float 也不得回流成金额。
   - 持久化：`services/store.py` 把金额以 **JSON 字符串**写出（`str(cost)`），读回用 `money.parse_money`（JSON 没有 Decimal 类型，写成 float 就等于放弃精度）。
   - 计算：`position_plan`（整手取整/成本/最大亏损）与 `compare` 的 P&L 全程 Decimal；`position_plan` 兼收 `Decimal|int|float` 本金并在入口用 `positive_money` 归一。

## 替代方案

1. **维持 float，仅在展示层舍入到 2 位（拒绝）**：改动最小，且展示结果多数时候"看起来对"。但它无法满足"计算过程不丢信息"——误差在减法/乘法/取整处已经产生并被放大（`pl_amount` 的 `9.999…`、整手 off-by-one 都发生在展示之前），展示层舍入只是把错误藏起来。这恰恰是 ENGINEERING_RULES 第 23 条要禁止的。
2. **整数最小单位（分）（拒绝）**：把金额存成 int 分，绝对精确、运算最快，是交易/清算系统的常见选择。拒绝理由：本产品的金额要与比率频繁互算（本金×仓位比例÷价格→股数、成本×股数、盈亏÷本金），到处都要 ×100/÷100 的手工换算，极易在某处漏乘而产生 100 倍错误；价格小数位、市值到"元/亿"的换算尤其繁琐；可读性与可审查性都差于 Decimal，而本产品是分析/辅助决策工具，不在纳秒级撮合路径上，Decimal 的性能开销无关紧要。
3. **全面 Decimal 化（含统计指标与大额聚合）（拒绝）**：形式上最"统一"。但 MA/MACD/RSI/ATR/布林是统计量，`statistics.mean`/`pstdev` 与 EMA 递推用 Decimal 既无精度语义（均值本就可能是无限小数）又要处处处理量化与除法精度；且成交额/市值等聚合量按亿/万展示，两位小数无意义。强行统一只会把 Decimal/float 的混用面积扩大到整个指标层与筛选层，增加出错面而无收益。
4. **（采用）金额与报价 Decimal（2 位、ROUND_HALF_UP），数量 int，比率/指标/大额聚合 float，并明确入口/指标/持久化/计算四处边界**：见"决策"。

## 后果

正面：

- 上述四个真实缺陷同时消失，且有可复现的实证：`(10.10-10.00)*100` 由 float 的 `9.999999999999964` 变为 Decimal 的 `10.00`。
- ENGINEERING_RULES 第 23 条从一条无法兑现的口号变成可执行、可验证的约束；"金额与价格统一两位小数、数量统一整数"成为全工程有单一真源（`money.py`/`numeric.py`）的约定。
- 精度问题被限制在类型系统里：金额是 Decimal、比率是 float，Decimal 与 float 直接做算术会**抛 TypeError**，误用在开发期即被 pyright 或运行时暴露，而不是悄悄产生错误数值。
- 入口不再失真：东财整数标度价的精确性被一路保留到存储与计算。

负面/成本：

- 边界处必须显式转换（指标层的 `float(price)`、持久化的 `str(money)`），比全 float 时代多了一层心智负担；漏转会在 pyright/测试处报错（这是有意的代价，把错误提前）。
- Decimal 运算慢于 float，且 Decimal 与 float 不能直接混算——任何"金额×比率"都要就地把比率转 `Decimal(str(ratio))`。对本产品的数据量级（单次数百根日线）无实际性能影响。
- JSON 无 Decimal 类型，持久化必须走字符串，读写两侧要成对维护（写 `str()`、读 `parse_money`），任一侧漏改会静默退回 float 语义。
- 大额聚合量保持 float 属于有意的范围收窄，意味着"金额一律 Decimal"这句话有例外，必须靠字段注释与本 ADR 说明，否则后来者会困惑。

## 回滚

不设"退回 float"的回滚路径：退回等于重新引入已被实证的错误数值，属于功能回退而非缓解。若某处 Decimal 确实不可行（例如引入的第三方库只接受 float），正确做法是在该边界显式转换并记录理由，而不是把模型字段改回 float。若要收窄或扩大范围（例如把成交额/市值也纳入 Decimal，或反之），须以本 ADR 的修订形式提出，并附带对筛选/展示换算面的影响评估。停止条件：任何把 `models.py` 中金额/报价字段改回 `float`、或绕过 `money.py` 直接对金额做 float 运算的改动，必须在代码评审阶段被阻断。

## 重访触发

- 若产品未来进入真实下单/对账场景（不再只是分析建议），需要重新评估是否升级到整数最小单位（分）以及是否需要更严格的舍入审计。
- 若引入的行情源或第三方计算库只接受/返回 float 金额，需要重新评估边界转换点的位置与是否需要在入口重新量化。
- 若成交额/市值等聚合量开始参与用户金额的精确运算（而不再只是展示与区间过滤），第 4 条的范围收窄即失效，须修订本 ADR 把它们纳入 Decimal。
- 若发现 `ROUND_HALF_UP` 与实际业务口径（例如某些场景要求截断或银行家舍入）不符，须修订而不是在个别调用处静默改 rounding。

## 关联

REQ-019、AC-007、WI-000、RISK-007、EVD-LOOP-004；`governance/ENGINEERING_RULES.md` 第 23 条；实现见 `domain/money.py`、`domain/numeric.py`。
