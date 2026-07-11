# 界面整改 P3 · 布局重构 + 视觉统一 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把首屏"很深的单列堆叠 + 大片假占位"重排为**紧凑分区**:合并冗余面板、未分析时折叠占位、统一卡片/间距/字号、把每档"决策强度说明"显示出来——达到赏心悦目、交互舒适,同时保留全部现有功能。

**Architecture:** 不改核心逻辑与数据流,只动 `app.py` 的界面组装与绘制。抽取统一卡片构件与间距/字号常量(放 `theme.py`),消除首屏冗余(sparkline↔K线、4指标↔徽标指标、状态/摘要/概览三段)与空态假占位;结果面板未分析时折叠为单行提示,有结果再展开。子窗口(自选/对比/预警)共用骨架抽公共构件。可测的纯逻辑(空态/展开状态判定、卡片规格)抽成纯函数并单测;观感由控制器真机截图核验。

**Tech Stack:** Python 3.14 标准库、tkinter、`unittest`;真机 4K@250% 目视核验。

## Global Constraints

- 运行期只用 Python 标准库;不新增运行期依赖;不改业务逻辑/数据/配色语义(红=涨买、绿=跌卖)。
- 保留全部现有功能入口(个股/选股/自选/对比/预警/资金流/复制/导出/本金计算器/K线十字光标/五档光谱)。
- 复用 P2 的 `self._sc()`/`self._ui_scale`:新增像素量一律走 `self._sc()`,不得引入新的 96-DPI 固定像素。
- 每个 Task 结束前:`python -m unittest discover -s tests` 全绿 **且** `python -m py_compile main.py build_exe.py src/stock_advisor/*.py` 无错 **且** `python main.py --self-test` 退出 0。
- 纯逻辑用 TDD;GUI 用 headless 覆盖关键结构(区块存在、折叠/展开切换、控制栏含档位说明)。
- 每条 commit message 末尾附 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
- 分支 `feat/ui-overhaul-foundation`;不动 main。**每个改动面板的 Task,控制器在其后做一次真机截图核验**(观感是本阶段的验收标准)。

## 现状(P2 后)与目标结构

**现状首屏(自上而下,`_build_results_region` 约 1303+):** 页眉 → 控制栏(模式+决策强度)→ 输入区 → 结果工具条(加自选/复制/更多 + 状态/摘要/进度)→ 组合概览 `_overview_label`(单独一条)→ 预警横幅(隐藏)→ 结果表 `table_card` → 洞察条 `insight_strip`(`visual_summary_frame` 4指标 + `spectrum_frame` 光谱)→ 图形区 `visual_workspace`(`visual` | `kline_canvas`)→ 详情卡 `detail_panel` → 免责。未分析即渲染 `_draw_empty_visual`/`_draw_empty_kline`/`_draw_empty_spectrum_prompt` 约 600px 假占位(且 empty-visual 以 520 回退宽绘制→标签挤左、面板欠填充)。

**目标首屏:** 页眉(紧凑)→ 控制栏(模式 · 决策强度 · **档位说明**)→ 输入/操作区 → **状态条**(状态+摘要+概览合一)→ 结果表(有结果才展开)→ **结论卡**(方向/仓位/把握/波动 + 五档光谱,合一)→ **价格卡**(单一 K 线 + 判断拆解因子;删冗余 sparkline)→ 详情卡 → 免责。**未分析时结论卡/价格卡/详情占位折叠为单行提示**,有结果展开。

---

## File Structure

**修改:** `src/stock_advisor/app.py`(界面组装 `_build_*`、绘制 `_draw_*`、状态刷新、子窗口管理器);`src/stock_advisor/theme.py`(新增卡片/间距/字号常量);`tests/test_gui_layout.py`、`tests/test_ui_polish.py`(结构与纯逻辑测试)。
**可能新增:** `src/stock_advisor/view_layout.py`(可选,若卡片规格/折叠判定纯函数成规模)——否则并入 `layout.py`。

---

### Task 1: 空态折叠为单行提示(消除 ~600px 假占位 + 修 P2 遗留的标签挤左)

**Files:** Modify `app.py`(`_build_results_region`、`_safe_draw_visual`/`_safe_draw_kline`/`_safe_draw_spectrum`、`_reset_results`、新增折叠/展开辅助);Test `tests/test_gui_layout.py`。

**Interfaces:**
- Produces: `self._results_expanded: bool`;`_set_results_expanded(expanded: bool)`——False 时隐藏结论卡/价格卡/详情卡的重内容、显示一条 `ttk.Label`("输入代码后点『开始分析』，结果、图表与解读将在此展开");True 时展开并绘制。
- Consumes: 现有 `insight_strip`/`visual_workspace_shell`/`detail_panel_shell` 句柄。

- [ ] **Step 1: 失败测试** —— `tests/test_gui_layout.py`:构造 app,断言初始 `app._results_expanded is False` 且折叠提示 `winfo_manager()` 非空、结论/价格/详情重内容未 pack;调用 `_set_results_expanded(True)` 后反之。RED(方法/状态不存在)。
- [ ] **Step 2: 运行确认 RED** —— `python -m unittest tests.test_gui_layout -k expand -v`。
- [ ] **Step 3: 实现** —— 在 `_build_results_region` 建一个 `self.results_placeholder = ttk.Label(outer, text=..., style="Hint.TLabel")`;把结论卡/价格卡/详情卡的**展开**收敛到 `_set_results_expanded`:未分析/清空时 `pack_forget` 重内容并 `pack` 提示;首个结果到达时相反。`analyze`/`start_screen` 成功回调里 `_set_results_expanded(True)`;`_reset_results`/`clear` 里 `False`。空态不再调用 `_draw_empty_visual` 等(改为提示)。`__init__`/构建末尾设初始 `False`。
- [ ] **Step 4: 全绿 + 自检** —— `unittest discover`、`--self-test`、`py_compile`。
- [ ] **Step 5: 提交** —— `git commit -m "feat(ui): collapse pre-analysis placeholders into a single prompt"`。
- [ ] **Step 6: 控制器真机核验** —— 启动 GUI 截图:首屏无 600px 假占位、无标签挤左;分析后展开正常。

### Task 2: 合并洞察条为统一「结论卡」+ 删死变量

**Files:** Modify `app.py`(`_build_results_region` 的 `insight_strip`/`visual_summary_frame`/`spectrum_frame`、`_set_summary_metrics*`、`_draw_spectrum_strip`);删 `visual_summary_var`(未绑定任何控件)。Test `tests/test_gui_layout.py`。

**Interfaces:**
- Produces: 单一 `self.verdict_card`——一行四指标(方向/仓位/把握/波动)+ 其下/其右五档光谱条,同一张卡内统一描边与内边距。
- Consumes: 现有 `visual_metric_vars`、`_draw_spectrum_strip`。

- [ ] **Step 1: 失败测试** —— 断言 `verdict_card` 存在且含四个指标 `Label`(绑 `visual_metric_vars`)与 `spectrum_canvas`;断言 `hasattr(app, "visual_summary_var") is False`。RED。
- [ ] **Step 2: RED 确认**。
- [ ] **Step 3: 实现** —— 把 `visual_summary_frame`(四指标)与 `spectrum_frame`(光谱)并入一张 `verdict_card`(统一卡片构件,见 Task 5;此任务可先用现有描边法,Task 5 再统一);四指标一行、光谱条其下。删 `visual_summary_var` 定义与所有 `.set()`。保留 `visual_metric_vars` 绑定与 `_draw_spectrum_strip`。
- [ ] **Step 4: 全绿 + 自检**。
- [ ] **Step 5: 提交** —— `"refactor(ui): merge insight strip into a single verdict card; drop dead visual_summary_var"`。
- [ ] **Step 6: 真机核验**。

### Task 3: 价格可视化去重(删 sparkline,保留 K 线)

**Files:** Modify `app.py`(`_draw_visual`/`_draw_empty_visual` 的 sparkline 段、`_draw_sparkline`;`visual_workspace` 两栏)。Test `tests/test_ui_polish.py`/`test_gui_layout.py`。

**Interfaces:**
- Produces: `visual` 面板不再画"近期价格走势"小折线;价格走势唯一由右侧 `kline_canvas` 承担。`visual` 面板聚焦"判断拆解"因子条(+徽标/指标已在结论卡,故 `visual` 可收窄或并入结论卡——本任务先删 sparkline,`visual` 保留因子条)。
- Consumes: `_draw_factor_bars`、`kline_canvas`。

- [ ] **Step 1: 失败/断言测试** —— 断言 `_draw_visual` 不再创建带 `empty_visual_sparkline`/sparkline tag 的 item(或 `_draw_sparkline` 不再被调用)。RED。
- [ ] **Step 2: RED 确认**。
- [ ] **Step 3: 实现** —— 从 `_draw_visual`/`_draw_empty_visual` 删除 sparkline 标题+框+折线;`_draw_sparkline` 若无其它调用则删除;`visual` 面板与 `kline` 两栏的权重按内容重新分配(K 线信息密度更高,给更大宽度)。
- [ ] **Step 4: 全绿 + 自检**。
- [ ] **Step 5: 提交** —— `"refactor(ui): drop redundant sparkline; K-line is the single price chart"`。
- [ ] **Step 6: 真机核验**。

### Task 4: 状态/摘要/概览合并为单一状态条

**Files:** Modify `app.py`(`_build_results_region` 的 `status_var`/`summary_var`/`_overview_label`、相关刷新方法)。Test `tests/test_gui_layout.py`。

**Interfaces:**
- Produces: 一条 `self.status_bar`,左侧组合概览、右侧状态+进度;`summary_var` 并入(或作为概览的一部分)。保留 `status_var`/`overview_var` 变量以最小化改动,只是显示合并到一条。
- Consumes: `build_portfolio_overview`、进度条。

- [ ] **Step 1: 失败测试** —— 断言概览与状态在同一容器(`status_bar`)内;`_overview_label` 不再单独占一行(其 `master` 为 `status_bar`)。RED。
- [ ] **Step 2: RED 确认**。
- [ ] **Step 3: 实现** —— 把 `_overview_label`、`status_var` label、`summary_label`、`progress` 收敛进一条 `status_bar`(左概览、右状态/进度),删除单独的概览行。刷新逻辑不变(仍 set 同名变量)。
- [ ] **Step 4: 全绿 + 自检**。
- [ ] **Step 5: 提交** —— `"refactor(ui): unify status/summary/overview into one status bar"`。
- [ ] **Step 6: 真机核验**。

### Task 5: 统一卡片/间距/字号系统

**Files:** Modify `theme.py`(新增 `CARD_RADIUS`/`CARD_INNER_BG`/间距刻度 `GAP_*`/字号层级 `FONT_*` 常量)、`app.py`(抽 `_card(parent) -> (shell, body)` 构件替换散落的 `tk.Frame(bg=CARD_BORDER, padx=1)`+内层法;统一各卡内边距与卡间距;字号走层级常量)。Test `tests/test_ui_polish.py`。

**Interfaces:**
- Produces: `theme` 中的卡片/间距/字号常量(单一真源);`app._card(parent, inner_bg=CARD_INNER_BG) -> (shell, body)` 复用构件。
- Consumes: 现有 `CARD_BORDER`、`self._sc`。

- [ ] **Step 1: 失败测试** —— 断言 `theme` 暴露新常量;`app._card(root)` 返回 (shell, body) 且 body 背景为统一色。RED。
- [ ] **Step 2: RED 确认**。
- [ ] **Step 3: 实现** —— 在 `theme.py` 定义常量;在 `app.py` 加 `_card()` 并将主界面各卡(结论卡/价格卡/详情卡/表卡/输入卡/控制栏)与内层底色统一(消除 `#ffffff`/`#fbfdff`/`#e9f1fc` 混用);卡间距用统一刻度替换零散 `pady`。字号统一到层级常量(标题/正文/提示)。**逐卡替换、每卡后跑测试**,避免一次大改难回滚。
- [ ] **Step 4: 全绿 + 自检**。
- [ ] **Step 5: 提交** —— `"refactor(ui): unify card component, spacing scale, and font hierarchy"`。
- [ ] **Step 6: 真机核验**。

### Task 6: 控制栏显示「决策强度档位说明」(WS4-M2)

**Files:** Modify `app.py`(`_build_strength_bar`、`_on_level_change`);使用已存在但未绑定的 `self.level_label_var`(`level_summary()` 已算)。Test `tests/test_gui_layout.py`。

**Interfaces:**
- Produces: 控制栏内一个 `ttk.Label(textvariable=self.level_label_var)`,随档位切换显示"标准 · 买线+25/卖线−25 · 仓位≤60%"等。
- Consumes: 既有 `level_summary`、`level_label_var`、`_on_level_change`。

- [ ] **Step 1: 失败测试** —— 断言存在绑定 `level_label_var` 的可见 Label;切换 `level_var` 调 `_on_level_change` 后其文本随之更新(非空、含关键字)。RED(当前变量未绑定任何控件)。
- [ ] **Step 2: RED 确认**。
- [ ] **Step 3: 实现** —— 在 `_build_strength_bar` 决策强度选择器旁/下加一个 `Hint` 风格 Label 绑 `level_label_var`;确保 `_on_level_change` 里 `level_label_var.set(level_summary(level))` 被调用(若已 set 只需加控件)。文案随 DPI 无固定像素。
- [ ] **Step 4: 全绿 + 自检**。
- [ ] **Step 5: 提交** —— `"feat(ui): show decision-strength level summary in the control bar"`。
- [ ] **Step 6: 真机核验**。

### Task 7: 子窗口公共骨架 + 尺寸随 DPI(自选/对比/预警)

**Files:** Modify `app.py`(`open_watchlist_manager`/`open_comparison`/`open_alert_manager`、`_center_child_window`)。Test `tests/test_gui_layout.py`。

**Interfaces:**
- Produces: 公共 `_build_metric_strip(parent, specs)` 与 `_child_window(title, size)` 构件供三窗复用;子窗固定尺寸乘 `self._ui_scale`(经 `_sc`),对比窗多列改为可横向滚动或按 DPI 收敛列宽。
- Consumes: 三个子窗现有内容构建。

- [ ] **Step 1: 失败测试** —— 断言打开子窗后其请求尺寸随 `_ui_scale` 放大(如 720→`_sc(720)`);三窗的指标条由公共构件产出(结构一致)。RED。
- [ ] **Step 2: RED 确认**。
- [ ] **Step 3: 实现** —— 抽 `_build_metric_strip`/`_child_window`;三窗改用;尺寸经 `_sc`;对比窗 11 列加横向滚动条或收敛列宽。**逐窗替换、每窗后测试**。
- [ ] **Step 4: 全绿 + 自检**。
- [ ] **Step 5: 提交** —— `"refactor(ui): shared child-window skeleton; scale dialog sizes by DPI"`。
- [ ] **Step 6: 真机核验(逐个打开子窗截图)**。

---

## Self-Review

**1. Spec 覆盖(WS3):** 合并冗余(sparkline/K线 T3、4指标+光谱 T2、状态三段 T4)✓;折叠空态 T1 ✓(并修 P2 遗留标签挤左);统一卡片/间距/字号 T5 ✓;子窗口公共构件+DPI 尺寸 T7 ✓;档位说明显示(WS4-M2,UI 部分)T6 ✓。保留全部功能——每个 Task 只重排/合并,不删功能入口。
**2. 占位符扫描:** 无 TBD;每 Task 有 RED→GREEN→真机核验闭环。UI 重排以"目标结构 + 合并/删除/新增操作 + 断言"描述(界面重构宜结构化描述而非逐像素),观感由真机截图验收。
**3. 名称一致性:** `_results_expanded`/`_set_results_expanded`/`verdict_card`/`status_bar`/`_card`/`level_label_var`/`_build_metric_strip`/`_child_window` 在定义与引用处一致;复用 P2 的 `_sc`/`_ui_scale`。

**风险与顺序:** 先 T1(折叠,最大可见收益且解 P2 遗留)→ T2/T3/T4(合并冗余)→ T5(统一视觉,逐卡)→ T6(档位说明)→ T7(子窗口)。每 Task 独立可交付、测试全绿、真机核验后再进下一。观感不达标就迭代该 Task,不顺延。
