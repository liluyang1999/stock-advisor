import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stock_advisor.policy import spectrum, flip_hint
from test_policy import make_measurement


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


if __name__ == "__main__":
    unittest.main()
