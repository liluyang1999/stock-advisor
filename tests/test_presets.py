import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from domain.models import TunableParam
from domain.presets import (
    PRESETS,
    _pair_label,
    apply_tunables,
    default_values,
    get_preset,
)
from domain.screener import OBJECTIVES


class PresetCatalogTests(unittest.TestCase):
    def test_six_presets_with_unique_keys_and_valid_objectives(self):
        self.assertEqual(len(PRESETS), 6)
        keys = [preset.key for preset in PRESETS]
        self.assertEqual(len(keys), len(set(keys)))
        for preset in PRESETS:
            self.assertIn(preset.objective, OBJECTIVES)
            self.assertTrue(preset.name and preset.description)

    def test_each_preset_exposes_tunables_including_top_n(self):
        for preset in PRESETS:
            keys = {param.key for param in preset.tunables}
            self.assertIn("top_n", keys)
            self.assertGreaterEqual(len(preset.tunables), 3)
            for param in preset.tunables:
                self.assertLessEqual(param.minimum, param.default)
                self.assertLessEqual(param.default, param.maximum)

    def test_get_preset_by_key(self):
        preset = get_preset("momentum_strong")
        self.assertEqual(preset.objective, "momentum")
        with self.assertRaises(KeyError):
            get_preset("does_not_exist")


class TunableApplicationTests(unittest.TestCase):
    def test_defaults_reproduce_baked_criteria(self):
        # 用每个预设暴露参数的默认值回填，应当还原预设自身的 criteria 与 top_n
        for preset in PRESETS:
            criteria, top_n = apply_tunables(preset, default_values(preset))
            self.assertEqual(criteria, preset.criteria, msg=f"{preset.key} 默认值未还原 criteria")
            self.assertEqual(top_n, preset.default_top_n)

    def test_override_changes_only_targeted_field(self):
        preset = get_preset("momentum_strong")
        criteria, _top_n = apply_tunables(preset, {"change_pct_min": 4.0})
        self.assertEqual(criteria.change_pct_min, 4.0)
        # 未触碰的字段维持预设原值
        self.assertEqual(criteria.volume_ratio_min, preset.criteria.volume_ratio_min)

    def test_amount_tunable_scales_from_yi_to_yuan(self):
        preset = get_preset("momentum_strong")
        criteria, _top_n = apply_tunables(preset, {"amount_min": 3.0})  # 3 亿
        self.assertEqual(criteria.amount_min, 3.0e8)

    def test_top_n_is_applied_and_floored_to_int(self):
        preset = get_preset("momentum_strong")
        _criteria, top_n = apply_tunables(preset, {"top_n": 12.6})
        self.assertEqual(top_n, 13)

    def test_non_finite_tunables_are_ignored(self):
        preset = get_preset("momentum_strong")
        criteria, top_n = apply_tunables(
            preset,
            {"amount_min": float("inf"), "change_pct_min": float("-inf"), "top_n": float("nan")},
        )

        self.assertEqual(criteria, preset.criteria)
        self.assertEqual(top_n, preset.default_top_n)

    def test_tunables_are_clamped_to_declared_bounds(self):
        preset = get_preset("momentum_strong")
        criteria, top_n = apply_tunables(
            preset,
            {"change_pct_min": -100.0, "amount_min": 9999.0, "top_n": 99.0},
        )

        self.assertEqual(criteria.change_pct_min, 0.0)
        self.assertEqual(criteria.amount_min, 50.0e8)
        self.assertEqual(top_n, 30)


class TunableCrossedBoundValidationTests(unittest.TestCase):
    """apply_tunables 只把每个可调项夹到自身 [min,max]，不该允许成对边界交叉
    （下限被调到高于上限，会让 screener._in_range 恒为空）。"""

    def test_change_pct_min_above_fixed_change_pct_max_raises_clear_error(self):
        preset = get_preset("momentum_strong")  # 固定 criteria.change_pct_max == 7.0
        with self.assertRaises(ValueError) as ctx:
            apply_tunables(preset, {"change_pct_min": 10.0})
        message = str(ctx.exception)
        self.assertIn("下限", message)
        self.assertIn("上限", message)
        self.assertIn("涨", message)  # 指名是涨幅相关边界，而非泛泛提示
        self.assertNotIn("放宽筛选", message)

    def test_turnover_min_above_turnover_max_raises_clear_error(self):
        preset = get_preset("activity_turnover")  # turnover_min(1~20) 与 turnover_max(10~60) 均可调
        with self.assertRaises(ValueError) as ctx:
            apply_tunables(preset, {"turnover_min": 20.0, "turnover_max": 10.0})
        message = str(ctx.exception)
        self.assertIn("下限", message)
        self.assertIn("上限", message)
        self.assertIn("换手", message)
        self.assertNotIn("放宽筛选", message)

    def test_non_crossed_tunables_still_apply_normally(self):
        preset = get_preset("momentum_strong")
        criteria, top_n = apply_tunables(preset, {"change_pct_min": 5.0})
        self.assertEqual(criteria.change_pct_min, 5.0)
        self.assertEqual(criteria.change_pct_max, 7.0)
        self.assertEqual(top_n, preset.default_top_n)

        turnover_preset = get_preset("activity_turnover")
        criteria2, _top_n2 = apply_tunables(
            turnover_preset, {"turnover_min": 8.0, "turnover_max": 15.0}
        )
        self.assertEqual(criteria2.turnover_min, 8.0)
        self.assertEqual(criteria2.turnover_max, 15.0)

    def test_equal_min_and_max_is_not_treated_as_crossed(self):
        # min == max 是合法（虽然狭窄）的区间，不应误判为交叉
        preset = get_preset("activity_turnover")
        criteria, _top_n = apply_tunables(preset, {"turnover_min": 12.0, "turnover_max": 12.0})
        self.assertEqual(criteria.turnover_min, 12.0)
        self.assertEqual(criteria.turnover_max, 12.0)


class TunableGuardTests(unittest.TestCase):
    def test_unknown_tunable_key_is_ignored(self):
        # values 里出现预设未暴露的键 → 跳过，不影响最终 criteria。
        preset = get_preset("momentum_strong")
        criteria, _top_n = apply_tunables(preset, {"not_a_real_key": 5.0})
        self.assertEqual(criteria, preset.criteria)

    def test_non_numeric_top_n_keeps_default(self):
        # top_n 非数字 → _finite_number 返回 None → 跳过，沿用预设默认 TopN。
        preset = get_preset("momentum_strong")
        _criteria, top_n = apply_tunables(preset, {"top_n": "abc"})
        self.assertEqual(top_n, preset.default_top_n)


class PairLabelTests(unittest.TestCase):
    """_pair_label 去掉标签的『下限/上限』方向后缀，避免报错消息里方向词重复。"""

    def test_strips_upper_bound_suffix(self):
        # 首个后缀『下限』不匹配→继续试『上限』→命中并去掉。
        param = TunableParam("k", "量比上限", "float", 1.0, 0.0, 5.0, "倍")
        self.assertEqual(_pair_label(param), "量比（倍）")

    def test_keeps_label_without_direction_suffix(self):
        # 标签不含方向后缀 → 循环走完不改动，原样加单位。
        param = TunableParam("k", "推荐数量", "int", 20.0, 5, 30, "只")
        self.assertEqual(_pair_label(param), "推荐数量（只）")


if __name__ == "__main__":
    unittest.main()
