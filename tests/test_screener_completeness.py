"""筛选完整度与失败隔离契约（REQ-010/026 / WI-014 / TEST-QT-SC-002 的框架无关半）。

WI-014 DoD：筛选控制器要呈现 partial/failed 市场完整度状态、驱动深度分析跟进，且单只失败不终止
批量。这里测编排层：ScreenReport 携带市场完整度（分页不完整默认不当全市场结果，DATA_QUALITY 的
partial_market），单只深度分析失败被隔离进该只的 error、不影响其余（REQ-010）。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_screener import snap

from stock_advisor.ports import Completeness
from stock_advisor.services.screener_run import run_screen


def _market(n=40):
    return [
        snap(
            code=f"6000{i:02d}",
            price=10.0 + i,
            change_pct=5.0 + i * 0.1,
            volume_ratio=2.0,
            amount=5e8,
        )
        for i in range(n)
    ]


class _CompleteProvider:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    def fetch_market_snapshot(self, page_size=1000, max_pages=12):
        return list(self._snapshots)

    def fetch_quote(self, symbol):
        raise AssertionError("deep=False 不应触发个股行情")

    def fetch_history(self, symbol):
        return []


class _PartialProvider(_CompleteProvider):
    """分页不完整：只拿到 expected 的一部分。"""

    def market_completeness(self) -> Completeness:
        return Completeness(expected=100, received=len(self._snapshots))


class _LegacyProvider(_CompleteProvider):
    """不实现 market_completeness 的旧 provider——编排应默认视为完整（向后兼容）。"""


class MarketCompletenessTests(unittest.TestCase):
    def test_report_defaults_to_complete_for_legacy_provider(self):
        report = run_screen(_LegacyProvider(_market()), "momentum_strong", {}, deep=False)
        self.assertTrue(report.completeness.is_complete)

    def test_partial_paging_is_surfaced_as_incomplete(self):
        report = run_screen(_PartialProvider(_market(40)), "momentum_strong", {}, deep=False)
        self.assertFalse(report.completeness.is_complete)
        self.assertEqual(report.completeness.expected, 100)
        self.assertEqual(report.completeness.received, 40)

    def test_complete_provider_reports_complete(self):
        report = run_screen(_CompleteProvider(_market(40)), "momentum_strong", {}, deep=False)
        self.assertTrue(report.completeness.is_complete)


class DeepAnalysisFailureIsolationTests(unittest.TestCase):
    def test_single_deep_failure_does_not_abort_the_screen(self):
        # deep=True：让个别只的深度分析失败，其余仍需产出（REQ-010）。
        market = _market(6)

        class _FlakyProvider(_CompleteProvider):
            def fetch_quote(self, symbol):
                if symbol.code.endswith("00"):  # 让 600000 深度分析失败
                    raise ValueError("行情不可用")
                from test_engine import fake_quote

                return fake_quote(symbol)

            def fetch_history(self, symbol):
                return []

        report = run_screen(_FlakyProvider(market), "momentum_strong", {"top_n": 6}, deep=True)
        self.assertTrue(report.ok)  # 整轮不因个别失败而失败
        # 每个 TopN 都有 Recommendation；失败的那只带 error，其余带 result。
        self.assertGreater(len(report.recommendations), 0)
        failed = [r for r in report.recommendations if r.error]
        ok = [r for r in report.recommendations if r.result is not None]
        self.assertTrue(failed)  # 确有失败被隔离
        self.assertTrue(ok)  # 确有成功
        self.assertEqual(len(failed) + len(ok), len(report.recommendations))


if __name__ == "__main__":
    unittest.main()
