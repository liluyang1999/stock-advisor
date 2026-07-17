"""Qt 外壳契约（REQ-011 / REQ-014 / REQ-031 / WI-004）。

WI-004 的 DoD：最小 QApplication/QMainWindow 外壳可运行，标题栏图标/标题只出现一次，
每个可见控件经 QFontInfo 解析到 token 真源的字体。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from PySide6 import QtGui, QtWidgets
except ImportError:  # pragma: no cover - Qt 是可选的迁移期依赖
    QtGui = QtWidgets = None

from stock_advisor.domain.models import CORE_DISCLAIMER
from stock_advisor.ui import theme

if QtWidgets is not None:
    from stock_advisor.qt_app import main_window


@unittest.skipIf(QtWidgets is None, "PySide6 未安装（pip install --group gui）")
class QtShellTests(unittest.TestCase):
    def setUp(self):
        self.app, self.window = main_window.build_application([])
        self.addCleanup(self.window.deleteLater)

    def test_shell_is_a_qmainwindow_titled_from_the_token_source(self):
        self.assertIsInstance(self.window, QtWidgets.QMainWindow)  # REQ-011
        self.assertEqual(self.window.windowTitle(), theme.APP_TITLE)

    def test_brand_appears_only_in_the_native_title_bar(self):
        # REQ-014：内容区不得再重复一遍图标/标题。原生标题栏已承担身份，
        # 任何内容区里出现 APP_TITLE 的可见文字都是重复。
        labels = self.window.centralWidget().findChildren(QtWidgets.QLabel)
        self.assertNotIn(theme.APP_TITLE, [label.text() for label in labels])

    def test_disclaimer_is_resident_in_the_shell(self):
        # REQ-031：免责声明常驻。放在状态栏——页面切换不会带走它。
        self.assertIn(CORE_DISCLAIMER, self.window.statusBar().currentMessage())

    def test_every_visible_widget_inherits_the_resolved_ui_font(self):
        """DoD 的核心判据：每个可见控件都经 QFontInfo 解析到同一个实际字体族。"""
        from stock_advisor.qt_app.theme import fonts

        expected = fonts.resolve_ui_font().actual_family
        self.window.set_page(QtWidgets.QLabel("测试页"))
        widgets = self.window.findChildren(QtWidgets.QWidget)
        self.assertGreater(len(widgets), 0)
        for widget in widgets:
            with self.subTest(widget=type(widget).__name__):
                self.assertEqual(QtGui.QFontInfo(widget.font()).family(), expected)

    def test_minimum_size_comes_from_the_token_source(self):
        self.assertEqual(
            (self.window.minimumSize().width(), self.window.minimumSize().height()),
            theme.MAIN_MIN_SIZE,
        )

    def test_set_page_mounts_and_shows_the_page(self):
        page = QtWidgets.QLabel("个股工作台")
        self.window.set_page(page)
        self.assertIs(
            self.window.centralWidget().findChild(QtWidgets.QStackedWidget).currentWidget(), page
        )

    def test_font_fallback_is_reported_visibly_not_swallowed(self):
        # REQ-033：回退必须可见。状态栏是外壳的可见常驻位。
        self.window.report_font_fallback("字体「X」不可用，已回退为「Y」")
        message = self.window.statusBar().currentMessage()
        self.assertIn("已回退", message)
        self.assertIn(CORE_DISCLAIMER, message)  # 回退提示不得挤掉免责声明


if __name__ == "__main__":
    unittest.main()
