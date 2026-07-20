"""已交付功能在页面里真的接通了（REQ-003/004/005 / WI-029 / TEST-QT-AN-002 / TEST-QT-PORT-001）。

背景：这四个部件本来都写好了、单测也齐全，却从没被挂进任何页面——需求与变更日志声称"五档决策强度""
证据""仓位计算器""横向对比"已交付，而用户在交付物里点不到。单测直接构造部件，永远发现不了这件事。

所以这套测试一律**从页面出发**驱动：往控制器灌结果、点选行、切档，然后断言用户看得见的东西变了。
"""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtWidgets, qt_app, requires_qt
from test_engine import FakeProvider

from stock_advisor.domain.symbols import normalize_symbol
from stock_advisor.services.workflow import analyze_symbol

if QtWidgets is not None:
    from stock_advisor.qt_app.controllers.analysis_controller import AnalysisController
    from stock_advisor.qt_app.pages.individual_page import IndividualPage
    from stock_advisor.qt_app.pages.portfolio_page import PortfolioPage
    from stock_advisor.qt_app.settings import Settings


def _outcome(code: str):
    return analyze_symbol(normalize_symbol(code), FakeProvider())


def _report(outcomes):
    from stock_advisor.services.batch import BatchReport

    # success_count / failure_count 是 BatchReport 的只读属性，由 outcomes 推导，不能传参。
    return BatchReport(total=len(outcomes), outcomes=list(outcomes))


@requires_qt
class IndividualPageWiringTests(unittest.TestCase):
    """个股页：切档、证据、仓位三件事必须随选中行与档位联动。"""

    def setUp(self):
        import tempfile

        self.app = qt_app()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Settings 的 path 是必填的，正是为了让"碰真实用户配置"不可能悄悄发生。
        self.settings = Settings(Path(self._tmp.name) / "config.json")
        self.controller = AnalysisController(FakeProvider())
        self.addCleanup(self.controller.shutdown)
        self.page = IndividualPage(self.controller, self.settings)
        self.outcomes = [_outcome("600000"), _outcome("600519")]
        for outcome in self.outcomes:
            self.page._append_row(outcome)
        self.page._on_finished(_report(self.outcomes))

    def test_tier_selector_is_present_and_defaults_to_standard(self):
        self.assertEqual(self.page.tier.current_level(), 3)

    def test_finishing_a_batch_selects_a_row_and_fills_the_detail_panes(self):
        """分析完就该看得到东西，而不是等用户自己先点一下才知道有详情。"""
        self.assertTrue(self.page.table.currentIndex().isValid())
        self.assertGreater(self.page.evidence.factor_model.rowCount(), 0)

    def test_switching_tier_redecides_without_touching_the_provider(self):
        """REQ-003：切档只对缓存的 Measurement 重判，绝不重新联网。"""

        class _ExplodingProvider:
            def fetch_quote(self, symbol):
                raise AssertionError("切档不得触发任何取数")

            def fetch_history(self, symbol):
                raise AssertionError("切档不得触发任何取数")

        self.page._controller._provider = _ExplodingProvider()
        before = [self.page.model.item(r, 2).text() for r in range(self.page.model.rowCount())]

        self.page.tier.set_level(5)  # 激进
        after = [self.page.model.item(r, 2).text() for r in range(self.page.model.rowCount())]

        self.assertEqual(len(before), len(after))
        self.assertEqual(self.page.tier.current_level(), 5)

    def test_switching_tier_keeps_the_selected_row(self):
        """切档不该把用户选中的那只票顶掉。"""
        self.page.table.setCurrentIndex(self.page.model.index(1, 0))
        selected = self.page._current_code()

        self.page.tier.set_level(1)

        self.assertEqual(self.page._current_code(), selected)

    def test_selecting_a_row_shows_that_symbols_evidence(self):
        self.page.table.setCurrentIndex(self.page.model.index(0, 0))
        first = self.page.evidence.factor_model.rowCount()

        self.page.table.setCurrentIndex(self.page.model.index(1, 0))

        self.assertGreater(first, 0)
        self.assertGreater(self.page.evidence.factor_model.rowCount(), 0)

    def test_selecting_a_row_runs_the_credibility_backtest(self):
        """REQ-021 的可信度回测：README 与变更日志都宣称它已交付，就必须真的算出来并显示。"""
        self.page.table.setCurrentIndex(self.page.model.index(0, 0))

        text = self.page.position.backtest_label.text()

        self.assertNotEqual(text, "—", "选中一行后回测区仍是空的——回测没有被调用")
        self.assertTrue(text.strip())

    def test_backtest_states_the_no_look_ahead_caveat(self):
        """回测结论必须带引擎给的"只用当日及之前数据"说明，不能只报一个漂亮数字。"""
        self.page.table.setCurrentIndex(self.page.model.index(0, 0))

        text = self.page.position.backtest_label.text()

        self.assertTrue(
            any(k in text for k in ("未来", "当日", "样本")),
            f"回测展示缺少无未来泄漏/样本说明：{text!r}",
        )

    def test_spectrum_shows_all_five_tiers_and_the_flip_point(self):
        """README 宣称的"决策强度光谱：同一只股票五档结论一眼对照"。"""
        self.page.table.setCurrentIndex(self.page.model.index(0, 0))

        text = self.page.spectrum_label.text()

        for name in ("稳健", "稳进", "标准", "积极", "激进"):
            self.assertIn(name, text, f"光谱缺少 {name} 档")
        self.assertIn("▸", text, "光谱没有标出当前档")

    def test_tier_choice_is_persisted_for_the_next_session(self):
        """REQ-009：档位跨会话保留。"""
        self.page.tier.set_level(4)

        from stock_advisor.services import store

        self.assertEqual(store.load_config(self.settings._path).level, 4)

    def test_capital_is_persisted_and_feeds_the_position_calculator(self):
        self.page.capital_input.setText("250000")
        self.page._on_capital_changed()

        from stock_advisor.services import store

        self.assertEqual(store.load_config(self.settings._path).capital, Decimal("250000.00"))
        self.assertEqual(self.page.capital_input.text(), "250000.00")  # 回填为规范形式

    def test_invalid_capital_is_rejected_without_destroying_the_current_value(self):
        """乱填不该把本金变成 0——那会让仓位计算器给出"可买 0 股"的假结论。"""
        self.page.capital_input.setText("abc")

        self.page._on_capital_changed()

        self.assertEqual(self.page._capital(), Decimal("100000.00"))
        self.assertEqual(self.page.capital_input.text(), "100000.00")

    def test_a_new_analysis_clears_the_detail_panes(self):
        """上一轮的证据/仓位不能留在新一轮的空表下面。"""
        self.page._on_analyze()

        self.assertEqual(self.page.chart.bar_count(), 0)
        self.assertEqual(self.page.evidence.factor_model.rowCount(), 0)


@requires_qt
class SettingsIsolationTests(unittest.TestCase):
    """页面拿不到"默认的真实用户配置"——这条曾经真的让测试写进了 %APPDATA%。"""

    def setUp(self):
        self.app = qt_app()

    def test_pages_refuse_to_be_built_without_explicit_settings(self):
        controller = AnalysisController(FakeProvider())
        self.addCleanup(controller.shutdown)

        for page_type in (IndividualPage, PortfolioPage):
            with self.subTest(page=page_type.__name__), self.assertRaises(TypeError):
                page_type(controller)  # type: ignore[call-arg]

    def test_settings_requires_an_explicit_path(self):
        """没有 Settings() 这种写法：缺省值就是"悄悄碰真实数据"的那条路径。"""
        with self.assertRaises(TypeError):
            Settings()  # type: ignore[call-arg]

    def test_only_the_assembly_reaches_the_real_user_config(self):
        """生产代码里 `Settings.for_user()` 只应出现在装配处一处。

        它是唯一通往用户真实 %APPDATA% 配置的入口。多一处调用就多一个绕开注入、直接读写用户数据的
        地方，也就多一条测试会污染真实配置的路——这正是本轮真实发生过的事。
        """
        qt_app_dir = Path(__file__).resolve().parents[1] / "src" / "stock_advisor" / "qt_app"
        callers = []
        for path in sorted(qt_app_dir.rglob("*.py")):
            if path.name == "settings.py":  # 定义处本身不算调用处
                continue
            if "for_user()" in path.read_text(encoding="utf-8"):
                callers.append(path.relative_to(qt_app_dir).as_posix())

        self.assertEqual(callers, ["app.py"], f"这些文件也在读真实用户配置：{callers}")


@requires_qt
class PortfolioPageWiringTests(unittest.TestCase):
    """自选页：增删即存盘，刷新后横向对比出行，没成本就没盈亏。"""

    def setUp(self):
        import os
        import tempfile

        self.app = qt_app()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # 严禁写真实 %APPDATA%：store 认这个环境变量（AGENTS.md 硬性约束）。
        self._config = Path(self._tmp.name) / "config.json"
        os.environ["STOCK_ADVISOR_CONFIG"] = str(self._config)
        self.addCleanup(lambda: os.environ.pop("STOCK_ADVISOR_CONFIG", None))

        self.settings = Settings(self._config)
        self.controller = AnalysisController(FakeProvider())
        self.addCleanup(self.controller.shutdown)
        self.page = PortfolioPage(self.controller, self.settings)

    def _add(self, code: str, cost: str = "", shares: str = "") -> None:
        self.page.code_input.setText(code)
        self.page.cost_input.setText(cost)
        self.page.shares_input.setText(shares)
        self.page.add_current_input()

    def test_adding_a_holding_persists_it(self):
        self._add("600000", "10.00", "100")

        self.assertTrue(self._config.is_file(), "自选改动没有落盘")
        from stock_advisor.services import store

        reloaded = store.load_config(self._config)
        # store 落盘时把代码规范化（600000 -> sh600000），表格与对比匹配都用这个形式。
        self.assertEqual([w.code for w in reloaded.watchlist], ["sh600000"])
        self.assertEqual(reloaded.watchlist[0].cost, Decimal("10.00"))
        self.assertEqual(reloaded.watchlist[0].shares, 100)

    def test_adding_the_same_code_updates_instead_of_duplicating(self):
        self._add("600000", "10.00", "100")
        self._add("600000", "12.00", "200")

        self.assertEqual(self.page.model.rowCount(), 1)
        self.assertEqual(self.page._config.watchlist[0].cost, Decimal("12.00"))

    def test_removing_the_selected_row_persists_the_removal(self):
        self._add("600000", "10.00", "100")
        self.page.table.setCurrentIndex(self.page.model.index(0, 0))

        self.page.remove_selected()

        self.assertEqual(self.page.model.rowCount(), 0)
        from stock_advisor.services import store

        self.assertFalse(store.load_config(self._config).watchlist)  # watchlist 是不可变元组

    def test_refreshing_fills_the_comparison_table(self):
        self._add("600000", "10.00", "100")
        outcomes = [_outcome("600000")]
        for outcome in outcomes:
            self.page._on_symbol(outcome)

        self.page._on_finished(_report(outcomes))

        self.assertGreater(self.page.comparison.model.rowCount(), 0)

    def test_a_holding_without_cost_shows_no_profit_rather_than_zero(self):
        """没填成本就没有盈亏——显示破折号，不是 0。把"没填"显示成"不赚不亏"是伪造。"""
        self._add("600000")
        outcomes = [_outcome("600000")]
        self.page._on_symbol(outcomes[0])

        self.page._on_finished(_report(outcomes))

        row = self.page.comparison.model.rowCount() - 1
        self.assertGreaterEqual(row, 0)
        self.assertEqual(self.page.comparison.model.item(row, 7).text(), "—")  # 浮动盈亏
        self.assertEqual(self.page.comparison.model.item(row, 8).text(), "—")  # 盈亏额

    def test_refreshing_an_empty_watchlist_says_so_instead_of_analysing_nothing(self):
        self.page.refresh()

        self.assertIn("自选为空", self.page.status.text())

    def test_watchlist_and_capital_edits_do_not_clobber_each_other(self):
        """两页共用一份 Settings 的理由：各存各的整份配置会互相覆盖，用户会静默丢数据。"""
        from stock_advisor.services import store

        self._add("600000", "10.00", "100")
        self.settings.update(capital=Decimal("777000.00"))  # 冒充个股页改本金
        self._add("600519", "20.00", "200")  # 自选页再次存盘

        reloaded = store.load_config(self._config)
        self.assertEqual(reloaded.capital, Decimal("777000.00"), "自选存盘把本金覆盖掉了")
        self.assertEqual(len(reloaded.watchlist), 2)

    def test_failed_symbols_are_excluded_and_reported(self):
        """取数失败的票不该以一行空数据混进对比表，但用户要知道少了几只。"""
        from stock_advisor.services.workflow import AnalysisOutcome

        self._add("600000")
        bad = AnalysisOutcome(symbol=normalize_symbol("600000"), error="boom")
        self.page._on_symbol(bad)

        self.page._on_finished(_report([bad]))

        self.assertEqual(self.page.comparison.model.rowCount(), 0)
        self.assertIn("未纳入", self.page.status.text())


if __name__ == "__main__":
    unittest.main()
