"""可访问性审计（REQ-016/017/018 / WI-021 / TEST-A11Y-001）。

对每个功能页的每个交互控件断言无障碍四要素：键盘可达、有可见焦点指示、暴露可访问名、颜色对比
达标。这是 TEST-A11Y-001 里可自动化的部分（离屏内省）；像素级视觉复核对照设计稿是人工 V4 环节。
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtCore, QtWidgets, qt_app, requires_qt
from test_engine import FakeProvider

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if QtWidgets is not None:
    from stock_advisor.qt_app.controllers.alert_controller import AlertController
    from stock_advisor.qt_app.controllers.analysis_controller import AnalysisController
    from stock_advisor.qt_app.controllers.fund_flow_controller import FundFlowController
    from stock_advisor.qt_app.controllers.screener_controller import ScreenerController
    from stock_advisor.qt_app.main_window import build_application
    from stock_advisor.qt_app.pages.alerts_page import AlertsPage
    from stock_advisor.qt_app.pages.evidence_page import EvidencePage
    from stock_advisor.qt_app.pages.individual_page import IndividualPage
    from stock_advisor.qt_app.pages.screener_page import ScreenerPage

    _INTERACTIVE = (
        QtWidgets.QLineEdit,
        QtWidgets.QAbstractButton,
        QtWidgets.QComboBox,
        QtWidgets.QAbstractSpinBox,
        QtWidgets.QAbstractItemView,
    )
    # 复合控件：其内部子件（spinbox 的行编辑、combobox 的弹出列表/按钮、表格的表头/滚动条按钮）
    # 不需要各自的可访问名——名字属于外层复合控件本身。审计时把这些内部件排除。
    _COMPOSITE = (
        QtWidgets.QComboBox,
        QtWidgets.QAbstractSpinBox,
        QtWidgets.QAbstractItemView,
    )


def _effective_accessible_name(widget) -> str:
    """控件对外暴露的可访问名：显式 accessibleName 优先，按钮回退到文本（Qt 据文本自动取名）。"""
    name = widget.accessibleName()
    if name:
        return name
    if isinstance(widget, QtWidgets.QAbstractButton):
        return widget.text()
    return ""


@requires_qt
class AccessibilityAuditTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _pages(self):
        pages = [
            IndividualPage(AnalysisController(FakeProvider())),
            EvidencePage(FundFlowController(FakeProvider())),
            ScreenerPage(ScreenerController(FakeProvider())),
            AlertsPage(AlertController(FakeProvider())),
        ]
        for page in pages:
            self.addCleanup(page.deleteLater)
        return pages

    def _interactive(self, page):
        controls = []
        for widget in page.findChildren(QtWidgets.QWidget):
            if not isinstance(widget, _INTERACTIVE):
                continue
            if self._nested_in_composite(widget, page):
                continue  # 复合控件的内部子件跳过——名字属于外层复合控件
            controls.append(widget)
        return controls

    @staticmethod
    def _nested_in_composite(widget, page) -> bool:
        parent = widget.parentWidget()
        while parent is not None and parent is not page:
            if isinstance(parent, _COMPOSITE):
                return True
            parent = parent.parentWidget()
        return False

    def test_every_interactive_control_is_keyboard_reachable(self):
        for page in self._pages():
            for widget in self._interactive(page):
                with self.subTest(page=type(page).__name__, widget=type(widget).__name__):
                    # 键盘可达：焦点策略不为 NoFocus（启用时可 Tab 抵达）。
                    self.assertNotEqual(widget.focusPolicy(), QtCore.Qt.FocusPolicy.NoFocus)

    def test_every_interactive_control_exposes_an_accessible_name(self):
        for page in self._pages():
            for widget in self._interactive(page):
                with self.subTest(page=type(page).__name__, widget=type(widget).__name__):
                    self.assertTrue(
                        _effective_accessible_name(widget),
                        f"{type(widget).__name__} 无可访问名（屏幕阅读器读不出）",
                    )

    def test_applied_qss_defines_a_visible_focus_indicator(self):
        app, window = build_application([])
        self.addCleanup(window.deleteLater)
        # REQ-017：焦点可见。QSS 的 *:focus 用 tokens 的 focus_ring 画可见边框。
        self.assertIn(":focus", app.styleSheet())

    def test_token_contrast_meets_documented_targets(self):
        # REQ-017 颜色对比：tokens.json 的 WCAG 实测比值须满足其声明的达标标记。
        tokens = json.loads(
            (PROJECT_ROOT / "loop" / "product" / "tokens.json").read_text(encoding="utf-8")
        )
        targets = tokens["contrast"]["targets"]
        for entry in tokens["contrast"]["measured"]:
            with self.subTest(fg=entry["foreground"], bg=entry["background"]):
                if entry.get("meets_body_text"):
                    self.assertGreaterEqual(entry["ratio"], targets["body_text_min_ratio"])
                if entry.get("meets_large_or_control"):
                    self.assertGreaterEqual(
                        entry["ratio"], targets["large_text_or_control_min_ratio"]
                    )
                # 每个前景至少达到大字/控件级 3.0（本设计里没有低于此的可见文本/控件）。
                self.assertGreaterEqual(entry["ratio"], targets["large_text_or_control_min_ratio"])


class ColorRedundancyTests(unittest.TestCase):
    """REQ-017 颜色冗余：涨跌不只靠红绿，结果表的涨跌幅列带 +/- 符号做非颜色冗余标识。"""

    def test_change_percent_column_carries_sign_redundant_with_color(self):
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
        from dataclasses import replace

        from stock_advisor.data.sample_data import make_sample_analysis
        from stock_advisor.ui.view_format import format_result_row

        up = make_sample_analysis()  # 正涨幅样例
        down = replace(up, change_pct=-1.53)
        self.assertTrue(format_result_row(up)[6].startswith("+"))  # 涨：+ 号（非颜色冗余）
        self.assertTrue(format_result_row(down)[6].startswith("-"))  # 跌：- 号


if __name__ == "__main__":
    unittest.main()
