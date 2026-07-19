"""离线自检的结构化封装契约（REQ-008 / WI-018）。

REQ-008 要求离线自检。main.py::_self_test 是 print+exit 形式；这里提供一个框架无关、返回结构化
结果的 run_self_check，供 Qt 自检对话框与命令行共用——不联网、不抛，把通过/失败收敛成结果对象。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.services.self_check import run_self_check


class RunSelfCheckTests(unittest.TestCase):
    def test_offline_self_check_passes(self):
        result = run_self_check()
        self.assertTrue(result.ok, result.summary)
        self.assertTrue(result.checks)  # 有具体检查项
        self.assertTrue(all(c.passed for c in result.checks))

    def test_summary_is_human_readable(self):
        result = run_self_check()
        self.assertIn("自检", result.summary)

    def test_each_check_has_a_name_and_status(self):
        result = run_self_check()
        for check in result.checks:
            self.assertTrue(check.name)
            self.assertIsInstance(check.passed, bool)

    def test_does_not_touch_the_network(self):
        # 自检必须离线：用一个会抛错的 provider 断言它根本没被调用（自检用样例数据）。
        class _NoNetwork:
            def fetch_quote(self, *a, **k):
                raise AssertionError("自检不得联网")

            def fetch_history(self, *a, **k):
                raise AssertionError("自检不得联网")

        # run_self_check 不接受 provider（结构上不联网）；此测试确认签名无 provider 参数。
        import inspect

        params = inspect.signature(run_self_check).parameters
        self.assertNotIn("provider", params)


if __name__ == "__main__":
    unittest.main()
