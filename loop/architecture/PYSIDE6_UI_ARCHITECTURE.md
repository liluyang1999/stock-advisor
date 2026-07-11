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

## 表格模型

- `QAbstractTableModel` 提供 DisplayRole、TextAlignmentRole、ForegroundRole、ToolTipRole、AccessibleTextRole。
- `QSortFilterProxyModel` 做排序/过滤；排序键使用原始数值而非格式化字符串。
- 名称左对齐，数字右对齐，状态居中。
- 缺失值展示 `—`，底层保持 `None`。
- 增量更新使用正确的 begin/endInsertRows 或 dataChanged 范围。
- 用 QAbstractItemModelTester 和行为测试验证模型一致性。

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
- 缓存静态背景层，鼠标移动仅重绘 crosshair/tooltip 受影响区域。
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
