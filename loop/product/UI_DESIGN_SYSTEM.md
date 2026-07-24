# PySide6 UI 设计系统

## 视觉命题与信息层级

视觉命题：**安静、宽松、可信的 A 股研究工作台**。用米白底、深海军蓝墨色、单一交互蓝和严格网格建立秩序；红绿只表达 A 股涨跌/买卖语义，不承担品牌装饰。

- 首屏从可操作的工作区开始，不做营销 hero、欢迎横幅或重复品牌头。
- 视觉优先级固定为：当前任务与主动作 → 结果表/图表 → 证据与上下文 → 系统状态。
- 主工作区至少占可用宽度的 60%；导航和检查器退居次级，不能与数据争夺注意力。
- 默认无卡片化：优先使用留白、对齐、分区底色、分隔线和 QSplitter；只有本身可选择/展开/拖拽的对象才使用容器卡片。
- 一个区域只承担一个任务，删除重复标题、重复结论和不能帮助操作/监控/判断的说明。

## 字体

唯一 UI 字体族：`Microsoft YaHei`。

- QApplication 启动时创建 `QFont("Microsoft YaHei")`，调用 `setPointSizeF(10.5)` 后全局设置，避免小数点字号被整数构造参数截断。
- 用 QFontDatabase 确认字体存在，用 QFontInfo 确认实际解析结果。
- 不允许 Consolas、Microsoft YaHei UI 或控件级任意字体例外。
- 股票代码仍使用 Microsoft YaHei，通过字距、对齐和 tabular number 能力改善扫描。
- 自绘 QPainter、tooltip、菜单、对话框、图表标签和 HTML 说明书使用同一字体策略。

| Token | 建议值 |
|---|---:|
| `font.caption` | 9 pt |
| `font.body` | 10.5 pt |
| `font.control` | 10.5 pt |
| `font.section` | 13 pt / semibold |
| `font.page` | 17 pt / semibold |

## 尺寸

- 间距：8 / 12 / 16 / 24 / 32 DIP。
- 普通控件最小高度 32 DIP；主按钮 36 DIP；按钮最小宽度 88 DIP（短标签不缩成小方块，一排按钮轮廓齐整）。
- 表格标准行高 30 DIP；图标 16/18/20 DIP。
- 上述为**桌面鼠标操作**的常规尺寸（对齐 Windows Fluent 32 / macOS 28–32 / Material 36–40）。
  此前写的 44/48 DIP 是**触摸**目标口径（Apple HIG 44pt、Material 48dp），套在本应用上会让每个
  按钮变成大色块、一屏放不下几行表格；本应用无触摸形态，故按鼠标口径取值。
- 内容常规边距 28 DIP，最大宽度 1520 DIP，水平居中。
- 主窗口最小 1000×680 DIP；窄态通过滚动、折叠和 overflow，不压扁控件。

## 颜色

配色沿用 WI-023 之前的 Tkinter 版（WI-035 复刻）：暖灰纸面 + 暖白卡片 + 墨蓝指挥带，红涨绿跌为 A 股本土惯例。

- 纸面：`page #F4F2ED`；卡片：`card #FFFDF9`；卡片描边：`card_border #D9D5CC`；分隔线：`border_soft #E7E3DA`。
- 文字三档：`ink #17212B`（正文）、`ink_soft #344250`（次级/表头）、`muted_ink #626D7A`（说明与提示）。
- 交互蓝：`interactive #173A5E`；填色按钮上的文字用 `panel #FFFFFF`。
- A 股红（`up_red #B4232C`）：上涨、买入、正净流入；A 股绿（`down_green #167044`）：下跌、卖出、净流出。
- 琥珀（`amber #9A4B1F`）：警告、降级、需要留意；其浅底为 `danger_bg #FFF1E8`。
- 结论行底色：`buy_row #FBEFEF` / `sell_row #EDF7F1` / `hold_row #F5F3EE`；选中行 `selected_row #DBE7EE` 一律压过行底色。
- 墨蓝指挥带：`command_bg #142B3D`、`command_surface #203B4E`、`command_border #355267`、`command_ink #F7F5EF`、`command_muted_ink #B8C4CF`。
- 红绿必须同时配 `+/-`、文字、图标或形状。
- 正文对比度目标 ≥4.5:1；大文本/控件 ≥3:1。语义色对纸面/卡片的实测对比度：`up_red` 5.83:1 / 6.42:1，`down_green` 5.46:1 / 6.02:1，`amber` 5.52:1 / 6.08:1，`muted_ink` 4.71:1 / 5.18:1（方法与逐对实测见 `tokens.json.contrast`；只测界面真正会出现的前景/背景组合）。
- 状态 token：`hover #214D76`、`pressed #102D49`（老版 ACCENT_HOVER / ACCENT_PRESSED）、`disabled #89939D`（WCAG 对禁用态豁免对比度要求）、`selected_row #DBE7EE`、`gridline #E7E3DA`（分隔线，非文字）、`focus_ring #2472C8`（刻意区别于交互蓝，避免聚焦态按钮的焦点框与自身底色融合；作为非文字图形按 ≥3:1 判定）。
- 圆角 token：`border_radius_dip 4`（克制圆角，呼应"禁止过度圆角"不变量）。
- `tokens.json`（`loop/schemas/tokens.schema.json` 校验）是 WI-005/WI-035 的机器权威来源；本节数值须与其保持一致，颜色/间距/字号等如有变更以 `tokens.json` 为准。

## 组件

- 导航/主要动作/状态才配图标，使用单一 18–20 DIP 线性家族。
- 表格用 QTableView，数字右对齐、名称左对齐；不为每个格子做胶囊。
- 分区标题、留白和低对比分隔线表达层级；GroupBox 仅用于真实表单分组，避免网页卡片瀑布流。
- 焦点框清晰；图标按钮必须有 tooltip 和 accessibleName。
- 主要按钮保留短文字，刷新/关闭/更多可只用图标但必须可访问。

### 标准控件映射

- 一级导航：`QTabBar` 或 toolbar action，不复制页面标题。
- 工作模式：两项 exclusive `QButtonGroup`，与“工作模式”标签共享一条基线。
- 决策强度：五项等宽 exclusive `QButtonGroup`，整体按内容区中轴居中；下一行只显示一条居中摘要。
- 主操作：48 DIP 文字按钮（运行/开始分析）；停止、复制、导出、刷新使用图标 + 短文字或可访问图标按钮。
- 数据：`QTableView + QAbstractTableModel + QSortFilterProxyModel`；筛选器使用标准输入控件，不自造网页式下拉。
- 主从内容：`QSplitter`；可选上下文：`QDockWidget`；轻量状态：`QStatusBar`。

### 图标合同

运行期不依赖图标字体、emoji 或在线 CDN。WI-005 经许可证门禁选择一个线性 SVG 家族并将所需图标 vendored 到 Qt resources；同一动作只能有一个语义图标。建议语义为：分析=趋势线、筛选=漏斗、组合=公文包、预警=铃铛、回测=历史、运行=播放、停止=方形、复制=双页、导出=向下箭头、帮助=圆形问号。图标不能替代关键文字，也不得在每个表格单元格重复装饰。

### 动效合同

- 页面切换只做 120–180ms 透明度/轻位移过渡；控件 hover/focus 80–120ms。
- 运行状态用确定进度或克制 busy indicator；禁止循环漂浮、弹跳或装饰性自动动画。
- 动效不得阻塞输入、改变数据时序或成为理解状态的唯一线索；系统减少动态效果时直接关闭非必要动画。

## 不变量

1. 原生标题栏只出现一次应用身份。
2. 内容区不出现第二个 Logo、产品名或营销副标题。
3. 决策强度五档等宽；整组与第二行摘要以窗口中轴居中。
4. 主状态、数据源、更新时间和监控放 QStatusBar，减少顶部文字。
5. 禁止渐变炫光、玻璃拟态、霓虹、过度圆角和图标汤。

## 验证矩阵

- 1366×768 @ 100%。
- 1920×1080 @ 125%、150%。
- 2560×1440 @ 200%。
- 长中文、缺失数值、负 PE、10+ 位价格、30 只输入、5000 行表格。
- 空态、加载、成功、部分失败、降级、停止、全失败。
