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

from qt_test_helpers import QtCore, QtWidgets, qt_app, requires_qt, temp_settings
from test_engine import FakeProvider

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if QtWidgets is not None:
    from qt_app.main_window import build_application

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
        """审计装配好的主窗里的每一页，而不是手写一份页面清单。

        手写清单会过期：自选/持仓页加进产品后，这里一直没跟上，于是它的代码/成本/股数输入、增删
        按钮和对比表从未被审计过——和"部件写好却没挂上"是同一类失误，只不过发生在测试这一侧。
        从装好的窗口拿页面，新增一页就自动进审计范围，没有清单可忘。
        """
        from qt_app.app import build_app

        _app, window = build_app([], provider=FakeProvider(), settings=temp_settings(self))
        self.addCleanup(window.deleteLater)
        return [window.tabs.widget(i) for i in range(window.tabs.count())]

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

    def test_a_readonly_table_cannot_be_created_without_an_accessible_name(self):
        """把"记得设可访问名"变成参数，而不是靠自觉。

        ComparisonView 就漏过一次，而且直到审计改为遍历装配好的主窗才暴露——两层疏漏叠在一起。
        表格没有文本，读屏只能靠可访问名认出它（REQ-017）。
        """
        from qt_app.widgets.table_utils import make_readonly_table

        with self.assertRaises(TypeError):
            make_readonly_table(["代码"])  # type: ignore[call-arg]
        with self.assertRaises(ValueError):
            make_readonly_table(["代码"], "   ")

    def test_every_table_in_the_assembled_window_is_named(self):
        """装配好的窗口里不该有任何无名表格。"""
        from qt_app.app import build_app

        _app, window = build_app([], provider=FakeProvider(), settings=temp_settings(self))
        self.addCleanup(window.deleteLater)

        unnamed = [
            table
            for table in window.findChildren(QtWidgets.QTableView)
            if not table.accessibleName()
        ]

        self.assertEqual(unnamed, [], f"{len(unnamed)} 个表格没有可访问名")

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

        from data.sample_data import make_sample_analysis
        from ui.view_format import format_result_row

        up = make_sample_analysis()  # 正涨幅样例
        down = replace(up, change_pct=-1.53)
        self.assertTrue(format_result_row(up)[6].startswith("+"))  # 涨：+ 号（非颜色冗余）
        self.assertTrue(format_result_row(down)[6].startswith("-"))  # 跌：- 号


if __name__ == "__main__":
    unittest.main()
