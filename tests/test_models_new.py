import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.domain.models import (
    STANDARD_LEVEL,
    LEVEL_NAMES,
    LevelSpec,
    Measurement,
    Decision,
    PositionPlan,
    BacktestStat,
    BacktestReport,
    SpectrumCell,
)


class ModelsTests(unittest.TestCase):
    def test_level_names_and_default(self):
        self.assertEqual(STANDARD_LEVEL, 3)
        self.assertEqual(LEVEL_NAMES[1], "稳健")
        self.assertEqual(LEVEL_NAMES[2], "稳进")
        self.assertEqual(LEVEL_NAMES[3], "标准")
        self.assertEqual(LEVEL_NAMES[4], "积极")
        self.assertEqual(LEVEL_NAMES[5], "激进")

    def test_dataclasses_construct(self):
        spec = LevelSpec(3, "标准", 25, -25, 1.0, 0, 0.01, 0.60, 2.0)
        self.assertEqual(spec.t_buy, 25)
        self.assertEqual(spec.t_sell, -25)

        cell = SpectrumCell(3, "标准", "BUY", True)
        self.assertTrue(cell.is_current)

        plan = PositionPlan(0.2, 100, 1, 10.0, 9.5, 5.0, 11.0, 10.0, 2.0, 1000.0, 50.0, 0.5, "")
        self.assertEqual(plan.lots, 1)
        self.assertEqual(plan.shares, 100)

        stat = BacktestStat("BUY", 12, 0.6, 1.5)
        report = BacktestReport(
            level=3, horizon=5, sample_size=40, stats={"BUY": stat}, buy_hold_return=0.9, note="x"
        )
        self.assertTrue(report.ok)
        self.assertEqual(report.stats["BUY"].count, 12)

    def test_default_stats_is_independent(self):
        a = BacktestReport(level=3, horizon=5, sample_size=0, buy_hold_return=0.0, note="")
        b = BacktestReport(level=3, horizon=5, sample_size=0, buy_hold_return=0.0, note="")
        a.stats["BUY"] = BacktestStat("BUY", 1, 1.0, 1.0)
        self.assertEqual(b.stats, {})


if __name__ == "__main__":
    unittest.main()
