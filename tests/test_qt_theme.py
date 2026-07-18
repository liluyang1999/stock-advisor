"""QSS 主题契约（REQ-015 / REQ-017 / REQ-018 / WI-005 / TEST-VIS-001）。

WI-005 的 DoD：tokens.json 的 spacing/font/color token 经 QSS 应用到各控件。关键约束是
**单一真源**——QSS 里出现的每个颜色/尺寸都必须来自 tokens.json，不得在 Qt 侧另抄一份，
否则 tokens.json（带 WCAG 实测的权威色源）与实际渲染就会分叉。
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from PySide6 import QtWidgets
except ImportError:  # pragma: no cover - Qt 是可选的迁移期依赖
    QtWidgets = None

if QtWidgets is not None:
    from stock_advisor.qt_app.theme import qss as qss_mod, tokens as tokens_mod


TOKENS_PATH = Path(__file__).resolve().parents[1] / "loop" / "product" / "tokens.json"


class TokenLoaderTests(unittest.TestCase):
    def test_tokens_load_from_the_machine_authoritative_file(self):
        import json

        raw = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
        if QtWidgets is None:
            self.skipTest("PySide6 未安装")
        loaded = tokens_mod.load_tokens()
        # 加载器不得改写权威文件里的任何色值。
        self.assertEqual(loaded.colors["interactive"], raw["colors"]["interactive"])
        self.assertEqual(loaded.colors["page"], raw["colors"]["page"])
        self.assertEqual(loaded.state_colors["focus_ring"], raw["state_colors"]["focus_ring"])


@unittest.skipIf(QtWidgets is None, "PySide6 未安装（pip install --group gui）")
class QssContractTests(unittest.TestCase):
    def setUp(self):
        self.tokens = tokens_mod.load_tokens()
        self.qss = qss_mod.build_qss(self.tokens)

    def test_qss_is_non_empty_and_styles_core_widgets(self):
        for selector in ("QWidget", "QPushButton", "QTableView", "QHeaderView"):
            self.assertIn(selector, self.qss, f"QSS 未覆盖 {selector}")

    def test_every_hex_colour_in_the_qss_comes_from_tokens(self):
        """核心单一真源断言：QSS 里的每个十六进制色都必须在 tokens.json 中。"""
        allowed = {
            value.upper()
            for value in list(self.tokens.colors.values()) + list(self.tokens.state_colors.values())
        }
        used = {m.group(0).upper() for m in re.finditer(r"#[0-9A-Fa-f]{6}", self.qss)}
        stray = used - allowed
        self.assertEqual(stray, set(), f"QSS 出现了不属于 tokens.json 的颜色：{stray}")

    def test_interactive_and_state_colours_are_actually_used(self):
        # 不只是"没有多余色"，还要"权威色确实被用上"——按钮的交互态必须落到 QSS 里。
        for token in (
            self.tokens.colors["interactive"],
            self.tokens.state_colors["hover"],
            self.tokens.state_colors["pressed"],
        ):
            self.assertIn(token.upper(), self.qss.upper())

    def test_control_heights_come_from_tokens(self):
        # REQ-018/AC-005：控件最小高度用 token 的 dip 值，不硬编码。
        self.assertIn(f"{self.tokens.control_min_height_dip}px", self.qss)
        self.assertIn(f"{self.tokens.table_row_height_dip}px", self.qss)

    def test_font_family_is_the_token_family_not_a_qt_default(self):
        self.assertIn(self.tokens.font_families[0], self.qss)

    def test_applying_qss_to_a_real_widget_does_not_throw(self):
        # QSS 语法错误不会抛异常但会被 Qt 静默忽略；至少确认 setStyleSheet 接受它、
        # 且样式非空地作用到控件上。
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        widget = QtWidgets.QPushButton("测试")
        widget.setStyleSheet(self.qss)
        self.assertEqual(widget.styleSheet(), self.qss)
        self.assertTrue(app)  # 保持引用

    def test_qss_has_no_unresolved_placeholders(self):
        # 生成器若漏填某个 token，会留下 {like_this} 占位符——绝不能进最终 QSS。
        self.assertNotRegex(self.qss, r"\{[a-z_]+\}")


if __name__ == "__main__":
    unittest.main()
