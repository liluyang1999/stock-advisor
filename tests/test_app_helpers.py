import sys
import unittest
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from data.sample_data import (
    make_sample_analysis,
    make_sample_history,
    make_sample_measurement,
    make_sample_recommendation,
)
from ui.theme import (
    ACTION_BUTTON_LABELS,
    APP_ICON_FILENAME,
    APP_TITLE,
    INFO_WINDOW_SIZE,
    MAIN_MIN_SIZE,
    WINDOW_MAX_SIZE,
    WINDOW_WORKAREA_MARGIN,
)
from ui.view_format import (
    build_snapshot_detail,
    build_snapshot_summary,
    format_comparison_row,
    format_recommendation_row,
    format_result_row,
    format_results_as_csv,
    format_results_for_clipboard,
    result_row_tags,
    snapshot_display,
    table_sort_key,
    watchlist_rows,
)
from ui.view_text import (
    build_backtest_text,
    build_detail_text,
    build_fund_flow_text,
    build_help_sections,
    build_manual_text,
    build_portfolio_overview,
    build_position_plan_text,
    build_recommendation_header,
    build_screener_overview,
    build_spectrum_text,
    build_strategy_explanation_text,
    build_visual_summary,
    level_summary,
    normalize_symbol_input_text,
    summarize_results,
)


class AppHelperTests(unittest.TestCase):
    def test_app_branding_uses_requested_name_and_theme_icon(self):
        self.assertEqual(APP_TITLE, "股市锦囊")
        self.assertEqual(APP_ICON_FILENAME, "a_stock_strategy.ico")
        self.assertTrue((PROJECT_ROOT / "assets" / APP_ICON_FILENAME).exists())

    def test_window_defaults_are_compact_and_centerable(self):
        # 主窗口按工作区自适应居中（四周均匀留白），不再用固定默认尺寸。
        self.assertEqual(INFO_WINDOW_SIZE, (880, 580))
        self.assertEqual(MAIN_MIN_SIZE, (1000, 680))
        self.assertGreater(WINDOW_WORKAREA_MARGIN, 0)
        self.assertGreaterEqual(WINDOW_MAX_SIZE[0], MAIN_MIN_SIZE[0])
        self.assertGreaterEqual(WINDOW_MAX_SIZE[1], MAIN_MIN_SIZE[1])

    # WI-023：原先三条断言 Tk StockAdvisorApp 私有方法存在的结构性用例随 Tk 生产层一并移除
    # （WI-002 归类为 qt_replaced —— 对应能力已由 test_qt_* 的行为测试覆盖，不再断言私有方法名）。

    def test_action_button_labels_remove_unneeded_paste_action(self):
        self.assertNotIn("粘贴代码", ACTION_BUTTON_LABELS)
        self.assertEqual(ACTION_BUTTON_LABELS, ("开始分析", "停止", "输入工具"))

    def test_normalize_symbol_input_text_cleans_duplicates_for_users(self):
        text = normalize_symbol_input_text("600519\nSH.600519, 000001  300750")

        self.assertEqual(text, "SH.600519, SZ.000001, SZ.300750")

    def test_format_result_row_contains_human_readable_fields(self):
        result = make_sample_analysis()

        row = format_result_row(result)

        self.assertEqual(row[0], result.symbol.display)
        self.assertIn(result.action_label, row)
        self.assertTrue(row[3].startswith(str(result.score)))
        self.assertTrue(row[4].endswith("%"))
        self.assertIn(row[7], {"低", "中", "高"})

    def test_user_visible_result_formatters_hide_non_finite_numbers(self):
        result = replace(
            make_sample_analysis(),
            score=float("nan"),
            confidence=float("inf"),
            last=float("inf"),
            change_pct=float("nan"),
            suggested_position=float("-inf"),
            expected_move_pct=float("inf"),
        )

        payload = "\n".join(
            [
                " ".join(format_result_row(result)),
                build_visual_summary(result),
                build_detail_text(result),
                format_results_for_clipboard([result]),
                format_results_as_csv([result]),
            ]
        ).lower()

        self.assertNotIn("nan", payload)
        self.assertNotIn("inf", payload)

    def test_detail_text_includes_reasons_and_risks(self):
        result = make_sample_analysis()

        text = build_detail_text(result)

        self.assertIn("为什么这样判断", text)
        self.assertIn("需要注意", text)
        self.assertIn(result.action_label, text)
        self.assertIn("建议投入比例", text)
        for technical_word in ("MACD", "ATR", "布林", "因子", "模型原理"):
            self.assertNotIn(technical_word, text)

    def test_visual_summary_is_short_and_actionable(self):
        result = make_sample_analysis()

        summary = build_visual_summary(result)

        self.assertIn("今日建议", summary)
        self.assertIn("投入比例", summary)
        self.assertIn("波动", summary)

    def test_portfolio_overview_highlights_counts_and_priority(self):
        buy = make_sample_analysis()
        sell = replace(buy, action="SELL", action_label="卖出/减仓", score=-35, confidence=72)

        overview = build_portfolio_overview([buy, sell], failures=1)

        self.assertIn("组合概览", overview)
        self.assertIn("买入 1", overview)
        self.assertIn("卖出 1", overview)
        self.assertIn("失败 1", overview)
        self.assertIn(buy.symbol.display, overview)

    def test_portfolio_overview_hides_non_finite_score_and_confidence(self):
        result = replace(make_sample_analysis(), score=float("nan"), confidence=float("inf"))

        overview = build_portfolio_overview([result], failures=0).lower()

        self.assertNotIn("nan", overview)
        self.assertNotIn("inf", overview)

    def test_table_sort_key_handles_numeric_columns_and_risk(self):
        row = format_result_row(make_sample_analysis())

        self.assertEqual(table_sort_key("score", row), 47.0)
        self.assertEqual(table_sort_key("confidence", row), 84.0)
        self.assertIsInstance(table_sort_key("change", row), float)
        self.assertEqual(table_sort_key("risk", (*row[:7], "高")), 2.0)

    def test_table_sort_key_treats_non_finite_cells_as_zero(self):
        row = ("", "", "", "nan", "inf%", "inf", "+nan%", "")

        self.assertEqual(table_sort_key("score", row), 0.0)
        self.assertEqual(table_sort_key("confidence", row), 0.0)
        self.assertEqual(table_sort_key("last", row), 0.0)
        self.assertEqual(table_sort_key("change", row), 0.0)

    def test_result_row_tags_mark_action_and_risk_for_table_color(self):
        result = make_sample_analysis()
        high_risk = replace(result, confidence=42, risks=[*result.risks, "额外风险", "继续注意"])

        tags = result_row_tags(high_risk)

        self.assertIn("action_buy", tags)
        self.assertIn("risk_high", tags)

    def test_summary_and_clipboard_text_are_useful_for_batches(self):
        result = make_sample_analysis()

        summary = summarize_results([result], failures=1)
        copied = format_results_for_clipboard([result])

        self.assertIn("完成 1", summary)
        self.assertIn("失败 1", summary)
        self.assertIn(result.symbol.display, copied)
        self.assertIn("风险等级", copied)

    def test_csv_export_uses_csv_quoting(self):
        result = make_sample_analysis()

        exported = format_results_as_csv([result])

        self.assertTrue(exported.startswith("\ufeff代码,名称,建议"))
        self.assertIn(result.symbol.display, exported)

    def test_manual_text_is_plain_language_for_non_technical_users(self):
        text = build_manual_text()

        self.assertIn("怎么使用", text)
        self.assertIn("怎么看结果", text)
        self.assertIn("数据从哪里来", text)
        self.assertIn("自动切换备用行情", text)
        self.assertIn("快捷操作", text)
        self.assertIn("Ctrl+Enter", text)
        self.assertIn("先看建议，再看理由，最后看风险", text)
        self.assertNotIn("粘贴代码", text)
        for technical_word in ("MACD", "ATR", "布林", "PyInstaller", "python -m", "模型原理"):
            self.assertNotIn(technical_word, text)

    def test_help_sections_are_structured_for_dialog_layout(self):
        sections = build_help_sections()
        titles = [title for title, _body in sections]

        self.assertIn("怎么使用", titles)
        self.assertIn("怎么看结果", titles)
        self.assertIn("数据与快捷操作", titles)
        self.assertGreaterEqual(len(sections), 4)
        self.assertTrue(all(title and body.strip() for title, body in sections))

    def test_strategy_explanation_is_plain_and_scientifically_honest(self):
        text = build_strategy_explanation_text()

        for keyword in ("多因子", "趋势", "成交", "波动", "风险", "不能保证"):
            self.assertIn(keyword, text)
        self.assertNotIn("绝对预测", text)

    def test_colors_use_a_share_native_red_up_green_down(self):
        from ui.view_format import _action_color, _score_color

        # 红=涨/买，绿=跌/卖：买入与正分同色，卖出与负分同色
        self.assertEqual(_action_color("BUY"), _score_color(10))
        self.assertEqual(_action_color("SELL"), _score_color(-10))
        self.assertNotEqual(_score_color(10), _score_color(-10))
        self.assertEqual(_score_color(10).lower(), "#b4232c")
        self.assertEqual(_score_color(-10).lower(), "#167044")

    def test_level_summary_reflects_strength(self):
        self.assertIn("标准", level_summary(3))
        self.assertIn("激进", level_summary(5))
        self.assertIn("稳健", level_summary(1))
        self.assertIn("仓位上限", level_summary(3))

    def test_level_summary_defaults_invalid_level_to_standard(self):
        self.assertIn("标准", level_summary(float("nan")))
        self.assertIn("标准", level_summary(float("inf")))
        self.assertIn("标准", level_summary("abc"))

    def test_position_plan_text_is_actionable(self):
        from domain.policy import position_plan

        m = make_sample_measurement()
        text = build_position_plan_text(position_plan(m, 3, 100000), "标准")
        self.assertIn("止损", text)
        self.assertIn("最大亏损", text)

    def test_position_plan_text_omits_zero_stop_for_invalid_plan(self):
        from domain.models import PositionPlan

        plan = PositionPlan(
            fraction=0.0,
            shares=0,
            lots=0,
            entry=0.0,
            stop_price=0.0,
            stop_pct=0.0,
            target_price=0.0,
            target_pct=0.0,
            reward_risk=2.0,
            cost=0.0,
            max_loss=0.0,
            max_loss_pct=0.0,
            note="价格无效，无法计算仓位。",
        )
        text = build_position_plan_text(plan, "标准")
        self.assertIn("价格无效", text)
        self.assertNotIn("参考止损价", text)

    def test_share_count_parser_rejects_fractional_input(self):
        from domain.input_validate import parse_optional_positive_int

        self.assertIsNone(parse_optional_positive_int("100.5"))
        self.assertEqual(parse_optional_positive_int("200.0"), 200)

    def test_positive_float_parser_rejects_non_finite_input(self):
        from domain.input_validate import parse_optional_positive

        self.assertIsNone(parse_optional_positive("NaN"))
        self.assertIsNone(parse_optional_positive("Infinity"))
        self.assertIsNone(parse_optional_positive("-Infinity"))

    def test_alert_threshold_parser_rejects_non_finite_input(self):
        from domain.input_validate import parse_alert_threshold

        self.assertEqual(parse_alert_threshold("12.5"), 12.5)
        self.assertIsNone(parse_alert_threshold("NaN"))
        self.assertIsNone(parse_alert_threshold("Infinity"))
        self.assertIsNone(parse_alert_threshold("-Infinity"))

    def test_backtest_text_has_winrate_and_honest_caveat(self):
        from domain.backtest import backtest_signals

        report = backtest_signals(make_sample_history(), level=3)
        text = build_backtest_text(report)
        self.assertIn("胜率", text)
        self.assertIn("不预示未来", text)

    def test_backtest_text_hides_non_finite_numbers(self):
        from domain.models import BacktestReport, BacktestStat

        report = BacktestReport(
            level=3,
            horizon=5,
            sample_size=20,
            buy_hold_return=float("inf"),
            note="异常样本",
            stats={
                "BUY": BacktestStat("BUY", 2, float("nan"), float("inf")),
                "SELL": BacktestStat("SELL", 1, float("-inf"), float("nan")),
            },
        )

        text = build_backtest_text(report).lower()

        self.assertIn("样本不足", text)
        self.assertNotIn("nan", text)
        self.assertNotIn("inf", text)

    def test_spectrum_text_lists_levels_and_hint(self):
        from domain.policy import spectrum

        text = build_spectrum_text(spectrum(make_sample_measurement(), 3))
        self.assertIn("决策强度光谱", text)
        self.assertIn("标准", text)

    def test_watchlist_rows_show_pl_when_held_and_analyzed(self):
        from domain.models import WatchItem

        result = make_sample_analysis()  # last≈26.6
        rows = watchlist_rows(
            [WatchItem(result.symbol.normalized, cost=20.0, shares=100)],
            {result.symbol.normalized: result},
        )
        self.assertEqual(rows[0][2], "20.00")  # 成本
        self.assertIn("%", rows[0][4])  # 浮动盈亏含百分比
        self.assertIn("元", rows[0][4])  # 含金额

    def test_watchlist_rows_hide_non_finite_cost_and_cached_price(self):
        from domain.models import WatchItem

        result = replace(make_sample_analysis(), last=float("inf"))

        rows = watchlist_rows(
            [
                WatchItem(result.symbol.normalized, cost=float("nan"), shares=100),
                WatchItem(result.symbol.normalized, cost=20.0, shares=100),
            ],
            {result.symbol.normalized: result},
        )

        payload = "\n".join(" ".join(row) for row in rows).lower()
        self.assertNotIn("nan", payload)
        self.assertNotIn("inf", payload)

    def test_watchlist_rows_dash_when_no_cost(self):
        from domain.models import WatchItem

        rows = watchlist_rows([WatchItem("sh600519")], {})
        self.assertEqual(rows[0][2], "—")
        self.assertEqual(rows[0][4], "—")

    def test_comparison_row_formatter_hides_non_finite_numbers(self):
        from domain.models import ComparisonRow

        row = ComparisonRow(
            code="SH.600519",
            name="bad-cache",
            last=float("inf"),
            change_pct=float("nan"),
            score=float("nan"),
            confidence=float("inf"),
            risk="high",
            position=float("-inf"),
            level_hint="",
            cost=float("inf"),
            pl_pct=float("nan"),
            pl_amount=float("inf"),
        )

        payload = " ".join(format_comparison_row(row)).lower()
        self.assertNotIn("nan", payload)
        self.assertNotIn("inf", payload)

    def test_fund_flow_text_formats_inflow_and_outflow(self):
        from domain.models import FundFlow

        text = build_fund_flow_text(
            FundFlow(today_main=3.0e8, main_5d=-1.0e8, recent=[("2026-06-24", 3.0e8)]), "测试"
        )
        self.assertIn("亿", text)
        self.assertIn("净流入", text)  # 今日 +3亿
        self.assertIn("净流出", text)  # 近5日 -1亿
        self.assertIn("测试", text)

    def test_fund_flow_text_hides_non_finite_numbers(self):
        from domain.models import FundFlow

        text = build_fund_flow_text(
            FundFlow(
                today_main=float("nan"),
                main_5d=float("inf"),
                recent=[("2026-06-24", float("-inf"))],
            ),
            "异常样本",
        ).lower()

        self.assertIn("样本不足", text)
        self.assertIn("方向不明", text)
        self.assertNotIn("nan", text)
        self.assertNotIn("inf", text)


class RecommendationRowTests(unittest.TestCase):
    def test_deep_recommendation_row_matches_analysis_row(self):
        rec = make_sample_recommendation(deep=True)
        self.assertEqual(format_recommendation_row(rec), format_result_row(rec.result))

    def test_snapshot_only_recommendation_row_shows_price_and_marker(self):
        rec = make_sample_recommendation(deep=False)
        row = format_recommendation_row(rec)
        self.assertEqual(row[0], snapshot_display(rec.snapshot))
        self.assertEqual(row[2], "快照")
        self.assertTrue(row[6].endswith("%"))

    def test_snapshot_recommendation_formatters_hide_non_finite_numbers(self):
        rec = make_sample_recommendation(deep=False)
        snapshot = replace(
            rec.snapshot,
            price=float("inf"),
            change_pct=float("nan"),
            turnover_rate=float("inf"),
            volume_ratio=float("nan"),
            amplitude=float("inf"),
            pe_ttm=float("nan"),
            pb=float("inf"),
            amount=float("inf"),
            total_cap=float("nan"),
            change_60d=float("inf"),
            change_ytd=float("nan"),
        )
        rec = replace(rec, snapshot=snapshot, screen_score=float("inf"))

        payload = "\n".join(
            [
                " ".join(format_recommendation_row(rec)),
                build_recommendation_header(rec),
                build_snapshot_summary(rec),
                build_snapshot_detail(rec),
            ]
        ).lower()

        self.assertNotIn("nan", payload)
        self.assertNotIn("inf", payload)

    def test_snapshot_display_prefixes_market_correctly(self):
        rec = make_sample_recommendation(deep=False)
        self.assertTrue(snapshot_display(rec.snapshot).startswith(("SH.", "SZ.", "BJ.")))

    def test_screener_overview_reports_scan_and_match_counts(self):
        overview = build_screener_overview(
            "强势动量", total=5865, matched=120, shown=20, failures=1
        )
        self.assertIn("强势动量", overview)
        self.assertIn("5865", overview)
        self.assertIn("120", overview)


if __name__ == "__main__":
    unittest.main()
