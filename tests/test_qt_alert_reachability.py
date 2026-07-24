"""预警触发必须在任何一页都看得见（REQ-006 / REQ-031 / WI-035）。

这条守的是一个真实发生过的静默失效：`AlertController.alerts_triggered` 只接到「条件预警」页，
往触发记录里追加一行；`IndividualPage.show_alert()` 与它的警示横幅写好了却**没有任何调用方**。
于是用户坐在个股分析页时，价格预警响了也永远不会知道——而"及时告诉你"正是这个功能的全部意义。

老 Tk 版一次做三件事：结果区弹横幅、状态行同文、响一声。这里断言前两件（响铃无法离屏断言），
并且是在**装配好的主窗**上断言，而不是在单个部件上——上一次正是因为只测部件，才漏掉了"没接线"。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import qt_app, requires_qt, temp_settings  # noqa: E402
from test_engine import FakeProvider  # noqa: E402

from domain.alerts import rule_summary  # noqa: E402
from domain.models import CORE_DISCLAIMER, AlertRule  # noqa: E402

try:
    from qt_app.app import AppWindow
except ImportError:  # pragma: no cover - PySide6 是可选的迁移期依赖
    AppWindow = None


def _rule() -> AlertRule:
    return AlertRule(code="sh600519", field="price", op=">=", threshold=1800.0)


@requires_qt
class AlertReachabilityTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()
        self.window = AppWindow(FakeProvider(), settings=temp_settings(self))
        self.addCleanup(self.window.close)

    def test_controller_signal_is_connected_at_the_assembly_point(self):
        """装配点必须把 alerts_triggered 接出去——只写 show_alert 而不接线等于没做。"""
        rule = _rule()
        self.window.alerts.alerts_triggered.emit([rule])

        banner = self.window.individual_page.alert_banner
        self.assertTrue(banner.isVisibleTo(self.window.individual_page), "预警横幅没有显示出来")
        self.assertIn(rule_summary(rule), banner.text())

    def test_alert_reaches_the_status_bar_so_it_survives_a_tab_switch(self):
        """页内横幅只在当前页可见；状态栏是壳级常驻位，切页也带得走。"""
        rule = _rule()
        self.window.tabs.setCurrentIndex(1)  # 用户此刻在「全市场选股」页
        self.window.alerts.alerts_triggered.emit([rule])

        shown = self.window.statusBar().currentMessage()
        self.assertIn(rule_summary(rule), shown)
        self.assertIn(CORE_DISCLAIMER, shown)  # REQ-031：这条消息不许把免责声明挤掉

    def test_empty_trigger_list_does_not_raise_a_blank_banner(self):
        """空列表不该弹一条什么都没写的横幅。

        断言的是"没显示"而非 `isVisible()`——窗口未 show 时 `isVisible()` 恒为 False，
        那样断言无论实现对错都会通过。这里查它是否被显式显示过，以及文本是否还是空的。
        """
        banner = self.window.individual_page.alert_banner
        self.window.alerts.alerts_triggered.emit([])

        self.assertEqual(banner.text(), "")
        self.assertFalse(banner.isVisibleTo(self.window.individual_page))


if __name__ == "__main__":
    unittest.main()
