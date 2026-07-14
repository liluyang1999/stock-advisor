from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from ..domain.alerts import FIELD_KEYS_BY_LABEL, FIELD_LABELS, OPS, check_rules, rule_summary
from ..domain.input_validate import _parse_alert_threshold
from ..domain.models import AlertRule
from ..domain.symbols import normalize_symbol
from ..services.workflow import analyze_symbol
from .theme import (
    ACCENT,
    ACCENT_SOFT,
    BORDER_SOFT,
    CARD_BG,
    CARD_BORDER,
    CONTROL_BG,
    INK,
    MONITOR_INTERVAL_MS,
    MUTED_INK,
    PAGE_BG,
    UI_FONT,
)
from .view_text import build_fund_flow_text
from .widgets import StatefulToplevel

if TYPE_CHECKING:
    from ._app_members import AppMembers as _MembersBase
else:
    _MembersBase = object


class AlertsMonitorMixin(_MembersBase):
    """预警规则管理 + 实时监控轮询 + 资金流查询——从 StockAdvisorApp 抽出的预警/监控关注点。"""

    def open_alert_manager(self) -> None:
        window = StatefulToplevel(self.root)
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
            summary_metrics.append(
                {"frame": cell, "title": title, "value": value, "value_var": summary_vars[key]}
            )
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
                tree.insert(
                    "",
                    tk.END,
                    iid=str(index),
                    values=(rule_summary(rule), "是" if rule.enabled else "否"),
                )
            update_summary()

        form = ttk.Frame(container)
        form.pack(fill=tk.X, pady=(10, 6))
        ttk.Label(form, text="代码", style="Hint.TLabel").pack(side=tk.LEFT)
        code_var = tk.StringVar()
        ttk.Entry(form, textvariable=code_var, width=10).pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(form, text="字段", style="Hint.TLabel").pack(side=tk.LEFT)
        field_var = tk.StringVar(value=FIELD_LABELS["price"])
        field_combobox = ttk.Combobox(
            form,
            textvariable=field_var,
            width=9,
            state="readonly",
            values=list(FIELD_LABELS.values()),
        )
        field_combobox.pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(form, text="条件", style="Hint.TLabel").pack(side=tk.LEFT)
        op_var = tk.StringVar(value=">=")
        ttk.Combobox(form, textvariable=op_var, width=4, state="readonly", values=list(OPS)).pack(
            side=tk.LEFT, padx=(4, 10)
        )
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
            self.alerts.append(
                AlertRule(code=symbol.normalized, field=field, op=op, threshold=threshold)
            )
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
            self.alerts[index] = AlertRule(
                rule.code, rule.field, rule.op, rule.threshold, not rule.enabled
            )
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
        close_button = ttk.Button(
            controls, text="关闭", style="Action.TButton", command=window.destroy
        )
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
                threading.Thread(
                    target=self._monitor_worker,
                    args=(codes, self.level_var.get(), generation),
                    daemon=True,
                ).start()
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

    def show_fund_flow(self) -> None:
        selected = self.tree.selection()
        result = self.results.get(selected[0]) if selected else None
        if result is None:
            messagebox.showinfo("资金流", "请先选择一只已分析的股票。")
            return
        self.status_var.set(f"正在查询 {result.symbol.display} 主力资金流...")
        threading.Thread(
            target=self._fund_flow_worker, args=(result.symbol, result.name), daemon=True
        ).start()
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
            messagebox.showinfo(
                "资金流", f"{symbol.display} 主力资金流暂取不到（数据源不稳定，可稍后重试）。"
            )
            return
        self.status_var.set(f"{symbol.display} 资金流已更新")
        messagebox.showinfo("主力资金流", build_fund_flow_text(flow, name))
