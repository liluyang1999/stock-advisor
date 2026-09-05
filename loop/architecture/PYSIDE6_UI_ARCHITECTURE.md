# PySide6 UI 架构

## 主窗口

- `QMainWindow` 是唯一主外壳。
- 原生标题栏设置小图标和“股市锦囊”；central widget 不再绘制品牌头。
- 顶部 `QToolBar/QTabBar` 负责一级导航。
- `QStackedWidget` 承载五个主页面。
- `QStatusBar` 承载任务、数据源、时间、新鲜度、监控和免责声明。
- `saveState/restoreState` 只保存版本化 Dock/Toolbar 布局；失败回退默认。
- 工作模式与 L1–L5 均用 exclusive QButtonGroup 组合标准按钮；L1–L5 等宽且容器居中，不假设 PySide6 存在原生 segmented control。

## 页面布局

- 个股：结果主表 + K线/因子 + 结论 Dock。
- 筛选：策略 Dock + QTableView + 入选依据 Dock。
- 组合：列表 + 比较表/当前持仓检查器。
- 预警：规则表 + 规则编辑 Dock。
- 深度证据：回测/五档/资金流二级 tab。

QSplitter 设置初始比例、最小宽度和 stretch factor；用户比例可版本化保存。核心表格不得被辅助 Dock 压到不可用。

## 表格模型（**已出货形态**，与本节最初设想不同，理由见下）

五张表统一由 `qt_app/widgets/table_utils.make_readonly_table` 建出，**实际落地的是
`QStandardItemModel` + `QTableView`**，而不是本节最初设想的「自定义 `QAbstractTableModel` +
`QSortFilterProxyModel`」。这是一次**有意的偏离**，记录在此而不是让文档与代码各说各话：

- **不用 `QSortFilterProxyModel`**：代理排序会让模型真的搬行，而各页普遍拿 `index.row()` 当数据
  下标（删除选中行、按行取结果都靠它）。因此 Qt 内建排序刻意关闭，改由 `_HeaderSort` **只重排
  垂直表头的视觉次序**，模型行号原地不动——既得到点表头排序，又不破坏行号即下标的约定。
- **不用自定义 `QAbstractTableModel`**：`QStandardItemModel` 已能承载本节要求的全部角色，且逐格
  `setData` 天然支持「切档只改已有行」的就地刷新。曾经存在一个自定义 `ResultTableModel`，但它
  从未被任何页面实例化过（纯遗留物），已随本次复核删除，以免文档与追溯继续引用一段死代码。

仍然成立的约束（由 `make_readonly_table` / `make_row` 统一施加）：

- 角色齐备：DisplayRole、TextAlignmentRole（表头与格值同边）、ForegroundRole/BackgroundRole
  （按结论着色）、ToolTipRole（失败行全文原因）、以及**排序键 `Qt.UserRole`**。
- **排序键使用原始数值而非格式化字符串**：`make_row` 建行时就把 `cell_sort_value` 落进 UserRole，
  `_HeaderSort` 优先读它——`+9.50%` 按 9.5 排、风险按 RISK_ORDER 排，而不是按字面量。
- 名称左对齐，数字右对齐，状态居中；缺失值展示 `—`，底层保持 `None`。
- 列宽按声明宽度**比例**分摊余宽（`_ProportionalColumns`），复刻 Tk Treeview 的行为；等宽拉伸与
  「余宽全给最后一列」都试过，都不是基线的样子。
- 当前排序在模型值改变或新行到达后继续生效，逐格更新合并到下一轮 Qt 事件再排序；模型行号保持稳定。
- 复制与 CSV 遵从视觉行序，完整结果的解释扩展列仍保留。
- 行为测试覆盖：排序与显示值一致（含切档后）、空态提示、失败行不着色且带全文 tooltip。

## 字体

bootstrap：

1. 查询 `QFontDatabase.families()` 是否有 `Microsoft YaHei`。
2. `font = QFont("Microsoft YaHei")`，再调用 `font.setPointSizeF(10.5)` 与 `QApplication.setFont(font)`，精确保留小数点字号。
3. 创建 `QFontInfo(app.font())`，若实际 family 不匹配则阻止发布构建并在开发模式明确报错。
4. QSS 不再覆盖 font-family；只引用字号 token 或由对象字体角色设置。
5. 子窗口显式继承应用字体；自绘控件取 theme font role。

## 图表

- 复用 `chart.py` 纯几何。
- `QWidget.paintEvent` + QPainter 绘制 K 线、成交量、因子条和十字线。
- 当前缓存蜡烛几何（按数据与尺寸失效）和均线序列（按数据失效）；鼠标移动复用计算结果后重绘。
- 窄图读数省略时可通过 tooltip 读取完整 OHLC 与涨跌幅。
- 不把架构绑定到已弃用的 Qt Charts；Qt Graphs 需另行 spike。

## 状态

- loading：确定进度优先；不可确定才用 busy indicator。
- partial failure：行级失败，其他任务继续。
- degraded：琥珀信息条 + 保守判断说明。
- cancelled：等待安全点完成，不使用 QThread.terminate。
- stale：持续显示数据时间和 stale 标签。

## 可访问性

- 所有动作有 accessibleName/Description。
- 图标按钮有 tooltip；主操作保留文字。
- Tab 顺序与视觉顺序一致，焦点态清晰。
- 红绿语义配符号、正负号和文字。
- 200% DPI 不缩小字号或点击目标。

## 过渡与反馈

- 页面切换可用 120–180ms 的 QPropertyAnimation，但动画只作用于表现层，不参与任务状态机。
- hover/focus 过渡 80–120ms；loading、partial、degraded、cancelled、stale 必须先有文本/形状语义，再考虑动效。
- 尊重系统减少动画偏好；测试环境和性能门可关闭所有非必要动画以保持确定性。
