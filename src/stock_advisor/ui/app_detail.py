from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ..domain.backtest import backtest_signals
from ..domain.formatting import _looks_positive, _looks_risky
from ..domain.models import LEVEL_NAMES
from ..domain.policy import position_plan, spectrum
from .theme import (
    ACCENT,
    ACCENT_SOFT,
    CARD_BG,
    CARD_BORDER,
    CONTROL_BG,
    DANGER_COLOR,
    DETAIL_NAV_SECTIONS,
    DISCLAIMER,
    INFO_WINDOW_SIZE,
    INK,
    INK_SOFT,
    MUTED_INK,
    NEG_COLOR,
    PAGE_BG,
    POS_COLOR,
    UI_FONT,
)
from .view_format import detail_line_tags
from .view_text import (
    build_backtest_text,
    build_help_sections,
    build_position_plan_text,
    build_spectrum_text,
    build_strategy_sections,
)
from .widgets import StatefulToplevel

if TYPE_CHECKING:
    from ._app_members import AppMembers as _MembersBase
else:
    _MembersBase = object


class DetailViewMixin(_MembersBase):
    """详情文本渲染 + 帮助/策略信息窗 + 强度模块文本——从 StockAdvisorApp 抽出的详情视图关注点。"""

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
        window = StatefulToplevel(self.root)
        window.title(title)
        self._center_child_window(
            window, (self._sc(INFO_WINDOW_SIZE[0]), self._sc(INFO_WINDOW_SIZE[1]))
        )
        self._apply_child_minimum(window, (720, 500))
        window.configure(bg=PAGE_BG)
        window.transient(self.root)
        self._set_window_icon(window)

        container = ttk.Frame(
            window, padding=(self._sc(18), self._sc(16), self._sc(18), self._sc(14))
        )
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container)
        header.pack(fill=tk.X, pady=(0, 12))
        logo = tk.Canvas(
            header, width=self._sc(40), height=self._sc(40), bg=PAGE_BG, highlightthickness=0
        )
        logo.pack(side=tk.LEFT, padx=(0, 10))
        self._draw_logo(logo)
        title_box = ttk.Frame(header)
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(title_box, text=title, font=(UI_FONT, 15, "bold"), foreground=INK).pack(
            anchor=tk.W
        )
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
            content,
            wrap=tk.WORD,
            borderwidth=0,
            relief=tk.FLAT,
            font=(UI_FONT, 10),
            background=CARD_BG,
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
        ttk.Button(footer, text="关闭", style="Action.TButton", command=window.destroy).pack(
            side=tk.RIGHT
        )

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
        text.tag_configure(
            "title", font=(UI_FONT, 14, "bold"), foreground=INK, spacing3=self._sc(12)
        )
        text.tag_configure(
            "body", foreground=INK_SOFT, lmargin1=0, lmargin2=0, spacing3=self._sc(7)
        )
        text.tag_configure(
            "bullet",
            foreground=INK_SOFT,
            lmargin1=self._sc(18),
            lmargin2=self._sc(30),
            spacing3=self._sc(6),
        )
        text.tag_configure(
            "number",
            foreground=ACCENT,
            lmargin1=self._sc(18),
            lmargin2=self._sc(34),
            spacing3=self._sc(6),
        )
        text.tag_configure(
            "risk",
            foreground=DANGER_COLOR,
            lmargin1=self._sc(18),
            lmargin2=self._sc(30),
            spacing3=self._sc(6),
        )
        text.tag_configure(
            "positive",
            foreground=POS_COLOR,
            lmargin1=self._sc(18),
            lmargin2=self._sc(30),
            spacing3=self._sc(6),
        )

    def _insert_info_text(self, text: tk.Text, title: str, body: str) -> None:
        text.insert(tk.END, title + "\n\n", ("title",))
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                text.insert(tk.END, "\n")
                continue
            if stripped.startswith("- "):
                tag = (
                    "risk"
                    if _looks_risky(stripped)
                    else "positive"
                    if _looks_positive(stripped)
                    else "bullet"
                )
            elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == ".":
                tag = "number"
            else:
                tag = "body"
            text.insert(tk.END, stripped + "\n", (tag,))

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
        self.detail.tag_configure(
            "headline", font=(UI_FONT, 14, "bold"), foreground=INK, spacing3=self._sc(12)
        )
        self.detail.tag_configure(
            "section",
            font=(UI_FONT, 12, "bold"),
            foreground=ACCENT,
            spacing1=self._sc(10),
            spacing3=self._sc(6),
        )
        self.detail.tag_configure("positive", foreground=POS_COLOR)
        self.detail.tag_configure("negative", foreground=NEG_COLOR)
        self.detail.tag_configure("muted", foreground=MUTED_INK)
        self.detail.tag_configure(
            "bullet", lmargin1=self._sc(16), lmargin2=self._sc(28), spacing3=self._sc(4)
        )
        self.detail.tag_configure(
            "risk",
            foreground=DANGER_COLOR,
            lmargin1=self._sc(16),
            lmargin2=self._sc(28),
            spacing3=self._sc(4),
        )

    def _insert_styled_detail(self, text: str) -> None:
        lines = text.splitlines()
        for index, line in enumerate(lines):
            self.detail.insert(tk.END, line + "\n", detail_line_tags(line, index == 0))
