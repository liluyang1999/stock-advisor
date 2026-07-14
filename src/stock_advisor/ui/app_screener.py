from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from ..domain.formatting import _format_number, _spin_step
from ..domain.input_validate import is_partial_number, validate_tunable
from ..domain.models import STANDARD_LEVEL, Recommendation
from ..domain.presets import PRESETS, apply_tunables, get_preset
from ..domain.screener import OBJECTIVE_LABELS
from ..services.workflow import ScreenReport, screen_and_recommend
from .theme import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_SOFT,
    CARD_BG,
    CARD_BORDER,
    DISCLAIMER,
    MUTED_INK,
    UI_FONT,
)
from .view_format import (
    _action_color,
    build_snapshot_detail,
    format_recommendation_row,
    result_row_tags,
)
from .view_text import (
    build_detail_text,
    build_recommendation_header,
    build_screener_overview,
    summarize_results,
)


class ScreenerMixin:
    """选股 tab 构建 + 预设/可调参数 + 批量选股运行/结果——从 StockAdvisorApp 抽出的选股关注点。"""

    def _build_screener_tab(self, parent: ttk.Frame) -> None:
        self.screener_section_title = ttk.Label(
            parent, text="策略扫描", style="SectionTitle.TLabel"
        )
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
            button.grid(
                row=index // 3,
                column=index % 3,
                sticky="ew",
                padx=(0 if index % 3 == 0 else 1, 0),
                pady=(0 if index < 3 else 1, 0),
            )
            self.preset_buttons[preset.key] = button
        for column in range(3):
            cards.columnconfigure(column, weight=1)

        ttk.Label(
            parent,
            textvariable=self.preset_desc_var,
            style="Subtitle.TLabel",
            wraplength=self._sc(760),
        ).pack(anchor=tk.W, pady=(self._sc(12), self._sc(10)))

        self.tunable_frame = ttk.Frame(parent)
        self.tunable_frame.pack(fill=tk.X, pady=(self._sc(4), self._sc(12)))

        run_row = ttk.Frame(parent)
        run_row.pack(fill=tk.X, pady=(self._sc(6), 0))
        self.screen_button = ttk.Button(
            run_row, text="开始选股", style="Primary.TButton", command=self.start_screen
        )
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
            "side": tk.LEFT,
            "padx": (8, 0),
            "before": self.deep_toggle_button,
        }
        ttk.Label(run_row, text="给买 / 持 / 卖与理由，较慢", style="Hint.TLabel").pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self._sync_deep_toggle()

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
                self.tunable_frame,
                textvariable=var,
                width=12,
                from_=param.minimum,
                to=param.maximum,
                increment=_spin_step(param),
                justify=tk.CENTER,
                validate="key",
                validatecommand=vcmd,
            )
            spin.grid(
                row=1,
                column=index,
                sticky="ew",
                pady=(0, self._sc(7)),
                padx=(0 if index == 0 else self._sc(12), self._sc(12)),
            )
            self.tunable_vars[param.key] = var
            self.tunable_frame.columnconfigure(
                index, minsize=self._sc(180), weight=1, uniform="tunable"
            )

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

    def _screen_worker(
        self, criteria, objective, top_n, deep, preset_name, level=STANDARD_LEVEL
    ) -> None:
        def progress(done: int, total: int, rec: Recommendation) -> None:
            self.queue.put(("screen_progress", (done, total, rec)))

        try:
            report = screen_and_recommend(
                self.provider,
                criteria,
                objective,
                top_n=top_n,
                deep=deep,
                cancel_event=self.cancel_event,
                progress_cb=progress,
                level=level,
            )
        except Exception as exc:  # noqa: BLE001 - 后台线程异常必须回主线程恢复 UI
            report = ScreenReport(
                total=0, matched=0, recommendations=[], error=f"选股任务异常：{exc}"
            )
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
        self.overview_var.set(
            build_screener_overview(preset_name, report.total, report.matched, shown, failures)
        )
        if report.cancelled:
            self.status_var.set("选股已停止")
        elif shown == 0:
            self.status_var.set("没有符合条件的股票")
            self.overview_var.set(
                f"选股概览（{preset_name}）：全市场扫描 {report.total} 只，没有符合条件的股票，请放宽筛选范围。"
            )
            self._set_detail(
                "没有符合条件的股票，请放宽筛选范围（如降低成交额下限或放宽涨跌幅区间）。\n\n"
                + DISCLAIMER
            )
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
