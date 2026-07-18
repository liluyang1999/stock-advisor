"""仓位与回测工作台契约（REQ-004/021 / WI-012 / TEST-POS-001 / TEST-BT-002）。

纯展示：把既有 `position_plan` 与 `backtest_signals` 的输出渲染到部件。回测的无未来泄漏保证由
domain 层与 WI-008 的 look-ahead 测试守住；此处验证展示层如实呈现成本/基线/样本/免责（caveats），
不自造数字、不改口径。
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from PySide6 import QtWidgets
except ImportError:  # pragma: no cover
    QtWidgets = None

from qt_test_helpers import qt_app, requires_qt
from test_engine import make_history, make_measurement

from stock_advisor.domain.backtest import backtest_signals
from stock_advisor.domain.models import CORE_DISCLAIMER
from stock_advisor.domain.policy import position_plan

if QtWidgets is not None:
    from stock_advisor.qt_app.widgets.position_plan import PositionPlanView


@requires_qt
class PositionPlanViewTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def test_disclaimer_is_resident(self):
        view = PositionPlanView()
        self.assertIn(CORE_DISCLAIMER, view.disclaimer.text())  # REQ-031

    def test_shows_the_position_plan_numbers_verbatim(self):
        plan = position_plan(make_measurement(), 3, Decimal("100000.00"))
        view = PositionPlanView()
        view.show_plan(plan)
        body = view.plan_label.text()
        # 展示层如实呈现引擎算出的数字，不自造。
        self.assertIn(str(plan.shares), body)
        self.assertIn(str(plan.entry), body)
        self.assertIn(str(plan.stop_price), body)
        self.assertIn(str(plan.target_price), body)

    def test_shows_backtest_cost_baseline_and_sample(self):
        report = backtest_signals(make_history(start=20.0, step=0.25, days=80), level=3)
        view = PositionPlanView()
        view.show_backtest(report)
        body = view.backtest_label.text()
        self.assertIn(str(report.sample_size), body)  # 样本
        self.assertIn(str(report.buy_hold_return), body)  # 基线（买入持有）
        self.assertIn(report.note, body)  # caveats/免责口径

    def test_backtest_note_carries_the_no_look_ahead_caveat(self):
        # REQ-021：回测结果必须带"用当日及之前数据、不预示未来"的说明；展示层原样透出。
        report = backtest_signals(make_history(start=20.0, step=0.25, days=80), level=3)
        view = PositionPlanView()
        view.show_backtest(report)
        self.assertIn("未来", view.backtest_label.text())

    def test_insufficient_sample_backtest_shows_its_message_not_fake_numbers(self):
        # 样本不足时引擎返回 ok=False + message；展示层显示该说明，绝不编造胜率。
        short = make_history(start=20.0, step=0.25, days=20)
        report = backtest_signals(short, level=3)
        self.assertFalse(report.ok)
        view = PositionPlanView()
        view.show_backtest(report)
        self.assertIn(report.message, view.backtest_label.text())

    def test_clear_resets_but_keeps_disclaimer(self):
        view = PositionPlanView()
        view.show_plan(position_plan(make_measurement(), 3, Decimal("100000.00")))
        view.clear()
        self.assertEqual(view.plan_label.text(), "—")
        self.assertIn(CORE_DISCLAIMER, view.disclaimer.text())


class DisclaimerStaticDetectionTests(unittest.TestCase):
    def test_module_references_the_core_disclaimer(self):
        src = (
            Path(__file__).resolve().parents[1]
            / "src/stock_advisor/qt_app/widgets/position_plan.py"
        ).read_text(encoding="utf-8")
        self.assertIn("CORE_DISCLAIMER", src)


if __name__ == "__main__":
    unittest.main()
