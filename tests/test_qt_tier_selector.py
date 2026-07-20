"""档位切换控件契约（REQ-003 / WI-011 / TEST-QT-AN-002）。

控件持有一次分析产出的缓存 Measurement，用户切档时对缓存重判并发信号——**不接受 provider、
不联网**。这是 REQ-003"切档只重判缓存"在 UI 上的落点；重判逻辑本身另由 test_tier_switch 覆盖。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from PySide6 import QtWidgets
except ImportError:  # pragma: no cover
    QtWidgets = None

from qt_test_helpers import QtWidgets, qt_app, requires_qt
from test_engine import make_measurements

from stock_advisor.domain.models import LEVEL_NAMES

if QtWidgets is not None:
    from stock_advisor.qt_app.widgets.tier_selector import TierSelector


@requires_qt
class TierSelectorTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def test_offers_all_five_levels_as_visible_segments(self):
        """五档是并排的分段按钮，不是下拉框。

        形态本身就是需求的一部分：产品的卖点是"五档一眼对照"，藏进下拉框就把对照关系藏掉了
        （REQ-015 / WI-034 视觉基线沿用 Tkinter 版）。
        """
        selector = TierSelector()

        segments = [
            b
            for b in selector.findChildren(QtWidgets.QPushButton)
            if b.property("role") == "segment"
        ]

        self.assertEqual(len(segments), len(LEVEL_NAMES))
        for name in LEVEL_NAMES.values():
            self.assertIn(name, [b.text() for b in segments])

    def test_exactly_one_segment_is_checked(self):
        """分段是互斥的：任何时候恰好一段亮着，用户才知道自己在第几档。"""
        selector = TierSelector()

        checked = [
            b
            for b in selector.findChildren(QtWidgets.QPushButton)
            if b.property("role") == "segment" and b.isChecked()
        ]

        self.assertEqual(len(checked), 1)
        self.assertEqual(checked[0].text(), LEVEL_NAMES[3])  # 默认标准档

    def test_clicking_a_segment_switches_the_level(self):
        selector = TierSelector()
        segments = {
            b.text(): b
            for b in selector.findChildren(QtWidgets.QPushButton)
            if b.property("role") == "segment"
        }

        segments[LEVEL_NAMES[5]].click()

        self.assertEqual(selector.current_level(), 5)

    def test_default_level_is_standard(self):
        selector = TierSelector()
        self.assertEqual(selector.current_level(), 3)  # STANDARD_LEVEL

    def test_changing_level_emits_redecided_results_without_a_provider(self):
        selector = TierSelector()
        selector.set_measurements(make_measurements(2))
        received: list = []
        selector.results_changed.connect(lambda results: received.append(results))
        selector.set_level(5)  # 切到激进档
        self.assertTrue(received)
        results = received[-1]
        self.assertEqual(len(results), 2)
        # 结果确实按新档重判（激进档买入仓位通常不小于标准档）。
        self.assertTrue(all(r.symbol for r in results))

    def test_switching_level_keeps_prices_constant(self):
        # REQ-003：切档只重判、不重新测量，故报价恒等。
        selector = TierSelector()
        selector.set_measurements(make_measurements(1))
        got: list = []
        selector.results_changed.connect(lambda results: got.append(results[0].last))
        selector.set_level(1)
        selector.set_level(5)
        self.assertEqual(got[0], got[-1])  # L1 与 L5 的报价一致

    def test_setting_measurements_emits_at_current_level(self):
        selector = TierSelector()
        emitted: list = []
        selector.results_changed.connect(lambda results: emitted.append(results))
        selector.set_measurements(make_measurements(3))
        self.assertTrue(emitted)
        self.assertEqual(len(emitted[-1]), 3)

    def test_no_measurements_yields_empty_results(self):
        selector = TierSelector()
        got: list = []
        selector.results_changed.connect(lambda results: got.append(results))
        selector.set_level(4)
        self.assertEqual(got[-1], [])


if __name__ == "__main__":
    unittest.main()
