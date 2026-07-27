"""domain.numeric 安全解析器的防御测试（数值纪律一致性）。

比率/百分比/评分/统计指标用 float，其安全解析器与 money.parse_money 遵循同一约定：
bool 是 int 的子类，必须显式拒绝，否则 True/False 会被静默当成 1.0/0.0。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from domain.numeric import (
    finite_float,
    nonnegative_finite_float,
    positive_finite_float,
    positive_finite_int,
    safe_int,
)


class FiniteFloatBoolGuardTests(unittest.TestCase):
    def test_finite_float_rejects_bool(self):
        self.assertIsNone(finite_float(True))
        self.assertIsNone(finite_float(False))

    def test_derived_parsers_reject_bool(self):
        self.assertIsNone(positive_finite_float(True))
        self.assertIsNone(nonnegative_finite_float(True))
        self.assertIsNone(positive_finite_int(True))

    def test_safe_int_falls_back_to_default_on_bool(self):
        self.assertEqual(safe_int(True, default=7), 7)
        self.assertEqual(safe_int(False, default=7), 7)

    def test_still_accepts_real_numbers_and_rejects_non_finite(self):
        self.assertEqual(finite_float(3), 3.0)
        self.assertEqual(finite_float("2.5"), 2.5)
        self.assertIsNone(finite_float(float("nan")))
        self.assertIsNone(finite_float("abc"))


if __name__ == "__main__":
    unittest.main()
