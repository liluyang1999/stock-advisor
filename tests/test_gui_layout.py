import os
import queue
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from stock_advisor.data.sample_data import make_sample_recommendation
from stock_advisor.ui.app import StockAdvisorApp
from stock_advisor.ui.layout import compute_scaled_minimum
from stock_advisor.ui.theme import (
    CHILD_WINDOW_WORKAREA_MARGIN,
    CONTENT_MARGIN,
    MAIN_MIN_SIZE,
    MAX_CONTENT_WIDTH,
    MONITOR_INTERVAL_MS,
    TABLE_EMPTY_VISIBLE_ROWS,
    TABLE_MAX_VISIBLE_ROWS,
    TABLE_MIN_VISIBLE_ROWS,
)


class _FakeEvent:
    def __init__(self, width):
        self.width = width


def _direct_child(widget, ancestor):
    """走 widget 的 master 链，返回 ancestor 的那个直属子级（内含 widget）；
    若 widget 根本不在 ancestor 之下则返回 None。用于断言"合并进同一张内层卡片"，
    不必假设具体嵌套层数。"""
    node = widget
    while node is not None:
        if node.master is ancestor:
            return node
        node = node.master
    return None


def _canvas_texts(canvas):
    """收集画布上所有 text 类型 item 的文本内容，用于按可见文案断言——不依赖 tag，
    覆盖 _draw_visual（未打 tag）与 _draw_empty_visual（打 tag）两种绘制路径。"""
    return [
        canvas.itemcget(item, "text") for item in canvas.find_all() if canvas.type(item) == "text"
    ]


def _find_widget_with_textvariable(widget, variable):
    """深度优先遍历 widget 子树，返回第一个 -textvariable 绑定到 variable 的控件；
    不支持该选项的控件（Frame/Canvas 等）会抛 TclError，忽略后继续遍历子级。用于断言
    某个 StringVar 真的挂在一个可见控件上，而不仅仅是在 Python 侧被 set()。"""
    target = str(variable)
    try:
        if str(widget.cget("textvariable")) == target:
            return widget
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        found = _find_widget_with_textvariable(child, variable)
        if found is not None:
            return found
    return None


class _HighDpiStockAdvisorApp(StockAdvisorApp):
    """250% DPI 桩：让 self._ui_scale 在 _build_ui() 之前就以 2.5 生效，
    用于验证构建期读取的固定像素尺寸（画布高、wraplength、length…）确实随之放大。"""

    def _tk_scaling(self, window):
        return 3.3366


class GuiLayoutTests(unittest.TestCase):
    def setUp(self):
        # 隔离持久化：指向临时配置文件，避免污染真实 %APPDATA% 或测试间互相干扰。
        self._cfg_dir = tempfile.mkdtemp()
        os.environ["STOCK_ADVISOR_CONFIG"] = str(Path(self._cfg_dir) / "config.json")
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = StockAdvisorApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        self.root.destroy()
        os.environ.pop("STOCK_ADVISOR_CONFIG", None)
        shutil.rmtree(self._cfg_dir, ignore_errors=True)

    def test_detail_view_resets_to_top_when_content_changes(self):
        self.app._set_detail("旧内容\n" + "\n".join(f"第 {index} 行" for index in range(60)))
        self.app.detail.yview_moveto(1.0)

        self.app._set_detail("顶部标题\n正文")
        self.root.update_idletasks()

        self.assertEqual(self.app.detail.get("1.0", "1.end"), "顶部标题")
        self.assertLessEqual(self.app.detail.yview()[0], 0.01)

    def test_result_table_height_is_compact_for_small_batches(self):
        self.app._refresh_table_height(4)

        self.assertTrue(hasattr(self.app, "table_card"))
        self.assertEqual(self.app.table_card.winfo_manager(), "pack")
        self.assertEqual(int(self.app.tree.cget("height")), TABLE_MIN_VISIBLE_ROWS)

    def test_empty_result_table_uses_shorter_placeholder_height(self):
        self.assertLess(int(self.app.tree.cget("height")), TABLE_MIN_VISIBLE_ROWS)

        self.app._refresh_table_height(0)

        self.assertTrue(hasattr(self.app, "table_card"))
        self.assertEqual(self.app.table_card.winfo_manager(), "")
        self.assertEqual(int(self.app.tree.cget("height")), TABLE_EMPTY_VISIBLE_ROWS)
        self.assertEqual(TABLE_EMPTY_VISIBLE_ROWS, 1)

    def test_result_table_height_is_bounded_for_large_batches(self):
        self.app._refresh_table_height(30)

        self.assertEqual(int(self.app.tree.cget("height")), TABLE_MAX_VISIBLE_ROWS)

    def test_visual_dashboard_has_enough_room_for_factor_rows(self):
        self.assertGreaterEqual(int(self.app.visual.cget("height")), 300)

    def test_primary_workflow_starts_within_first_viewport(self):
        base = self.app.page_canvas.winfo_rooty()
        input_y = self.app.symbol_input.winfo_rooty() - base
        table_y = self.app.tree.winfo_rooty() - base
        self.assertLessEqual(input_y, 310)
        self.assertLessEqual(table_y, 600)

    def test_header_and_mode_controls_remain_within_first_work_area(self):
        base = self.app.page_canvas.winfo_rooty()
        input_y = self.app.symbol_input.winfo_rooty() - base
        table_y = self.app.tree.winfo_rooty() - base

        self.assertTrue(hasattr(self.app, "logo_canvas"))
        self.assertEqual(int(self.app.logo_canvas.cget("width")), 48)
        self.assertEqual(int(self.app.logo_canvas.cget("height")), 48)
        self.assertLessEqual(input_y, 300)
        self.assertLessEqual(table_y, 680)

    def test_main_window_minimum_is_scaled_and_clamped_to_work_area(self):
        from stock_advisor.ui.layout import compute_scaled_minimum
        from stock_advisor.ui.theme import WINDOW_WORKAREA_MARGIN

        self.assertGreaterEqual(MAIN_MIN_SIZE[1], 680)
        _left, _top, work_width, work_height = self.app._screen_work_area(self.root)
        frame_width, frame_height = self.app._frame_extents(self.root)
        expected = compute_scaled_minimum(
            work_width,
            work_height,
            self.app._ui_scale,
            MAIN_MIN_SIZE[0],
            MAIN_MIN_SIZE[1],
            margin=WINDOW_WORKAREA_MARGIN,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        self.assertEqual(self.root.minsize(), expected)

    def test_header_help_actions_are_grouped_under_single_menu(self):
        self.assertTrue(hasattr(self.app, "header_help_button"))
        self.assertTrue(hasattr(self.app, "header_help_menu"))
        self.assertEqual(self.app.header_help_button.cget("text"), "说明")

        header_buttons = [
            widget
            for widget in self.app.header_actions.winfo_children()
            if isinstance(widget, ttk.Button)
        ]
        header_menus = [
            widget
            for widget in self.app.header_actions.winfo_children()
            if isinstance(widget, ttk.Menubutton)
        ]
        self.assertEqual(header_buttons, [])
        self.assertEqual([button.cget("text") for button in header_menus], ["说明"])
        self.assertLessEqual(self.app.header_help_button.winfo_reqwidth(), 112)

        menu = self.app.header_help_menu
        labels = [menu.entrycget(index, "label") for index in range(menu.index("end") + 1)]
        self.assertEqual(labels, ["使用说明", "策略说明"])

    def test_mode_and_strength_share_one_responsive_control_ribbon(self):
        base = self.app.page_canvas.winfo_rooty()
        input_y = self.app.symbol_input.winfo_rooty() - base
        table_y = self.app.tree.winfo_rooty() - base

        self.assertTrue(hasattr(self.app, "mode_control_shell"))
        self.assertTrue(hasattr(self.app, "mode_tab_group"))
        self.assertTrue(hasattr(self.app, "level_control_group"))
        self.assertTrue(
            all(button.master is self.app.mode_tab_group for button in self.app._tab_buttons)
        )
        self.assertIs(self.app.mode_tab_group.master.master, self.app.mode_primary_row)
        self.assertIs(self.app.level_control_group.master, self.app.mode_primary_row)
        self.assertIs(self.app.mode_primary_row.master, self.app.mode_control_body)
        self.assertIs(self.app.level_hint_label.master, self.app.mode_control_body)
        self.assertLessEqual(input_y, 310)
        self.assertLessEqual(table_y, 720)

    def test_control_ribbon_uses_spacious_primary_and_summary_rows(self):
        self.assertEqual(self.app.level_control_group.winfo_y(), self.app.mode_row.winfo_y())
        selector = self.app.level_buttons[0].master
        selector_right = selector.winfo_x() + selector.winfo_width()

        self.assertLessEqual(selector_right, self.app.level_control_group.winfo_width())
        self.assertGreater(self.app.level_hint_label.winfo_y(), self.app.mode_primary_row.winfo_y())
        self.assertGreaterEqual(self.app.mode_control_shell.winfo_height(), 104)
        self.assertLessEqual(self.app.mode_control_shell.winfo_height(), 170)

    def test_control_ribbon_keeps_each_heading_attached_to_its_selector(self):
        mode_label = next(
            widget
            for widget in self.app.mode_row.winfo_children()
            if isinstance(widget, tk.Label) and widget.cget("text") == "工作模式"
        )
        level_label = next(
            widget
            for widget in self.app.level_control_group.winfo_children()
            if isinstance(widget, tk.Label) and widget.cget("text") == "决策强度"
        )
        level_selector = self.app.level_buttons[0].master

        self.assertEqual(self.app.mode_tab_group.pack_info().get("side"), "left")
        self.assertEqual(level_selector.pack_info().get("side"), "left")

        mode_gap = self.app.mode_tab_group.winfo_x() - (
            mode_label.winfo_x() + mode_label.winfo_width()
        )
        level_gap = level_selector.winfo_x() - (level_label.winfo_x() + level_label.winfo_width())
        for gap in (mode_gap, level_gap):
            self.assertGreaterEqual(gap, self.app._sc(8))
            self.assertLessEqual(gap, self.app._sc(16))

        mode_label_center = mode_label.winfo_rooty() + mode_label.winfo_height() / 2
        mode_selector_center = (
            self.app.mode_tab_group.winfo_rooty() + self.app.mode_tab_group.winfo_height() / 2
        )
        level_label_center = level_label.winfo_rooty() + level_label.winfo_height() / 2
        level_selector_center = level_selector.winfo_rooty() + level_selector.winfo_height() / 2
        self.assertLessEqual(abs(mode_label_center - mode_selector_center), self.app._sc(2))
        self.assertLessEqual(abs(level_label_center - level_selector_center), self.app._sc(2))
        self.assertLessEqual(
            abs(self.app.mode_tab_group.winfo_height() - level_selector.winfo_height()),
            self.app._sc(2),
        )

    def test_control_ribbon_selector_heights_stay_equal_at_high_dpi(self):
        root2 = tk.Tk()
        root2.withdraw()
        try:
            app2 = _HighDpiStockAdvisorApp(root2)
            root2.update_idletasks()
            level_selector = app2.level_buttons[0].master

            self.assertEqual(app2._ui_scale, 2.5)
            self.assertLessEqual(
                abs(app2.mode_tab_group.winfo_height() - level_selector.winfo_height()),
                app2._sc(2),
            )
        finally:
            root2.destroy()

    def test_unified_control_bar_keeps_strength_selector_visible(self):
        labels = [
            widget
            for widget in self.app.level_control_group.winfo_children()
            if isinstance(widget, tk.Label)
        ]

        self.assertEqual([label.cget("text") for label in labels], ["决策强度"])
        self.assertTrue(all(int(button.cget("width")) <= 8 for button in self.app.level_buttons))
        self.assertTrue(all(int(button.cget("width")) <= 12 for button in self.app._tab_buttons))

    def test_result_status_and_progress_share_the_two_row_toolbar(self):
        base = self.app.page_canvas.winfo_rooty()
        table_y = self.app.tree.winfo_rooty() - base

        self.assertIs(self.app.progress.master, self.app.results_context_row)
        self.assertTrue(hasattr(self.app, "summary_label"))
        self.assertIs(self.app.summary_label.master, self.app.results_context_row)
        self.assertLessEqual(table_y, 720)

    def test_overview_uses_the_context_row_inside_the_status_bar(self):
        outer = self.app.results_toolbar.master

        self.assertIs(self.app.status_bar, self.app.results_toolbar)
        self.assertIs(self.app._overview_label.master, self.app.results_context_row)
        self.assertIn(self.app._overview_label, self.app.results_context_row.pack_slaves())
        self.assertIn(self.app.results_context_row, self.app.results_toolbar.pack_slaves())
        self.assertNotIn(self.app._overview_label, outer.pack_slaves())

        self.assertGreater(
            self.app.results_context_row.winfo_y(), self.app.results_action_row.winfo_y()
        )

        self.assertEqual(
            str(self.app._overview_label.cget("textvariable")), str(self.app.overview_var)
        )

    def test_results_toolbar_uses_two_rows_so_overview_is_not_clipped(self):
        self.root.geometry("1000x680+0+0")
        self.app._on_canvas_configure(_FakeEvent(1000))
        self.root.update_idletasks()

        self.assertIs(self.app.results_action_row.master, self.app.results_toolbar)
        self.assertIs(self.app.results_context_row.master, self.app.results_toolbar)
        self.assertIs(self.app._overview_label.master, self.app.results_context_row)
        self.assertGreater(
            self.app.results_context_row.winfo_y(), self.app.results_action_row.winfo_y()
        )
        self.assertGreaterEqual(
            self.app._overview_label.winfo_width(), self.app._overview_label.winfo_reqwidth()
        )

    def test_result_progress_is_visible_only_while_running(self):
        self.assertEqual(self.app.progress.winfo_manager(), "")

        self.app._set_running(True)
        self.root.update_idletasks()

        self.assertEqual(self.app.progress.winfo_manager(), "pack")

        self.app._set_running(False)
        self.root.update_idletasks()

        self.assertEqual(self.app.progress.winfo_manager(), "")

    def test_stop_controls_are_visible_only_while_running(self):
        self.assertEqual(self.app.stop_button.winfo_manager(), "")
        self.assertEqual(self.app.screen_stop_button.winfo_manager(), "")

        self.app._set_running(True)
        self.root.update_idletasks()

        self.assertEqual(self.app.stop_button.winfo_manager(), "pack")
        self.assertEqual(self.app.screen_stop_button.winfo_manager(), "pack")

        self.app._set_running(False)
        self.root.update_idletasks()

        self.assertEqual(self.app.stop_button.winfo_manager(), "")
        self.assertEqual(self.app.screen_stop_button.winfo_manager(), "")

    def test_individual_input_secondary_tools_are_grouped_under_menu(self):
        self.assertEqual(
            [button.cget("text") for button in self.app.input_primary_buttons], ["开始分析", "停止"]
        )
        self.assertEqual(self.app.input_tools_button.cget("text"), "输入工具")
        self.assertLessEqual(self.app.input_tools_button.winfo_reqwidth(), 112)

        menu = self.app.input_tools_menu
        labels = [menu.entrycget(index, "label") for index in range(menu.index("end") + 1)]
        self.assertEqual(labels, ["整理代码", "示例", "清空"])

    def test_individual_input_uses_unified_command_panel(self):
        from stock_advisor.ui.theme import CARD_BORDER

        self.assertTrue(hasattr(self.app, "input_panel_shell"))
        self.assertEqual(str(self.app.input_panel_shell.cget("background")), CARD_BORDER)
        self.assertIs(self.app.input_panel_body.master, self.app.input_panel_shell)
        self.assertIs(self.app.symbol_input_holder.master, self.app.input_panel_body)
        self.assertIs(self.app.input_action_frame.master, self.app.input_panel_body)
        self.assertEqual(self.app.symbol_input_holder.pack_info().get("side"), "left")
        self.assertEqual(self.app.input_action_frame.pack_info().get("side"), "right")
        self.assertEqual(self.app.input_context_frame.pack_info().get("side"), "top")
        self.assertEqual(self.app.input_context_divider.pack_info().get("fill"), "x")
        self.assertTrue(hasattr(self.app, "input_panel_divider"))
        self.assertIs(self.app.input_panel_divider.master, self.app.input_panel_body)
        self.assertEqual(self.app.input_panel_divider.pack_info().get("side"), "right")
        self.assertLessEqual(int(self.app.input_panel_divider.cget("width")), 1)

    def test_individual_input_actions_stay_inside_panel_width(self):
        self.root.geometry("1376x633+0+0")
        self.app._on_canvas_configure(_FakeEvent(1376))
        self.root.update_idletasks()

        panel_right = (
            self.app.input_panel_body.winfo_rootx() + self.app.input_panel_body.winfo_width()
        )
        for widget in (self.app.analyze_button, self.app.input_tools_button):
            with self.subTest(widget=widget.cget("text")):
                self.assertTrue(widget.winfo_ismapped())
                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), panel_right)

    def test_individual_input_actions_use_spacious_row(self):
        base = self.app.page_canvas.winfo_rooty()
        table_y = self.app.tree.winfo_rooty() - base

        action_widgets = [self.app.analyze_button, self.app.input_tools_button]
        self.assertTrue(all(widget.pack_info().get("side") == "left" for widget in action_widgets))
        self.assertGreaterEqual(self.app.input_action_frame.winfo_height(), 44)
        self.assertGreaterEqual(self.app.input_panel_shell.winfo_height(), 118)
        self.assertLessEqual(self.app.input_panel_shell.winfo_height(), 190)
        self.assertLessEqual(table_y, 720)

    def test_tab_bar_has_individual_and_screener_segments(self):
        labels = [button.cget("text") for button in self.app._tab_buttons]
        self.assertEqual(labels, ["个股分析", "全市场选股"])

    def test_selected_tab_keeps_geometry_only_color_changes(self):
        from stock_advisor.ui.theme import COMMAND_SELECTED_BG

        # 自绘分段选项卡：选中只改配色不改尺寸（两胶囊 padding/字体一致 → 天然等尺寸）。
        buttons = self.app._tab_buttons
        self.assertEqual(buttons[0].cget("padx"), buttons[1].cget("padx"))
        self.assertEqual(buttons[0].cget("pady"), buttons[1].cget("pady"))
        self.app._select_tab(1)
        self.assertEqual(self.app._active_tab, 1)
        self.assertEqual(str(buttons[1].cget("bg")).lower(), COMMAND_SELECTED_BG.lower())
        self.assertNotEqual(str(buttons[0].cget("bg")).lower(), COMMAND_SELECTED_BG.lower())
        # padding 不因选中变化
        self.assertEqual(buttons[0].cget("padx"), buttons[1].cget("padx"))

    def test_screener_exposes_six_presets_and_controls(self):
        self.assertEqual(len(self.app.preset_buttons), 6)
        self.assertTrue(hasattr(self.app, "screen_button"))
        self.assertTrue(hasattr(self.app, "tunable_frame"))
        # 默认选中第一个预设，渲染出可微调参数（含 TopN）
        self.assertIn("top_n", self.app.tunable_vars)

    def test_screener_presets_use_spacious_radio_buttons(self):
        from stock_advisor.domain.presets import PRESETS
        from stock_advisor.ui.theme import ACCENT

        buttons = list(self.app.preset_buttons.values())

        self.assertEqual(len(buttons), len(PRESETS))
        self.assertTrue(all(isinstance(button, tk.Radiobutton) for button in buttons))
        self.assertTrue(all(int(button.cget("width")) <= 14 for button in buttons))
        self.assertTrue(all(int(button.cget("pady")) >= 10 for button in buttons))

        self.app._select_preset("value_blue")
        self.root.update_idletasks()

        self.assertEqual(self.app.preset_buttons["value_blue"].cget("bg"), ACCENT)
        self.assertNotEqual(self.app.preset_buttons[PRESETS[0].key].cget("bg"), ACCENT)

    def test_screener_deep_analysis_uses_compact_toggle(self):
        from stock_advisor.ui.theme import ACCENT

        self.assertTrue(hasattr(self.app, "deep_toggle_button"))
        self.assertFalse(bool(int(self.app.deep_toggle_button.cget("indicatoron"))))
        self.assertLessEqual(int(self.app.deep_toggle_button.cget("width")), 12)
        self.assertIn("开", self.app.deep_toggle_button.cget("text"))
        self.assertEqual(self.app.deep_toggle_button.cget("bg"), ACCENT)

        self.app.deep_toggle_button.invoke()
        self.root.update_idletasks()

        self.assertFalse(self.app.deep_var.get())
        self.assertIn("关", self.app.deep_toggle_button.cget("text"))
        self.assertNotEqual(self.app.deep_toggle_button.cget("bg"), ACCENT)

    def test_selecting_preset_rerenders_tunables(self):
        self.app._select_preset("value_blue")
        self.assertEqual(self.app.active_preset_key, "value_blue")
        self.assertIn("pe_max", self.app.tunable_vars)

    def test_preset_selection_reports_config_save_failure_without_dialog(self):
        from stock_advisor.ui import app as app_module

        errors = []
        original_save = app_module.store.save_config
        original_showerror = app_module.messagebox.showerror
        app_module.store.save_config = lambda *_args, **_kwargs: False
        app_module.messagebox.showerror = lambda *args, **kwargs: errors.append((args, kwargs))
        try:
            self.app._select_preset("value_blue")
        finally:
            app_module.store.save_config = original_save
            app_module.messagebox.showerror = original_showerror

        self.assertEqual(errors, [])
        self.assertIn("未保存", self.app.status_var.get())

    def test_content_band_centers_page_window_with_even_margins(self):
        wide = MAX_CONTENT_WIDTH + 400  # 宽于上限，内容收窄并居中
        self.app._on_canvas_configure(_FakeEvent(wide))
        self.root.update_idletasks()
        x, _y = self.app.page_canvas.coords(self.app.page_window)
        width = int(self.app.page_canvas.itemcget(self.app.page_window, "width"))
        self.assertEqual(width, MAX_CONTENT_WIDTH)
        self.assertEqual(int(x), (wide - MAX_CONTENT_WIDTH) // 2)

    def test_content_band_shrinks_with_even_margins_on_narrow_window(self):
        self.app._on_canvas_configure(_FakeEvent(800))
        x, _y = self.app.page_canvas.coords(self.app.page_window)
        width = int(self.app.page_canvas.itemcget(self.app.page_window, "width"))
        self.assertEqual(width, 800 - 2 * CONTENT_MARGIN)
        self.assertEqual(int(x), CONTENT_MARGIN)

    def test_actual_content_has_equal_horizontal_and_top_outer_margins(self):
        self.root.geometry("1200x800+0+0")
        self.root.update_idletasks()
        canvas_width = self.app.page_canvas.winfo_width()
        self.app._on_canvas_configure(_FakeEvent(canvas_width))
        self.root.update_idletasks()

        left = self.app.header_frame.winfo_rootx() - self.app.page_canvas.winfo_rootx()
        top = self.app.header_frame.winfo_rooty() - self.app.page_canvas.winfo_rooty()
        right = canvas_width - left - self.app.header_frame.winfo_width()
        self.assertLessEqual(abs(left - right), 1)
        self.assertLessEqual(abs(left - top), 1)

    def test_add_recommendation_inserts_row_and_shows_detail(self):
        rec = make_sample_recommendation(deep=True)
        self.app._add_recommendation(rec, done=1, total=1)
        children = self.app.tree.get_children()
        self.assertEqual(len(children), 1)
        self.app.tree.selection_set(children[0])
        self.app._show_selected_detail()
        self.assertIn("选股入围", self.app.detail.get("1.0", tk.END))

    def test_add_snapshot_only_recommendation_shows_snapshot_detail(self):
        rec = make_sample_recommendation(deep=False)
        self.app._add_recommendation(rec, done=1, total=1)
        children = self.app.tree.get_children()
        self.app.tree.selection_set(children[0])
        self.app._show_selected_detail()
        detail = self.app.detail.get("1.0", tk.END)
        self.assertIn("快照特征", detail)

    def test_snapshot_only_selection_keeps_kline_empty_state(self):
        rec = make_sample_recommendation(deep=False)
        self.app._add_recommendation(rec, done=1, total=1)
        children = self.app.tree.get_children()

        self.app.tree.selection_set(children[0])
        self.app._show_selected_detail()

        self.assertTrue(self.app.kline_canvas.find_withtag("empty_kline_candles"))
        self.assertFalse(getattr(self.app, "_kline_state", {}).get("layout"))

    def test_snapshot_only_results_can_be_copied_and_exported(self):
        # copy_results/export_csv now live in app_results; patch messagebox/filedialog there.
        from stock_advisor.ui import app_results as app_module
        from stock_advisor.ui.view_format import snapshot_display

        rec = make_sample_recommendation(deep=False)
        self.app._add_recommendation(rec, done=1, total=1)
        export_path = Path(self._cfg_dir) / "snapshot-results.csv"
        info_calls = []
        original_showinfo = app_module.messagebox.showinfo
        original_saveas = app_module.filedialog.asksaveasfilename
        app_module.messagebox.showinfo = lambda *args, **kwargs: info_calls.append((args, kwargs))
        app_module.filedialog.asksaveasfilename = lambda **kwargs: str(export_path)
        try:
            self.app.copy_results()
            try:
                copied = self.root.clipboard_get()
            except tk.TclError:
                copied = ""
            self.app.export_csv()
        finally:
            app_module.messagebox.showinfo = original_showinfo
            app_module.filedialog.asksaveasfilename = original_saveas

        self.assertFalse(info_calls)
        self.assertIn(snapshot_display(rec.snapshot), copied)
        self.assertIn("快照", copied)
        exported = export_path.read_text(encoding="utf-8-sig")
        self.assertIn(snapshot_display(rec.snapshot), exported)
        self.assertIn("快照", exported)

    def test_export_csv_reports_unwritable_path_without_crashing(self):
        # export_csv now lives in app_results; patch messagebox/filedialog there.
        from stock_advisor.ui import app_results as app_module

        rec = make_sample_recommendation(deep=False)
        self.app._add_recommendation(rec, done=1, total=1)
        error_calls = []
        original_showerror = app_module.messagebox.showerror
        original_saveas = app_module.filedialog.asksaveasfilename
        app_module.messagebox.showerror = lambda *args, **kwargs: error_calls.append((args, kwargs))
        app_module.filedialog.asksaveasfilename = lambda **kwargs: self._cfg_dir
        try:
            try:
                self.app.export_csv()
            except OSError as exc:
                self.fail(f"export_csv leaked file write error instead of showing UI error: {exc}")
        finally:
            app_module.messagebox.showerror = original_showerror
            app_module.filedialog.asksaveasfilename = original_saveas

        self.assertTrue(error_calls)
        self.assertIn("CSV", error_calls[0][0][0])

    def test_copy_results_reports_clipboard_failure_without_crashing(self):
        from stock_advisor.ui import app as app_module

        rec = make_sample_recommendation(deep=False)
        self.app._add_recommendation(rec, done=1, total=1)
        error_calls = []
        original_showerror = app_module.messagebox.showerror
        original_clear = self.app.root.clipboard_clear
        app_module.messagebox.showerror = lambda *args, **kwargs: error_calls.append((args, kwargs))
        self.app.root.clipboard_clear = lambda: (_ for _ in ()).throw(tk.TclError("clipboard busy"))
        try:
            try:
                self.app.copy_results()
            except tk.TclError as exc:
                self.fail(f"copy_results leaked clipboard error instead of showing UI error: {exc}")
        finally:
            app_module.messagebox.showerror = original_showerror
            self.app.root.clipboard_clear = original_clear

        self.assertTrue(error_calls)
        self.assertIn("复制", error_calls[0][0][0])

    def test_copy_current_detail_reports_clipboard_failure_without_crashing(self):
        from stock_advisor.ui import app as app_module

        self.app._set_detail("detail text")
        error_calls = []
        original_showerror = app_module.messagebox.showerror
        original_clear = self.app.root.clipboard_clear
        app_module.messagebox.showerror = lambda *args, **kwargs: error_calls.append((args, kwargs))
        self.app.root.clipboard_clear = lambda: (_ for _ in ()).throw(tk.TclError("clipboard busy"))
        try:
            try:
                self.app.copy_current_detail()
            except tk.TclError as exc:
                self.fail(
                    f"copy_current_detail leaked clipboard error instead of showing UI error: {exc}"
                )
        finally:
            app_module.messagebox.showerror = original_showerror
            self.app.root.clipboard_clear = original_clear

        self.assertTrue(error_calls)
        self.assertIn("复制", error_calls[0][0][0])

    def test_failed_result_selection_keeps_kline_empty_state(self):
        self.app.tree.insert(
            "",
            tk.END,
            iid="fail-row",
            values=("SH.600000", "", "失败", "", "", "", "", "高"),
            tags=("risk_high",),
        )

        self.app.tree.selection_set("fail-row")
        self.app._show_selected_detail()

        self.assertTrue(self.app.kline_canvas.find_withtag("empty_kline_candles"))
        self.assertFalse(getattr(self.app, "_kline_state", {}).get("layout"))

    def test_strength_bar_and_new_canvases_exist(self):
        self.assertTrue(hasattr(self.app, "level_var"))
        self.assertTrue(hasattr(self.app, "spectrum_canvas"))
        self.assertTrue(hasattr(self.app, "kline_canvas"))
        self.assertEqual(self.app.level_var.get(), 3)

    def test_strength_selector_uses_five_compact_level_buttons(self):
        from stock_advisor.ui.theme import COMMAND_SELECTED_BG
        from stock_advisor.ui.view_text import level_summary

        self.assertTrue(hasattr(self.app, "level_buttons"))
        self.assertEqual(
            [button.cget("text") for button in self.app.level_buttons],
            ["L1稳健", "L2稳进", "L3标准", "L4积极", "L5激进"],
        )

        self.app.level_buttons[4].invoke()
        self.root.update_idletasks()

        self.assertEqual(self.app.level_var.get(), 5)
        self.assertEqual(self.app.level_label_var.get(), level_summary(5))
        self.assertEqual(self.app.level_buttons[4].cget("bg"), COMMAND_SELECTED_BG)
        self.assertEqual(self.app.level_buttons[4].cget("selectcolor"), COMMAND_SELECTED_BG)

    def test_control_bar_shows_level_summary_label(self):
        # Task 6: level_label_var 此前只在 Python 侧被 _on_level_change set()，未绑定任何
        # 控件——用户切档看不到"标准档 · 买入线 +25 / 卖出线 -25 · ..."这句摘要。这里断言
        # 控制栏内确实存在一个可见的 -textvariable 绑定控件，而不仅是变量本身有值。
        from stock_advisor.ui.view_text import level_summary

        label = _find_widget_with_textvariable(
            self.app.mode_control_shell, self.app.level_label_var
        )
        self.assertIsNotNone(label, "决策强度控制栏内应有一个绑定 level_label_var 的可见 Label")
        self.assertTrue(label.winfo_ismapped())

        initial_text = self.app.level_label_var.get()
        self.assertTrue(initial_text)
        self.assertEqual(initial_text, level_summary(self.app.level_var.get()))

        self.app.level_var.set(1)
        self.app._on_level_change()
        self.root.update_idletasks()

        updated_text = self.app.level_label_var.get()
        self.assertNotEqual(updated_text, initial_text)
        self.assertEqual(updated_text, level_summary(1))
        self.assertIn("稳健", updated_text)

    def test_strength_summary_uses_a_full_width_second_line_at_minimum_width(self):
        self.root.geometry("1000x680+0+0")
        self.app._on_canvas_configure(_FakeEvent(1000))
        self.root.update_idletasks()

        self.assertIs(self.app.level_hint_label.master, self.app.mode_control_body)
        self.assertEqual(self.app.level_hint_label.pack_info().get("fill"), "x")
        self.assertGreater(self.app.level_hint_label.winfo_y(), self.app.mode_row.winfo_y())
        self.assertGreaterEqual(
            self.app.level_hint_label.winfo_width(), self.app.level_hint_label.winfo_reqwidth()
        )

    def test_visual_dashboard_and_kline_share_one_workspace_row(self):
        workspace = getattr(self.app, "visual_workspace", None)

        self.assertIsNotNone(workspace)
        self.assertIs(self.app.visual.master.master, workspace)
        self.assertIs(self.app.kline_canvas.master.master, workspace)
        self.assertEqual(self.app.visual.master.pack_info().get("side"), "left")
        self.assertEqual(self.app.kline_canvas.master.pack_info().get("side"), "left")
        self.assertEqual(
            int(self.app.visual.cget("height")), int(self.app.kline_canvas.cget("height"))
        )

    def test_visual_and_kline_share_one_bordered_analysis_panel(self):
        from stock_advisor.ui.theme import CARD_BORDER

        self.assertTrue(hasattr(self.app, "visual_workspace_shell"))
        self.assertEqual(str(self.app.visual_workspace_shell.cget("background")), CARD_BORDER)
        self.assertIs(self.app.visual_workspace.master, self.app.visual_workspace_shell)
        self.assertIs(self.app.visual.master.master, self.app.visual_workspace)
        self.assertIs(self.app.kline_canvas.master.master, self.app.visual_workspace)
        self.assertTrue(hasattr(self.app, "visual_workspace_divider"))
        self.assertEqual(self.app.visual_workspace_divider.pack_info().get("side"), "left")
        self.assertLessEqual(int(self.app.visual_workspace_divider.cget("width")), 1)

    def test_visual_workspace_starts_without_excess_vertical_chrome(self):
        self.root.geometry("1365x680+0+0")
        self.app._on_canvas_configure(_FakeEvent(1365))
        self.root.update_idletasks()

        base = self.app.page_canvas.winfo_rooty()
        visual_y = self.app.visual_workspace_shell.winfo_rooty() - base

        self.assertLessEqual(visual_y, 380)

    def test_visual_workspace_draws_within_visible_half_width_canvases(self):
        self._inject_sample()
        self.app._show_selected_detail()
        self.root.update_idletasks()

        for canvas in (self.app.visual, self.app.kline_canvas):
            bbox = canvas.bbox("all")
            self.assertIsNotNone(bbox)
            self.assertGreater(canvas.winfo_width(), 1)
            self.assertLessEqual(bbox[2], canvas.winfo_width() + 2)

    def test_kline_never_draws_past_actual_canvas_at_minimum_width(self):
        self.root.geometry("1000x680+0+0")
        self.app._on_canvas_configure(_FakeEvent(1000))
        self._inject_sample()
        self.app._show_selected_detail()
        self.root.update_idletasks()

        bbox = self.app.kline_canvas.bbox("all")
        self.assertIsNotNone(bbox)
        assert bbox is not None
        self.assertGreater(self.app.kline_canvas.winfo_width(), 1)
        self.assertLessEqual(bbox[0], self.app.kline_canvas.winfo_width())
        self.assertLessEqual(bbox[2], self.app.kline_canvas.winfo_width() + 2)

    def test_results_area_collapses_to_single_prompt_before_first_result(self):
        # 未分析时结论卡/价格卡/详情卡应折叠，只留一行提示——取代原先约 600px 的假占位。
        self.assertFalse(self.app._results_expanded)
        self.assertEqual(self.app.results_placeholder.winfo_manager(), "pack")
        self.assertEqual(self.app.insight_strip.winfo_manager(), "")
        self.assertEqual(self.app.visual_workspace_shell.winfo_manager(), "")
        self.assertEqual(self.app.detail_panel_shell.winfo_manager(), "")

        self.app._set_results_expanded(True)
        self.root.update_idletasks()

        self.assertTrue(self.app._results_expanded)
        self.assertEqual(self.app.results_placeholder.winfo_manager(), "")
        self.assertEqual(self.app.insight_strip.winfo_manager(), "pack")
        self.assertEqual(self.app.visual_workspace_shell.winfo_manager(), "pack")
        self.assertEqual(self.app.detail_panel_shell.winfo_manager(), "pack")

    def test_empty_visual_workspace_uses_refined_placeholders(self):
        # P3 起，未分析时不再自动预绘这些占位图形（见
        # test_results_area_collapses_to_single_prompt_before_first_result）；
        # 这里改为显式展开后直接调用 _draw_empty_visual/_draw_empty_kline，验证这两个
        # "仍会在展开但暂无数据时使用"的绘制函数本身依旧产出预期的精修占位标签。
        # Task 3b 起，visual 面板只剩"判断拆解"占位条：徽标已删除，不再打
        # empty_visual_badge tag（见 test_empty_visual_only_shows_factor_breakdown_placeholder）。
        self.app._set_results_expanded(True)
        self.app._draw_empty_visual()
        self.app._draw_empty_kline()
        self.root.update_idletasks()

        self.assertFalse(self.app.visual.find_withtag("empty_visual_badge"))
        self.assertTrue(self.app.visual.find_withtag("empty_visual_bars"))
        self.assertTrue(self.app.kline_canvas.find_withtag("empty_kline_grid"))
        self.assertTrue(self.app.kline_canvas.find_withtag("empty_kline_candles"))
        self.assertFalse(getattr(self.app, "_kline_state", {}).get("layout"))

    def test_empty_visual_only_shows_factor_breakdown_placeholder(self):
        # Task 3b：无结果占位态同步瘦身——徽标(empty_visual_badge)、"今日结论"标题+
        # 叙述文案(empty_visual_text)、三项指标占位全部删除，只保留"判断拆解"占位条
        # （复用同款视觉但用假比例绘制，因为这条路径没有真实 AnalysisResult 可读）。
        self.app._set_results_expanded(True)
        self.app._draw_empty_visual("图形面板暂不可用")
        self.root.update_idletasks()

        self.assertFalse(self.app.visual.find_withtag("empty_visual_badge"))
        self.assertFalse(self.app.visual.find_withtag("empty_visual_text"))
        texts = _canvas_texts(self.app.visual)
        self.assertNotIn("今日结论", texts)
        self.assertNotIn("综合判断", texts)
        self.assertNotIn("投入比例", texts)
        self.assertNotIn("把握程度", texts)
        self.assertNotIn("待分析", texts)
        self.assertNotIn("图形面板暂不可用", texts)
        self.assertIn("判断拆解", texts)

    def test_empty_visual_workspace_no_longer_draws_sparkline_placeholder(self):
        # Task 3：价格走势唯一由右侧 kline_canvas 承担，visual 面板不再画"近期价格走势"
        # 小折线占位（旧 tag empty_visual_sparkline 应彻底消失）。
        self.app._set_results_expanded(True)
        self.app._draw_empty_visual()
        self.root.update_idletasks()

        self.assertFalse(self.app.visual.find_withtag("empty_visual_sparkline"))
        self.assertNotIn("近期价格走势", _canvas_texts(self.app.visual))
        # 同卡的"判断拆解"占位保留，本任务只删 sparkline。
        self.assertIn("判断拆解", _canvas_texts(self.app.visual))

    def test_draw_visual_no_longer_draws_sparkline(self):
        # Task 3：_draw_visual（有真实结果时的渲染）不再调用 _draw_sparkline；该私有
        # helper 在 app.py 中已无其它调用方，随之一并删除（不再是 app 的属性）。
        self._inject_sample()
        self.app._show_selected_detail()
        self.root.update_idletasks()

        self.assertFalse(hasattr(self.app, "_draw_sparkline"))
        self.assertNotIn("近期价格走势", _canvas_texts(self.app.visual))
        # 判断拆解 因子条仍保留：本任务范围只删 sparkline，不动 _draw_factor_bars。
        self.assertIn("判断拆解", _canvas_texts(self.app.visual))

    def test_kline_panel_gets_more_width_than_visual_panel(self):
        # Task 3：K 线现为唯一价格图、信息密度更高，两栏从旧的 expand=True 各占一半
        # 改为不等宽——kline 应始终获得比 visual 更多的横向空间。
        self._inject_sample()
        self.app._show_selected_detail()
        self.root.update_idletasks()

        visual_width = self.app.visual.winfo_width()
        chart_width = self.app.kline_canvas.winfo_width()
        self.assertGreater(chart_width, visual_width)
        self.assertGreaterEqual(chart_width / visual_width, 1.65)

    def test_clear_collapses_results_back_to_single_prompt(self):
        # P3 起，clear() 不再重绘空态占位图形，而是把结论/价格/详情卡折叠回一行提示
        # （与 _reset_results 一致，见 test_results_area_collapses_to_single_prompt_before_first_result）。
        self._inject_sample()
        self.app._show_selected_detail()
        self.root.update_idletasks()
        self.assertTrue(self.app._results_expanded)
        self.assertFalse(self.app.visual.find_withtag("empty_visual_badge"))
        self.assertTrue(getattr(self.app, "_kline_state", {}).get("layout"))

        self.app.clear()
        self.root.update_idletasks()

        self.assertFalse(self.app._results_expanded)
        self.assertEqual(self.app.results_placeholder.winfo_manager(), "pack")
        self.assertEqual(self.app.insight_strip.winfo_manager(), "")
        self.assertEqual(self.app.visual_workspace_shell.winfo_manager(), "")
        self.assertEqual(self.app.detail_panel_shell.winfo_manager(), "")
        self.assertFalse(getattr(self.app, "_kline_state", {}).get("layout"))

    def test_reset_results_clears_stale_summary_and_collapses_panels(self):
        # P3 起，_reset_results 不再重绘 spectrum_canvas，而是折叠结论/价格/详情卡
        # （旧行为断言 spectrum_canvas 只剩一个"五档结论待显示"占位 item；新行为下
        # spectrum_canvas 干脆不再可见，验证折叠状态即可，摘要变量的清空逻辑不变）。
        self._inject_sample()
        self.app._show_selected_detail()
        self.root.update_idletasks()
        self.assertTrue(self.app._results_expanded)
        self.assertNotEqual(self.app.visual_metric_vars["action"].get(), "未选择")

        self.app._reset_results()
        self.root.update_idletasks()

        self.assertFalse(self.app._results_expanded)
        self.assertEqual(self.app.insight_strip.winfo_manager(), "")
        self.assertEqual(self.app.visual_metric_vars["action"].get(), "未选择")
        self.assertEqual(self.app.visual_metric_vars["position"].get(), "—")

    def test_visual_summary_uses_spacious_metric_panel(self):
        self.assertTrue(hasattr(self.app, "visual_summary_metrics"))
        self.assertEqual(
            [metric["title"].cget("text") for metric in self.app.visual_summary_metrics],
            ["方向", "仓位", "把握", "波动"],
        )
        self.assertGreaterEqual(self.app.insight_strip.winfo_reqheight(), 145)
        self.assertLessEqual(self.app.insight_strip.winfo_reqheight(), 240)

        self._inject_sample()
        self.app._show_selected_detail()
        self.root.update_idletasks()

        values = [metric["value_var"].get() for metric in self.app.visual_summary_metrics]
        self.assertIn("买入", values[0])
        self.assertIn("%", values[1])
        self.assertIn("%", values[2])
        self.assertIn("%", values[3])
        for metric in self.app.visual_summary_metrics:
            self.assertLessEqual(int(metric["value"].cget("width")), 12)
            self.assertIn(" 12 ", f" {metric['value'].cget('font')} ")
        self.assertGreaterEqual(self.app.insight_strip.winfo_height(), 145)

    def test_summary_metrics_and_spectrum_share_one_verdict_card(self):
        # P3 Task2：insight_strip 本身就是结论卡（verdict card）外壳——四指标一行 + 其下五档
        # 光谱条合并进同一张内层白底卡片（不再是并排两张各自描边的卡：visual_summary_frame/
        # spectrum_frame 均已删除）。
        from stock_advisor.ui.theme import CARD_BG, CARD_BORDER

        self.assertTrue(hasattr(self.app, "insight_strip"))
        self.assertFalse(hasattr(self.app, "visual_summary_frame"))
        self.assertFalse(hasattr(self.app, "spectrum_frame"))
        self.assertFalse(hasattr(self.app, "visual_summary_var"))
        self.assertEqual(str(self.app.insight_strip.cget("background")), CARD_BORDER)

        value_labels = [metric["value"] for metric in self.app.visual_summary_metrics]
        self.assertEqual(len(value_labels), 4)
        for key, metric in zip(
            ("action", "position", "confidence", "move"), self.app.visual_summary_metrics
        ):
            self.assertIs(metric["value_var"], self.app.visual_metric_vars[key])
            self.assertEqual(
                str(metric["value"].cget("textvariable")), str(self.app.visual_metric_vars[key])
            )

        # 四指标行与光谱条都挂在 insight_strip 之下，且共用同一张直属内层卡片——不是两张
        # 并排的独立描边卡。
        metrics_body = _direct_child(value_labels[0], self.app.insight_strip)
        spectrum_body = _direct_child(self.app.spectrum_canvas, self.app.insight_strip)
        self.assertIsNotNone(metrics_body)
        self.assertIsNotNone(spectrum_body)
        self.assertIs(metrics_body, spectrum_body)
        self.assertEqual(str(metrics_body.cget("background")), CARD_BG)

        # 光谱条排在四指标行下方（同一内层卡片中自上而下堆叠，而非并排）。
        slaves = metrics_body.pack_slaves()
        self.assertIn(self.app.spectrum_canvas, slaves)
        self.assertGreater(slaves.index(self.app.spectrum_canvas), 0)

        self.assertGreaterEqual(int(self.app.spectrum_canvas.cget("height")), 64)
        self.assertLessEqual(int(self.app.spectrum_canvas.cget("height")), 80)
        self.assertGreaterEqual(self.app.insight_strip.winfo_reqheight(), 145)

    def test_empty_spectrum_prompt_is_short_and_fits_canvas(self):
        # P3 起 spectrum 面板折叠时不预绘；显式展开后再画，回归覆盖的仍是同一段
        # 摆放/换行像素计算（regression: 250% DPI 下文案曾溢出画布）。
        self.app._set_results_expanded(True)
        self.app._safe_draw_spectrum(None)
        self.root.update_idletasks()

        items = self.app.spectrum_canvas.find_all()
        self.assertEqual(len(items), 1)
        self.assertEqual(self.app.spectrum_canvas.itemcget(items[0], "text"), "五档结论待显示")

        bbox = self.app.spectrum_canvas.bbox("all")
        self.assertIsNotNone(bbox)
        assert bbox is not None
        self.assertGreaterEqual(bbox[0], -2)
        self.assertLessEqual(bbox[0], 20)
        self.assertLessEqual(bbox[2], self.app.spectrum_canvas.winfo_width() + 2)

    def test_spectrum_render_failure_falls_back_to_nonblank_prompt(self):
        def _raise(_measurement):
            raise RuntimeError("render failed")

        self.app._draw_spectrum_strip = _raise

        self.app._safe_draw_spectrum(None)
        self.root.update_idletasks()

        items = self.app.spectrum_canvas.find_all()
        self.assertEqual(len(items), 1)
        self.assertIn("暂不可用", self.app.spectrum_canvas.itemcget(items[0], "text"))

    def test_detail_view_uses_compact_section_navigation(self):
        from stock_advisor.ui.theme import ACCENT

        self.assertTrue(hasattr(self.app, "detail_nav_buttons"))
        self.assertEqual(
            [button.cget("text") for button in self.app.detail_nav_buttons],
            ["结论", "依据", "风险", "操作"],
        )
        self.assertTrue(
            all(isinstance(button, tk.Radiobutton) for button in self.app.detail_nav_buttons)
        )
        self.assertTrue(
            all(not bool(int(button.cget("indicatoron"))) for button in self.app.detail_nav_buttons)
        )
        self.assertTrue(
            all(int(button.cget("width")) <= 8 for button in self.app.detail_nav_buttons)
        )

        self._inject_sample()
        self.app._show_selected_detail()
        self.root.update_idletasks()
        before_text = self.app.detail.get("1.0", tk.END)
        before_y = self.app.detail.yview()[0]

        self.app.detail_nav_buttons[2].invoke()
        self.root.update_idletasks()

        self.assertEqual(before_text, self.app.detail.get("1.0", tk.END))
        self.assertGreater(self.app.detail.yview()[0], before_y)
        self.assertEqual(self.app.detail_nav_buttons[2].cget("bg"), ACCENT)

    def test_detail_calculator_and_section_nav_share_spacious_toolbar(self):
        self.assertTrue(hasattr(self.app, "detail_control_bar"))
        self.assertIs(self.app.capital_tools_frame.master, self.app.detail_control_bar)
        self.assertIs(self.app.detail_nav_frame.master, self.app.detail_control_bar)
        self.assertEqual(self.app.capital_tools_frame.pack_info().get("side"), "left")
        self.assertEqual(self.app.detail_nav_frame.pack_info().get("side"), "right")
        self.assertIs(self.app.capital_entry.master, self.app.capital_tools_frame)
        self.assertEqual(int(self.app.capital_entry.cget("width")), 14)
        self.assertEqual(self.app.capital_hint_label.cget("text"), "即时重算")

    def test_detail_toolbar_and_text_share_one_bordered_panel(self):
        from stock_advisor.ui.theme import CARD_BORDER

        self.assertTrue(hasattr(self.app, "detail_panel_shell"))
        self.assertEqual(str(self.app.detail_panel_shell.cget("background")), CARD_BORDER)
        self.assertIs(self.app.detail_panel_body.master, self.app.detail_panel_shell)
        self.assertIs(self.app.detail_control_bar.master, self.app.detail_panel_body)
        self.assertIs(self.app.detail_holder.master, self.app.detail_panel_body)
        self.assertIs(self.app.detail.master, self.app.detail_holder)
        self.assertTrue(hasattr(self.app, "detail_panel_divider"))
        self.assertIs(self.app.detail_panel_divider.master, self.app.detail_panel_body)
        self.assertEqual(self.app.detail_panel_divider.pack_info().get("fill"), "x")

    def _inject_sample(self):
        from stock_advisor.data.sample_data import (
            make_sample_analysis,
            make_sample_history,
            make_sample_measurement,
        )
        from stock_advisor.ui.view_format import format_result_row, result_row_tags

        result = make_sample_analysis()
        iid = result.symbol.normalized
        self.app.results[iid] = result
        self.app.measurements[iid] = make_sample_measurement()
        self.app.histories[iid] = make_sample_history()
        self.app.tree.insert(
            "", tk.END, iid=iid, values=format_result_row(result), tags=result_row_tags(result)
        )
        self.app.tree.selection_set(iid)
        return iid

    def test_selection_renders_strength_modules_and_charts(self):
        self._inject_sample()
        self.app._show_selected_detail()
        self.root.update_idletasks()
        detail = self.app.detail.get("1.0", tk.END)
        self.assertIn("决策强度光谱", detail)
        self.assertIn("仓位 / 风控计算器", detail)
        self.assertIn("可信度回测", detail)
        self.assertTrue(self.app.spectrum_canvas.find_all())
        self.assertTrue(self.app.kline_canvas.find_all())

    def test_visual_render_failure_falls_back_without_blocking_detail(self):
        def _raise(_result):
            raise RuntimeError("visual render failed")

        self._inject_sample()
        self.app._draw_visual = _raise

        self.app._show_selected_detail()
        self.root.update_idletasks()

        # Task 3b 起 _draw_empty_visual 只剩"判断拆解"占位条，徽标/今日结论文案已删除
        # （不再打 empty_visual_badge/empty_visual_text tag）；回退态改为断言占位条本身
        # 仍能画出，且不阻塞详情/光谱面板。
        self.assertFalse(self.app.visual.find_withtag("empty_visual_badge"))
        self.assertFalse(self.app.visual.find_withtag("empty_visual_text"))
        self.assertTrue(self.app.visual.find_withtag("empty_visual_bars"))
        self.assertIn("核心结论", self.app.detail.get("1.0", tk.END))
        self.assertTrue(self.app.spectrum_canvas.find_all())

    def test_draw_visual_only_shows_factor_breakdown(self):
        # Task 3b：真实结果渲染时，visual 面板不再重复结果表(建议列)/结论卡已有的
        # 内容——徽标(action_label)、"今日结论"标题+叙述、三项指标(综合判断/投入比例/
        # 把握程度)全部删除；只保留本面板独有的"判断拆解"因子分解。_draw_metric_bar
        # 连同其唯一调用方一起删除，_draw_factor_bars 保留。
        self.assertFalse(hasattr(self.app, "_draw_metric_bar"))
        self.assertTrue(hasattr(self.app, "_draw_factor_bars"))

        iid = self._inject_sample()
        self.app._show_selected_detail()
        self.root.update_idletasks()

        result = self.app.results[iid]
        texts = _canvas_texts(self.app.visual)
        self.assertNotIn(result.action_label, texts)
        self.assertNotIn("今日结论", texts)
        self.assertNotIn("综合判断", texts)
        self.assertNotIn("投入比例", texts)
        self.assertNotIn("把握程度", texts)
        self.assertIn("判断拆解", texts)

    def test_level_change_redecides_without_error(self):
        from stock_advisor.ui.view_text import level_summary

        iid = self._inject_sample()
        self.app._show_selected_detail()
        self.app.level_var.set(5)
        self.app._on_level_change()
        self.root.update_idletasks()
        self.assertEqual(self.app.level_label_var.get(), level_summary(5))
        self.assertTrue(self.app.tree.exists(iid))

    def test_analysis_worker_reports_unexpected_exception_and_finishes(self):
        from stock_advisor.domain.symbols import normalize_symbol
        from stock_advisor.ui import app as app_module

        original = app_module.analyze_symbol
        app_module.analyze_symbol = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("boom")
        )
        self.app.queue = queue.Queue()
        try:
            try:
                self.app._worker([normalize_symbol("600519")])
            except RuntimeError as exc:
                self.fail(f"worker leaked exception instead of queueing failure: {exc}")
        finally:
            app_module.analyze_symbol = original

        first_kind, first_payload = self.app.queue.get_nowait()
        done_kind, done_payload = self.app.queue.get_nowait()
        self.assertEqual(first_kind, "outcome")
        self.assertIn("boom", first_payload.error)
        self.assertEqual(done_kind, "done")
        self.assertIsNone(done_payload)

    def test_screen_worker_reports_unexpected_exception_and_finishes(self):
        # _screen_worker now lives in app_screener; patch the name where it is looked up.
        from stock_advisor.ui import app_screener as screener_module

        original = screener_module.screen_and_recommend
        screener_module.screen_and_recommend = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("screen boom")
        )
        self.app.queue = queue.Queue()
        try:
            try:
                self.app._screen_worker(object(), "score", 5, True, "测试策略")
            except RuntimeError as exc:
                self.fail(f"screen worker leaked exception instead of queueing failure: {exc}")
        finally:
            screener_module.screen_and_recommend = original

        kind, payload = self.app.queue.get_nowait()
        self.assertEqual(kind, "screen_done")
        preset_name, report = payload
        self.assertEqual(preset_name, "测试策略")
        self.assertIn("screen boom", report.error)

    def test_clear_during_running_discards_late_analysis_results(self):
        from stock_advisor.data.sample_data import make_sample_analysis
        from stock_advisor.services.workflow import AnalysisOutcome

        result = make_sample_analysis()
        self.app._set_running(True)

        self.app.clear()

        self.assertTrue(self.app.cancel_event.is_set())
        self.app.queue.put(("outcome", AnalysisOutcome(symbol=result.symbol, result=result)))
        self.app.queue.put(("done", None))
        self.app._poll_queue()
        self.root.update_idletasks()

        self.assertFalse(self.app.busy)
        self.assertEqual(self.app.results, {})
        self.assertEqual(self.app.tree.get_children(), ())
        self.assertEqual(self.app.progress.winfo_manager(), "")

    def test_clear_during_screening_discards_late_recommendation_rows(self):
        from stock_advisor.services.workflow import ScreenReport

        rec = make_sample_recommendation(deep=True)
        report = ScreenReport(total=1, matched=1, recommendations=[rec])
        self.app._set_running(True)

        self.app.clear()

        self.assertTrue(self.app.cancel_event.is_set())
        self.app.queue.put(("screen_progress", (1, 1, rec)))
        self.app.queue.put(("screen_done", ("preset", report)))
        self.app._poll_queue()
        self.root.update_idletasks()

        self.assertFalse(self.app.busy)
        self.assertEqual(self.app.results, {})
        self.assertEqual(self.app.rec_meta, {})
        self.assertEqual(self.app.tree.get_children(), ())
        self.assertEqual(self.app.progress.winfo_manager(), "")

    def test_stop_while_idle_is_noop(self):
        self.app.status_var.set("就绪")
        self.app.cancel_event.clear()
        stop_state = self.app.stop_button.cget("state")
        screen_stop_state = self.app.screen_stop_button.cget("state")

        self.app.stop()

        self.assertFalse(self.app.cancel_event.is_set())
        self.assertEqual(self.app.status_var.get(), "就绪")
        self.assertEqual(self.app.stop_button.cget("state"), stop_state)
        self.assertEqual(self.app.screen_stop_button.cget("state"), screen_stop_state)

    def test_running_state_disables_input_tools(self):
        self.app._set_running(True)

        self.assertEqual(str(self.app.input_tools_button.cget("state")), tk.DISABLED)

        self.app._set_running(False)

        self.assertEqual(str(self.app.input_tools_button.cget("state")), tk.NORMAL)

    def test_input_tools_do_not_mutate_input_while_running(self):
        original_text = "600519"
        self.app._replace_input(original_text)
        self.app._set_running(True)

        self.app.fill_sample()
        self.app.clean_input()

        self.assertEqual(self.app.symbol_input.get("1.0", "end-1c"), original_text)

    def test_close_cancels_running_work_and_monitoring(self):
        destroyed = []
        original_destroy = self.app.root.destroy
        self.app.root.destroy = lambda: destroyed.append(True)
        self.app._set_running(True)
        self.app.monitor_var.set(True)
        self.app._monitor_on = True
        self.app._monitoring = True
        self.app.monitor_queue.put((1, {}))
        try:
            self.app.close()
        finally:
            self.app.root.destroy = original_destroy

        self.assertTrue(destroyed)
        self.assertTrue(self.app.cancel_event.is_set())
        self.assertTrue(self.app._discard_running_results)
        self.assertFalse(self.app._monitor_on)
        self.assertFalse(self.app._monitoring)
        self.assertFalse(self.app.monitor_var.get())
        self.assertTrue(self.app.monitor_queue.empty())

    def test_closing_poll_callbacks_do_not_reschedule(self):
        after_calls = []
        original_after = self.app.root.after
        self.app.root.after = lambda *args: after_calls.append(args)
        self.app._closing = True
        self.app.monitor_var.set(True)
        try:
            self.app._poll_queue()
            self.app._monitor_tick(self.app._monitor_generation)
            self.app._poll_monitor(self.app._monitor_generation)
            self.app._poll_fund_flow()
        finally:
            self.app.root.after = original_after

        self.assertEqual(after_calls, [])

    def test_capital_change_refreshes_calculator(self):
        self._inject_sample()
        self.app.capital_var.set("50000")
        self.app._refresh_capital()
        self.root.update_idletasks()
        self.assertIn("仓位 / 风控计算器", self.app.detail.get("1.0", tk.END))

    def test_capital_change_reports_config_save_failure_without_dialog(self):
        from stock_advisor.ui import app as app_module

        errors = []
        original_save = app_module.store.save_config
        original_showerror = app_module.messagebox.showerror
        app_module.store.save_config = lambda *_args, **_kwargs: False
        app_module.messagebox.showerror = lambda *args, **kwargs: errors.append((args, kwargs))
        try:
            self.app.capital_var.set("50000")
            self.app._refresh_capital()
        finally:
            app_module.store.save_config = original_save
            app_module.messagebox.showerror = original_showerror

        self.assertEqual(errors, [])
        self.assertIn("未保存", self.app.status_var.get())

    def test_invalid_capital_entry_shows_explicit_calculator_warning(self):
        self._inject_sample()
        for value in ("-1", "NaN", "Infinity"):
            with self.subTest(value=value):
                self.app.capital_var.set(value)
                self.app._refresh_capital()
                self.root.update_idletasks()
                detail = self.app.detail.get("1.0", tk.END)
                self.assertIn("仓位 / 风控计算器", detail)
                self.assertIn("本金需大于0", detail)

    def test_invalid_capital_is_not_kept_in_memory_config(self):
        self.app.capital_var.set("Infinity")

        self.app._save_persisted()

        self.assertEqual(self.app._config.capital, 100000.0)

    def test_add_to_watchlist_persists_across_instances(self):
        self._inject_sample()
        self.app.add_to_watchlist()
        self.assertEqual(len(self.app.watch), 1)
        # 新实例从同一（临时）配置加载到自选
        root2 = tk.Tk()
        root2.withdraw()
        try:
            app2 = StockAdvisorApp(root2)
            self.assertEqual(len(app2.watch), 1)
        finally:
            root2.destroy()

    def test_add_to_watchlist_reports_config_save_failure(self):
        from stock_advisor.ui import app as app_module

        self._inject_sample()
        errors = []
        original_save = app_module.store.save_config
        original_showerror = app_module.messagebox.showerror
        app_module.store.save_config = lambda *_args, **_kwargs: False
        app_module.messagebox.showerror = lambda *args, **kwargs: errors.append((args, kwargs))
        try:
            self.app.add_to_watchlist()
        finally:
            app_module.store.save_config = original_save
            app_module.messagebox.showerror = original_showerror

        self.assertEqual(len(self.app.watch), 1)
        self.assertTrue(errors)
        self.assertIn("配置", errors[0][0][0])
        self.assertIn("未保存", self.app.status_var.get())

    def test_level_change_is_persisted(self):
        self.app.level_var.set(5)
        self.app._on_level_change()
        root2 = tk.Tk()
        root2.withdraw()
        try:
            app2 = StockAdvisorApp(root2)
            self.assertEqual(app2.level_var.get(), 5)
        finally:
            root2.destroy()

    def test_level_change_reports_config_save_failure_without_dialog(self):
        from stock_advisor.ui import app as app_module

        errors = []
        original_save = app_module.store.save_config
        original_showerror = app_module.messagebox.showerror
        app_module.store.save_config = lambda *_args, **_kwargs: False
        app_module.messagebox.showerror = lambda *args, **kwargs: errors.append((args, kwargs))
        try:
            self.app.level_var.set(5)
            self.app._on_level_change()
        finally:
            app_module.store.save_config = original_save
            app_module.messagebox.showerror = original_showerror

        self.assertEqual(errors, [])
        self.assertIn("未保存", self.app.status_var.get())

    def test_comparison_window_opens_with_rows(self):
        self._inject_sample()
        self.app.open_comparison()
        tops = [w for w in self.app.root.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertTrue(tops)
        for window in tops:
            window.destroy()

    def test_comparison_window_uses_compact_summary_strip(self):
        self._inject_sample()

        self.app.open_comparison()
        window = [w for w in self.app.root.winfo_children() if isinstance(w, tk.Toplevel)][0]
        try:
            summary = getattr(window, "_comparison_summary_metrics")

            self.assertEqual(
                [metric["title"].cget("text") for metric in summary],
                ["对比", "买入", "高风险", "持仓"],
            )
            self.assertEqual(summary[0]["value_var"].get(), "1")
            self.assertEqual(summary[1]["value_var"].get(), "1")
            self.assertTrue(all(int(metric["value"].cget("width")) <= 8 for metric in summary))
        finally:
            window.destroy()

    def test_watchlist_manager_opens(self):
        self._inject_sample()
        self.app.add_to_watchlist()
        self.app.open_watchlist_manager()
        tops = [w for w in self.app.root.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertTrue(tops)
        for window in tops:
            window.destroy()

    def test_watchlist_manager_uses_compact_summary_and_more_menu(self):
        self._inject_sample()
        self.app.add_to_watchlist()

        self.app.open_watchlist_manager()
        window = [w for w in self.app.root.winfo_children() if isinstance(w, tk.Toplevel)][0]
        try:
            summary = getattr(window, "_watchlist_summary_metrics")
            buttons = getattr(window, "_watchlist_primary_buttons")
            more_menu = getattr(window, "_watchlist_actions_menu")

            self.assertEqual(
                [metric["title"].cget("text") for metric in summary],
                ["自选", "持仓", "已分析", "待补"],
            )
            self.assertEqual(summary[0]["value_var"].get(), "1")
            self.assertTrue(all(int(metric["value"].cget("width")) <= 8 for metric in summary))
            self.assertEqual(
                [button.cget("text") for button in buttons], ["保存持仓", "更多操作", "关闭"]
            )

            labels = [
                more_menu.entrycget(index, "label") for index in range(more_menu.index("end") + 1)
            ]
            self.assertEqual(labels, ["载入到输入框", "删除选中", "清空自选"])
        finally:
            window.destroy()

    def test_watchlist_position_save_reports_config_save_failure(self):
        from stock_advisor.ui import app as app_module

        self._inject_sample()
        self.app.add_to_watchlist()
        self.app.open_watchlist_manager()
        window = [w for w in self.app.root.winfo_children() if isinstance(w, tk.Toplevel)][0]
        errors = []
        original_save = app_module.store.save_config
        original_showerror = app_module.messagebox.showerror
        app_module.store.save_config = lambda *_args, **_kwargs: False
        app_module.messagebox.showerror = lambda *args, **kwargs: errors.append((args, kwargs))
        try:

            def walk(widget):
                yield widget
                for child in widget.winfo_children():
                    yield from walk(child)

            tree = next(widget for widget in walk(window) if isinstance(widget, ttk.Treeview))
            entries = [widget for widget in walk(window) if isinstance(widget, ttk.Entry)]
            tree.selection_set("0")
            entries[0].delete(0, tk.END)
            entries[0].insert(0, "12.5")
            entries[1].delete(0, tk.END)
            entries[1].insert(0, "100")

            getattr(window, "_watchlist_primary_buttons")[0].invoke()
        finally:
            app_module.store.save_config = original_save
            app_module.messagebox.showerror = original_showerror
            window.destroy()

        self.assertTrue(errors)
        self.assertIn("配置", errors[0][0][0])
        self.assertIn("未保存", self.app.status_var.get())

    def test_kline_hover_draws_and_clears_crosshair(self):
        self._inject_sample()
        self.app._show_selected_detail()
        self.root.update_idletasks()

        class _Motion:
            x = 200
            y = 80

        self.app._on_kline_motion(_Motion())
        self.assertTrue(self.app.kline_canvas.find_withtag("crosshair"))
        self.app._on_kline_leave()
        self.assertFalse(self.app.kline_canvas.find_withtag("crosshair"))

    def test_kline_tooltip_box_width_fits_measured_text_at_high_dpi(self):
        # 回归:旧实现按 7.2*len(text) 估算底框宽度,是与字体实际渲染宽度无关的固定像素公式;
        # 250% DPI 下字体实测显著变宽，旧公式会让文案溢出底框。新实现须按 font.measure 实测
        # 宽度绘制，底框宽恒不小于文案实测宽度——用真实 tk scaling（而非仅 _ui_scale 数值)
        # 让字体测量也随之放大，才能让回归在旧实现下真正失败。
        self._inject_sample()
        self.app._show_selected_detail()
        self.root.update_idletasks()

        # tk scaling 是按屏幕（而非按 Tk() 实例）生效的进程级设置：显式设置后会残留给同一
        # 进程里随后创建的其它 Tk()/StockAdvisorApp（其 _ui_scale 在构造期据此现测），
        # 必须原样恢复，否则会污染其它测试文件里默认 100% DPI 的断言。
        original_scaling = self.root.tk.call("tk", "scaling")
        # 与 _HighDpiStockAdvisorApp 约定一致的 250% DPI tk_scaling。
        self.root.tk.call("tk", "scaling", 3.3366)
        try:
            self.app._ui_scale = 2.5

            class _Motion:
                x = 200
                y = 80

            self.app._on_kline_motion(_Motion())

            canvas = self.app.kline_canvas
            crosshair_items = canvas.find_withtag("crosshair")
            rect_items = [item for item in crosshair_items if canvas.type(item) == "rectangle"]
            text_items = [item for item in crosshair_items if canvas.type(item) == "text"]
            self.assertEqual(len(rect_items), 1)
            self.assertEqual(len(text_items), 1)

            tooltip_text = canvas.itemcget(text_items[0], "text")
            tooltip_font = tkfont.Font(root=self.root, font=("Microsoft YaHei UI", 8))
            measured_w = tooltip_font.measure(tooltip_text)

            x0, _y0, x1, _y1 = canvas.coords(rect_items[0])
            self.assertGreaterEqual(x1 - x0, measured_w)
        finally:
            self.root.tk.call("tk", "scaling", original_scaling)

    def test_clear_resets_kline_hover_state(self):
        self._inject_sample()
        self.app._show_selected_detail()
        self.root.update_idletasks()
        self.assertTrue(getattr(self.app, "_kline_state", {}).get("layout"))

        self.app.clear()
        self.root.update_idletasks()

        class _Motion:
            x = 200
            y = 80

        self.app._on_kline_motion(_Motion())
        self.assertFalse(self.app.kline_canvas.find_withtag("crosshair"))
        self.assertFalse(getattr(self.app, "_kline_state", {}).get("layout"))

    def test_alert_manager_opens(self):
        self.app.open_alert_manager()
        tops = [w for w in self.app.root.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertTrue(tops)
        for window in tops:
            window.destroy()

    def test_alert_field_dropdown_shows_chinese_labels_and_maps_selection_back_to_key(self):
        # Task 4 Fix A: "字段"下拉此前用 values=list(FIELD_LABELS) 展示英文键
        # (price/change_pct/score)；应展示 FIELD_LABELS 的中文值，且选中中文标签添加规则时，
        # 需要映射回对应键写入 AlertRule.field（其余预警逻辑仍按键索引，不应改动）。
        from stock_advisor.domain.alerts import FIELD_LABELS

        self.app.open_alert_manager()
        window = [w for w in self.app.root.winfo_children() if isinstance(w, tk.Toplevel)][0]
        try:
            combobox = getattr(window, "_alert_field_combobox")
            displayed = list(combobox.cget("values"))
            self.assertEqual(displayed, list(FIELD_LABELS.values()))
            for key in FIELD_LABELS:
                self.assertNotIn(key, displayed)
            # 默认选中项也必须是有效中文标签（能映射回合法键），而非原始英文键。
            self.assertEqual(combobox.get(), FIELD_LABELS["price"])

            def walk(widget):
                yield widget
                for child in widget.winfo_children():
                    yield from walk(child)

            # 真正的 ttk.Entry（代码/阈值输入框）会被改写；只读态的 Combobox（含"字段"
            # 下拉，它是 ttk.Entry 子类）在 readonly 下会静默忽略 delete/insert，
            # 因此可安全地对所有 Entry 实例统一赋同一个既是合法代码又是合法阈值的值。
            for entry in [w for w in walk(window) if isinstance(w, ttk.Entry)]:
                entry.delete(0, tk.END)
                entry.insert(0, "600519")
            combobox.set(FIELD_LABELS["change_pct"])  # 选中中文标签"涨跌幅"

            before = len(self.app.alerts)
            getattr(window, "_alert_primary_buttons")[0].invoke()

            self.assertEqual(len(self.app.alerts), before + 1)
            self.assertEqual(self.app.alerts[-1].field, "change_pct")
        finally:
            window.destroy()

    def test_alert_manager_uses_compact_summary_toggle_and_more_menu(self):
        from stock_advisor.domain.models import AlertRule

        self.app.alerts = [
            AlertRule("sh600519", "price", ">=", 1700.0, True),
            AlertRule("sz000001", "score", "<=", -5.0, False),
        ]
        self.app._fired = {("sh600519", "price", ">=", 1700.0)}

        self.app.open_alert_manager()
        window = [w for w in self.app.root.winfo_children() if isinstance(w, tk.Toplevel)][0]
        try:
            summary = getattr(window, "_alert_summary_metrics")
            monitor_button = getattr(window, "_alert_monitor_button")
            primary_buttons = getattr(window, "_alert_primary_buttons")
            actions_menu = getattr(window, "_alert_actions_menu")

            self.assertEqual(
                [metric["title"].cget("text") for metric in summary],
                ["规则", "启用", "触发", "监控"],
            )
            self.assertEqual(
                [metric["value_var"].get() for metric in summary], ["2", "1", "1", "关"]
            )
            self.assertTrue(all(int(metric["value"].cget("width")) <= 8 for metric in summary))
            self.assertFalse(bool(int(monitor_button.cget("indicatoron"))))
            self.assertLessEqual(int(monitor_button.cget("width")), 10)
            self.assertEqual(
                [button.cget("text") for button in primary_buttons],
                ["添加", "实时预警 关", "更多操作", "关闭"],
            )

            labels = [
                actions_menu.entrycget(index, "label")
                for index in range(actions_menu.index("end") + 1)
            ]
            self.assertEqual(labels, ["启用/停用", "删除选中"])
        finally:
            window.destroy()

    def test_alert_add_reports_config_save_failure(self):
        from stock_advisor.ui import app as app_module

        self.app.open_alert_manager()
        window = [w for w in self.app.root.winfo_children() if isinstance(w, tk.Toplevel)][0]
        errors = []
        original_save = app_module.store.save_config
        original_showerror = app_module.messagebox.showerror
        app_module.store.save_config = lambda *_args, **_kwargs: False
        app_module.messagebox.showerror = lambda *args, **kwargs: errors.append((args, kwargs))
        try:

            def walk(widget):
                yield widget
                for child in widget.winfo_children():
                    yield from walk(child)

            entries = [widget for widget in walk(window) if isinstance(widget, ttk.Entry)]
            for entry in entries:
                entry.delete(0, tk.END)
                entry.insert(0, "600519")

            getattr(window, "_alert_primary_buttons")[0].invoke()
        finally:
            app_module.store.save_config = original_save
            app_module.messagebox.showerror = original_showerror
            window.destroy()

        self.assertTrue(errors)
        self.assertIn("配置", errors[0][0][0])
        self.assertIn("未保存", self.app.status_var.get())

    def test_alert_fires_banner_edge_triggered(self):
        from stock_advisor.data.sample_data import make_sample_analysis
        from stock_advisor.domain.models import AlertRule

        result = make_sample_analysis()
        code = result.symbol.normalized
        self.app.alerts = [AlertRule(code, "price", ">=", 1.0)]
        self.assertEqual(self.app.alert_banner.winfo_manager(), "")
        self.app._check_alerts({code: result})
        self.assertEqual(self.app.alert_banner.winfo_manager(), "pack")
        self.assertIn("预警触发", self.app.alert_banner.cget("text"))
        # 边沿触发：再次检查同一真值不重复触发（_fired 已记录）
        self.assertIn(
            ("%s" % code, "price", ">=", 1.0), {(k[0], k[1], k[2], k[3]) for k in self.app._fired}
        )

    def test_monitor_toggle_no_crash(self):
        self.app.monitor_var.set(True)
        self.app._toggle_monitor()
        self.root.update_idletasks()
        self.app.monitor_var.set(False)
        self.app._toggle_monitor()
        self.root.update_idletasks()
        self.assertFalse(self.app._monitor_on)

    def test_monitor_toggle_off_clears_pending_worker_state(self):
        self.app._monitoring = True
        self.app.monitor_queue.put({"SH.600519": object()})

        self.app.monitor_var.set(False)
        self.app._toggle_monitor()

        self.assertFalse(self.app._monitoring)
        self.assertTrue(self.app.monitor_queue.empty())

    def test_stale_monitor_timer_does_not_schedule_after_reenable(self):
        after_calls = []
        original_after = self.app.root.after

        def fake_after(delay, callback=None, *args):
            after_calls.append((delay, callback, args))
            return f"after-{len(after_calls)}"

        self.app.root.after = fake_after
        try:
            self.app.monitor_var.set(True)
            self.app._toggle_monitor()
            stale_tick = next(call for call in after_calls if call[0] == MONITOR_INTERVAL_MS)
            stale_poll = next(call for call in after_calls if call[0] == 700)

            self.app.monitor_var.set(False)
            self.app._toggle_monitor()
            self.app.monitor_var.set(True)
            self.app._toggle_monitor()
            scheduled_before_stale_callbacks = len(after_calls)

            stale_tick[1](*stale_tick[2])
            stale_poll[1](*stale_poll[2])
        finally:
            self.app.root.after = original_after

        self.assertEqual(len(after_calls), scheduled_before_stale_callbacks)

    def test_fund_flow_handler_exists(self):
        self.assertTrue(hasattr(self.app, "show_fund_flow"))
        self.assertTrue(hasattr(self.app, "_show_fund_flow_result"))
        self.assertTrue(hasattr(self.app, "_poll_fund_flow"))
        self.assertIsInstance(self.app.fund_flow_queue, queue.Queue)

    def test_fund_flow_worker_only_enqueues_result(self):
        """worker 是 daemon 线程：不得直接触碰 Tk（不能调用 root.after），只能把结果放进队列，
        由主线程轮询消费——违反此约定正是本次要修复的问题。"""
        from stock_advisor.domain.symbols import normalize_symbol

        class Provider:
            def fetch_fund_flow(self, _symbol):
                return None

        self.app.provider = Provider()
        after_calls = []
        original_after = self.app.root.after
        self.app.root.after = lambda *args, **kwargs: after_calls.append((args, kwargs))
        symbol = normalize_symbol("600519")
        try:
            self.app._fund_flow_worker(symbol, "sample")
        finally:
            self.app.root.after = original_after

        self.assertEqual(after_calls, [])
        self.assertFalse(self.app.fund_flow_queue.empty())
        queued_symbol, queued_name, queued_flow = self.app.fund_flow_queue.get_nowait()
        self.assertEqual(queued_symbol, symbol)
        self.assertEqual(queued_name, "sample")
        self.assertIsNone(queued_flow)

    def test_poll_fund_flow_drains_queue_and_renders(self):
        from stock_advisor.domain.models import FundFlow
        from stock_advisor.domain.symbols import normalize_symbol
        from stock_advisor.ui import app as app_module

        info_calls = []
        original_showinfo = app_module.messagebox.showinfo
        app_module.messagebox.showinfo = lambda *args, **kwargs: info_calls.append((args, kwargs))
        after_calls = []
        original_after = self.app.root.after
        self.app.root.after = lambda *args, **kwargs: after_calls.append((args, kwargs))
        symbol = normalize_symbol("600519")
        flow = FundFlow(today_main=1.5e8, main_5d=3.0e8, recent=[("2026-07-08", 1.5e8)])
        self.app.fund_flow_queue.put((symbol, "示例股票", flow))
        try:
            self.app._poll_fund_flow()
        finally:
            app_module.messagebox.showinfo = original_showinfo
            self.app.root.after = original_after

        self.assertTrue(self.app.fund_flow_queue.empty())
        self.assertEqual(len(info_calls), 1)
        self.assertIn("主力资金流", info_calls[0][0][0])
        self.assertIn("示例股票", info_calls[0][0][1])
        # 只要窗口未关闭，轮询应继续排程（fund_flow 是常驻的单一轮询链）。
        self.assertTrue(after_calls)

    def test_poll_fund_flow_reports_degrade_message_when_flow_missing(self):
        from stock_advisor.domain.symbols import normalize_symbol
        from stock_advisor.ui import app as app_module

        info_calls = []
        original_showinfo = app_module.messagebox.showinfo
        app_module.messagebox.showinfo = lambda *args, **kwargs: info_calls.append((args, kwargs))
        original_after = self.app.root.after
        self.app.root.after = lambda *args, **kwargs: None
        symbol = normalize_symbol("600519")
        self.app.fund_flow_queue.put((symbol, "示例股票", None))
        try:
            self.app._poll_fund_flow()
        finally:
            app_module.messagebox.showinfo = original_showinfo
            self.app.root.after = original_after

        self.assertEqual(len(info_calls), 1)
        self.assertIn("稍后重试", info_calls[0][0][1])
        self.assertEqual(self.app.status_var.get(), "资金流暂取不到")

    def test_info_window_opens_without_ttk_notebook(self):
        from tkinter import ttk as _ttk

        self.app.show_help()
        tops = [w for w in self.app.root.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertTrue(tops)

        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)

        for window in tops:
            self.assertFalse(any(isinstance(w, _ttk.Notebook) for w in walk(window)))
            window.destroy()

    def test_info_window_uses_compact_side_navigation(self):
        self.app.show_help()
        window = [w for w in self.app.root.winfo_children() if isinstance(w, tk.Toplevel)][0]
        try:
            buttons = getattr(window, "_info_nav_buttons")
            text = getattr(window, "_info_text")

            self.assertTrue(buttons)
            self.assertTrue(all(isinstance(button, tk.Radiobutton) for button in buttons))
            self.assertTrue(all(int(button.cget("width")) <= 14 for button in buttons))
            self.assertTrue(all(button.pack_info().get("side") == "top" for button in buttons))

            first_text = text.get("1.0", tk.END)
            buttons[1].invoke()
            self.root.update_idletasks()

            self.assertNotEqual(first_text, text.get("1.0", tk.END))
            self.assertIn(buttons[1].cget("text"), text.get("1.0", tk.END))
        finally:
            window.destroy()

    def test_sc_scales_canvas_dims(self):
        # 纯算术：_ui_scale 生效后，_sc() 按同一因子换算像素（四舍五入取整）。
        self.app._ui_scale = 2.5
        self.assertEqual(self.app._sc(300), 750)
        self.assertEqual(self.app._sc(48), 120)
        self.assertEqual(self.app._sc(32), 80)

        # 构建期验证：画布高在 _build_ui()（由 __init__ 调用）期间就读取 self._sc(...)，
        # 所以要在 _build_ui() 之前让 _ui_scale 生效——用子类桩掉 _tk_scaling 再构造新实例。
        root2 = tk.Tk()
        root2.withdraw()
        try:
            app2 = _HighDpiStockAdvisorApp(root2)
            self.assertEqual(app2._ui_scale, 2.5)
            self.assertEqual(int(app2.visual.cget("height")), app2._sc(360))
            self.assertEqual(int(app2.kline_canvas.cget("height")), app2._sc(360))
            self.assertEqual(int(app2.spectrum_canvas.cget("height")), app2._sc(68))
            self.assertEqual(int(app2.visual.cget("height")), 900)
            self.assertEqual(int(app2.kline_canvas.cget("height")), 900)
            self.assertEqual(int(app2.spectrum_canvas.cget("height")), 170)
        finally:
            root2.destroy()

    def test_sc_scales_construction_time_widget_options(self):
        # 进度条 length、选股页说明 wraplength、说明窗章节按钮 wraplength 都是构建期传入
        # 控件构造函数的实例级选项（非 ttk 样式），随高 DPI 子类一起验证。
        root2 = tk.Tk()
        root2.withdraw()
        try:
            app2 = _HighDpiStockAdvisorApp(root2)
            self.assertEqual(int(app2.progress.cget("length")), app2._sc(180))
            self.assertEqual(int(app2.progress.cget("length")), 450)

            screener_tab = app2._tab_frames[1]
            desc_label = next(
                widget
                for widget in screener_tab.winfo_children()
                if isinstance(widget, ttk.Label)
                and str(widget.cget("textvariable")) == str(app2.preset_desc_var)
            )
            self.assertEqual(int(desc_label.cget("wraplength")), app2._sc(760))
            self.assertEqual(int(desc_label.cget("wraplength")), 1900)

            app2.show_help()
            info_window = [w for w in app2.root.winfo_children() if isinstance(w, tk.Toplevel)][0]
            try:
                nav_buttons = getattr(info_window, "_info_nav_buttons")
                self.assertTrue(nav_buttons)
                for button in nav_buttons:
                    self.assertEqual(int(button.cget("wraplength")), app2._sc(112))
                    self.assertEqual(int(button.cget("wraplength")), 280)
            finally:
                info_window.destroy()
        finally:
            root2.destroy()

    def test_sc_applies_to_style_configured_decorations(self):
        # Treeview 行高 / 进度条厚度 / 滚动条宽度与箭头 / Spinbox 箭头都经 ttk.Style()
        # 配置——bare ttk.Style() 绑定的是进程级 default root，在同一 root 上强制缩放
        # 因子后重跑 _configure_styles() 即可验证，无需另建 Tk() 根（那样反而会因
        # ttk.Style() 落在别的 default root 上而读不到）。
        self.app._ui_scale = 2.5
        self.app._configure_styles()
        style = ttk.Style(self.root)
        self.assertEqual(int(style.lookup("Treeview", "rowheight")), self.app._sc(42))
        self.assertEqual(
            int(style.lookup("Horizontal.TProgressbar", "thickness")), self.app._sc(14)
        )
        self.assertEqual(int(style.lookup("Vertical.TScrollbar", "width")), self.app._sc(11))
        self.assertEqual(int(style.lookup("Vertical.TScrollbar", "arrowsize")), self.app._sc(11))
        self.assertEqual(int(style.lookup("Horizontal.TScrollbar", "width")), self.app._sc(11))
        self.assertEqual(int(style.lookup("Horizontal.TScrollbar", "arrowsize")), self.app._sc(11))
        self.assertEqual(int(style.lookup("TSpinbox", "arrowsize")), self.app._sc(13))
        # 具体数值（银行家舍入：11*2.5=27.5→28，13*2.5=32.5→32）防止两处都算错而互相抵消。
        self.assertEqual(int(style.lookup("Treeview", "rowheight")), 105)
        self.assertEqual(int(style.lookup("Horizontal.TProgressbar", "thickness")), 35)
        self.assertEqual(int(style.lookup("Vertical.TScrollbar", "width")), 28)
        self.assertEqual(int(style.lookup("TSpinbox", "arrowsize")), 32)

    def test_sc_scales_content_band_width_and_margin(self):
        # _apply_content_band 在每次 <Configure> 回调时读取 self._ui_scale（非构建期
        # 烘焙），可直接在已构造的 app 上强制缩放因子后验证。
        self.app._ui_scale = 2.5
        scaled_max = self.app._sc(MAX_CONTENT_WIDTH)
        scaled_margin = self.app._sc(CONTENT_MARGIN)
        self.assertEqual(scaled_max, round(MAX_CONTENT_WIDTH * 2.5))
        self.assertEqual(scaled_margin, round(CONTENT_MARGIN * 2.5))

        wide = scaled_max + 400
        self.app._on_canvas_configure(_FakeEvent(wide))
        self.root.update_idletasks()
        x, _y = self.app.page_canvas.coords(self.app.page_window)
        width = int(self.app.page_canvas.itemcget(self.app.page_window, "width"))
        self.assertEqual(width, scaled_max)
        self.assertEqual(int(x), (wide - scaled_max) // 2)

        self.app._on_canvas_configure(_FakeEvent(800))
        x2, _y2 = self.app.page_canvas.coords(self.app.page_window)
        width2 = int(self.app.page_canvas.itemcget(self.app.page_window, "width"))
        self.assertEqual(width2, 800 - 2 * scaled_margin)
        self.assertEqual(int(x2), scaled_margin)

    def test_manager_child_windows_scale_size_and_minsize_with_ui_scale(self):
        # Task 7: 自选股/条件预警等子窗口此前把 (720,520)/(780,560) 这类设计稿像素原样传给
        # _center_child_window/minsize，250% DPI 下窗口显得很小。断言传给
        # _center_child_window 的尺寸、以及最终 minsize，都随 _ui_scale 放大。
        root2 = tk.Tk()
        root2.withdraw()
        try:
            app2 = _HighDpiStockAdvisorApp(root2)
            self.assertEqual(app2._ui_scale, 2.5)
            sizes: list[tuple[int, int]] = []
            original = app2._center_child_window

            def spy(window, size):
                sizes.append(tuple(size))
                return original(window, size)

            app2._center_child_window = spy
            opened: list[tk.Toplevel] = []
            try:
                app2.open_watchlist_manager()
                app2.open_alert_manager()
                opened = [w for w in app2.root.winfo_children() if isinstance(w, tk.Toplevel)]
                self.assertEqual(len(opened), 2)
                watchlist_window, alert_window = opened

                self.assertEqual(sizes[0], (app2._sc(720), app2._sc(520)))
                self.assertEqual(sizes[0], (1800, 1300))
                _left, _top, work_width, work_height = app2._screen_work_area(watchlist_window)
                minimum_width, minimum_height = watchlist_window.minsize()
                self.assertGreater(minimum_width, 620)
                self.assertGreater(minimum_height, 420)
                self.assertLessEqual(
                    minimum_width + 2 * app2._sc(CHILD_WINDOW_WORKAREA_MARGIN), work_width
                )
                self.assertLessEqual(
                    minimum_height + 2 * app2._sc(CHILD_WINDOW_WORKAREA_MARGIN), work_height
                )

                self.assertEqual(sizes[1], (app2._sc(780), app2._sc(560)))
                self.assertEqual(sizes[1], (1950, 1400))
                _left, _top, work_width, work_height = app2._screen_work_area(alert_window)
                minimum_width, minimum_height = alert_window.minsize()
                self.assertGreater(minimum_width, 660)
                self.assertGreater(minimum_height, 460)
                self.assertLessEqual(
                    minimum_width + 2 * app2._sc(CHILD_WINDOW_WORKAREA_MARGIN), work_width
                )
                self.assertLessEqual(
                    minimum_height + 2 * app2._sc(CHILD_WINDOW_WORKAREA_MARGIN), work_height
                )
            finally:
                for window in opened:
                    window.destroy()
        finally:
            root2.destroy()

    def test_comparison_window_scales_size_columns_and_gets_horizontal_scrollbar(self):
        # Task 7: 对比窗 11 列此前是固定像素列宽，250% 下相对巨大的行高/字体显得局促；
        # 加一条横向滚动条兜底任意 DPI 下的溢出，同时列宽本身也随 _ui_scale 放大。
        root2 = tk.Tk()
        root2.withdraw()
        try:
            app2 = _HighDpiStockAdvisorApp(root2)
            from stock_advisor.data.sample_data import (
                make_sample_analysis,
                make_sample_history,
                make_sample_measurement,
            )

            result = make_sample_analysis()
            iid = result.symbol.normalized
            app2.results[iid] = result
            app2.measurements[iid] = make_sample_measurement()
            app2.histories[iid] = make_sample_history()

            sizes: list[tuple[int, int]] = []
            original = app2._center_child_window

            def spy(window, size):
                sizes.append(tuple(size))
                return original(window, size)

            app2._center_child_window = spy
            app2.open_comparison()
            tops = [w for w in app2.root.winfo_children() if isinstance(w, tk.Toplevel)]
            self.assertEqual(len(tops), 1)
            window = tops[0]
            try:
                self.assertEqual(sizes[-1], (app2._sc(1200), app2._sc(560)))
                self.assertEqual(sizes[-1], (3000, 1400))
                _left, _top, work_width, work_height = app2._screen_work_area(window)
                frame_width, frame_height = app2._frame_extents(window)
                self.assertEqual(
                    window.minsize(),
                    compute_scaled_minimum(
                        work_width,
                        work_height,
                        app2._ui_scale,
                        900,
                        380,
                        margin=CHILD_WINDOW_WORKAREA_MARGIN,
                        frame_width=frame_width,
                        frame_height=frame_height,
                    ),
                )

                def walk(widget):
                    yield widget
                    for child in widget.winfo_children():
                        yield from walk(child)

                tree = next(w for w in walk(window) if isinstance(w, ttk.Treeview))
                expected_base_widths = {
                    "code": 100,
                    "name": 120,
                    "last": 80,
                    "change": 80,
                    "score": 80,
                    "conf": 70,
                    "risk": 60,
                    "pos": 80,
                    "cost": 90,
                    "pl": 150,
                    "hint": 230,
                }
                self.assertEqual(list(tree["columns"]), list(expected_base_widths))
                for col, base in expected_base_widths.items():
                    with self.subTest(col=col):
                        self.assertEqual(int(tree.column(col, "width")), app2._sc(base))

                hbars = [
                    w
                    for w in walk(window)
                    if isinstance(w, ttk.Scrollbar) and str(w.cget("orient")) == "horizontal"
                ]
                self.assertEqual(len(hbars), 1)
                self.assertEqual(hbars[0].winfo_manager(), "pack")
                self.assertTrue(str(tree.cget("xscrollcommand")))
            finally:
                window.destroy()
        finally:
            root2.destroy()

    def test_info_window_scales_size_minsize_and_nav_frame_width(self):
        # Task 7 / 控制器真机核验:使用说明窗固定 880x580 打开偏小；左侧 nav_frame 固定
        # 154px，250% 下即使 wraplength 已放大，章节名仍会被过窄的框裁切
        # ("几个重要数[据]"/"数据与快[捷]")。断言窗口尺寸、minsize、nav_frame 宽度均
        # 随 _ui_scale 放大，且框宽显著大于 wraplength（不再贴边裁切）。
        root2 = tk.Tk()
        root2.withdraw()
        try:
            app2 = _HighDpiStockAdvisorApp(root2)
            sizes: list[tuple[int, int]] = []
            original = app2._center_child_window

            def spy(window, size):
                sizes.append(tuple(size))
                return original(window, size)

            app2._center_child_window = spy
            app2.show_help()
            tops = [w for w in app2.root.winfo_children() if isinstance(w, tk.Toplevel)]
            self.assertEqual(len(tops), 1)
            window = tops[0]
            try:
                self.assertEqual(sizes[-1], (app2._sc(880), app2._sc(580)))
                self.assertEqual(sizes[-1], (2200, 1450))
                _left, _top, work_width, work_height = app2._screen_work_area(window)
                frame_width, frame_height = app2._frame_extents(window)
                self.assertEqual(
                    window.minsize(),
                    compute_scaled_minimum(
                        work_width,
                        work_height,
                        app2._ui_scale,
                        720,
                        500,
                        margin=CHILD_WINDOW_WORKAREA_MARGIN,
                        frame_width=frame_width,
                        frame_height=frame_height,
                    ),
                )

                nav_frame = getattr(window, "_info_nav_frame")
                self.assertEqual(int(nav_frame.cget("width")), app2._sc(154))
                self.assertEqual(int(nav_frame.cget("width")), 385)

                nav_buttons = getattr(window, "_info_nav_buttons")
                self.assertTrue(nav_buttons)
                for button in nav_buttons:
                    # 章节名不再贴边裁切：框宽须比换行宽度多出可见的内边距余量。
                    self.assertLess(int(button.cget("wraplength")), int(nav_frame.cget("width")))
            finally:
                window.destroy()
        finally:
            root2.destroy()


class HighDpiCenteredGeometryTests(unittest.TestCase):
    # 本机测试进程默认不 DPI-aware（未调用 main.enable_dpi_awareness），Windows 因此把它当作
    # 旧版应用做“DPI 虚拟化”：一旦窗口被真正实体化/校验过一次，任何超出该虚拟化小屏的
    # wm geometry 请求都会被系统悄悄按虚拟化尺寸裁掉——这不是本次改动引入的缺陷，纯属测试宿主
    # 进程缺少 DPI 感知的假象；真实 main.py 在创建任何 Tk 窗口前就调用了
    # enable_dpi_awareness()，因此生产环境不会触发这条系统裁剪路径（已用同样的桩数据在一个手动
    # 开启 DPI 感知的进程里验证过：_apply_centered_geometry 产出与本测试断言完全一致，不被裁剪）。
    # SetProcessDpiAwareness 是进程级且不可逆的，直接在本测试进程调用会污染同一 `discover` 运行里
    # 其余所有 GUI 测试（它们的像素级断言都是按当前不感知 DPI 的小窗口环境校准的）。故在子进程里
    # 复现 main.py 的真实启动顺序（先 enable_dpi_awareness 再建 Tk 窗口），既贴近生产场景，又不
    # 泄漏全局状态。
    def test_apply_centered_geometry_high_dpi(self):
        script = (
            "import sys\n"
            f"sys.path.insert(0, {str(PROJECT_ROOT)!r})\n"
            f"sys.path.insert(0, {str(PROJECT_ROOT / 'src')!r})\n"
            "from main import enable_dpi_awareness\n"
            "enable_dpi_awareness()\n"
            "import tkinter as tk\n"
            "from stock_advisor.ui.app import StockAdvisorApp\n"
            "root = tk.Tk(); root.withdraw()\n"
            "try:\n"
            "    app = StockAdvisorApp(root)\n"
            "    app._screen_work_area = lambda w: (0, 0, 3840, 2040)   # 物理工作区\n"
            "    app._frame_extents = lambda w: (16, 39)\n"
            "    app._tk_scaling = lambda w: 3.3366                     # 250%\n"
            "    app._apply_centered_geometry(root)\n"
            "    root.update_idletasks()\n"
            '    print(root.geometry())                                # 形如 "3464x1700+180+150"\n'
            "finally:\n"
            "    root.destroy()\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, f"stdout={result.stdout!r} stderr={result.stderr!r}")
        geo = result.stdout.strip().splitlines()[-1]
        wh, x, y = geo.split("+")[0], int(geo.split("+")[1]), int(geo.split("+")[2])
        w, h = (int(v) for v in wh.split("x"))
        self.assertGreaterEqual(w, 3000)  # 非旧 bug 的 1376
        self.assertGreaterEqual(h, 1600)  # 非旧 bug 的 680
        self.assertGreater(x, 0)
        self.assertGreater(y, 0)  # 居中,非左上角


if __name__ == "__main__":
    unittest.main()
