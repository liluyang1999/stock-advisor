"""input_validate.py 可选数值解析器的行为锁定测试（空串 / 非数字 → None）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from domain.input_validate import (
    parse_alert_threshold,
    parse_optional_positive,
    parse_optional_positive_int,
)


class OptionalNumberParsingTests(unittest.TestCase):
    def testparse_optional_positive_none_for_blank_or_non_numeric(self):
        self.assertIsNone(parse_optional_positive(""))  # 空串
        self.assertIsNone(parse_optional_positive("   "))  # 纯空白
        self.assertIsNone(parse_optional_positive("abc"))  # 非数字
        # 正常正数仍照常解析（锚定“空/非数才 None”的口径）。
        self.assertEqual(parse_optional_positive("3.5"), 3.5)

    def testparse_optional_positive_int_none_for_blank_or_non_numeric(self):
        self.assertIsNone(parse_optional_positive_int(""))
        self.assertIsNone(parse_optional_positive_int("abc"))
        self.assertEqual(parse_optional_positive_int("7"), 7)

    def testparse_alert_threshold_none_for_non_numeric(self):
        self.assertIsNone(parse_alert_threshold("abc"))
        # 阈值允许负数/零，只要求有限数字。
        self.assertEqual(parse_alert_threshold("-3"), -3.0)


if __name__ == "__main__":
    unittest.main()
