"""ui/ 纯 helper 契约（不依赖 Tk）：主题常量对比度、因子着色、输入校验。

由 WI-023 从原 test_ui_polish.py 抽出——那个文件随 Tk 生产层一并删除，但这些断言验证的是
框架无关的纯函数（ui/theme.py 常量、ui/view_format.py、domain/input_validate），在 PySide6 下
继续成立，故按 WI-002 的 pure_preserved 分类保留下来。

（原本还覆盖 ui/layout.py 的窗口几何/DPI 数学，那是 Tk 时代的死代码——Qt 原生处理 DPI 与窗口
居中，src 无任何调用方——随 WI-032 与 layout.py 一并移除。）
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from domain.input_validate import is_partial_number, validate_tunable
from domain.presets import get_preset
from ui.theme import (  # noqa: E402
    ACCENT,
    CARD_BG,
    COMMAND_BG,
    COMMAND_INK,
    COMMAND_MUTED_INK,
    DANGER_COLOR,
    INK,
    MUTED_INK,
    NEG_COLOR,
    PAGE_BG,
    POS_COLOR,
)
from ui.view_format import detail_line_tags


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)), reverse=True
    )
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
        self.assertNotIn(
            DANGER_COLOR.lower(), {POS_COLOR.lower(), NEG_COLOR.lower(), ACCENT.lower()}
        )


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
