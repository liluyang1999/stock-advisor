import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_policy import make_measurement

from domain.models import SpectrumCell
from domain.policy import flip_hint, spectrum

_LEVEL_NAMES = ("稳健", "稳进", "标准", "积极", "激进")


def _cells(actions):
    return [SpectrumCell(i + 1, _LEVEL_NAMES[i], action, False) for i, action in enumerate(actions)]


class SpectrumTests(unittest.TestCase):
    def test_five_cells_current_marked(self):
        cells = spectrum(make_measurement(20), 3)
        self.assertEqual([c.level for c in cells], [1, 2, 3, 4, 5])
        self.assertTrue(cells[2].is_current)
        self.assertEqual(sum(1 for c in cells if c.is_current), 1)

    def test_buy_set_upward_closed(self):
        acts = [c.action for c in spectrum(make_measurement(20), 3)]
        first_buy = next((i for i, a in enumerate(acts) if a == "BUY"), None)
        self.assertIsNotNone(first_buy)
        self.assertTrue(all(a == "BUY" for a in acts[first_buy:]))

    def test_sell_set_downward_closed(self):
        acts = [c.action for c in spectrum(make_measurement(-20), 3)]
        last_sell = max((i for i, a in enumerate(acts) if a == "SELL"), default=None)
        self.assertIsNotNone(last_sell)
        self.assertTrue(all(a == "SELL" for a in acts[: last_sell + 1]))

    def test_flip_hint_text(self):
        hint = flip_hint(spectrum(make_measurement(20), 3))
        self.assertIsInstance(hint, str)
        self.assertIn("积极", hint)  # 此股需到「积极」(L4) 才买入

    def test_flip_hint_all_buy(self):
        hint = flip_hint(spectrum(make_measurement(60, confidence=90), 3))
        self.assertIn("各档均建议买入", hint)


class FlipHintSellSideTests(unittest.TestCase):
    """flip_hint 卖出/观望侧文案（买入侧由 SpectrumTests 覆盖）。直接构造 SpectrumCell 以隔离档位阈值。"""

    def test_all_cells_sell(self):
        hint = flip_hint(_cells(["SELL"] * 5))
        self.assertIn("各档均建议卖出/减仓", hint)

    def test_some_cells_sell_names_the_boundary_level(self):
        # 仅稳健/稳进两档卖出：提示以最后一个卖出档（稳进）为界。
        hint = flip_hint(_cells(["SELL", "SELL", "HOLD", "HOLD", "HOLD"]))
        self.assertIn("及以下偏向卖出/减仓", hint)
        self.assertIn("稳进", hint)

    def test_no_buy_no_sell_is_all_watch(self):
        hint = flip_hint(_cells(["HOLD"] * 5))
        self.assertIn("各档均建议观望", hint)


if __name__ == "__main__":
    unittest.main()
