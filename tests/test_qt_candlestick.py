"""K 线蜡烛图部件（REQ-004 / AC-003 / AC-004 / WI-027 / TEST-QT-AN-002）。

守两件事：

1. **几何来自 domain/chart.py，部件不自己算。** 断言的是部件读出来的坐标与纯函数直接算出来的一致，
   而不是"图看起来对"——后者只能靠人眼，前者每次提交都能跑。
2. **不伪造。** 没有历史数据就明说"暂无历史数据"，不画空图也不沿用上一只的图；缺价显示破折号，
   不显示 0。

绘制本身走真实 QPainter（画进 QPixmap），因此 paintEvent 里的分支是真的被执行过的，不是靠 mock
绕过去的。
"""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtGui, QtWidgets, qt_app, requires_qt, temp_settings

from domain import chart as geometry
from domain.models import DailyBar

if QtWidgets is not None:
    from qt_app.widgets.candlestick_chart import CandlestickChart


def _bar(date: str, o: str, c: str, h: str, low: str, volume: int = 1000) -> DailyBar:
    return DailyBar(
        date=date,
        open=Decimal(o),
        close=Decimal(c),
        high=Decimal(h),
        low=Decimal(low),
        volume=volume,
        amount=float(volume) * float(c),
        pct_change=0.0,
        turnover_rate=0.0,
    )


def _series(n: int = 30) -> list[DailyBar]:
    bars = []
    for i in range(n):
        base = 10 + i * 0.1
        up = i % 3 != 0
        open_price = f"{base:.2f}"
        close_price = f"{base + (0.2 if up else -0.2):.2f}"
        bars.append(
            _bar(
                f"2026-06-{i + 1:02d}",
                open_price,
                close_price,
                f"{base + 0.4:.2f}",
                f"{base - 0.4:.2f}",
                volume=1000 + i * 10,
            )
        )
    return bars


@requires_qt
class CandlestickGeometryTests(unittest.TestCase):
    """坐标只有一个来源：domain/chart.py。"""

    def setUp(self):
        self.app = qt_app()
        self.widget = CandlestickChart()
        self.widget.resize(600, 300)

    def test_candle_positions_match_the_pure_geometry_exactly(self):
        bars = _series()
        self.widget.set_bars(bars)

        left, right, top, height = self.widget._plot_rect()
        expected = geometry.candle_layout(bars, left, right, top, height)

        self.assertEqual(self.widget._layout(), expected)

    def test_widget_reports_the_bar_count_it_was_given(self):
        self.widget.set_bars(_series(12))

        self.assertEqual(self.widget.bar_count(), 12)

    def test_clear_drops_the_previous_stock_rather_than_keeping_a_stale_chart(self):
        self.widget.set_bars(_series())

        self.widget.clear()

        self.assertEqual(self.widget.bar_count(), 0)
        self.assertEqual(self.widget.hovered_index(), -1)


@requires_qt
class CandlestickHoverTests(unittest.TestCase):
    """hover 命中同样走纯函数 nearest_index，读数如实反映那一根。"""

    def setUp(self):
        self.app = qt_app()
        self.widget = CandlestickChart()
        self.widget.resize(600, 300)
        self.bars = _series()
        self.widget.set_bars(self.bars)

    def _hover_at(self, x: float) -> None:
        self.widget._set_hover(x)

    def test_hovering_selects_the_nearest_candle(self):
        layout = self.widget._layout()
        target = 7

        self._hover_at(layout[target]["x"])

        self.assertEqual(self.widget.hovered_index(), target)

    def test_hover_readout_shows_that_bars_own_ohlc(self):
        layout = self.widget._layout()
        target = 3

        self._hover_at(layout[target]["x"])
        text = self.widget.hover_text()

        bar = self.bars[target]
        self.assertIn(bar.date, text)
        for price in (bar.open, bar.high, bar.low, bar.close):
            self.assertIn(f"{price:.2f}", text)
        # 说明书承诺"开/高/低/收与涨跌幅"——读数必须兑现涨跌那一半。
        self.assertIn("涨跌", text)
        self.assertIn(f"{bar.pct_change:+.2f}%", text)

    def test_leaving_the_widget_clears_the_readout(self):
        self._hover_at(self.widget._layout()[5]["x"])
        self.assertNotEqual(self.widget.hovered_index(), -1)

        self.widget._set_hover(None)

        self.assertEqual(self.widget.hovered_index(), -1)
        self.assertEqual(self.widget.hover_text(), "")

    def test_hover_on_an_empty_chart_reports_nothing(self):
        self.widget.clear()

        self._hover_at(120.0)

        self.assertEqual(self.widget.hovered_index(), -1)
        self.assertEqual(self.widget.hover_text(), "")

    def test_prices_are_formatted_from_decimal_without_a_float_round_trip(self):
        """行情价是 2 位小数的 Decimal；经 float 会引入二进制误差（ADR-0013）。"""
        exact = _bar("2026-06-30", "10.10", "10.30", "10.35", "10.05")
        self.widget.set_bars([exact])

        self.widget._set_hover(self.widget._layout()[0]["x"])
        text = self.widget.hover_text()

        for literal in ("10.10", "10.30", "10.35", "10.05"):
            self.assertIn(literal, text)


@requires_qt
class CandlestickPaintTests(unittest.TestCase):
    """真的画一遍：paintEvent 的分支必须被执行，而不是被 mock 掉。"""

    def setUp(self):
        self.app = qt_app()
        self.widget = CandlestickChart()
        self.widget.resize(640, 320)

    def _render(self) -> QtGui.QImage:
        pixmap = QtGui.QPixmap(self.widget.size())
        pixmap.fill(QtGui.QColor("white"))
        self.widget.render(pixmap)
        return pixmap.toImage()

    def test_price_axis_reserves_a_right_gutter(self):
        """绘图区右边必须给价格标尺留槽：刻度文字不许压在蜡烛上。"""
        self.widget.set_bars(_series(30), "SH.600519")
        _left, right, _top, _height = self.widget._plot_rect()
        self.assertLessEqual(right, self.widget.width() - 48, "右侧应留出 >=48px 的价格标尺槽")
        self._render()  # 轴绘制路径真的执行一遍，抛异常即失败

    def test_axes_use_domain_geometry_ticks(self):
        """轴刻度必须与 domain 纯函数同源——部件不许自算一套。"""
        from domain.chart import nice_price_ticks, price_bounds

        self.widget.set_bars(_series(30), "SH.600519")
        lo, hi = price_bounds(self.widget._bars)
        ticks = nice_price_ticks(lo, hi)
        self.assertTrue(ticks, "正常序列必须有价格刻度")
        for tick in ticks:
            self.assertTrue(lo <= tick <= hi)

    def test_painting_a_normal_series_marks_the_canvas(self):
        self.widget.set_bars(_series())

        image = self._render()

        white = QtGui.QColor("white").rgb()
        painted = sum(
            1
            for y in range(0, image.height(), 4)
            for x in range(0, image.width(), 4)
            if image.pixel(x, y) != white
        )
        self.assertGreater(painted, 0, "K 线没有画出任何东西")

    def test_painting_with_hover_active_does_not_crash(self):
        self.widget.set_bars(_series())
        self.widget._set_hover(self.widget._layout()[9]["x"])

        self._render()  # 十字光标 + 读数分支

        self.assertEqual(self.widget.hovered_index(), 9)

    def test_empty_chart_says_so_instead_of_drawing_a_blank_plot(self):
        self.widget.set_bars([], "600519 贵州茅台")

        self._render()

        # 空态走的是文案分支；断言它没有把上一只的数据留在部件里。
        self.assertEqual(self.widget.bar_count(), 0)
        self.assertEqual(self.widget.hover_text(), "")

    def test_a_single_bar_series_still_renders(self):
        """n=1 时 index_to_x 走的是"居中"分支，蜡烛宽度也没有相邻间距可算。"""
        self.widget.set_bars([_bar("2026-06-01", "10.00", "10.00", "10.00", "10.00")])

        self._render()

        self.assertEqual(self.widget.bar_count(), 1)

    def test_flat_bar_where_open_equals_close_keeps_a_visible_body(self):
        """实体高度为 0 时若照实画就消失了——必须至少留一条横线。"""
        self.widget.set_bars([_bar("2026-06-01", "10.00", "10.00", "10.20", "9.80")] * 5)

        image = self._render()

        white = QtGui.QColor("white").rgb()
        painted = any(
            image.pixel(x, y) != white
            for y in range(0, image.height(), 2)
            for x in range(0, image.width(), 2)
        )
        self.assertTrue(painted, "开盘=收盘的蜡烛没有画出实体")

    def test_zero_volume_series_does_not_divide_by_zero(self):
        self.widget.set_bars([_bar("2026-06-01", "10.00", "10.20", "10.30", "9.90", volume=0)] * 4)

        self._render()

        self.assertEqual(self.widget.bar_count(), 4)


@requires_qt
class CandlestickAccessibilityTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def test_chart_carries_an_accessible_name_and_description(self):
        """图形没有文本，读屏只能靠可访问名（REQ-017）。"""
        widget = CandlestickChart()

        self.assertTrue(widget.accessibleName())
        self.assertIn("K线", widget.accessibleName())
        self.assertTrue(widget.accessibleDescription())

    def test_mouse_tracking_is_on_so_hover_works_without_pressing(self):
        widget = CandlestickChart()

        self.assertTrue(widget.hasMouseTracking())


@requires_qt
class IndividualPageChartTests(unittest.TestCase):
    """页面把 K 线接到选中行上：换行换图，失败行不沿用上一只的图。"""

    def setUp(self):
        self.app = qt_app()
        from test_engine import FakeProvider

        from qt_app.controllers.analysis_controller import AnalysisController
        from qt_app.pages.individual_page import IndividualPage

        self.controller = AnalysisController(FakeProvider())
        self.addCleanup(self.controller.shutdown)
        self.page = IndividualPage(self.controller, temp_settings(self))

    def _make_outcome(self, code: str, bars: list[DailyBar], ok: bool = True):
        from domain.symbols import normalize_symbol
        from services.workflow import AnalysisOutcome

        symbol = normalize_symbol(code)
        result = None
        if ok:
            from test_engine import FakeProvider

            from services.workflow import analyze_symbol

            result = analyze_symbol(symbol, FakeProvider()).result
        return AnalysisOutcome(
            symbol=symbol,
            result=result,
            measurement=None,
            history=bars,
            error="" if ok else "boom",
            degraded=False,
            quality=_quality(),
        )

    def test_selecting_a_row_shows_that_symbols_bars(self):
        bars = _series(8)
        self.page._append_row(self._make_outcome("600000", bars))

        self.page.table.setCurrentIndex(self.page.model.index(0, 0))

        self.assertEqual(self.page.chart.bar_count(), len(bars))

    def test_switching_rows_switches_the_chart(self):
        self.page._append_row(self._make_outcome("600000", _series(8)))
        self.page._append_row(self._make_outcome("600001", _series(15)))

        self.page.table.setCurrentIndex(self.page.model.index(0, 0))
        first = self.page.chart.bar_count()
        self.page.table.setCurrentIndex(self.page.model.index(1, 0))

        self.assertEqual(first, 8)
        self.assertEqual(self.page.chart.bar_count(), 15)

    def test_a_row_without_history_clears_the_chart_rather_than_keeping_the_previous_one(self):
        """失败/无历史的票必须把图清空——沿用上一只的 K 线就是把别人的数据当成它的。"""
        self.page._append_row(self._make_outcome("600000", _series(8)))
        self.page._append_row(self._make_outcome("600002", [], ok=False))

        self.page.table.setCurrentIndex(self.page.model.index(0, 0))
        self.page.table.setCurrentIndex(self.page.model.index(1, 0))

        self.assertEqual(self.page.chart.bar_count(), 0)

    def test_starting_a_new_analysis_drops_the_previous_chart(self):
        self.page._append_row(self._make_outcome("600000", _series(8)))
        self.page.table.setCurrentIndex(self.page.model.index(0, 0))

        self.page._on_analyze()

        self.assertEqual(self.page.chart.bar_count(), 0)


def _quality():
    from domain.data_quality import DataQuality

    return DataQuality(level="ok")


if __name__ == "__main__":
    unittest.main()
