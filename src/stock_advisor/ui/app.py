from __future__ import annotations

import math
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Any

from ..services import store
from ..domain.alerts import FIELD_KEYS_BY_LABEL, FIELD_LABELS, OPS, check_rules, rule_summary
from ..domain.backtest import backtest_signals
from ..domain.chart import candle_layout, moving_average_series, nearest_index, price_bounds, price_to_y, volume_heights
from ..domain.compare import build_comparison_rows
from ..data.data_provider import EastmoneyProvider
from ..domain.engine import build_analysis_result
from ..domain.models import (
    AlertRule,
    AnalysisResult,
    AppConfig,
    BacktestReport,
    DailyBar,
    FundFlow,
    LEVEL_NAMES,
    Measurement,
    PositionPlan,
    Recommendation,
    STANDARD_LEVEL,
    SpectrumCell,
    WatchItem,
)
from ..domain.policy import decide, flip_hint, level_spec, position_plan, spectrum
from ..domain.presets import PRESETS, apply_tunables, get_preset
from ..domain.screener import OBJECTIVE_LABELS
from ..domain.symbols import normalize_symbol, parse_user_symbols
from ..services.workflow import AnalysisOutcome, ScreenReport, analyze_symbol, screen_and_recommend


from .theme import (
    MAX_SYMBOLS, MONITOR_INTERVAL_MS, APP_TITLE, APP_ICON_FILENAME, INFO_WINDOW_SIZE,
    MAIN_MIN_SIZE, WINDOW_MAX_SIZE, WINDOW_WORKAREA_MARGIN, CHILD_WINDOW_WORKAREA_MARGIN,
    WINDOW_ALPHA, MAX_CONTENT_WIDTH,
    CONTENT_MARGIN, HEADER_LOGO_SIZE, MENU_BUTTON_SHORT_WIDTH, MENU_BUTTON_TOOL_WIDTH,
    UI_FONT, MONO_FONT, PAGE_BG, CARD_BG, SURFACE_ALT, CONTROL_BG, CONTROL_HOVER_BG,
    CONTROL_DISABLED_BG, CARD_BORDER, BORDER_SOFT, GRID_COLOR, INK, INK_SOFT, MUTED_INK,
    MUTED_LIGHT, ACCENT, ACCENT_HOVER, ACCENT_PRESSED, ACCENT_SOFT, ACCENT_SOFT_HOVER,
    SELECTION_BG, DANGER_COLOR, DANGER_BG, COMMAND_BG, COMMAND_SURFACE, COMMAND_BORDER, COMMAND_INK,
    COMMAND_MUTED_INK, COMMAND_SELECTED_BG, COMMAND_SELECTED_INK, TABLE_HEADER_BG,
    SCROLLBAR_BG, SCROLLBAR_ACTIVE_BG, SCROLLBAR_PRESSED_BG, POS_COLOR, NEG_COLOR, FLAT_COLOR,
    POS_BG, NEG_BG, HOLD_BG, ACTION_BUTTON_LABELS, TABLE_MIN_VISIBLE_ROWS, TABLE_MAX_VISIBLE_ROWS,
    TABLE_EMPTY_VISIBLE_ROWS, DETAIL_NAV_SECTIONS, ASSET_DIR, SAMPLE_INPUT, DISCLAIMER,
    TABLE_COLUMNS,
)


def app_asset_path(filename: str) -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "assets" / filename
    return ASSET_DIR / filename


from ..data.sample_data import (
    _sample_quote_history, make_sample_analysis, make_sample_measurement,
    make_sample_history, make_sample_recommendation,
)


from .view_text import (
    level_summary, build_position_plan_text, build_backtest_text, build_spectrum_text,
    build_fund_flow_text, build_screener_overview, build_recommendation_header,
    build_visual_summary, build_detail_text, summarize_results, normalize_symbol_input_text,
    build_portfolio_overview, build_help_sections, build_manual_text, build_strategy_sections,
    build_strategy_explanation_text, _focus_symbols, _friendly_factor_name, _friendly_verdict,
)


from ..domain.formatting import (
    _positive_finite_float, _positive_finite_int, _safe_int,
    _fmt_decimal, _fmt_whole_percent, _fmt_percent_points,
    _fmt_rate_percent, _fmt_backtest_return, _fmt_backtest_excess,
    _format_number, _spin_step, _fmt_yi, _flow_direction,
    _fmt_percent, _fmt_percent_value, risk_level, _looks_risky, _looks_positive,
)


from .view_format import (
    watchlist_rows, format_comparison_row, snapshot_display, format_recommendation_row,
    build_snapshot_summary, build_snapshot_detail, format_result_row, table_sort_key,
    result_row_tags, detail_line_tags, _score_color, _action_color,
    format_results_for_clipboard, format_results_as_csv, format_table_rows_for_clipboard,
    format_table_rows_as_csv,
)


from ..domain.input_validate import (
    _parse_optional_positive, _parse_optional_positive_int, _parse_alert_threshold,
    is_partial_number, validate_tunable,
)


from .layout import (
    compute_centered_geometry, compute_window_position, compute_child_window_geometry,
    normalize_work_area_to_screen,
    choose_centering_screen_size, compute_centered_window,
    compute_content_band, active_mode_action, ui_scale, compute_main_geometry,
    compute_scaled_minimum, compute_workspace_columns, stacked_text_y,
)


class StockAdvisorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self._ui_scale = ui_scale(self._tk_scaling(root))
        self._center_window(self.root)
        self._apply_root_minimum()
        self._set_window_icon(self.root)
        self.provider = EastmoneyProvider()
        # 二期：跨会话持久化（自选股/持仓、本金、档位、预设）。读坏/不可写都回退默认。
        self.config_path = store.config_path()
        self._config = store.load_config(self.config_path)
        self.watch: list[WatchItem] = list(self._config.watchlist)
        self.alerts: list[AlertRule] = list(self._config.alerts)
        self._fired: set = set()
        self._monitoring = False
        self._monitor_on = False  # 工作线程读的纯布尔镜像（避免跨线程读 tk 变量）
        self._monitor_generation = 0
        self.monitor_queue: "queue.Queue" = queue.Queue()
        self.fund_flow_queue: "queue.Queue" = queue.Queue()
        self._fund_flow_polling = False
        self._ready = False
        self._closing = False
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.results: dict[str, AnalysisResult] = {}
        self.rec_meta: dict[str, Recommendation] = {}
        self.failures = 0
        self.sort_reverse: dict[str, bool] = {}
        self.cancel_event = threading.Event()
        self.busy = False
        self._discard_running_results = False
        self.active_preset_key = self._config.preset or PRESETS[0].key
        self.tunable_vars: dict[str, tk.StringVar] = {}
        self.deep_var = tk.BooleanVar(value=True)
        self.preset_var = tk.StringVar(value=self.active_preset_key)
        self.preset_desc_var = tk.StringVar(value=PRESETS[0].description)
        self.visual_metric_vars: dict[str, tk.StringVar] = {
            "action": tk.StringVar(value="未选择"),
            "position": tk.StringVar(value="—"),
            "confidence": tk.StringVar(value="—"),
            "move": tk.StringVar(value="—"),
        }
        # 决策强度（贯穿两页）与缓存：改档对缓存的客观测量重判，不重新联网。
        self.level_var = tk.IntVar(value=self._config.level)
        self.level_label_var = tk.StringVar(value=level_summary(self._config.level))
        self.capital_var = tk.StringVar(value=_format_number(self._config.capital))
        self.monitor_var = tk.BooleanVar(value=False)
        self.measurements: dict[str, Measurement | None] = {}
        self.histories: dict[str, list[DailyBar]] = {}
        self._current_history: list[DailyBar] = []
        self._build_ui()
        self._bind_shortcuts()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._select_preset(self.active_preset_key)
        if self.watch:
            self.status_var.set(f"已载入自选 {len(self.watch)} 只（点“自选股”查看）")
        self._ready = True
        # 窗口映射后按真实外框精确居中并按真实宽度排布内容，避免首帧未居中/未填满。
        self.root.after(60, self._finalize_geometry)

    def _persisted_config(self) -> AppConfig:
        fallback_capital = (
            self._config.capital
            if math.isfinite(self._config.capital) and self._config.capital > 0
            else AppConfig().capital
        )
        try:
            capital = float(self.capital_var.get())
        except (ValueError, tk.TclError):
            capital = fallback_capital
        if not math.isfinite(capital) or capital <= 0:
            capital = fallback_capital
        return AppConfig(
            watchlist=tuple(self.watch),
            capital=capital,
            level=self.level_var.get(),
            preset=self.active_preset_key,
            alerts=tuple(self.alerts),
        )

    def _save_persisted(self) -> bool:
        if not getattr(self, "_ready", False):
            return True
        self._config = self._persisted_config()
        return store.save_config(self.config_path, self._config)

    def _report_config_save_failure(
        self,
        action_text: str,
        parent: tk.Misc | None = None,
        show_dialog: bool = True,
    ) -> None:
        self.status_var.set(f"{action_text}，但配置未保存")
        if not show_dialog:
            return
        messagebox.showerror(
            "配置未保存",
            "当前更改只在本次运行中生效，配置文件暂时写入失败；请检查权限或磁盘空间后重试。",
            parent=parent,
        )

    def close(self) -> None:
        """Stop background activity before letting Tk destroy the main window."""
        if self._closing:
            return
        self._closing = True
        self.cancel_event.set()
        if self.busy:
            self._discard_running_results = True
        self._monitor_on = False
        self._monitoring = False
        try:
            self.monitor_var.set(False)
        except tk.TclError:
            pass
        self._drain_monitor_queue()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _results_by_code(self) -> dict:
        return {result.symbol.normalized: result for result in self.results.values()}

    def add_to_watchlist(self) -> None:
        codes = [result.symbol.normalized for result in self.results.values()]
        if not codes:
            messagebox.showinfo("加入自选", "当前没有可加入自选的分析结果。请先分析或选股。")
            return
        existing = {item.code for item in self.watch}
        added = 0
        for code in codes:
            if code not in existing:
                self.watch.append(WatchItem(code=code))
                existing.add(code)
                added += 1
        action_text = f"已加入自选 {added} 只（自选共 {len(self.watch)} 只）"
        if self._save_persisted():
            self.status_var.set(action_text)
        else:
            self._report_config_save_failure(action_text)

    def open_watchlist_manager(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("自选股 / 持仓")
        self._center_child_window(window, (self._sc(720), self._sc(520)))
        self._apply_child_minimum(window, (620, 420))
        window.configure(bg=PAGE_BG)
        window.transient(self.root)
        self._set_window_icon(window)

        container = ttk.Frame(window, padding=(self._sc(16), self._sc(14)))
        container.pack(fill=tk.BOTH, expand=True)
        self._build_dialog_heading(
            container,
            "自选股 / 持仓",
            "维护关注标的；填写成本与股数后，可结合已分析行情查看浮动盈亏。",
        )

        summary_strip = tk.Frame(container, bg=CARD_BORDER, padx=1, pady=1)
        summary_strip.pack(fill=tk.X, pady=(0, 8))
        summary_inner = tk.Frame(summary_strip, bg=CARD_BG)
        summary_inner.pack(fill=tk.X)
        summary_vars = {
            "total": tk.StringVar(value="0"),
            "held": tk.StringVar(value="0"),
            "analyzed": tk.StringVar(value="0"),
            "missing": tk.StringVar(value="0"),
        }
        summary_metrics: list[dict[str, Any]] = []
        for index, (title_text, key) in enumerate(
            (("自选", "total"), ("持仓", "held"), ("已分析", "analyzed"), ("待补", "missing"))
        ):
            if index:
                tk.Frame(summary_inner, width=1, bg=BORDER_SOFT).pack(side=tk.LEFT, fill=tk.Y)
            cell = tk.Frame(summary_inner, bg=CARD_BG, padx=self._sc(12), pady=self._sc(6))
            cell.pack(side=tk.LEFT, fill=tk.X, expand=True)
            title = tk.Label(cell, text=title_text, bg=CARD_BG, fg=MUTED_INK, font=(UI_FONT, 8))
            title.pack(anchor=tk.W)
            value = tk.Label(
                cell,
                textvariable=summary_vars[key],
                width=8,
                anchor=tk.W,
                bg=CARD_BG,
                fg=INK,
                font=(UI_FONT, 10, "bold"),
            )
            value.pack(anchor=tk.W)
            summary_metrics.append({"frame": cell, "title": title, "value": value, "value_var": summary_vars[key]})
        window._watchlist_summary_metrics = summary_metrics

        table_card = tk.Frame(container, bg=CARD_BORDER, padx=1, pady=1)
        table_card.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(table_card, columns=("code", "name", "cost", "shares", "pl"),
                            show="headings", height=10)
        watch_headings = {
            "code": ("代码", 110), "name": ("名称", 130), "cost": ("成本", 90),
            "shares": ("股数", 90), "pl": ("浮动盈亏", 190),
        }
        watch_anchors = {"code": tk.W, "name": tk.W, "cost": tk.E, "shares": tk.E, "pl": tk.E}
        for col, (title, width) in watch_headings.items():
            tree.heading(col, text=title)
            tree.column(col, width=self._sc(width), anchor=watch_anchors[col])
        tree.pack(fill=tk.BOTH, expand=True)

        def refresh() -> None:
            results_by_code = self._results_by_code()
            for child in tree.get_children():
                tree.delete(child)
            for index, row in enumerate(watchlist_rows(self.watch, results_by_code)):
                tree.insert("", tk.END, iid=str(index), values=row)
            held = sum(
                1
                for item in self.watch
                if _positive_finite_float(item.cost) is not None or _positive_finite_int(item.shares) is not None
            )
            summary_vars["total"].set(str(len(self.watch)))
            summary_vars["held"].set(str(held))
            summary_vars["analyzed"].set(str(sum(1 for item in self.watch if item.code in results_by_code)))
            summary_vars["missing"].set(str(max(0, len(self.watch) - held)))

        edit = ttk.Frame(container)
        edit.pack(fill=tk.X, pady=(10, 6))
        ttk.Label(edit, text="成本", style="Hint.TLabel").pack(side=tk.LEFT)
        cost_var = tk.StringVar()
        ttk.Entry(edit, textvariable=cost_var, width=10).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(edit, text="股数", style="Hint.TLabel").pack(side=tk.LEFT)
        shares_var = tk.StringVar()
        ttk.Entry(edit, textvariable=shares_var, width=10).pack(side=tk.LEFT, padx=(4, 12))

        def on_select(_event: object = None) -> None:
            selected = tree.selection()
            if not selected:
                return
            item = self.watch[int(selected[0])]
            cost = _positive_finite_float(item.cost)
            shares = _positive_finite_int(item.shares)
            cost_var.set(_format_number(cost) if cost is not None else "")
            shares_var.set(str(shares) if shares is not None else "")

        tree.bind("<<TreeviewSelect>>", on_select)

        def save_position() -> None:
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("保存持仓", "请先选中一只自选股。", parent=window)
                return
            cost = _parse_optional_positive(cost_var.get())
            shares = _parse_optional_positive_int(shares_var.get())
            if cost_var.get().strip() and cost is None:
                messagebox.showerror("保存持仓", "成本必须是正数或留空。", parent=window)
                return
            if shares_var.get().strip() and shares is None:
                messagebox.showerror("保存持仓", "股数必须是正整数或留空。", parent=window)
                return
            index = int(selected[0])
            self.watch[index] = WatchItem(code=self.watch[index].code, cost=cost, shares=shares)
            saved = self._save_persisted()
            refresh()
            if saved:
                self.status_var.set("持仓已更新")
            else:
                self._report_config_save_failure("持仓已更新", parent=window)

        def load_to_input() -> None:
            if not self.watch:
                messagebox.showinfo("载入自选", "自选为空。", parent=window)
                return
            codes = ", ".join(normalize_symbol(item.code).display for item in self.watch)
            self._select_tab(0)
            self._replace_input(codes)
            window.destroy()
            self.status_var.set("自选已载入输入框")

        def remove_selected() -> None:
            selected = tree.selection()
            if not selected:
                return
            del self.watch[int(selected[0])]
            saved = self._save_persisted()
            refresh()
            if saved:
                self.status_var.set("自选已删除")
            else:
                self._report_config_save_failure("自选已删除", parent=window)

        def clear_all() -> None:
            if self.watch and messagebox.askyesno("清空自选", "确定清空全部自选/持仓？", parent=window):
                self.watch.clear()
                saved = self._save_persisted()
                refresh()
                if saved:
                    self.status_var.set("自选已清空")
                else:
                    self._report_config_save_failure("自选已清空", parent=window)

        buttons = ttk.Frame(container)
        buttons.pack(fill=tk.X, pady=(6, 0))
        save_button = ttk.Button(buttons, text="保存持仓", style="Action.TButton", command=save_position)
        save_button.pack(side=tk.LEFT)
        more_button = ttk.Menubutton(buttons, text="更多操作", style="Action.TMenubutton")
        more_button.pack(side=tk.LEFT, padx=(8, 0))
        actions_menu = self._menu(more_button)
        actions_menu.add_command(label="载入到输入框", command=load_to_input)
        actions_menu.add_command(label="删除选中", command=remove_selected)
        actions_menu.add_command(label="清空自选", command=clear_all)
        more_button.configure(menu=actions_menu)
        close_button = ttk.Button(buttons, text="关闭", style="Action.TButton", command=window.destroy)
        close_button.pack(side=tk.RIGHT)
        window._watchlist_primary_buttons = [save_button, more_button, close_button]
        window._watchlist_actions_menu = actions_menu
        refresh()

    def _comparison_entries(self) -> list:
        cost_by_code = {item.code: item for item in self.watch}
        entries = []
        for iid, result in self.results.items():
            measurement = self.measurements.get(iid)
            if measurement is None:
                continue
            held = cost_by_code.get(result.symbol.normalized)
            entries.append(
                {
                    "result": result, "measurement": measurement, "risk": risk_level(result),
                    "cost": held.cost if held else None, "shares": held.shares if held else None,
                }
            )
        return entries

    def open_comparison(self) -> None:
        entries = self._comparison_entries()
        if not entries:
            messagebox.showinfo("横向对比", "先分析一些股票（个股分析或选股深度分析）再对比。")
            return
        rows = build_comparison_rows(entries)
        window = tk.Toplevel(self.root)
        window.title("横向对比")
        self._center_child_window(window, (self._sc(1200), self._sc(560)))
        self._apply_child_minimum(window, (900, 380))
        window.configure(bg=PAGE_BG)
        window.transient(self.root)
        self._set_window_icon(window)

        container = ttk.Frame(window, padding=(self._sc(16), self._sc(14)))
        container.pack(fill=tk.BOTH, expand=True)
        self._build_dialog_heading(
            container,
            "横向对比",
            "把已完成深度分析的标的放在同一张表里，比较结论、风险与持仓表现。",
        )

        summary_strip = tk.Frame(container, bg=CARD_BORDER, padx=1, pady=1)
        summary_strip.pack(fill=tk.X, pady=(0, 8))
        summary_inner = tk.Frame(summary_strip, bg=CARD_BG)
        summary_inner.pack(fill=tk.X)
        summary_values = {
            "total": str(len(rows)),
            "buy": str(sum(1 for row in rows if row.action == "BUY")),
            "risk": str(sum(1 for row in rows if row.risk == "高")),
            "held": str(sum(1 for row in rows if row.cost is not None)),
        }
        summary_vars = {key: tk.StringVar(value=value) for key, value in summary_values.items()}
        summary_metrics: list[dict[str, Any]] = []
        for index, (title_text, key) in enumerate(
            (("对比", "total"), ("买入", "buy"), ("高风险", "risk"), ("持仓", "held"))
        ):
            if index:
                tk.Frame(summary_inner, width=1, bg=BORDER_SOFT).pack(side=tk.LEFT, fill=tk.Y)
            cell = tk.Frame(summary_inner, bg=CARD_BG, padx=self._sc(12), pady=self._sc(6))
            cell.pack(side=tk.LEFT, fill=tk.X, expand=True)
            title = tk.Label(cell, text=title_text, bg=CARD_BG, fg=MUTED_INK, font=(UI_FONT, 8))
            title.pack(anchor=tk.W)
            value = tk.Label(
                cell,
                textvariable=summary_vars[key],
                width=8,
                anchor=tk.W,
                bg=CARD_BG,
                fg=INK,
                font=(UI_FONT, 10, "bold"),
            )
            value.pack(anchor=tk.W)
            summary_metrics.append({"frame": cell, "title": title, "value": value, "value_var": summary_vars[key]})
        window._comparison_summary_metrics = summary_metrics

        table_card = tk.Frame(container, bg=CARD_BORDER, padx=1, pady=1)
        table_card.pack(fill=tk.BOTH, expand=True)
        headings = {
            "code": ("代码", 100), "name": ("名称", 120), "last": ("现价", 80), "change": ("涨跌", 80),
            "score": ("综合分", 80), "conf": ("把握", 70), "risk": ("风险", 60), "pos": ("建议仓位", 80),
            "cost": ("持仓成本", 90), "pl": ("浮动盈亏", 150), "hint": ("档位提示", 230),
        }
        tree = ttk.Treeview(table_card, columns=tuple(headings), show="headings", height=12)
        comparison_anchors = {
            "code": tk.W, "name": tk.W, "last": tk.E, "change": tk.E, "score": tk.E,
            "conf": tk.E, "risk": tk.CENTER, "pos": tk.E, "cost": tk.E, "pl": tk.E, "hint": tk.W,
        }
        for col, (title, width) in headings.items():
            tree.heading(col, text=title)
            tree.column(col, width=self._sc(width), anchor=comparison_anchors[col])
        tree.tag_configure("action_buy", background=POS_BG, foreground=POS_COLOR)
        tree.tag_configure("action_sell", background=NEG_BG, foreground=NEG_COLOR)
        tree.tag_configure("action_hold", background=HOLD_BG, foreground=FLAT_COLOR)
        for index, row in enumerate(rows):
            tree.insert("", tk.END, iid=str(index), values=format_comparison_row(row),
                        tags=(f"action_{row.action.lower()}",))
        # 11 列按 DPI 放大后总宽仍可能超出可视区——加一条横向滚动条兜底，避免任意 DPI 下右侧列被裁掉。
        vscroll = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=tree.yview)
        hscroll = ttk.Scrollbar(table_card, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Button(container, text="关闭", style="Action.TButton", command=window.destroy).pack(anchor=tk.E, pady=(8, 0))

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
        canvas.create_line(left, y, max(canvas.winfo_width() - self._sc(12), left + self._sc(10)), y,
                           fill=BORDER_SOFT, dash=(2, 2), tags="crosshair")
        text = (f"{bar.date}  开{bar.open:.2f} 高{bar.high:.2f} 低{bar.low:.2f} "
                f"收{bar.close:.2f}  {bar.pct_change:+.2f}%")
        # 底框尺寸按字体实测宽/行高绘制（而非固定 7.2*len(text)/20px），避免高 DPI 下文字溢出。
        tooltip_font = tkfont.Font(root=self.root, font=("Microsoft YaHei UI", 8))
        box_w = tooltip_font.measure(text) + self._sc(8)
        box_h = tooltip_font.metrics("linespace") + self._sc(6)
        box_x0, box_y0 = left + self._sc(4), top + self._sc(2)
        canvas.create_rectangle(box_x0, box_y0, box_x0 + box_w, box_y0 + box_h,
                                fill=COMMAND_BG, outline="", tags="crosshair")
        canvas.create_text(box_x0 + self._sc(6), box_y0 + box_h / 2, text=text, anchor=tk.W, fill="#ffffff",
                           font=("Microsoft YaHei UI", 8), tags="crosshair")

    def _on_kline_leave(self, _event: object = None) -> None:
        self.kline_canvas.delete("crosshair")

    # ---- 条件预警 ----

    def open_alert_manager(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("条件预警")
        self._center_child_window(window, (self._sc(780), self._sc(560)))
        self._apply_child_minimum(window, (660, 460))
        window.configure(bg=PAGE_BG)
        window.transient(self.root)
        self._set_window_icon(window)

        container = ttk.Frame(window, padding=(self._sc(16), self._sc(14)))
        container.pack(fill=tk.BOTH, expand=True)
        self._build_dialog_heading(
            container,
            "条件预警",
            "价格、涨跌幅或综合分越过阈值时提醒；仅在程序开启且空闲时轮询。",
        )

        summary_strip = tk.Frame(container, bg=CARD_BORDER, padx=1, pady=1)
        summary_strip.pack(fill=tk.X, pady=(0, 8))
        summary_inner = tk.Frame(summary_strip, bg=CARD_BG)
        summary_inner.pack(fill=tk.X)
        summary_vars = {
            "rules": tk.StringVar(value="0"),
            "enabled": tk.StringVar(value="0"),
            "fired": tk.StringVar(value="0"),
            "monitor": tk.StringVar(value="关"),
        }
        summary_metrics: list[dict[str, Any]] = []
        for index, (title_text, key) in enumerate(
            (("规则", "rules"), ("启用", "enabled"), ("触发", "fired"), ("监控", "monitor"))
        ):
            if index:
                tk.Frame(summary_inner, width=1, bg=BORDER_SOFT).pack(side=tk.LEFT, fill=tk.Y)
            cell = tk.Frame(summary_inner, bg=CARD_BG, padx=self._sc(12), pady=self._sc(7))
            cell.pack(side=tk.LEFT, fill=tk.X, expand=True)
            title = tk.Label(cell, text=title_text, bg=CARD_BG, fg=MUTED_INK, font=(UI_FONT, 8))
            title.pack(anchor=tk.W)
            value = tk.Label(
                cell,
                textvariable=summary_vars[key],
                width=8,
                anchor=tk.W,
                bg=CARD_BG,
                fg=INK,
                font=(UI_FONT, 10, "bold"),
            )
            value.pack(anchor=tk.W)
            summary_metrics.append({"frame": cell, "title": title, "value": value, "value_var": summary_vars[key]})
        window._alert_summary_metrics = summary_metrics

        table_card = tk.Frame(container, bg=CARD_BORDER, padx=1, pady=1)
        table_card.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(table_card, columns=("rule", "enabled"), show="headings", height=9)
        tree.heading("rule", text="规则")
        tree.column("rule", width=self._sc(440), anchor=tk.W)
        tree.heading("enabled", text="启用")
        tree.column("enabled", width=self._sc(80), anchor=tk.CENTER)
        tree.pack(fill=tk.BOTH, expand=True)

        def sync_monitor_button() -> None:
            button = getattr(window, "_alert_monitor_button", None)
            if button is None:
                return
            if bool(self.monitor_var.get()):
                button.configure(
                    text="实时预警 开",
                    bg=ACCENT,
                    fg="#ffffff",
                    activebackground=ACCENT,
                    activeforeground="#ffffff",
                    selectcolor=ACCENT,
                )
            else:
                button.configure(
                    text="实时预警 关",
                    bg=CONTROL_BG,
                    fg=MUTED_INK,
                    activebackground=ACCENT_SOFT,
                    activeforeground=ACCENT,
                    selectcolor=CONTROL_BG,
                )

        def update_summary() -> None:
            summary_vars["rules"].set(str(len(self.alerts)))
            summary_vars["enabled"].set(str(sum(1 for rule in self.alerts if rule.enabled)))
            summary_vars["fired"].set(str(len(self._fired)))
            summary_vars["monitor"].set("开" if self.monitor_var.get() else "关")
            sync_monitor_button()

        def refresh() -> None:
            for child in tree.get_children():
                tree.delete(child)
            for index, rule in enumerate(self.alerts):
                tree.insert("", tk.END, iid=str(index),
                            values=(rule_summary(rule), "是" if rule.enabled else "否"))
            update_summary()

        form = ttk.Frame(container)
        form.pack(fill=tk.X, pady=(10, 6))
        ttk.Label(form, text="代码", style="Hint.TLabel").pack(side=tk.LEFT)
        code_var = tk.StringVar()
        ttk.Entry(form, textvariable=code_var, width=10).pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(form, text="字段", style="Hint.TLabel").pack(side=tk.LEFT)
        field_var = tk.StringVar(value=FIELD_LABELS["price"])
        field_combobox = ttk.Combobox(form, textvariable=field_var, width=9, state="readonly",
                                       values=list(FIELD_LABELS.values()))
        field_combobox.pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(form, text="条件", style="Hint.TLabel").pack(side=tk.LEFT)
        op_var = tk.StringVar(value=">=")
        ttk.Combobox(form, textvariable=op_var, width=4, state="readonly",
                     values=list(OPS)).pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(form, text="阈值", style="Hint.TLabel").pack(side=tk.LEFT)
        threshold_var = tk.StringVar()
        ttk.Entry(form, textvariable=threshold_var, width=8).pack(side=tk.LEFT, padx=(4, 10))

        def add_rule() -> None:
            try:
                symbol = normalize_symbol(code_var.get().strip())
            except ValueError:
                messagebox.showerror("添加预警", "代码无效。", parent=window)
                return
            field = FIELD_KEYS_BY_LABEL.get(field_var.get())
            op = op_var.get()
            if field is None or op not in OPS:
                messagebox.showerror("添加预警", "字段或条件无效。", parent=window)
                return
            threshold = _parse_alert_threshold(threshold_var.get())
            if threshold is None:
                messagebox.showerror("添加预警", "阈值必须是数字。", parent=window)
                return
            self.alerts.append(AlertRule(code=symbol.normalized, field=field, op=op, threshold=threshold))
            saved = self._save_persisted()
            refresh()
            code_var.set("")
            threshold_var.set("")
            if saved:
                self.status_var.set("预警已添加")
            else:
                self._report_config_save_failure("预警已添加", parent=window)

        add_button = ttk.Button(form, text="添加", style="Action.TButton", command=add_rule)
        add_button.pack(side=tk.LEFT, padx=(6, 0))

        def toggle_enabled() -> None:
            selected = tree.selection()
            if not selected:
                return
            index = int(selected[0])
            rule = self.alerts[index]
            self.alerts[index] = AlertRule(rule.code, rule.field, rule.op, rule.threshold, not rule.enabled)
            saved = self._save_persisted()
            refresh()
            if saved:
                self.status_var.set("预警已更新")
            else:
                self._report_config_save_failure("预警已更新", parent=window)

        def remove_selected() -> None:
            selected = tree.selection()
            if not selected:
                return
            del self.alerts[int(selected[0])]
            self._fired.clear()
            saved = self._save_persisted()
            refresh()
            if saved:
                self.status_var.set("预警已删除")
            else:
                self._report_config_save_failure("预警已删除", parent=window)

        def toggle_monitor_from_window() -> None:
            self._toggle_monitor()
            update_summary()

        controls = ttk.Frame(container)
        controls.pack(fill=tk.X, pady=(6, 0))
        monitor_button = tk.Checkbutton(
            controls,
            text="实时预警 关",
            variable=self.monitor_var,
            indicatoron=False,
            command=toggle_monitor_from_window,
            width=10,
            padx=7,
            pady=5,
            bd=0,
            relief=tk.FLAT,
            bg=CONTROL_BG,
            fg=MUTED_INK,
            selectcolor=CONTROL_BG,
            activebackground=ACCENT_SOFT,
            activeforeground=ACCENT,
            font=(UI_FONT, 9, "bold"),
        )
        monitor_button.pack(side=tk.LEFT)
        more_button = ttk.Menubutton(controls, text="更多操作", style="Action.TMenubutton")
        more_button.pack(side=tk.LEFT, padx=(8, 0))
        actions_menu = self._menu(more_button)
        actions_menu.add_command(label="启用/停用", command=toggle_enabled)
        actions_menu.add_command(label="删除选中", command=remove_selected)
        more_button.configure(menu=actions_menu)
        close_button = ttk.Button(controls, text="关闭", style="Action.TButton", command=window.destroy)
        close_button.pack(side=tk.RIGHT)
        window._alert_monitor_button = monitor_button
        window._alert_primary_buttons = [add_button, monitor_button, more_button, close_button]
        window._alert_actions_menu = actions_menu
        window._alert_field_combobox = field_combobox
        refresh()

    def _toggle_monitor(self) -> None:
        self._monitor_on = bool(self.monitor_var.get())
        self._monitor_generation += 1
        if self._monitor_on:
            self._fired.clear()
            self.status_var.set("实时预警已开启（每 60 秒检查自选预警）")
            generation = self._monitor_generation
            self._monitor_tick(generation)
            self._poll_monitor(generation)
        else:
            self._monitoring = False
            self._drain_monitor_queue()
            self.status_var.set("实时预警已关闭")
            self.alert_banner.pack_forget()

    def _monitor_tick(self, generation: int) -> None:
        if self._closing:
            return
        if generation != self._monitor_generation or not self.monitor_var.get():
            return
        if not self.busy and not self._monitoring:
            codes = sorted({rule.code for rule in self.alerts if rule.enabled})
            if codes:
                self._monitoring = True
                threading.Thread(target=self._monitor_worker, args=(codes, self.level_var.get(), generation),
                                 daemon=True).start()
        self.root.after(MONITOR_INTERVAL_MS, self._monitor_tick, generation)

    def _monitor_worker(self, codes: list, level: int, generation: int) -> None:
        results: dict = {}
        for code in codes:
            if not self._monitor_on or generation != self._monitor_generation:
                break
            try:
                symbol = normalize_symbol(code)
            except ValueError:
                continue
            try:
                outcome = analyze_symbol(symbol, self.provider, level)
            except Exception:  # noqa: BLE001 - 监控线程兜底，不影响 UI
                continue
            if outcome.ok and outcome.result is not None:
                results[code] = outcome.result
        if self._monitor_on and generation == self._monitor_generation:
            self.monitor_queue.put((generation, results))

    def _poll_monitor(self, generation: int) -> None:
        if self._closing:
            return
        if generation != self._monitor_generation or not self.monitor_var.get():
            self._monitoring = False
            self._drain_monitor_queue()
            return
        try:
            while True:
                generation, results = self.monitor_queue.get_nowait()
                if generation != self._monitor_generation:
                    continue
                self._monitoring = False
                self._check_alerts(results)
        except queue.Empty:
            pass
        self.root.after(700, self._poll_monitor, generation)

    def _drain_monitor_queue(self) -> None:
        try:
            while True:
                self.monitor_queue.get_nowait()
        except queue.Empty:
            pass

    def _check_alerts(self, results_by_code: dict) -> None:
        newly, self._fired = check_rules(self.alerts, results_by_code, self._fired)
        if newly:
            self._notify_alerts(newly)

    def _notify_alerts(self, newly: list) -> None:
        text = "【预警触发】" + "；".join(rule_summary(rule) for rule in newly)
        self.alert_banner.configure(text=text)
        self.alert_banner.pack(fill=tk.X, pady=(0, 8), after=self.results_toolbar)
        self.status_var.set(text)
        try:
            self.root.bell()
        except tk.TclError:
            pass

    # ---- 个股资金流（按需、降级安全；数据源偶发不稳定，不进核心流程）----

    def show_fund_flow(self) -> None:
        selected = self.tree.selection()
        result = self.results.get(selected[0]) if selected else None
        if result is None:
            messagebox.showinfo("资金流", "请先选择一只已分析的股票。")
            return
        self.status_var.set(f"正在查询 {result.symbol.display} 主力资金流...")
        threading.Thread(target=self._fund_flow_worker, args=(result.symbol, result.name),
                         daemon=True).start()
        # 轮询链是常驻单例：懒启动一次即可，后续请求复用同一条链，避免重复排程。
        if not self._fund_flow_polling:
            self._fund_flow_polling = True
            self.root.after(120, self._poll_fund_flow)

    def _fund_flow_worker(self, symbol, name: str) -> None:
        """daemon 线程：只负责取数与入队，禁止触碰 Tk（与其余三个 worker 的约定一致）。"""
        try:
            flow = self.provider.fetch_fund_flow(symbol)
        except Exception:  # noqa: BLE001 - 资金流取不到时降级，不影响其它
            flow = None
        self.fund_flow_queue.put((symbol, name, flow))

    def _poll_fund_flow(self) -> None:
        if self._closing:
            return
        try:
            while True:
                symbol, name, flow = self.fund_flow_queue.get_nowait()
                self._show_fund_flow_result(symbol, name, flow)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_fund_flow)

    def _show_fund_flow_result(self, symbol, name: str, flow) -> None:
        if flow is None:
            self.status_var.set("资金流暂取不到")
            messagebox.showinfo("资金流", f"{symbol.display} 主力资金流暂取不到（数据源不稳定，可稍后重试）。")
            return
        self.status_var.set(f"{symbol.display} 资金流已更新")
        messagebox.showinfo("主力资金流", build_fund_flow_text(flow, name))

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=PAGE_BG)
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("TLabel", background=PAGE_BG, foreground=INK)
        style.configure("Title.TLabel", font=(UI_FONT, 18, "bold"), foreground=INK, background=PAGE_BG)
        style.configure("Subtitle.TLabel", foreground=MUTED_INK, font=(UI_FONT, 10), background=PAGE_BG)
        style.configure("Hint.TLabel", foreground=MUTED_INK, font=(UI_FONT, 10), background=PAGE_BG)
        style.configure("SurfaceHint.TLabel", foreground=MUTED_INK, font=(UI_FONT, 10), background=CARD_BG)
        style.configure("SectionTitle.TLabel", foreground=INK, font=(UI_FONT, 12, "bold"), background=PAGE_BG)
        style.configure("DialogTitle.TLabel", foreground=INK, font=(UI_FONT, 16, "bold"), background=PAGE_BG)
        style.configure("HeaderMeta.TLabel", foreground=MUTED_INK, font=(UI_FONT, 9), background=PAGE_BG)
        style.configure(
            "LevelHint.TLabel",
            foreground=COMMAND_MUTED_INK,
            font=(UI_FONT, 10),
            background=COMMAND_BG,
        )
        style.configure(
            "Step.TLabel",
            background=ACCENT_SOFT,
            foreground=ACCENT,
            padding=(self._sc(14), self._sc(8)),
            font=(UI_FONT, 10, "bold"),
        )
        style.configure(
            "Overview.TLabel",
            background=CONTROL_BG,
            foreground=INK_SOFT,
            padding=(self._sc(16), self._sc(10)),
            font=(UI_FONT, 10, "bold"),
        )

        # 研究工作台采用扁平控件：状态只由明度/颜色变化表达，按下不再造成控件几何位移。
        style.configure(
            "Primary.TButton",
            padding=(self._sc(20), self._sc(12)),
            font=(UI_FONT, 11, "bold"),
            background=ACCENT,
            foreground="#ffffff",
            borderwidth=0,
            relief="flat",
            focusthickness=1,
            focuscolor=ACCENT_SOFT,
        )
        style.map("Primary.TButton",
                  background=[("pressed", ACCENT_PRESSED), ("active", ACCENT_HOVER),
                              ("disabled", MUTED_LIGHT)],
                  foreground=[("disabled", SURFACE_ALT)],
                  relief=[("pressed", "flat"), ("!pressed", "flat")])

        for name, pad in (
            ("Action.TButton", (self._sc(14), self._sc(10))),
            ("Quiet.TButton", (self._sc(13), self._sc(10))),
            ("Preset.TButton", (self._sc(16), self._sc(11))),
        ):
            style.configure(name, padding=pad, font=(UI_FONT, 10),
                            background=CONTROL_BG, foreground=INK_SOFT, borderwidth=0, relief="flat",
                            focusthickness=1, focuscolor=ACCENT_SOFT)
            style.map(name,
                      background=[("pressed", ACCENT_SOFT_HOVER), ("active", CONTROL_HOVER_BG),
                                  ("disabled", CONTROL_DISABLED_BG)],
                      foreground=[("disabled", MUTED_LIGHT)],
                      relief=[("pressed", "flat"), ("!pressed", "flat")])

        style.configure("PresetActive.TButton", padding=(self._sc(16), self._sc(11)), font=(UI_FONT, 10, "bold"),
                        background=ACCENT, foreground="#ffffff", borderwidth=0, relief="flat", focusthickness=1,
                        focuscolor=ACCENT_SOFT)
        style.map("PresetActive.TButton",
                  background=[("pressed", ACCENT_PRESSED), ("active", ACCENT_HOVER)],
                  relief=[("pressed", "flat"), ("!pressed", "flat")])
        style.configure("Action.TMenubutton", padding=(self._sc(14), self._sc(10)), font=(UI_FONT, 10),
                        background=CONTROL_BG, foreground=INK_SOFT, borderwidth=0, relief="flat",
                        focusthickness=1, focuscolor=ACCENT_SOFT)
        style.configure("Quiet.TMenubutton", padding=(self._sc(13), self._sc(10)), font=(UI_FONT, 10),
                        background=CONTROL_BG, foreground=INK_SOFT, borderwidth=0, relief="flat",
                        focusthickness=1, focuscolor=ACCENT_SOFT)
        for name in ("Action.TMenubutton", "Quiet.TMenubutton"):
            style.map(name,
                      background=[("pressed", ACCENT_SOFT_HOVER), ("active", CONTROL_HOVER_BG),
                                  ("disabled", CONTROL_DISABLED_BG)],
                      foreground=[("disabled", MUTED_LIGHT)],
                      relief=[("pressed", "flat"), ("!pressed", "flat")])

        # 选项卡改为自绘分段胶囊（见 _build_tabs / _show_info_window），不再用 ttk.Notebook 样式，
        # 因为 clam 主题的选中标签会明显变矮/位移，难以做到等尺寸精致。

        style.configure("Treeview", rowheight=self._sc(42), font=(UI_FONT, 10), borderwidth=0,
                        background=CARD_BG, fieldbackground=CARD_BG, foreground=INK)
        style.configure("Treeview.Heading", font=(UI_FONT, 10, "bold"),
                        background=TABLE_HEADER_BG, foreground=INK_SOFT, relief="flat", borderwidth=0,
                        padding=(0, self._sc(8)))
        style.map("Treeview", background=[("selected", SELECTION_BG)], foreground=[("selected", INK)])
        style.map("Treeview.Heading", background=[("active", ACCENT_SOFT)])

        for field_style in ("TEntry", "TCombobox", "TSpinbox"):
            style.configure(field_style, fieldbackground=CARD_BG, background=CONTROL_BG,
                            bordercolor=CARD_BORDER, lightcolor=CARD_BORDER, darkcolor=CARD_BORDER,
                            foreground=INK, padding=self._sc(7), relief="flat")
            style.map(field_style, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
                      darkcolor=[("focus", ACCENT)])
        style.configure("TSpinbox", arrowsize=self._sc(13))
        style.configure("TCheckbutton", background=PAGE_BG, foreground=INK)
        style.map("TCheckbutton", background=[("active", PAGE_BG)])
        style.configure("Horizontal.TProgressbar", troughcolor=CONTROL_BG, background=ACCENT,
                        bordercolor=CONTROL_BG, lightcolor=ACCENT, darkcolor=ACCENT,
                        thickness=self._sc(14))
        # 细窄、低对比的滚动条，避免抢夺工作区视觉焦点。
        for _orient in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            style.configure(_orient, gripcount=0, borderwidth=0, relief="flat",
                            background=SCROLLBAR_BG, troughcolor=PAGE_BG, bordercolor=PAGE_BG,
                            lightcolor=PAGE_BG, darkcolor=PAGE_BG, arrowcolor=MUTED_LIGHT,
                            arrowsize=self._sc(11), width=self._sc(11))
            style.map(_orient, background=[("active", SCROLLBAR_ACTIVE_BG),
                                           ("pressed", SCROLLBAR_PRESSED_BG)])

    def _apply_glass_effect(self) -> None:
        # 整窗不透明：不创建分层窗口，省去逐帧合成开销，桌面底色也不会透出（兼顾性能与观感）。
        if WINDOW_ALPHA >= 1.0:
            return
        try:
            self.root.attributes("-alpha", WINDOW_ALPHA)
        except tk.TclError:
            pass

    def _scrolled_text(
        self, parent: tk.Misc, autohide_scrollbar: bool = False, **text_kwargs: Any
    ) -> tuple[tk.Frame, tk.Text, ttk.Scrollbar]:
        """tk.Text + 统一风格的 ttk 竖向滚动条；返回 (容器, 文本框, 滚动条)。

        所有可滚动文本框（输入框、解释区、说明窗）都走这里，滚动条样式与页面/表格一致，
        不再混入经典 tk 滚动条那种粗边带箭头的不一致外观。
        """
        bg = str(text_kwargs.get("background", CARD_BG))
        holder = tk.Frame(parent, bg=bg)
        text = tk.Text(holder, **text_kwargs)  # type: ignore[arg-type]
        bar = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=bar.set)
        if not autohide_scrollbar:
            bar.pack(side=tk.RIGHT, fill=tk.Y)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return holder, text, bar

    def _menu(self, owner: tk.Misc) -> tk.Menu:
        """创建与研究工作台主题一致的弹出菜单。"""
        return tk.Menu(
            owner,
            tearoff=False,
            background=CARD_BG,
            foreground=INK,
            activebackground=ACCENT_SOFT,
            activeforeground=ACCENT,
            borderwidth=1,
            relief=tk.FLAT,
            font=(UI_FONT, 10),
        )

    def _build_dialog_heading(self, parent: tk.Misc, title: str, subtitle: str) -> ttk.Frame:
        heading = ttk.Frame(parent)
        heading.pack(fill=tk.X, pady=(0, self._sc(12)))
        ttk.Label(heading, text=title, style="DialogTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(heading, text=subtitle, style="Subtitle.TLabel").pack(anchor=tk.W, pady=(self._sc(3), 0))
        return heading

    def _build_ui(self) -> None:
        self.root.configure(bg=PAGE_BG)
        self._apply_glass_effect()
        self._configure_styles()

        shell = ttk.Frame(self.root)
        shell.pack(fill=tk.BOTH, expand=True)
        self.page_canvas = tk.Canvas(shell, bg=PAGE_BG, highlightthickness=0)
        page_scrollbar = ttk.Scrollbar(shell, orient=tk.VERTICAL, command=self.page_canvas.yview)
        self.page_canvas.configure(yscrollcommand=page_scrollbar.set)
        page_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.page_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 居中内容带：内容固定在 outer 内，由 _on_canvas_configure 限制最大宽度并左右均匀留白。
        content_margin = self._sc(CONTENT_MARGIN)
        # 水平留白由 compute_content_band 负责；outer 只补上下同值留白，避免横向 margin 双算。
        outer = ttk.Frame(self.page_canvas, padding=(0, content_margin, 0, content_margin))
        self.page_window = self.page_canvas.create_window((0, 0), window=outer, anchor=tk.NW)
        self._bind_page_scroll(outer)

        self._build_header(outer)
        self._build_strength_bar(outer)

        self._build_tabs(outer)

        self._build_results_region(outer)

    def _build_tabs(self, outer: ttk.Frame) -> None:
        """构建两页工作区；模式切换按钮由统一控制栏承载。"""
        holder = tk.Frame(outer, bg=PAGE_BG)
        holder.pack(fill=tk.X, pady=(0, self._sc(16)))
        individual_tab = ttk.Frame(holder)
        screener_tab = ttk.Frame(holder)
        self._tab_frames = [individual_tab, screener_tab]
        self._build_individual_tab(individual_tab)
        self._build_screener_tab(screener_tab)
        self._select_tab(0)

    def _hover_tab(self, index: int, entering: bool) -> None:
        if index != self._active_tab:
            self._tab_buttons[index].configure(bg=COMMAND_BORDER if entering else COMMAND_SURFACE)

    def _select_tab(self, index: int) -> None:
        self._active_tab = index
        for i, button in enumerate(self._tab_buttons):
            if i == index:
                button.configure(bg=COMMAND_SELECTED_BG, fg=COMMAND_SELECTED_INK)
            else:
                button.configure(bg=COMMAND_SURFACE, fg=COMMAND_MUTED_INK)
        for i, frame in enumerate(self._tab_frames):
            if i == index:
                frame.pack(fill=tk.BOTH, expand=True)
            else:
                frame.pack_forget()

    def _build_header(self, outer: ttk.Frame) -> None:
        self.header_frame = ttk.Frame(outer)
        self.header_frame.pack(fill=tk.X, pady=(0, self._sc(10)))
        self.logo_canvas = tk.Canvas(
            self.header_frame,
            width=self._sc(HEADER_LOGO_SIZE),
            height=self._sc(HEADER_LOGO_SIZE),
            bg=PAGE_BG,
            highlightthickness=0,
        )
        self.logo_canvas.pack(side=tk.LEFT, anchor=tk.NW, padx=(0, self._sc(14)), pady=(self._sc(2), 0))
        self._draw_logo(self.logo_canvas)

        title_block = ttk.Frame(self.header_frame)
        title_block.pack(side=tk.LEFT, anchor=tk.W, fill=tk.X, expand=True)
        self.header_title_label = ttk.Label(title_block, text=APP_TITLE, style="Title.TLabel")
        self.header_title_label.pack(anchor=tk.W)
        self.header_subtitle_label = ttk.Label(
            title_block,
            text="个股判断、全市场筛选与仓位风控，一处完成。",
            style="Subtitle.TLabel",
        )
        self.header_subtitle_label.pack(anchor=tk.W, pady=(self._sc(3), 0))

        self.header_actions = ttk.Frame(self.header_frame)
        self.header_actions.pack(side=tk.RIGHT, anchor=tk.NE, pady=self._sc(3))
        self.header_help_button = ttk.Menubutton(
            self.header_actions,
            text="说明",
            style="Quiet.TMenubutton",
            width=MENU_BUTTON_SHORT_WIDTH,
        )
        self.header_help_button.pack(side=tk.RIGHT)
        self.header_meta_label = ttk.Label(
            self.header_actions,
            text="本地规则引擎 · 行情按需更新",
            style="HeaderMeta.TLabel",
        )
        self.header_meta_label.pack(side=tk.RIGHT, padx=(0, self._sc(16)), pady=(self._sc(10), 0))
        self.header_help_menu = self._menu(self.header_help_button)
        for label, command in (
            ("使用说明", self.show_help),
            ("策略说明", self.show_strategy),
        ):
            self.header_help_menu.add_command(label=label, command=command)
        self.header_help_button.configure(menu=self.header_help_menu)

    def _build_strength_bar(self, outer: ttk.Frame) -> None:
        """宽松的决策控制台：模式与档位保持同一视觉锚点，但提供更大的触达面积。"""
        self.mode_control_shell = tk.Frame(outer, bg=COMMAND_BORDER, padx=1, pady=1)
        self.mode_control_shell.pack(fill=tk.X, pady=(self._sc(4), self._sc(16)))
        self.mode_control_body = tk.Frame(self.mode_control_shell, bg=COMMAND_BG)
        self.mode_control_body.pack(fill=tk.X)

        self.mode_primary_row = tk.Frame(self.mode_control_body, bg=COMMAND_BG)
        self.mode_primary_row.pack(fill=tk.X)
        self.mode_primary_row.grid_columnconfigure(0, weight=1)
        self.mode_primary_row.grid_columnconfigure(2, weight=1)

        self.mode_row = tk.Frame(self.mode_primary_row, bg=COMMAND_BG)
        self.mode_row.grid(
            row=0,
            column=0,
            sticky=tk.E,
            padx=(self._sc(18), self._sc(20)),
            pady=(self._sc(13), self._sc(11)),
        )
        tk.Label(
            self.mode_row,
            text="工作模式",
            bg=COMMAND_BG,
            fg=COMMAND_MUTED_INK,
            font=(UI_FONT, 10, "bold"),
        ).pack(side=tk.LEFT, padx=(0, self._sc(12)))
        self.mode_tab_group = tk.Frame(self.mode_row, bg=COMMAND_BORDER, padx=1, pady=1)
        self.mode_tab_group.pack(side=tk.LEFT)
        self.mode_tab_group.grid_rowconfigure(0, minsize=self._sc(40))
        self._active_tab = 0
        self._tab_buttons: list[tk.Label] = []
        for index, text in enumerate(("个股分析", "全市场选股")):
            seg = tk.Label(
                self.mode_tab_group,
                text=text,
                font=(UI_FONT, 10, "bold"),
                width=12,
                padx=2,
                pady=8,
                cursor="hand2",
                bd=0,
                bg=COMMAND_SURFACE,
                fg=COMMAND_MUTED_INK,
            )
            seg.grid(row=0, column=index, sticky=tk.NSEW, padx=(0 if index == 0 else 1, 0))
            seg.bind("<Button-1>", lambda _e, i=index: self._select_tab(i))
            seg.bind("<Enter>", lambda _e, i=index: self._hover_tab(i, True))
            seg.bind("<Leave>", lambda _e, i=index: self._hover_tab(i, False))
            self._tab_buttons.append(seg)

        self.mode_control_divider = tk.Frame(self.mode_primary_row, width=1, bg=COMMAND_BORDER)
        self.mode_control_divider.grid(
            row=0,
            column=1,
            sticky=tk.NS,
            pady=(self._sc(12), self._sc(10)),
        )

        self.level_control_group = tk.Frame(self.mode_primary_row, bg=COMMAND_BG)
        self.level_control_group.grid(
            row=0,
            column=2,
            sticky=tk.W,
            padx=(self._sc(20), self._sc(18)),
            pady=(self._sc(13), self._sc(11)),
        )
        tk.Label(self.level_control_group, text="决策强度", bg=COMMAND_BG, fg=COMMAND_MUTED_INK,
                 font=(UI_FONT, 10, "bold")).pack(side=tk.LEFT, padx=(0, self._sc(12)))
        selector = tk.Frame(self.level_control_group, bg=COMMAND_BORDER, padx=1, pady=1)
        selector.pack(side=tk.LEFT)
        selector.grid_rowconfigure(0, minsize=self._sc(40))
        self.level_buttons: list[tk.Radiobutton] = []
        for level, label in enumerate(("L1稳健", "L2稳进", "L3标准", "L4积极", "L5激进"), start=1):
            button = tk.Radiobutton(
                selector,
                text=label,
                variable=self.level_var,
                value=level,
                indicatoron=False,
                command=self._on_level_change,
                width=8,
                padx=3,
                pady=7,
                borderwidth=0,
                relief=tk.FLAT,
                bg=COMMAND_SURFACE,
                fg=COMMAND_MUTED_INK,
                selectcolor=COMMAND_SURFACE,
                activebackground=COMMAND_BORDER,
                activeforeground=COMMAND_INK,
                font=(UI_FONT, 10, "bold"),
            )
            button.grid(row=0, column=level - 1, sticky=tk.NSEW, padx=(0 if level == 1 else 1, 0))
            self.level_buttons.append(button)
        self._sync_level_buttons()

        # 档位摘要：level_label_var 早已在 __init__ 里被 _on_level_change 实时 set()，但此前
        # 未绑定任何控件——切档用户看不到"标准档 · 买入线 +25 / 卖出线 -25 · ..."这句提示。
        # LevelHint.TLabel 使用 COMMAND_BG 专属背景，避免把 PAGE_BG 的普通提示标签直接放进
        # 深色工作带而露出色块。用 ttk.Label 而非 tk.Label，是为了不影响
        # test_unified_control_bar_keeps_strength_selector_visible 对
        # level_control_group 下 tk.Label 子控件数量（仅"决策强度"一个）的既有断言。
        self.level_hint_label = ttk.Label(
            self.mode_control_body,
            textvariable=self.level_label_var,
            style="LevelHint.TLabel",
            anchor=tk.W,
        )
        self.level_hint_label.pack(
            fill=tk.X,
            padx=self._sc(18),
            pady=(0, self._sc(15)),
        )

    def _build_individual_tab(self, parent: ttk.Frame) -> None:
        self.input_panel_shell = tk.Frame(parent, bg=CARD_BORDER, padx=1, pady=1)
        self.input_panel_shell.pack(fill=tk.X)
        self.input_panel_body = tk.Frame(self.input_panel_shell, bg=CARD_BG)
        self.input_panel_body.pack(fill=tk.X)
        self.symbol_input_holder, self.symbol_input, self.symbol_scroll = self._scrolled_text(
            self.input_panel_body, autohide_scrollbar=True,
            height=3, wrap=tk.WORD, font=(MONO_FONT, 12), relief=tk.FLAT,
            borderwidth=0, background=SURFACE_ALT, foreground=INK, insertbackground=ACCENT,
            padx=self._sc(14), pady=self._sc(10),
        )
        self.symbol_input.insert("1.0", SAMPLE_INPUT)
        self.symbol_input.edit_modified(False)
        self.symbol_input.bind("<<Modified>>", self._on_symbol_input_modified, add="+")
        self.symbol_input.bind("<Configure>", lambda _event: self._schedule_symbol_scrollbar_refresh(), add="+")
        self._schedule_symbol_scrollbar_refresh()

        self.input_context_frame = tk.Frame(
            self.input_panel_body,
            bg=CARD_BG,
            padx=self._sc(16),
            pady=self._sc(11),
        )
        self.input_context_frame.pack(side=tk.TOP, fill=tk.X)
        self.input_context_title = tk.Label(
            self.input_context_frame, text="研究标的", bg=CARD_BG, fg=INK,
            font=(UI_FONT, 11, "bold"), anchor=tk.W,
        )
        self.input_context_title.pack(side=tk.LEFT, anchor=tk.W)
        self.input_context_hint = tk.Label(
            self.input_context_frame, text=f"最多 {MAX_SYMBOLS} 只", bg=CARD_BG, fg=MUTED_INK,
            font=(UI_FONT, 9), anchor=tk.E,
        )
        self.input_context_hint.pack(side=tk.RIGHT, anchor=tk.E)
        self.input_context_divider = tk.Frame(self.input_panel_body, height=1, bg=BORDER_SOFT)
        self.input_context_divider.pack(side=tk.TOP, fill=tk.X)

        self.input_panel_divider = tk.Frame(self.input_panel_body, width=1, bg=BORDER_SOFT)
        self.input_action_frame = tk.Frame(self.input_panel_body, bg=CARD_BG)
        self.input_action_frame.pack(
            side=tk.RIGHT,
            padx=(self._sc(16), self._sc(16)),
            pady=self._sc(16),
        )
        self.input_panel_divider.pack(side=tk.RIGHT, fill=tk.Y, pady=self._sc(14))
        self.symbol_input_holder.pack(
            side=tk.LEFT,
            fill=tk.BOTH,
            expand=True,
            padx=(self._sc(16), 0),
            pady=self._sc(14),
        )
        self.analyze_button = ttk.Button(self.input_action_frame, text="开始分析", style="Primary.TButton", command=self.analyze)
        self.analyze_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(self.input_action_frame, text="停止", style="Action.TButton", command=self.stop, state=tk.DISABLED)
        self.input_primary_buttons = [self.analyze_button, self.stop_button]
        self.input_tools_button = ttk.Menubutton(
            self.input_action_frame,
            text="输入工具",
            style="Action.TMenubutton",
            width=MENU_BUTTON_TOOL_WIDTH,
        )
        self.input_tools_button.pack(side=tk.LEFT, padx=(self._sc(10), 0))
        self._stop_button_pack_options = {
            "side": tk.LEFT,
            "padx": (self._sc(10), 0),
            "before": self.input_tools_button,
        }
        self.input_tools_menu = self._menu(self.input_tools_button)
        for label, command in (
            ("整理代码", self.clean_input),
            ("示例", self.fill_sample),
            ("清空", self.clear),
        ):
            self.input_tools_menu.add_command(label=label, command=command)
        self.input_tools_button.configure(menu=self.input_tools_menu)

    def _schedule_symbol_scrollbar_refresh(self) -> None:
        self.root.after_idle(self._refresh_symbol_scrollbar)

    def _on_symbol_input_modified(self, _event: object | None = None) -> None:
        if self.symbol_input.edit_modified():
            self.symbol_input.edit_modified(False)
        self._schedule_symbol_scrollbar_refresh()

    def _refresh_symbol_scrollbar(self) -> None:
        self.symbol_input.update_idletasks()
        first, last = self.symbol_input.yview()
        should_show = first > 0.0 or last < 1.0
        if should_show and not self.symbol_scroll.winfo_ismapped():
            self.symbol_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        elif not should_show and self.symbol_scroll.winfo_ismapped():
            self.symbol_scroll.pack_forget()

    def _build_screener_tab(self, parent: ttk.Frame) -> None:
        self.screener_section_title = ttk.Label(parent, text="策略扫描", style="SectionTitle.TLabel")
        self.screener_section_title.pack(anchor=tk.W)
        ttk.Label(
            parent,
            text="选择预设并微调参数，从当前全市场快照中筛选；深度分析可继续给出买 / 持 / 卖。",
            style="Hint.TLabel",
        ).pack(anchor=tk.W, pady=(self._sc(4), self._sc(14)))

        cards = tk.Frame(parent, bg=CARD_BORDER, padx=1, pady=1)
        cards.pack(fill=tk.X)
        self.preset_buttons: dict[str, tk.Radiobutton] = {}
        for index, preset in enumerate(PRESETS):
            button = tk.Radiobutton(
                cards,
                text=preset.name,
                variable=self.preset_var,
                value=preset.key,
                indicatoron=False,
                command=lambda key=preset.key: self._select_preset(key),
                width=14,
                padx=10,
                pady=10,
                borderwidth=0,
                relief=tk.FLAT,
                bg=CARD_BG,
                fg=MUTED_INK,
                selectcolor=CARD_BG,
                activebackground=ACCENT_SOFT,
                activeforeground=ACCENT,
                font=(UI_FONT, 10, "bold"),
            )
            button.grid(row=index // 3, column=index % 3, sticky="ew", padx=(0 if index % 3 == 0 else 1, 0), pady=(0 if index < 3 else 1, 0))
            self.preset_buttons[preset.key] = button
        for column in range(3):
            cards.columnconfigure(column, weight=1)

        ttk.Label(parent, textvariable=self.preset_desc_var, style="Subtitle.TLabel", wraplength=self._sc(760)).pack(
            anchor=tk.W, pady=(self._sc(12), self._sc(10))
        )

        self.tunable_frame = ttk.Frame(parent)
        self.tunable_frame.pack(fill=tk.X, pady=(self._sc(4), self._sc(12)))

        run_row = ttk.Frame(parent)
        run_row.pack(fill=tk.X, pady=(self._sc(6), 0))
        self.screen_button = ttk.Button(run_row, text="开始选股", style="Primary.TButton", command=self.start_screen)
        self.screen_button.pack(side=tk.LEFT)
        self.screen_stop_button = ttk.Button(
            run_row, text="停止", style="Action.TButton", command=self.stop, state=tk.DISABLED
        )
        self.deep_toggle_button = tk.Checkbutton(
            run_row,
            text="深度分析 开",
            variable=self.deep_var,
            indicatoron=False,
            command=self._sync_deep_toggle,
            width=12,
            padx=12,
            pady=10,
            borderwidth=0,
            relief=tk.FLAT,
            bg=ACCENT,
            fg="#ffffff",
            selectcolor=ACCENT,
            activebackground=ACCENT,
            activeforeground="#ffffff",
            font=(UI_FONT, 10, "bold"),
        )
        self.deep_toggle_button.pack(side=tk.LEFT, padx=(10, 0))
        self._screen_stop_button_pack_options = {
            "side": tk.LEFT, "padx": (8, 0), "before": self.deep_toggle_button
        }
        ttk.Label(run_row, text="给买 / 持 / 卖与理由，较慢", style="Hint.TLabel").pack(side=tk.LEFT, padx=(8, 0))
        self._sync_deep_toggle()

    def _build_results_region(self, outer: ttk.Frame) -> None:
        toolbar = ttk.Frame(outer)
        self.results_toolbar = toolbar
        # 标准结果区头部：标题/说明在左，动作簇在右；组合概览与运行状态独占第二行。
        self.status_bar = toolbar
        toolbar.pack(fill=tk.X, pady=(0, self._sc(14)))
        self.results_action_row = ttk.Frame(toolbar)
        self.results_action_row.pack(fill=tk.X, pady=(self._sc(2), self._sc(10)))
        self.results_context_row = tk.Frame(toolbar, bg=CONTROL_BG)
        self.results_context_row.pack(fill=tk.X)

        action_row = self.results_action_row
        self.results_heading_block = ttk.Frame(action_row)
        self.results_heading_block.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.results_section_label = ttk.Label(
            self.results_heading_block,
            text="研究结果",
            style="SectionTitle.TLabel",
        )
        self.results_section_label.pack(anchor=tk.W)
        self.results_section_hint = ttk.Label(
            self.results_heading_block,
            text="先浏览股票列表，再查看当前标的的摘要、图表与完整解释。",
            style="Hint.TLabel",
        )
        self.results_section_hint.pack(anchor=tk.W, pady=(self._sc(3), 0))

        self.results_actions_cluster = ttk.Frame(action_row)
        self.results_actions_cluster.pack(side=tk.RIGHT, anchor=tk.E, padx=(self._sc(18), 0))
        self.add_to_watchlist_button = ttk.Button(
            self.results_actions_cluster,
            text="加入自选",
            style="Action.TButton",
            command=self.add_to_watchlist,
        )
        self.copy_tools_button = ttk.Menubutton(
            self.results_actions_cluster,
            text="复制",
            style="Action.TMenubutton",
            width=MENU_BUTTON_SHORT_WIDTH,
        )
        self.copy_tools_menu = self._menu(self.copy_tools_button)
        for label, command in (
            ("复制结果", self.copy_results),
            ("复制解释", self.copy_current_detail),
        ):
            self.copy_tools_menu.add_command(label=label, command=command)
        self.copy_tools_button.configure(menu=self.copy_tools_menu)
        self.secondary_tools_button = ttk.Menubutton(
            self.results_actions_cluster,
            text="更多",
            style="Action.TMenubutton",
            width=MENU_BUTTON_SHORT_WIDTH,
        )
        self.secondary_tools_button.pack(side=tk.LEFT)
        self.secondary_tools_menu = self._menu(self.secondary_tools_button)
        for label, command in (
            ("导出 CSV", self.export_csv),
            ("自选股", self.open_watchlist_manager),
            ("横向对比", self.open_comparison),
            ("预警", self.open_alert_manager),
            ("资金流", self.show_fund_flow),
        ):
            self.secondary_tools_menu.add_command(label=label, command=command)
        self.secondary_tools_button.configure(menu=self.secondary_tools_menu)
        self._add_to_watchlist_pack_options = {"side": tk.LEFT, "before": self.secondary_tools_button}
        self._copy_tools_pack_options = {"side": tk.LEFT, "padx": (6, 0), "before": self.secondary_tools_button}
        self.status_var = tk.StringVar(value="就绪")
        self.summary_var = tk.StringVar(value="暂无结果")
        self.results_status_label = tk.Label(
            self.results_context_row,
            textvariable=self.status_var,
            bg=CONTROL_BG,
            fg=MUTED_INK,
            font=(UI_FONT, 10),
        )
        self.results_status_label.pack(side=tk.RIGHT, padx=(self._sc(12), self._sc(16)))
        self.summary_label = tk.Label(
            self.results_context_row,
            textvariable=self.summary_var,
            bg=CONTROL_BG,
            fg=INK_SOFT,
            font=(UI_FONT, 10, "bold"),
        )
        self.summary_label.pack(side=tk.RIGHT, padx=(self._sc(12), 0))

        # 组合概览独占第二行的弹性空间；运行时进度条从右侧出现，不再挤压第一行操作。
        self.overview_var = tk.StringVar(value=build_portfolio_overview([], 0))
        self._overview_label = ttk.Label(
            self.results_context_row, textvariable=self.overview_var, style="Overview.TLabel"
        )
        self._overview_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.progress = ttk.Progressbar(
            self.results_context_row, mode="determinate", maximum=1, value=0, length=self._sc(180)
        )
        self._progress_pack_options = {"side": tk.RIGHT, "padx": (self._sc(12), 0)}

        # 预警横幅：平时隐藏，命中时显示规则摘要（红底）。
        self.alert_banner = tk.Label(outer, text="", bg=DANGER_BG, fg=DANGER_COLOR, anchor=tk.W,
                                     font=(UI_FONT, 10, "bold"), padx=self._sc(12), pady=self._sc(8))

        self.table_card = tk.Frame(outer, bg=CARD_BORDER, padx=1, pady=1)
        self._table_card_pack_options = {"fill": tk.X, "pady": (0, self._sc(14))}
        self.table_header_bar = tk.Frame(self.table_card, bg=CARD_BG)
        self.table_header_bar.pack(side=tk.TOP, fill=tk.X)
        table_title_block = tk.Frame(self.table_header_bar, bg=CARD_BG)
        table_title_block.pack(side=tk.LEFT, padx=self._sc(16), pady=self._sc(12))
        self.stock_list_title_label = tk.Label(
            table_title_block,
            text="股票列表",
            bg=CARD_BG,
            fg=INK,
            font=(UI_FONT, 11, "bold"),
        )
        self.stock_list_title_label.pack(anchor=tk.W)
        tk.Label(
            table_title_block,
            text="点击任一行，展开该股票的完整判断与依据。",
            bg=CARD_BG,
            fg=MUTED_INK,
            font=(UI_FONT, 9),
        ).pack(anchor=tk.W, pady=(self._sc(2), 0))
        self.table_header_divider = tk.Frame(self.table_card, height=1, bg=BORDER_SOFT)
        self.table_header_divider.pack(side=tk.TOP, fill=tk.X)
        self.tree = ttk.Treeview(self.table_card, columns=TABLE_COLUMNS, show="headings", height=TABLE_EMPTY_VISIBLE_ROWS)
        self.table_scroll = ttk.Scrollbar(self.table_card, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=self._on_table_scroll)
        headings = {
            "code": ("代码", 110),
            "name": ("名称", 150),
            "action": ("建议", 130),
            "score": ("综合分", 90),
            "confidence": ("把握", 90),
            "last": ("最新价", 100),
            "change": ("涨跌幅", 100),
            "risk": ("风险", 90),
        }
        anchors = {
            "code": tk.W,
            "name": tk.W,
            "action": tk.CENTER,
            "score": tk.E,
            "confidence": tk.E,
            "last": tk.E,
            "change": tk.E,
            "risk": tk.CENTER,
        }
        for column, (title, width) in headings.items():
            self.tree.heading(column, text=title, command=lambda key=column: self._sort_by_column(key))
            self.tree.column(column, width=self._sc(width), anchor=anchors[column])
        self._configure_tree_tags()
        self.table_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._show_selected_detail)
        # 滚轮悬停表格时滚动表格本身，而不是整页
        self.tree.bind("<MouseWheel>", self._on_tree_mousewheel)

        # 结论卡（verdict card）：四指标一行 + 其下五档光谱条合并为一张卡——统一描边、统一
        # 内层背景，取代此前并排的两张卡（原 visual_summary_frame | spectrum_frame）。
        # insight_strip 本身即是这张卡的外壳，沿用旧属性名以兼容 _set_results_expanded 等
        # 既有折叠/展开与锚点逻辑。
        self.insight_strip = tk.Frame(outer, bg=CARD_BORDER, padx=1, pady=1)
        self.insight_strip.pack(fill=tk.X, pady=(0, self._sc(14)))
        self.verdict_body = tk.Frame(self.insight_strip, bg=CARD_BG)
        self.verdict_body.pack(fill=tk.BOTH, expand=True)

        self.verdict_header = tk.Frame(self.verdict_body, bg=CARD_BG)
        self.verdict_header.pack(fill=tk.X, padx=self._sc(16), pady=(self._sc(13), self._sc(10)))
        self.verdict_title_label = tk.Label(
            self.verdict_header,
            text="当前股票摘要",
            bg=CARD_BG,
            fg=INK,
            font=(UI_FONT, 11, "bold"),
        )
        self.verdict_title_label.pack(side=tk.LEFT)
        tk.Label(
            self.verdict_header,
            text="方向、建议仓位、把握程度与近期波动",
            bg=CARD_BG,
            fg=MUTED_INK,
            font=(UI_FONT, 9),
        ).pack(side=tk.RIGHT)
        self.verdict_header_divider = tk.Frame(self.verdict_body, height=1, bg=BORDER_SOFT)
        self.verdict_header_divider.pack(fill=tk.X)

        summary_inner = tk.Frame(self.verdict_body, bg=CARD_BG)
        summary_inner.pack(fill=tk.X)
        self.visual_summary_metrics: list[dict[str, Any]] = []
        for index, (title_text, key) in enumerate(
            (("方向", "action"), ("仓位", "position"), ("把握", "confidence"), ("波动", "move"))
        ):
            if index:
                tk.Frame(summary_inner, width=1, bg=BORDER_SOFT).pack(side=tk.LEFT, fill=tk.Y)
            cell = tk.Frame(summary_inner, bg=CARD_BG, padx=self._sc(18), pady=self._sc(12))
            cell.pack(side=tk.LEFT, fill=tk.X, expand=True)
            title = tk.Label(
                cell,
                text=title_text,
                bg=CARD_BG,
                fg=MUTED_INK,
                font=(UI_FONT, 9),
            )
            title.pack(anchor=tk.W)
            value = tk.Label(
                cell,
                textvariable=self.visual_metric_vars[key],
                width=12,
                anchor=tk.W,
                bg=CARD_BG,
                fg=INK,
                font=(UI_FONT, 12, "bold"),
            )
            value.pack(anchor=tk.W)
            self.visual_summary_metrics.append(
                {"frame": cell, "title": title, "value": value, "value_var": self.visual_metric_vars[key]}
            )
        self.visual_summary_label = self.visual_summary_metrics[0]["value"]

        # 决策强度光谱尺：五档结论一眼可见（红买/灰观望/绿卖），高亮当前档；与四指标同处一张
        # 结论卡内，一条细分隔线隔开（复用 detail_panel_divider 那种同卡分节手法）。
        self.verdict_divider = tk.Frame(self.verdict_body, height=1, bg=BORDER_SOFT)
        self.verdict_divider.pack(fill=tk.X)
        self.spectrum_canvas = tk.Canvas(
            self.verdict_body,
            height=self._sc(68),
            bg=CARD_BG,
            highlightthickness=0,
        )
        self.spectrum_canvas.pack(fill=tk.BOTH, expand=True)

        self.visual_workspace_shell = tk.Frame(outer, bg=CARD_BORDER, padx=1, pady=1)
        self.visual_workspace_shell.pack(fill=tk.X, pady=(0, self._sc(14)))
        self.visual_workspace = tk.Frame(self.visual_workspace_shell, bg=CARD_BG)
        self.visual_workspace.pack(fill=tk.BOTH, expand=True)

        self.visual_workspace_header = tk.Frame(self.visual_workspace, bg=CARD_BG)
        self.visual_workspace_header.pack(side=tk.TOP, fill=tk.X, padx=self._sc(16), pady=self._sc(12))
        self.visual_workspace_title_label = tk.Label(
            self.visual_workspace_header,
            text="判断依据与价格走势",
            bg=CARD_BG,
            fg=INK,
            font=(UI_FONT, 11, "bold"),
        )
        self.visual_workspace_title_label.pack(side=tk.LEFT)
        tk.Label(
            self.visual_workspace_header,
            text="左侧为因子拆解，右侧为近 90 日 K 线与成交量",
            bg=CARD_BG,
            fg=MUTED_INK,
            font=(UI_FONT, 9),
        ).pack(side=tk.RIGHT)
        self.visual_workspace_header_divider = tk.Frame(
            self.visual_workspace,
            height=1,
            bg=BORDER_SOFT,
        )
        self.visual_workspace_header_divider.pack(side=tk.TOP, fill=tk.X)

        # 因子拆解 | K 线固定保持 36:64 的信息权重；宽度由 compute_workspace_columns 在
        # 内容带每次重排时重算，窄屏和高 DPI 下也不会退回等宽。
        self.visual_panel_frame = tk.Frame(
            self.visual_workspace,
            width=self._sc(340),
            height=self._sc(360),
            bg=CARD_BG,
        )
        self.visual_panel_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        self.visual_panel_frame.pack_propagate(False)
        self.visual = tk.Canvas(
            self.visual_panel_frame,
            width=self._sc(340),
            height=self._sc(360),
            bg=CARD_BG,
            highlightthickness=0,
        )
        self.visual.pack(fill=tk.BOTH, expand=True)

        self.visual_workspace_divider = tk.Frame(self.visual_workspace, width=1, bg=BORDER_SOFT)
        self.visual_workspace_divider.pack(side=tk.LEFT, fill=tk.Y)

        # 专业 K 线（纯 Canvas）：蜡烛 + MA5/10/20 + 成交量副图。价格走势的唯一承担者，
        # 两栏不等宽分配见上方注释。
        self.kline_panel_frame = tk.Frame(self.visual_workspace, bg=CARD_BG)
        self.kline_panel_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.kline_canvas = tk.Canvas(
            self.kline_panel_frame,
            width=self._sc(620),
            height=self._sc(360),
            bg=CARD_BG,
            highlightthickness=0,
        )
        self.kline_canvas.pack(fill=tk.BOTH, expand=True)
        self._kline_state: dict = {"layout": []}
        self.kline_canvas.bind("<Motion>", self._on_kline_motion)
        self.kline_canvas.bind("<Leave>", self._on_kline_leave)

        self.detail_panel_shell = tk.Frame(outer, bg=CARD_BORDER, padx=1, pady=1)
        self.detail_panel_shell.pack(fill=tk.BOTH, expand=True)
        self.detail_panel_body = tk.Frame(self.detail_panel_shell, bg=CARD_BG)
        self.detail_panel_body.pack(fill=tk.BOTH, expand=True)

        self.detail_header = tk.Frame(self.detail_panel_body, bg=CARD_BG)
        self.detail_header.pack(fill=tk.X, padx=self._sc(16), pady=(self._sc(13), self._sc(10)))
        self.detail_title_label = tk.Label(
            self.detail_header,
            text="详细解释与操作计划",
            bg=CARD_BG,
            fg=INK,
            font=(UI_FONT, 11, "bold"),
        )
        self.detail_title_label.pack(side=tk.LEFT)
        tk.Label(
            self.detail_header,
            text="切换章节快速定位；调整本金可即时重算仓位",
            bg=CARD_BG,
            fg=MUTED_INK,
            font=(UI_FONT, 9),
        ).pack(side=tk.RIGHT)
        self.detail_header_divider = tk.Frame(self.detail_panel_body, height=1, bg=BORDER_SOFT)
        self.detail_header_divider.pack(fill=tk.X)

        self.detail_control_bar = tk.Frame(self.detail_panel_body, bg=CARD_BG)
        self.detail_control_bar.pack(fill=tk.X, padx=self._sc(16), pady=self._sc(12))

        self.capital_tools_frame = tk.Frame(self.detail_control_bar, bg=CARD_BG)
        self.capital_tools_frame.pack(side=tk.LEFT)
        ttk.Label(self.capital_tools_frame, text="本金", style="SurfaceHint.TLabel").pack(side=tk.LEFT)
        self.capital_entry = ttk.Entry(self.capital_tools_frame, textvariable=self.capital_var, width=14)
        self.capital_entry.pack(side=tk.LEFT, padx=(self._sc(8), self._sc(8)))
        self.capital_entry.bind("<KeyRelease>", lambda _e: self._refresh_capital())
        self.capital_hint_label = ttk.Label(self.capital_tools_frame, text="即时重算", style="SurfaceHint.TLabel")
        self.capital_hint_label.pack(side=tk.LEFT)

        self.detail_nav_frame = tk.Frame(self.detail_control_bar, bg=CARD_BG)
        self.detail_nav_frame.pack(side=tk.RIGHT)
        ttk.Label(self.detail_nav_frame, text="详情", style="SurfaceHint.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self.detail_nav_var = tk.StringVar(value=DETAIL_NAV_SECTIONS[0][0])
        self.detail_nav_buttons: list[tk.Radiobutton] = []
        for label, target in DETAIL_NAV_SECTIONS:
            button = tk.Radiobutton(
                self.detail_nav_frame,
                text=label,
                variable=self.detail_nav_var,
                value=label,
                indicatoron=False,
                command=lambda key=label, heading=target: self._jump_detail_section(key, heading),
                width=7,
                padx=10,
                pady=7,
                bd=0,
                relief=tk.FLAT,
                bg=CONTROL_BG,
                fg=MUTED_INK,
                selectcolor=CONTROL_BG,
                activebackground=ACCENT_SOFT,
                activeforeground=ACCENT,
                font=(UI_FONT, 10, "bold"),
            )
            button.pack(side=tk.LEFT, padx=(0, 4))
            self.detail_nav_buttons.append(button)
        self._sync_detail_nav_buttons()

        self.detail_panel_divider = tk.Frame(self.detail_panel_body, height=1, bg=BORDER_SOFT)
        self.detail_panel_divider.pack(fill=tk.X)
        self.detail_holder, self.detail, self.detail_scroll = self._scrolled_text(
            self.detail_panel_body,
            wrap=tk.WORD,
            font=(UI_FONT, 11),
            relief=tk.FLAT,
            borderwidth=0,
            height=14,
            background=CARD_BG,
            padx=self._sc(16),
            pady=self._sc(14),
        )
        self.detail_holder.pack(fill=tk.BOTH, expand=True)
        self._configure_detail_tags()
        self._set_detail("分析结果会显示在这里。\n\n" + DISCLAIMER)

        self._results_disclaimer_label = ttk.Label(outer, text=DISCLAIMER, style="Hint.TLabel")
        self._results_disclaimer_label.pack(anchor=tk.W, pady=(self._sc(16), 0))

        # 未有结果前，结论卡/价格卡/详情卡折叠为紧凑三步引导，取代原先固定绘制的 ~600px 假占位
        # （且假占位在画布未实体化时按 520px 回退宽绘制，导致标签挤在左三分之一）。三张卡的
        # 展开/折叠统一收敛到 _set_results_expanded；pack 时都带 before=disclaimer，使折叠
        # 后再展开仍插回 disclaimer 之前，保持与构建时一致的纵向顺序。
        self.results_placeholder = tk.Frame(outer, bg=CARD_BORDER, padx=1, pady=1)
        self.empty_state_body = tk.Frame(
            self.results_placeholder,
            bg=CARD_BG,
            padx=self._sc(24),
            pady=self._sc(22),
        )
        self.empty_state_body.pack(fill=tk.X)
        self.empty_state_title = tk.Label(
            self.empty_state_body,
            text="从一组代码开始",
            bg=CARD_BG,
            fg=INK,
            font=(UI_FONT, 14, "bold"),
        )
        self.empty_state_title.pack()
        tk.Label(
            self.empty_state_body,
            text="运行后，这里会按顺序展开结论、图表与可解释依据。",
            bg=CARD_BG,
            fg=MUTED_INK,
            font=(UI_FONT, 10),
        ).pack(pady=(self._sc(5), self._sc(14)))
        empty_steps_row = tk.Frame(self.empty_state_body, bg=CARD_BG)
        empty_steps_row.pack()
        self.empty_state_steps: list[tk.Label] = []
        for index, text in enumerate(("01  输入标的", "02  调整强度", "03  阅读结论与依据")):
            if index:
                tk.Label(empty_steps_row, text="→", bg=CARD_BG, fg=MUTED_LIGHT,
                         font=(UI_FONT, 10)).pack(side=tk.LEFT, padx=self._sc(12))
            label = tk.Label(
                empty_steps_row,
                text=text,
                bg=ACCENT_SOFT,
                fg=ACCENT,
                font=(UI_FONT, 10, "bold"),
                padx=self._sc(14),
                pady=self._sc(8),
            )
            label.pack(side=tk.LEFT)
            self.empty_state_steps.append(label)
        self._insight_strip_pack_options = {
            "fill": tk.X, "pady": (0, self._sc(14)), "before": self._results_disclaimer_label,
        }
        self._visual_workspace_shell_pack_options = {
            "fill": tk.X, "pady": (0, self._sc(14)), "before": self._results_disclaimer_label,
        }
        self._detail_panel_shell_pack_options = {
            "fill": tk.BOTH, "expand": True, "before": self._results_disclaimer_label,
        }
        self._results_placeholder_pack_options = {
            "fill": tk.X, "pady": (0, self._sc(14)), "before": self._results_disclaimer_label,
        }
        # 到这里三张卡已按上面的初始 .pack(...) 调用真正展开；先如实置位，再交给
        # _set_results_expanded(False) 折叠，使其“旧值→新值”判断和实际起始状态一致。
        self._results_expanded = True
        self._set_results_expanded(False)

    def _set_results_expanded(self, expanded: bool) -> None:
        """折叠/展开结论卡(insight_strip)·价格卡(visual_workspace_shell)·详情卡(detail_panel_shell)：
        未有结果时只显示一行 results_placeholder 提示；首个结果到达后展开三卡并（由调用方）绘制内容。"""
        if expanded == self._results_expanded:
            return
        self._results_expanded = expanded
        if expanded:
            self.results_placeholder.pack_forget()
            self.insight_strip.pack(**self._insight_strip_pack_options)
            self.visual_workspace_shell.pack(**self._visual_workspace_shell_pack_options)
            self.detail_panel_shell.pack(**self._detail_panel_shell_pack_options)
            # 先清空三张画布：折叠期间它们可能还留着上一轮分析的旧图形（折叠只隐藏面板，
            # 不清画布）；紧接着的 update_idletasks() 会让刚映射的面板真正过一遍绘制，若不
            # 先清空，可能把这份陈旧内容闪一下画到屏幕上，才轮到调用方随后画出的新内容。
            self.visual.delete("all")
            self.kline_canvas.delete("all")
            self.spectrum_canvas.delete("all")
            # 三卡此前可能从未映射过（winfo_width() 仍是初始的 1px）；绘制前强制走一遍布局，
            # 否则 _draw_visual/_draw_kline/_draw_spectrum_strip 会读到陈旧宽度，退回硬编码的
            # 520/640px 兜底值——正是 P2 遗留、本任务要修的"标签挤左"根因。
            self.root.update_idletasks()
        else:
            self.detail_panel_shell.pack_forget()
            self.visual_workspace_shell.pack_forget()
            self.insight_strip.pack_forget()
            self.results_placeholder.pack(**self._results_placeholder_pack_options)

    def _bind_page_scroll(self, content: ttk.Frame) -> None:
        content.bind("<Configure>", self._on_page_configure)
        self.page_canvas.bind("<Configure>", self._on_canvas_configure)
        self.root.bind_all("<MouseWheel>", self._on_page_mousewheel)

    def _bind_shortcuts(self) -> None:
        # 主操作快捷键跟随当前选项卡：个股页触发“开始分析”，全市场页触发“开始选股”。
        self.root.bind("<Control-Return>", lambda _event: self._run_active_tab())
        self.root.bind("<F5>", lambda _event: self._run_active_tab())
        self.root.bind("<Control-l>", lambda _event: self.clear())
        self.root.bind("<Control-L>", lambda _event: self.clear())
        self.root.bind("<Control-Shift-C>", lambda _event: self.copy_current_detail())

    def _active_tab_index(self) -> int:
        return getattr(self, "_active_tab", 0)

    def _run_active_tab(self) -> None:
        """按当前选项卡运行主操作：个股分析或全市场选股。"""
        if active_mode_action(self._active_tab_index()) == "screen":
            self.start_screen()
        else:
            self.analyze()

    def _center_window(self, window: tk.Tk | tk.Toplevel) -> None:
        # 主窗口：在「屏幕工作区」（已排除任务栏）内按【外框】居中，四周（含底部任务栏一侧）
        # 留出 WINDOW_WORKAREA_MARGIN 的均匀空隙。两遍：先放一版让窗口实体化以量出标题栏/边框
        # 厚度，再带着外框厚度精确居中（窗口映射后还会在 _finalize_geometry 再校准一次）。
        self._apply_centered_geometry(window)
        window.update_idletasks()
        self._apply_centered_geometry(window)

    def _apply_centered_geometry(self, window: tk.Tk | tk.Toplevel) -> None:
        left, top, work_w, work_h = self._screen_work_area(window)
        frame_w, frame_h = self._frame_extents(window)
        factor = ui_scale(self._tk_scaling(window))
        win_w, win_h, x, y = compute_main_geometry(
            left, top, work_w, work_h, factor,
            MAIN_MIN_SIZE[0], MAIN_MIN_SIZE[1], WINDOW_MAX_SIZE[0], WINDOW_MAX_SIZE[1],
            WINDOW_WORKAREA_MARGIN, frame_w, frame_h,
        )
        window.geometry(f"{win_w}x{win_h}+{x}+{y}")

    def _apply_root_minimum(self) -> None:
        _left, _top, work_width, work_height = self._screen_work_area(self.root)
        frame_width, frame_height = self._frame_extents(self.root)
        self.root.minsize(*compute_scaled_minimum(
            work_width,
            work_height,
            self._ui_scale,
            MAIN_MIN_SIZE[0],
            MAIN_MIN_SIZE[1],
            margin=WINDOW_WORKAREA_MARGIN,
            frame_width=frame_width,
            frame_height=frame_height,
        ))

    def _tk_scaling(self, window: tk.Misc) -> float:
        try:
            return float(window.tk.call("tk", "scaling"))
        except (tk.TclError, ValueError, TypeError):
            return 96 / 72

    def _sc(self, px: float) -> int:
        """把设计稿像素值按 self._ui_scale 换算为当前 DPI 下的实际像素——所有固定画布高/
        行高/装饰尺寸都经此换算，使其随字体一起放大，避免大屏下内容显得局促。"""
        return int(round(px * self._ui_scale))

    def _frame_extents(self, window: tk.Misc) -> tuple[int, int]:
        """量出窗口外框（标题栏 + 边框）比客户区多出的宽/高；窗口未实体化时返回 (0, 0)。"""
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = ctypes.windll.user32.GetAncestor(window.winfo_id(), 2)  # GA_ROOT
            rect = wintypes.RECT()
            if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                outer_w = rect.right - rect.left
                outer_h = rect.bottom - rect.top
                client_w, client_h = window.winfo_width(), window.winfo_height()
                if client_w > 1 and client_h > 1 and outer_w >= client_w and outer_h >= client_h:
                    return outer_w - client_w, outer_h - client_h
        except Exception:
            pass
        return 0, 0

    def _child_frame_extents(self, window: tk.Toplevel) -> tuple[int, int]:
        """子窗尚未实体化而量不到外框时，按主窗同类外框保守回退。"""
        frame_width, frame_height = self._frame_extents(window)
        if frame_width > 0 and frame_height > 0:
            return frame_width, frame_height
        root_width, root_height = self._frame_extents(self.root)
        return (
            frame_width if frame_width > 0 else root_width,
            frame_height if frame_height > 0 else root_height,
        )

    def _finalize_geometry(self) -> None:
        # 窗口映射后再按真实外框居中一次（此时能量准标题栏/边框），并把内容带按真实宽度居中。
        self._apply_root_minimum()
        self._apply_centered_geometry(self.root)
        self._relayout_content()

    def _screen_work_area(self, window: tk.Misc) -> tuple[int, int, int, int]:
        """返回屏幕工作区 (left, top, width, height)，已排除任务栏；失败回退到整屏。均为物理像素。"""
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        try:
            import ctypes
            from ctypes import wintypes

            primary_w = ctypes.windll.user32.GetSystemMetrics(0)  # SM_CXSCREEN
            primary_h = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN
            screen_w, screen_h = choose_centering_screen_size(screen_w, screen_h, primary_w, primary_h)

            rect = wintypes.RECT()
            # SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if width > 0 and height > 0:
                    return normalize_work_area_to_screen(rect.left, rect.top, width, height, screen_w, screen_h)
        except Exception:
            pass
        return 0, 0, screen_w, screen_h

    def _center_child_window(self, window: tk.Toplevel, size: tuple[int, int]) -> None:
        self.root.update_idletasks()

        def place(frame_width: int, frame_height: int) -> None:
            work_left, work_top, work_width, work_height = self._screen_work_area(window)
            width, height, x, y = compute_child_window_geometry(
                parent_left=self.root.winfo_x(),
                parent_top=self.root.winfo_y(),
                parent_width=self.root.winfo_width(),
                parent_height=self.root.winfo_height(),
                work_left=work_left,
                work_top=work_top,
                work_width=work_width,
                work_height=work_height,
                requested_width=size[0],
                requested_height=size[1],
                margin=self._sc(CHILD_WINDOW_WORKAREA_MARGIN),
                frame_width=frame_width,
                frame_height=frame_height,
            )
            window.geometry(f"{width}x{height}+{x}+{y}")

        # 先以主窗外框厚度给出稳定首帧，再在子窗实体化后用它自己的真实外框校准一次。
        frame_width, frame_height = self._frame_extents(self.root)
        place(frame_width, frame_height)
        window.update_idletasks()
        frame_width, frame_height = self._child_frame_extents(window)
        place(frame_width, frame_height)

    def _apply_child_minimum(self, window: tk.Toplevel, logical_size: tuple[int, int]) -> None:
        """DPI 放大子窗最小尺寸，但绝不让其外框越过当前屏幕工作区。"""
        _left, _top, work_width, work_height = self._screen_work_area(window)
        frame_width, frame_height = self._child_frame_extents(window)
        window.minsize(*compute_scaled_minimum(
            work_width,
            work_height,
            self._ui_scale,
            logical_size[0],
            logical_size[1],
            margin=CHILD_WINDOW_WORKAREA_MARGIN,
            frame_width=frame_width,
            frame_height=frame_height,
        ))

    def _set_window_icon(self, window: tk.Tk | tk.Toplevel) -> None:
        icon = app_asset_path(APP_ICON_FILENAME)
        if not icon.exists():
            return
        try:
            window.iconbitmap(str(icon))
        except tk.TclError:
            pass

    def _draw_logo(self, canvas: tk.Canvas) -> None:
        canvas.delete("all")
        width = max(1, int(canvas.cget("width")))
        height = max(1, int(canvas.cget("height")))
        scale = min(width, height) / 54
        x_offset = (width - 54 * scale) / 2
        y_offset = (height - 54 * scale) / 2

        def box(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float, float, float]:
            return (
                x_offset + x1 * scale,
                y_offset + y1 * scale,
                x_offset + x2 * scale,
                y_offset + y2 * scale,
            )

        def points(*coords: float) -> list[float]:
            return [
                (x_offset + value * scale) if index % 2 == 0 else (y_offset + value * scale)
                for index, value in enumerate(coords)
            ]

        stroke = max(1, round(3 * scale))
        canvas.create_oval(*box(4, 4, 50, 50), fill="#0f2f57", outline="")
        canvas.create_oval(*box(11, 11, 43, 43), fill="#163f73", outline="")
        canvas.create_polygon(*points(27, 13, 39, 40, 33, 40, 30, 32, 21, 32, 18, 40, 12, 40, 24, 13), fill="#ffffff", outline="")
        canvas.create_line(*points(20, 29, 31, 29), fill="#0f2f57", width=stroke)
        canvas.create_line(*points(13, 39, 22, 31, 31, 34, 41, 20), fill=POS_COLOR,
                           width=stroke, smooth=True)
        canvas.create_oval(*box(39, 18, 44, 23), fill=POS_COLOR, outline="")

    def _configure_tree_tags(self) -> None:
        self.tree.tag_configure("risk_low")
        self.tree.tag_configure("risk_medium")
        self.tree.tag_configure("risk_high")
        self.tree.tag_configure("action_buy", background=POS_BG, foreground=POS_COLOR)
        self.tree.tag_configure("action_hold", background=HOLD_BG, foreground=FLAT_COLOR)
        self.tree.tag_configure("action_sell", background=NEG_BG, foreground=NEG_COLOR)

    def _on_page_configure(self, _event: object | None = None) -> None:
        self.page_canvas.configure(scrollregion=self.page_canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._apply_content_band(event.width)

    def _relayout_content(self) -> None:
        self.root.update_idletasks()
        width = self.page_canvas.winfo_width()
        if width > 1:
            self._apply_content_band(width)

    def _apply_content_band(self, width: int) -> None:
        # 内容填满窗口并水平居中（四边留白均匀）；仅在超宽屏才收窄到上限，避免组件被拉得过长。
        # 上限与边距随 DPI 放大，使内容带在高 DPI 下按比例加宽、留白均匀。
        x_offset, content_width = compute_content_band(width, self._sc(MAX_CONTENT_WIDTH), self._sc(CONTENT_MARGIN))
        self.page_canvas.itemconfigure(self.page_window, width=content_width)
        self.page_canvas.coords(self.page_window, x_offset, 0)
        if hasattr(self, "visual_panel_frame"):
            workspace_width = max(3, content_width - 2)
            visual_width, chart_width = compute_workspace_columns(workspace_width, gap=1)
            self.visual_panel_frame.configure(width=visual_width)
            self.kline_panel_frame.configure(width=chart_width)

    def _on_page_mousewheel(self, event: tk.Event) -> None:
        if self.root.focus_get() is self.detail:
            return
        self.page_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_table_scroll(self, first: str, last: str) -> None:
        # 行数不超过可视区时自动隐藏滚动条，溢出时再显示
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.table_scroll.pack_forget()
        elif not self.table_scroll.winfo_ismapped():
            self.table_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.table_scroll.set(first, last)

    def _on_tree_mousewheel(self, event: tk.Event) -> str:
        self.tree.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def analyze(self) -> None:
        if self.busy:
            return
        try:
            symbols = parse_user_symbols(self.symbol_input.get("1.0", tk.END), max_count=MAX_SYMBOLS)
        except ValueError as exc:
            messagebox.showerror("输入错误", str(exc))
            return

        self._replace_input(", ".join(symbol.display for symbol in symbols))
        self.cancel_event.clear()
        self._discard_running_results = False
        self._reset_results()
        self.queue = queue.Queue()
        self._set_detail("正在分析，请稍候...")
        self._set_running(True)
        self.progress.configure(maximum=len(symbols), value=0)
        self.status_var.set(f"正在分析 {len(symbols)} 只股票...")
        self.summary_var.set("分析中")
        self.overview_var.set("组合概览：正在整理行情和判断结果...")

        level = self.level_var.get()
        worker = threading.Thread(target=self._worker, args=(symbols, level), daemon=True)
        worker.start()
        self.root.after(120, self._poll_queue)

    def stop(self) -> None:
        if not self.busy:
            return
        self.cancel_event.set()
        self.status_var.set("正在停止，已发出的请求会完成后退出...")
        self.stop_button.configure(state=tk.DISABLED)
        self.screen_stop_button.configure(state=tk.DISABLED)

    def _set_running(self, running: bool) -> None:
        self.busy = running
        self._set_progress_visible(running)
        self._set_stop_controls_visible(running)
        if not running:
            self.progress.configure(value=0)
        run_state = tk.DISABLED if running else tk.NORMAL
        stop_state = tk.NORMAL if running else tk.DISABLED
        self.analyze_button.configure(state=run_state)
        self.screen_button.configure(state=run_state)
        self.input_tools_button.configure(state=run_state)
        self.stop_button.configure(state=stop_state)
        self.screen_stop_button.configure(state=stop_state)

    def _set_progress_visible(self, visible: bool) -> None:
        is_visible = bool(self.progress.winfo_manager())
        if visible and not is_visible:
            self.progress.pack(**self._progress_pack_options)
        elif not visible and is_visible:
            self.progress.pack_forget()

    def _set_stop_controls_visible(self, visible: bool) -> None:
        controls = (
            (self.stop_button, self._stop_button_pack_options),
            (self.screen_stop_button, self._screen_stop_button_pack_options),
        )
        for button, pack_options in controls:
            is_visible = bool(button.winfo_manager())
            if visible and not is_visible:
                button.pack(**pack_options)
            elif not visible and is_visible:
                button.pack_forget()

    def _set_result_action_tools_visible(self, has_deep_results: bool, has_visible_rows: bool) -> None:
        controls = (
            (self.add_to_watchlist_button, self._add_to_watchlist_pack_options, has_deep_results),
            (self.copy_tools_button, self._copy_tools_pack_options, has_visible_rows),
        )
        for button, pack_options, visible in controls:
            is_visible = bool(button.winfo_manager())
            if visible and not is_visible:
                button.pack(**pack_options)
            elif not visible and is_visible:
                button.pack_forget()
        more_padx = (6, 0) if has_deep_results or has_visible_rows else 0
        self.secondary_tools_button.pack_configure(padx=more_padx)

    def _sync_result_action_tools(self) -> None:
        self._set_result_action_tools_visible(bool(self.results), bool(self.tree.get_children()))

    def _reset_results(self) -> None:
        self.results.clear()
        self.rec_meta.clear()
        self.measurements.clear()
        self.histories.clear()
        self._current_history = []
        self._kline_state = {"layout": []}
        self.failures = 0
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._refresh_table_height(0)
        if hasattr(self, "visual_metric_vars"):
            self._set_summary_metrics("未选择", "—", "—", "—")
            self._set_summary_color(MUTED_INK)
        if hasattr(self, "results_placeholder"):
            # 无结果：折叠回一行提示，不再预绘空态图形（空态不再调用 _draw_empty_* 系列）。
            self._set_results_expanded(False)
        self._sync_result_action_tools()

    def _on_level_change(self, _value: object = None) -> None:
        """改档：对缓存的客观测量重新决策并刷新表格与当前选中详情（不重新联网）。"""
        level = self.level_var.get()
        self.level_label_var.set(level_summary(level))
        self._sync_level_buttons()
        saved = self._save_persisted()
        if not self.measurements:
            if not saved:
                self._report_config_save_failure("决策强度已更新", show_dialog=False)
            return
        for iid, m in self.measurements.items():
            if m is None:
                continue
            result = build_analysis_result(m, decide(m, level))
            self.results[iid] = result
            if self.tree.exists(iid):
                self.tree.item(iid, values=format_result_row(result), tags=result_row_tags(result))
        self.overview_var.set(build_portfolio_overview(list(self.results.values()), self.failures))
        self._show_selected_detail()
        if not saved:
            self._report_config_save_failure("决策强度已更新", show_dialog=False)

    def fill_sample(self) -> None:
        if self.busy:
            return
        self._replace_input(SAMPLE_INPUT)

    def clean_input(self) -> None:
        if self.busy:
            return
        try:
            cleaned = normalize_symbol_input_text(self.symbol_input.get("1.0", tk.END), max_count=MAX_SYMBOLS)
        except ValueError as exc:
            messagebox.showerror("输入错误", str(exc))
            return
        self._replace_input(cleaned)
        self.status_var.set("代码已整理并去重")

    def _sync_level_buttons(self) -> None:
        current = self.level_var.get()
        for index, button in enumerate(getattr(self, "level_buttons", []), start=1):
            if index == current:
                button.configure(
                    bg=COMMAND_SELECTED_BG,
                    fg=COMMAND_SELECTED_INK,
                    selectcolor=COMMAND_SELECTED_BG,
                    activebackground=COMMAND_SELECTED_BG,
                    activeforeground=COMMAND_SELECTED_INK,
                )
            else:
                button.configure(
                    bg=COMMAND_SURFACE,
                    fg=COMMAND_MUTED_INK,
                    selectcolor=COMMAND_SURFACE,
                    activebackground=COMMAND_BORDER,
                    activeforeground=COMMAND_INK,
                )

    def _sync_deep_toggle(self) -> None:
        button = getattr(self, "deep_toggle_button", None)
        if button is None:
            return
        if bool(self.deep_var.get()):
            button.configure(
                text="深度分析 开",
                bg=ACCENT,
                fg="#ffffff",
                activebackground=ACCENT,
                activeforeground="#ffffff",
                selectcolor=ACCENT,
            )
        else:
            button.configure(
                text="深度分析 关",
                bg=CONTROL_BG,
                fg=MUTED_INK,
                activebackground=ACCENT_SOFT,
                activeforeground=ACCENT,
                selectcolor=CONTROL_BG,
            )

    def clear(self) -> None:
        was_busy = self.busy
        self.cancel_event.set()
        if was_busy:
            self._discard_running_results = True
            self.stop_button.configure(state=tk.DISABLED)
            self.screen_stop_button.configure(state=tk.DISABLED)
        self._replace_input("")
        self._reset_results()
        self.progress.configure(value=0)
        self._set_progress_visible(False)
        self.status_var.set("正在停止并清空..." if was_busy else "就绪")
        self.summary_var.set("暂无结果")
        self.overview_var.set(build_portfolio_overview([], 0))
        self._set_summary_metrics("未选择", "—", "—", "—")
        self._set_summary_color(MUTED_INK)
        self._set_detail("分析结果会显示在这里。\n\n" + DISCLAIMER)

    def _replace_input(self, text: str) -> None:
        self.symbol_input.delete("1.0", tk.END)
        self.symbol_input.insert("1.0", text)
        self.symbol_input.edit_modified(False)
        self._schedule_symbol_scrollbar_refresh()

    def copy_results(self) -> None:
        rows = self._table_export_rows()
        if not rows:
            messagebox.showinfo("复制结果", "当前没有可复制的分析结果。")
            return
        results = list(self.results.values())
        if results and len(results) == len(rows) and not self.failures:
            text = format_results_for_clipboard(results)
        else:
            text = format_table_rows_for_clipboard(rows)
        self._copy_text_to_clipboard("复制结果", text, "结果已复制到剪贴板")

    def copy_current_detail(self) -> None:
        text = self.detail.get("1.0", tk.END).strip()
        if not text:
            messagebox.showinfo("复制解释", "当前没有可复制的解释内容。")
            return
        self._copy_text_to_clipboard("复制解释", text, "当前解释已复制到剪贴板")

    def _copy_text_to_clipboard(self, title: str, text: str, success_status: str) -> None:
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except tk.TclError as exc:
            self.status_var.set("复制失败")
            messagebox.showerror(title, f"剪贴板暂不可用：{exc}")
            return
        self.status_var.set(success_status)

    def export_csv(self) -> None:
        rows = self._table_export_rows()
        if not rows:
            messagebox.showinfo("导出 CSV", "当前没有可导出的分析结果。")
            return
        path = filedialog.asksaveasfilename(
            title="导出分析结果",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
        )
        if not path:
            return
        results = list(self.results.values())
        if results and len(results) == len(rows) and not self.failures:
            payload = format_results_as_csv(results)
        else:
            payload = format_table_rows_as_csv(rows)
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                handle.write(payload.lstrip("\ufeff"))
        except OSError as exc:
            self.status_var.set("导出失败")
            messagebox.showerror("导出 CSV", f"无法写入文件：{exc}")
            return
        self.status_var.set(f"已导出：{path}")

    def _table_export_rows(self) -> list[tuple[str, ...]]:
        rows: list[tuple[str, ...]] = []
        for iid in self.tree.get_children():
            values = self.tree.item(iid, "values")
            rows.append(tuple(str(value) for value in values))
        return rows

    def show_help(self) -> None:
        self._show_info_window(
            "使用说明 / 结果解释 / 数据说明",
            build_help_sections(),
            "按输入、结果、数据和异常处理拆开查看，减少阅读负担。",
        )

    def show_strategy(self) -> None:
        self._show_info_window(
            "策略说明 / 计算逻辑",
            build_strategy_sections(),
            "当前采用可解释的多因子评分，重点控制风险和过度自信。",
        )

    def _show_info_window(self, title: str, sections: list[tuple[str, str]], subtitle: str) -> None:
        window = tk.Toplevel(self.root)
        window.title(title)
        self._center_child_window(window, (self._sc(INFO_WINDOW_SIZE[0]), self._sc(INFO_WINDOW_SIZE[1])))
        self._apply_child_minimum(window, (720, 500))
        window.configure(bg=PAGE_BG)
        window.transient(self.root)
        self._set_window_icon(window)

        container = ttk.Frame(window, padding=(self._sc(18), self._sc(16), self._sc(18), self._sc(14)))
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container)
        header.pack(fill=tk.X, pady=(0, 12))
        logo = tk.Canvas(header, width=self._sc(40), height=self._sc(40), bg=PAGE_BG, highlightthickness=0)
        logo.pack(side=tk.LEFT, padx=(0, 10))
        self._draw_logo(logo)
        title_box = ttk.Frame(header)
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(title_box, text=title, font=(UI_FONT, 15, "bold"), foreground=INK).pack(anchor=tk.W)
        ttk.Label(title_box, text=subtitle, style="Subtitle.TLabel").pack(anchor=tk.W, pady=(3, 0))

        body = ttk.Frame(container)
        body.pack(fill=tk.BOTH, expand=True)
        # 章节导航栏此前固定 154px：250% DPI 下即使 wraplength 已放大，过窄的框仍会把
        # 章节名裁掉("几个重要数[据]"/"数据与快[捷]")——随 _ui_scale 放大后才与放大的
        # wraplength/字体成比例，章节名不再溢出被裁。
        nav_frame = tk.Frame(body, bg=PAGE_BG, width=self._sc(154))
        nav_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        nav_frame.pack_propagate(False)
        ttk.Label(nav_frame, text="章节", style="Hint.TLabel").pack(anchor=tk.W, pady=(0, 6))

        content = tk.Frame(body, bg=CARD_BORDER, padx=1, pady=1)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_holder, text, _bar = self._scrolled_text(
            content, wrap=tk.WORD, borderwidth=0, relief=tk.FLAT,
            font=(UI_FONT, 10), background=CARD_BG,
        )
        text_holder.pack(fill=tk.BOTH, expand=True)
        self._configure_info_text(text)

        nav_var = tk.IntVar(value=0)
        info_buttons: list[tk.Radiobutton] = []
        info_state = {"active": 0}

        def show_section(idx: int) -> None:
            nav_var.set(idx)
            info_state["active"] = idx
            for i, button in enumerate(info_buttons):
                button.configure(
                    bg=ACCENT if i == idx else CONTROL_BG,
                    fg="#ffffff" if i == idx else MUTED_INK,
                    activebackground=ACCENT if i == idx else ACCENT_SOFT,
                    activeforeground="#ffffff" if i == idx else ACCENT,
                    selectcolor=ACCENT if i == idx else CONTROL_BG,
                )
            section_title, body = sections[idx]
            text.configure(state=tk.NORMAL)
            text.delete("1.0", tk.END)
            self._insert_info_text(text, section_title, body)
            text.configure(state=tk.DISABLED)
            text.yview_moveto(0.0)

        def info_hover(idx: int, entering: bool) -> None:
            if idx != info_state["active"]:
                info_buttons[idx].configure(bg=ACCENT_SOFT if entering else CONTROL_BG)

        for index, (section_title, _body) in enumerate(sections):
            seg = tk.Radiobutton(
                nav_frame,
                text=section_title,
                variable=nav_var,
                value=index,
                indicatoron=False,
                command=lambda i=index: show_section(i),
                width=14,
                anchor=tk.W,
                justify=tk.LEFT,
                padx=10,
                pady=7,
                wraplength=self._sc(112),
                cursor="hand2",
                bd=0,
                relief=tk.FLAT,
                bg=CONTROL_BG,
                fg=MUTED_INK,
                selectcolor=CONTROL_BG,
                activebackground=ACCENT_SOFT,
                activeforeground=ACCENT,
                font=(UI_FONT, 9, "bold"),
            )
            seg.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))
            seg.bind("<Enter>", lambda _e, i=index: info_hover(i, True))
            seg.bind("<Leave>", lambda _e, i=index: info_hover(i, False))
            info_buttons.append(seg)
        show_section(0)
        window._info_nav_buttons = info_buttons
        window._info_nav_frame = nav_frame
        window._info_text = text

        footer = ttk.Frame(container)
        footer.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(footer, text=DISCLAIMER, style="Hint.TLabel").pack(side=tk.LEFT)
        ttk.Button(footer, text="关闭", style="Action.TButton", command=window.destroy).pack(side=tk.RIGHT)

    def _configure_info_text(self, text: tk.Text) -> None:
        text.configure(
            background=CARD_BG,
            foreground=INK,
            insertbackground=INK,
            padx=self._sc(18),
            pady=self._sc(16),
            spacing1=self._sc(3),
            spacing2=self._sc(1),
            spacing3=self._sc(8),
        )
        text.tag_configure("title", font=(UI_FONT, 14, "bold"), foreground=INK, spacing3=self._sc(12))
        text.tag_configure("body", foreground=INK_SOFT, lmargin1=0, lmargin2=0, spacing3=self._sc(7))
        text.tag_configure("bullet", foreground=INK_SOFT, lmargin1=self._sc(18), lmargin2=self._sc(30),
                           spacing3=self._sc(6))
        text.tag_configure("number", foreground=ACCENT, lmargin1=self._sc(18), lmargin2=self._sc(34),
                           spacing3=self._sc(6))
        text.tag_configure("risk", foreground=DANGER_COLOR, lmargin1=self._sc(18), lmargin2=self._sc(30),
                           spacing3=self._sc(6))
        text.tag_configure("positive", foreground=POS_COLOR, lmargin1=self._sc(18), lmargin2=self._sc(30),
                           spacing3=self._sc(6))

    def _insert_info_text(self, text: tk.Text, title: str, body: str) -> None:
        text.insert(tk.END, title + "\n\n", ("title",))
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                text.insert(tk.END, "\n")
                continue
            if stripped.startswith("- "):
                tag = "risk" if _looks_risky(stripped) else "positive" if _looks_positive(stripped) else "bullet"
            elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == ".":
                tag = "number"
            else:
                tag = "body"
            text.insert(tk.END, stripped + "\n", (tag,))

    def _worker(self, symbols: list, level: int = STANDARD_LEVEL) -> None:
        try:
            for symbol in symbols:
                if self.cancel_event.is_set():
                    break
                try:
                    outcome = analyze_symbol(symbol, self.provider, level)
                except Exception as exc:  # noqa: BLE001 - UI 线程必须收到失败结果与 done 收口
                    outcome = AnalysisOutcome(symbol=symbol, error=f"分析任务异常：{exc}")
                self.queue.put(("outcome", outcome))
        finally:
            self.queue.put(("done", None))

    def _poll_queue(self) -> None:
        if self._closing:
            return
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                break
            if kind == "outcome":
                outcome = payload
                assert isinstance(outcome, AnalysisOutcome)
                if not self._discard_running_results:
                    self._add_outcome(outcome)
            elif kind == "screen_progress":
                done, total, rec = payload  # type: ignore[misc]
                if not self._discard_running_results:
                    self._add_recommendation(rec, done, total)
            elif kind == "done":
                self._set_running(False)
                if self._discard_running_results:
                    self._discard_running_results = False
                    self.status_var.set("已清空")
                    return
                self.status_var.set("分析已停止" if self.cancel_event.is_set() else "分析完成")
                first = self.tree.get_children()
                if first:
                    self.tree.selection_set(first[0])
                    self._show_selected_detail()
                return
            elif kind == "screen_done":
                if self._discard_running_results:
                    self._set_running(False)
                    self._discard_running_results = False
                    self.status_var.set("已清空")
                    return
                self._finish_screen(payload)  # type: ignore[arg-type]
                return
        self.root.after(120, self._poll_queue)

    def _add_outcome(self, outcome: AnalysisOutcome) -> None:
        if outcome.ok and outcome.result is not None:
            result = outcome.result
            item_id = result.symbol.normalized
            self.results[item_id] = result
            self.measurements[item_id] = outcome.measurement
            self.histories[item_id] = outcome.history
            self.tree.insert("", tk.END, iid=item_id, values=format_result_row(result), tags=result_row_tags(result))
        else:
            self.failures += 1
            item_id = f"fail-{self.failures}-{outcome.symbol.normalized}"
            self.tree.insert(
                "",
                tk.END,
                iid=item_id,
                values=(outcome.symbol.display, "", "失败", "", "", "", "", "高"),
                tags=("risk_high",),
            )
        completed = len(self.results) + self.failures
        self._refresh_table_height(completed)
        self.progress.configure(value=completed)
        self.summary_var.set(summarize_results(list(self.results.values()), self.failures))
        self.overview_var.set(build_portfolio_overview(list(self.results.values()), self.failures))
        self.status_var.set(f"已处理 {completed} 只股票")
        self._sync_result_action_tools()

    # ---- 全市场选股 ----

    def _select_preset(self, key: str) -> None:
        self.active_preset_key = key
        self.preset_var.set(key)
        preset = get_preset(key)
        self.preset_desc_var.set(
            f"{preset.description}（排序：{OBJECTIVE_LABELS.get(preset.objective, preset.objective)}）"
        )
        self._sync_preset_buttons()
        self._render_tunables(preset)
        if not self._save_persisted():
            self._report_config_save_failure("选股策略已切换", show_dialog=False)

    def _sync_preset_buttons(self) -> None:
        for preset_key, button in getattr(self, "preset_buttons", {}).items():
            if preset_key == self.active_preset_key:
                button.configure(
                    bg=ACCENT,
                    fg="#ffffff",
                    selectcolor=ACCENT,
                    activebackground=ACCENT_HOVER,
                    activeforeground="#ffffff",
                )
            else:
                button.configure(
                    bg=CARD_BG,
                    fg=MUTED_INK,
                    selectcolor=CARD_BG,
                    activebackground=ACCENT_SOFT,
                    activeforeground=ACCENT,
                )

    def _render_tunables(self, preset) -> None:
        for child in self.tunable_frame.winfo_children():
            child.destroy()
        self.tunable_vars = {}
        # 四项参数组成一条均衡横向带：标签同处第一行、输入同处第二行，宽屏不再只挤在左半边。
        for index, param in enumerate(preset.tunables):
            label = param.label if not param.unit else f"{param.label}（{param.unit}）"
            ttk.Label(self.tunable_frame, text=label, style="Hint.TLabel", anchor=tk.W).grid(
                row=0,
                column=index,
                sticky="ew",
                pady=(self._sc(3), self._sc(7)),
                padx=(0 if index == 0 else self._sc(12), self._sc(12)),
            )
            var = tk.StringVar(value=_format_number(param.default))
            allow_negative = "1" if param.minimum < 0 else "0"
            vcmd = (self.root.register(self._validate_spinbox_key), "%P", allow_negative)
            spin = ttk.Spinbox(
                self.tunable_frame, textvariable=var, width=12, from_=param.minimum, to=param.maximum,
                increment=_spin_step(param), justify=tk.CENTER, validate="key", validatecommand=vcmd,
            )
            spin.grid(
                row=1,
                column=index,
                sticky="ew",
                pady=(0, self._sc(7)),
                padx=(0 if index == 0 else self._sc(12), self._sc(12)),
            )
            self.tunable_vars[param.key] = var
            self.tunable_frame.columnconfigure(index, minsize=self._sc(180), weight=1, uniform="tunable")

    def _validate_spinbox_key(self, proposed: str, allow_negative: str) -> bool:
        """Spinbox key 级校验：只允许逐字符构造合法数字（按需允许负号）。"""
        return is_partial_number(proposed, allow_negative == "1")

    def _collect_tunable_values(self) -> dict[str, float]:
        """校验全部选股参数；任一“明显错误”（留空/非数字/超范围）都汇总成错误信息抛出，
        由调用方弹出错误窗口，绝不带着非法值继续选股，也不再静默纠正。"""
        preset = get_preset(self.active_preset_key)
        values: dict[str, float] = {}
        errors: list[str] = []
        for param in preset.tunables:
            var = self.tunable_vars.get(param.key)
            if var is None:
                continue
            try:
                value = validate_tunable(param.label, var.get(), param.minimum, param.maximum)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            values[param.key] = value
            var.set(_format_number(value))
        if errors:
            raise ValueError("\n".join(errors))
        return values

    def start_screen(self) -> None:
        if self.busy:
            return
        preset = get_preset(self.active_preset_key)
        try:
            values = self._collect_tunable_values()
            criteria, top_n = apply_tunables(preset, values)
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        deep = bool(self.deep_var.get())

        self.cancel_event.clear()
        self._discard_running_results = False
        self._reset_results()
        self.queue = queue.Queue()
        self._set_detail("正在拉取全市场行情并筛选，请稍候...")
        self._set_running(True)
        self.progress.configure(maximum=max(1, top_n), value=0)
        self.status_var.set(f"正在按“{preset.name}”从全市场选股...")
        self.summary_var.set("选股中")
        self.overview_var.set("选股概览：正在拉取全市场行情并筛选...")

        level = self.level_var.get()
        worker = threading.Thread(
            target=self._screen_worker,
            args=(criteria, preset.objective, top_n, deep, preset.name, level),
            daemon=True,
        )
        worker.start()
        self.root.after(120, self._poll_queue)

    def _screen_worker(self, criteria, objective, top_n, deep, preset_name, level=STANDARD_LEVEL) -> None:
        def progress(done: int, total: int, rec: Recommendation) -> None:
            self.queue.put(("screen_progress", (done, total, rec)))

        try:
            report = screen_and_recommend(
                self.provider, criteria, objective, top_n=top_n, deep=deep,
                cancel_event=self.cancel_event, progress_cb=progress, level=level,
            )
        except Exception as exc:  # noqa: BLE001 - 后台线程异常必须回主线程恢复 UI
            report = ScreenReport(total=0, matched=0, recommendations=[], error=f"选股任务异常：{exc}")
        self.queue.put(("screen_done", (preset_name, report)))

    def _add_recommendation(self, rec: Recommendation, done: int, total: int) -> None:
        item_id = f"rec-{rec.rank}-{rec.snapshot.code}"
        self.rec_meta[item_id] = rec
        if rec.measurement is not None:
            self.measurements[item_id] = rec.measurement
        if rec.result is not None:
            self.results[item_id] = rec.result
            tags = result_row_tags(rec.result)
        elif rec.error:
            tags = ("risk_high",)
        else:
            tags = ("action_hold",)
        self.tree.insert("", tk.END, iid=item_id, values=format_recommendation_row(rec), tags=tags)
        self._refresh_table_height(len(self.rec_meta))
        self.progress.configure(value=done)
        self.status_var.set(f"已分析入选股 {done}/{total}")
        self._sync_result_action_tools()

    def _finish_screen(self, payload: tuple[str, ScreenReport]) -> None:
        preset_name, report = payload
        self._set_running(False)
        if report.error:
            self.status_var.set("选股失败")
            self.overview_var.set(f"选股概览：{report.error}")
            self._set_detail(f"全市场选股失败：{report.error}\n\n" + DISCLAIMER)
            self._draw_empty_visual("全市场行情暂时取不到，请稍后重试。")
            messagebox.showerror("选股失败", report.error)
            return
        failures = sum(1 for rec in report.recommendations if rec.result is None and rec.error)
        shown = len(report.recommendations)
        self.overview_var.set(build_screener_overview(preset_name, report.total, report.matched, shown, failures))
        if report.cancelled:
            self.status_var.set("选股已停止")
        elif shown == 0:
            self.status_var.set("没有符合条件的股票")
            self.overview_var.set(
                f"选股概览（{preset_name}）：全市场扫描 {report.total} 只，没有符合条件的股票，请放宽筛选范围。"
            )
            self._set_detail("没有符合条件的股票，请放宽筛选范围（如降低成交额下限或放宽涨跌幅区间）。\n\n" + DISCLAIMER)
            self._draw_empty_visual("没有符合条件的股票，请放宽筛选范围。")
        else:
            self.status_var.set(f"选股完成，共 {shown} 只")
        self.summary_var.set(summarize_results(list(self.results.values()), failures))
        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])
            self._show_selected_detail()

    def _show_selected_detail(self, _event: object | None = None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        self._set_results_expanded(True)
        iid = selected[0]
        result = self.results.get(iid)
        rec = self.rec_meta.get(iid)
        measurement = self.measurements.get(iid)
        if result is not None:
            self._set_summary_metrics_for_result(result)
            self._set_summary_color(_action_color(result.action))
            self._current_history = self.histories.get(iid, [])
            self._safe_draw_visual(result)
            self._safe_draw_spectrum(measurement)
            self._safe_draw_kline(self._current_history)
            detail = build_detail_text(result)
            if rec is not None:
                detail = build_recommendation_header(rec) + "\n\n" + detail
            detail += self._build_strength_modules_text(iid)
            self._set_detail(detail)
            return
        self._safe_draw_spectrum(None)
        self._draw_empty_kline()
        if rec is not None:
            self._set_summary_metrics_for_snapshot(rec)
            self._set_summary_color(MUTED_INK)
            self._draw_empty_visual(
                f"深度分析失败：{rec.error}" if rec.error else "快照排序结果（未深度分析）"
            )
            self._set_detail(build_snapshot_detail(rec))
            return
        self._set_summary_metrics("失败", "—", "—", "—")
        self._set_summary_color(MUTED_INK)
        self._draw_empty_visual("该股票分析失败，请检查网络、代码有效性或稍后重试。")
        self._set_detail("该股票分析失败，请检查网络、代码有效性或稍后重试。\n\n" + DISCLAIMER)

    def _capital_value(self) -> float:
        try:
            value = float(self.capital_var.get())
        except (ValueError, AttributeError, tk.TclError):
            return 0.0
        return value if math.isfinite(value) and value > 0 else 0.0

    def _refresh_capital(self) -> None:
        saved = self._save_persisted()
        self._show_selected_detail()
        if not saved:
            self._report_config_save_failure("本金已更新", show_dialog=False)

    def _build_strength_modules_text(self, iid: str) -> str:
        """选中股的「决策强度光谱 + 仓位计算器 + 可信度回测」文本段。"""
        m = self.measurements.get(iid)
        if m is None:
            return ""
        level = self.level_var.get()
        level_name = LEVEL_NAMES[max(1, min(5, level))]
        parts = [
            "",
            build_spectrum_text(spectrum(m, level)),
            "",
            build_position_plan_text(position_plan(m, level, self._capital_value()), level_name),
        ]
        history = self.histories.get(iid)
        if history:
            parts += ["", build_backtest_text(backtest_signals(history, level))]
        return "\n" + "\n".join(parts)

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
    def _canvas_extent(canvas: tk.Canvas, fallback_width: int, fallback_height: int) -> tuple[int, int]:
        """返回画布当前真实尺寸；仅在尚未映射（1px）时使用控件请求尺寸兜底。

        绘图不得用大于真实可见宽度的设计稿回退值，否则最小窗口下图元会越过画布右缘。
        """
        width = int(canvas.winfo_width())
        height = int(canvas.winfo_height())
        if width <= 1:
            try:
                width = int(float(canvas.cget("width")))
            except (TypeError, ValueError, tk.TclError):
                width = int(fallback_width)
        if height <= 1:
            try:
                height = int(float(canvas.cget("height")))
            except (TypeError, ValueError, tk.TclError):
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
        colors = {"BUY": (POS_BG, POS_COLOR), "SELL": (NEG_BG, NEG_COLOR), "HOLD": (HOLD_BG, FLAT_COLOR)}
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
            self._round_rect(canvas, x0, box_top, x1, box_bottom, self._sc(7), fill=bg,
                             outline=ACCENT if cell.is_current else bg, width=2 if cell.is_current else 1)
            mark = " ●" if cell.is_current else ""
            canvas.create_text((x0 + x1) / 2, row1_y, text=cell.name + mark, fill=fg, font=name_font)
            canvas.create_text((x0 + x1) / 2, row2_y, text=labels.get(cell.action, cell.action), fill=fg,
                               font=label_font)

    def _draw_kline(self, history: list) -> None:
        canvas = self.kline_canvas
        canvas.delete("all")
        width, height = self._canvas_extent(canvas, self._sc(620), self._sc(300))
        canvas.create_text(self._sc(12), self._sc(14), text="近期 K 线（红涨绿跌） · MA5/10/20", anchor=tk.W,
                           fill=INK, font=(UI_FONT, 9, "bold"))
        bars = list(history[-60:]) if history else []
        if len(bars) < 2:
            self._draw_empty_kline("K线样本不足")
            return
        left, right, top, ph = self._sc(50), width - self._sc(16), self._sc(32), height - self._sc(104)
        vol_top, vol_h = top + ph + self._sc(14), self._sc(42)
        lo, hi = price_bounds(bars)
        layout = candle_layout(bars, left, right, top, ph)
        closes = [bar.close for bar in bars]
        bw = max(float(self._sc(2)), (right - left) / len(bars) * 0.6)
        canvas.create_text(left - self._sc(5), top, text=f"{hi:.2f}", anchor=tk.E, fill=MUTED_INK,
                           font=(UI_FONT, 8))
        canvas.create_text(left - self._sc(5), top + ph, text=f"{lo:.2f}", anchor=tk.E, fill=MUTED_INK,
                           font=(UI_FONT, 8))
        for cell, bar in zip(layout, bars):
            color = POS_COLOR if cell["up"] else NEG_COLOR
            canvas.create_line(cell["x"], cell["wick_top"], cell["x"], cell["wick_bottom"], fill=color)
            body_bottom = max(cell["body_bottom"], cell["body_top"] + self._sc(1))
            canvas.create_rectangle(cell["x"] - bw / 2, cell["body_top"], cell["x"] + bw / 2, body_bottom,
                                    fill=color, outline=color)
        for window, color in ((5, "#f59e0b"), (10, "#2563eb"), (20, "#7c3aed")):
            series = moving_average_series(closes, window)
            points: list[float] = []
            for index, value in enumerate(series):
                if value is not None:
                    points.extend([layout[index]["x"], price_to_y(value, lo, hi, top, ph)])
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=self._sc(1), smooth=True)
        volumes = volume_heights(bars, vol_h)
        for cell, _bar, vh in zip(layout, bars, volumes):
            color = "#e7a3a3" if cell["up"] else "#a7d6bd"
            canvas.create_rectangle(cell["x"] - bw / 2, vol_top + vol_h - vh, cell["x"] + bw / 2,
                                    vol_top + vol_h, fill=color, outline=color)
        # 存几何状态供 hover 十字光标映射
        self._kline_state = {"bars": bars, "layout": layout, "top": top, "ph": ph, "left": left}

    def _set_summary_color(self, color: str) -> None:
        metrics = getattr(self, "visual_summary_metrics", [])
        if not metrics:
            return
        for index, metric in enumerate(metrics):
            metric["value"].configure(fg=color if index == 0 else INK)

    def _set_summary_metrics(self, action: str, position: str, confidence: str, move: str) -> None:
        self.visual_metric_vars["action"].set(action)
        self.visual_metric_vars["position"].set(position)
        self.visual_metric_vars["confidence"].set(confidence)
        self.visual_metric_vars["move"].set(move)

    def _set_summary_metrics_for_result(self, result: AnalysisResult) -> None:
        move = _fmt_percent_value(result.expected_move_pct)
        if move != "样本不足":
            move = f"±{move}"
        self._set_summary_metrics(
            result.action_label,
            _fmt_whole_percent(result.suggested_position),
            _fmt_whole_percent(result.confidence),
            move,
        )

    def _set_summary_metrics_for_snapshot(self, rec: Recommendation) -> None:
        self._set_summary_metrics(
            "快照入围",
            f"第{rec.rank}名",
            _fmt_decimal(rec.snapshot.price),
            _fmt_percent_points(rec.snapshot.change_pct, signed=True),
        )

    def _sort_by_column(self, column: str) -> None:
        if column not in self.sort_reverse:
            reverse = column in {"score", "confidence", "change", "risk"}
        else:
            reverse = not self.sort_reverse[column]
        self.sort_reverse[column] = reverse
        rows = [(table_sort_key(column, tuple(self.tree.item(item, "values"))), item) for item in self.tree.get_children("")]
        rows.sort(reverse=reverse)
        for index, (_key, item) in enumerate(rows):
            self.tree.move(item, "", index)

    def _refresh_table_height(self, row_count: int) -> None:
        visible_rows = (
            TABLE_EMPTY_VISIBLE_ROWS
            if row_count <= 0
            else max(TABLE_MIN_VISIBLE_ROWS, min(TABLE_MAX_VISIBLE_ROWS, row_count))
        )
        self.tree.configure(height=visible_rows)
        if row_count <= 0:
            if self.table_card.winfo_manager():
                self.table_card.pack_forget()
            return
        if not self.table_card.winfo_manager():
            pack_options = dict(self._table_card_pack_options)
            if hasattr(self, "insight_strip"):
                # 结论卡折叠时 insight_strip 本身未 pack，不能拿来做 before= 锚点（Tk 会报
                # "isn't packed"）；这时结果表应插在占位提示之前，位置语义不变。
                anchor = self.insight_strip if self.insight_strip.winfo_manager() else self.results_placeholder
                pack_options["before"] = anchor
            self.table_card.pack(**pack_options)

    def _draw_empty_visual(self, message: str = "等待分析结果") -> None:
        # Task 3b 起，本面板只承担"判断拆解"——徽标/今日结论叙述/三项指标(综合判断·
        # 投入比例·把握程度)已分别在结果表(建议列)、结论卡(verdict card)和详情面板重复
        # 展示，这里不再重绘。message 形参保留（调用方仍传入语境化文案，见各调用点），
        # 但不再上屏——真正呈现给用户的错误/占位说明统一交给详情面板文本。
        self.visual.delete("all")
        width, height = self._canvas_extent(self.visual, self._sc(340), self._sc(300))
        left, top, right, bottom = self._sc(20), self._sc(20), width - self._sc(20), height - self._sc(20)

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
        left, right, top, bottom = self._sc(50), width - self._sc(16), self._sc(38), height - self._sc(82)
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
            canvas.create_line(x, y - self._sc(14), x, y + body_h + self._sc(14),
                               fill=color, tags=("empty_kline_candles",))
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
        for index, ratio in enumerate((0.54, 0.48, 0.51, 0.40, 0.34, 0.37, 0.29, 0.31, 0.25, 0.28, 0.23, 0.20)):
            ma_points.extend([left + step * (index + 0.5), top + (bottom - top) * ratio])
        canvas.create_line(*ma_points, fill=ACCENT_HOVER, width=self._sc(2), smooth=True,
                           tags=("empty_kline_candles",))

        vol_top, vol_h = bottom + self._sc(18), self._sc(30)
        for index, ratio in enumerate((0.40, 0.52, 0.31, 0.62, 0.35, 0.48, 0.57, 0.34, 0.64, 0.38, 0.46, 0.55)):
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
        left, top, right, bottom = self._sc(20), self._sc(20), width - self._sc(20), height - self._sc(20)

        # 因子分解整体在面板可用高度内垂直居中，避免只贴顶留下一大片空白；与
        # _draw_empty_visual 使用同一组尺寸常量，保证真实/占位两态观感一致。
        bars_h = self._sc(120)
        bars_y = top + max(0.0, (bottom - top - self._sc(28) - bars_h) / 2) + self._sc(28)
        self._draw_factor_bars(left, bars_y, right - left, bars_h, result)

    def _round_rect(self, canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float, **kwargs: Any) -> None:
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

    def _draw_factor_bars(self, x: float, y: float, width: float, height: float, result: AnalysisResult) -> None:
        self.visual.create_text(x, y - self._sc(9), text="判断拆解", anchor=tk.W, fill=INK,
                                font=(UI_FONT, 10, "bold"))
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
            self.visual.create_text(x, row_y + row_h / 2, text=_friendly_factor_name(factor.name),
                                    anchor=tk.W, fill=INK_SOFT, font=(UI_FONT, 8))
            self._round_rect(self.visual, bar_x, row_y + self._sc(4), bar_x + bar_w,
                             row_y + row_h - self._sc(4), self._sc(5), fill=CONTROL_BG, outline="")
            zero = bar_x + bar_w / 2
            score = _safe_int(factor.score)
            max_abs_score = max(_safe_int(factor.max_abs_score, default=1), 1)
            ratio = min(1.0, abs(score) / max_abs_score)
            end = zero + (bar_w / 2) * ratio * (1 if score >= 0 else -1)
            color = _score_color(score)
            self.visual.create_line(zero, row_y + self._sc(2), zero, row_y + row_h - self._sc(2),
                                    fill=MUTED_LIGHT)
            self._round_rect(self.visual, min(zero, end), row_y + self._sc(4), max(zero, end), row_y + row_h - self._sc(4), self._sc(5), fill=color, outline="")
            self.visual.create_text(x + width, row_y + row_h / 2, text=f"{score:+d}", anchor=tk.E,
                                    fill=color, font=(UI_FONT, 8, "bold"))

    def _set_detail(self, text: str) -> None:
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self._insert_styled_detail(text)
        self.detail.yview_moveto(0.0)
        self.detail.configure(state=tk.DISABLED)
        if hasattr(self, "detail_nav_var"):
            self.detail_nav_var.set(DETAIL_NAV_SECTIONS[0][0])
            self._sync_detail_nav_buttons()

    def _jump_detail_section(self, label: str, heading: str) -> None:
        self.detail_nav_var.set(label)
        index = self.detail.search(heading, "1.0", tk.END, exact=True)
        if index:
            self.detail.see(index)
        self._sync_detail_nav_buttons()

    def _sync_detail_nav_buttons(self) -> None:
        current = getattr(self, "detail_nav_var", tk.StringVar(value="")).get()
        for button in getattr(self, "detail_nav_buttons", []):
            selected = button.cget("text") == current
            button.configure(
                bg=ACCENT if selected else CONTROL_BG,
                fg="#ffffff" if selected else MUTED_INK,
                activebackground=ACCENT if selected else ACCENT_SOFT,
                activeforeground="#ffffff" if selected else ACCENT,
                selectcolor=ACCENT if selected else CONTROL_BG,
            )

    def _configure_detail_tags(self) -> None:
        self.detail.configure(
            background=CARD_BG,
            foreground=INK,
            insertbackground=INK,
            padx=self._sc(16),
            pady=self._sc(14),
            spacing1=self._sc(2),
            spacing2=self._sc(1),
            spacing3=self._sc(7),
        )
        self.detail.tag_configure("headline", font=(UI_FONT, 14, "bold"), foreground=INK, spacing3=self._sc(12))
        self.detail.tag_configure("section", font=(UI_FONT, 12, "bold"), foreground=ACCENT,
                                  spacing1=self._sc(10), spacing3=self._sc(6))
        self.detail.tag_configure("positive", foreground=POS_COLOR)
        self.detail.tag_configure("negative", foreground=NEG_COLOR)
        self.detail.tag_configure("muted", foreground=MUTED_INK)
        self.detail.tag_configure("bullet", lmargin1=self._sc(16), lmargin2=self._sc(28), spacing3=self._sc(4))
        self.detail.tag_configure("risk", foreground=DANGER_COLOR, lmargin1=self._sc(16),
                                  lmargin2=self._sc(28), spacing3=self._sc(4))

    def _insert_styled_detail(self, text: str) -> None:
        lines = text.splitlines()
        for index, line in enumerate(lines):
            self.detail.insert(tk.END, line + "\n", detail_line_tags(line, index == 0))


def run_gui() -> None:
    root = tk.Tk()
    StockAdvisorApp(root)
    root.mainloop()
