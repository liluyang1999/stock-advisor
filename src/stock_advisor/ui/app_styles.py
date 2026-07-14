from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .theme import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_PRESSED,
    ACCENT_SOFT,
    ACCENT_SOFT_HOVER,
    CARD_BG,
    CARD_BORDER,
    COMMAND_BG,
    COMMAND_MUTED_INK,
    CONTROL_BG,
    CONTROL_DISABLED_BG,
    CONTROL_HOVER_BG,
    FLAT_COLOR,
    HOLD_BG,
    INK,
    INK_SOFT,
    MUTED_INK,
    MUTED_LIGHT,
    NEG_BG,
    NEG_COLOR,
    PAGE_BG,
    POS_BG,
    POS_COLOR,
    SCROLLBAR_ACTIVE_BG,
    SCROLLBAR_BG,
    SCROLLBAR_PRESSED_BG,
    SELECTION_BG,
    SURFACE_ALT,
    TABLE_HEADER_BG,
    UI_FONT,
    WINDOW_ALPHA,
)


class StyleMixin:
    """ttk 样式/主题配置 + 毛玻璃 + 表格行标签配色——从 StockAdvisorApp 抽出的视觉样式关注点。"""

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

    def _configure_tree_tags(self) -> None:
        self.tree.tag_configure("risk_low")
        self.tree.tag_configure("risk_medium")
        self.tree.tag_configure("risk_high")
        self.tree.tag_configure("action_buy", background=POS_BG, foreground=POS_COLOR)
        self.tree.tag_configure("action_hold", background=HOLD_BG, foreground=FLAT_COLOR)
        self.tree.tag_configure("action_sell", background=NEG_BG, foreground=NEG_COLOR)
