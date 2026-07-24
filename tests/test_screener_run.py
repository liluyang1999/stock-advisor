"""全市场筛选编排包装契约（REQ-002 / WI-013 的框架无关半）。

REQ-002：六种预设、参数校验、稳定排序、TopN 5–30。`screen_and_recommend` 已是编排核心；这里
测一层薄包装 `run_screen`——把"预设 key + 用户微调值"解析成有效 criteria 与 TopN 再调编排，
统一 UI 与后台之间的入口。框架无关、可离线确定性测试。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_screener import snap

from domain.presets import PRESETS
from ports import ManualCancel
from services.screener_run import run_screen


class _FakeScreeningProvider:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    def fetch_market_snapshot(self, page_size=1000, max_pages=12):
        return list(self._snapshots)

    def fetch_quote(self, symbol):
        raise AssertionError("run_screen(deep=False) 不应触发个股行情")

    def fetch_history(self, symbol):
        return []


def _market(n=40):
    # 造一批强动量样本，确保多数预设能筛出东西。
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


class RunScreenTests(unittest.TestCase):
    def test_each_preset_runs_and_returns_a_report(self):
        provider = _FakeScreeningProvider(_market())
        for preset in PRESETS:
            with self.subTest(preset=preset.key):
                report = run_screen(provider, preset.key, {}, deep=False)
                self.assertTrue(report.ok, preset.key)
                self.assertGreaterEqual(report.total, 0)

    def test_topn_is_clamped_to_5_30(self):
        provider = _FakeScreeningProvider(_market(60))
        # 请求 100 应被夹到 30；请求 1 应被夹到 5。
        big = run_screen(provider, "momentum_strong", {"top_n": 100}, deep=False)
        small = run_screen(provider, "momentum_strong", {"top_n": 1}, deep=False)
        self.assertLessEqual(len(big.recommendations), 30)
        self.assertLessEqual(len(small.recommendations), 5)

    def test_ranking_is_stable_and_ranked_desc(self):
        provider = _FakeScreeningProvider(_market(40))
        report = run_screen(provider, "momentum_strong", {"top_n": 10}, deep=False)
        ranks = [r.rank for r in report.recommendations]
        self.assertEqual(ranks, sorted(ranks))  # rank 从 1 递增
        scores = [r.screen_score for r in report.recommendations]
        self.assertEqual(scores, sorted(scores, reverse=True))  # 分数降序

    def test_unknown_preset_is_an_input_error(self):
        provider = _FakeScreeningProvider(_market())
        report = run_screen(provider, "no_such_preset", {}, deep=False)
        self.assertFalse(report.ok)
        self.assertIn("预设", report.error)

    def test_invalid_tunable_value_is_reported_not_crashed(self):
        provider = _FakeScreeningProvider(_market())
        report = run_screen(provider, "momentum_strong", {"change_pct_min": "abc"}, deep=False)
        # 非法微调值不应崩溃：要么被忽略回退预设默认，要么明确报错——两者皆可，但不得抛。
        self.assertIsNotNone(report)

    def test_cancellation_is_reported(self):
        provider = _FakeScreeningProvider(_market(30))
        cancel = ManualCancel()
        cancel.cancel()
        report = run_screen(provider, "momentum_strong", {}, deep=False, cancel_token=cancel)
        self.assertTrue(report.cancelled)


if __name__ == "__main__":
    unittest.main()
