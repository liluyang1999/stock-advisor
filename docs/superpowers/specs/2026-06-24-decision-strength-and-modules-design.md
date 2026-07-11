# 股市锦囊 — 决策强度内核 + 三大实用模块 设计

> 本设计在既有「个股分析 + 全市场选股」基础上，新增**决策强度（5 档滑杆）**这一贯穿全局的科学内核，并落地三个高价值模块：**仓位/风控计算器、可信度回测、专业 K 线图**；同时把产品正式更名为 **股市锦囊**，并把全局配色统一为 A 股本土惯例（红=涨/买，绿=跌/卖）。交付物仍为单文件 EXE `股市锦囊.exe` + HTML 说明书。

## 1. 目标

1. **决策强度可调（核心）**：用户用一个 5 档滑杆在「极稳健 → 激进」之间选择风险偏好；同一只股票的客观测量不变，但**买/持/卖结论、建议仓位、风险容忍**随档位科学地变化。
2. **后台逻辑绝对科学客观**：把「测量」与「决策」彻底分离——因子分数与指标是客观测量（对谁都一样）；档位只改变**决策策略**（阈值/风险权重/置信门槛/仓位预算/盈亏比）。仓位由经验常数升级为**基于风险预算 + ATR 止损的固定分数法**。
3. **三个实用模块**：仓位/风控计算器、可信度回测、专业 K 线图，充分利用已抓取的数据，不新增任何运行期依赖。
4. **更名**：`A股策略助手` → `股市锦囊`（取「锦囊妙计」之意）。
5. **配色本土化**：红=涨/买入/积极，绿=跌/卖出/谨慎，全局统一。
6. **详细测试**：纯逻辑 TDD 全覆盖；既有 139 测试保持全绿；打包后 `--self-test` 自验。

## 2. 不变的硬约束（沿用 AGENTS.md）

- 运行期只用 Python 标准库；构建期唯一依赖 PyInstaller；不引入 Node/.NET/浏览器框架。
- 单文件 EXE 交付（onefile/windowed）+ HTML 说明书；中间产物入 `build/`，交付物入 `dist/`；写边界在项目内。
- 核心逻辑与界面严格分离：新逻辑模块**纯逻辑、无网络、无 tkinter、可独立单测**。
- 接口失败明确报错，**绝不伪造行情或建议**；产品定位是**可解释的辅助判断工具，不构成投资建议**。

## 3. 核心原则：测量 / 决策分离

```
行情 + K线 ──► [测量层 measure()] ──► Measurement（客观，不随档位变）
                                          │
                       决策强度档位 level ─┤
                                          ▼
                                  [决策层 decide()] ──► Decision（买/持/卖 + 仓位% + 理由）
                                          │
                          本金 capital ───┤
                                          ▼
                              [仓位层 position_plan()] ──► 股数/止损/止盈/最大亏损
```

- **测量层只测量**：8 因子分数、综合分、各指标、风控扣分、置信度，全部与档位无关。
- **决策层只决策**：把客观测量按所选档位翻译成行动与仓位比例。
- **关键性质**：改档位 = 对**已缓存的 Measurement** 重新 `decide()`，**瞬时重算、绝不重新联网**。

## 4. 决策强度模型（5 档）

档位为整数 `1..5`，默认 **L3 标准**。各参数随档位**单调**，L3 等同当前行为（保证回归）。

| 档位 | 名称 | 买入阈值 `T_buy` | 卖出阈值 `T_sell` | 风险扣分权重 `w_risk` | 置信门槛 `C` | 单笔风险预算 `r` | 仓位上限 `cap` | 盈亏比 `RR` |
|---|---|---|---|---|---|---|---|---|
| L1 | 稳健 | +40 | −15 | ×1.6 | 70 | 0.5% | 30% | 2.5 |
| L2 | 稳进 | +33 | −19 | ×1.3 | 60 | 0.75% | 45% | 2.2 |
| L3 | 标准 | +25 | −25 | ×1.0 | —（不设门槛） | 1.0% | 60% | 2.0 |
| L4 | 积极 | +18 | −33 | ×0.8 | —（不设门槛） | 1.5% | 75% | 1.7 |
| L5 | 激进 | +12 | −42 | ×0.6 | —（不设门槛） | 2.0% | 90% | 1.5 |

**行为含义（科学/行为金融依据）**：

- **阈值非对称且「旋转」**：越保守 → 买入门槛越高（只在强确认时进场）、卖出门槛越低（更快减仓护本）；越激进 → 买入门槛越低（弱信号也进）、卖出门槛越高（容忍回撤、扛单）。这对应「保守=慢进快出、激进=快进慢出」的真实风险偏好，而非简单对称缩放。
- **风险扣分权重**：激进档把跳空/振幅/回撤等事件性风险扣分调轻，保守档调重。
- **置信门槛**：仅在保守端（L1/L2）生效——保守者要求更高把握才出手；L3 及以上不设门槛，避免改变既有标准档行为。
- **风险预算 / 仓位上限 / 盈亏比**：见第 6 节仓位科学化。

档间取表中离散值（5 档，非连续插值），实现为一张 `LEVELS` 表。

## 5. 决策层 `policy.py`（新增，纯逻辑）

```python
STANDARD = 3
LEVELS: dict[int, LevelSpec]  # 上表，含名称/阈值/权重/门槛/预算/上限/盈亏比

def decide(m: Measurement, level: int = STANDARD) -> Decision:
    policy_score = clamp(round(m.base_factor_sum + m.risk_penalty * w_risk(level)), -100, 100)
    if m.history_len < 30:
        policy_score = int(policy_score * 0.75)      # 小样本降权，沿用既有
    action = _action(policy_score, m.confidence, level)
    ...
```

- `_action`：`policy_score >= T_buy(level)`（且 `level<=2` 时还需 `confidence >= C`）→ BUY；`policy_score <= T_sell(level)` → SELL；否则 HOLD。当分数过阈但置信不足被降级时，附理由「信号达标但把握不足，本档要求更高确认」。
- `Decision` 含：`action`、`action_label`、`policy_score`、`confidence`（来自 Measurement，客观）、`suggested_position`（= `size_fraction` 百分数）、`forecast_label`、以及在 measurement 既有 reasons/risks 上追加的「档位说明」。
- **回归保证**：L3 时 `w_risk=1.0` 故 `policy_score == 既有 score`、阈值 ±25 == 既有、无置信门槛 → 买/持/卖与既有完全一致。

### `measure()`（由 `engine.py` 拆出，纯逻辑）

`measure(quote, history) -> Measurement`，字段：

- `factors: list[FactorScore]`（8 因子，客观，与今日一致）
- `risk_penalty: int`（风控扣分，单列出来供决策层重新加权；≤0）
- `base_factor_sum: int`（8 因子之和，**不含**风控扣分）
- `objective_score: int`（= `base_factor_sum + risk_penalty`，等于今日的综合分，供置信度与展示）
- `confidence: int`（沿用今日公式，基于 `objective_score`，客观、与档位无关）
- `indicators: IndicatorSnapshot`、`recent_closes`、`reasons`、`risks`、`history_len`、`last`、`change_pct`、`symbol`、`name`、`expected_move_pct`

`analyze_stock(quote, history, level=STANDARD) -> AnalysisResult` 改为 `combine(measure(), decide())` 的**薄包装**，保持既有签名与字段（供旧测试、`--self-test`、剪贴板/CSV 使用）。新增可选字段不破坏既有消费方。

## 6. 仓位科学化（替换经验常数 `_suggested_position`）

固定分数法 + ATR 止损，全部有界、可复核。两个层次：

**① 仓位比例（不需要本金，线程进结果表/详情）** `size_fraction(m, level) -> float`：

```
atr_pct   = m.indicators.atr_percent  or 当日振幅% or 默认 3.0
stop_pct  = clamp(1.8 * atr_pct, 2.0, 12.0)            # 止损距离%
strength  = clamp(|policy_score| / 55, 0.4, 1.0)        # 弱信号→小仓
conf_f    = clamp(confidence / 100, 0.5, 1.0)
fraction  = (r(level) / (stop_pct/100)) * strength * conf_f
fraction  = clamp(fraction, 0, cap(level))
# 非买入：HOLD/SELL → fraction = 0（不建议新建多头，附引导语）
suggested_position = round(fraction * 100)              # 即结果里的「投入比例%」
```

**② 绝对计划（需本金，供计算器模块）** `position_plan(m, level, capital) -> PositionPlan`：

```
entry      = m.last
stop_price = entry * (1 - stop_pct/100)
target_pct = stop_pct * RR(level)
target_price = entry * (1 + target_pct/100)
shares     = floor(capital * fraction / entry / 100) * 100   # A股 1 手=100 股
cost       = shares * entry
max_loss   = shares * (entry - stop_price)
max_loss_pct_of_capital = max_loss / capital
```

`PositionPlan` 字段：`shares, lots, entry, stop_price, stop_pct, target_price, target_pct, risk_reward, cost, max_loss, max_loss_pct, fraction, note`。

边界与诚实：本金不足 1 手 → `shares=0`，`note="本金不足以买入 1 手（100 股）"`；HOLD → `note="本档观望，不建议新建仓位"`；SELL → `note="本档建议减仓/离场，不计算买入仓位"`。

## 7. 模块①：仓位 / 风控计算器

- UI：详情区下方一张卡。输入「可用本金」（数字框，给合理默认值如 ¥100,000 并在会话内记忆；跨会话持久化为可选项，见第 19 节），自动取当前选中股的 Measurement + 全局档位，输出 `PositionPlan` 各项。
- 纯逻辑 `position_plan()`（第 6 节）；UI 仅渲染。
- 文案：止损红、止盈绿（本土配色）；最大亏损额与占本金% 突出显示。

## 8. 模块②：可信度回测（信号事后复盘）

`backtest.py`（新增，纯逻辑）：

```python
def backtest_signals(history, level=STANDARD, horizon=5, warmup=30, cost_pct=0.13) -> BacktestReport:
    for t in range(warmup, len(history) - horizon):
        as_of_history = history[:t]            # 仅当日之前
        pseudo_quote  = quote_from_bar(history[t], prev=history[t-1])
        decision      = decide(measure(pseudo_quote, as_of_history), level)
        fwd_return    = (history[t+horizon].close - history[t].close)/history[t].close*100 - cost_pct
        record(decision.action, fwd_return)
```

- 聚合：对 BUY/SELL/HOLD 各算 `次数 / 胜率 / 平均未来 horizon 日收益`；BUY 胜率=未来为正占比，SELL 胜率=未来为负占比。与「买入持有基线」对比，给出「信号超额」。
- **无未来泄漏**：信号只用 `history[:t]` + 第 t 根，未来收益 `close[t+h]` 仅作度量、不作输入。测试显式断言（构造未来异动不改变 t 时刻信号）。
- **诚实边界（必须随结果展示）**：单只标的、样本约 ≤90、指标为样本内、计入固定单边成本 `cost_pct`（默认 0.13%）、不含滑点冲击、**不预示未来**。
- `BacktestReport` 字段：`per_action: dict[action -> {count, win_rate, avg_return}]`、`buy_hold_return`、`sample_size`、`horizon`、`level`、`note`。

## 9. 模块③：专业 K 线图（纯 Canvas，不引第三方）

`chart.py`（新增，纯几何函数，可单测）：

- `index_to_x(i, n, left, right) -> float`、`price_to_y(price, lo, hi, top, height) -> float`
- `candle_geometry(bars, area) -> list[Candle]`（每根含 x、实体上沿/高、影线上下端、是否上涨）
- `moving_average_series(closes, window) -> list[float|None]`（warmup 段为 None）
- 支撑/压力复用 `engine.support_resistance`

渲染（`app.py` / 视图层）：主图蜡烛（**红涨绿跌**）+ MA5/MA10/MA20 叠加 + 成交量副图 + 支撑/压力虚线 + 回测买卖点标记（买点用强调蓝三角，避开红绿双义）。替换现有迷你 sparkline；几何走纯函数、绘制走 tkinter。可选 hover 十字光标与 OHLC 提示（二期可加，不阻塞本期）。

## 10. 想象力亮点：决策强度光谱尺

`spectrum(m) -> list[(level, action)]`（对 5 档各 `decide()`，纯逻辑可测）：

- UI：选中股下方一条 1–5 刻度，每格按该档结论着色（红买/灰观望/绿卖），高亮当前档。
- `flip_hint(spectrum) -> str`：给出「该股需到 X 档及以上才建议买入 / 各档均买入 / 仅激进才买」等一句话。
- 单调性（供测试）：买入阈值随档降→**BUY 集合向上封闭**（某档买，更激进档必买）；卖出阈值随档升→**SELL 集合向下封闭**。

## 11. 全局配色：A 股本土（红=涨/买，绿=跌/卖）

集中为命名常量（便于一处改、可测）。影响清单：

- `_score_color`：分数 >0 → 红，<0 → 绿（翻转）。
- `_action_color`：BUY→红，SELL→绿，HOLD→灰。
- Treeview 标签：`action_buy` 红底红字，`action_sell` 绿底绿字（互换）。
- 详情文本 `positive`→红、`negative`→绿；因子行按分数正负着色随之翻转（`_FACTOR_SCORE_RE` 逻辑不变，仅颜色映射翻转）。
- 可视化徽章/摘要色、光谱尺、计算器止损止盈色。
- K 线蜡烛：上涨红、下跌绿（本就本土）。
- 关键词着色集合 `_looks_positive/_looks_negative` 不变（仍按语义分类），仅其映射到的红/绿标签翻转。

## 12. 贯穿两页

- **全局决策强度滑杆**置于顶部（header），对**个股分析**与**全市场选股**两页同时生效。
- **个股分析**：表格、详情、K 线、计算器、光谱尺均反映当前档；拖动滑杆 → 对缓存的 Measurement 重新 `decide()`+`size_fraction()` 并重渲染，**不重新联网**。
- **全市场选股**：预设**筛选条件不变**（它筛的是证券特征，与风险偏好正交）；但对入选 Top N 的**买/持/卖结论与建议仓位列**采用当前档。故 `workflow`/`app` 需缓存每只入选股的 Measurement，支持改档即时重判。
- 结果表新增/复用「建议仓位」列（来自 `size_fraction`）。

## 13. 架构与文件变更

| 文件 | 变化 | 网络 | 可测 |
|---|---|---|---|
| `models.py` | 新增 `Measurement`、`Decision`、`PositionPlan`、`BacktestReport`、`LevelSpec`、`SpectrumCell`；保留 `AnalysisResult`（增可选字段） | 否 | — |
| `engine.py` | 拆出 `measure()`；`analyze_stock(...,level=STANDARD)` 改薄包装；指标函数不动 | 否 | 是 |
| `policy.py` **新** | `LEVELS`、`decide()`、`size_fraction()`、`position_plan()`、`spectrum()`、`flip_hint()` | 否 | 是 |
| `backtest.py` **新** | `backtest_signals()`、`quote_from_bar()` | 否 | 是 |
| `chart.py` **新** | K 线/光谱的纯几何函数 | 否 | 是 |
| `workflow.py` | 个股/选股编排回传 Measurement（供改档重判）；深度分析改用 measure+decide | 经 provider | FakeProvider |
| `app.py` | 顶部滑杆、全局重渲染、K 线渲染（调用 `chart.py`）、计算器卡、回测面板、光谱尺、配色翻转、更名；新增纯文本/格式 builder（`build_position_plan_text`/`build_backtest_text`/光谱单元） | — | 纯函数可测 |
| `manual.py` | 说明书更名、新增三模块与决策强度章节 | 否 | 是 |
| `build_exe.py` | EXE 名 `股市锦囊.exe`、HTML 名 `使用说明.html` | — | 配置可测 |
| `main.py` | `--self-test` 覆盖 measure→decide 多档 + 仓位 + 回测；更名字符串 | — | 是 |

> `app.py` 已 1846 行；本次把 K 线渲染与新 builder 抽到纯函数/`chart.py`，避免继续膨胀、并让新逻辑可测。不做与目标无关的重构。

## 14. 数据流（增量）

1. 抓行情/K 线（同今日，唯一联网处在 `data_provider`）。
2. `measure()` → Measurement（缓存于 app）。
3. 当前档位 `decide()` → 行动/仓位；`size_fraction()` → 投入比例。
4. 选中股时：`position_plan(capital)`、`backtest_signals(level)`、K 线几何、`spectrum()` 一并渲染。
5. **改档**：对所有缓存 Measurement 重做 3–4，重渲染，无网络。
6. 选股页：筛选/排序不变；Top N 深度分析回传 Measurement，按档判定与定仓。

## 15. 错误处理（延续诚实）

- 历史数据不足：`measure` 仍可出客观测量但置信下调；回测样本不足（`len<warmup+horizon`）→ 报「样本不足，暂不回测」，不伪造。
- 本金非法/为空：计算器明确提示，不静默纠正。
- 行情/全市场拉取失败：明确报错，不伪造。
- 始终保留免责声明与「不构成投资建议」。

## 16. 测试策略（详细 · TDD）

新增/更新测试，先红后绿，既有 139 全绿不破：

- `test_policy.py`：阈值非对称且随档单调；`decide` 在 L3 复现既有三类路径；同一 Measurement 下「激进买入数 ≥ 保守」；置信门槛仅 L1/L2 生效；`size_fraction` 随档/分数/置信单调、受 `cap` 封顶、HOLD/SELL→0。
- `test_sizing.py`：`position_plan` 股数按 100 取整、`max_loss`/`target` 数学正确、随本金单调、本金不足→0 股带诚实 note、SELL/HOLD 不给多头。
- `test_backtest.py`：上升序列→BUY 占优且平均未来为正；下降→SELL 且为负；横盘→HOLD 多；**无未来泄漏**断言；horizon 截断；成本拉低收益；样本不足报错。
- `test_chart.py`：`price_to_y` 单调且夹界、`index_to_x` 均布、`candle_geometry` 上下涨实体方向、MA warmup 段 None、空数据安全。
- `test_spectrum.py`：返回 5 格；BUY 集合向上封闭、SELL 集合向下封闭；`flip_hint` 文案正确。
- `test_engine.py`（更新）：保留三类路径；`suggested_position` 断言适配新仓位法（仍 `BUY>0`、`HOLD` 合理上限）。
- `test_app_helpers.py`（更新）：配色映射（行动→红/绿）、光谱单元格式、`build_position_plan_text`/`build_backtest_text`、滑杆档位解析、`APP_TITLE == "股市锦囊"`。
- `test_build_config.py`（更新）：EXE 名 `股市锦囊.exe`、HTML 名更新。
- `test_workflow.py`（更新）：选股回传 Measurement、按档重判。
- 全量：`python -m unittest discover -s tests` 全绿；`py_compile` 通过。
- 打包：`build_exe.py` → `dist\股市锦囊.exe --self-test` 退出码 0、打印 `SELF_TEST_OK`（含档位/仓位/回测自检）。
- GUI 冒烟：按记忆中 4K@250% DPI-unaware 机器的方式截图核验（见用户记忆 `stock-adviser-gui-verification`）。

## 17. 交付物

- `dist/股市锦囊.exe`（onefile/windowed/运行期纯标准库）。
- `dist/使用说明.html`（含两大功能 + 决策强度 + 三模块 + 配色与免责）。

## 18. 二期（不在本期范围）

自选股/持仓跟踪与持久化组合、条件预警、多股横向对比、板块/概念广度热力、资金流与基本面因子、K 线 hover 十字光标的完整交互、回测的多标的/walk-forward 滚动优化。本期已为「改档即时重算」「Measurement 缓存」打好结构，二期可在其上扩展。

## 19. 风险与缓解

- **配色翻转涉及面广** → 集中为命名常量 + 映射测试，避免遗漏。
- **回测可信度的表达边界** → 强制随结果展示样本/成本/不预示未来的诚实声明，文案不得暗示确定收益。
- **L3 回归** → `analyze_stock` 薄包装 + 既有测试守门；仓位法变更仅影响数值型断言，买/持/卖路径与分数不变。
- **持久化写边界** → 用户配置（本金/上次档位）写入系统用户配置目录（应用自身运行态，非本任务产物），不写项目目录之外的代码区；若不便则降级为「仅本次会话记忆」。
