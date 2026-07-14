from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Any

from ..domain.chart import (
    candle_layout,
    moving_average_series,
    nearest_index,
    price_bounds,
    price_to_y,
    volume_heights,
)
from ..domain.formatting import _safe_int
from ..domain.models import AnalysisResult, Measurement
from ..domain.policy import spectrum
from .layout import stacked_text_y
from .theme import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_SOFT,
    BORDER_SOFT,
    COMMAND_BG,
    CONTROL_BG,
    FLAT_COLOR,
    GRID_COLOR,
    HOLD_BG,
    INK,
    INK_SOFT,
    MUTED_INK,
    MUTED_LIGHT,
    NEG_BG,
    NEG_COLOR,
    POS_BG,
    POS_COLOR,
    UI_FONT,
)
from .view_format import _score_color
from .view_text import _friendly_factor_name


class ChartRenderMixin:
    """K线 / 因子光谱 / 可视化画布渲染 + 悬停提示——从 StockAdvisorApp 抽出的图表绘制关注点。"""

    def _on_kline_motion(self, event: tk.Event) -> None:
        state = getattr(self, "_kline_state", None)
        if not state or not state.get("layout"):
            return
        index = nearest_index(event.x, state["layout"])
        if index < 0:
            return
        canvas = self.kline_canvas
        canvas.delete("crosshair")
        cell = state["layout"][index]
        bar = state["bars"][index]
        top, ph, left = state["top"], state["ph"], state.get("left", 48)
        x = cell["x"]
        canvas.create_line(x, top, x, top + ph, fill=MUTED_LIGHT, dash=(2, 2), tags="crosshair")
        y = max(top, min(top + ph, event.y))
        canvas.create_line(
            left,
            y,
            max(canvas.winfo_width() - self._sc(12), left + self._sc(10)),
            y,
            fill=BORDER_SOFT,
            dash=(2, 2),
            tags="crosshair",
        )
        text = (
            f"{bar.date}  开{bar.open:.2f} 高{bar.high:.2f} 低{bar.low:.2f} "
            f"收{bar.close:.2f}  {bar.pct_change:+.2f}%"
        )
        # 底框尺寸按字体实测宽/行高绘制（而非固定 7.2*len(text)/20px），避免高 DPI 下文字溢出。
        tooltip_font = tkfont.Font(root=self.root, font=("Microsoft YaHei UI", 8))
        box_w = tooltip_font.measure(text) + self._sc(8)
        box_h = tooltip_font.metrics("linespace") + self._sc(6)
        box_x0, box_y0 = left + self._sc(4), top + self._sc(2)
        canvas.create_rectangle(
            box_x0,
            box_y0,
            box_x0 + box_w,
            box_y0 + box_h,
            fill=COMMAND_BG,
            outline="",
            tags="crosshair",
        )
        canvas.create_text(
            box_x0 + self._sc(6),
            box_y0 + box_h / 2,
            text=text,
            anchor=tk.W,
            fill="#ffffff",
            font=("Microsoft YaHei UI", 8),
            tags="crosshair",
        )

    def _on_kline_leave(self, _event: object = None) -> None:
        self.kline_canvas.delete("crosshair")

    def _safe_draw_spectrum(self, measurement: Measurement | None) -> None:
        try:
            self._draw_spectrum_strip(measurement)
        except Exception:  # noqa: BLE001 - 渲染异常不应中断选择
            self._draw_empty_spectrum_prompt("五档结论暂不可用")

    def _safe_draw_kline(self, history: list) -> None:
        try:
            self._draw_kline(history)
        except Exception:  # noqa: BLE001
            self._draw_empty_kline("K线图暂不可用")

    def _safe_draw_visual(self, result: AnalysisResult) -> None:
        try:
            self._draw_visual(result)
        except Exception:  # noqa: BLE001
            self._draw_empty_visual("图形面板暂不可用")

    @staticmethod
    def _canvas_extent(
        canvas: tk.Canvas, fallback_width: int, fallback_height: int
    ) -> tuple[int, int]:
        """返回画布当前真实尺寸；仅在尚未映射（1px）时使用控件请求尺寸兜底。

        绘图不得用大于真实可见宽度的设计稿回退值，否则最小窗口下图元会越过画布右缘。
        """
        width = int(canvas.winfo_width())
        height = int(canvas.winfo_height())
        if width <= 1:
            try:
                width = int(float(canvas.cget("width")))
            except TypeError, ValueError, tk.TclError:
                width = int(fallback_width)
        if height <= 1:
            try:
                height = int(float(canvas.cget("height")))
            except TypeError, ValueError, tk.TclError:
                height = int(fallback_height)
        return max(1, width), max(1, height)

    def _draw_empty_spectrum_prompt(self, text: str = "五档结论待显示") -> None:
        self.spectrum_canvas.delete("all")
        self.spectrum_canvas.create_text(
            14,
            24,
            anchor=tk.W,
            text=text,
            fill=MUTED_INK,
            font=(UI_FONT, 9),
        )

    def _draw_spectrum_strip(self, measurement: Measurement | None) -> None:
        canvas = self.spectrum_canvas
        canvas.delete("all")
        if measurement is None:
            self._draw_empty_spectrum_prompt()
            return
        width, _height = self._canvas_extent(canvas, self._sc(640), self._sc(50))
        level = self.level_var.get()
        cells = spectrum(measurement, level)
        labels = {"BUY": "买入", "SELL": "卖出", "HOLD": "观望"}
        colors = {
            "BUY": (POS_BG, POS_COLOR),
            "SELL": (NEG_BG, NEG_COLOR),
            "HOLD": (HOLD_BG, FLAT_COLOR),
        }
        n = len(cells)
        margin, gap = self._sc(8), self._sc(6)
        cell_w = (width - 2 * margin - gap * (n - 1)) / n

        name_font = (UI_FONT, 9, "bold")
        label_font = (UI_FONT, 9)
        # 两行文字纵向按字体实测行高堆叠（而非固定像素差 15），避免高 DPI 下放大字体重叠。
        line_height = tkfont.Font(root=self.root, font=name_font).metrics("linespace")
        row1_y, row2_y = stacked_text_y(self._sc(18), line_height, 2)
        box_top, box_bottom = self._sc(5), self._sc(42)
        # 兜底：超大字号/超高缩放下两行文字底边仍可能超出画布，撑高画布而非裁切文字。
        text_bottom = int(row2_y + line_height / 2)
        if text_bottom > int(canvas.cget("height")):
            canvas.configure(height=text_bottom + self._sc(4))
            box_bottom = max(box_bottom, text_bottom)

        for index, cell in enumerate(cells):
            x0 = margin + index * (cell_w + gap)
            x1 = x0 + cell_w
            bg, fg = colors.get(cell.action, (HOLD_BG, FLAT_COLOR))
            self._round_rect(
                canvas,
                x0,
                box_top,
                x1,
                box_bottom,
                self._sc(7),
                fill=bg,
                outline=ACCENT if cell.is_current else bg,
                width=2 if cell.is_current else 1,
            )
            mark = " ●" if cell.is_current else ""
            canvas.create_text(
                (x0 + x1) / 2, row1_y, text=cell.name + mark, fill=fg, font=name_font
            )
            canvas.create_text(
                (x0 + x1) / 2,
                row2_y,
                text=labels.get(cell.action, cell.action),
                fill=fg,
                font=label_font,
            )

    def _draw_kline(self, history: list) -> None:
        canvas = self.kline_canvas
        canvas.delete("all")
        width, height = self._canvas_extent(canvas, self._sc(620), self._sc(300))
        canvas.create_text(
            self._sc(12),
            self._sc(14),
            text="近期 K 线（红涨绿跌） · MA5/10/20",
            anchor=tk.W,
            fill=INK,
            font=(UI_FONT, 9, "bold"),
        )
        bars = list(history[-60:]) if history else []
        if len(bars) < 2:
            self._draw_empty_kline("K线样本不足")
            return
        left, right, top, ph = (
            self._sc(50),
            width - self._sc(16),
            self._sc(32),
            height - self._sc(104),
        )
        vol_top, vol_h = top + ph + self._sc(14), self._sc(42)
        lo, hi = price_bounds(bars)
        layout = candle_layout(bars, left, right, top, ph)
        closes = [bar.close for bar in bars]
        bw = max(float(self._sc(2)), (right - left) / len(bars) * 0.6)
        canvas.create_text(
            left - self._sc(5),
            top,
            text=f"{hi:.2f}",
            anchor=tk.E,
            fill=MUTED_INK,
            font=(UI_FONT, 8),
        )
        canvas.create_text(
            left - self._sc(5),
            top + ph,
            text=f"{lo:.2f}",
            anchor=tk.E,
            fill=MUTED_INK,
            font=(UI_FONT, 8),
        )
        for cell, _bar in zip(layout, bars, strict=False):
            color = POS_COLOR if cell["up"] else NEG_COLOR
            canvas.create_line(
                cell["x"], cell["wick_top"], cell["x"], cell["wick_bottom"], fill=color
            )
            body_bottom = max(cell["body_bottom"], cell["body_top"] + self._sc(1))
            canvas.create_rectangle(
                cell["x"] - bw / 2,
                cell["body_top"],
                cell["x"] + bw / 2,
                body_bottom,
                fill=color,
                outline=color,
            )
        for window, color in ((5, "#f59e0b"), (10, "#2563eb"), (20, "#7c3aed")):
            series = moving_average_series(closes, window)
            points: list[float] = []
            for index, value in enumerate(series):
                if value is not None:
                    points.extend([layout[index]["x"], price_to_y(value, lo, hi, top, ph)])
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=self._sc(1), smooth=True)
        volumes = volume_heights(bars, vol_h)
        for cell, _bar, vh in zip(layout, bars, volumes, strict=False):
            color = "#e7a3a3" if cell["up"] else "#a7d6bd"
            canvas.create_rectangle(
                cell["x"] - bw / 2,
                vol_top + vol_h - vh,
                cell["x"] + bw / 2,
                vol_top + vol_h,
                fill=color,
                outline=color,
            )
        # 存几何状态供 hover 十字光标映射
        self._kline_state = {"bars": bars, "layout": layout, "top": top, "ph": ph, "left": left}

    def _draw_empty_visual(self, message: str = "等待分析结果") -> None:
        # Task 3b 起，本面板只承担"判断拆解"——徽标/今日结论叙述/三项指标(综合判断·
        # 投入比例·把握程度)已分别在结果表(建议列)、结论卡(verdict card)和详情面板重复
        # 展示，这里不再重绘。message 形参保留（调用方仍传入语境化文案，见各调用点），
        # 但不再上屏——真正呈现给用户的错误/占位说明统一交给详情面板文本。
        self.visual.delete("all")
        width, height = self._canvas_extent(self.visual, self._sc(340), self._sc(300))
        left, top, right, bottom = (
            self._sc(20),
            self._sc(20),
            width - self._sc(20),
            height - self._sc(20),
        )

        # 因子占位条整体在面板可用高度内垂直居中，避免只贴顶留下一大片空白。
        bars_h = self._sc(120)
        bars_y = top + max(0.0, (bottom - top - self._sc(28) - bars_h) / 2) + self._sc(28)
        self.visual.create_text(
            left,
            bars_y - self._sc(9),
            text="判断拆解",
            anchor=tk.W,
            fill=INK,
            font=(UI_FONT, 10, "bold"),
            tags=("empty_visual_bars",),
        )
        bars_w = right - left
        row_h = bars_h / 4
        for index, ratio in enumerate((0.62, 0.45, 0.70, 0.36)):
            row_y = bars_y + index * row_h
            self._round_rect(
                self.visual,
                left,
                row_y + self._sc(4),
                left + bars_w,
                row_y + row_h - self._sc(4),
                self._sc(5),
                fill=CONTROL_BG,
                outline="",
                tags=("empty_visual_bars",),
            )
            self._round_rect(
                self.visual,
                left,
                row_y + self._sc(4),
                left + bars_w * ratio,
                row_y + row_h - self._sc(4),
                self._sc(5),
                fill=ACCENT_SOFT,
                outline="",
                tags=("empty_visual_bars",),
            )

    def _draw_empty_kline(self, message: str = "K线图待显示") -> None:
        canvas = self.kline_canvas
        canvas.delete("all")
        width, height = self._canvas_extent(canvas, self._sc(620), self._sc(300))
        canvas.create_text(
            self._sc(12),
            self._sc(14),
            text="近期 K 线（红涨绿跌） · MA5/10/20",
            anchor=tk.W,
            fill=INK,
            font=(UI_FONT, 9, "bold"),
            tags=("empty_kline_title",),
        )
        left, right, top, bottom = (
            self._sc(50),
            width - self._sc(16),
            self._sc(38),
            height - self._sc(82),
        )
        for index in range(5):
            y = top + (bottom - top) * index / 4
            canvas.create_line(left, y, right, y, fill=GRID_COLOR, tags=("empty_kline_grid",))
        for index in range(6):
            x = left + (right - left) * index / 5
            canvas.create_line(x, top, x, bottom, fill=BORDER_SOFT, tags=("empty_kline_grid",))

        shape = (0.46, 0.58, 0.38, 0.50, 0.31, 0.42, 0.28, 0.36, 0.24, 0.33, 0.29, 0.22)
        step = (right - left) / max(len(shape), 1)
        for index, ratio in enumerate(shape):
            x = left + step * (index + 0.5)
            body_h = self._sc(18 + (index % 3) * 4)
            y = top + (bottom - top) * ratio
            color = POS_COLOR if index % 3 != 1 else NEG_COLOR
            canvas.create_line(
                x,
                y - self._sc(14),
                x,
                y + body_h + self._sc(14),
                fill=color,
                tags=("empty_kline_candles",),
            )
            canvas.create_rectangle(
                x - self._sc(5),
                y,
                x + self._sc(5),
                y + body_h,
                fill=color,
                outline=color,
                tags=("empty_kline_candles",),
            )
        ma_points: list[float] = []
        for index, ratio in enumerate(
            (0.54, 0.48, 0.51, 0.40, 0.34, 0.37, 0.29, 0.31, 0.25, 0.28, 0.23, 0.20)
        ):
            ma_points.extend([left + step * (index + 0.5), top + (bottom - top) * ratio])
        canvas.create_line(
            *ma_points,
            fill=ACCENT_HOVER,
            width=self._sc(2),
            smooth=True,
            tags=("empty_kline_candles",),
        )

        vol_top, vol_h = bottom + self._sc(18), self._sc(30)
        for index, ratio in enumerate(
            (0.40, 0.52, 0.31, 0.62, 0.35, 0.48, 0.57, 0.34, 0.64, 0.38, 0.46, 0.55)
        ):
            x = left + step * (index + 0.5)
            vh = vol_h * ratio
            canvas.create_rectangle(
                x - self._sc(5),
                vol_top + vol_h - vh,
                x + self._sc(5),
                vol_top + vol_h,
                fill=ACCENT_SOFT,
                outline=ACCENT_SOFT,
                tags=("empty_kline_candles",),
            )
        canvas.create_text(
            left,
            height - self._sc(18),
            text=message,
            anchor=tk.W,
            fill=MUTED_INK,
            font=(UI_FONT, 9),
            tags=("empty_kline_text",),
        )
        self._kline_state = {"layout": []}

    def _draw_visual(self, result: AnalysisResult) -> None:
        # Task 3b 起，本面板只承担"判断拆解"——徽标(action_label)、"今日结论"标题+叙述
        # (forecast_label)、三项指标(综合判断/投入比例/把握程度)分别与结果表(建议列)、
        # 结论卡(verdict card)重复，已删除；详情面板的"结论"段同样覆盖了叙述文案。
        self.visual.delete("all")
        width, height = self._canvas_extent(self.visual, self._sc(340), self._sc(300))
        left, top, right, bottom = (
            self._sc(20),
            self._sc(20),
            width - self._sc(20),
            height - self._sc(20),
        )

        # 因子分解整体在面板可用高度内垂直居中，避免只贴顶留下一大片空白；与
        # _draw_empty_visual 使用同一组尺寸常量，保证真实/占位两态观感一致。
        bars_h = self._sc(120)
        bars_y = top + max(0.0, (bottom - top - self._sc(28) - bars_h) / 2) + self._sc(28)
        self._draw_factor_bars(left, bars_y, right - left, bars_h, result)

    def _round_rect(
        self,
        canvas: tk.Canvas,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        radius: float,
        **kwargs: Any,
    ) -> None:
        if x2 <= x1 or y2 <= y1:
            return
        radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        canvas.create_polygon(points, smooth=True, splinesteps=16, **kwargs)

    def _draw_factor_bars(
        self, x: float, y: float, width: float, height: float, result: AnalysisResult
    ) -> None:
        self.visual.create_text(
            x, y - self._sc(9), text="判断拆解", anchor=tk.W, fill=INK, font=(UI_FONT, 10, "bold")
        )
        factors = result.factor_scores[:5]
        if not factors:
            self.visual.create_text(x + width / 2, y + height / 2, text="暂无因子", fill=MUTED_INK)
            return
        row_h = height / max(len(factors), 1)
        for index, factor in enumerate(factors):
            row_y = y + index * row_h + self._sc(2)
            label_w = self._sc(86)
            bar_x = x + label_w
            bar_w = width - label_w - self._sc(48)
            self.visual.create_text(
                x,
                row_y + row_h / 2,
                text=_friendly_factor_name(factor.name),
                anchor=tk.W,
                fill=INK_SOFT,
                font=(UI_FONT, 8),
            )
            self._round_rect(
                self.visual,
                bar_x,
                row_y + self._sc(4),
                bar_x + bar_w,
                row_y + row_h - self._sc(4),
                self._sc(5),
                fill=CONTROL_BG,
                outline="",
            )
            zero = bar_x + bar_w / 2
            score = _safe_int(factor.score)
            max_abs_score = max(_safe_int(factor.max_abs_score, default=1), 1)
            ratio = min(1.0, abs(score) / max_abs_score)
            end = zero + (bar_w / 2) * ratio * (1 if score >= 0 else -1)
            color = _score_color(score)
            self.visual.create_line(
                zero, row_y + self._sc(2), zero, row_y + row_h - self._sc(2), fill=MUTED_LIGHT
            )
            self._round_rect(
                self.visual,
                min(zero, end),
                row_y + self._sc(4),
                max(zero, end),
                row_y + row_h - self._sc(4),
                self._sc(5),
                fill=color,
                outline="",
            )
            self.visual.create_text(
                x + width,
                row_y + row_h / 2,
                text=f"{score:+d}",
                anchor=tk.E,
                fill=color,
                font=(UI_FONT, 8, "bold"),
            )
