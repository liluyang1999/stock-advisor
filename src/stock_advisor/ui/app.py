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

from ..data.data_provider import EastmoneyProvider
from ..data.sample_data import (
    _sample_quote_history,
    make_sample_analysis,
    make_sample_history,
    make_sample_measurement,
    make_sample_recommendation,
)
from ..domain.alerts import FIELD_KEYS_BY_LABEL, FIELD_LABELS, OPS, check_rules, rule_summary
from ..domain.backtest import backtest_signals
from ..domain.chart import (
    candle_layout,
    moving_average_series,
    nearest_index,
    price_bounds,
    price_to_y,
    volume_heights,
)
from ..domain.compare import build_comparison_rows
from ..domain.engine import build_analysis_result
from ..domain.formatting import (
    _flow_direction,
    _fmt_backtest_excess,
    _fmt_backtest_return,
    _fmt_decimal,
    _fmt_percent,
    _fmt_percent_points,
    _fmt_percent_value,
    _fmt_rate_percent,
    _fmt_whole_percent,
    _fmt_yi,
    _format_number,
    _looks_positive,
    _looks_risky,
    _positive_finite_float,
    _positive_finite_int,
    _safe_int,
    _spin_step,
    risk_level,
)
from ..domain.input_validate import (
    _parse_alert_threshold,
    _parse_optional_positive,
    _parse_optional_positive_int,
    is_partial_number,
    validate_tunable,
)
from ..domain.models import (
    LEVEL_NAMES,
    STANDARD_LEVEL,
    AlertRule,
    AnalysisResult,
    AppConfig,
    BacktestReport,
    DailyBar,
    FundFlow,
    Measurement,
    PositionPlan,
    Recommendation,
    SpectrumCell,
    WatchItem,
)
from ..domain.policy import decide, flip_hint, level_spec, position_plan, spectrum
from ..domain.presets import PRESETS, apply_tunables, get_preset
from ..domain.screener import OBJECTIVE_LABELS
from ..domain.symbols import normalize_symbol, parse_user_symbols
from ..services import store
from ..services.workflow import AnalysisOutcome, ScreenReport, analyze_symbol, screen_and_recommend
from .app_alerts import AlertsMonitorMixin
from .app_charts import ChartRenderMixin
from .app_detail import DetailViewMixin
from .app_geometry import WindowGeometryMixin
from .app_screener import ScreenerMixin
from .app_watchlist import WatchlistCompareMixin
from .layout import (
    active_mode_action,
    choose_centering_screen_size,
    compute_centered_geometry,
    compute_centered_window,
    compute_child_window_geometry,
    compute_content_band,
    compute_main_geometry,
    compute_scaled_minimum,
    compute_window_position,
    compute_workspace_columns,
    normalize_work_area_to_screen,
    stacked_text_y,
    ui_scale,
)
from .theme import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_PRESSED,
    ACCENT_SOFT,
    ACCENT_SOFT_HOVER,
    ACTION_BUTTON_LABELS,
    APP_ICON_FILENAME,
    APP_TITLE,
    ASSET_DIR,
    BORDER_SOFT,
    CARD_BG,
    CARD_BORDER,
    CHILD_WINDOW_WORKAREA_MARGIN,
    COMMAND_BG,
    COMMAND_BORDER,
    COMMAND_INK,
    COMMAND_MUTED_INK,
    COMMAND_SELECTED_BG,
    COMMAND_SELECTED_INK,
    COMMAND_SURFACE,
    CONTENT_MARGIN,
    CONTROL_BG,
    CONTROL_DISABLED_BG,
    CONTROL_HOVER_BG,
    DANGER_BG,
    DANGER_COLOR,
    DETAIL_NAV_SECTIONS,
    DISCLAIMER,
    FLAT_COLOR,
    GRID_COLOR,
    HEADER_LOGO_SIZE,
    HOLD_BG,
    INFO_WINDOW_SIZE,
    INK,
    INK_SOFT,
    MAIN_MIN_SIZE,
    MAX_CONTENT_WIDTH,
    MAX_SYMBOLS,
    MENU_BUTTON_SHORT_WIDTH,
    MENU_BUTTON_TOOL_WIDTH,
    MONITOR_INTERVAL_MS,
    MONO_FONT,
    MUTED_INK,
    MUTED_LIGHT,
    NEG_BG,
    NEG_COLOR,
    PAGE_BG,
    POS_BG,
    POS_COLOR,
    SAMPLE_INPUT,
    SCROLLBAR_ACTIVE_BG,
    SCROLLBAR_BG,
    SCROLLBAR_PRESSED_BG,
    SELECTION_BG,
    SURFACE_ALT,
    TABLE_COLUMNS,
    TABLE_EMPTY_VISIBLE_ROWS,
    TABLE_HEADER_BG,
    TABLE_MAX_VISIBLE_ROWS,
    TABLE_MIN_VISIBLE_ROWS,
    UI_FONT,
    WINDOW_ALPHA,
    WINDOW_MAX_SIZE,
    WINDOW_WORKAREA_MARGIN,
)
from .view_format import (
    _action_color,
    _score_color,
    build_snapshot_detail,
    build_snapshot_summary,
    detail_line_tags,
    format_comparison_row,
    format_recommendation_row,
    format_result_row,
    format_results_as_csv,
    format_results_for_clipboard,
    format_table_rows_as_csv,
    format_table_rows_for_clipboard,
    result_row_tags,
    snapshot_display,
    table_sort_key,
    watchlist_rows,
)
from .view_text import (
    _focus_symbols,
    _friendly_factor_name,
    _friendly_verdict,
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
    build_strategy_sections,
    build_visual_summary,
    level_summary,
    normalize_symbol_input_text,
    summarize_results,
)


class StockAdvisorApp(
    WatchlistCompareMixin,
    DetailViewMixin,
    ScreenerMixin,
    ChartRenderMixin,
    AlertsMonitorMixin,
    WindowGeometryMixin,
):
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
        self.monitor_queue: queue.Queue = queue.Queue()
        self.fund_flow_queue: queue.Queue = queue.Queue()
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
        except ValueError, tk.TclError:
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

    # ---- 条件预警 ----

    # ---- 个股资金流（按需、降级安全；数据源偶发不稳定，不进核心流程）----

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=PAGE_BG)
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("TLabel", background=PAGE_BG, foreground=INK)
        style.configure(
            "Title.TLabel", font=(UI_FONT, 18, "bold"), foreground=INK, background=PAGE_BG
        )
        style.configure(
            "Subtitle.TLabel", foreground=MUTED_INK, font=(UI_FONT, 10), background=PAGE_BG
        )
        style.configure("Hint.TLabel", foreground=MUTED_INK, font=(UI_FONT, 10), background=PAGE_BG)
        style.configure(
            "SurfaceHint.TLabel", foreground=MUTED_INK, font=(UI_FONT, 10), background=CARD_BG
        )
        style.configure(
            "SectionTitle.TLabel", foreground=INK, font=(UI_FONT, 12, "bold"), background=PAGE_BG
        )
        style.configure(
            "DialogTitle.TLabel", foreground=INK, font=(UI_FONT, 16, "bold"), background=PAGE_BG
        )
        style.configure(
            "HeaderMeta.TLabel", foreground=MUTED_INK, font=(UI_FONT, 9), background=PAGE_BG
        )
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
        style.map(
            "Primary.TButton",
            background=[
                ("pressed", ACCENT_PRESSED),
                ("active", ACCENT_HOVER),
                ("disabled", MUTED_LIGHT),
            ],
            foreground=[("disabled", SURFACE_ALT)],
            relief=[("pressed", "flat"), ("!pressed", "flat")],
        )

        for name, pad in (
            ("Action.TButton", (self._sc(14), self._sc(10))),
            ("Quiet.TButton", (self._sc(13), self._sc(10))),
            ("Preset.TButton", (self._sc(16), self._sc(11))),
        ):
            style.configure(
                name,
                padding=pad,
                font=(UI_FONT, 10),
                background=CONTROL_BG,
                foreground=INK_SOFT,
                borderwidth=0,
                relief="flat",
                focusthickness=1,
                focuscolor=ACCENT_SOFT,
            )
            style.map(
                name,
                background=[
                    ("pressed", ACCENT_SOFT_HOVER),
                    ("active", CONTROL_HOVER_BG),
                    ("disabled", CONTROL_DISABLED_BG),
                ],
                foreground=[("disabled", MUTED_LIGHT)],
                relief=[("pressed", "flat"), ("!pressed", "flat")],
            )

        style.configure(
            "PresetActive.TButton",
            padding=(self._sc(16), self._sc(11)),
            font=(UI_FONT, 10, "bold"),
            background=ACCENT,
            foreground="#ffffff",
            borderwidth=0,
            relief="flat",
            focusthickness=1,
            focuscolor=ACCENT_SOFT,
        )
        style.map(
            "PresetActive.TButton",
            background=[("pressed", ACCENT_PRESSED), ("active", ACCENT_HOVER)],
            relief=[("pressed", "flat"), ("!pressed", "flat")],
        )
        style.configure(
            "Action.TMenubutton",
            padding=(self._sc(14), self._sc(10)),
            font=(UI_FONT, 10),
            background=CONTROL_BG,
            foreground=INK_SOFT,
            borderwidth=0,
            relief="flat",
            focusthickness=1,
            focuscolor=ACCENT_SOFT,
        )
        style.configure(
            "Quiet.TMenubutton",
            padding=(self._sc(13), self._sc(10)),
            font=(UI_FONT, 10),
            background=CONTROL_BG,
            foreground=INK_SOFT,
            borderwidth=0,
            relief="flat",
            focusthickness=1,
            focuscolor=ACCENT_SOFT,
        )
        for name in ("Action.TMenubutton", "Quiet.TMenubutton"):
            style.map(
                name,
                background=[
                    ("pressed", ACCENT_SOFT_HOVER),
                    ("active", CONTROL_HOVER_BG),
                    ("disabled", CONTROL_DISABLED_BG),
                ],
                foreground=[("disabled", MUTED_LIGHT)],
                relief=[("pressed", "flat"), ("!pressed", "flat")],
            )

        # 选项卡改为自绘分段胶囊（见 _build_tabs / _show_info_window），不再用 ttk.Notebook 样式，
        # 因为 clam 主题的选中标签会明显变矮/位移，难以做到等尺寸精致。

        style.configure(
            "Treeview",
            rowheight=self._sc(42),
            font=(UI_FONT, 10),
            borderwidth=0,
            background=CARD_BG,
            fieldbackground=CARD_BG,
            foreground=INK,
        )
        style.configure(
            "Treeview.Heading",
            font=(UI_FONT, 10, "bold"),
            background=TABLE_HEADER_BG,
            foreground=INK_SOFT,
            relief="flat",
            borderwidth=0,
            padding=(0, self._sc(8)),
        )
        style.map(
            "Treeview", background=[("selected", SELECTION_BG)], foreground=[("selected", INK)]
        )
        style.map("Treeview.Heading", background=[("active", ACCENT_SOFT)])

        for field_style in ("TEntry", "TCombobox", "TSpinbox"):
            style.configure(
                field_style,
                fieldbackground=CARD_BG,
                background=CONTROL_BG,
                bordercolor=CARD_BORDER,
                lightcolor=CARD_BORDER,
                darkcolor=CARD_BORDER,
                foreground=INK,
                padding=self._sc(7),
                relief="flat",
            )
            style.map(
                field_style,
                bordercolor=[("focus", ACCENT)],
                lightcolor=[("focus", ACCENT)],
                darkcolor=[("focus", ACCENT)],
            )
        style.configure("TSpinbox", arrowsize=self._sc(13))
        style.configure("TCheckbutton", background=PAGE_BG, foreground=INK)
        style.map("TCheckbutton", background=[("active", PAGE_BG)])
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=CONTROL_BG,
            background=ACCENT,
            bordercolor=CONTROL_BG,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=self._sc(14),
        )
        # 细窄、低对比的滚动条，避免抢夺工作区视觉焦点。
        for _orient in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            style.configure(
                _orient,
                gripcount=0,
                borderwidth=0,
                relief="flat",
                background=SCROLLBAR_BG,
                troughcolor=PAGE_BG,
                bordercolor=PAGE_BG,
                lightcolor=PAGE_BG,
                darkcolor=PAGE_BG,
                arrowcolor=MUTED_LIGHT,
                arrowsize=self._sc(11),
                width=self._sc(11),
            )
            style.map(
                _orient,
                background=[("active", SCROLLBAR_ACTIVE_BG), ("pressed", SCROLLBAR_PRESSED_BG)],
            )

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
        ttk.Label(heading, text=subtitle, style="Subtitle.TLabel").pack(
            anchor=tk.W, pady=(self._sc(3), 0)
        )
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
        self.logo_canvas.pack(
            side=tk.LEFT, anchor=tk.NW, padx=(0, self._sc(14)), pady=(self._sc(2), 0)
        )
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
        tk.Label(
            self.level_control_group,
            text="决策强度",
            bg=COMMAND_BG,
            fg=COMMAND_MUTED_INK,
            font=(UI_FONT, 10, "bold"),
        ).pack(side=tk.LEFT, padx=(0, self._sc(12)))
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
            self.input_panel_body,
            autohide_scrollbar=True,
            height=3,
            wrap=tk.WORD,
            font=(MONO_FONT, 12),
            relief=tk.FLAT,
            borderwidth=0,
            background=SURFACE_ALT,
            foreground=INK,
            insertbackground=ACCENT,
            padx=self._sc(14),
            pady=self._sc(10),
        )
        self.symbol_input.insert("1.0", SAMPLE_INPUT)
        self.symbol_input.edit_modified(False)
        self.symbol_input.bind("<<Modified>>", self._on_symbol_input_modified, add="+")
        self.symbol_input.bind(
            "<Configure>", lambda _event: self._schedule_symbol_scrollbar_refresh(), add="+"
        )
        self._schedule_symbol_scrollbar_refresh()

        self.input_context_frame = tk.Frame(
            self.input_panel_body,
            bg=CARD_BG,
            padx=self._sc(16),
            pady=self._sc(11),
        )
        self.input_context_frame.pack(side=tk.TOP, fill=tk.X)
        self.input_context_title = tk.Label(
            self.input_context_frame,
            text="研究标的",
            bg=CARD_BG,
            fg=INK,
            font=(UI_FONT, 11, "bold"),
            anchor=tk.W,
        )
        self.input_context_title.pack(side=tk.LEFT, anchor=tk.W)
        self.input_context_hint = tk.Label(
            self.input_context_frame,
            text=f"最多 {MAX_SYMBOLS} 只",
            bg=CARD_BG,
            fg=MUTED_INK,
            font=(UI_FONT, 9),
            anchor=tk.E,
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
        self.analyze_button = ttk.Button(
            self.input_action_frame, text="开始分析", style="Primary.TButton", command=self.analyze
        )
        self.analyze_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(
            self.input_action_frame,
            text="停止",
            style="Action.TButton",
            command=self.stop,
            state=tk.DISABLED,
        )
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
        self._add_to_watchlist_pack_options = {
            "side": tk.LEFT,
            "before": self.secondary_tools_button,
        }
        self._copy_tools_pack_options = {
            "side": tk.LEFT,
            "padx": (6, 0),
            "before": self.secondary_tools_button,
        }
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
        self.alert_banner = tk.Label(
            outer,
            text="",
            bg=DANGER_BG,
            fg=DANGER_COLOR,
            anchor=tk.W,
            font=(UI_FONT, 10, "bold"),
            padx=self._sc(12),
            pady=self._sc(8),
        )

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
        self.tree = ttk.Treeview(
            self.table_card, columns=TABLE_COLUMNS, show="headings", height=TABLE_EMPTY_VISIBLE_ROWS
        )
        self.table_scroll = ttk.Scrollbar(
            self.table_card, orient=tk.VERTICAL, command=self.tree.yview
        )
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
            self.tree.heading(
                column, text=title, command=lambda key=column: self._sort_by_column(key)
            )
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
                {
                    "frame": cell,
                    "title": title,
                    "value": value,
                    "value_var": self.visual_metric_vars[key],
                }
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
        self.visual_workspace_header.pack(
            side=tk.TOP, fill=tk.X, padx=self._sc(16), pady=self._sc(12)
        )
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
        ttk.Label(self.capital_tools_frame, text="本金", style="SurfaceHint.TLabel").pack(
            side=tk.LEFT
        )
        self.capital_entry = ttk.Entry(
            self.capital_tools_frame, textvariable=self.capital_var, width=14
        )
        self.capital_entry.pack(side=tk.LEFT, padx=(self._sc(8), self._sc(8)))
        self.capital_entry.bind("<KeyRelease>", lambda _e: self._refresh_capital())
        self.capital_hint_label = ttk.Label(
            self.capital_tools_frame, text="即时重算", style="SurfaceHint.TLabel"
        )
        self.capital_hint_label.pack(side=tk.LEFT)

        self.detail_nav_frame = tk.Frame(self.detail_control_bar, bg=CARD_BG)
        self.detail_nav_frame.pack(side=tk.RIGHT)
        ttk.Label(self.detail_nav_frame, text="详情", style="SurfaceHint.TLabel").pack(
            side=tk.LEFT, padx=(0, 6)
        )
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
                tk.Label(
                    empty_steps_row, text="→", bg=CARD_BG, fg=MUTED_LIGHT, font=(UI_FONT, 10)
                ).pack(side=tk.LEFT, padx=self._sc(12))
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
            "fill": tk.X,
            "pady": (0, self._sc(14)),
            "before": self._results_disclaimer_label,
        }
        self._visual_workspace_shell_pack_options = {
            "fill": tk.X,
            "pady": (0, self._sc(14)),
            "before": self._results_disclaimer_label,
        }
        self._detail_panel_shell_pack_options = {
            "fill": tk.BOTH,
            "expand": True,
            "before": self._results_disclaimer_label,
        }
        self._results_placeholder_pack_options = {
            "fill": tk.X,
            "pady": (0, self._sc(14)),
            "before": self._results_disclaimer_label,
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
        x_offset, content_width = compute_content_band(
            width, self._sc(MAX_CONTENT_WIDTH), self._sc(CONTENT_MARGIN)
        )
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
            symbols = parse_user_symbols(
                self.symbol_input.get("1.0", tk.END), max_count=MAX_SYMBOLS
            )
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

    def _set_result_action_tools_visible(
        self, has_deep_results: bool, has_visible_rows: bool
    ) -> None:
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
            cleaned = normalize_symbol_input_text(
                self.symbol_input.get("1.0", tk.END), max_count=MAX_SYMBOLS
            )
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
            self.tree.insert(
                "",
                tk.END,
                iid=item_id,
                values=format_result_row(result),
                tags=result_row_tags(result),
            )
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

    def _capital_value(self) -> float:
        try:
            value = float(self.capital_var.get())
        except ValueError, AttributeError, tk.TclError:
            return 0.0
        return value if math.isfinite(value) and value > 0 else 0.0

    def _refresh_capital(self) -> None:
        saved = self._save_persisted()
        self._show_selected_detail()
        if not saved:
            self._report_config_save_failure("本金已更新", show_dialog=False)

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
        rows = [
            (table_sort_key(column, tuple(self.tree.item(item, "values"))), item)
            for item in self.tree.get_children("")
        ]
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
                anchor = (
                    self.insight_strip
                    if self.insight_strip.winfo_manager()
                    else self.results_placeholder
                )
                pack_options["before"] = anchor
            self.table_card.pack(**pack_options)


def run_gui() -> None:
    root = tk.Tk()
    StockAdvisorApp(root)
    root.mainloop()
