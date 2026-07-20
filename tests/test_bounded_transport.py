"""有界 urllib 迁移适配器的合同矩阵（REQ-025 / REQ-026 / AC-006 / WI-026 / TEST-NET-001）。

DoD 点名的八种情形逐条覆盖：分页 / 429 / 5xx / DNS / TLS / 超时 / 截断 / 字段漂移，外加总 deadline、
协作取消与**零伪造回退**。

全部离线：注入一个假 opener 顶替 urlopen，因此每种故障都是确定性的，不靠碰运气撞真网络。时钟也注入，
deadline 相关断言不睡任何一秒。
"""

from __future__ import annotations

import json
import socket
import ssl
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.data.bounded_transport import (
    BoundedUrllibProvider,
    classify_exception,
)
from stock_advisor.domain.symbols import normalize_symbol
from stock_advisor.ports import Deadline, ManualCancel

SYMBOL = normalize_symbol("600000")


def _http_error(status: int, reason: str = "boom") -> urllib.error.HTTPError:
    """构造一个 HTTPError。

    fp 传 None 时 HTTPError 会自建一个临时文件，不关就会在测试输出里刷 ResourceWarning——
    断言看得见的噪声会让真正的警告淹掉，所以这里当场关掉。
    """
    error = urllib.error.HTTPError("http://x", status, reason, {}, None)  # type: ignore[arg-type]
    error.close()
    return error


class _FakeClock:
    """手动推进的单调时钟：deadline 的行为要能被断言，而不是靠 sleep 去等。"""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _Opener:
    """按调用顺序回放脚本：每项是要返回的 payload，或要抛出的异常。"""

    def __init__(self, *script: object) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, float]] = []

    def __call__(
        self, request: urllib.request.Request, timeout: float, encoding: str | None
    ) -> str:
        self.calls.append((request.full_url, timeout))
        item = self.script.pop(0) if self.script else Exception("脚本已用尽")
        if isinstance(item, BaseException):
            raise item
        return str(item)


def _quote_payload(price: str = "10.50") -> str:
    return json.dumps(
        {
            "data": {
                "f43": 1050,
                "f44": 1080,
                "f45": 1020,
                "f46": 1030,
                "f47": 12345,
                "f48": 1.0e8,
                "f57": "600000",
                "f58": "浦发银行",
                "f60": 1040,
                "f168": 1.2,
                "f170": 96,
            }
        }
    )


def _sina_quote_payload() -> str:
    """新浪实时行情：文本而非 JSON，字段按位取。"""
    parts = [
        "浦发银行",
        "10.40",
        "10.30",
        "10.50",
        "10.80",
        "10.20",
        "10.49",
        "10.51",
        "12345",
        "1.0e8",
    ]
    return 'var hq_str_sh600000="' + ",".join(parts) + '";'


def _clist_payload(codes: list[str], total: int) -> str:
    return json.dumps(
        {
            "data": {
                "total": total,
                "diff": [
                    {
                        "f12": code,
                        "f13": 1,
                        "f14": f"股票{code}",
                        "f2": 10.5,
                        "f3": 1.2,
                        "f4": 0.12,
                        "f5": 100000,
                        "f6": 1.0e8,
                        "f7": 1.5,
                        "f8": 2.0,
                        "f9": 15.0,
                        "f10": 1.8,
                        "f20": 1.0e10,
                        "f21": 8.0e9,
                        "f22": 0.5,
                        "f23": 1.2,
                        "f24": 3.0,
                        "f25": 5.0,
                    }
                    for code in codes
                ],
            }
        }
    )


class ErrorClassificationTests(unittest.TestCase):
    """分类的分界线是"换个源还有没有希望"。"""

    def test_http_status_errors_are_network(self):
        for status in (429, 500, 502, 503, 403):
            error = urllib.error.HTTPError("http://x", status, "boom", {}, None)  # type: ignore[arg-type]
            self.assertEqual(classify_exception(error), "network", status)

    def test_dns_failure_is_network(self):
        error = urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))

        self.assertEqual(classify_exception(error), "network")

    def test_tls_failure_is_network(self):
        self.assertEqual(classify_exception(ssl.SSLError(1, "handshake failure")), "network")
        self.assertEqual(classify_exception(ssl.CertificateError("hostname mismatch")), "network")

    def test_timeout_is_network(self):
        self.assertEqual(classify_exception(TimeoutError("timed out")), "network")
        self.assertEqual(classify_exception(urllib.error.URLError(TimeoutError())), "network")

    def test_truncated_json_is_parse_not_network(self):
        """截断的响应换源没用——同一份坏内容重取一遍还是坏的，不该浪费预算。"""
        try:
            json.loads('{"data": {"diff": [')
        except json.JSONDecodeError as exc:
            self.assertEqual(classify_exception(exc), "parse")
        else:
            self.fail("应当抛出 JSONDecodeError")

    def test_field_drift_is_parse(self):
        self.assertEqual(classify_exception(KeyError("f43")), "parse")
        self.assertEqual(classify_exception(ValueError("字段缺失")), "parse")


class QuoteContractTests(unittest.TestCase):
    def setUp(self):
        self.clock = _FakeClock()

    def _provider(self, *script: object) -> tuple[BoundedUrllibProvider, _Opener]:
        opener = _Opener(*script)
        provider = BoundedUrllibProvider(
            budget_seconds=10.0, clock=self.clock, opener=opener, request_timeout=8.0
        )
        return provider, opener

    def test_primary_source_success_never_touches_the_fallback(self):
        provider, opener = self._provider(_quote_payload())

        outcome = provider.fetch_quote(SYMBOL)

        self.assertTrue(outcome.succeeded)
        self.assertIsNotNone(outcome.data)
        self.assertEqual(outcome.attempts, ("eastmoney",))
        self.assertEqual(len(opener.calls), 1)

    def test_429_on_the_primary_falls_over_to_the_next_source(self):
        rate_limited = _http_error(429, "Too Many Requests")
        provider, _ = self._provider(rate_limited, _sina_quote_payload())

        outcome = provider.fetch_quote(SYMBOL)

        self.assertTrue(outcome.succeeded)
        self.assertEqual(outcome.attempts, ("eastmoney", "sina"))

    def test_5xx_on_every_source_fails_as_network_and_carries_no_data(self):
        boom = _http_error(503, "Service Unavailable")
        provider, _ = self._provider(boom, boom)

        outcome = provider.fetch_quote(SYMBOL)

        self.assertFalse(outcome.succeeded)
        self.assertEqual(outcome.error_class, "network")
        self.assertIsNone(outcome.data)  # 零伪造：失败的 envelope 结构上没有数据

    def test_truncated_payload_stops_immediately_instead_of_burning_the_fallback(self):
        """parse 类失败不换源：内容不合契约，换个主机拿到的还是同样的坏内容。"""
        provider, opener = self._provider('{"data": {"f43": ', _sina_quote_payload())

        outcome = provider.fetch_quote(SYMBOL)

        self.assertFalse(outcome.succeeded)
        self.assertEqual(outcome.error_class, "parse")
        self.assertEqual(outcome.attempts, ("eastmoney",))
        self.assertEqual(len(opener.calls), 1, "parse 失败后不该再试备用源")

    def test_dns_failure_falls_over(self):
        dns = urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
        provider, _ = self._provider(dns, _sina_quote_payload())

        outcome = provider.fetch_quote(SYMBOL)

        self.assertTrue(outcome.succeeded)
        self.assertEqual(outcome.attempts, ("eastmoney", "sina"))

    def test_tls_failure_falls_over(self):
        provider, _ = self._provider(ssl.SSLError(1, "handshake failure"), _sina_quote_payload())

        outcome = provider.fetch_quote(SYMBOL)

        self.assertTrue(outcome.succeeded)
        self.assertEqual(outcome.attempts, ("eastmoney", "sina"))


class DeadlineContractTests(unittest.TestCase):
    """一个总预算覆盖所有源——不是每个源都重新拿一份完整预算（ADR-0003）。"""

    def setUp(self):
        self.clock = _FakeClock()

    def test_budget_exhausted_between_sources_stops_the_chain(self):
        clock = self.clock

        def slow_then_fine(request, timeout, encoding):
            clock.advance(6.0)  # 第一个源烧掉 6 秒
            raise urllib.error.URLError(TimeoutError())

        provider = BoundedUrllibProvider(budget_seconds=5.0, clock=clock, opener=slow_then_fine)

        outcome = provider.fetch_quote(SYMBOL)

        self.assertFalse(outcome.succeeded)
        self.assertEqual(outcome.error_class, "network")
        self.assertIn("deadline", outcome.message)
        self.assertEqual(outcome.attempts, ("eastmoney",), "预算耗尽后不该再开新源")

    def test_per_request_timeout_is_clamped_to_the_remaining_budget(self):
        """剩余预算比单次上界还小时，socket 超时必须跟着缩——否则最后一个源能独自超出总预算。"""
        opener = _Opener(_quote_payload())
        provider = BoundedUrllibProvider(
            budget_seconds=2.0, request_timeout=8.0, clock=self.clock, opener=opener
        )

        provider.fetch_quote(SYMBOL)

        _, timeout = opener.calls[0]
        self.assertLessEqual(timeout, 2.0)

    def test_a_shared_deadline_spans_separate_calls(self):
        """调用方可以传入同一个 deadline，让整批取数共用一个预算。"""
        deadline = Deadline.start(5.0, clock=self.clock)
        opener = _Opener(_quote_payload())
        provider = BoundedUrllibProvider(clock=self.clock, opener=opener)

        self.clock.advance(6.0)  # 预算在第一次调用前就已耗尽
        outcome = provider.fetch_quote(SYMBOL, deadline=deadline)

        self.assertFalse(outcome.succeeded)
        self.assertEqual(opener.calls, [], "预算已耗尽却仍发出了请求")


class CancellationContractTests(unittest.TestCase):
    def setUp(self):
        self.clock = _FakeClock()

    def test_cancelling_before_the_first_attempt_makes_no_request(self):
        opener = _Opener(_quote_payload())
        provider = BoundedUrllibProvider(clock=self.clock, opener=opener)
        cancel = ManualCancel()
        cancel.cancel()

        outcome = provider.fetch_quote(SYMBOL, cancel_token=cancel)

        self.assertFalse(outcome.succeeded)
        self.assertTrue(outcome.cancelled)
        self.assertIsNone(outcome.data)
        self.assertEqual(opener.calls, [])

    def test_cancelling_between_sources_stops_the_fallback_chain(self):
        cancel = ManualCancel()

        def fail_then_cancel(request, timeout, encoding):
            cancel.cancel()
            raise urllib.error.URLError(socket.gaierror(-2, "dns"))

        provider = BoundedUrllibProvider(clock=self.clock, opener=fail_then_cancel)

        outcome = provider.fetch_quote(SYMBOL, cancel_token=cancel)

        self.assertTrue(outcome.cancelled)
        self.assertEqual(outcome.attempts, ("eastmoney",))

    def test_cancellation_is_not_reported_as_a_data_error(self):
        """取消是结果状态，与错误分类正交——不能让用户看到"网络失败"的错误提示。"""
        cancel = ManualCancel()
        cancel.cancel()
        provider = BoundedUrllibProvider(clock=self.clock, opener=_Opener())

        outcome = provider.fetch_quote(SYMBOL, cancel_token=cancel)

        self.assertTrue(outcome.cancelled)
        self.assertEqual(outcome.message, "已取消")


class PagingCompletenessTests(unittest.TestCase):
    """分页是这个 WI 最实际的收获：残缺的全市场必须自报家门。"""

    def setUp(self):
        self.clock = _FakeClock()

    def _provider(self, *script: object) -> BoundedUrllibProvider:
        return BoundedUrllibProvider(budget_seconds=30.0, clock=self.clock, opener=_Opener(*script))

    def test_complete_paging_reports_complete(self):
        provider = self._provider(
            _clist_payload(["600000", "600001"], total=4),
            _clist_payload(["600002", "600003"], total=4),
        )

        outcome = provider.fetch_market_snapshot(page_size=2, max_pages=5)

        self.assertTrue(outcome.succeeded)
        self.assertEqual(len(outcome.data or []), 4)
        self.assertTrue(outcome.completeness.is_complete)
        self.assertEqual(outcome.completeness.expected, 4)
        self.assertEqual(outcome.completeness.received, 4)

    def test_a_failed_later_page_yields_partial_data_that_says_it_is_partial(self):
        """原实现在这里静默返回半个市场。现在数据照给，但完整度写明缺了哪一页。"""
        provider = self._provider(
            _clist_payload(["600000", "600001"], total=6),
            _http_error(500, "boom"),  # type: ignore[arg-type]
        )

        outcome = provider.fetch_market_snapshot(page_size=2, max_pages=5)

        self.assertTrue(outcome.succeeded)
        self.assertEqual(len(outcome.data or []), 2)
        self.assertFalse(outcome.completeness.is_complete, "残缺的全市场谎称完整")
        self.assertEqual(outcome.completeness.missing_pages, (2,))
        self.assertEqual(outcome.completeness.expected, 6)
        self.assertEqual(outcome.completeness.received, 2)

    def test_first_page_failure_falls_over_to_the_next_host(self):
        provider = self._provider(
            _http_error(503, "boom"),  # type: ignore[arg-type]
            _clist_payload(["600000"], total=1),
        )

        outcome = provider.fetch_market_snapshot(page_size=50, max_pages=3)

        self.assertTrue(outcome.succeeded)
        self.assertEqual(len(outcome.attempts), 2)

    def test_every_host_failing_carries_no_data(self):
        boom = _http_error(503, "boom")
        provider = self._provider(boom, boom)

        outcome = provider.fetch_market_snapshot(page_size=50, max_pages=2)

        self.assertFalse(outcome.succeeded)
        self.assertIsNone(outcome.data)
        self.assertEqual(outcome.error_class, "network")

    def test_duplicate_codes_across_pages_are_not_double_counted(self):
        provider = self._provider(
            _clist_payload(["600000", "600001"], total=3),
            _clist_payload(["600001", "600002"], total=3),
        )

        outcome = provider.fetch_market_snapshot(page_size=2, max_pages=4)

        codes = [row.code for row in outcome.data or []]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(len(codes), 3)

    def test_cancelling_mid_paging_records_the_pages_never_fetched(self):
        cancel = ManualCancel()
        payload = _clist_payload(["600000", "600001"], total=100)

        def one_page_then_cancel(request, timeout, encoding):
            cancel.cancel()
            return payload

        provider = BoundedUrllibProvider(
            budget_seconds=30.0, clock=self.clock, opener=one_page_then_cancel
        )

        outcome = provider.fetch_market_snapshot(page_size=2, max_pages=4, cancel_token=cancel)

        self.assertTrue(outcome.succeeded)  # 已取到的页照常交付
        self.assertFalse(outcome.completeness.is_complete)
        self.assertEqual(outcome.completeness.missing_pages, (2, 3, 4))


class FundFlowContractTests(unittest.TestCase):
    def setUp(self):
        self.clock = _FakeClock()

    def test_empty_flow_is_a_parse_failure_not_a_fabricated_zero(self):
        """资金流为空时不能返回一个全 0 的 FundFlow——那是把"没有数据"伪造成"净流入为零"。"""
        provider = BoundedUrllibProvider(
            clock=self.clock, opener=_Opener('{"data": null}', '{"data": null}')
        )

        outcome = provider.fetch_fund_flow(SYMBOL)

        self.assertFalse(outcome.succeeded)
        self.assertIsNone(outcome.data)


class HistoryContractTests(unittest.TestCase):
    def setUp(self):
        self.clock = _FakeClock()

    def test_empty_history_falls_through_every_source_then_fails_without_data(self):
        empty = json.dumps({"data": {"klines": []}})
        provider = BoundedUrllibProvider(
            clock=self.clock, opener=_Opener(empty, empty, empty, empty)
        )

        outcome = provider.fetch_history(SYMBOL, limit=30)

        self.assertFalse(outcome.succeeded)
        self.assertIsNone(outcome.data)

    def test_an_empty_primary_falls_over_rather_than_ending_the_chain(self):
        """空 ≠ 内容坏。第一个源没有数据时必须继续试备用源，否则备用源形同虚设。"""
        empty = json.dumps({"data": {"klines": []}})
        good = json.dumps({"data": {"klines": ["2026-06-01,10.00,10.50,10.60,9.90,1000,1.0e7"]}})
        provider = BoundedUrllibProvider(clock=self.clock, opener=_Opener(empty, good))

        outcome = provider.fetch_history(SYMBOL, limit=30)

        self.assertGreater(len(outcome.attempts), 1, "主源为空却没有继续试备用源")
        self.assertIn("sina", outcome.attempts)

    def test_a_malformed_primary_does_end_the_chain(self):
        """反过来，内容不合契约就该停——换源拿到的是同样的坏内容，重试只是烧预算。"""
        provider = BoundedUrllibProvider(
            clock=self.clock, opener=_Opener('{"data": {"klines": [', "irrelevant")
        )

        outcome = provider.fetch_history(SYMBOL, limit=30)

        self.assertFalse(outcome.succeeded)
        self.assertEqual(outcome.error_class, "parse")
        self.assertEqual(outcome.attempts, ("eastmoney",))


if __name__ == "__main__":
    unittest.main()
