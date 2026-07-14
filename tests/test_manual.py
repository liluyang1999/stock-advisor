import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from stock_advisor.domain.presets import PRESETS
from stock_advisor.ui.manual import build_manual_html


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

    def test_uses_segmented_button_wording_not_slider_wording(self):
        # 决策强度控件是一排点选式分段按钮（tk.Radiobutton, indicatoron=False），不是可拖动的
        # 滑杆；说明书措辞需如实反映交互方式。
        self.assertNotIn("滑杆", self.html)
        self.assertNotIn("拖动", self.html)
        self.assertIn("分段按钮", self.html)
        self.assertIn("点选", self.html)


if __name__ == "__main__":
    unittest.main()
