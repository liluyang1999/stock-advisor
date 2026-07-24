import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from domain.engine import (
    analyze_stock,
    average_true_range_percent,
    bollinger_position,
    macd_snapshot,
    moving_average,
    rsi,
    support_resistance,
)
from domain.models import DailyBar, Quote
from domain.symbols import normalize_symbol


def make_quote(code, last, open_price, high, low, previous_close, volume=500000):
    return Quote(
        symbol=normalize_symbol(code),
        name="测试股票",
        last=last,
        open=open_price,
        high=high,
        low=low,
        previous_close=previous_close,
        volume=volume,
        amount=volume * last,
        turnover_rate=2.0,
        change_pct=(last - previous_close) / previous_close * 100,
    )


def make_history(start=10.0, step=0.1, days=80, volume=100000):
    rows = []
    price = start
    for day in range(days):
        close = price + step
        rows.append(
            DailyBar(
                date=f"2026-04-{day + 1:02d}",
                open=price,
                close=close,
                high=max(price, close) + 0.05,
                low=min(price, close) - 0.05,
                volume=volume + day * 100,
                amount=(volume + day * 100) * close,
                pct_change=(close - price) / price * 100,
                turnover_rate=1.5,
            )
        )
        price = close
    return rows


# --- 跨测试共享的框架无关夹具（原先在 test_qt_*/test_batch_controller 里各写一份）---


def fake_quote(symbol):
    """给定一个 StockSymbol，构造一份最小可用的 Decimal 报价（供 FakeProvider 用）。

    `Quote.symbol` 契约类型是 StockSymbol（真实 provider 亦然）；此处如实传 StockSymbol 本身，
    而非它的 normalized 字符串，否则下游 `result.symbol.display`（如 CSV/剪贴板导出）会拿到 str
    而炸。曾用 `.normalized` 只是碰巧没有测试走到需要 `.display` 的导出路径。
    """
    from decimal import Decimal

    return Quote(
        symbol=symbol,
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


class FakeProvider:
    """按 symbol 决定成功/抛错的假 provider（现有两版的超集：带 .calls 记录 + 含代码的错误消息）。"""

    def __init__(self, fail_codes=None):
        self.fail_codes = set(fail_codes or ())
        self.calls: list[str] = []

    def fetch_quote(self, symbol):
        self.calls.append(symbol.normalized)
        if any(code in symbol.normalized for code in self.fail_codes):
            raise ValueError(f"{symbol.normalized} 行情不可用")
        return fake_quote(symbol)

    def fetch_history(self, symbol):
        return []


def make_measurement(code="600519", last=41.0):
    """一次已完成的客观测量，供切档/结果视图等"分析已完成"场景复用。"""
    from domain.engine import measure

    history = make_history(start=20.0, step=0.25, days=80)
    quote = make_quote(code, last, 40.2, 41.2, 39.9, 40.0, volume=260000)
    return measure(quote, history)


def make_measurements(n=2):
    return [make_measurement(f"60000{i}", 41.0 + i) for i in range(n)]


class IndicatorTests(unittest.TestCase):
    def test_moving_average_uses_latest_window(self):
        self.assertAlmostEqual(moving_average([1, 2, 3, 4, 5], 3), 4.0)
        self.assertIsNone(moving_average([1, 2], 3))

    def test_rsi_reports_neutral_for_flat_prices(self):
        self.assertAlmostEqual(rsi([10.0] * 20), 50.0)

    def test_macd_bollinger_atr_and_support_resistance_are_calculated(self):
        history = make_history(start=10, step=0.15, days=40, volume=100000)
        closes = [bar.close for bar in history]

        macd = macd_snapshot(closes)
        position = bollinger_position(closes, closes[-1])
        atr = average_true_range_percent(history, closes[-1])
        support, resistance = support_resistance(history, window=20)

        self.assertIsNotNone(macd)
        self.assertGreater(macd[0], 0)
        self.assertIsNotNone(position)
        self.assertGreater(position, 0.5)
        self.assertIsNotNone(atr)
        self.assertGreater(atr, 0)
        self.assertLess(support, resistance)

    def test_indicators_reject_non_positive_windows(self):
        history = make_history(start=10, step=0.15, days=40, volume=100000)
        closes = [bar.close for bar in history]

        self.assertIsNone(moving_average(closes, 0))
        self.assertIsNone(moving_average(closes, -5))
        self.assertIsNone(bollinger_position(closes, closes[-1], window=0))
        self.assertIsNone(average_true_range_percent(history, closes[-1], period=0))
        self.assertEqual(support_resistance(history, window=0), (None, None))
        self.assertIsNone(rsi(closes, period=0))

    def test_indicators_do_not_return_non_finite_values_for_bad_inputs(self):
        closes = [10.0 + index * 0.1 for index in range(40)]
        with_nan = [*closes[:-1], float("nan")]
        with_inf = [*closes[:-1], float("inf")]
        history = make_history(start=10, step=0.15, days=40, volume=100000)
        bad_history = [*history[:-1], replace(history[-1], high=float("inf"))]

        self.assertIsNone(moving_average(with_nan, 5))
        self.assertIsNone(rsi(with_inf, period=14))
        self.assertIsNone(macd_snapshot(with_inf))
        self.assertIsNone(bollinger_position(with_nan, closes[-1]))
        self.assertIsNone(bollinger_position(closes, float("inf")))
        self.assertIsNone(average_true_range_percent(bad_history, closes[-1]))
        support, resistance = support_resistance(bad_history, window=20)
        self.assertTrue(support is None or math.isfinite(support))
        self.assertTrue(resistance is None or math.isfinite(resistance))


class StrategyEngineTests(unittest.TestCase):
    def test_buy_signal_for_confirmed_uptrend_with_intraday_strength(self):
        history = make_history(start=20, step=0.25, days=80, volume=100000)
        quote = make_quote(
            "600519",
            last=41.0,
            open_price=40.2,
            high=41.2,
            low=39.9,
            previous_close=40.0,
            volume=260000,
        )

        result = analyze_stock(quote, history)

        self.assertEqual(result.action, "BUY")
        self.assertGreaterEqual(result.score, 25)
        self.assertTrue(any("均线" in reason for reason in result.reasons))
        self.assertTrue(any("量能" in reason for reason in result.reasons))
        self.assertGreater(result.suggested_position, 0)
        self.assertTrue(result.forecast_label)
        self.assertTrue(result.factor_scores)
        self.assertTrue(result.recent_closes)
        self.assertIsNotNone(result.indicators.macd_histogram)
        self.assertIsNotNone(result.indicators.bollinger_position)
        self.assertIsNotNone(result.indicators.atr_percent)

    def test_sell_signal_for_breakdown_and_weak_intraday_close(self):
        history = make_history(start=40, step=-0.22, days=80, volume=180000)
        quote = make_quote(
            "000001",
            last=21.0,
            open_price=22.2,
            high=22.4,
            low=20.9,
            previous_close=22.0,
            volume=260000,
        )

        result = analyze_stock(quote, history)

        self.assertEqual(result.action, "SELL")
        self.assertLessEqual(result.score, -25)
        self.assertTrue(any("弱势" in reason or "跌破" in reason for reason in result.reasons))

    def test_hold_signal_for_mixed_evidence(self):
        history = make_history(start=30, step=0.0, days=80, volume=100000)
        quote = make_quote(
            "300750",
            last=30.1,
            open_price=30.0,
            high=30.5,
            low=29.7,
            previous_close=30.0,
            volume=105000,
        )

        result = analyze_stock(quote, history)

        self.assertEqual(result.action, "HOLD")
        self.assertLess(abs(result.score), 25)
        self.assertTrue(result.risks)
        self.assertLessEqual(result.suggested_position, 40)

    def test_non_finite_history_rows_do_not_reach_result(self):
        history = make_history(start=20, step=0.2, days=80, volume=100000)
        bad = replace(
            history[-1],
            close=float("inf"),
            high=float("inf"),
            amount=float("inf"),
            pct_change=float("nan"),
        )
        quote = make_quote(
            "600519",
            last=36.0,
            open_price=35.6,
            high=36.2,
            low=35.4,
            previous_close=35.5,
            volume=260000,
        )

        result = analyze_stock(quote, [*history[:-1], bad])

        self.assertTrue(all(math.isfinite(value) for value in result.recent_closes))
        for value in (
            result.indicators.support,
            result.indicators.resistance,
            result.indicators.atr_percent,
            result.expected_move_pct,
        ):
            self.assertTrue(value is None or math.isfinite(value))


if __name__ == "__main__":
    unittest.main()
