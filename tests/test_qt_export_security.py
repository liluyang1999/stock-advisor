"""TEST-SEC-001（Qt 侧）：个股页导出必须走中和后的格式化函数（REQ-032 / AC-032 / WI-028）。

`test_export_security.py` 在单元层证明 `view_format` 的四条导出路径都中和公式引导符；这里在**集成
层**证明 Qt 个股页的复制/CSV 导出确实经由那些已加固的函数，而非另起一条能绕过中和的旁路——名称
来自远端行情、是最现实的注入入口，页面导出若不走 view_format 就会把 `=cmd|…` 直接送进用户的表格
软件。导出目标路径由系统另存对话框给出、不由数据派生，故无路径穿越攻击面（与 Tk 版一致）。
"""

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtWidgets, qt_app, requires_qt, temp_settings
from test_engine import FakeProvider

from data.sample_data import make_sample_analysis

if QtWidgets is not None:
    from qt_app.controllers.analysis_controller import AnalysisController
    from qt_app.pages.individual_page import IndividualPage

_INJECTION_NAME = "=cmd|' /C calc'!A0"
_FORMULA_LEADS = ("=", "+", "-", "@")


def _hostile_result():
    """一份除名称是注入载荷外完全正常的分析结果（名称模拟远端返回的恶意值）。"""
    sample = make_sample_analysis()
    if isinstance(sample, list):
        sample = sample[0]
    return replace(sample, name=_INJECTION_NAME)


@requires_qt
class IndividualPageExportSecurityTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _page_with_hostile_results(self):
        controller = AnalysisController(FakeProvider())
        self.addCleanup(controller.shutdown)
        page = IndividualPage(controller, temp_settings(self))
        self.addCleanup(page.deleteLater)
        # 直接注入含恶意名称的结果，聚焦验证导出方法本身的中和路由（批量→provider 路径另有测试覆盖）。
        page._results = [_hostile_result()]
        return page

    def _assert_no_live_formula(self, text: str):
        # 载荷含 ASCII 逗号/竖线，逐单元解析过度复杂；这里直接确认原始注入串未以公式引导符原样出现。
        self.assertIn(_INJECTION_NAME, text)  # 原文保留（中和是加前缀，不删改）
        self.assertNotIn(f",{_INJECTION_NAME}", text)  # CSV 单元未以裸载荷紧跟分隔符
        self.assertNotIn(f"\t{_INJECTION_NAME}", text)  # TSV 单元同理
        for line in text.splitlines():
            for cell in line.replace("\t", ",").split(","):
                self.assertFalse(
                    cell.startswith(_FORMULA_LEADS),
                    f"导出单元格未中和：{cell!r}",
                )

    def test_copy_results_neutralizes_hostile_name(self):
        page = self._page_with_hostile_results()
        self._assert_no_live_formula(page.copy_results())

    def test_export_csv_neutralizes_hostile_name(self):
        page = self._page_with_hostile_results()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "结果.csv"
            page.export_csv_to(out)
            content = out.read_text(encoding="utf-8")
        self._assert_no_live_formula(content)

    def test_clipboard_receives_the_neutralized_text(self):
        page = self._page_with_hostile_results()
        text = page.copy_results()
        self.assertEqual(QtWidgets.QApplication.clipboard().text(), text)
        self._assert_no_live_formula(QtWidgets.QApplication.clipboard().text())


if __name__ == "__main__":
    unittest.main()
