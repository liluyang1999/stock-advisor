import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from domain.money import (
    CENT,
    ZERO_MONEY,
    parse_money,
    positive_money,
    quantize_money,
    scaled_price,
    to_money,
)


class QuantizeMoneyTests(unittest.TestCase):
    def test_uses_half_up_not_pythons_default_bankers_rounding(self):
        # ADR-0013 选的是金额习惯的四舍五入，而 Decimal 默认是银行家舍入（ROUND_HALF_EVEN）。
        # 以下两例正是二者分道扬镳之处：银行家舍入会给 0.00 与 0.02。
        self.assertEqual(quantize_money(Decimal("0.005")), Decimal("0.01"))
        self.assertEqual(quantize_money(Decimal("0.025")), Decimal("0.03"))

    def test_negative_amounts_round_away_from_zero(self):
        self.assertEqual(quantize_money(Decimal("-0.005")), Decimal("-0.01"))

    def test_result_always_has_exactly_two_places(self):
        # "金额与价格统一两位小数" 是全工程约定，量化后一律以 CENT 为标度。
        for raw in ("3", "3.1", "3.14159", "-0.001", "1234567.891"):
            with self.subTest(raw=raw):
                self.assertEqual(quantize_money(Decimal(raw)).as_tuple().exponent, -2)
        self.assertEqual(CENT, Decimal("0.01"))
        self.assertEqual(ZERO_MONEY, Decimal("0.00"))


class ToMoneyTests(unittest.TestCase):
    def test_float_goes_through_repr_so_binary_expansion_cannot_shift_the_cent(self):
        # float 直接喂给 Decimal 会带进二进制展开（2.675 实为 2.67499999…），在半分边界上
        # 会把答案推向错误的一侧：Decimal(2.675) 量化得 2.67，而 repr 路径得 2.68。
        self.assertEqual(to_money(2.675), Decimal("2.68"))
        self.assertNotEqual(to_money(2.675), quantize_money(Decimal(2.675)))
        self.assertEqual(to_money(10.1), Decimal("10.10"))

    def test_accepts_decimal_int_and_str(self):
        self.assertEqual(to_money(Decimal("3")), Decimal("3.00"))
        self.assertEqual(to_money(7), Decimal("7.00"))
        self.assertEqual(to_money("2.5"), Decimal("2.50"))


class ParseMoneyTests(unittest.TestCase):
    def test_rejects_missing_blank_and_unparseable(self):
        for raw in (None, "", "   ", "-", "abc", "1.2.3"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_money(raw))

    def test_rejects_bool_even_though_bool_is_an_int(self):
        # Python 的 bool 是 int 的子类；少了显式防御，True 会被静默解析成 1.00。
        self.assertIsNone(parse_money(True))
        self.assertIsNone(parse_money(False))

    def test_rejects_non_finite_from_every_input_type(self):
        for raw in (float("inf"), float("-inf"), float("nan"), Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_money(raw))

    def test_parses_each_accepted_type_to_two_places(self):
        for raw, expected in (
            ("10.1", "10.10"),
            (" 10.1 ", "10.10"),
            (10.1, "10.10"),
            (10, "10.00"),
            (Decimal("10.1"), "10.10"),
            ("-3.456", "-3.46"),
        ):
            with self.subTest(raw=raw):
                parsed = parse_money(raw)
                self.assertEqual(parsed, Decimal(expected))
                assert parsed is not None
                self.assertEqual(parsed.as_tuple().exponent, -2)


class PositiveMoneyTests(unittest.TestCase):
    def test_rejects_zero_and_negative(self):
        for raw in (0, "0", "0.00", -5, "-0.01"):
            with self.subTest(raw=raw):
                self.assertIsNone(positive_money(raw))

    def test_rejects_what_parse_money_rejects(self):
        for raw in (None, "", "-", "abc", True, float("nan")):
            with self.subTest(raw=raw):
                self.assertIsNone(positive_money(raw))

    def test_accepts_positive(self):
        self.assertEqual(positive_money(12.5), Decimal("12.50"))


class ScaledPriceTests(unittest.TestCase):
    def test_eastmoney_scaled_int_stays_exact(self):
        # 东财返回的是整数标度价（如 f43 = 价格×100）；源是整数、除数是 10 的幂，
        # Decimal 除法精确，入口即不失真。
        self.assertEqual(scaled_price(1010, 100), Decimal("10.10"))
        self.assertEqual(scaled_price(1234567, 1000), Decimal("1234.57"))
        self.assertEqual(scaled_price("1010", 100), Decimal("10.10"))
        self.assertEqual(scaled_price(0, 100), ZERO_MONEY)

    def test_rejects_missing_bool_and_unparseable(self):
        for raw in (None, True, False, "abc", ""):
            with self.subTest(raw=raw):
                self.assertIsNone(scaled_price(raw, 100))

    def test_rejects_non_finite(self):
        self.assertIsNone(scaled_price(float("nan"), 100))
        self.assertIsNone(scaled_price(float("inf"), 100))


if __name__ == "__main__":
    unittest.main()
