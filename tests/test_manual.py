import re
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from domain.presets import PRESETS
from ui.manual import build_manual_html


class ManualHtmlTests(unittest.TestCase):
    def setUp(self):
        self.html = build_manual_html()

    def test_is_well_formed_html_document(self):
        self.assertTrue(self.html.startswith("<!DOCTYPE html>"))
        self.assertIn('<html lang="zh-CN">', self.html)
        self.assertEqual(self.html.count("<body>"), 1)
        self.assertTrue(self.html.rstrip().endswith("</html>"))

    def test_covers_both_features_and_all_presets(self):
        self.assertIn("个股分析", self.html)
        self.assertIn("全市场选股", self.html)
        self.assertIn("可筛选的证券特征", self.html)
        for preset in PRESETS:
            self.assertIn(preset.name, self.html)

    def test_explains_key_characteristics_and_keeps_disclaimer(self):
        for term in ("市盈率", "换手率", "量比", "成交额", "总市值"):
            self.assertIn(term, self.html)
        self.assertIn("不构成", self.html)  # 免责声明保留

    def test_documents_decision_strength_and_modules(self):
        for term in ("决策强度", "仓位", "回测", "红=上涨"):
            self.assertIn(term, self.html)
        self.assertIn("股市锦囊", self.html)

    def test_documents_current_qt_interactions_not_tk_ones(self):
        """说明书必须描述现在的五页布局与真实入口，而不是老 Tk 的弹窗按钮。"""
        for term in ("条件预警", "个股资金流", "载入分析", "查看当前标的资金流", "表头", "排序"):
            self.assertIn(term, self.html)
        # 旧交互的原话不许再出现：这些按钮已不存在。
        for stale in ("点「横向对比」", "点「预警」", "点「资金流」", "自选股」窗"):
            self.assertNotIn(stale, self.html)

    def test_uses_segmented_button_wording_not_slider_wording(self):
        # 决策强度控件是一排点选式分段按钮（tk.Radiobutton, indicatoron=False），不是可拖动的
        # 滑杆；说明书措辞需如实反映交互方式。
        self.assertNotIn("滑杆", self.html)
        self.assertNotIn("拖动", self.html)
        self.assertIn("分段按钮", self.html)
        self.assertIn("点选", self.html)


class ManualFontAuditTests(unittest.TestCase):
    """TEST-FONT-002：生成的 HTML 说明书 CSS 字体静态审计（REQ-016）。

    说明书正文字体须为微软雅黑，且**零** UI 体（Microsoft YaHei UI）或等宽体例外——正文是长
    段中文阅读，用非 UI 的雅黑；曾经硬编码的 'Microsoft YaHei UI' 与 tokens.json 的真源分叉，
    此审计把它钉死为回归。
    """

    def setUp(self):
        self.html = build_manual_html()
        self.decls = re.findall(r"font-family:[^;}]*", self.html)

    def test_manual_declares_a_font_family(self):
        # 至少要有一处字体声明，否则“审计通过”只是因为压根没声明字体。
        self.assertTrue(self.decls, "说明书 CSS 未声明任何 font-family")

    def test_every_font_family_is_microsoft_yahei(self):
        for decl in self.decls:
            self.assertIn("Microsoft YaHei", decl, f"字体声明未使用微软雅黑：{decl}")

    def test_no_ui_font_exception(self):
        for decl in self.decls:
            self.assertNotIn("Microsoft YaHei UI", decl, f"出现 UI 体例外：{decl}")

    def test_no_monospace_exception(self):
        low = self.html.lower()
        self.assertNotIn("monospace", low)
        self.assertNotIn("consolas", low)

    def test_font_family_is_sourced_from_tokens_not_hardcoded(self):
        # 字体应来自 tokens.json 的 font_families，与 Qt QSS/字体契约同一真源（WI-005 教训）。
        import json

        from ui.assets import tokens_path

        families = json.loads(tokens_path().read_text(encoding="utf-8"))["font_families"]
        for family in families:
            self.assertIn(family, self.html, f"tokens 声明的字体未出现在说明书：{family}")


if __name__ == "__main__":
    unittest.main()
