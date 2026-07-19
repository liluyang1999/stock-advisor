"""预警页视图契约（REQ-006/031 / WI-016 / TEST-QT-ALERT-001）。

薄壳：规则表落进 QTableView、监控开关切换、触发经信号追加到触发记录、免责声明常驻。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import qt_app, requires_qt, wait_for
from test_engine import FakeProvider

from stock_advisor.domain.models import CORE_DISCLAIMER, AlertRule

if True:
    try:
        from stock_advisor.qt_app.controllers.alert_controller import AlertController
        from stock_advisor.qt_app.pages.alerts_page import AlertsPage
    except ImportError:  # pragma: no cover
        AlertController = AlertsPage = None


def _rule(code, threshold=5.0):
    return AlertRule(code=code, field="price", op=">=", threshold=threshold, enabled=True)


@requires_qt
class AlertsPageTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _page(self, provider=None):
        controller = AlertController(provider or FakeProvider())
        self.addCleanup(controller.shutdown)
        page = AlertsPage(controller)
        self.addCleanup(page.deleteLater)
        return page, controller

    def test_disclaimer_is_resident(self):
        page, _ = self._page()
        self.assertIn(CORE_DISCLAIMER, page.status.text())  # REQ-031

    def test_set_rules_fills_the_rule_table(self):
        page, _ = self._page()
        page.set_rules([_rule("sh600519"), _rule("sz000001")])
        self.assertEqual(page.rule_model.rowCount(), 2)

    def test_monitor_toggle_starts_and_stops(self):
        page, controller = self._page()
        page.set_rules([_rule("sh600519")])
        page.monitor_button.setChecked(True)  # 触发 toggled(True)
        self.assertTrue(controller.is_running())
        self.assertEqual(page.monitor_button.text(), "停止监控")
        page.monitor_button.setChecked(False)
        self.assertFalse(controller.is_running())
        self.assertEqual(page.monitor_button.text(), "开始监控")

    def test_triggered_alert_appears_in_the_log(self):
        page, controller = self._page()
        page.set_rules([_rule("sh600519", threshold=5.0)])
        page.monitor_button.setChecked(True)
        wait_for(controller.alerts_triggered)
        # rule_summary 用 normalize_symbol 显示规范化代码（SH.600519），断言其可见即可。
        self.assertIn("600519", page.triggered.toPlainText())

    def test_status_keeps_disclaimer_while_monitoring(self):
        page, controller = self._page()
        page.set_rules([_rule("sh600519")])
        page.monitor_button.setChecked(True)
        self.assertIn(CORE_DISCLAIMER, page.status.text())


class DisclaimerStaticDetectionTests(unittest.TestCase):
    def test_module_references_the_core_disclaimer(self):
        src = (
            Path(__file__).resolve().parents[1] / "src/stock_advisor/qt_app/pages/alerts_page.py"
        ).read_text(encoding="utf-8")
        self.assertIn("CORE_DISCLAIMER", src)


if __name__ == "__main__":
    unittest.main()
