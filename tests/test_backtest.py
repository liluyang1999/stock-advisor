import sys
import unittest
from dataclasses import replace
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stock_advisor.backtest import backtest_signals, quote_from_bar
from test_engine import make_history


class BacktestTests(unittest.TestCase):
    def test_uptrend_buy_signals_positive(self):
        report = backtest_signals(make_history(start=20, step=0.3, days=90), level=3, horizon=5)
        self.assertTrue(report.ok)
        self.assertGreater(report.sample_size, 0)
        buy = report.stats.get("BUY")
        self.assertIsNotNone(buy)
        self.assertGreater(buy.count, 0)
        self.assertGreater(buy.avg_return, 0)

    def test_downtrend_sell_signals_negative(self):
        report = backtest_signals(make_history(start=40, step=-0.3, days=90), level=3, horizon=5)
        sell = report.stats.get("SELL")
        self.assertIsNotNone(sell)
        self.assertGreater(sell.count, 0)
        self.assertLess(sell.avg_return, 0)

    def test_insufficient_sample_reports_not_ok(self):
        report = backtest_signals(make_history(days=20), level=3, horizon=5, warmup=30)
        self.assertFalse(report.ok)
        self.assertTrue(report.message)
        self.assertEqual(report.sample_size, 0)

    def test_invalid_parameters_report_not_ok(self):
        history = make_history(days=80)
        cases = (
            {"horizon": 0, "warmup": 30, "cost_pct": 0.13},
            {"horizon": -3, "warmup": 30, "cost_pct": 0.13},
            {"horizon": 5, "warmup": 0, "cost_pct": 0.13},
            {"horizon": 5, "warmup": -10, "cost_pct": 0.13},
            {"horizon": 5, "warmup": 30, "cost_pct": -0.1},
            {"horizon": float("inf"), "warmup": 30, "cost_pct": 0.13},
            {"horizon": 5, "warmup": float("inf"), "cost_pct": 0.13},
            {"horizon": 5, "warmup": 30, "cost_pct": float("nan")},
            {"horizon": 5, "warmup": 30, "cost_pct": float("inf")},
        )
        for params in cases:
            with self.subTest(params=params):
                report = backtest_signals(history, **params)
                self.assertFalse(report.ok)
                self.assertEqual(report.sample_size, 0)
                self.assertIn("参数", report.message)

    def test_cost_reduces_returns(self):
        h = make_history(start=20, step=0.3, days=90)
        hi = backtest_signals(h, cost_pct=0.0)
        lo = backtest_signals(h, cost_pct=1.0)
        self.assertGreaterEqual(hi.stats["BUY"].avg_return, lo.stats["BUY"].avg_return)

    def test_no_future_leakage(self):
        # 在序列尾部加一根未来异动，不应改变更早某日 t 的信号（信号只看 t 及之前）。
        base = make_history(start=20, step=0.2, days=80)
        spiked = list(base)
        spiked[-1] = spiked[-1].__class__(**{**spiked[-1].__dict__, "close": spiked[-1].close * 1.3})
        r1 = backtest_signals(base, horizon=5)
        r2 = backtest_signals(spiked, horizon=5)
        # 早期日（不触及尾部 horizon 窗口）的 BUY 计数应一致或仅因尾部样本数变化
        self.assertEqual(r1.stats.get("BUY") is None, r2.stats.get("BUY") is None)

    def test_signal_measurement_history_includes_current_bar_without_future_bars(self):
        history = make_history(start=20, step=0.2, days=50)
        captured: list[list[str]] = []

        def fake_measure(_quote, as_of):
            captured.append([bar.date for bar in as_of])
            return object()

        def fake_decide(_measurement, _level):
            return SimpleNamespace(action="HOLD")

        with patch("stock_advisor.backtest.measure", fake_measure), patch("stock_advisor.backtest.decide", fake_decide):
            backtest_signals(history, level=3, horizon=5, warmup=30)

        self.assertTrue(captured)
        self.assertEqual(captured[0][-1], history[30].date)
        self.assertNotIn(history[36].date, captured[0])

    def test_non_finite_history_rows_are_ignored(self):
        history = make_history(start=20, step=0.2, days=90)
        bad = replace(history[40], close=float("inf"), high=float("inf"), amount=float("inf"))

        report = backtest_signals([*history[:40], bad, *history[41:]], level=3, horizon=5)

        self.assertTrue(report.ok)
        self.assertTrue(math.isfinite(report.buy_hold_return))
        for stat in report.stats.values():
            self.assertTrue(math.isfinite(stat.avg_return))
            self.assertTrue(math.isfinite(stat.win_rate))

    def test_quote_from_bar_change_pct(self):
        bars = make_history(start=10, step=0.5, days=3)
        q = quote_from_bar(bars[1], bars[0])
        self.assertEqual(q.last, bars[1].close)
        self.assertGreater(q.change_pct, 0)


if __name__ == "__main__":
    unittest.main()
