"""字体契约（REQ-016 / REQ-033 / WI-004）。

REQ-016 要求所有可见文字统一 `ui/theme.py::UI_FONT`；REQ-033 要求该字体缺失时**可见失败或
走文档化回退**，禁止静默错字体渲染——后者正是这里的重点：Qt 在字体缺失时会**默默**换一个，
只有 `QFontInfo` 能看穿"要了 A 实际拿到 B"。

因此测试断言的是**契约**而不是"本机装了雅黑"：CI 跑在英文 windows 镜像上，雅黑可能不存在，
但"绝不静默用错字体"这条在两种环境下都必须成立。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from PySide6 import QtGui, QtWidgets
except ImportError:  # pragma: no cover - Qt 是可选的迁移期依赖（pyproject 的 gui 组）
    QtGui = QtWidgets = None

from stock_advisor.ui import theme

if QtWidgets is not None:
    from stock_advisor.qt_app.theme import fonts


def _app() -> object:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@unittest.skipIf(QtWidgets is None, "PySide6 未安装（pip install --group gui）")
class FontContractTests(unittest.TestCase):
    def setUp(self):
        self.app = _app()

    def test_resolution_never_silently_substitutes(self):
        """核心契约：要么拿到请求的字体，要么如实报告替换——绝不静默。"""
        resolved = fonts.resolve_ui_font()
        if resolved.is_exact:
            self.assertEqual(resolved.actual_family, resolved.requested_family)
            self.assertIsNone(resolved.fallback_note)
        else:
            # 未拿到请求字体时，必须留下可呈现给用户的说明（REQ-033 的"可见失败/文档化回退"）。
            self.assertTrue(resolved.fallback_note)
            self.assertIn(resolved.actual_family, resolved.fallback_note)

    def test_requested_family_comes_from_the_theme_single_source(self):
        # 不得在 Qt 侧另写一份字体名，否则 token 真源立刻分叉。
        self.assertEqual(fonts.resolve_ui_font().requested_family, theme.UI_FONT)

    def test_applied_font_is_what_qfontinfo_reports(self):
        """QFont('X') 永远"设置成功"，QFontInfo 才说出实际渲染字体——断言必须基于后者。"""
        resolved = fonts.resolve_ui_font()
        widget = QtWidgets.QLabel("模型仅供研究和辅助决策，不构成投资建议。")
        widget.setFont(resolved.font)
        self.assertEqual(QtGui.QFontInfo(widget.font()).family(), resolved.actual_family)

    def test_exact_match_flag_is_not_qt_exactmatch(self):
        # 陷阱：QFontInfo.exactMatch() 即便字体族正确也常为 False（字号/字重差异），
        # 用它做判据会把正确的字体误报成缺失。契约按 family() 判定。
        resolved = fonts.resolve_ui_font()
        self.assertEqual(resolved.is_exact, resolved.actual_family == resolved.requested_family)

    def test_missing_family_falls_back_and_says_so(self):
        resolved = fonts.resolve_ui_font(requested="A Font That Does Not Exist 12345")
        self.assertFalse(resolved.is_exact)
        self.assertTrue(resolved.fallback_note)
        self.assertNotEqual(resolved.actual_family, "A Font That Does Not Exist 12345")

    def test_point_size_flows_through(self):
        self.assertEqual(fonts.resolve_ui_font(point_size=13).font.pointSize(), 13)


if __name__ == "__main__":
    unittest.main()
