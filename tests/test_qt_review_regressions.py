"""装配级回归：真实小窗内容、迟到信号、档位摘要与查询身份。"""

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "src"), str(Path(__file__).parent)]

from qt_test_helpers import QtCore, QtWidgets, qt_app, requires_qt, temp_settings
from test_engine import FakeProvider

from domain.models import FundFlow
from domain.symbols import normalize_symbol
from qt_app.app import build_app
from services.batch import BatchProgress, BatchReport
from services.fund_flow import FundFlowResult
from services.workflow import analyze_symbol
from ui.view_text import summarize_results


@requires_qt
class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()
        _, self.window = build_app([], provider=FakeProvider(), settings=temp_settings(self))
        self.addCleanup(self.window.close)
        self.addCleanup(self.window.deleteLater)
        self.page = self.window.individual_page

    def _populate(self):
        outcomes = [
            analyze_symbol(normalize_symbol(code), FakeProvider()) for code in ("600000", "000001")
        ]
        for outcome in outcomes:
            self.page._append_row(outcome)
        self.page._on_finished(BatchReport(total=2, outcomes=outcomes))
        return outcomes

    def test_actual_scroll_contents_fit_the_minimum_window(self):
        self._populate()
        self.window.resize(1000, 680)
        self.window.show()
        for i in range(self.window.tabs.count()):
            with self.subTest(page=self.window.tabs.tabText(i)):
                self.window.tabs.setCurrentIndex(i)
                self.app.processEvents()
                scroll = self.window.tabs.widget(i).findChild(QtWidgets.QScrollArea)
                self.assertLessEqual(scroll.widget().width(), scroll.viewport().width())

    def test_clear_rejects_already_queued_results_and_completion(self):
        outcome = analyze_symbol(normalize_symbol("600000"), FakeProvider())
        with patch.object(self.window.analysis, "start"):
            self.page._on_analyze()
        self.page.clear_all()
        self.page._append_row(outcome)
        self.page._on_progress(BatchProgress(done=1, total=1, outcome=outcome))
        self.page._on_finished(BatchReport(total=1, outcomes=[outcome], cancelled=True))
        self.assertEqual(self.page.model.rowCount(), 0)
        self.assertEqual(self.page._results, [])
        self.assertEqual(self.page.run_status.text(), "已清空")
        self.assertTrue(self.page.analyze_button.isEnabled())
        self.assertTrue(self.page.progress.isHidden())

    def test_tier_after_clear_cannot_resurrect_the_previous_batch(self):
        self._populate()
        self.page.clear_all()
        self.page.tier.set_level(5)
        self.assertEqual(self.page._results, [])
        self.assertFalse(self.page.watch_button.isEnabled())

    def test_tier_during_new_batch_does_not_restore_old_measurements(self):
        self._populate()
        with patch.object(self.window.analysis, "start"):
            self.page._on_analyze()
        self.page.tier.set_level(1)
        self.assertEqual(self.page._results, [])

    def test_tier_refreshes_summary_and_overview_together_with_rows(self):
        self._populate()
        measurements = [
            replace(m, base_factor_sum=30, risk_penalty=0, history_len=90)
            for m in self.page._measurements.values()
        ]
        self.page.tier.set_measurements(measurements)
        before = self.page.overview.text()
        self.page.tier.set_level(1)
        self.assertEqual(self.page.summary.text(), summarize_results(self.page._results, 0))
        self.assertNotEqual(self.page.overview.text(), before)

    def test_active_shortcut_respects_disabled_primary_action(self):
        self.page.analyze_button.setEnabled(False)
        with patch.object(self.page, "_on_analyze") as start:
            self.window.run_active_tab()
        start.assert_not_called()

    def test_position_summary_uses_percentage_points_once(self):
        self._populate()
        self.page._results[0] = replace(self.page._results[0], suggested_position=30)
        self.page._show_details_for(self.page._results[0].symbol.normalized)
        values = [
            w.text()
            for w in self.page.stats.findChildren(QtWidgets.QLabel)
            if w.accessibleName() == "仓位"
        ]
        self.assertEqual(values, ["30%"])

    def test_fund_flow_result_keeps_the_submitted_symbol(self):
        page = self.window.fund_flow_page
        page.input.setText("600519")
        with patch.object(self.window.fund_flow, "start"):
            page._on_query()
        page.input.setText("000001")
        page._on_ready(FundFlowResult(flow=FundFlow(today_main=1e8, main_5d=2e8, recent=[])))
        self.assertIn("600519", page.body.text())
        self.assertNotIn("000001", page.body.text())

    def test_closed_help_dialogs_release_their_widget_tree(self):
        for _ in range(3):
            self.window.open_help().close()
            self.app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        self.assertEqual(self.window._open_dialogs, [])
        self.assertEqual(self.window.findChildren(QtWidgets.QDialog), [])

    def test_copy_uses_the_visible_sorted_row_order(self):
        self._populate()
        self.page.table.horizontalHeader().sectionClicked.emit(0)
        self.page.table.horizontalHeader().sectionClicked.emit(0)
        header = self.page.table.verticalHeader()
        shown = [
            self.page.model.item(header.logicalIndex(i), 0).text() for i in range(header.count())
        ]
        self.assertEqual([row[0] for row in self.page._table_rows()], shown)
        text = self.page.copy_results()
        self.assertLess(text.index(shown[0]), text.index(shown[1]))

    def test_close_does_not_destroy_a_window_with_a_worker_still_running(self):
        from PySide6 import QtGui

        event = QtGui.QCloseEvent()
        with patch.object(self.window.analysis, "shutdown", return_value=False):
            self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertIn("停止后台任务", self.window.statusBar().currentMessage())


if __name__ == "__main__":
    unittest.main()
