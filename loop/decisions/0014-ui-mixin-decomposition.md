# ADR-0014：StockAdvisorApp 的分解——按关注点拆为 app_* mixin 模块

- 状态：accepted
- 日期：2026-07-15

## 背景

ADR-0007 把 `src/` 分层成 `domain`/`data`/`services`/`ui` 四个子包，纯逻辑（引擎、策略、格式化、布局、校验）也确实都落在了各自的模块里。但 `ui/app.py` 本身没有被分解：它是一个 **3383 行、单一 `StockAdvisorApp` 类、131 个方法**的 god-class，占当时整个 `src/` 的 42%——四层分层干净，问题全部堆在 UI 这一个文件里。

131 个方法实际上是按功能聚簇的（窗口几何、预警/监控、图表渲染、选股、详情、自选/对比、样式、结果表），只是全部挤在一个类里，导致：定位一个功能要在 3000+ 行里翻找；任何 UI 改动的 diff 都落在同一个文件上；无法按关注点做局部审查。

同时 `app.py` 还兼作"再导出门面"：`main.py`、`ui/manual.py` 与测试套件从 `stock_advisor.ui.app` 导入主题常量、领域类型、视图助手、样例数据（共 72 个名字），使得 app.py 的导入区不能按"本模块是否真的使用"来清理。

约束：这是一个 Tkinter GUI，行为必须**逐字保持不变**（449 个产品测试中有约 187 个 GUI 测试直接实例化 `StockAdvisorApp` 并调用其方法）。

## 决策

1. **按关注点把方法整体搬到同包的 mixin 模块**，`StockAdvisorApp` 继承它们组合而成。共 8 个：`app_geometry`（WindowGeometryMixin，窗口居中/DPI/图标/几何）、`app_alerts`（AlertsMonitorMixin，预警管理/监控轮询/资金流）、`app_charts`（ChartRenderMixin，K线/光谱/可视化渲染与悬停）、`app_screener`（ScreenerMixin）、`app_detail`（DetailViewMixin，详情与帮助窗）、`app_watchlist`（WatchlistCompareMixin）、`app_styles`（StyleMixin，ttk 样式主题）、`app_results`（ResultsTableMixin，结果表与导出）。`ui/assets.py` 承载 `app_asset_path`，`ui/widgets.py` 承载 `StatefulToplevel`（见后果）。**方法逐字搬移**，不改任何方法体——每搬一块跑一次全量测试作为判据。
2. **`app.py` 保留"应用外壳 + 个股分析主流程"**：`__init__`、配置持久化、主窗/标签页/表头构建、个股分析工作流（analyze/worker/poll/outcome）、输入与档位控件、内容带与滚动。
3. **新增方法归入对应关注点的 mixin，不再退回 `app.py`。**
4. **mixin 的类型可见性用 `ui/_app_members.py`**：一个**仅供类型检查**的 `AppMembers` 类，声明共享的 `self` 表面（307 个名字）；各 mixin **仅在 `TYPE_CHECKING` 下**继承它（运行时基类是 `object`），因此运行期的组合与行为完全不变，而 pyright 能解析每个 mixin 里的 `self.<attr>`。共享表面若变化需重新生成该文件。
5. **拆除再导出门面**：`main.py`/`ui/manual.py`/测试改为从真源模块导入（主题常量→`ui/theme`、领域类型→`domain/models`、视图助手→`ui/view_*`、样例→`data/sample_data`），`app.py` 只保留自身定义的 `StockAdvisorApp`/`run_gui`。
6. **测试的 monkey-patch 遵循"在被查找处打桩"**：方法搬走后，其模块级依赖也随之移动，测试须 patch 该 mixin 模块（如 `app_screener.screen_and_recommend`、`app_results.filedialog`），而非 `app`。

## 替代方案

1. **维持 god-class 不动（拒绝）**：零风险，但 3383 行/131 方法的可维护性问题原样保留，且与 ADR-0007 已确立的"按关注点分模块"取向自相矛盾——四层分好了却在 UI 留一个 42% 的巨石。
2. **改为组合：把每块 UI 抽成独立的 Panel/View 部件类，由 App 持有（拒绝——现阶段）**：面向对象上更干净（真正的封装，而非共享 `self`），是 GUI 分解的理想终态。拒绝理由：它要求重新设计每块的 widget 归属、状态所有权与回调走向，等于重写 Tkinter 布局与事件线，而本次的硬约束是**行为逐字不变**、且 187 个 GUI 测试直接依赖 `StockAdvisorApp` 的方法表面；组合式重构无法做到"方法逐字搬移+每步全量测试"这种可验证的小步前进，风险与收益不成比例。留作重访触发。
3. **按文件行数机械切分（例如每 500 行一个模块）（拒绝）**：能立刻把文件变小，但切口不沿关注点，等于把一个巨石砸成几块碎石，定位功能反而更难，且切口会随行数变化漂移。
4. **（采用）按关注点搬为 mixin + `TYPE_CHECKING` 下的 `AppMembers` 类型基座 + 拆除再导出门面**：见"决策"。

## 后果

正面：

- `app.py` 由 **3383 → 1094 行、131 → 48 方法**（本 ADR 记录时的实测值），`ui/` 再无单一文件主导；每个关注点有独立、可单独审查的模块，UI 改动的 diff 落在对应模块上。
- 行为可证明未变：每次搬移后全量 449 产品测试 + `main.py --self-test` 全绿；一次真实的搬移缺陷（`@staticmethod` 装饰器未随方法一起搬走，导致 `_canvas_extent` 在 mixin 里失去 staticmethod、并在 app.py 留下孤儿装饰器）正是被这套判据当场抓出并修正的。
- 拆掉门面后，各模块的导入区第一次能按"本模块是否真的使用"清理，产品 ruff 归零。
- `AppMembers` 的 `TYPE_CHECKING` 基座把 mixin 分解引入的 554 条 pyright 假报（每个 mixin 单独看不到 `self.<attr>`）消掉，且不改变任何运行期语义。

负面/成本：

- mixin 共享 `self`，不是真正的封装：任一 mixin 都能读写其它关注点的状态，模块边界靠约定而非语言强制——这是相对"组合"方案的实质让步。
- `_app_members.py` 是**衍生产物**：共享表面变化时需要重新生成，若忘记更新会重新出现 pyright 假报（不影响运行）。
- `StatefulToplevel`（`ui/widgets.py`）把 4 个对话框往 Toplevel 上挂的 12 个动态属性集中声明在一个子类里，属于把 Tkinter 的动态属性习惯"就地正名"，并非真正按对话框分离。
- 测试的 monkey-patch 与模块布局耦合：方法搬家会让"在 app 上打桩"失效，需按第 6 条改到被查找处（本次已实测触发两处）。

## 回滚

不设整体回滚（把 8 个 mixin 合回 app.py 等于主动退回 god-class）。若某个关注点的切分被证明不合理（例如两块之间 `self` 交叉过密、反而更难读），正确做法是**调整该关注点的边界**（合并两个 mixin 或重划方法归属）并更新本 ADR 的第 1 条清单，而不是恢复单文件。若未来采纳替代方案 2（组合式部件类），那是对本 ADR 的**取代**而非回滚，须新增 ADR 说明迁移路径与如何保持 GUI 测试可用。停止条件：任何把 mixin 方法搬回 `app.py`、或让 `app.py` 重新充当再导出门面的改动，须在评审阶段阻断。

## 重访触发

- 若 GUI 从 Tkinter 迁移到 PySide6（ADR-0001 的既定方向），UI 分解须整体重做：届时应直接评估替代方案 2（组合式部件类），而不是把 mixin 结构照搬到 Qt。
- 若某个 mixin 再次膨胀到难以审查的规模（例如单模块重回千行级），须重新划分该关注点。
- 若 `_app_members.py` 的维护负担被证明高于它消除的 pyright 噪音（例如共享表面频繁变动），须重新评估是否改用更细的 Protocol 或就地类型标注。
- 若 `app.py` 剩余的"外壳 + 个股分析主流程"本身再次成为瓶颈（当前 48 方法），可考虑把个股分析工作流单独析出。

## 关联

REQ-028、AC-005、WI-000、EVD-LOOP-004；承接 ADR-0007（源码分层）；实现见 `ui/app.py` 与 `ui/app_*.py`、`ui/_app_members.py`、`ui/widgets.py`、`ui/assets.py`。
