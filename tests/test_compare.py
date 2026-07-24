import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_engine import make_history, make_quote

from domain.compare import build_comparison_rows
from domain.engine import build_analysis_result, measure
from domain.policy import decide
from ui.view_format import format_comparison_row


def entry(code, last_price, cost=None, shares=None, step=0.25):
    history = make_history(start=20, step=step, days=80)
    quote = make_quote(
        code,
        last=last_price,
        open_price=last_price - 0.5,
        high=last_price + 0.3,
        low=last_price - 0.6,
        previous_close=last_price - 0.4,
        volume=200000,
    )
    measurement = measure(quote, history)
    result = build_analysis_result(measurement, decide(measurement, 3))
    return {
        "result": result,
        "measurement": measurement,
        "risk": "低",
        "cost": cost,
        "shares": shares,
    }


class CompareTests(unittest.TestCase):
    def test_pl_with_cost_and_shares(self):
        row = build_comparison_rows([entry("600519", 41.0, cost=40.0, shares=100)])[0]
        self.assertAlmostEqual(row.pl_pct, (41.0 - 40.0) / 40.0 * 100, places=2)
        self.assertAlmostEqual(row.pl_amount, (41.0 - 40.0) * 100, places=2)

    def test_cost_without_shares_has_pct_only(self):
        row = build_comparison_rows([entry("600519", 41.0, cost=40.0)])[0]
        self.assertIsNotNone(row.pl_pct)
        self.assertIsNone(row.pl_amount)

    def test_no_cost_means_no_pl(self):
        row = build_comparison_rows([entry("600519", 41.0)])[0]
        self.assertIsNone(row.pl_pct)
        self.assertIsNone(row.pl_amount)

    def test_non_finite_price_cost_and_shares_do_not_create_pl(self):
        item = entry("600519", 41.0, cost=float("inf"), shares=float("nan"))
        item["result"] = replace(item["result"], last=float("inf"))

        row = build_comparison_rows([item])[0]

        self.assertIsNone(row.last)
        self.assertIsNone(row.cost)
        self.assertIsNone(row.pl_pct)
        self.assertIsNone(row.pl_amount)

    def test_non_finite_market_values_display_as_missing_in_comparison(self):
        item = entry("600519", 41.0)
        item["result"] = replace(item["result"], last=float("inf"), change_pct=float("nan"))

        row = build_comparison_rows([item])[0]
        display = format_comparison_row(row)

        self.assertEqual(display[2], "—")
        self.assertEqual(display[3], "—")

    def test_sorted_by_score_desc(self):
        rows = build_comparison_rows(
            [entry("600519", 41.0, step=0.25), entry("000001", 21.0, step=-0.22)]
        )
        self.assertEqual(len(rows), 2)
        self.assertGreaterEqual(rows[0].score, rows[1].score)

    def test_level_hint_present(self):
        row = build_comparison_rows([entry("600519", 41.0)])[0]
        self.assertTrue(row.level_hint)


if __name__ == "__main__":
    unittest.main()
