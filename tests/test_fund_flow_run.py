"""资金流按需拉取包装契约（REQ-007 / WI-017）。

REQ-007：资金流独立、可失败、失败可见降级、不影响核心分析。`fetch_fund_flow` 全失败才抛；
这里测薄包装 fetch_fund_flow_result——把成功/失败都收敛成一个可展示的结果对象（失败带 error、
不抛、不进核心分析路径）。框架无关，可离线测。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data.data_provider import MarketDataError
from domain.models import FundFlow
from services.fund_flow import fetch_fund_flow_result


class _OkProvider:
    def fetch_fund_flow(self, symbol, limit=6):
        return FundFlow(today_main=1.5e8, main_5d=3.2e8, recent=[("2026-07-17", 1.5e8)])


class _FailProvider:
    def fetch_fund_flow(self, symbol, limit=6):
        raise MarketDataError("资金流获取失败：所有源均不可用")


class _CrashProvider:
    def fetch_fund_flow(self, symbol, limit=6):
        raise RuntimeError("意外崩溃")


class FetchFundFlowResultTests(unittest.TestCase):
    def test_success_carries_the_flow_and_no_error(self):
        result = fetch_fund_flow_result("600519", _OkProvider())
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.flow)
        self.assertEqual(result.error, "")

    def test_market_data_error_degrades_visibly_without_raising(self):
        result = fetch_fund_flow_result("600519", _FailProvider())
        self.assertFalse(result.ok)
        self.assertIsNone(result.flow)
        self.assertIn("资金流", result.error)  # 可见的降级说明

    def test_unexpected_exception_is_also_contained(self):
        # 任何异常都不得逃逸污染核心分析（REQ-007）。
        result = fetch_fund_flow_result("600519", _CrashProvider())
        self.assertFalse(result.ok)
        self.assertIsNone(result.flow)
        self.assertTrue(result.error)

    def test_invalid_symbol_is_a_contained_error(self):
        result = fetch_fund_flow_result("", _OkProvider())
        self.assertFalse(result.ok)
        self.assertTrue(result.error)


if __name__ == "__main__":
    unittest.main()
