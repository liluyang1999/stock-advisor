# 股市锦囊 二期 2A — 自选股/持仓 + 横向对比 + K线 hover 设计

> 二期平台化主干：把"单次分析工具"升级为可保存、可对比的工作台。三件事：①自选股/持仓 + 本地持久化（含持仓成本与浮动盈亏）②多股横向对比 ③K线 hover 十字光标。沿用纯标准库 + 单 EXE。

## 目标

1. **自选股/持仓 + 持久化**：保存自选股；每只可选填**持仓成本价**与股数；分析后显示**浮动盈亏**。本金/档位/预设/自选随手保存，启动恢复。
2. **多股横向对比**：把已深度分析的股票放进一张对比表，含各项指标 + 当前档建议 + 各档强度提示 + 持仓盈亏。
3. **K线 hover 十字光标**：鼠标移动显示十字线 + 当根 OHLC/涨跌浮窗。

## 约束（沿用）

- 运行期纯标准库；构建期仅 PyInstaller；单 EXE。
- 纯逻辑模块无网络无 tkinter，独立可测。
- **用户配置写到 `%APPDATA%\股市锦囊\config.json`**：这是应用自身运行态（配置），非项目产物，符合写边界；测试经环境变量 `STOCK_ADVISOR_CONFIG` 指向临时文件。
- 配置损坏/不可写都回退默认且不崩溃；保存尽力而为、失败静默。
- 既有 **190 测试保持全绿**。

## 架构与文件

| 文件 | 职责 | 网络 | 可测 |
|---|---|---|---|
| `models.py` | 新增 `WatchItem(code, cost, shares)`、`AppConfig(watchlist, capital, level, preset)`、`ComparisonRow` | 否 | — |
| `store.py` **新** | `config_path()`、`parse_config(dict)`/`config_to_dict(cfg)`（纯）、`load_config(path)`/`save_config(path,cfg)`（I/O，鲁棒、原子写） | 否 | 纯函数 + 临时目录 |
| `compare.py` **新** | `build_comparison_rows(entries)`：组装对比行（含各档强度提示 + 浮动盈亏），按综合分排序，跳过无测量项 | 否 | 是 |
| `chart.py` | 新增 `nearest_index(x, layout)`：hover 命中最近蜡烛 | 否 | 是 |
| `app.py` | 自选股/持仓管理窗、横向对比窗、K线 hover、启动加载/变更即存 | — | 纯 builder + headless 冒烟 |

## 数据模型

```python
@dataclass(frozen=True)
class WatchItem:
    code: str            # 规范化形式，如 "sh600519"
    cost: float | None = None    # 持仓成本价（None=仅自选未持仓）
    shares: int | None = None    # 持仓股数（可选）

@dataclass(frozen=True)
class AppConfig:
    watchlist: tuple[WatchItem, ...] = ()
    capital: float = 100000.0
    level: int = 3
    preset: str = ""             # 空=用 PRESETS[0]

@dataclass(frozen=True)
class ComparisonRow:
    code: str; name: str; last: float; change_pct: float
    score: int; confidence: int; risk: str; position: int
    level_hint: str              # 各档强度提示（复用 flip_hint）
    cost: float | None; pl_pct: float | None; pl_amount: float | None
```

## store.py（持久化）

- `config_path() -> Path`：优先 `os.environ["STOCK_ADVISOR_CONFIG"]`；否则 `Path(os.environ.get("APPDATA") or Path.home()) / "股市锦囊" / "config.json"`。
- `parse_config(data) -> AppConfig`（纯、鲁棒）：`level` 夹到 1–5；`capital>0` 否则默认；`watchlist` 逐项用 `normalize_symbol` 校验（无效跳过）、按 code 去重、上限 100 项；`cost/shares` 为正才保留，否则置 None；`preset` 不在 PRESETS 内则置空。
- `config_to_dict(cfg) -> dict`：序列化（watchlist→[{code,cost,shares}]）。
- `load_config(path) -> AppConfig`：读文件→json→parse_config；**任何异常→默认配置**（不抛）。
- `save_config(path, cfg) -> bool`：建目录→写临时文件→`os.replace` 原子替换；**异常返回 False，不抛**。

## compare.py（对比）

`build_comparison_rows(entries) -> list[ComparisonRow]`，`entries` 为 `list[dict]`，每项含 `result: AnalysisResult`、`measurement: Measurement`、`risk: str`、`cost: float|None`、`shares: int|None`：

- 基本列取自 `result`（current 档已重判）。`level_hint = flip_hint(spectrum(measurement, 0))`（各档买/卖翻转点）。
- 浮动盈亏：`pl_pct=(last-cost)/cost*100`（cost 时），`pl_amount=(last-cost)*shares`（cost+shares 时），否则 None。
- 按 `score` 降序、再按 code 稳定排序。无 measurement 的项不传入（由 app 过滤）。

## app.py（界面接线）

- **启动**：`self.config_path=store.config_path()`；`cfg=store.load_config(...)`；应用 `capital_var/level_var/active_preset_key` 与 `self.watch: list[WatchItem]`；状态栏提示自选数量。
- **变更即存**（尽力而为）：本金失焦、档位变更、预设选择、自选增删 → 组装 `AppConfig` 调 `save_config`。
- **自选股/持仓**：结果区工具栏加「加入自选」「自选股」「横向对比」。
  - 加入自选：把当前结果代码并入 `self.watch`（已在则跳过）并保存。
  - 自选股管理窗（Toplevel，居中）：Treeview（代码/名称/成本/股数/浮动盈亏）+ 选中项编辑「成本」「股数」+ 「载入到输入框」「删除」「清空」「保存」。浮动盈亏在该股已分析时按现价算。
- **横向对比窗**（Toplevel，居中）：Treeview 列 `代码 名称 现价 涨跌 综合分 把握 风险 建议仓位 持仓成本 浮动盈亏 档位提示`；行按当前建议着色（复用 action_buy/sell 标签）；按综合分排序；无已分析股票时友好提示。
- **K线 hover**：`_draw_kline` 末尾存 `self._kline_state={bars,layout,top,ph,lo,hi}`；`<Motion>`→`nearest_index`→画竖/横十字线 + 浮窗（日期/开/高/低/收/涨跌%），打 `crosshair` 标签，移动先清除；`<Leave>` 清除。

## 错误处理

- 配置读坏/不可写：默认值 + 应用照常；保存失败静默（可选状态栏提示一次）。
- 对比无数据：提示"先分析一些股票再对比"。
- hover 无 K 线 / 空 layout：no-op。
- 成本/股数非法输入：管理窗内提示，不写入非法值。

## 测试

- `test_store.py`：缺省（文件不存在→默认）；往返保存/加载（临时目录，含 cost/shares）；损坏 JSON→默认；`parse_config` 夹紧 level、过滤非法 watchlist/cost、去重、preset 校验；`save_config` 原子写不破坏旧文件、不可写目录→False 不抛。
- `test_compare.py`：行含浮动盈亏（cost/shares 组合）、`level_hint` 来自 flip_hint、按 score 排序、无 measurement 由调用方过滤的契约。
- `test_chart.py`：`nearest_index` 取最近、边界（首/尾/空）。
- `test_app_helpers.py` / `test_gui_layout.py`：启动加载配置（env 指向临时文件）、加入自选去重并保存、对比窗可开且有行、hover 处理不崩、本金/档位变更触发保存。
- 既有 **190 全绿** + `py_compile` + 打包 `--self-test` + GUI 实截核验（自选/对比/hover）。

## 不做（留三期）

条件预警（2B）、资金流/基本面/板块广度（2C，需接口可行性研究）、对比窗的逐格五档彩色矩阵（先用文字档位提示）、持仓的历史成本/分批建仓。
