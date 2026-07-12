"""Tests for the UI polish pass: window centering, opacity, scrollbar/card
consistency, factor-score coloring, mode-aware shortcuts and input validation.

Pure helpers are tested without Tk; widget wiring uses a headless (withdrawn) root.
"""

import sys
import tkinter as tk
import unittest
from tkinter import ttk
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from stock_advisor.ui.app import (  # noqa: E402
    CARD_BORDER,
    CHILD_WINDOW_WORKAREA_MARGIN,
    WINDOW_ALPHA,
    WINDOW_WORKAREA_MARGIN,
    StockAdvisorApp,
    active_mode_action,
    choose_centering_screen_size,
    compute_centered_window,
    normalize_work_area_to_screen,
    detail_line_tags,
    get_preset,
    is_partial_number,
    make_sample_recommendation,
    validate_tunable,
)
from stock_advisor.ui.layout import (  # noqa: E402
    ui_scale,
    compute_child_window_geometry,
    compute_main_geometry,
    compute_centered_window,
    compute_scaled_minimum,
    compute_workspace_columns,
    stacked_text_y,
)
from stock_advisor.ui.theme import (  # noqa: E402
    ACCENT,
    CARD_BG,
    COMMAND_BG,
    COMMAND_INK,
    COMMAND_MUTED_INK,
    COMMAND_SELECTED_BG,
    CONTROL_BG,
    DANGER_COLOR,
    INK,
    MUTED_INK,
    NEG_COLOR,
    PAGE_BG,
    POS_COLOR,
)


def _relative_luminance(color: str) -> float:
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted((_relative_luminance(foreground), _relative_luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class ResearchWorkbenchThemeTests(unittest.TestCase):
    def test_core_text_and_action_colors_meet_accessible_contrast(self):
        pairs = (
            (INK, PAGE_BG),
            (MUTED_INK, PAGE_BG),
            ("#ffffff", ACCENT),
            (COMMAND_INK, COMMAND_BG),
            (COMMAND_MUTED_INK, COMMAND_BG),
            (POS_COLOR, CARD_BG),
            (NEG_COLOR, CARD_BG),
            (DANGER_COLOR, CARD_BG),
        )

        for foreground, background in pairs:
            with self.subTest(foreground=foreground, background=background):
                self.assertGreaterEqual(_contrast_ratio(foreground, background), 4.5)

    def test_market_semantic_colors_are_not_reused_as_primary_accent(self):
        self.assertNotIn(ACCENT.lower(), {POS_COLOR.lower(), NEG_COLOR.lower()})
        self.assertNotEqual(POS_COLOR.lower(), NEG_COLOR.lower())
        self.assertNotIn(DANGER_COLOR.lower(), {POS_COLOR.lower(), NEG_COLOR.lower(), ACCENT.lower()})

    def test_workspace_columns_keep_chart_visually_dominant(self):
        visual_w, chart_w = compute_workspace_columns(1200, gap=1)
        self.assertEqual(visual_w + chart_w + 1, 1200)
        self.assertGreaterEqual(chart_w / visual_w, 1.65)

    def test_workspace_columns_degrade_safely_on_narrow_widths(self):
        visual_w, chart_w = compute_workspace_columns(640, gap=1)
        self.assertGreater(visual_w, 0)
        self.assertGreater(chart_w, visual_w)
        self.assertEqual(visual_w + chart_w + 1, 640)

    def test_scaled_minimum_tracks_dpi_without_exceeding_the_work_area(self):
        self.assertEqual(compute_scaled_minimum(3840, 2100, 2.5, 1000, 680), (2500, 1700))
        self.assertEqual(compute_scaled_minimum(1536, 816, 2.5, 1000, 680), (1536, 816))
        self.assertEqual(
            compute_scaled_minimum(
                1920, 1040, 1.5, 1000, 680, margin=72, frame_width=16, frame_height=39
            ),
            (1500, 785),
        )


class WindowCenteringTests(unittest.TestCase):
    def test_child_window_centers_over_parent_when_it_fits(self):
        self.assertEqual(
            compute_child_window_geometry(
                parent_left=200,
                parent_top=100,
                parent_width=1520,
                parent_height=800,
                work_left=0,
                work_top=0,
                work_width=1920,
                work_height=1040,
                requested_width=720,
                requested_height=520,
                margin=24,
                frame_width=16,
                frame_height=39,
            ),
            (720, 520, 600, 240),
        )

    def test_oversized_child_window_is_centered_and_clamped_inside_work_area(self):
        width, height, x, y = compute_child_window_geometry(
            parent_left=200,
            parent_top=100,
            parent_width=1520,
            parent_height=800,
            work_left=0,
            work_top=0,
            work_width=1920,
            work_height=1040,
            requested_width=3000,
            requested_height=1400,
            margin=24,
            frame_width=32,
            frame_height=88,
        )
        self.assertEqual((width, height, x, y), (1840, 904, 24, 24))
        self.assertLessEqual(x + width + 32, 1920 - 24)
        self.assertLessEqual(y + height + 88, 1040 - 24)

    def test_virtual_desktop_work_area_falls_back_to_current_screen(self):
        self.assertEqual(
            normalize_work_area_to_screen(0, 0, 3840, 1040, 1536, 864),
            (0, 0, 1536, 864),
        )

    def test_virtual_tk_screen_uses_primary_monitor_size_for_centering(self):
        self.assertEqual(
            choose_centering_screen_size(3840, 1040, 1536, 864),
            (1536, 864),
        )

    def test_single_monitor_work_area_is_preserved(self):
        self.assertEqual(
            normalize_work_area_to_screen(0, 0, 1536, 816, 1536, 864),
            (0, 0, 1536, 816),
        )

    def test_matching_tk_screen_keeps_tk_size_for_centering(self):
        self.assertEqual(
            choose_centering_screen_size(1536, 864, 1536, 864),
            (1536, 864),
        )

    def test_window_leaves_uniform_margin_on_all_four_sides(self):
        # 工作区 1536x816（底部 48px 任务栏），四周留 48px 均匀空隙
        win_w, win_h, x, y = compute_centered_window(
            work_w=1536, work_h=816, margin=48, max_w=1600, max_h=1120, min_w=1000, min_h=660
        )
        # 四边空隙完全相等：左右 = 上下 = margin
        self.assertEqual(x, 48)
        self.assertEqual(y, 48)
        self.assertEqual(1536 - win_w - x, x, "左右空隙应相等")
        self.assertEqual(816 - win_h - y, y, "上下空隙应相等")

    def test_window_never_hugs_the_taskbar(self):
        # 旧行为是 1200x760 → 底部只剩 28px；新行为底部空隙应 >= margin
        _w, win_h, _x, y = compute_centered_window(
            work_w=1536, work_h=816, margin=48, max_w=1600, max_h=1120, min_w=1000, min_h=660
        )
        bottom_gap = 816 - win_h - y
        self.assertGreaterEqual(bottom_gap, 48)

    def test_window_caps_size_on_large_monitors(self):
        win_w, win_h, _x, _y = compute_centered_window(
            work_w=3840, work_h=2120, margin=48, max_w=1600, max_h=1120, min_w=1000, min_h=660
        )
        self.assertEqual(win_w, 1600)
        self.assertEqual(win_h, 1120)

    def test_window_respects_min_size_on_tiny_work_area(self):
        win_w, win_h, x, y = compute_centered_window(
            work_w=1024, work_h=700, margin=48, max_w=1600, max_h=1120, min_w=1000, min_h=660
        )
        self.assertEqual(win_w, 1000)  # work-2*margin=928 < min 1000 → floored
        self.assertEqual(win_h, 660)   # work-2*margin=604 < min 660 → floored
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)

    def test_window_clamps_an_oversized_scaled_minimum_inside_work_area(self):
        win_w, win_h, x, y = compute_centered_window(
            work_w=1920,
            work_h=1040,
            margin=180,
            max_w=4000,
            max_h=4000,
            min_w=2500,
            min_h=1700,
            frame_w=32,
            frame_h=88,
        )
        self.assertLessEqual(win_w + 32, 1920)
        self.assertLessEqual(win_h + 88, 1040)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)

    def test_window_stays_centered_inside_work_area(self):
        win_w, win_h, x, y = compute_centered_window(
            work_w=1536, work_h=816, margin=48, max_w=1600, max_h=1120, min_w=1000, min_h=660
        )
        self.assertEqual(x, (1536 - win_w) // 2)
        self.assertEqual(y, (816 - win_h) // 2)

    def test_outer_window_is_centered_when_title_bar_frame_is_known(self):
        # 计入标题栏(frame_h)与边框(frame_w)后，按【外框】居中——否则标题栏会把底部空隙吃掉。
        fw, fh = 16, 39
        win_w, win_h, x, y = compute_centered_window(
            work_w=1536, work_h=816, margin=72, max_w=1600, max_h=1600,
            min_w=1000, min_h=660, frame_w=fw, frame_h=fh,
        )
        outer_w, outer_h = win_w + fw, win_h + fh
        # 外框左右、上下空隙相等（整数居中允许 1px 取整误差）。
        self.assertLessEqual(abs((1536 - outer_w - x) - x), 1)
        self.assertLessEqual(abs((816 - outer_h - y) - y), 1)
        # 底部外框空隙明显大于标题栏厚度，窗口下沿不再贴近任务栏。
        self.assertGreaterEqual(816 - outer_h - y, 40)


class MainGeometryDpiTests(unittest.TestCase):
    def test_ui_scale_from_tk_scaling(self):
        assert ui_scale(96/72) == 1.0            # 100%
        assert ui_scale(3.3366) == 2.5           # 250% (4K 本机)
        assert ui_scale(2.0) == 1.5              # 150%
        assert ui_scale("bad") == 1.0            # 非法→1.0
        assert ui_scale(0.5) == 1.0              # 下限 1.0

    def test_main_geometry_high_dpi_centers_and_fills(self):
        # 4K@250%: 物理工作区 3840x2040, ui_scale 2.5 —— 复现被修的 bug 场景
        win_w, win_h, x, y = compute_main_geometry(
            0, 0, 3840, 2040, 2.5, 1000, 680, 1600, 1600, 72, frame_w=16, frame_h=39,
        )
        assert win_w >= 3000 and win_h >= 1600   # 旧 bug 是 1376x680,现在填满
        assert x > 0 and y > 0                    # 旧 bug 是 +72+48 贴左上;现居中
        assert abs((3840 - (win_w + 16)) // 2 - x) <= 1   # 四边留白均匀(按外框)
        assert abs((2040 - (win_h + 39)) // 2 - y) <= 1

    def test_main_geometry_no_scaling_matches_plain_centering(self):
        # ui_scale=1.0 时等价于直接 compute_centered_window + 原点偏移
        got = compute_main_geometry(0, 0, 1536, 816, 1.0, 1000, 680, 1600, 1600, 72, 16, 39)
        base = compute_centered_window(1536, 816, 72, 1600, 1600, 1000, 680, 16, 39)
        assert got == (base[0], base[1], base[2], base[3])

    def test_main_geometry_small_high_dpi_work_area_never_overflows(self):
        win_w, win_h, x, y = compute_main_geometry(
            0, 0, 1920, 1040, 2.5, 1000, 680, 1600, 1600, 72, frame_w=32, frame_h=88,
        )
        self.assertLessEqual(x + win_w + 32, 1920)
        self.assertLessEqual(y + win_h + 88, 1040)


class StackedTextLayoutTests(unittest.TestCase):
    def test_stacked_text_no_overlap(self):
        # 给定行高 47(250% 下 11pt 实测)与起始 y，后一行 y 必须 >= 前一行 y + 行高，
        # 否则固定像素间距会被放大字体撑破，导致两行文字互相重叠。
        ys = stacked_text_y(top=18, line_height=47, count=2)
        self.assertEqual(ys, [18, 65])
        self.assertGreaterEqual(ys[1] - ys[0], 47)

    def test_stacked_text_y_handles_arbitrary_line_counts(self):
        ys = stacked_text_y(top=10, line_height=20, count=4)
        self.assertEqual(ys, [10, 30, 50, 70])
        for earlier, later in zip(ys, ys[1:]):
            self.assertGreaterEqual(later - earlier, 20)

    def test_stacked_text_y_single_line_is_just_top(self):
        self.assertEqual(stacked_text_y(top=5, line_height=99, count=1), [5])


class OpacityTests(unittest.TestCase):
    def test_window_is_fully_opaque_for_performance(self):
        # 用户要求不透明 + 顾及性能：不创建分层窗口
        self.assertGreaterEqual(WINDOW_ALPHA, 1.0)


class ModeAwareShortcutTests(unittest.TestCase):
    def test_individual_tab_runs_stock_analysis(self):
        self.assertEqual(active_mode_action(0), "analyze")

    def test_screener_tab_runs_market_screen(self):
        self.assertEqual(active_mode_action(1), "screen")


class FactorColorTests(unittest.TestCase):
    def test_positive_factor_with_risky_word_is_not_red(self):
        # 核心 bug：+5 分却因为描述里含“回撤”被标红
        line = "- 最近走势节奏：+5分，中性。综合短期斜率、20日斜率、近5日胜率和20日回撤。"
        tags = detail_line_tags(line, is_first=False)
        self.assertNotIn("risk", tags)
        self.assertNotIn("negative", tags)
        self.assertIn("positive", tags)

    def test_positive_factor_uses_a_share_positive_tag(self):
        line = "- 中短线走势：+28分，偏积极。价格站上短中期平均价。"
        self.assertIn("positive", detail_line_tags(line, False))

    def test_negative_factor_uses_a_share_negative_tag(self):
        line = "- 额外风险：-6分，需要谨慎。跳空、振幅或回撤触发风险扣分。"
        tags = detail_line_tags(line, False)
        self.assertIn("negative", tags)
        self.assertNotIn("positive", tags)

    def test_zero_factor_is_neutral(self):
        line = "- 价格位置：+0分，中性。价格区间位置104%，方向迹象一般。"
        tags = detail_line_tags(line, False)
        self.assertNotIn("positive", tags)
        self.assertNotIn("negative", tags)
        self.assertNotIn("risk", tags)

    def test_real_risk_bullet_stays_red(self):
        # “需要注意”里的真实风险项（非因子行）仍应标红
        line = "- 20日最大回撤约8.0%，趋势修复需要时间。"
        self.assertIn("risk", detail_line_tags(line, False))

    def test_section_title_and_headline_keep_their_styles(self):
        self.assertEqual(detail_line_tags("判断拆解", False), ("section",))
        self.assertEqual(detail_line_tags("SH.600519 离线样例", True), ("headline",))


class PartialNumberValidationTests(unittest.TestCase):
    def test_allows_building_a_positive_decimal(self):
        for text in ("", "1", "12", "12.", "12.5", ".5"):
            self.assertTrue(is_partial_number(text, allow_negative=False), text)

    def test_allows_negative_when_permitted(self):
        for text in ("-", "-1", "-1.5"):
            self.assertTrue(is_partial_number(text, allow_negative=True), text)

    def test_rejects_negative_when_not_permitted(self):
        self.assertFalse(is_partial_number("-1", allow_negative=False))
        self.assertFalse(is_partial_number("-", allow_negative=False))

    def test_rejects_non_numeric_and_malformed(self):
        for text in ("abc", "1a", "1.2.3", "+1", "1,2", "1 2"):
            self.assertFalse(is_partial_number(text, allow_negative=True), text)


class WidgetWiringTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = StockAdvisorApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        self.root.destroy()

    def test_child_minimum_falls_back_to_root_frame_extents(self):
        child = tk.Toplevel(self.root)
        original_work_area = self.app._screen_work_area
        original_frame_extents = self.app._frame_extents
        original_scale = self.app._ui_scale
        try:
            self.app._ui_scale = 2.5
            self.app._screen_work_area = lambda _window: (0, 0, 1920, 1040)
            self.app._frame_extents = lambda window: (0, 0) if window is child else (16, 39)

            self.app._apply_child_minimum(child, (900, 500))

            self.assertEqual(
                child.minsize(),
                compute_scaled_minimum(
                    1920,
                    1040,
                    2.5,
                    900,
                    500,
                    margin=CHILD_WINDOW_WORKAREA_MARGIN,
                    frame_width=16,
                    frame_height=39,
                ),
            )
        finally:
            self.app._screen_work_area = original_work_area
            self.app._frame_extents = original_frame_extents
            self.app._ui_scale = original_scale
            child.destroy()

    def test_f5_dispatch_runs_screen_on_screener_tab(self):
        calls = []
        self.app.analyze = lambda: calls.append("analyze")
        self.app.start_screen = lambda: calls.append("screen")
        self.app._select_tab(1)
        self.root.update_idletasks()
        self.app._run_active_tab()
        self.assertEqual(calls, ["screen"])

    def test_f5_dispatch_runs_analyze_on_individual_tab(self):
        calls = []
        self.app.analyze = lambda: calls.append("analyze")
        self.app.start_screen = lambda: calls.append("screen")
        self.app._select_tab(0)
        self.root.update_idletasks()
        self.app._run_active_tab()
        self.assertEqual(calls, ["analyze"])

    def test_primary_shortcuts_are_bound_to_the_dispatcher(self):
        self.assertTrue(self.root.bind("<F5>"))
        self.assertTrue(self.root.bind("<Control-Return>"))

    def test_primary_and_secondary_controls_use_flat_visual_language(self):
        style = ttk.Style(self.root)

        self.assertEqual(str(style.lookup("Primary.TButton", "relief")), "flat")
        self.assertEqual(str(style.lookup("Action.TButton", "relief")), "flat")
        self.assertEqual(str(style.lookup("Primary.TButton", "borderwidth")), "0")
        self.assertEqual(str(style.lookup("Action.TButton", "background")), CONTROL_BG)

    def test_command_ribbon_is_the_single_dark_visual_anchor(self):
        self.assertEqual(str(self.app.mode_control_body.cget("background")), COMMAND_BG)
        self.assertEqual(str(self.app.mode_row.cget("background")), COMMAND_BG)
        self.assertEqual(str(self.app.level_control_group.cget("background")), COMMAND_BG)

        selected_mode = self.app._tab_buttons[self.app._active_tab]
        selected_level = self.app.level_buttons[self.app.level_var.get() - 1]
        self.assertEqual(str(selected_mode.cget("background")), COMMAND_SELECTED_BG)
        self.assertEqual(str(selected_level.cget("background")), COMMAND_SELECTED_BG)

    def test_header_and_input_panel_explain_context_at_a_glance(self):
        self.assertEqual(self.app.header_meta_label.cget("text"), "本地规则引擎 · 行情按需更新")
        self.assertEqual(self.app.input_context_title.cget("text"), "研究标的")
        self.assertEqual(self.app.input_context_hint.cget("text"), "最多 30 只")
        self.assertIs(self.app.input_context_frame.master, self.app.input_panel_body)

    def test_screener_parameters_form_one_balanced_horizontal_band(self):
        spinboxes = [widget for widget in self.app.tunable_frame.winfo_children() if isinstance(widget, ttk.Spinbox)]
        labels = [widget for widget in self.app.tunable_frame.winfo_children() if isinstance(widget, ttk.Label)]

        self.assertEqual(len(spinboxes), 4)
        self.assertEqual({int(spin.grid_info()["row"]) for spin in spinboxes}, {1})
        self.assertEqual(sorted(int(spin.grid_info()["column"]) for spin in spinboxes), list(range(4)))
        self.assertEqual({int(label.grid_info()["row"]) for label in labels}, {0})
        self.assertTrue(all(spin.grid_info()["sticky"] == "ew" for spin in spinboxes))

    def test_screener_selected_preset_uses_clear_accent_surface(self):
        active = self.app.preset_buttons[self.app.active_preset_key]

        self.assertEqual(str(active.cget("bg")), ACCENT)
        self.assertEqual(str(active.cget("selectcolor")), ACCENT)
        self.assertEqual(str(active.cget("fg")), "#ffffff")

    def test_empty_state_teaches_the_three_step_workflow_in_a_guided_panel(self):
        self.assertEqual(
            [label.cget("text") for label in self.app.empty_state_steps],
            ["01  输入标的", "02  调整强度", "03  阅读结论与依据"],
        )
        self.assertEqual(self.app.empty_state_title.cget("text"), "从一组代码开始")
        self.assertEqual(self.app.results_placeholder.cget("background"), CARD_BORDER)

    def test_spacious_workspace_uses_large_touch_targets(self):
        style = ttk.Style(self.root)

        self.assertGreaterEqual(int(self.app._tab_buttons[0].cget("pady")), 8)
        self.assertGreaterEqual(int(self.app.level_buttons[0].cget("pady")), 7)
        self.assertGreaterEqual(self.app.analyze_button.winfo_reqheight(), 42)
        self.assertGreaterEqual(int(style.lookup("Treeview", "rowheight")), 40)

    def test_result_components_have_clear_section_headers(self):
        self.assertEqual(self.app.stock_list_title_label.cget("text"), "股票列表")
        self.assertEqual(self.app.verdict_title_label.cget("text"), "当前股票摘要")
        self.assertEqual(self.app.visual_workspace_title_label.cget("text"), "判断依据与价格走势")
        self.assertEqual(self.app.detail_title_label.cget("text"), "详细解释与操作计划")
        self.assertIs(self.app.table_header_bar.master, self.app.table_card)
        self.assertIs(self.app.verdict_header.master, self.app.verdict_body)
        self.assertIs(self.app.visual_workspace_header.master, self.app.visual_workspace)
        self.assertIs(self.app.detail_header.master, self.app.detail_panel_body)

    def test_risk_surfaces_use_the_dedicated_danger_color(self):
        self.assertEqual(self.app.alert_banner.cget("fg"), DANGER_COLOR)
        self.assertEqual(self.app.detail.tag_cget("risk", "foreground"), DANGER_COLOR)

    def test_result_table_alignment_matches_data_type(self):
        self.assertEqual(str(self.app.tree.column("code", "anchor")), "w")
        self.assertEqual(str(self.app.tree.column("name", "anchor")), "w")
        for column in ("score", "confidence", "last", "change"):
            self.assertEqual(str(self.app.tree.column(column, "anchor")), "e")
        for column in ("action", "risk"):
            self.assertEqual(str(self.app.tree.column(column, "anchor")), "center")

    def test_detail_box_uses_ttk_scrollbar_for_consistent_style(self):
        self.assertIsInstance(self.app.detail_scroll, ttk.Scrollbar)
        self.assertIsInstance(self.app.symbol_scroll, ttk.Scrollbar)
        self.assertEqual(self.app.detail_scroll.winfo_manager(), "pack")

    def test_symbol_input_scrollbar_is_hidden_for_short_input(self):
        self.root.update_idletasks()

        self.assertEqual(self.app.symbol_scroll.winfo_manager(), "")

    def test_symbol_input_scrollbar_appears_only_when_content_overflows(self):
        self.app.symbol_input.delete("1.0", tk.END)
        self.app.symbol_input.insert("1.0", "\n".join(f"600{index:03d}" for index in range(20)))
        self.app._refresh_symbol_scrollbar()
        self.root.update_idletasks()

        self.assertEqual(self.app.symbol_scroll.winfo_manager(), "pack")

        self.app.symbol_input.delete("1.0", tk.END)
        self.app.symbol_input.insert("1.0", "600519, 000001")
        self.app._refresh_symbol_scrollbar()
        self.root.update_idletasks()

        self.assertEqual(self.app.symbol_scroll.winfo_manager(), "")

    def test_visual_dashboard_is_wrapped_in_consistent_card_border(self):
        shell = getattr(self.app, "visual_workspace_shell", None)
        self.assertIsNotNone(shell)
        self.assertEqual(str(shell.cget("background")), CARD_BORDER)
        self.assertIs(self.app.visual_workspace.master, shell)

    def test_header_logo_uses_full_canvas_footprint(self):
        self.assertEqual(int(self.app.logo_canvas.cget("width")), 48)
        self.assertEqual(int(self.app.logo_canvas.cget("height")), 48)
        bbox = self.app.logo_canvas.bbox("all")
        self.assertIsNotNone(bbox)
        assert bbox is not None
        self.assertGreaterEqual(bbox[2] - bbox[0], 40)
        self.assertGreaterEqual(bbox[3] - bbox[1], 40)
        logo_colors = {
            str(self.app.logo_canvas.itemcget(item, "fill")).lower()
            for item in self.app.logo_canvas.find_all()
        }
        self.assertIn(POS_COLOR.lower(), logo_colors)
        self.assertNotIn("#19c37d", logo_colors)

    def test_secondary_result_tools_are_grouped_under_more_menu(self):
        watchlist_button = getattr(self.app, "add_to_watchlist_button", None)
        copy_button = getattr(self.app, "copy_tools_button", None)
        copy_menu = getattr(self.app, "copy_tools_menu", None)
        button = getattr(self.app, "secondary_tools_button", None)
        menu = getattr(self.app, "secondary_tools_menu", None)

        self.assertIsNotNone(watchlist_button)
        self.assertIsNotNone(copy_button)
        self.assertIsNotNone(copy_menu)
        self.assertIsNotNone(button)
        self.assertIsNotNone(menu)
        self.assertEqual(watchlist_button.cget("text"), "加入自选")
        self.assertEqual(copy_button.cget("text"), "复制")
        self.assertEqual(button.cget("text"), "更多")

        self.assertEqual(
            [
                widget.cget("text")
                for widget in self.app.results_actions_cluster.winfo_children()
                if isinstance(widget, ttk.Button) and widget.winfo_manager()
            ],
            [],
        )
        self.assertEqual(
            [
                widget.cget("text")
                for widget in self.app.results_actions_cluster.winfo_children()
                if isinstance(widget, ttk.Menubutton) and widget.winfo_manager()
            ],
            ["更多"],
        )
        self.assertLessEqual(button.winfo_reqwidth(), 112)

        rec = make_sample_recommendation(deep=True)
        self.app._add_recommendation(rec, done=1, total=1)
        self.root.update_idletasks()

        self.assertEqual(
            [
                widget.cget("text")
                for widget in self.app.results_actions_cluster.winfo_children()
                if isinstance(widget, ttk.Button) and widget.winfo_manager()
            ],
            ["加入自选"],
        )
        self.assertEqual(
            [
                widget.cget("text")
                for widget in self.app.results_actions_cluster.winfo_children()
                if isinstance(widget, ttk.Menubutton) and widget.winfo_manager()
            ],
            ["复制", "更多"],
        )
        self.assertLessEqual(copy_button.winfo_reqwidth(), 112)
        self.assertLessEqual(button.winfo_reqwidth(), 112)

        copy_end = copy_menu.index("end")
        copy_labels = [copy_menu.entrycget(index, "label") for index in range(copy_end + 1)]
        self.assertEqual(copy_labels, ["复制结果", "复制解释"])

        end = menu.index("end")
        labels = [menu.entrycget(index, "label") for index in range(end + 1)]
        self.assertEqual(labels, ["导出 CSV", "自选股", "横向对比", "预警", "资金流"])

    def test_snapshot_rows_show_copy_without_watchlist_action(self):
        rec = make_sample_recommendation(deep=False)
        self.app._add_recommendation(rec, done=1, total=1)
        self.root.update_idletasks()

        visible_buttons = [
            widget.cget("text")
            for widget in self.app.results_actions_cluster.winfo_children()
            if isinstance(widget, ttk.Button) and widget.winfo_manager()
        ]
        visible_menus = [
            widget.cget("text")
            for widget in self.app.results_actions_cluster.winfo_children()
            if isinstance(widget, ttk.Menubutton) and widget.winfo_manager()
        ]

        self.assertEqual(visible_buttons, [])
        self.assertEqual(visible_menus, ["复制", "更多"])

    def test_tunable_spinboxes_have_key_validation(self):
        spinboxes = [w for w in self.app.tunable_frame.winfo_children() if isinstance(w, ttk.Spinbox)]
        self.assertTrue(spinboxes)
        for spin in spinboxes:
            self.assertEqual(str(spin.cget("validate")), "key")

    def _set_tunable(self, key, value):
        self.app.tunable_vars[key].set(value)

    def test_collect_rejects_out_of_range_recommendation_count(self):
        # 推荐数量超过 30 → 必须抛错（弹错误窗口），不静默纠正
        self._set_tunable("top_n", "45")
        with self.assertRaises(ValueError) as ctx:
            self.app._collect_tunable_values()
        self.assertIn("推荐数量", str(ctx.exception))

    def test_collect_rejects_too_few_recommendations(self):
        self._set_tunable("top_n", "3")
        with self.assertRaises(ValueError) as ctx:
            self.app._collect_tunable_values()
        self.assertIn("推荐数量", str(ctx.exception))

    def test_collect_rejects_blank_parameter(self):
        self._set_tunable("top_n", "")
        with self.assertRaises(ValueError):
            self.app._collect_tunable_values()

    def test_collect_accepts_valid_parameters(self):
        self._set_tunable("top_n", "20")
        values = self.app._collect_tunable_values()
        self.assertEqual(values["top_n"], 20.0)


class ValidateTunableTests(unittest.TestCase):
    def test_accepts_value_inside_range(self):
        self.assertEqual(validate_tunable("推荐数量", "20", 5, 30), 20.0)

    def test_rejects_blank_with_helpful_message(self):
        with self.assertRaises(ValueError) as ctx:
            validate_tunable("推荐数量", "   ", 5, 30)
        self.assertIn("不能为空", str(ctx.exception))
        self.assertIn("5", str(ctx.exception))
        self.assertIn("30", str(ctx.exception))

    def test_rejects_non_numeric(self):
        with self.assertRaises(ValueError) as ctx:
            validate_tunable("量比下限", "abc", 0.5, 5.0)
        self.assertIn("数字", str(ctx.exception))

    def test_rejects_non_finite_numeric_text(self):
        for raw in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError) as ctx:
                    validate_tunable("推荐数量", raw, 5, 30)
                self.assertIn("数字", str(ctx.exception))

    def test_rejects_below_minimum(self):
        with self.assertRaises(ValueError) as ctx:
            validate_tunable("推荐数量", "4", 5, 30)
        self.assertIn("5", str(ctx.exception))

    def test_rejects_above_maximum(self):
        with self.assertRaises(ValueError) as ctx:
            validate_tunable("推荐数量", "31", 5, 30)
        self.assertIn("30", str(ctx.exception))

    def test_recommendation_count_bounds_are_five_to_thirty(self):
        top_n = next(p for p in get_preset("momentum_strong").tunables if p.key == "top_n")
        self.assertEqual((top_n.minimum, top_n.maximum), (5, 30))


if __name__ == "__main__":
    unittest.main()
