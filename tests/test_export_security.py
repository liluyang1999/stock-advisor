"""TEST-SEC-001：CSV/剪贴板导出的公式注入中和（REQ-032 / AC-032 / WI-028）。

威胁模型：导出内容里的股票名称等字段来自远端行情接口，用户拿 Excel/WPS 打开导出的 CSV、
或把结果粘进表格时，以 `=`/`+`/`-`/`@` 开头的单元格会被当成公式求值（DDE 可执行外部命令）。
四条导出路径（两条 CSV、两条剪贴板）都会流向表格软件，因此都必须中和。
"""

import csv
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.ui.view_format import (
    format_results_as_csv,
    format_results_for_clipboard,
    format_table_rows_as_csv,
    format_table_rows_for_clipboard,
    neutralize_export_cell,
)

# Excel/WPS 会把这些开头的单元格当公式；`=cmd|…!A0` 是经典的 DDE 命令执行载荷。
INJECTION_PAYLOADS = (
    "=cmd|' /C calc'!A0",
    "+cmd|' /C calc'!A0",
    "-2+3+cmd|' /C calc'!A0",
    "@SUM(1+9)*cmd|' /C calc'!A0",
    "=1+1",
    '=HYPERLINK("http://evil","click")',
)


class NeutralizeCellTests(unittest.TestCase):
    def test_every_dangerous_lead_is_neutralized(self):
        for payload in INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                cell = neutralize_export_cell(payload)
                self.assertFalse(
                    cell.startswith(("=", "+", "-", "@")),
                    f"{payload!r} 仍以公式引导符开头：{cell!r}",
                )
                # 中和不得丢失原文：加前缀而非删改，用户仍看得到原始内容。
                self.assertIn(payload, cell)

    def test_tab_and_carriage_return_leads_are_neutralized(self):
        # 与四个引导符同属 DDE 触发类；REQ-032 未逐一点名，但同一缺陷类一并堵住。
        for payload in ("\tcmd", "\rcmd"):
            with self.subTest(payload=payload):
                self.assertTrue(neutralize_export_cell(payload).startswith("'"))

    def test_ordinary_text_is_left_untouched(self):
        for safe in ("600519", "贵州茅台", "买入/加仓", "47 分", "84%", "26.60", "低", ""):
            with self.subTest(safe=safe):
                self.assertEqual(neutralize_export_cell(safe), safe)

    def test_non_string_values_pass_through_as_text(self):
        self.assertEqual(neutralize_export_cell(None), "")
        self.assertEqual(neutralize_export_cell(26.6), "26.6")


class ExportPathsAreNeutralizedTests(unittest.TestCase):
    """四条导出路径逐一验证：任何一条漏掉，注入即可达用户的表格软件。"""

    @staticmethod
    def _cells(payload: str, text: str, delimiter: str) -> list[str]:
        reader = csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=delimiter)
        return [cell for row in reader for cell in row]

    def _assert_no_live_formula(self, text: str, delimiter: str = ","):
        for cell in self._cells("", text, delimiter):
            self.assertFalse(
                cell.startswith(("=", "+", "-", "@")),
                f"导出单元格未中和：{cell!r}",
            )

    def test_table_rows_as_csv_neutralizes(self):
        for payload in INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                self._assert_no_live_formula(format_table_rows_as_csv([(payload, "x")]))

    def test_table_rows_for_clipboard_neutralizes(self):
        for payload in INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                self._assert_no_live_formula(
                    format_table_rows_for_clipboard([(payload, "x")]), delimiter="\t"
                )

    def test_results_as_csv_neutralizes_hostile_name(self):
        # 名称来自远端接口，是最现实的注入入口。
        result = _hostile_result()
        self._assert_no_live_formula(format_results_as_csv([result]))

    def test_results_for_clipboard_neutralizes_hostile_name(self):
        self._assert_no_live_formula(
            format_results_for_clipboard([_hostile_result()]), delimiter="\t"
        )


def _hostile_result():
    """一份除名称是注入载荷外完全正常的分析结果。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from dataclasses import replace

    from stock_advisor.data.sample_data import make_sample_analysis

    sample = make_sample_analysis()
    if isinstance(sample, list):
        sample = sample[0]
    return replace(sample, name="=cmd|' /C calc'!A0")


if __name__ == "__main__":
    unittest.main()
