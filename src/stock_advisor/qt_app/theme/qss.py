"""把 `tokens.json` 的设计 token 生成为应用级 QSS（WI-005 / REQ-015/017/018）。

每个颜色与尺寸都取自 `DesignTokens`，QSS 里不出现任何字面色值——这样 tokens.json 始终是
唯一真源，`test_qt_theme.py` 会断言 QSS 中的每个十六进制色都能在 tokens 中找到。
"""

from __future__ import annotations

from .tokens import DesignTokens


def build_qss(tokens: DesignTokens) -> str:
    """构造应用级样式表。选择器覆盖外壳、按钮、表格、输入、滚动条与焦点态。"""

    c = tokens.colors
    s = tokens.state_colors
    family = tokens.font_families[0]
    radius = tokens.border_radius_dip
    ctrl_h = tokens.control_min_height_dip
    primary_h = tokens.primary_control_height_dip
    row_h = tokens.table_row_height_dip
    pad_s, pad_m = tokens.spacing_dip[0], tokens.spacing_dip[1]
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
    color: {c["ink"]};
}}

QFrame[role="panel"], QGroupBox {{
    background-color: {c["panel"]};
    border: 1px solid {s["gridline"]};
    border-radius: {radius}px;
}}

QPushButton {{
    background-color: {c["interactive"]};
    color: {c["panel"]};
    border: none;
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
    background-color: {s["disabled"]};
    color: {c["page"]};
}}
QPushButton[role="primary"] {{
    min-height: {primary_h}px;
}}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{
    background-color: {c["panel"]};
    color: {c["ink"]};
    border: 1px solid {s["gridline"]};
    border-radius: {radius}px;
    min-height: {ctrl_h}px;
    padding: 0px {pad_s}px;
}}

QTableView {{
    background-color: {c["panel"]};
    alternate-background-color: {c["page"]};
    gridline-color: {s["gridline"]};
    selection-background-color: {s["selected_row"]};
    selection-color: {c["ink"]};
    border: 1px solid {s["gridline"]};
}}
QTableView::item {{
    min-height: {row_h}px;
    padding: 0px {pad_s}px;
}}

QHeaderView::section {{
    background-color: {c["page"]};
    color: {c["ink"]};
    border: none;
    border-bottom: 1px solid {s["gridline"]};
    min-height: {ctrl_h}px;
    padding: 0px {pad_s}px;
}}

QScrollBar:vertical, QScrollBar:horizontal {{
    background-color: {c["page"]};
    border: none;
}}
QScrollBar::handle {{
    background-color: {s["disabled"]};
    border-radius: {radius}px;
}}

QStatusBar {{
    background-color: {c["panel"]};
    color: {c["ink"]};
    border-top: 1px solid {s["gridline"]};
}}

*:focus {{
    border: 2px solid {s["focus_ring"]};
}}
"""


def apply_theme(app: object, tokens: DesignTokens | None = None) -> str:
    """把生成的 QSS 设为应用级样式，返回该 QSS 供检查。"""

    from .tokens import load_tokens

    resolved = tokens if tokens is not None else load_tokens()
    qss = build_qss(resolved)
    app.setStyleSheet(qss)  # type: ignore[attr-defined]
    return qss
