from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from ..domain.formatting import (
    _fmt_decimal,
    _fmt_percent_points,
    _fmt_percent_value,
    _fmt_whole_percent,
)
from ..domain.models import AnalysisResult, Recommendation
from .theme import (
    ACCENT,
    ACCENT_SOFT,
    BORDER_SOFT,
    CARD_BG,
    CARD_BORDER,
    CONTROL_BG,
    DANGER_BG,
    DANGER_COLOR,
    DETAIL_NAV_SECTIONS,
    DISCLAIMER,
    INK,
    INK_SOFT,
    MENU_BUTTON_SHORT_WIDTH,
    MUTED_INK,
    MUTED_LIGHT,
    TABLE_COLUMNS,
    TABLE_EMPTY_VISIBLE_ROWS,
    TABLE_MAX_VISIBLE_ROWS,
    TABLE_MIN_VISIBLE_ROWS,
    UI_FONT,
)
from .view_format import (
    format_results_as_csv,
    format_results_for_clipboard,
    format_table_rows_as_csv,
    format_table_rows_for_clipboard,
    table_sort_key,
)
from .view_text import build_portfolio_overview


class ResultsTableMixin:
    """结果表格构建/排序/高度 + 摘要指标 + 复制/CSV 导出——从 StockAdvisorApp 抽出的结果表关注点。"""

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

    def _table_export_rows(self) -> list[tuple[str, ...]]:
        rows: list[tuple[str, ...]] = []
        for iid in self.tree.get_children():
            values = self.tree.item(iid, "values")
            rows.append(tuple(str(value) for value in values))
        return rows

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
