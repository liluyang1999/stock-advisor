# 股市锦囊 二期 2B — 条件预警 设计

> 给自选股加条件预警：程序开启时按间隔轮询，当`价格/涨跌幅/综合分`越过阈值（边沿触发）时，顶部横幅 + 提示音提醒。复用 2A 持久化与现有取数；纯逻辑可独立测。

## 目标
- 用户对某股设规则：`字段(价格/涨跌幅/综合分) 操作(>= / <=) 阈值`，可启用/停用。规则随配置持久化。
- 开「实时预警」后，程序每 60 秒对有启用规则的股票做一次分析，**边沿触发**（假→真才提醒，回落自动复位）地提醒，不刷屏、不弹模态。
- 监控仅在程序开启、未在分析/选股时进行；纯逻辑离线可测。

## 约束（沿用）
运行期纯标准库；纯逻辑无网络无 tkinter；既有 212 测试全绿；配置写 `%APPDATA%`（测试经 `STOCK_ADVISOR_CONFIG` 隔离）。

## 数据模型（models.py）
```python
@dataclass(frozen=True)
class AlertRule:
    code: str          # 规范化，如 "sh600519"
    field: str         # "price" | "change_pct" | "score"
    op: str            # ">=" | "<="
    threshold: float
    enabled: bool = True
```
`AppConfig` 增 `alerts: tuple[AlertRule, ...] = ()`（持久化）。

## 纯逻辑（alerts.py 新）
- `FIELD_LABELS = {"price":"价格","change_pct":"涨跌幅","score":"综合分"}`
- `evaluate_rule(rule, result) -> bool`：取 result 的 last/change_pct/score 比较；字段无效或 result 为 None → False。
- `rule_summary(rule) -> str`：如「SH.600519 价格 ≥ 1700」。
- `check_rules(rules, results_by_code, fired) -> tuple[list[AlertRule], set]`：**边沿触发纯函数**——返回（本次新触发的规则列表，更新后的 fired 集合）。条件为真且键不在 fired→触发并入集；条件为假→从集合移除（复位）。`results_by_code` 缺该 code 则跳过（不改状态）。

## store.py
`parse_config`/`config_to_dict` 增 `alerts`：逐条校验（field/op 合法、threshold 数值、code 经 normalize_symbol，非法跳过），序列化为 `[{code,field,op,threshold,enabled}]`。

## app.py
- 状态：`self.alerts: list[AlertRule]`（启动从配置载入）、`self.monitor_var: tk.BooleanVar(False)`、`self._fired: set`、`self.monitor_queue`、`self._monitoring=False`、`MONITOR_INTERVAL_MS=60000`。
- 工具栏加「预警」按钮 → 预警管理窗（Toplevel）：规则列表（代码/字段/操作/阈值/启用）+ 新增表单（代码输入、字段下拉、操作下拉、阈值、添加）+ 删除/清空；「实时预警」开关（Checkbutton）。增删改即存。
- 监控环：`_toggle_monitor`（开→启动 `_monitor_tick` 与 `_poll_monitor`）；`_monitor_tick`（main，after 自循环）：监控开且不忙且未在监控→起线程 `_monitor_worker(codes, level)` 对每个启用规则的去重 code 跑 `analyze_symbol`，结果入 `monitor_queue`；`_poll_monitor`（main，after 自循环）：drain 队列→`check_rules`→`_notify_alerts`。
- `_notify_alerts(newly)`：顶部预警横幅（专用 Label，平时隐藏；触发时显示规则摘要、红底）+ `root.bell()`；状态栏提示。
- 监控开关状态可不持久化（默认关，避免启动即联网）；规则持久化。

## 错误处理
单只分析失败：跳过该 code（不触发、不崩）。监控线程异常兜底为可读日志、不影响 UI。规则非法输入：管理窗内提示，不写入。

## 测试
- `test_alerts.py`：`evaluate_rule`（三字段 × 两操作 × 边界）；`check_rules` 边沿触发（首次触发、重复不再触发、回落复位、缺 result 跳过）；`rule_summary` 文本。
- `test_store.py`：alerts 往返、非法 field/op 过滤、code 规范化。
- `test_gui_layout.py`：预警管理窗可开；注入 results 调 `_check_or_notify` 不崩、横幅出现；监控开关切换不崩。
- 既有 212 全绿 + `py_compile` + 打包 `--self-test`（加 alerts 自检）+ GUI 实截预警窗/横幅。

## 不做（留后）
盘后/离线推送、声音自定义、跨进程常驻监控、按"建议动作变化"触发（v1 用综合分阈值近似）。
