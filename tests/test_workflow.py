import sys
import threading
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from stock_advisor.data.data_provider import MarketDataError
from stock_advisor.domain.models import DailyBar, FilterCriteria, MarketSnapshot, Quote
from stock_advisor.domain.symbols import normalize_symbol
from stock_advisor.services.workflow import (
    CancelToken,
    ScreeningProvider,
    analyze_symbol,
    screen_and_recommend,
)


class FakeProvider:
    def __init__(self, quote_error=False, history_error=False):
        self.quote_error = quote_error
        self.history_error = history_error

    def fetch_quote(self, symbol):
        if self.quote_error:
            raise MarketDataError("quote failed")
        return Quote(
            symbol=symbol,
            name="测试股票",
            last=10.2,
            open=10.0,
            high=10.3,
            low=9.9,
            previous_close=10.0,
            volume=100000,
            amount=1020000,
            turnover_rate=1.0,
            change_pct=2.0,
        )

    def fetch_history(self, symbol):
        if self.history_error:
            raise MarketDataError("history failed")
        return [
            DailyBar(
                date=f"2026-06-{day + 1:02d}",
                open=10 + day * 0.01,
                close=10.02 + day * 0.01,
                high=10.05 + day * 0.01,
                low=9.95 + day * 0.01,
                volume=90000 + day,
                amount=900000 + day,
                pct_change=0.2,
                turnover_rate=1.0,
            )
            for day in range(40)
        ]


class InvalidQuoteProvider(FakeProvider):
    def fetch_quote(self, symbol):
        quote = super().fetch_quote(symbol)
        return Quote(
            symbol=quote.symbol,
            name=quote.name,
            last=float("nan"),
            open=quote.open,
            high=quote.high,
            low=quote.low,
            previous_close=quote.previous_close,
            volume=quote.volume,
            amount=quote.amount,
            turnover_rate=quote.turnover_rate,
            change_pct=quote.change_pct,
        )


class MalformedHistoryProvider(FakeProvider):
    def fetch_history(self, symbol):
        return None


class WorkflowTests(unittest.TestCase):
    def test_history_failure_returns_degraded_result_instead_of_total_failure(self):
        outcome = analyze_symbol(normalize_symbol("600519"), FakeProvider(history_error=True))

        self.assertTrue(outcome.ok)
        self.assertTrue(outcome.degraded)
        self.assertIsNotNone(outcome.result)
        self.assertTrue(any("历史数据暂时取不到" in risk for risk in outcome.result.risks))
        self.assertFalse(
            any("Remote end" in risk or "connection" in risk for risk in outcome.result.risks)
        )

    def test_quote_failure_returns_failure_outcome(self):
        outcome = analyze_symbol(normalize_symbol("600519"), FakeProvider(quote_error=True))

        self.assertFalse(outcome.ok)
        self.assertIsNone(outcome.result)
        self.assertIn("quote failed", outcome.error)

    def test_invalid_quote_value_returns_failure_outcome(self):
        outcome = analyze_symbol(normalize_symbol("600519"), InvalidQuoteProvider())

        self.assertFalse(outcome.ok)
        self.assertIsNone(outcome.result)
        self.assertIn("实时行情", outcome.error)

    def test_malformed_history_returns_failure_outcome_instead_of_raising(self):
        outcome = analyze_symbol(normalize_symbol("600519"), MalformedHistoryProvider())

        self.assertFalse(outcome.ok)
        self.assertIsNone(outcome.result)
        self.assertIn("分析计算", outcome.error)

    def test_outcome_carries_measurement_for_redecide(self):
        outcome = analyze_symbol(normalize_symbol("600519"), FakeProvider())
        self.assertIsNotNone(outcome.measurement)
        self.assertGreater(len(outcome.measurement.factors), 0)

    def test_level_changes_action_on_same_fetch(self):
        # 同一次行情下，激进档买入数应不少于稳健档（不重新联网，仅换档重判）。
        provider = FakeProvider()
        order = {"SELL": 0, "HOLD": 1, "BUY": 2}
        aggressive = analyze_symbol(normalize_symbol("600519"), provider, level=5)
        conservative = analyze_symbol(normalize_symbol("600519"), provider, level=1)
        self.assertGreaterEqual(order[aggressive.result.action], order[conservative.result.action])


def _snap(code, market_id, change_pct, name="个股"):
    return MarketSnapshot(
        code=code,
        market_id=market_id,
        name=name,
        price=10.0,
        change_pct=change_pct,
        change=0.1,
        volume=100000,
        amount=2.0e8,
        amplitude=3.0,
        turnover_rate=4.0,
        pe_ttm=18.0,
        volume_ratio=1.5,
        total_cap=5.0e10,
        float_cap=4.0e10,
        speed=0.3,
        pb=2.0,
        change_60d=10.0,
        change_ytd=12.0,
    )


class FakeMarketProvider:
    def __init__(self, snapshots, quote_fail_codes=frozenset(), market_error=False):
        self.snapshots = snapshots
        self.quote_fail_codes = frozenset(quote_fail_codes)
        self.market_error = market_error
        self.quote_calls = []
        self.snapshot_calls = 0

    def fetch_market_snapshot(self, page_size=1000, max_pages=12):
        self.snapshot_calls += 1
        if self.market_error:
            raise MarketDataError("全市场行情获取失败")
        return list(self.snapshots)

    def fetch_quote(self, symbol):
        self.quote_calls.append(symbol.code)
        if symbol.code in self.quote_fail_codes:
            raise MarketDataError("quote failed")
        return Quote(
            symbol=symbol,
            name="深度个股",
            last=10.2,
            open=10.0,
            high=10.3,
            low=9.9,
            previous_close=10.0,
            volume=120000,
            amount=1224000,
            turnover_rate=1.0,
            change_pct=2.0,
        )

    def fetch_history(self, symbol):
        return [
            DailyBar(
                date=f"2026-06-{day + 1:02d}",
                open=10 + day * 0.01,
                close=10.02 + day * 0.01,
                high=10.05 + day * 0.01,
                low=9.95 + day * 0.01,
                volume=90000 + day,
                amount=900000 + day,
                pct_change=0.2,
                turnover_rate=1.0,
            )
            for day in range(40)
        ]


class ScreenAndRecommendTests(unittest.TestCase):
    def setUp(self):
        self.snapshots = [
            _snap("600001", "1", 6.0),
            _snap("000002", "0", 4.0),
            _snap("300003", "0", 2.0),
        ]

    def test_deep_mode_ranks_and_attaches_full_analysis(self):
        provider = FakeMarketProvider(self.snapshots)
        report = screen_and_recommend(provider, FilterCriteria(), "momentum", top_n=2, deep=True)

        self.assertEqual(report.total, 3)
        self.assertEqual(report.matched, 3)
        self.assertEqual(len(report.recommendations), 2)
        # 动量排序：涨幅最高在前
        self.assertEqual(report.recommendations[0].snapshot.code, "600001")
        self.assertEqual(report.recommendations[0].rank, 1)
        self.assertIsNotNone(report.recommendations[0].result)
        self.assertEqual(provider.quote_calls, ["600001", "000002"])

    def test_snapshot_only_mode_does_not_fetch_per_stock(self):
        provider = FakeMarketProvider(self.snapshots)
        report = screen_and_recommend(provider, FilterCriteria(), "momentum", top_n=3, deep=False)

        self.assertEqual(len(report.recommendations), 3)
        self.assertTrue(all(rec.result is None for rec in report.recommendations))
        self.assertEqual(provider.quote_calls, [])

    def test_individual_deep_failure_degrades_without_killing_batch(self):
        provider = FakeMarketProvider(self.snapshots, quote_fail_codes={"600001"})
        report = screen_and_recommend(provider, FilterCriteria(), "momentum", top_n=3, deep=True)

        failed = report.recommendations[0]
        self.assertEqual(failed.snapshot.code, "600001")
        self.assertIsNone(failed.result)
        self.assertTrue(failed.error)
        # 其余仍正常深度分析
        self.assertIsNotNone(report.recommendations[1].result)

    def test_empty_result_when_filters_match_nothing(self):
        provider = FakeMarketProvider(self.snapshots)
        report = screen_and_recommend(provider, FilterCriteria(price_max=1.0), "momentum")

        self.assertEqual(report.matched, 0)
        self.assertEqual(report.recommendations, [])
        self.assertEqual(report.total, 3)

    def test_market_fetch_failure_sets_error_not_fake_results(self):
        provider = FakeMarketProvider(self.snapshots, market_error=True)
        report = screen_and_recommend(provider, FilterCriteria(), "momentum")

        self.assertTrue(report.error)
        self.assertEqual(report.recommendations, [])

    def test_cancellation_stops_deep_analysis_early(self):
        provider = FakeMarketProvider(self.snapshots)
        cancel = threading.Event()
        cancel.set()
        report = screen_and_recommend(
            provider, FilterCriteria(), "momentum", top_n=3, deep=True, cancel_event=cancel
        )

        self.assertTrue(report.cancelled)
        self.assertEqual(provider.quote_calls, [])

    def test_progress_callback_receives_each_recommendation(self):
        provider = FakeMarketProvider(self.snapshots)
        seen = []
        screen_and_recommend(
            provider,
            FilterCriteria(),
            "momentum",
            top_n=2,
            deep=True,
            progress_cb=lambda done, total, rec: seen.append((done, total, rec.snapshot.code)),
        )
        self.assertEqual(seen, [(1, 2, "600001"), (2, 2, "000002")])

    def test_invalid_top_n_returns_parameter_error_without_fetching_market(self):
        provider = FakeMarketProvider(self.snapshots)
        report = screen_and_recommend(provider, FilterCriteria(), "momentum", top_n=float("nan"))

        self.assertTrue(report.error)
        self.assertIn("推荐数量", report.error)
        self.assertEqual(report.recommendations, [])
        self.assertEqual(provider.snapshot_calls, 0)

    def test_non_positive_top_n_returns_parameter_error_without_fetching_market(self):
        for top_n in (0, -3):
            with self.subTest(top_n=top_n):
                provider = FakeMarketProvider(self.snapshots)
                report = screen_and_recommend(provider, FilterCriteria(), "momentum", top_n=top_n)

                self.assertTrue(report.error)
                self.assertIn("推荐数量", report.error)
                self.assertEqual(report.recommendations, [])
                self.assertEqual(provider.snapshot_calls, 0)


class BoomQuoteProvider(FakeProvider):
    def fetch_quote(self, symbol):
        raise RuntimeError("boom")


class BoomHistoryProvider(FakeProvider):
    def fetch_history(self, symbol):
        raise RuntimeError("boom")


class BoomMarketProvider(FakeMarketProvider):
    def fetch_market_snapshot(self, page_size=1000, max_pages=12):
        raise RuntimeError("boom")


class WorkflowProtocolTests(unittest.TestCase):
    def test_protocol_method_bodies_raise_not_implemented(self):
        # Protocol 方法体是声明式的 raise NotImplementedError：锁定"父类体不可直接复用"，
        # 防止将来误加默认实现让漏实现的子类被静默放行。
        class Impl(ScreeningProvider):
            def fetch_quote(self, symbol):
                return super().fetch_quote(symbol)

            def fetch_history(self, symbol):
                return super().fetch_history(symbol)

            def fetch_market_snapshot(self, page_size=1000, max_pages=12):
                return super().fetch_market_snapshot(page_size, max_pages)

        class Token(CancelToken):
            def is_set(self):
                return super().is_set()

        impl = Impl()
        with self.assertRaises(NotImplementedError):
            impl.fetch_quote(None)
        with self.assertRaises(NotImplementedError):
            impl.fetch_history(None)
        with self.assertRaises(NotImplementedError):
            impl.fetch_market_snapshot()
        with self.assertRaises(NotImplementedError):
            Token().is_set()


class WorkflowGenericFailureTests(unittest.TestCase):
    # RuntimeError 不在 (MarketDataError, ValueError) 之列（MarketDataError 是其子类，反之不然），
    # 应走"except Exception"兜底分支：给出可展示错误，绝不让后台线程抛裸异常。

    def test_generic_quote_exception_becomes_readable_error(self):
        outcome = analyze_symbol(normalize_symbol("600519"), BoomQuoteProvider())

        self.assertFalse(outcome.ok)
        self.assertIsNone(outcome.result)
        self.assertIn("实时行情获取失败", outcome.error)
        self.assertIn("boom", outcome.error)

    def test_generic_history_exception_degrades_like_market_error(self):
        outcome = analyze_symbol(normalize_symbol("600519"), BoomHistoryProvider())

        self.assertTrue(outcome.ok)
        self.assertTrue(outcome.degraded)
        self.assertEqual(outcome.history, [])
        self.assertTrue(any("历史数据暂时取不到" in risk for risk in outcome.result.risks))

    def test_generic_market_snapshot_exception_becomes_report_error(self):
        report = screen_and_recommend(BoomMarketProvider([]), FilterCriteria(), "momentum")

        self.assertFalse(report.ok)
        self.assertIn("全市场行情获取失败", report.error)
        self.assertIn("boom", report.error)
        self.assertEqual(report.recommendations, [])


class ScreenReportEdgeTests(unittest.TestCase):
    def test_successful_report_is_ok(self):
        provider = FakeMarketProvider([_snap("600001", "1", 2.0)])
        report = screen_and_recommend(provider, FilterCriteria(), "momentum", top_n=1, deep=False)

        self.assertTrue(report.ok)

    def test_unparseable_top_n_returns_parameter_error_without_fetching(self):
        # None/字符串等完全不可解析的 top_n（异常路径，区别于已测的 NaN/非正数路径）
        for top_n in (None, "abc"):
            with self.subTest(top_n=top_n):
                provider = FakeMarketProvider([_snap("600001", "1", 2.0)])
                report = screen_and_recommend(provider, FilterCriteria(), "momentum", top_n=top_n)

                self.assertIn("推荐数量", report.error)
                self.assertEqual(report.recommendations, [])
                self.assertEqual(provider.snapshot_calls, 0)

    def test_deep_analysis_flags_snapshot_with_unknown_market_id(self):
        # 快照市场号未知（既非沪 1 也非深/北 0）：深度分析应明确报"代码市场信息缺失"，
        # 不猜 secid、也不为该股发起任何行情请求
        provider = FakeMarketProvider([_snap("600001", "9", 2.0)])
        report = screen_and_recommend(provider, FilterCriteria(), "momentum", top_n=1, deep=True)

        self.assertTrue(report.ok)
        recommendation = report.recommendations[0]
        self.assertIsNone(recommendation.result)
        self.assertIn("代码市场信息缺失", recommendation.error)
        self.assertEqual(provider.quote_calls, [])


if __name__ == "__main__":
    unittest.main()
