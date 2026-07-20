"""个股页视图契约（REQ-001/010/031/013 / WI-010）。

页面是薄壳：验证它把 controller 信号正确落进表格与状态、按钮态随批量生命周期切换、免责声明常驻。
用事件循环等待，不睡眠。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtWidgets, qt_app, requires_qt, temp_settings, wait_for
from test_engine import FakeProvider

from stock_advisor.domain.models import CORE_DISCLAIMER

if QtWidgets is not None:
    from stock_advisor.qt_app.controllers.analysis_controller import AnalysisController
    from stock_advisor.qt_app.pages.individual_page import IndividualPage


@requires_qt
class IndividualPageTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _page(self, provider):
        controller = AnalysisController(provider)
        self.addCleanup(controller.shutdown)
        page = IndividualPage(controller, temp_settings(self))
        self.addCleanup(page.deleteLater)
        return page, controller

    def test_disclaimer_is_resident(self):
        page, _ = self._page(FakeProvider())
        self.assertIn(CORE_DISCLAIMER, page.status.text())  # REQ-031

    def test_analyze_fills_a_row_per_symbol(self):
        page, controller = self._page(FakeProvider())
        page.input.setText("600519 000001 600000")
        page._on_analyze()
        wait_for(controller.batch_finished)
        self.assertEqual(page.model.rowCount(), 3)

    def test_failed_symbol_still_gets_a_row(self):
        page, controller = self._page(FakeProvider(fail_codes={"600519"}))
        page.input.setText("600519 000001")
        page._on_analyze()
        wait_for(controller.batch_finished)
        self.assertEqual(page.model.rowCount(), 2)  # 失败的也占一行（REQ-010 可见）

    def test_buttons_toggle_across_the_batch_lifecycle(self):
        page, controller = self._page(FakeProvider())
        self.assertTrue(page.analyze_button.isEnabled())
        self.assertFalse(page.stop_button.isEnabled())
        page.input.setText("600519 000001")
        page._on_analyze()
        self.assertFalse(page.analyze_button.isEnabled())  # 运行中禁用分析
        self.assertTrue(page.stop_button.isEnabled())  # 运行中启用停止
        wait_for(controller.batch_finished)
        self.assertTrue(page.analyze_button.isEnabled())  # 完成后复位
        self.assertFalse(page.stop_button.isEnabled())

    def test_input_error_is_shown_in_status(self):
        page, controller = self._page(FakeProvider())
        page.input.setText("   ")  # 空输入
        page._on_analyze()
        wait_for(controller.batch_finished)
        self.assertIn("输入有误", page.status.text())
        self.assertEqual(page.model.rowCount(), 0)

    def test_finished_status_reports_counts_and_keeps_disclaimer(self):
        page, controller = self._page(FakeProvider(fail_codes={"600519"}))
        page.input.setText("600519 000001")
        page._on_analyze()
        wait_for(controller.batch_finished)
        self.assertIn("成功 1", page.status.text())
        self.assertIn("失败 1", page.status.text())
        self.assertIn(CORE_DISCLAIMER, page.status.text())  # 结果态仍常驻免责声明

    # --- 复制 / CSV 导出（WI-018 / TEST-QT-HELP-001）---

    def test_export_buttons_enable_only_after_results(self):
        page, controller = self._page(FakeProvider())
        self.assertFalse(page.copy_button.isEnabled())  # 初始无结果 → 禁用
        self.assertFalse(page.export_button.isEnabled())
        page.input.setText("600519 000001")
        page._on_analyze()
        wait_for(controller.batch_finished)
        self.assertTrue(page.copy_button.isEnabled())  # 有结果 → 放开
        self.assertTrue(page.export_button.isEnabled())

    def test_export_buttons_redisable_when_a_new_batch_starts(self):
        page, controller = self._page(FakeProvider())
        page.input.setText("600519")
        page._on_analyze()
        wait_for(controller.batch_finished)
        self.assertTrue(page.copy_button.isEnabled())
        page._on_analyze()  # 新一轮开始 → 立即禁用，避免复制上一轮的陈旧结果
        self.assertFalse(page.copy_button.isEnabled())
        self.assertFalse(page.export_button.isEnabled())

    def test_copy_results_puts_disclaimer_bearing_text_on_clipboard(self):
        page, controller = self._page(FakeProvider())
        page.input.setText("600519 000001")
        page._on_analyze()
        wait_for(controller.batch_finished)
        text = page.copy_results()
        self.assertIn(CORE_DISCLAIMER, text)  # 导出件自带免责声明
        self.assertEqual(QtWidgets.QApplication.clipboard().text(), text)

    def test_export_csv_writes_file_with_header_and_disclaimer(self):
        import tempfile

        page, controller = self._page(FakeProvider())
        page.input.setText("600519 000001")
        page._on_analyze()
        wait_for(controller.batch_finished)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "结果.csv"
            page.export_csv_to(out)
            content = out.read_text(encoding="utf-8")
        self.assertIn("代码", content)  # 表头
        self.assertIn(CORE_DISCLAIMER, content)  # 免责声明页脚
        self.assertIn("模型", content.strip().splitlines()[-1])  # 声明在末行


if __name__ == "__main__":
    unittest.main()
