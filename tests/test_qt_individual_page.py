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

from domain.models import CORE_DISCLAIMER

if QtWidgets is not None:
    from qt_app.controllers.analysis_controller import AnalysisController
    from qt_app.pages.individual_page import IndividualPage


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
        page.input.setPlainText("600519 000001 600000")
        page._on_analyze()
        wait_for(controller.batch_finished)
        self.assertEqual(page.model.rowCount(), 3)

    def test_failed_symbol_still_gets_a_row(self):
        page, controller = self._page(FakeProvider(fail_codes={"600519"}))
        page.input.setPlainText("600519 000001")
        page._on_analyze()
        wait_for(controller.batch_finished)
        self.assertEqual(page.model.rowCount(), 2)  # 失败的也占一行（REQ-010 可见）

    def test_buttons_toggle_across_the_batch_lifecycle(self):
        page, controller = self._page(FakeProvider())
        self.assertTrue(page.analyze_button.isEnabled())
        self.assertFalse(page.stop_button.isEnabled())
        page.input.setPlainText("600519 000001")
        page._on_analyze()
        self.assertFalse(page.analyze_button.isEnabled())  # 运行中禁用分析
        self.assertTrue(page.stop_button.isEnabled())  # 运行中启用停止
        wait_for(controller.batch_finished)
        self.assertTrue(page.analyze_button.isEnabled())  # 完成后复位
        self.assertFalse(page.stop_button.isEnabled())

    def test_input_error_is_shown_in_status(self):
        page, controller = self._page(FakeProvider())
        page.input.setPlainText("   ")  # 空输入
        page._on_analyze()
        wait_for(controller.batch_finished)
        self.assertIn("输入有误", page.run_status.text())
        self.assertEqual(page.model.rowCount(), 0)

    def test_finished_status_reports_counts_and_keeps_disclaimer(self):
        """成败计数与免责声明分居两处，且都必须可见。

        老 Tkinter 版把"这次跑得怎么样"（summary/status）与常驻免责声明分开放置，免责声明不随
        每次运行被覆写；Qt 版此前把两者拼进同一个 label，于是每条状态消息都要手工再拼一遍
        CORE_DISCLAIMER，漏拼一次免责声明就消失了（REQ-031）。
        """
        page, controller = self._page(FakeProvider(fail_codes={"600519"}))
        page.input.setPlainText("600519 000001")
        page._on_analyze()
        wait_for(controller.batch_finished)
        self.assertIn("完成 1 只", page.summary.text())
        self.assertIn("失败 1 只", page.summary.text())
        self.assertIn(CORE_DISCLAIMER, page.status.text())  # 结果态仍常驻免责声明

    def test_tier_switch_keeps_sort_keys_in_sync_with_displayed_values(self):
        """切档就地刷新必须同步排序键（Qt.UserRole），否则显示新档数字、排序仍按旧档。

        行在默认档（L3）用 `make_row` 追加，UserRole 存的是当时的排序值；切到别的档后
        `_refresh_rows` 就地改了显示文本却漏拷 UserRole，于是 `_HeaderSort` 会按陈旧的旧档
        键排序，点列头得到与屏上数字矛盾的顺序。不变量：任一单元格的排序键恒等于其当前显示
        文本的排序值。
        """
        from PySide6 import QtCore

        from qt_app.widgets.table_utils import cell_sort_value

        page, controller = self._page(FakeProvider())
        page.input.setPlainText("600519 000001")
        page._on_analyze()
        wait_for(controller.batch_finished)

        before = {
            (r, c): page.model.item(r, c).text()
            for r in range(page.model.rowCount())
            for c in range(page.model.columnCount())
        }
        page.tier.set_level(1)  # 切到 L1（稳健），触发缓存重判 + 就地刷新

        changed = 0
        for r in range(page.model.rowCount()):
            for c in range(page.model.columnCount()):
                item = page.model.item(r, c)
                if item is None:
                    continue
                if item.text() != before[(r, c)]:
                    changed += 1
                self.assertEqual(
                    item.data(QtCore.Qt.ItemDataRole.UserRole),
                    cell_sort_value(item.text()),
                    msg=f"row={r} col={c} text={item.text()!r} 的排序键与显示值脱节",
                )
        self.assertGreater(changed, 0, "切档应至少改变一个单元格，否则本测试无法暴露脱节")

    # --- 复制 / CSV 导出（WI-018 / TEST-QT-HELP-001）---

    def test_export_buttons_enable_only_after_results(self):
        page, controller = self._page(FakeProvider())
        self.assertFalse(page.copy_button.isEnabled())  # 初始无结果 → 禁用
        self.assertFalse(page.export_button.isEnabled())
        page.input.setPlainText("600519 000001")
        page._on_analyze()
        wait_for(controller.batch_finished)
        self.assertTrue(page.copy_button.isEnabled())  # 有结果 → 放开
        self.assertTrue(page.export_button.isEnabled())

    def test_export_buttons_redisable_when_a_new_batch_starts(self):
        page, controller = self._page(FakeProvider())
        page.input.setPlainText("600519")
        page._on_analyze()
        wait_for(controller.batch_finished)
        self.assertTrue(page.copy_button.isEnabled())
        page._on_analyze()  # 新一轮开始 → 立即禁用，避免复制上一轮的陈旧结果
        self.assertFalse(page.copy_button.isEnabled())
        self.assertFalse(page.export_button.isEnabled())

    def test_copy_results_puts_disclaimer_bearing_text_on_clipboard(self):
        page, controller = self._page(FakeProvider())
        page.input.setPlainText("600519 000001")
        page._on_analyze()
        wait_for(controller.batch_finished)
        text = page.copy_results()
        self.assertIn(CORE_DISCLAIMER, text)  # 导出件自带免责声明
        self.assertEqual(QtWidgets.QApplication.clipboard().text(), text)

    def test_export_csv_writes_file_with_header_and_disclaimer(self):
        import tempfile

        page, controller = self._page(FakeProvider())
        page.input.setPlainText("600519 000001")
        page._on_analyze()
        wait_for(controller.batch_finished)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "结果.csv"
            page.export_csv_to(out)
            content = out.read_text(encoding="utf-8")
        self.assertIn("代码", content)  # 表头
        self.assertIn(CORE_DISCLAIMER, content)  # 免责声明页脚
        self.assertIn("模型", content.strip().splitlines()[-1])  # 声明在末行


@requires_qt
class FailureRowReadabilityTests(unittest.TestCase):
    """失败原因必须读得到：行上有全文 tooltip，选中失败行时摘要区如实显示原因。"""

    def setUp(self):
        self.app = qt_app()

    def _page(self, provider):
        from qt_app.controllers.analysis_controller import AnalysisController
        from qt_app.pages.individual_page import IndividualPage

        controller = AnalysisController(provider)
        self.addCleanup(controller.shutdown)
        page = IndividualPage(controller, temp_settings(self))
        self.addCleanup(page.deleteLater)
        return page, controller

    def test_failed_row_carries_the_full_reason_as_tooltip(self):
        page, controller = self._page(FakeProvider(fail_codes={"000001"}))
        page.input.setPlainText("600519 000001")
        page._on_analyze()
        wait_for(controller.batch_finished)

        failed = None
        for row in range(page.model.rowCount()):
            if page.model.item(row, 2).text() == "失败":
                failed = row
        self.assertIsNotNone(failed, "应有一条失败行")
        tooltip = page.model.item(failed, 0).toolTip()
        self.assertIn("000001", tooltip)
        self.assertTrue(len(tooltip) >= 6, f"tooltip 应是完整原因：{tooltip!r}")

    def test_selecting_a_failed_row_shows_the_reason_in_the_summary(self):
        page, controller = self._page(FakeProvider(fail_codes={"000001"}))
        page.input.setPlainText("600519 000001")
        page._on_analyze()
        wait_for(controller.batch_finished)

        for row in range(page.model.rowCount()):
            if page.model.item(row, 2).text() == "失败":
                page.table.selectRow(row)
        hint = page.summary_card.hint_text()
        self.assertIn("失败", hint)
        self.assertIn("000001", hint)


if __name__ == "__main__":
    unittest.main()
