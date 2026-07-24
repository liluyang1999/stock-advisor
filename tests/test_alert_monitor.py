"""预警监控编排契约（REQ-006/010 / WI-016 / TEST-QT-ALERT-001 的框架无关半）。

边沿触发 check_rules 是纯函数；这里测一层薄编排 run_alert_cycle——刷新各 code 的分析、跑边沿触发、
推进 fired 状态、隔离单只刷新失败（一条规则/一只失败不停监控，REQ-010）。QTimer 驱动另测。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_engine import FakeProvider

from domain.models import AlertRule
from services.alert_monitor import run_alert_cycle


class _FlakyProvider(FakeProvider):
    """指定 code 的 fetch_quote 抛错，模拟单只刷新失败。"""

    def __init__(self, fail_codes=None):
        super().__init__(fail_codes=fail_codes)


def _rule(code, field="price", op=">=", threshold=5.0):
    return AlertRule(code=code, field=field, op=op, threshold=threshold, enabled=True)


class RunAlertCycleTests(unittest.TestCase):
    def test_edge_trigger_fires_once_then_stays_quiet(self):
        # price=10.00 >= 5 恒真：第一轮触发，第二轮已在 fired 集合里，不再重复触发。
        rules = [_rule("sh600519", threshold=5.0)]
        newly1, fired1 = run_alert_cycle(rules, FakeProvider(), fired=set())
        self.assertEqual(len(newly1), 1)
        newly2, fired2 = run_alert_cycle(rules, FakeProvider(), fired=fired1)
        self.assertEqual(newly2, [])  # 边沿已触发，不重复
        self.assertEqual(fired1, fired2)

    def test_condition_false_does_not_fire(self):
        rules = [_rule("sh600519", op="<=", threshold=1.0)]  # price=10 <= 1 假
        newly, fired = run_alert_cycle(rules, FakeProvider(), fired=set())
        self.assertEqual(newly, [])
        self.assertEqual(fired, set())

    def test_single_symbol_failure_never_stops_monitoring(self):
        # 一只刷新失败，其余规则仍应被评估（REQ-010）。
        rules = [_rule("sh600519", threshold=5.0), _rule("sz000001", threshold=5.0)]
        provider = _FlakyProvider(fail_codes={"sh600519"})
        newly, fired = run_alert_cycle(rules, provider, fired=set())
        codes = {r.code for r in newly}
        self.assertIn("sz000001", codes)  # 未失败的那只照常触发
        self.assertNotIn("sh600519", codes)  # 失败的那只不触发也不崩

    def test_disabled_rule_resets_and_never_fires(self):
        rule = AlertRule(code="sh600519", field="price", op=">", threshold=5.0, enabled=False)
        newly, fired_out = run_alert_cycle([rule], FakeProvider(), fired=set())
        self.assertEqual(newly, [])
        self.assertEqual(fired_out, set())

    def test_empty_rules_is_a_quiet_no_op(self):
        newly, fired = run_alert_cycle([], FakeProvider(), fired=set())
        self.assertEqual(newly, [])
        self.assertEqual(fired, set())


if __name__ == "__main__":
    unittest.main()
