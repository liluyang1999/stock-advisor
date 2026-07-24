"""把 `tokens.json` 的设计 token 生成为应用级 QSS（WI-005 / WI-035 / REQ-014/015/017/018）。

每个颜色与尺寸都取自 `DesignTokens`，QSS 里不出现任何字面色值——这样 tokens.json 始终是
唯一真源，`test_qt_theme.py` 会断言 QSS 中的每个十六进制色都能在 tokens 中找到。

**视觉基线是 WI-023 之前的 Tkinter 版**（WI-035）。老版的结构语言只有三层，QSS 按它重建：

1. **暖灰纸面**（page `#f4f2ed`）承载一切，不用纯白——长时间盯盘时纯白更累。
2. **暖白卡片**（card `#fffdf9`）+ 1px 暖灰描边（card_border）。老版每张卡都是"外层 Frame 涂
   描边色 + padx/pady=1 + 内层 Frame 涂填充色"这一招手搓出来的；Qt 侧用 `QFrame[role="card"]`
   的 border + background 一句话表达同一件事。
3. **墨蓝指挥带**（command_*）——老版最强的视觉锚点：工作模式与决策强度坐在这条深色带里，
   与纸面形成明确的"控制区 vs 内容区"分工。

**为什么不再写 `QWidget { background-color: ... }`**：那条规则会命中每一个 QWidget，包括卡片、
表格视口和各种内部子部件，于是"卡片"永远被刷成纸面色、描边也无从显现——这正是重构前整个界面
看起来是一片平摊的直接原因。现在底色只落在真正的顶层容器（QMainWindow/QDialog/页签面板）上，
其余容器保持透明、透出父级底色，需要自己一层面的（卡片、指挥带）再显式声明。

同理，旧版的 `*:focus { border: 2px solid ... }` 是通配选择器：它给**任何**获得焦点的部件加 2px
边框，连容器和表格都不放过，而边框会改变盒模型 → 每次焦点移动都引发布局抖动。现在焦点态只落在
真正可聚焦的控件上，且用 border-color 替换而非新增边框，尺寸不变。
"""

from __future__ import annotations

from .tokens import DesignTokens


def build_qss(tokens: DesignTokens) -> str:
    """构造应用级样式表。选择器覆盖外壳、指挥带、卡片、按钮、表格、输入、滚动条与焦点态。"""

    c = tokens.colors
    s = tokens.state_colors
    f = tokens.surfaces
    family = tokens.font_families[0]
    radius = tokens.border_radius_dip
    ctrl_h = tokens.control_min_height_dip
    primary_h = tokens.primary_control_height_dip
    btn_w = tokens.button_min_width_dip
    row_h = tokens.table_row_height_dip
    pad_s, pad_m, pad_l = tokens.spacing_dip[0], tokens.spacing_dip[1], tokens.spacing_dip[2]
    caption_pt = tokens.font_points["caption"]
    body_pt = tokens.font_points["body"]
    section_pt = tokens.font_points["section"]

    return f"""\
/* 由 qt_app/theme/qss.py 从 loop/product/tokens.json 生成——勿手改，改 tokens.json */

/* 字体与文字色可以安全地全局继承；底色不行（见模块文档），故这里刻意不设 background。 */
QWidget {{
    color: {c["ink"]};
    font-family: "{family}";
    font-size: {body_pt}pt;
}}

/* 只有真正的顶层容器铺纸面色，其余容器保持透明、透出父级。 */
QMainWindow, QDialog {{
    background-color: {c["page"]};
}}
QWidget[role="page"] {{
    background-color: {c["page"]};
}}

QToolTip {{
    background-color: {f["command_bg"]};
    color: {f["command_ink"]};
    border: 1px solid {f["command_border"]};
    padding: {pad_s}px;
}}

/* --- 文字层级：沿用老版 ttk 的 Title/Subtitle/SectionTitle/Hint 四档 --- */
QLabel {{
    background-color: transparent;
}}
QLabel[role="title"] {{
    font-size: {tokens.font_points["page"]}pt;
    font-weight: bold;
    color: {c["ink"]};
}}
QLabel[role="section"] {{
    font-size: {section_pt}pt;
    font-weight: bold;
    color: {c["ink"]};
}}
QLabel[role="hint"] {{
    font-size: {caption_pt}pt;
    color: {c["muted_ink"]};
}}
QLabel[role="summary"] {{
    font-weight: bold;
    color: {c["ink_soft"]};
}}
/* 概览条：老版 Overview.TLabel——浅控件底 + 内缩，横贯结果区上沿 */
QLabel[role="overview"] {{
    background-color: {f["control"]};
    color: {c["ink_soft"]};
    font-weight: bold;
    padding: {pad_s}px {pad_m}px;
    border-radius: {radius}px;
}}
/* 预警横幅：老版 alert_banner，仅在规则触发时出现 */
QLabel[role="alert"] {{
    background-color: {f["danger_bg"]};
    color: {c["amber"]};
    font-weight: bold;
    border: 1px solid {c["amber"]};
    border-radius: {radius}px;
    padding: {pad_s}px {pad_m}px;
}}
/* 空态里的步骤药丸：01 输入标的 → 02 调整强度 → 03 阅读结论与依据 */
QLabel[role="step"] {{
    background-color: {f["accent_soft"]};
    color: {c["interactive"]};
    font-weight: bold;
    border-radius: {radius}px;
    padding: {pad_s}px {pad_m}px;
}}
QLabel[role="value"] {{
    font-size: {section_pt}pt;
    font-weight: bold;
    color: {c["ink"]};
}}

/* --- 卡片：老版"1px 描边 Frame 套填充 Frame"的等价物 --- */
QFrame[role="card"] {{
    background-color: {f["card"]};
    border: 1px solid {f["card_border"]};
    border-radius: {radius}px;
}}
/* 卡片内的分隔线（老版 BORDER_SOFT 的 1px Frame） */
QFrame[role="divider"] {{
    background-color: {f["border_soft"]};
    border: none;
}}
/* 卡片表头条：标题 + 说明，坐在卡片顶部 */
QWidget[role="card-head"] {{
    background-color: transparent;
}}

/* --- 指挥带：老版最强的视觉锚点，控制区与内容区在此分界 --- */
QWidget[role="command"] {{
    background-color: {f["command_bg"]};
    border: 1px solid {f["command_border"]};
    border-radius: {radius}px;
}}
QWidget[role="command"] QLabel {{
    color: {f["command_muted_ink"]};
    font-weight: bold;
    background-color: transparent;
}}
QWidget[role="command"] QLabel[role="hint"] {{
    color: {f["command_muted_ink"]};
    font-weight: normal;
    font-size: {body_pt}pt;
}}

/* 指挥带里的分段按钮：五档一字排开，选中段翻成暖白纸面色（老版的"反相亮药丸"） */
QPushButton[role="segment"] {{
    background-color: {f["command_surface"]};
    color: {f["command_muted_ink"]};
    border: none;
    border-radius: 0px;
    font-weight: bold;
    min-height: {ctrl_h}px;
    min-width: 0px;
    padding: 0px {pad_l}px;
}}
QPushButton[role="segment"]:hover {{
    background-color: {f["command_border"]};
    color: {f["command_ink"]};
}}
QPushButton[role="segment"]:checked {{
    background-color: {f["card"]};
    color: {f["command_bg"]};
}}

/* --- 页签：QTabWidget 承载五个功能页 --- */
QTabWidget::pane {{
    background-color: {c["page"]};
    border: none;
    top: -1px;
}}
QTabBar {{
    background-color: transparent;
    qproperty-drawBase: 0;
}}
QTabBar::tab {{
    background-color: {f["control"]};
    color: {c["muted_ink"]};
    font-weight: bold;
    border: 1px solid {f["card_border"]};
    border-bottom: none;
    /* 顶边统一 2px：未选中与描边同色，选中翻成口音色顶线。两态等宽，切换不引起文字位移。 */
    border-top: 2px solid {f["card_border"]};
    border-top-left-radius: {radius}px;
    border-top-right-radius: {radius}px;
    min-height: {ctrl_h}px;
    padding: 0px {pad_l}px;
    margin-right: 2px;
}}
QTabBar::tab:hover {{
    background-color: {f["accent_soft"]};
    color: {c["interactive"]};
}}
QTabBar::tab:selected {{
    background-color: {f["card"]};
    color: {c["interactive"]};
    border-top-color: {c["interactive"]};
}}

/* --- 按钮：老版 Primary / Action / Quiet 三族 ---
   尺寸取桌面鼠标操作的常规值（tokens 里 32 / 主按钮 36），不是触摸目标的 44/48——后者套在
   桌面应用上会让每个按钮都变成一块大色块。`min-width` 让「停止」「添加」这类短标签不至于
   缩成小方块，与长标签并排时一排按钮的轮廓是齐整的。 */
QPushButton {{
    background-color: {f["control"]};
    color: {c["ink_soft"]};
    border: 1px solid {f["card_border"]};
    border-radius: {radius}px;
    min-height: {ctrl_h}px;
    min-width: {btn_w}px;
    padding: 0px {pad_m}px;
}}
QPushButton:hover {{
    background-color: {f["control_hover"]};
    border-color: {c["interactive"]};
    color: {c["interactive"]};
}}
QPushButton:pressed {{
    background-color: {f["accent_soft_hover"]};
}}
QPushButton:disabled {{
    background-color: {f["control_disabled"]};
    color: {s["disabled"]};
    border-color: {f["border_soft"]};
}}
QPushButton[role="primary"] {{
    background-color: {c["interactive"]};
    color: {c["panel"]};
    border: 1px solid {c["interactive"]};
    font-weight: bold;
    min-height: {primary_h}px;
    padding: 0px {pad_l}px;
}}
QPushButton[role="primary"]:hover {{
    background-color: {s["hover"]};
    border-color: {s["hover"]};
    color: {c["panel"]};  /* 覆盖普通按钮 hover 的口音色字，实心按钮上必须仍是白字 */
}}
QPushButton[role="primary"]:pressed {{
    background-color: {s["pressed"]};
    border-color: {s["pressed"]};
}}
QPushButton[role="primary"]:disabled {{
    background-color: {s["disabled"]};
    color: {f["surface_alt"]};
    border-color: {s["disabled"]};
}}
/* 紧凑分段（详情章节导航 结论/依据/风险/操作）：短标签，不吃按钮的 88px 最小宽度，
   否则四个两字标签会摊成一条 350px 的长带。选中态用浅口音底，坐在暖白卡片上而非墨蓝带里。 */
QPushButton[role="chip"] {{
    background-color: {f["control"]};
    color: {c["muted_ink"]};
    border: 1px solid {f["card_border"]};
    border-radius: 0px;
    min-width: 0px;
    padding: 0px {pad_m}px;
}}
QPushButton[role="chip"]:hover {{
    background-color: {f["accent_soft"]};
    color: {c["interactive"]};
}}
QPushButton[role="chip"]:checked {{
    background-color: {f["accent_soft"]};
    color: {c["interactive"]};
    border-color: {c["interactive"]};
    font-weight: bold;
}}

/* 单选组的成员按钮（策略预设六宫格）：未选中坐在卡片上要安静——暖白底 + 卡片描边，
   不再是六块灰色板砖；选中段仍翻成实心口音色，与决策强度分段同语言。 */
QPushButton[role="toggle"] {{
    background-color: {f["card"]};
    color: {c["ink_soft"]};
}}
QPushButton[role="toggle"]:hover {{
    background-color: {f["accent_soft"]};
    color: {c["interactive"]};
}}
QPushButton[role="toggle"]:checked {{
    background-color: {c["interactive"]};
    color: {c["panel"]};
    border-color: {c["interactive"]};
    font-weight: bold;
}}

/* 开关按钮（深度分析 开/关、实时预警 开/关）：它是状态开关不是主动作，"开"用浅口音底 +
   口音描边表达，与实心的主按钮（开始选股/添加）拉开身份——此前两者同为实心墨蓝，
   一排里"哪个是动作、哪个是状态"分不出来。 */
QPushButton[role="switch"]:checked {{
    background-color: {f["accent_soft"]};
    color: {c["interactive"]};
    border: 1px solid {c["interactive"]};
    font-weight: bold;
}}
QPushButton[role="switch"]:checked:hover {{
    background-color: {f["accent_soft_hover"]};
    color: {c["interactive"]};
}}

QToolButton {{
    background-color: {f["control"]};
    color: {c["ink_soft"]};
    border: 1px solid {f["card_border"]};
    border-radius: {radius}px;
    min-height: {ctrl_h}px;
    min-width: {btn_w}px;
    padding: 0px {pad_l}px 0px {pad_m}px;
}}
QToolButton:hover {{
    background-color: {f["control_hover"]};
}}
QToolButton::menu-indicator {{
    subcontrol-position: right center;
    subcontrol-origin: padding;
    right: {pad_s}px;
}}

/* --- 输入控件 --- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {f["card"]};
    color: {c["ink"]};
    border: 1px solid {f["card_border"]};
    border-radius: {radius}px;
    selection-background-color: {s["selected_row"]};
    selection-color: {c["ink"]};
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    min-height: {ctrl_h}px;
    padding: 0px {pad_s}px;
}}
QPlainTextEdit, QTextEdit {{
    padding: {pad_s}px;
}}
/* 代码输入框沿用老版：Consolas 等宽 + 略深的 surface_alt 底，与普通输入框区分开 */
QPlainTextEdit[role="symbols"] {{
    background-color: {f["surface_alt"]};
    font-family: "Consolas";
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {f["control_disabled"]};
    color: {s["disabled"]};
}}
QComboBox::drop-down {{
    border: none;
    width: {pad_l}px;
}}
QComboBox QAbstractItemView {{
    background-color: {f["card"]};
    color: {c["ink"]};
    border: 1px solid {f["card_border"]};
    selection-background-color: {f["accent_soft"]};
    selection-color: {c["interactive"]};
}}
/* 微调按钮：给一条左分隔线把按钮区从输入区里划出来，宽度放到 16px 让箭头不挤在边上。 */
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {f["control"]};
    border: none;
    border-left: 1px solid {f["border_soft"]};
    width: {pad_l}px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {f["control_hover"]};
}}

/* --- 表格：表头自成一色，行高按 token，选中行浅蓝 --- */
QTableView {{
    background-color: {f["card"]};
    alternate-background-color: {f["card"]};
    gridline-color: {f["border_soft"]};
    selection-background-color: {s["selected_row"]};
    selection-color: {c["ink"]};
    border: 1px solid {f["card_border"]};
    border-radius: {radius}px;
    /* 去掉当前单元格的焦点虚框：它按 style 的高亮色逐格描边，在有行底色的表里会显示成
       每个单元格左侧一道竖杠，看着像分隔线画错了位置。 */
    outline: none;
}}
QTableView::item {{
    padding: 0px {pad_s}px;
    border: none;
}}
QTableView::item:selected {{
    background-color: {s["selected_row"]};
    color: {c["ink"]};
}}
QHeaderView {{
    background-color: {f["table_header"]};
}}
QHeaderView::section {{
    background-color: {f["table_header"]};
    color: {c["ink_soft"]};
    font-weight: bold;
    border: none;
    border-right: 1px solid {f["border_soft"]};
    border-bottom: 1px solid {f["card_border"]};
    min-height: {ctrl_h}px;
    padding: 0px {pad_m}px;
}}
QHeaderView::section:hover {{
    background-color: {f["accent_soft"]};
    color: {c["interactive"]};
}}
QTableCornerButton::section {{
    background-color: {f["table_header"]};
    border: none;
}}

/* --- 进度条 --- */
QProgressBar {{
    background-color: {f["control"]};
    border: none;
    border-radius: {radius}px;
    max-height: {pad_m}px;
    text-align: center;
    color: {c["ink_soft"]};
}}
QProgressBar::chunk {{
    background-color: {c["interactive"]};
    border-radius: {radius}px;
}}

/* --- 滚动条：老版的细灰条，无箭头 --- */
QScrollBar:vertical, QScrollBar:horizontal {{
    background-color: {c["page"]};
    border: none;
    width: {pad_m}px;
    height: {pad_m}px;
}}
QScrollBar::handle {{
    background-color: {f["scrollbar"]};
    border-radius: {radius}px;
    min-height: {pad_l}px;
    min-width: {pad_l}px;
}}
QScrollBar::handle:hover {{
    background-color: {f["scrollbar_active"]};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

QSplitter::handle {{
    background-color: {f["border_soft"]};
}}

QStatusBar {{
    background-color: {f["control"]};
    color: {c["muted_ink"]};
    border-top: 1px solid {f["card_border"]};
}}
QStatusBar::item {{
    border: none;
}}

QMenuBar {{
    background-color: {f["card"]};
    color: {c["ink"]};
    border-bottom: 1px solid {f["card_border"]};
}}
QMenu {{
    background-color: {f["card"]};
    color: {c["ink"]};
    border: 1px solid {f["card_border"]};
}}
QMenu::item {{
    padding: {pad_s}px {pad_l}px;
}}
QMenu::item:selected, QMenuBar::item:selected {{
    background-color: {f["accent_soft"]};
    color: {c["interactive"]};
}}

/* --- 焦点：只落在真正可聚焦的控件上，且替换边框颜色而非新增边框（尺寸不变，不引发重排） --- */
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus, QTableView:focus {{
    border: 1px solid {s["focus_ring"]};
}}
QPushButton:focus, QToolButton:focus, QTabBar::tab:focus {{
    border: 1px solid {s["focus_ring"]};
}}

/* 表格行高由 QSS 管不到，交给 table_utils 在构造时按 token 设置 —— 见 make_readonly_table。
   这里保留 {row_h}px 的记号，便于对照 tokens.table_row_height_dip。 */
"""


def apply_theme(app: object, tokens: DesignTokens | None = None) -> str:
    """把生成的 QSS 设为应用级样式，返回该 QSS 供检查。"""

    from .tokens import load_tokens

    resolved = tokens if tokens is not None else load_tokens()
    qss = build_qss(resolved)
    app.setStyleSheet(qss)  # type: ignore[attr-defined]
    return qss
