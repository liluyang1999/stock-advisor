from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from ..domain.compare import build_comparison_rows
from ..domain.formatting import (
    _format_number,
    _positive_finite_float,
    _positive_finite_int,
    risk_level,
)
from ..domain.input_validate import _parse_optional_positive, _parse_optional_positive_int
from ..domain.models import WatchItem
from ..domain.symbols import normalize_symbol
from .theme import (
    BORDER_SOFT,
    CARD_BG,
    CARD_BORDER,
    FLAT_COLOR,
    HOLD_BG,
    INK,
    MUTED_INK,
    NEG_BG,
    NEG_COLOR,
    PAGE_BG,
    POS_BG,
    POS_COLOR,
    UI_FONT,
)
from .view_format import format_comparison_row, watchlist_rows

if TYPE_CHECKING:
    from ._app_members import AppMembers as _MembersBase
else:
    _MembersBase = object


class WatchlistCompareMixin(_MembersBase):
    """自选股加入/管理 + 多股对比窗——从 StockAdvisorApp 抽出的自选/对比关注点。"""

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

    def _results_by_code(self) -> dict:
        return {result.symbol.normalized: result for result in self.results.values()}

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
            summary_metrics.append(
                {"frame": cell, "title": title, "value": value, "value_var": summary_vars[key]}
            )
        window._watchlist_summary_metrics = summary_metrics

        table_card = tk.Frame(container, bg=CARD_BORDER, padx=1, pady=1)
        table_card.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(
            table_card, columns=("code", "name", "cost", "shares", "pl"), show="headings", height=10
        )
        watch_headings = {
            "code": ("代码", 110),
            "name": ("名称", 130),
            "cost": ("成本", 90),
            "shares": ("股数", 90),
            "pl": ("浮动盈亏", 190),
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
                if _positive_finite_float(item.cost) is not None
                or _positive_finite_int(item.shares) is not None
            )
            summary_vars["total"].set(str(len(self.watch)))
            summary_vars["held"].set(str(held))
            summary_vars["analyzed"].set(
                str(sum(1 for item in self.watch if item.code in results_by_code))
            )
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
            if self.watch and messagebox.askyesno(
                "清空自选", "确定清空全部自选/持仓？", parent=window
            ):
                self.watch.clear()
                saved = self._save_persisted()
                refresh()
                if saved:
                    self.status_var.set("自选已清空")
                else:
                    self._report_config_save_failure("自选已清空", parent=window)

        buttons = ttk.Frame(container)
        buttons.pack(fill=tk.X, pady=(6, 0))
        save_button = ttk.Button(
            buttons, text="保存持仓", style="Action.TButton", command=save_position
        )
        save_button.pack(side=tk.LEFT)
        more_button = ttk.Menubutton(buttons, text="更多操作", style="Action.TMenubutton")
        more_button.pack(side=tk.LEFT, padx=(8, 0))
        actions_menu = self._menu(more_button)
        actions_menu.add_command(label="载入到输入框", command=load_to_input)
        actions_menu.add_command(label="删除选中", command=remove_selected)
        actions_menu.add_command(label="清空自选", command=clear_all)
        more_button.configure(menu=actions_menu)
        close_button = ttk.Button(
            buttons, text="关闭", style="Action.TButton", command=window.destroy
        )
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
                    "result": result,
                    "measurement": measurement,
                    "risk": risk_level(result),
                    "cost": held.cost if held else None,
                    "shares": held.shares if held else None,
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
            summary_metrics.append(
                {"frame": cell, "title": title, "value": value, "value_var": summary_vars[key]}
            )
        window._comparison_summary_metrics = summary_metrics

        table_card = tk.Frame(container, bg=CARD_BORDER, padx=1, pady=1)
        table_card.pack(fill=tk.BOTH, expand=True)
        headings = {
            "code": ("代码", 100),
            "name": ("名称", 120),
            "last": ("现价", 80),
            "change": ("涨跌", 80),
            "score": ("综合分", 80),
            "conf": ("把握", 70),
            "risk": ("风险", 60),
            "pos": ("建议仓位", 80),
            "cost": ("持仓成本", 90),
            "pl": ("浮动盈亏", 150),
            "hint": ("档位提示", 230),
        }
        tree = ttk.Treeview(table_card, columns=tuple(headings), show="headings", height=12)
        comparison_anchors = {
            "code": tk.W,
            "name": tk.W,
            "last": tk.E,
            "change": tk.E,
            "score": tk.E,
            "conf": tk.E,
            "risk": tk.CENTER,
            "pos": tk.E,
            "cost": tk.E,
            "pl": tk.E,
            "hint": tk.W,
        }
        for col, (title, width) in headings.items():
            tree.heading(col, text=title)
            tree.column(col, width=self._sc(width), anchor=comparison_anchors[col])
        tree.tag_configure("action_buy", background=POS_BG, foreground=POS_COLOR)
        tree.tag_configure("action_sell", background=NEG_BG, foreground=NEG_COLOR)
        tree.tag_configure("action_hold", background=HOLD_BG, foreground=FLAT_COLOR)
        for index, row in enumerate(rows):
            tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=format_comparison_row(row),
                tags=(f"action_{row.action.lower()}",),
            )
        # 11 列按 DPI 放大后总宽仍可能超出可视区——加一条横向滚动条兜底，避免任意 DPI 下右侧列被裁掉。
        vscroll = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=tree.yview)
        hscroll = ttk.Scrollbar(table_card, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Button(container, text="关闭", style="Action.TButton", command=window.destroy).pack(
            anchor=tk.E, pady=(8, 0)
        )
