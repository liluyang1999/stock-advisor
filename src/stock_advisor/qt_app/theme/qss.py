"""把 `tokens.json` 的设计 token 生成为应用级 QSS（WI-005 / WI-034 / REQ-014/015/017/018）。

每个颜色与尺寸都取自 `DesignTokens`，QSS 里不出现任何字面色值——这样 tokens.json 始终是
唯一真源，`test_qt_theme.py` 会断言 QSS 中的每个十六进制色都能在 tokens 中找到。

**视觉基线沿用 Tkinter 版的语言**（WI-034）。此前 Qt 版只有一套通用样式：没有卡片面、没有指挥带、
表头与页面同色、标签页是 Qt 默认外观，因此与老版看起来完全是两个产品。本文件按老版的三层结构重建：

1. **暖灰纸面**（page）承载一切，不用纯白——纯白在长时间盯盘时更累。
2. **暖白卡片**（card）+ 1px 暖灰描边承载内容块，让表格与详情有"纸片"的边界感。
3. **墨蓝指挥带**（command_*）——老版最强的视觉锚点：工作模式与决策强度都坐在这条深色带里，
   与纸面形成明确的"控制区 vs 内容区"分工。Qt 侧用 QTabBar 与 `role="command"` 实现同一语言。
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
    row_h = tokens.table_row_height_dip
    pad_s, pad_m, pad_l = tokens.spacing_dip[0], tokens.spacing_dip[1], tokens.spacing_dip[2]
    caption_pt = tokens.font_points["caption"]
    body_pt = tokens.font_points["body"]
    section_pt = tokens.font_points["section"]

    return f"""\
/* 由 qt_app/theme/qss.py 从 loop/product/tokens.json 生成——勿手改，改 tokens.json */
QWidget {{
    background-color: {c["page"]};
    color: {c["ink"]};
    font-family: "{family}";
    font-size: {body_pt}pt;
}}

QMainWindow, QDialog {{
    background-color: {c["page"]};
}}

QLabel {{
    background-color: transparent;
}}

QLabel[role="section"] {{
    font-size: {section_pt}pt;
    font-weight: bold;
    color: {c["ink"]};
}}

QLabel[role="hint"] {{
    font-size: {caption_pt}pt;
    color: {s["disabled"]};
}}

/* --- 指挥带：老版最强的视觉锚点，控制区与内容区在此分界 --- */
QTabWidget::pane {{
    background-color: {c["page"]};
    border: none;
    top: -1px;
}}

QTabBar {{
    background-color: {f["command_bg"]};
    qproperty-drawBase: 0;
}}

QTabBar::tab {{
    background-color: {f["command_surface"]};
    color: {f["command_muted_ink"]};
    font-weight: bold;
    border: 1px solid {f["command_border"]};
    border-bottom: none;
    min-height: {ctrl_h}px;
    min-width: 132px;
    padding: {pad_s}px {pad_l}px;
    margin-right: 1px;
}}

QTabBar::tab:hover {{
    background-color: {s["hover"]};
    color: {f["command_ink"]};
}}

QTabBar::tab:selected {{
    background-color: {f["card"]};
    color: {c["ink"]};
    border-color: {f["card_border"]};
}}

QWidget[role="command"] {{
    background-color: {f["command_bg"]};
    border: 1px solid {f["command_border"]};
    border-radius: {radius}px;
}}
QWidget[role="command"] QLabel {{
    color: {f["command_muted_ink"]};
    font-weight: bold;
}}

/* 指挥带里的分段按钮：决策强度五档一字排开，选中段翻成纸面色，与老版一致 */
QPushButton[role="segment"] {{
    background-color: {f["command_surface"]};
    color: {f["command_muted_ink"]};
    border: 1px solid {f["command_border"]};
    border-radius: 0px;
    font-weight: bold;
    min-height: {ctrl_h}px;
    padding: {pad_s}px {pad_m}px;
}}
QPushButton[role="segment"]:hover {{
    background-color: {s["hover"]};
    color: {f["command_ink"]};
}}
QPushButton[role="segment"]:checked {{
    background-color: {f["card"]};
    color: {c["ink"]};
}}

/* --- 卡片：内容块的纸片边界 --- */
QFrame[role="panel"], QGroupBox {{
    background-color: {f["card"]};
    border: 1px solid {f["card_border"]};
    border-radius: {radius}px;
}}

QSplitter::handle {{
    background-color: {f["card_border"]};
}}

/* --- 按钮：主行动填色，次要行动留白 --- */
QPushButton {{
    background-color: {c["interactive"]};
    color: {f["command_ink"]};
    border: 1px solid {c["interactive"]};
    border-radius: {radius}px;
    min-height: {ctrl_h}px;
    padding: {pad_s}px {pad_m}px;
}}
QPushButton:hover {{
    background-color: {s["hover"]};
}}
QPushButton:pressed {{
    background-color: {s["pressed"]};
}}
QPushButton:disabled {{
    background-color: {f["control"]};
    color: {s["disabled"]};
    border-color: {f["card_border"]};
}}
QPushButton[role="primary"] {{
    min-height: {primary_h}px;
}}
QPushButton[role="quiet"] {{
    background-color: {f["control"]};
    color: {c["ink"]};
    border: 1px solid {f["card_border"]};
}}
QPushButton[role="quiet"]:hover {{
    background-color: {f["surface_alt"]};
}}

/* --- 输入控件 --- */
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{
    background-color: {f["card"]};
    color: {c["ink"]};
    border: 1px solid {f["card_border"]};
    border-radius: {radius}px;
    min-height: {ctrl_h}px;
    padding: 0px {pad_s}px;
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    background-color: {f["control"]};
    color: {s["disabled"]};
}}
QComboBox::drop-down {{
    border: none;
    width: {pad_l}px;
}}

/* --- 表格：表头自成一色，行高按 token，选中行浅蓝 --- */
QTableView {{
    background-color: {f["card"]};
    alternate-background-color: {f["surface_alt"]};
    gridline-color: {s["gridline"]};
    selection-background-color: {s["selected_row"]};
    selection-color: {c["ink"]};
    border: 1px solid {f["card_border"]};
    border-radius: {radius}px;
}}
QTableView::item {{
    padding: 0px {pad_s}px;
}}

QHeaderView::section {{
    background-color: {f["table_header"]};
    color: {c["ink"]};
    font-weight: bold;
    border: none;
    border-right: 1px solid {s["gridline"]};
    border-bottom: 1px solid {f["card_border"]};
    min-height: {ctrl_h}px;
    padding: 0px {pad_s}px;
}}

QScrollBar:vertical, QScrollBar:horizontal {{
    background-color: {f["surface_alt"]};
    border: none;
    width: {pad_m}px;
    height: {pad_m}px;
}}
QScrollBar::handle {{
    background-color: {f["card_border"]};
    border-radius: {radius}px;
    min-height: {pad_l}px;
}}
QScrollBar::handle:hover {{
    background-color: {s["disabled"]};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}

QStatusBar {{
    background-color: {f["surface_alt"]};
    color: {c["ink"]};
    border-top: 1px solid {f["card_border"]};
}}

QMenuBar, QMenu {{
    background-color: {f["card"]};
    color: {c["ink"]};
}}
QMenu::item:selected, QMenuBar::item:selected {{
    background-color: {s["selected_row"]};
}}

*:focus {{
    border: 2px solid {s["focus_ring"]};
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
