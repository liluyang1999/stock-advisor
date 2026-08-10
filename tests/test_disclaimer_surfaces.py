"""TEST-DISC-001：不构成投资建议声明的跨面静态扫描（REQ-031 / WI-018）。

免责声明必须出现在**每一个**关键面：每个结果视图、生成的 HTML 说明书、以及每一种导出
（CSV / 剪贴板）。导出件常被单独保存或转发，脱离界面里常驻的那句声明，因此声明必须随数据
一起走。本测试是「零面缺失」的静态回归：任何新增结果页或导出格式漏了声明都会在此变红。
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data.sample_data import make_sample_analysis
from domain.models import CORE_DISCLAIMER
from ui.manual import build_manual_html
from ui.view_format import (
    format_results_as_csv,
    format_results_for_clipboard,
    format_table_rows_as_csv,
    format_table_rows_for_clipboard,
)

# 声明的稳定可检子串：结果视图/导出用 CORE_DISCLAIMER，说明书用更长的 theme.DISCLAIMER，
# 两者都含这一句，用它做跨面判据不受长短文案差异影响。
_DISCLAIMER_TOKEN = "不构成投资建议"

_SAMPLE_TABLE_ROWS = [("600519", "贵州茅台", "买入", "47", "84", "1688.00", "+1.5%", "低")]

# 结果视图页：每个都必须在源码里静态引用 CORE_DISCLAIMER（常驻声明，切页不带走）。
_RESULT_VIEW_PAGES = (
    "src/qt_app/pages/individual_page.py",
    "src/qt_app/pages/screener_page.py",
    "src/qt_app/pages/alerts_page.py",
    "src/qt_app/pages/evidence_page.py",
    # 自选/持仓页同样是结果视图（横向对比表就是一份结论），此前漏在这份清单外——
    # 守卫少一页，就等于那一页的免责声明可以被删掉而没人发现（REQ-031）。
    "src/qt_app/pages/portfolio_page.py",
)


class ExportSurfaceDisclaimerTests(unittest.TestCase):
    def setUp(self):
        self.results = [make_sample_analysis()]

    def test_results_csv_carries_disclaimer(self):
        self.assertIn(CORE_DISCLAIMER, format_results_as_csv(self.results))

    def test_results_clipboard_carries_disclaimer(self):
        self.assertIn(CORE_DISCLAIMER, format_results_for_clipboard(self.results))

    def test_table_csv_carries_disclaimer(self):
        self.assertIn(CORE_DISCLAIMER, format_table_rows_as_csv(_SAMPLE_TABLE_ROWS))

    def test_table_clipboard_carries_disclaimer(self):
        self.assertIn(CORE_DISCLAIMER, format_table_rows_for_clipboard(_SAMPLE_TABLE_ROWS))

    def test_disclaimer_is_the_last_line_of_each_export(self):
        # 声明置于末行（页脚），不与表头/数据行混排，导出后一眼可见。
        for text in (
            format_results_as_csv(self.results),
            format_results_for_clipboard(self.results),
            format_table_rows_as_csv(_SAMPLE_TABLE_ROWS),
            format_table_rows_for_clipboard(_SAMPLE_TABLE_ROWS),
        ):
            self.assertIn(_DISCLAIMER_TOKEN, text.strip().splitlines()[-1])


class ManualDisclaimerTests(unittest.TestCase):
    def test_manual_html_carries_disclaimer(self):
        self.assertIn(_DISCLAIMER_TOKEN, build_manual_html())


class ResultViewDisclaimerTests(unittest.TestCase):
    def test_every_result_view_references_core_disclaimer(self):
        for rel in _RESULT_VIEW_PAGES:
            src = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("CORE_DISCLAIMER", src, f"结果视图未引用免责声明：{rel}")

    def test_core_disclaimer_actually_says_it_is_not_advice(self):
        """免责声明的**内容**也要守住：字符串还在、话却说没了，等于没有声明。

        （原先这条断言挂在 `test_qt_result_model.py` 里，随那个从未被生产实例化的
        `ResultTableModel` 一起被删除时移到这里——它与那个类无关，不该跟着消失。）
        """
        self.assertIn("不构成投资建议", CORE_DISCLAIMER)


if __name__ == "__main__":
    unittest.main()
