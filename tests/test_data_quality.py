"""数据质量信封契约（REQ-023 / REQ-026 / AC-006 / WI-007 / TEST-DATA-001）。

REQ-023：所有结果携带数据来源、获取时间、完整度、新鲜度和降级状态。
WI-007 DoD：结果对象以**向后兼容**的模型携带 provenance / fetched_at / completeness / staleness。

设计要点：质量元数据是一个独立的 `DataQuality` 值对象，字段全带默认值，可选附加到结果上——
不往 Quote/AnalysisResult 等现有 dataclass 塞必填字段，否则 449 个现存测试与整个 domain 层
的构造点会全数破裂。质量等级与 `loop/architecture/DATA_QUALITY.md` 的五级定义严格对齐。
"""

import sys
import unittest
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.domain.data_quality import (
    QUALITY_LEVELS,
    DataProvenance,
    DataQuality,
    is_actionable,
)


class QualityLevelTests(unittest.TestCase):
    def test_levels_match_the_data_quality_contract(self):
        # 与 DATA_QUALITY.md「质量等级」一节逐字对齐；顺序即从好到坏的严重度。
        self.assertEqual(
            QUALITY_LEVELS,
            ("complete", "degraded_history", "partial_market", "stale", "invalid"),
        )

    def test_invalid_is_the_only_non_actionable_besides_partial(self):
        # invalid 禁止分析；partial_market 默认不得当成全市场结果。其余可用于展示/判断。
        self.assertTrue(is_actionable("complete"))
        self.assertTrue(is_actionable("degraded_history"))
        self.assertTrue(is_actionable("stale"))  # 可看但须标注，属可用
        self.assertFalse(is_actionable("invalid"))
        self.assertFalse(is_actionable("partial_market"))


class DataQualityValueObjectTests(unittest.TestCase):
    def test_is_frozen(self):
        q = DataQuality()
        with self.assertRaises(FrozenInstanceError):
            q.level = "invalid"  # type: ignore[misc]

    def test_defaults_are_a_complete_no_metadata_envelope(self):
        # 默认必须是"什么都没说"的良性值，这样给现有结果附加它不改变既有语义。
        q = DataQuality()
        self.assertEqual(q.level, "complete")
        self.assertIsNone(q.fetched_at)
        self.assertEqual(q.provenance, ())
        self.assertEqual(q.degradations, ())
        self.assertTrue(q.is_actionable)

    def test_carries_provenance_fetched_at_and_degradations(self):
        ts = datetime(2026, 7, 17, 9, 30, tzinfo=UTC)
        q = DataQuality(
            level="degraded_history",
            fetched_at=ts,
            provenance=(DataProvenance(source="eastmoney", endpoint="clist", fallback_rank=0),),
            degradations=("history 不足 30 个交易日",),
        )
        self.assertEqual(q.fetched_at, ts)
        self.assertEqual(q.provenance[0].source, "eastmoney")
        self.assertEqual(q.degradations, ("history 不足 30 个交易日",))
        self.assertTrue(q.is_actionable)

    def test_invalid_level_is_not_actionable(self):
        self.assertFalse(DataQuality(level="invalid").is_actionable)

    def test_age_seconds_none_without_fetched_at(self):
        self.assertIsNone(DataQuality().age_seconds(now=datetime.now(UTC)))

    def test_age_seconds_computed_from_fetched_at(self):
        fetched = datetime(2026, 7, 17, 9, 0, 0, tzinfo=UTC)
        now = datetime(2026, 7, 17, 9, 0, 45, tzinfo=UTC)
        self.assertEqual(DataQuality(fetched_at=fetched).age_seconds(now=now), 45.0)

    def test_is_stale_against_ttl(self):
        fetched = datetime(2026, 7, 17, 9, 0, 0, tzinfo=UTC)
        now = datetime(2026, 7, 17, 9, 0, 45, tzinfo=UTC)
        q = DataQuality(fetched_at=fetched)
        self.assertTrue(q.is_stale(ttl_seconds=30, now=now))  # 45s > 30s(quote TTL)
        self.assertFalse(q.is_stale(ttl_seconds=60, now=now))  # 45s < 60s

    def test_is_stale_is_false_when_age_unknown(self):
        # 没有 fetched_at 时不能凭空判 stale（宁可不误报）。
        self.assertFalse(DataQuality().is_stale(ttl_seconds=30, now=datetime.now(UTC)))


class ProvenanceTests(unittest.TestCase):
    def test_provenance_is_frozen_and_records_the_fallback_chain(self):
        p = DataProvenance(source="sina", endpoint="hq", fallback_rank=1)
        self.assertEqual((p.source, p.endpoint, p.fallback_rank), ("sina", "hq", 1))
        with self.assertRaises(FrozenInstanceError):
            p.source = "x"  # type: ignore[misc]


class WorkflowIntegrationTests(unittest.TestCase):
    """WI-007 的真实兑现：编排结果携带质量信封，且既有 `degraded` bool 保持不变。"""

    def _provider(self, *, history_fails: bool):
        from datetime import date
        from decimal import Decimal

        from stock_advisor.data.data_provider import MarketDataError
        from stock_advisor.domain.models import DailyBar, Quote

        quote = Quote(
            symbol="SH.600519",
            name="贵州茅台",
            last=Decimal("1680.00"),
            open=Decimal("1670.00"),
            high=Decimal("1690.00"),
            low=Decimal("1660.00"),
            previous_close=Decimal("1675.00"),
            volume=1000,
            amount=1.0,
            turnover_rate=0.5,
            change_pct=0.3,
        )

        class _P:
            def fetch_quote(self, symbol):
                return quote

            def fetch_history(self, symbol):
                if history_fails:
                    raise MarketDataError("history down")
                return [
                    DailyBar(
                        date=date(2026, 7, d),
                        open=Decimal("1670.00"),
                        close=Decimal("1680.00"),
                        high=Decimal("1690.00"),
                        low=Decimal("1660.00"),
                        volume=1000,
                        amount=1.0,
                        pct_change=0.3,
                        turnover_rate=0.5,
                    )
                    for d in range(1, 16)
                ]

        return _P()

    def test_healthy_fetch_yields_complete_quality(self):
        from stock_advisor.services.workflow import analyze_symbol

        outcome = analyze_symbol("SH.600519", self._provider(history_fails=False))
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.quality.level, "complete")
        self.assertFalse(outcome.degraded)  # 既有 bool 语义不变
        self.assertTrue(outcome.quality.is_actionable)

    def test_history_failure_is_degraded_history_with_a_visible_reason(self):
        from stock_advisor.services.workflow import analyze_symbol

        outcome = analyze_symbol("SH.600519", self._provider(history_fails=True))
        self.assertTrue(outcome.ok)  # 降级仍出结果（保守判断）
        self.assertTrue(outcome.degraded)  # 既有 bool 仍为 True
        self.assertEqual(outcome.quality.level, "degraded_history")
        # REQ-023 的"降级状态"必须可见地记录，不只是一个 bool。
        self.assertTrue(outcome.quality.degradations)
        self.assertTrue(outcome.quality.is_actionable)  # degraded_history 仍可用


class BackwardCompatibilityTests(unittest.TestCase):
    def test_existing_result_dataclasses_are_unchanged(self):
        # WI-007 的硬约束：加质量模型不得改动现有结果对象的构造签名。
        # 用最少必填字段构造 Quote，证明它仍可在不知道 DataQuality 的情况下建立。
        from decimal import Decimal

        from stock_advisor.domain.models import Quote

        quote = Quote(
            symbol="SH.600519",
            name="贵州茅台",
            last=Decimal("1680.00"),
            open=Decimal("1670.00"),
            high=Decimal("1690.00"),
            low=Decimal("1660.00"),
            previous_close=Decimal("1675.00"),
            volume=1000,
            amount=1.0,
            turnover_rate=0.5,
            change_pct=0.3,
        )
        self.assertEqual(quote.symbol, "SH.600519")


if __name__ == "__main__":
    unittest.main()
