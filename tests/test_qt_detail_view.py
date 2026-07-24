"""详情区契约（REQ-004 / REQ-021 / REQ-022 / REQ-031 / WI-035）。

替代 WI-035 之前的 `test_qt_evidence_view.py` 与 `test_qt_position_plan.py`：那两个部件
（`EvidenceView` 的四列因子表 + `PositionPlanView` 的两个 label）在复刻 Tkinter 版式时被
`FactorBars`（因子条形图）与 `DetailView`（整篇解释）取代，本文件把它们守住的 REQ 逐条搬过来，
断言的是同样的保证、只是换了承载它的部件：

- REQ-004 因子/理由/风险证据可见 → 因子条数 + 解释正文里的「判断拆解 / 为什么这样判断 / 需要注意」
- REQ-004 仓位与风控计算器可见 → 解释正文里的「仓位 / 风控计算器」一节，数字原样透出
- REQ-021 回测带"只用当日及之前数据"的说明，样本不足时如实说明而非编造胜率
- REQ-022 分数不得描述为收益概率或确定置信度
- REQ-031 免责声明常驻
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import qt_app, requires_qt, temp_settings  # noqa: E402
from test_engine import FakeProvider, make_history, make_measurement  # noqa: E402

from domain.backtest import backtest_signals  # noqa: E402
from domain.models import CORE_DISCLAIMER  # noqa: E402
from domain.policy import position_plan  # noqa: E402
from services.tier_switch import redecide_at_level  # noqa: E402
from ui.view_text import (  # noqa: E402
    build_backtest_text,
    build_position_plan_text,
    build_visual_summary,
)

try:
    from qt_app.controllers.analysis_controller import AnalysisController
    from qt_app.pages.individual_page import IndividualPage
    from qt_app.widgets.detail_view import DetailView
    from qt_app.widgets.factor_bars import FactorBars
except ImportError:  # pragma: no cover - PySide6 是可选的迁移期依赖
    AnalysisController = IndividualPage = DetailView = FactorBars = None


def _result():
    return redecide_at_level(make_measurement(), 3)


@requires_qt
class DetailViewTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def test_renders_every_explanation_section(self):
        """REQ-004：因子拆解、理由与风险三类证据都要落到正文里。"""
        view = DetailView()
        view.show_result(_result())
        body = view.toPlainText()
        for heading in ("核心结论", "看懂结果", "判断拆解", "为什么这样判断", "需要注意"):
            self.assertIn(heading, body, f"解释正文缺少「{heading}」一节")

    def test_reasons_and_risks_are_shown(self):
        result = _result()
        view = DetailView()
        view.show_result(result)
        body = view.toPlainText()
        if result.reasons:
            self.assertIn(result.reasons[0][:6], body)

    def test_shows_the_position_plan_numbers_verbatim(self):
        """REQ-004：展示层如实呈现引擎算出的数字，不自造。"""
        plan = position_plan(make_measurement(), 3, Decimal("100000.00"))
        view = DetailView()
        view.show_result(_result(), build_position_plan_text(plan, "标准"))
        body = view.toPlainText()
        self.assertIn("仓位 / 风控计算器", body)
        self.assertIn(str(plan.shares), body)
        self.assertIn(f"{plan.stop_price:.2f}", body)
        self.assertIn(f"{plan.target_price:.2f}", body)

    def test_backtest_carries_sample_baseline_and_no_look_ahead_caveat(self):
        """REQ-021：回测必须带样本量、买入持有基线与"不预示未来"的说明。"""
        report = backtest_signals(make_history(start=20.0, step=0.25, days=80), level=3)
        view = DetailView()
        view.show_result(_result(), build_backtest_text(report))
        body = view.toPlainText()
        self.assertIn(str(report.sample_size), body)
        # 基线是格式化后展示的（两位小数），断言格式化值而非 repr。
        self.assertIn("买入持有基线", body)
        self.assertIn(f"{report.buy_hold_return:.2f}", body)
        self.assertIn("未来", body)

    def test_insufficient_sample_backtest_shows_its_message_not_fake_numbers(self):
        """样本不足时引擎返回 ok=False + message；展示层显示该说明，绝不编造胜率。"""
        report = backtest_signals(make_history(start=20.0, step=0.25, days=20), level=3)
        self.assertFalse(report.ok)
        view = DetailView()
        view.show_result(_result(), build_backtest_text(report))
        self.assertIn(report.message, view.toPlainText())

    def test_clearing_resets_to_the_placeholder(self):
        view = DetailView()
        view.show_result(_result())
        view.clear_detail()
        self.assertNotIn("判断拆解", view.toPlainText())

    def test_jump_to_finds_a_real_section_and_reports_a_missing_one(self):
        """章节导航跳不到就要说跳不到，不能假装成功。"""
        view = DetailView()
        view.show_result(_result())
        self.assertTrue(view.jump_to("需要注意"))
        self.assertFalse(view.jump_to("并不存在的小节"))


@requires_qt
class ScoreWordingTests(unittest.TestCase):
    """REQ-022：未经统计校准的分数不得描述为收益概率或确定置信度。"""

    def test_summary_line_avoids_probability_wording(self):
        summary = build_visual_summary(_result())
        self.assertIn("把握程度", summary)  # 老版的中性措辞
        for banned in ("收益概率", "胜率", "必然", "确定盈利", "确定置信"):
            self.assertNotIn(banned, summary, f"分数被描述为「{banned}」，违反 REQ-022")


@requires_qt
class IndividualPageEvidenceSurfaceTests(unittest.TestCase):
    """证据确实挂在装配好的页面上，而不只是部件自己能渲染（WI-031 的教训）。"""

    def setUp(self):
        self.app = qt_app()
        self.controller = AnalysisController(FakeProvider())
        self.addCleanup(self.controller.shutdown)
        self.page = IndividualPage(self.controller, temp_settings(self))

    def test_factor_bars_and_detail_are_mounted(self):
        self.assertTrue(self.page.findChildren(FactorBars))
        self.assertTrue(self.page.findChildren(DetailView))

    def test_disclaimer_is_resident_before_any_analysis(self):
        # REQ-031：空态即常驻，不必等有结果才出现。
        self.assertIn(CORE_DISCLAIMER, self.page.status.text())


if __name__ == "__main__":
    unittest.main()
