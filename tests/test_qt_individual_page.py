"""个股页视图契约（REQ-001/010/031/013 / WI-010）。

页面是薄壳：验证它把 controller 信号正确落进表格与状态、按钮态随批量生命周期切换、免责声明常驻。
用事件循环等待，不睡眠。
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:  # pragma: no cover
    QtCore = QtWidgets = None

from stock_advisor.domain.models import CORE_DISCLAIMER, Quote

if QtWidgets is not None:
    from stock_advisor.qt_app.controllers.analysis_controller import AnalysisController
    from stock_advisor.qt_app.pages.individual_page import IndividualPage


def _quote(symbol) -> Quote:
    return Quote(
        symbol=symbol.normalized,
        name="测试",
        last=Decimal("10.00"),
        open=Decimal("10.00"),
        high=Decimal("10.50"),
        low=Decimal("9.50"),
        previous_close=Decimal("9.90"),
        volume=1000,
        amount=1.0,
        turnover_rate=0.5,
        change_pct=0.3,
    )


class _FakeProvider:
    def __init__(self, fail_codes=None):
        self.fail_codes = fail_codes or set()

    def fetch_quote(self, symbol):
        if any(code in symbol.normalized for code in self.fail_codes):
            raise ValueError("行情不可用")
        return _quote(symbol)

    def fetch_history(self, symbol):
        return []


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _wait_for(signal, timeout_ms=5000):
    loop = QtCore.QEventLoop()
    got = []
    signal.connect(lambda *a: (got.append(a), loop.quit()))
    guard = QtCore.QTimer()
    guard.setSingleShot(True)
    guard.timeout.connect(loop.quit)
    guard.start(timeout_ms)
    loop.exec()
    return got


@unittest.skipIf(QtWidgets is None, "PySide6 未安装（pip install --group gui）")
class IndividualPageTests(unittest.TestCase):
    def setUp(self):
        self.app = _app()

    def _page(self, provider):
        controller = AnalysisController(provider)
        self.addCleanup(controller.shutdown)
        page = IndividualPage(controller)
        self.addCleanup(page.deleteLater)
        return page, controller

    def test_disclaimer_is_resident(self):
        page, _ = self._page(_FakeProvider())
        self.assertIn(CORE_DISCLAIMER, page.status.text())  # REQ-031

    def test_analyze_fills_a_row_per_symbol(self):
        page, controller = self._page(_FakeProvider())
        page.input.setText("600519 000001 600000")
        page._on_analyze()
        _wait_for(controller.batch_finished)
        self.assertEqual(page.model.rowCount(), 3)

    def test_failed_symbol_still_gets_a_row(self):
        page, controller = self._page(_FakeProvider(fail_codes={"600519"}))
        page.input.setText("600519 000001")
        page._on_analyze()
        _wait_for(controller.batch_finished)
        self.assertEqual(page.model.rowCount(), 2)  # 失败的也占一行（REQ-010 可见）

    def test_buttons_toggle_across_the_batch_lifecycle(self):
        page, controller = self._page(_FakeProvider())
        self.assertTrue(page.analyze_button.isEnabled())
        self.assertFalse(page.stop_button.isEnabled())
        page.input.setText("600519 000001")
        page._on_analyze()
        self.assertFalse(page.analyze_button.isEnabled())  # 运行中禁用分析
        self.assertTrue(page.stop_button.isEnabled())  # 运行中启用停止
        _wait_for(controller.batch_finished)
        self.assertTrue(page.analyze_button.isEnabled())  # 完成后复位
        self.assertFalse(page.stop_button.isEnabled())

    def test_input_error_is_shown_in_status(self):
        page, controller = self._page(_FakeProvider())
        page.input.setText("   ")  # 空输入
        page._on_analyze()
        _wait_for(controller.batch_finished)
        self.assertIn("输入有误", page.status.text())
        self.assertEqual(page.model.rowCount(), 0)

    def test_finished_status_reports_counts_and_keeps_disclaimer(self):
        page, controller = self._page(_FakeProvider(fail_codes={"600519"}))
        page.input.setText("600519 000001")
        page._on_analyze()
        _wait_for(controller.batch_finished)
        self.assertIn("成功 1", page.status.text())
        self.assertIn("失败 1", page.status.text())
        self.assertIn(CORE_DISCLAIMER, page.status.text())  # 结果态仍常驻免责声明


if __name__ == "__main__":
    unittest.main()
