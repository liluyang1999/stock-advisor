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

## 档位切换

```text
level changed -> cached Measurement -> decide -> result projection -> UI
```

此路径禁止 provider、网络和重新计算客观 Measurement。

## 预警

QTimer 只触发调度。Worker 获取启用规则涉及的最新分析，主线程/纯逻辑 `check_rules` 判定假→真事件。generation 不匹配的监控结果丢弃。

## 持久化

SessionState 生成 AppConfig → ConfigStore 纯序列化 → 临时文件 → fsync/replace（实现可评估）→ 成功/错误事件。UI 不直接写文件。

