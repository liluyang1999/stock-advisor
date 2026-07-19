"""离线故障注入矩阵（REQ-023/024/025/026 / WI-020 / TEST-NET-002）。

对个股分析、资金流、全市场选股三条取数路径注入完整故障矩阵——超时 / DNS / 连接拒绝 / 响应不满足
契约（malformed）/ 部分缺失（partial）——断言每一格都满足**文档化契约**：

1. **零未处理异常**：服务对每种故障都正常返回一个可展示结果，绝不把裸异常抛给调用方/GUI 线程。
2. **零伪造**（REQ-024）：数据取不到时结果是「错误/降级」而非伪造的零价/空流/假建议——不无中生有。
3. **可见降级**：失败进入结果的 error 或 degraded 标志，用户看得到，而非静默吞掉。
4. **结构化日志**：每格都发一条带正确 `error_class`（network/parse）的 NDJSON 日志（OBSERVABILITY.md）。
"""

import io
import json
import logging
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_engine import fake_quote

from stock_advisor.data.data_provider import MarketDataError
from stock_advisor.domain.models import FundFlow
from stock_advisor.domain.presets import apply_tunables, default_values, get_preset
from stock_advisor.domain.symbols import normalize_symbol
from stock_advisor.observability import JsonLinesFormatter
from stock_advisor.services.fund_flow import fetch_fund_flow_result
from stock_advisor.services.workflow import analyze_symbol, screen_and_recommend

# 网络类故障：连通/超时/拒绝层面，归 error_class=network（OBSERVABILITY.md 错误分类法）。
_NETWORK_FAULTS = {
    "timeout": MarketDataError("读取超时（3000ms）"),
    "dns": MarketDataError("DNS 解析失败"),
    "refused": MarketDataError("连接被拒绝"),
    "http_5xx": MarketDataError("HTTP 503 服务不可用"),
    "http_429": MarketDataError("HTTP 429 限流"),
}
# parse 类故障：已连通但内容不满足契约（malformed/字段缺失/截断），归 error_class=parse。
_PARSE_FAULTS = {
    "malformed_json": ValueError("响应不是合法 JSON"),
    "missing_field": ValueError("必需字段 price 缺失"),
    "truncated": ValueError("分页计数与返回行数不一致"),
}


@contextmanager
def _capture_logs():
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setLevel(logging.INFO)
    handler.setFormatter(JsonLinesFormatter())
    logger = logging.getLogger("stock_advisor")
    saved = (list(logger.handlers), logger.level, logger.propagate)
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield lambda: [json.loads(line) for line in buffer.getvalue().splitlines() if line]
    finally:
        logger.handlers, logger.level, logger.propagate = saved


class _FaultProvider:
    """按注入的异常在指定取数点失败，其余点返回最小可用数据。"""

    def __init__(self, *, quote=None, history=None, flow=None, snapshot=None):
        self._quote = quote
        self._history = history
        self._flow = flow
        self._snapshot = snapshot

    def fetch_quote(self, symbol):
        if self._quote is not None:
            raise self._quote
        return fake_quote(symbol)

    def fetch_history(self, symbol):
        if self._history is not None:
            raise self._history
        return []

    def fetch_fund_flow(self, symbol, limit=6):
        if self._flow is not None:
            raise self._flow
        return FundFlow(today_main=1.0e8, main_5d=2.0e8, recent=[])

    def fetch_market_snapshot(self, page_size=1000, max_pages=12):
        if self._snapshot is not None:
            raise self._snapshot
        return []


_SYMBOL = normalize_symbol("600519")


class QuoteFetchFaultMatrixTests(unittest.TestCase):
    """个股实时行情取数：每种故障都不可分析（零伪造）+ 结构化日志，绝不外抛。"""

    def _assert_degraded_not_fabricated(self, fault, expected_class):
        with _capture_logs() as logs:
            outcome = analyze_symbol(_SYMBOL, _FaultProvider(quote=fault))  # 绝不外抛
        self.assertFalse(outcome.ok)  # 不可分析
        self.assertIsNone(outcome.result)  # 零伪造：没有假结果
        self.assertTrue(outcome.error)  # 可见错误
        classes = {e.get("error_class") for e in logs()}
        self.assertIn(expected_class, classes)  # 结构化日志带正确 error_class

    def test_network_faults_degrade_and_log_network(self):
        for name, fault in _NETWORK_FAULTS.items():
            with self.subTest(fault=name):
                self._assert_degraded_not_fabricated(fault, "network")

    def test_parse_faults_degrade_and_log_parse(self):
        for name, fault in _PARSE_FAULTS.items():
            with self.subTest(fault=name):
                self._assert_degraded_not_fabricated(fault, "parse")


class HistoryDegradationTests(unittest.TestCase):
    """历史日线取不到不致命：降级为实时价格保守判断（真实降级，非伪造历史）。"""

    def test_history_fault_degrades_but_still_analyzes(self):
        for name, fault in {**_NETWORK_FAULTS, **_PARSE_FAULTS}.items():
            with self.subTest(fault=name):
                with _capture_logs() as logs:
                    outcome = analyze_symbol(_SYMBOL, _FaultProvider(history=fault))
                self.assertTrue(outcome.ok)  # 仍可出结论（实时价格保守判断）
                self.assertTrue(outcome.degraded)  # 但明确标降级
                self.assertTrue(outcome.quality.degradations)  # 降级原因可见
                ops = {e.get("operation") for e in logs()}
                self.assertIn("analyze_symbol.history", ops)  # 记了降级日志


class FundFlowFaultMatrixTests(unittest.TestCase):
    """资金流是可失败辅助通道：每种故障都收敛成可展示 error，绝不外抛、绝不伪造流向。"""

    def _assert_contained(self, fault, expected_class):
        with _capture_logs() as logs:
            result = fetch_fund_flow_result("600519", _FaultProvider(flow=fault))  # 绝不外抛
        self.assertFalse(result.ok)
        self.assertIsNone(result.flow)  # 零伪造：没有假资金流
        self.assertTrue(result.error)
        self.assertIn(expected_class, {e.get("error_class") for e in logs()})

    def test_network_faults_are_contained(self):
        for name, fault in _NETWORK_FAULTS.items():
            with self.subTest(fault=name):
                self._assert_contained(fault, "network")

    def test_parse_faults_are_contained(self):
        for name, fault in _PARSE_FAULTS.items():
            with self.subTest(fault=name):
                self._assert_contained(fault, "parse")

    def test_unexpected_exception_is_contained_as_unknown(self):
        with _capture_logs() as logs:
            result = fetch_fund_flow_result("600519", _FaultProvider(flow=RuntimeError("爆炸")))
        self.assertFalse(result.ok)
        self.assertIsNone(result.flow)
        self.assertIn("unknown", {e.get("error_class") for e in logs()})


class ScreenerFaultMatrixTests(unittest.TestCase):
    """全市场选股：首段快照拉取失败即明确报错（零伪造推荐），绝不外抛 + 结构化日志。"""

    @staticmethod
    def _criteria_and_top():
        preset = get_preset("momentum_strong")
        criteria, top_n = apply_tunables(preset, default_values(preset))
        return criteria, preset.objective, top_n

    def _assert_error_not_fabricated(self, fault, expected_class):
        criteria, objective, top_n = self._criteria_and_top()
        with _capture_logs() as logs:
            report = screen_and_recommend(
                _FaultProvider(snapshot=fault), criteria, objective, top_n=top_n
            )  # 绝不外抛
        self.assertFalse(report.ok)  # 明确失败
        self.assertEqual(report.recommendations, [])  # 零伪造：没有假推荐
        self.assertTrue(report.error)
        self.assertIn(expected_class, {e.get("error_class") for e in logs()})

    def test_network_snapshot_faults_report_error(self):
        for name, fault in _NETWORK_FAULTS.items():
            with self.subTest(fault=name):
                self._assert_error_not_fabricated(fault, "network")

    def test_parse_snapshot_faults_report_error(self):
        for name, fault in _PARSE_FAULTS.items():
            with self.subTest(fault=name):
                self._assert_error_not_fabricated(fault, "parse")


class ZeroUnhandledExceptionSweepTests(unittest.TestCase):
    """整张矩阵一遍：没有任何一格把裸异常抛出——这是"零未处理异常"的总扫。"""

    def test_no_fault_ever_escapes_any_path(self):
        all_faults = {**_NETWORK_FAULTS, **_PARSE_FAULTS, "unexpected": RuntimeError("爆炸")}
        with _capture_logs():  # 把 exc_info 日志收进 buffer，避免污染测试控制台
            for name, fault in all_faults.items():
                with self.subTest(fault=name):
                    # analyze_symbol（quote 失败 / history 失败）与 fund_flow 三条路径都不外抛。
                    analyze_symbol(_SYMBOL, _FaultProvider(quote=fault))
                    analyze_symbol(_SYMBOL, _FaultProvider(history=fault))
                    fetch_fund_flow_result("600519", _FaultProvider(flow=fault))


if __name__ == "__main__":
    unittest.main()
