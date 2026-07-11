# 二期 2A — 自选股/持仓 + 横向对比 + K线 hover 实现计划

> TDD：先写失败测试再实现；每个任务以 `python -m unittest discover -s tests` 全绿为检查点（非 git 仓库）。
> 跨测试模块复用 helper 时用顶层导入（`from test_engine import ...` + 把 tests 目录加入 sys.path），匹配 discover 运行方式。

**Goal:** 把股市锦囊升级为可保存自选股/持仓、可横向对比、K线可 hover 的工作台。
**约束:** 运行期纯标准库；用户配置写 `%APPDATA%\股市锦囊\config.json`（测试经 `STOCK_ADVISOR_CONFIG` 指向临时文件）；既有 190 测试全绿。

---

### Task 1: 数据模型
- Modify `models.py`：`WatchItem(code:str, cost:float|None=None, shares:int|None=None)`、`AppConfig(watchlist:tuple[WatchItem,...]=(), capital:float=100000.0, level:int=3, preset:str="")`、`ComparisonRow(code,name,last,change_pct,score,confidence,risk,position,level_hint,cost,pl_pct,pl_amount)`。
- Test `tests/test_store.py`（部分）：构造三者。
- 检查点：全绿。

### Task 2: store.py 持久化
- Create `store.py`：`config_path()`、`parse_config(dict)->AppConfig`、`config_to_dict(AppConfig)->dict`、`load_config(path)->AppConfig`、`save_config(path,AppConfig)->bool`。
- Test `tests/test_store.py`：
  - 文件不存在→默认；往返（含 cost/shares）；损坏 JSON→默认；
  - `parse_config` level 夹 1–5、capital>0、watchlist 无效跳过+去重+上限、cost/shares 仅正、preset 校验；
  - `save_config` 原子写、不可写→False 不抛、旧文件不损坏。
- 检查点：全绿。

### Task 3: compare.py
- Create `compare.py`：`build_comparison_rows(entries:list[dict])->list[ComparisonRow]`，每 entry 含 result/measurement/risk/cost/shares；`level_hint=flip_hint(spectrum(measurement,0))`；浮动盈亏按 cost/shares；按 score 降序+code 稳定。
- Test `tests/test_compare.py`：盈亏计算（cost、cost+shares、无 cost）、排序、level_hint 文本。
- 检查点：全绿。

### Task 4: chart.nearest_index
- Modify `chart.py`：`nearest_index(x:float, layout:list[dict])->int`（最近 "x"，空→-1）。
- Test `tests/test_chart.py`：最近、首尾、空。
- 检查点：全绿。

### Task 5: app 启动加载 + 变更持久化
- Modify `app.py`：导入 store/compare/WatchItem/AppConfig；`__init__` 末尾 `self.config_path=store.config_path()`，`self._load_persisted()`（应用 capital/level/preset/watch）；`self._save_persisted()`（组装 AppConfig 调 save_config，尽力而为）；在 `_on_level_change`、`_select_preset`、本金失焦、自选增删后调用保存。`level_summary`/现有逻辑不变。
- Test `tests/test_app_helpers.py`：`_persisted_config()` 纯组装函数返回含当前 watch/capital/level/preset 的 AppConfig；`test_gui_layout.py`：env 指向临时文件时启动能加载 watchlist。
- 检查点：全绿。

### Task 6: app 自选股/持仓
- Modify `app.py`：工具栏「加入自选」「自选股」按钮；`add_to_watchlist()`（并入去重+保存）；`open_watchlist_manager()`（Toplevel：Treeview 代码/名称/成本/股数/浮动盈亏 + 成本/股数编辑 + 载入/删除/清空/保存）。纯 helper：`watchlist_rows(watch, results)`（格式化行 + 盈亏）。
- Test：`watchlist_rows` 纯函数（盈亏、未持仓显示 "—"）；GUI 冒烟：加入自选去重、管理窗可开。
- 检查点：全绿。

### Task 7: app 横向对比
- Modify `app.py`：「横向对比」按钮 → `open_comparison()`（Toplevel：Treeview 列见 spec，行按建议着色，按 score 排序；无数据提示）。用 `compare.build_comparison_rows` + `_comparison_entries()`（从 results/measurements/watch 成本组装）。
- Test：`_comparison_entries` 组装契约；GUI 冒烟：分析样例后对比窗有行。
- 检查点：全绿。

### Task 8: app K线 hover
- Modify `app.py`：`_draw_kline` 存 `self._kline_state`；`_on_kline_motion(event)`/`_on_kline_leave(event)` 画/清十字线 + OHLC 浮窗；`_build_results_region` 绑定 `<Motion>/<Leave>`。
- Test：GUI 冒烟：注入样例并 `_draw_kline` 后，模拟 Motion 事件不崩、产生 crosshair 元素。
- 检查点：全绿。

### Task 9: 收尾验证
- 全量 `unittest`；`py_compile`；`python main.py --self-test`；`python build_exe.py` → `dist\股市锦囊.exe --self-test`；GUI 实截核验自选/对比/hover（临时截图脚本，截完即删）。
