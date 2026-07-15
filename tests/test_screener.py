import math
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from stock_advisor.domain.models import FilterCriteria, MarketSnapshot
from stock_advisor.domain.screener import (
    ALL_BOARDS,
    BOARD_BJ,
    BOARD_CHINEXT,
    BOARD_SH_MAIN,
    BOARD_STAR,
    BOARD_SZ_MAIN,
    _finite_optional,
    _liquidity_bonus,
    _top_limit,
    apply_filters,
    board_of,
    rank,
    recommend,
    score_for,
)


def snap(
    code="600000",
    market_id="1",
    name="测试",
    price=10.0,
    change_pct=1.0,
    change=0.1,
    volume=100000,
    amount=1.0e8,
    amplitude=2.0,
    turnover_rate=2.0,
    pe_ttm=15.0,
    volume_ratio=1.2,
    total_cap=1.0e10,
    float_cap=8.0e9,
    speed=0.2,
    pb=2.0,
    change_60d=5.0,
    change_ytd=8.0,
):
    return MarketSnapshot(
        code=code,
        market_id=market_id,
        name=name,
        price=price,
        change_pct=change_pct,
        change=change,
        volume=volume,
        amount=amount,
        amplitude=amplitude,
        turnover_rate=turnover_rate,
        pe_ttm=pe_ttm,
        volume_ratio=volume_ratio,
        total_cap=total_cap,
        float_cap=float_cap,
        speed=speed,
        pb=pb,
        change_60d=change_60d,
        change_ytd=change_ytd,
    )


class BoardDerivationTests(unittest.TestCase):
    def test_board_of_covers_all_segments(self):
        self.assertEqual(board_of(snap(code="600000", market_id="1")), BOARD_SH_MAIN)
        self.assertEqual(board_of(snap(code="688981", market_id="1")), BOARD_STAR)
        self.assertEqual(board_of(snap(code="000001", market_id="0")), BOARD_SZ_MAIN)
        self.assertEqual(board_of(snap(code="300750", market_id="0")), BOARD_CHINEXT)
        self.assertEqual(board_of(snap(code="920083", market_id="0")), BOARD_BJ)
        self.assertEqual(board_of(snap(code="830799", market_id="0")), BOARD_BJ)
        self.assertEqual(len(ALL_BOARDS), 5)


class FilterTests(unittest.TestCase):
    def test_price_and_change_ranges_are_inclusive_bounds(self):
        rows = [
            snap(code="a", price=5.0, change_pct=1.0),
            snap(code="b", price=50.0, change_pct=9.0),
        ]
        criteria = FilterCriteria(price_min=4.0, price_max=10.0, change_pct_max=5.0)
        self.assertEqual([s.code for s in apply_filters(rows, criteria)], ["a"])

    def test_exclude_st_drops_risk_warning_names(self):
        rows = [
            snap(code="ok", name="平安银行"),
            snap(code="st", name="ST康美"),
            snap(code="del", name="退市某某"),
        ]
        kept = apply_filters(rows, FilterCriteria(exclude_st=True))
        self.assertEqual([s.code for s in kept], ["ok"])
        kept_all = apply_filters(rows, FilterCriteria(exclude_st=False))
        self.assertEqual(len(kept_all), 3)

    def test_exclude_loss_drops_negative_or_missing_pe(self):
        rows = [
            snap(code="profit", pe_ttm=20.0),
            snap(code="loss", pe_ttm=-30.0),
            snap(code="none", pe_ttm=None),
        ]
        kept = apply_filters(rows, FilterCriteria(exclude_loss=True))
        self.assertEqual([s.code for s in kept], ["profit"])

    def test_exclude_loss_drops_non_finite_pe(self):
        rows = [
            snap(code="profit", pe_ttm=20.0),
            snap(code="nan_pe", pe_ttm=float("nan")),
            snap(code="inf_pe", pe_ttm=float("inf")),
        ]

        kept = apply_filters(rows, FilterCriteria(exclude_loss=True))

        self.assertEqual([s.code for s in kept], ["profit"])

    def test_board_filter_restricts_to_selected_boards(self):
        rows = [
            snap(code="600000", market_id="1"),
            snap(code="300750", market_id="0"),
            snap(code="920083", market_id="0"),
        ]
        kept = apply_filters(rows, FilterCriteria(boards=frozenset({BOARD_CHINEXT})))
        self.assertEqual([s.code for s in kept], ["300750"])

    def test_amount_floor_enforces_liquidity(self):
        rows = [snap(code="big", amount=5.0e8), snap(code="small", amount=1.0e7)]
        kept = apply_filters(rows, FilterCriteria(amount_min=1.0e8))
        self.assertEqual([s.code for s in kept], ["big"])

    def test_missing_value_fails_only_when_a_bound_is_set(self):
        row = snap(code="x", pe_ttm=None)
        # no bound on PE -> kept
        self.assertEqual(len(apply_filters([row], FilterCriteria())), 1)
        # bound on PE -> missing value cannot satisfy it -> dropped
        self.assertEqual(len(apply_filters([row], FilterCriteria(pe_min=0.0, pe_max=20.0))), 0)

    def test_market_cap_bucket(self):
        rows = [snap(code="large", total_cap=3.0e11), snap(code="micro", total_cap=2.0e9)]
        kept = apply_filters(rows, FilterCriteria(total_cap_min=2.0e10))
        self.assertEqual([s.code for s in kept], ["large"])

    def test_non_finite_required_values_are_excluded_before_ranking(self):
        rows = [
            snap(code="good", price=10.0, change_pct=1.0, amount=1.0e8),
            snap(code="nan_price", price=float("nan")),
            snap(code="inf_change", change_pct=float("inf")),
            snap(code="inf_amount", amount=float("inf")),
        ]

        kept = apply_filters(rows, FilterCriteria())

        self.assertEqual([s.code for s in kept], ["good"])


class RankTests(unittest.TestCase):
    def test_momentum_ranks_stronger_movers_first(self):
        weak = snap(code="weak", change_pct=1.0, change_60d=2.0, volume_ratio=1.0)
        strong = snap(code="strong", change_pct=6.0, change_60d=30.0, volume_ratio=2.5)
        ranked = rank([weak, strong], "momentum")
        self.assertEqual([s.code for _score, s in ranked], ["strong", "weak"])

    def test_value_ranks_cheaper_valuation_first(self):
        cheap = snap(code="cheap", pe_ttm=8.0, pb=1.0)
        pricey = snap(code="pricey", pe_ttm=60.0, pb=8.0)
        ranked = rank([pricey, cheap], "value")
        self.assertEqual([s.code for _score, s in ranked], ["cheap", "pricey"])

    def test_rebound_ranks_most_oversold_first(self):
        mild = snap(code="mild", change_60d=-5.0, change_pct=0.5)
        deep = snap(code="deep", change_60d=-40.0, change_pct=0.5)
        ranked = rank([mild, deep], "rebound")
        self.assertEqual([s.code for _score, s in ranked], ["deep", "mild"])

    def test_tied_score_and_amount_use_code_ascending(self):
        late_code = snap(code="600002", amount=1.0e8, change_pct=1.0, change_60d=5.0)
        early_code = snap(code="600001", amount=1.0e8, change_pct=1.0, change_60d=5.0)
        ranked = rank([late_code, early_code], "momentum")
        self.assertEqual([s.code for _score, s in ranked], ["600001", "600002"])

    def test_non_finite_optional_inputs_do_not_create_non_finite_scores(self):
        row = snap(
            code="optional_bad",
            volume_ratio=float("inf"),
            change_60d=float("nan"),
            change_ytd=float("-inf"),
            speed=float("inf"),
            pe_ttm=float("nan"),
            pb=float("inf"),
        )

        for objective in ("momentum", "breakout", "activity", "value", "rebound", "balanced"):
            self.assertTrue(math.isfinite(score_for(row, objective)), objective)

    def test_rank_treats_non_finite_scores_and_amount_as_neutral(self):
        good = snap(code="600001", change_pct=1.0, amount=1.0e8)
        malformed = snap(code="600000", change_pct=float("nan"), amount=float("inf"))

        ranked = rank([malformed, good], "momentum")

        self.assertTrue(all(math.isfinite(score) for score, _snapshot in ranked))
        self.assertEqual(ranked[0][1].code, "600001")


class RecommendTests(unittest.TestCase):
    def test_recommend_filters_ranks_and_caps_top_n(self):
        rows = [snap(code=f"60000{i}", change_pct=float(i)) for i in range(1, 6)]
        recs = recommend(rows, FilterCriteria(), "momentum", top_n=3)
        self.assertEqual(len(recs), 3)
        self.assertEqual([r.rank for r in recs], [1, 2, 3])
        # highest change_pct first
        self.assertEqual(recs[0].snapshot.code, "600005")
        self.assertEqual(recs[0].board, BOARD_SH_MAIN)
        self.assertIsNone(recs[0].result)

    def test_recommend_returns_empty_when_nothing_passes(self):
        rows = [snap(price=100.0)]
        self.assertEqual(recommend(rows, FilterCriteria(price_max=5.0), "momentum"), [])

    def test_recommend_handles_non_finite_top_n_as_empty(self):
        rows = [snap(code="600001")]

        self.assertEqual(recommend(rows, FilterCriteria(), "momentum", top_n=float("nan")), [])
        self.assertEqual(recommend(rows, FilterCriteria(), "momentum", top_n=float("inf")), [])

    def test_recommend_excludes_non_finite_required_snapshots(self):
        rows = [
            snap(code="good", change_pct=1.0),
            snap(code="bad", change_pct=float("inf")),
        ]

        recs = recommend(rows, FilterCriteria(), "momentum", top_n=2)

        self.assertEqual([rec.snapshot.code for rec in recs], ["good"])


class ScreenerGuardTests(unittest.TestCase):
    def test_finite_optional_none_for_non_numeric(self):
        self.assertIsNone(_finite_optional("abc"))

    def test_liquidity_bonus_zero_for_non_positive_amount(self):
        self.assertEqual(_liquidity_bonus(0.0), 0.0)

    def test_score_for_unknown_objective_falls_back_to_change_pct(self):
        # 未知目标 → 直接返回当日涨跌幅（cp）作为分数。
        self.assertEqual(score_for(snap(change_pct=2.5), "unknown"), 2.5)

    def test_top_limit_zero_for_non_numeric(self):
        self.assertEqual(_top_limit("abc"), 0)


if __name__ == "__main__":
    unittest.main()
