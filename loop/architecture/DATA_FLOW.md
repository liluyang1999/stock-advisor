# 数据流与状态流

## 个股分析

```text
用户输入
 -> parse_user_symbols（最多30、规范化、去重）
 -> AnalysisController 创建 task_id/generation/deadline
 -> Worker 调 workflow.analyze_symbol
 -> Provider 获取 quote/history
 -> measure() 生成 Measurement
 -> decide(level) 生成 Decision
 -> build_analysis_result()
 -> signal(result envelope)
 -> Controller 校验 generation
 -> SessionState 原子更新
 -> TableModel/Views 响应 change signal
```

quote 失败：该标的失败。history 失败：允许显式保守降级，结果必须包含 degraded reason。

## 全市场筛选

```text
preset + validated tunables
 -> market snapshot pages
 -> completeness validation
 -> filter + deterministic rank + TopN
 -> optional per-symbol deep analysis
 -> incremental rows + final report
```

任何分页中断必须返回 `complete=false`；严格模式失败，允许部分模式必须由用户明确选择并在 UI 持续显示。

## 行情字段合同与筛选预设参数表（东方财富 clist）

以下内容提取自已归档/删除的遗留设计 `docs/superpowers/specs/2026-06-22-market-screener-and-ui-design.md`（2026-06-22，可从 git 历史恢复），2026-07-13 已逐项对照 `src/stock_advisor/data/data_provider.py` 与 `src/stock_advisor/domain/presets.py` 核对仍然准确。市场号 `f13`（1=沪，0=深/北）、`secid` 不靠代码前缀猜测、`920xxx` 北交所新代码段这三点的权威定义已在根 `AGENTS.md`"行情数据约定"给出，此处不重复；下表只补充该文档未覆盖的字段级契约与预设参数。

### 全市场快照字段契约

`fetch_market_snapshot()` 分页请求 `data/data_provider.py::CLIST_FIELDS` 声明的字段（`f13` 语义见上，不重复列出）：

| 字段 | 含义 | 备注 |
|---|---|---|
| f12 | 代码 | 6 位数字字符串 |
| f14 | 名称 | 缺失时回退为代码 |
| f2 | 最新价 | 有限数，缺失记 `None` |
| f3 | 涨跌幅% | — |
| f4 | 涨跌额 | — |
| f5 | 成交量 | — |
| f6 | 成交额 | 预设的"成交额下限"流动性门槛用此字段 |
| f7 | 振幅% | — |
| f8 | 换手率% | — |
| f9 | 市盈率TTM | 可能为负（亏损股）；缺失记 `None` |
| f10 | 量比 | 钳制为非负 |
| f20 | 总市值 | — |
| f21 | 流通市值 | — |
| f22 | 涨速 | — |
| f23 | 市净率 | — |
| f24 | 60 日涨幅% | — |
| f25 | 年初至今涨幅% | — |

板块选择 `fs`（`data/data_provider.py::CLIST_FS`，五段用逗号拼接为一次请求）：`m:0+t:6`(深主板) `m:0+t:80`(创业板) `m:1+t:2`(沪主板) `m:1+t:23`(科创板) `m:0+t:81+s:2048`(北交所)。

### 六个筛选预设参数表（`domain/presets.py::PRESETS`）

TopN 默认 20（可调 5–30）；六个预设均含"剔除 ST"与成交额下限（流动性门槛，见下表）；每预设暴露 2–4 个可调关键参数，成对的上下限（如换手率上下限）经交叉校验（见 `apply_tunables`/`_check_crossed_bounds`），防止用户把区间调反导致筛选结果恒空。

| 预设 key | 名称 | 排序目标 | 核心条件（含固定 + 可调默认值） |
|---|---|---|---|
| `momentum_strong` | 强势动量 | momentum | 涨幅 2~7%、量比≥1.2、成交额≥1 亿、60 日涨幅>0、剔除 ST |
| `breakout_volume` | 放量突破 | breakout | 涨幅 1~9%、量比≥1.8、换手 3~25%、成交额≥2 亿、剔除 ST |
| `rebound_oversold` | 超跌反弹 | rebound | 今日涨幅≥−3%（企稳）、60 日跌幅≤−15%、年初至今<0、成交额≥1 亿、剔除 ST |
| `value_blue` | 低估值蓝筹 | value | PE 0~20、PB 0.5~3、总市值≥200 亿、成交额≥1 亿、剔除 ST |
| `activity_turnover` | 高换手活跃 | activity | 换手 5~30%、量比≥1.5、价格 3~60、成交额≥1 亿、剔除 ST |
| `steady_lowvol` | 稳健低波动 | balanced | 振幅≤4%、换手 1~8%、总市值≥100 亿、PE 0~30、成交额≥1 亿、剔除 ST |

## 档位切换

```text
level changed -> cached Measurement -> decide -> result projection -> UI
```

此路径禁止 provider、网络和重新计算客观 Measurement。

## 预警

QTimer 只触发调度。Worker 获取启用规则涉及的最新分析，主线程/纯逻辑 `check_rules` 判定假→真事件。generation 不匹配的监控结果丢弃。

## 持久化

SessionState 生成 AppConfig → ConfigStore 纯序列化 → 临时文件 → fsync/replace（实现可评估）→ 成功/错误事件。UI 不直接写文件。

