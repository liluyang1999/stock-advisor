"""筛选页视图契约（REQ-002/004/012/031 / WI-013 / TEST-QT-SC-001）。

薄壳：6 预设下拉、TopN 微调、结果表、状态行，全部连 ScreenerController 信号。参数解析/排序/
TopN 钳制已由 test_screener_run 覆盖；这里验证页面把信号落进 QTableView、按钮态随生命周期切换、
免责声明常驻。

另外守住这一页曾经缺掉的那条路径：**选中一行必须出详情**。老 Tk 版把选股结果并进个股分析的同一
棵结果树，选中即渲染完整解释；拆成独立 Qt 页时这条线没跟过来，结果表点了等于没点。零命中与失败
时的引导文案（放宽哪一类条件、失败在哪）同样是那次拆分丢掉的，一并在此回归。
"""

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import qt_app, requires_qt, temp_settings, wait_for
from test_screener import snap

from data.sample_data import make_sample_recommendation
from domain.models import CORE_DISCLAIMER
from domain.presets import PRESETS
from services.workflow import ScreenReport
from ui.view_text import build_recommendation_header

if True:  # 延迟 import 让 requires_qt 生效
    try:
        from qt_app.controllers.screener_controller import ScreenerController
        from qt_app.pages.screener_page import ScreenerPage
        from qt_app.widgets.detail_view import DetailView
    except ImportError:  # pragma: no cover
        ScreenerController = ScreenerPage = DetailView = None


class _FakeScreeningProvider:
    def fetch_market_snapshot(self, page_size=1000, max_pages=12):
        return [
            snap(
                code=f"6000{i:02d}",
                price=10.0 + i,
                change_pct=5.0 + i * 0.1,
                volume_ratio=2.0,
                amount=5e8,
            )
            for i in range(30)
        ]

    def fetch_quote(self, symbol):
        raise AssertionError("deep=False 不应触发个股行情")

    def fetch_history(self, symbol):
        return []


@requires_qt
class ScreenerPageTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _page(self):
        controller = ScreenerController(_FakeScreeningProvider())
        self.addCleanup(controller.shutdown)
        page = ScreenerPage(controller, temp_settings(self))
        self.addCleanup(page.deleteLater)
        return page, controller

    def test_offers_all_six_presets(self):
        page, _ = self._page()
        self.assertEqual(page.preset_combo.count(), len(PRESETS))

    def test_disclaimer_is_resident(self):
        page, _ = self._page()
        self.assertIn(CORE_DISCLAIMER, page.status.text())  # REQ-031

    def test_screen_fills_the_result_table(self):
        page, controller = self._page()
        page._on_screen()
        wait_for(controller.screen_finished)
        self.assertGreater(page.model.rowCount(), 0)  # 结果落进 QTableView

    def test_buttons_toggle_across_the_lifecycle(self):
        page, controller = self._page()
        self.assertTrue(page.screen_button.isEnabled())
        self.assertFalse(page.stop_button.isEnabled())
        page._on_screen()
        self.assertFalse(page.screen_button.isEnabled())
        self.assertTrue(page.stop_button.isEnabled())
        wait_for(controller.screen_finished)
        self.assertTrue(page.screen_button.isEnabled())
        self.assertFalse(page.stop_button.isEnabled())

    def test_finished_status_keeps_disclaimer(self):
        page, controller = self._page()
        page._on_screen()
        wait_for(controller.screen_finished)
        self.assertIn(CORE_DISCLAIMER, page.status.text())

    def test_partial_market_is_surfaced_in_status(self):
        # WI-014：分页不完整时页面必须明确提示"非全市场结果"，不静默伪装成全市场。
        from ports import Completeness

        class _PartialProvider(_FakeScreeningProvider):
            def market_completeness(self):
                return Completeness(expected=100, received=30)

        controller = ScreenerController(_PartialProvider())
        self.addCleanup(controller.shutdown)
        page = ScreenerPage(controller, temp_settings(self))
        self.addCleanup(page.deleteLater)
        page._on_screen()
        wait_for(controller.screen_finished)
        # 运行态在 run_status，常驻免责声明在 status——与个股页一致（老 Tk 版也是分开的两处）。
        self.assertIn("不完整", page.run_status.text())


@requires_qt
class ScreenerDetailTests(unittest.TestCase):
    """选中一行就要看到"它为什么入围、它本身怎么样"（REQ-004）。

    两条分支各自写一次详情，且都要覆盖掉上一次的内容——把上一只票的解释留在屏幕上，比什么都不
    显示更糟：那篇文字会被当成当前选中行的结论（REQ-022 的同一条底线）。
    """

    def setUp(self):
        self.app = qt_app()
        self.controller = ScreenerController(_FakeScreeningProvider())
        self.addCleanup(self.controller.shutdown)
        self.page = ScreenerPage(self.controller, temp_settings(self))
        self.addCleanup(self.page.deleteLater)

    def _select(self, row):
        """选中第 row 行，返回详情区当前的正文。"""
        self.page.table.setCurrentIndex(self.page.model.index(row, 0))
        return self.page.detail.toPlainText()

    def test_detail_view_is_mounted_on_the_page(self):
        # WI-031 的教训：部件自己能渲染不等于它挂在页面上。
        self.assertTrue(self.page.findChildren(DetailView))

    def test_selecting_a_deep_row_shows_its_explanation(self):
        rec = make_sample_recommendation(deep=True)
        self.page._append_row(rec)
        body = self._select(0)
        # 入围抬头在最前（第 N 名 · 板块 · 入选评分），后面才是整篇解释——老版就是这个顺序。
        self.assertTrue(body.startswith(build_recommendation_header(rec)), body[:80])
        for heading in ("核心结论", "判断拆解", "为什么这样判断", "需要注意"):
            self.assertIn(heading, body, f"深度解释缺少「{heading}」一节")

    def test_selecting_a_snapshot_row_replaces_the_previous_explanation(self):
        deep = make_sample_recommendation(deep=True)
        shallow = replace(make_sample_recommendation(deep=False), rank=2, board="创业板")
        self.page._append_row(deep)
        self.page._append_row(shallow)
        self.assertIn("判断拆解", self._select(0))

        body = self._select(1)
        self.assertIn("快照特征", body)  # 快照口径的详情
        self.assertIn("第 2 名", body)  # 而且是这一行的排名
        self.assertNotIn("判断拆解", body)  # 上一行的深度解释必须已经被换掉
        self.assertIn("勾选“深度分析”", body)  # 并说清为什么没有买/持/卖

    def test_snapshot_row_surfaces_the_deep_failure_reason(self):
        rec = replace(make_sample_recommendation(deep=False), error="实时行情获取失败")
        self.page._append_row(rec)
        body = self._select(0)
        self.assertIn("实时行情获取失败", body)  # 失败原因如实给出，不是含糊的"暂无数据"
        self.assertIn("仅展示快照信息", body)

    def test_a_new_run_drops_the_previous_selection_detail(self):
        self.page._append_row(make_sample_recommendation(deep=True))
        self.assertIn("判断拆解", self._select(0))
        self.page._on_screen()
        self.assertNotIn("判断拆解", self.page.detail.toPlainText())

    def test_finished_run_selects_the_first_row_so_the_detail_is_not_hidden(self):
        # 跑完自动选中首行：详情随即出现，不必让用户先猜这张表能点。
        self.page._on_screen()
        wait_for(self.controller.screen_finished)
        self.assertEqual(self.page.table.currentIndex().row(), 0)
        self.assertIn("核心结论", self.page.detail.toPlainText())


@requires_qt
class ScreenerGuidanceTests(unittest.TestCase):
    """零命中与失败都要给出下一步——两者都不是"什么都没发生"。"""

    def setUp(self):
        self.app = qt_app()
        self.controller = ScreenerController(_FakeScreeningProvider())
        self.addCleanup(self.controller.shutdown)
        self.page = ScreenerPage(self.controller, temp_settings(self))
        self.addCleanup(self.page.deleteLater)

    def test_zero_match_advises_widening_the_filter(self):
        self.page._on_finished(ScreenReport(total=5000, matched=0, recommendations=[]))
        self.assertIn("没有符合条件的股票", self.page.run_status.text())
        self.assertIn("请放宽筛选范围", self.page.overview.text())
        # 详情要说清放宽哪一类条件；只说"没有结果"等于把用户留在原地（老版的原话）。
        body = self.page.detail.toPlainText()
        self.assertIn("降低成交额下限", body)
        self.assertIn("放宽涨跌幅区间", body)

    def test_failed_run_shows_the_reason_in_every_surface(self):
        self.page._on_screen()  # 先进入"筛选中…"，验证失败会把三处都改写掉
        self.page._on_finished(
            ScreenReport(total=0, matched=0, recommendations=[], error="行情源无响应")
        )
        for surface, text in (
            ("状态行", self.page.run_status.text()),
            ("概览", self.page.overview.text()),
            ("详情", self.page.detail.toPlainText()),
        ):
            self.assertIn("行情源无响应", text, f"{surface}没有说明失败原因")
        self.assertNotIn("筛选中", self.page.run_status.text())


class DisclaimerStaticDetectionTests(unittest.TestCase):
    def test_module_references_the_core_disclaimer(self):
        src = (Path(__file__).resolve().parents[1] / "src/qt_app/pages/screener_page.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("CORE_DISCLAIMER", src)


if __name__ == "__main__":
    unittest.main()
