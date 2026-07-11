# 界面整改 P4 · 功能补漏(查缺补漏)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 修复用户可见的功能瑕疵与文档漂移(WS4):选股参数上下限交叉、说明书"滑杆"误称、免责声明两套措辞、资金流线程越线、预警字段显英文键、取整口径不一;并**重新生成把红绿买卖讲反的技术报告 HTML**。不改核心决策模型。

**Architecture:** 纯逻辑用 TDD(先失败测试);文案/文档为文本修正,以 grep + 现有测试守门。运行期纯标准库不变。

## Global Constraints
- 运行期只用 Python 标准库;不改核心决策模型/数据源/预设算法语义;配色 A 股本土:红=涨/买、绿=跌/卖。
- 立场:不构成投资建议——统一为单一权威免责文案。
- 每个 Task 结束:`python -m unittest discover -s tests` 全绿 + `python -m py_compile main.py build_exe.py src/stock_advisor/*.py` + 相关时 `python main.py --self-test` 退出 0。
- 每条 commit 末尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。分支 `feat/ui-overhaul-foundation`,不动 main。

---

### Task 1: 选股参数上下限交叉校验(M3)

**Files:** Modify `src/stock_advisor/presets.py`(`apply_tunables` ~148-166);Test `tests/test_presets.py`。
**问题:** `apply_tunables` 只把每个可调项夹到自身 `[min,max]`,不校验成对边界。`momentum_strong` 的 `change_pct_min` 可调到 10 而固定 `change_pct_max=7`;`activity_turnover` 的 `turnover_min`(1-20)/`turnover_max`(10-60)可交叉 → `screener._in_range` 恒空 → 界面弹"没有符合条件…请放宽筛选"误导。

- [ ] **Step 1:** 写失败测试:`apply_tunables` 遇成对下限>上限时应抛可展示的 `ValueError`(或返回明确标记),文案指出是"下限高于上限"而非泛泛;覆盖 `change_pct_min>change_pct_max`(含固定上限)与 `turnover_min>turnover_max`。RED。
- [ ] **Step 2:** 运行确认 RED。
- [ ] **Step 3:** 实现:在 `apply_tunables` 内,对每组"同一指标的 min/max 边界"(可调 vs 可调,或可调 vs 固定 criterion)做协同校验;`min>max` 时抛 `ValueError(f"『{标签}』下限 {lo} 高于上限 {hi}，请调低下限或调高上限。")`。GUI 的 `start_screen` 已 try/except 展示 ValueError 文案(核对),故不必改 UI。识别成对边界的映射写清楚(change_pct_min↔change_pct_max、turnover_min↔turnover_max 等,按各预设 tunables 与 criteria 实际字段)。
- [ ] **Step 4:** 全绿 + self-test。
- [ ] **Step 5:** 提交 `fix(screener): reject crossed tunable bounds with a clear message`。

### Task 2: 说明书"滑杆"改文案(M1)+ 免责声明统一(M4)

**Files:** Modify `src/stock_advisor/manual.py`(~89-91)、`README.md`;免责:`src/stock_advisor/policy.py`(`_DISCLAIMER` :28)与权威常量。Test 现有 `tests/test_manual.py` 等。
**问题:** manual/README 把五档分段按钮说成"滑杆·拖动";免责有两套措辞(`theme.DISCLAIMER` 全文 vs `policy._DISCLAIMER` 短句)。

- [ ] **Step 1:** 写/改测试:`build_manual_text()` 不含"滑杆"/"拖动",含"分段按钮"/"点选";免责一致性——`policy` 追加到每条决策 risks 的免责句与权威文案措辞一致(同一核心句)。RED。
- [ ] **Step 2:** RED 确认。
- [ ] **Step 3:** 实现:`manual.py` 把"滑杆"→"分段按钮/档位按钮","拖动滑杆"→"点选档位";`README.md` 同改。免责:定义单一权威短句常量(放 `models.py` 或新 `constants` 叶子——**不要让 `policy.py` import UI 层 `theme`**;若 `theme.DISCLAIMER` 是全文页脚,则新增一个核心短句常量供 policy 复用,并让全文页脚以其为基或措辞对齐),`policy._DISCLAIMER` 引用它。
- [ ] **Step 4:** 全绿 + self-test。
- [ ] **Step 5:** 提交 `fix(docs): correct slider->segmented-button wording; unify disclaimer`。

### Task 3: 资金流 worker 改队列回主线程(M6)

**Files:** Modify `src/stock_advisor/app.py`(`_fund_flow_worker` ~ `self.root.after(0, ...)`、`show_fund_flow`、新增/复用队列轮询)。Test `tests/test_gui_layout.py`。
**问题:** `_fund_flow_worker`(daemon 线程)直接 `self.root.after(0, lambda...)` 回主线程,违反项目"经队列回主线程"约定(其余三 worker 皆队列+轮询)。

- [ ] **Step 1:** 写测试:资金流结果经一个队列(如 `self.fund_flow_queue`)+ 主线程轮询消费,worker 不直接触碰 Tk(可断言 worker 只 put 队列;或轮询方法存在并从队列取)。RED。
- [ ] **Step 2:** RED 确认。
- [ ] **Step 3:** 实现:仿 `_poll_monitor`,worker 把 `(symbol,name,flow_or_error)` 入队,主线程 `after(interval,...)` 轮询消费并渲染;移除 worker 内 `root.after`。保留降级安全(取不到→提示稍后重试)。
- [ ] **Step 4:** 全绿 + self-test。
- [ ] **Step 5:** 提交 `fix(app): route fund-flow worker result through a queue, not after()`。

### Task 4: 预警字段下拉显中文(L1)+ 取整口径统一(L2)

**Files:** Modify `src/stock_advisor/app.py`(`open_alert_manager` 字段下拉 ~ `values=list(FIELD_LABELS)`)、`src/stock_advisor/engine.py`(:199 `int(objective*0.75)`)vs `policy.py`(:96-97 `int(round(...))`)。Test `tests/test_alerts.py`/`test_engine.py`/`test_policy.py`。
**问题:** 预警"字段"下拉显示英文键 price/change_pct/score;`engine` 小样本降权用截断、`policy` 用四舍五入,破坏"L3=客观综合分"文档承诺(边界差 1)。

- [ ] **Step 1:** 写测试:字段下拉展示 `FIELD_LABELS` 中文值,保存映射回键(`AlertRule.field` 仍是键);取整——构造 base+penalty=26 且历史<30 天,断言 `engine` 客观分 == `policy` L3 分。RED。
- [ ] **Step 2:** RED 确认。
- [ ] **Step 3:** 实现:下拉 `values=list(FIELD_LABELS.values())`,添加规则时把中文标签映射回键;`engine.py:199` 与 `policy.py:96-97` 统一取整(择一,推荐 `int(round(...))`),保证 L3 一致。
- [ ] **Step 4:** 全绿 + self-test。
- [ ] **Step 5:** 提交 `fix: show Chinese alert field labels; unify rounding so L3 == objective score`。

### Task 5: 重新生成技术报告 HTML(把红绿讲反的那份)

**Files:** Rewrite `docs/stock_advisor_technical_stack_report.html`。
**问题(高):** 该已交付报告把买卖配色**讲反**("买入偏绿/卖出偏红",与 A 股本土及全程序相反),且旧名"A股策略助手"、旧路径 `outputs/`、只讲单一 ±25 阈值、缺 8 个模块、把已实现功能当"未来扩展"。用户已选**按现状重新生成**。

- [ ] **Step 1:** 通读现有报告,列出所有过时/错误点(配色、名称、五档决策强度、每档仓位上限、完整模块清单 `theme/layout/formatting/view_text/view_format/sample_data/input_validate/screener/presets/policy/backtest/chart/compare/alerts/store/…`、`dist/` 路径)。数据层回退链章节仍准确可保留。
- [ ] **Step 2:** 重写为对应**当前实现**的报告:新名"股市锦囊";**正确 A 股配色(红=涨/买、绿=跌/卖)**;五档决策强度 + 每档买卖线/仓位上限;完整模块架构;`dist/股市锦囊.exe` 交付;去掉"未来扩展"里已实现项。顶部注明"对应 2026-07 当前版本"。样式自包含(内联 CSS),中文,与 `dist/使用说明.html` 立场一致(不构成投资建议)。
- [ ] **Step 3:** 校验:浏览器可打开无误(或 `python -c` 粗校 HTML 结构);`grep` 确认无"A股策略助手"/"outputs/"/买入偏绿 残留。
- [ ] **Step 4:** 提交 `docs: regenerate technical report for current impl with correct A-share colors`。

---

## 说明(本计划外、后续可选)
- **P3 T5(卡片/间距/字号统一)、T7(子窗口公共骨架 + DPI 尺寸)**:视觉打磨,已记入 P3 计划,边际收益较低,置于功能补漏之后。
- **WS5b 子窗口 Mixin(app.py 进一步瘦身)**:代码健康,低风险高收益顺序中排最后。
- **打包自验**:`build_exe.py` → `dist\股市锦囊.exe --self-test` 退出 0(`--add-data` 分隔符已在 P1 修);构建产物已 gitignore。

## Self-Review
- WS4 覆盖:M3→T1、M1+M4→T2、M6→T3、L1+L2→T4、危险报告→T5。均有 RED→GREEN 或 grep 守门。
- 无占位符;`policy` 不 import UI 层(免责常量放叶子);取整统一后 L3 恒等客观分;字段键/标签双向映射保持 `AlertRule.field` 语义不变。
