import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from stock_advisor.domain.symbols import (
    _market_for_prefix,
    normalize_symbol,
    parse_user_symbols,
    symbol_from_market,
)


class SymbolParsingTests(unittest.TestCase):
    def test_normalize_common_a_share_codes(self):
        self.assertEqual(normalize_symbol("600519").normalized, "sh600519")
        self.assertEqual(normalize_symbol("000001").normalized, "sz000001")
        self.assertEqual(normalize_symbol("300750").normalized, "sz300750")
        self.assertEqual(normalize_symbol("688981").normalized, "sh688981")

    def test_beijing_exchange_new_920_code_segment_is_not_misread_as_shanghai(self):
        symbol = normalize_symbol("920083")
        self.assertEqual(symbol.prefix, "bj")
        self.assertEqual(symbol.exchange, "北京证券交易所")
        self.assertEqual(symbol.secid, "0.920083")
        # 沪市B股 900xxx 仍应判为沪市
        self.assertEqual(normalize_symbol("900957").prefix, "sh")

    def test_symbol_from_market_uses_authoritative_market_id_for_secid(self):
        sh = symbol_from_market("688981", "1")
        self.assertEqual(sh.secid, "1.688981")
        self.assertEqual(sh.prefix, "sh")
        bj = symbol_from_market("920083", 0)
        self.assertEqual(bj.secid, "0.920083")
        self.assertEqual(bj.prefix, "bj")
        sz = symbol_from_market("300750", "0")
        self.assertEqual(sz.secid, "0.300750")
        self.assertEqual(sz.prefix, "sz")

    def test_normalize_prefixed_codes(self):
        self.assertEqual(normalize_symbol("SH.600519").secid, "1.600519")
        self.assertEqual(normalize_symbol("sz000001").secid, "0.000001")

    def test_parse_user_symbols_removes_duplicates_in_order(self):
        parsed = parse_user_symbols("600519, 000001\n600519;300750")
        self.assertEqual([item.normalized for item in parsed], ["sh600519", "sz000001", "sz300750"])

    def test_parse_user_symbols_supports_limit_for_batch_safety(self):
        with self.assertRaisesRegex(ValueError, "最多"):
            parse_user_symbols("600519,000001,300750", max_count=2)

    def test_invalid_symbol_raises_helpful_error(self):
        with self.assertRaisesRegex(ValueError, "6位数字"):
            normalize_symbol("ABC")


class SymbolGuardTests(unittest.TestCase):
    """代码/市场号校验与交易所推断的错误分支（错误信息直接展示给用户，故锁定其可读性）。"""

    def test_symbol_from_market_rejects_non_six_digit_code(self):
        with self.assertRaisesRegex(ValueError, "6位数字"):
            symbol_from_market("123", "1")

    def test_symbol_from_market_rejects_unknown_market_id(self):
        with self.assertRaisesRegex(ValueError, "市场号"):
            symbol_from_market("123456", "9")

    def test_infer_prefix_maps_old_beijing_8_segment(self):
        # 8 开头是北交所老代码段（先于深市 0/2/3 判断）。
        self.assertEqual(normalize_symbol("830799").prefix, "bj")

    def test_normalize_raises_when_exchange_cannot_be_inferred(self):
        # 首位不属于任何已知段（1/5/7 开头）→ 无法推断交易所，提示用户加前缀。
        for code in ("500000", "700000"):
            with self.subTest(code=code):
                with self.assertRaisesRegex(ValueError, "推断"):
                    normalize_symbol(code)

    def test_parse_user_symbols_skips_empty_tokens_from_leading_separator(self):
        # 分隔符切出的空 token 被跳过，不影响其后的有效代码。
        self.assertEqual([s.normalized for s in parse_user_symbols(",600519")], ["sh600519"])

    def test_parse_user_symbols_requires_at_least_one_code(self):
        for text in ("", "   ", ",,"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "至少"):
                    parse_user_symbols(text)

    def test_market_for_prefix_rejects_unknown_prefix(self):
        # 私有守卫：normalize 只会喂入 sh/sz/bj，直测非法前缀的兜底报错。
        with self.assertRaisesRegex(ValueError, "不支持"):
            _market_for_prefix("xx")


if __name__ == "__main__":
    unittest.main()
