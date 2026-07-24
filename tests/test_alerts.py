import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from domain.alerts import (
    FIELD_KEYS_BY_LABEL,
    FIELD_LABELS,
    check_rules,
    evaluate_rule,
    rule_key,
    rule_summary,
)
from domain.models import AlertRule


class FakeResult:
    def __init__(self, last, change_pct, score):
        self.last = last
        self.change_pct = change_pct
        self.score = score


def rule(code="sh600519", field="price", op=">=", threshold=100.0, enabled=True):
    return AlertRule(code, field, op, threshold, enabled)


class AlertsTests(unittest.TestCase):
    def test_evaluate_price_ge(self):
        self.assertTrue(evaluate_rule(rule(threshold=100), FakeResult(101, 1, 10)))
        self.assertFalse(evaluate_rule(rule(threshold=100), FakeResult(99, 1, 10)))

    def test_evaluate_change_le(self):
        self.assertTrue(
            evaluate_rule(rule(field="change_pct", op="<=", threshold=-3), FakeResult(10, -5, 0))
        )
        self.assertFalse(
            evaluate_rule(rule(field="change_pct", op="<=", threshold=-3), FakeResult(10, -1, 0))
        )

    def test_evaluate_score(self):
        self.assertTrue(
            evaluate_rule(rule(field="score", op=">=", threshold=25), FakeResult(10, 1, 30))
        )

    def test_evaluate_rule_ignores_non_finite_values_and_thresholds(self):
        self.assertFalse(evaluate_rule(rule(threshold=100), FakeResult(float("inf"), 1, 10)))
        self.assertFalse(
            evaluate_rule(rule(field="change_pct", threshold=1), FakeResult(10, float("nan"), 10))
        )
        self.assertFalse(
            evaluate_rule(rule(field="score", threshold=25), FakeResult(10, 1, float("inf")))
        )
        self.assertFalse(evaluate_rule(rule(threshold=float("nan")), FakeResult(101, 1, 10)))
        self.assertFalse(evaluate_rule(rule(threshold=float("inf")), FakeResult(101, 1, 10)))

    def test_evaluate_none_result_or_bad_field(self):
        self.assertFalse(evaluate_rule(rule(), None))
        self.assertFalse(evaluate_rule(rule(field="bogus"), FakeResult(10, 1, 10)))

    def test_check_rules_edge_trigger_once_then_rearm(self):
        r = rule(field="price", op=">=", threshold=100)
        newly, fired = check_rules([r], {"sh600519": FakeResult(101, 1, 10)}, set())
        self.assertEqual(newly, [r])
        self.assertIn(rule_key(r), fired)

        newly2, fired2 = check_rules([r], {"sh600519": FakeResult(102, 1, 10)}, fired)
        self.assertEqual(newly2, [])  # 仍为真，不再触发

        newly3, fired3 = check_rules([r], {"sh600519": FakeResult(98, 1, 10)}, fired2)
        self.assertEqual(newly3, [])
        self.assertNotIn(rule_key(r), fired3)  # 回落复位

        newly4, _ = check_rules([r], {"sh600519": FakeResult(101, 1, 10)}, fired3)
        self.assertEqual(newly4, [r])  # 再次越线再次触发

    def test_check_rules_skips_missing_result(self):
        newly, fired = check_rules([rule()], {}, set())
        self.assertEqual(newly, [])
        self.assertEqual(fired, set())

    def test_check_rules_ignores_disabled(self):
        newly, _ = check_rules([rule(enabled=False)], {"sh600519": FakeResult(101, 1, 10)}, set())
        self.assertEqual(newly, [])

    def test_disabled_rule_resets_fired_state_for_reenable(self):
        enabled = rule(field="price", op=">=", threshold=100, enabled=True)
        disabled = rule(field="price", op=">=", threshold=100, enabled=False)
        key = rule_key(enabled)

        newly, fired = check_rules([disabled], {"sh600519": FakeResult(101, 1, 10)}, {key})

        self.assertEqual(newly, [])
        self.assertNotIn(key, fired)

        newly2, fired2 = check_rules([enabled], {"sh600519": FakeResult(101, 1, 10)}, fired)
        self.assertEqual(newly2, [enabled])
        self.assertIn(key, fired2)

    def test_rule_summary(self):
        summary = rule_summary(rule(field="price", op=">=", threshold=1700))
        self.assertIn("价格", summary)
        self.assertIn("1700", summary)
        self.assertIn(">=", summary)

    def test_evaluate_rule_false_for_unknown_operator(self):
        # op 既非 ">=" 也非 "<="（如历史遗留/损坏的 "=="）→ 不触发，安全返回 False。
        self.assertFalse(evaluate_rule(rule(op="=="), FakeResult(100, 1, 10)))

    def test_rule_summary_falls_back_to_raw_code_when_unnormalizable(self):
        # 代码无法规范化（非6位）时，摘要用原始 code 兜底而不抛错。
        summary = rule_summary(rule(code="notacode", field="price", op=">=", threshold=100))
        self.assertIn("notacode", summary)
        self.assertIn(">=", summary)

    def test_field_keys_by_label_maps_chinese_labels_back_to_english_keys(self):
        # 预警"字段"下拉展示 FIELD_LABELS 的中文值；添加规则时需要把选中的中文标签映射回
        # AlertRule.field 实际存储的英文键。FIELD_KEYS_BY_LABEL 就是这个反向映射表。
        self.assertEqual(
            FIELD_KEYS_BY_LABEL, {"价格": "price", "涨跌幅": "change_pct", "综合分": "score"}
        )
        for key, label in FIELD_LABELS.items():
            self.assertEqual(FIELD_KEYS_BY_LABEL[label], key)
        # 值域与 FIELD_LABELS 互为逆映射，一一对应、无遗漏。
        self.assertEqual(set(FIELD_KEYS_BY_LABEL.values()), set(FIELD_LABELS.keys()))
        self.assertEqual(set(FIELD_KEYS_BY_LABEL.keys()), set(FIELD_LABELS.values()))


if __name__ == "__main__":
    unittest.main()
