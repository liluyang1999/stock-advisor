"""网络传输 port/envelope 基础合同的故障矩阵测试（REQ-025/026 / ADR-0003 / WI-009 / TEST-NET-001）。

DoD：传输合同对 paging/429/5xx/DNS/TLS/timeout/truncation/field-drift 故障矩阵通过，零伪造回退。
本套件测的是**框架无关的合同逻辑**（ports.py），因此 QNAM 终态与 urllib 迁移桥两条路径共享同一
验证——ADR-0003 所说"两条路径都必须验证一致的 port/envelope"。全部离线、确定性、时钟可注入。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_advisor.ports import (
    Completeness,
    Deadline,
    ManualCancel,
    TransportError,
    TransportOutcome,
    classify_http_status,
    run_with_contract,
)


class _Clock:
    """可手动推进的单调时钟，使 deadline 行为完全确定。"""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _ok(label: str, value):
    return (label, lambda: value)


def _fault(label: str, error_class, message: str):
    def _raise():
        raise TransportError(error_class, message)

    return (label, _raise)


# 故障矩阵：每一类故障 -> 期望的 error_class（依 OBSERVABILITY 分类法）。
FAULT_MATRIX = {
    "http_429": ("network", _fault("eastmoney", "network", "429 Too Many Requests")),
    "http_503": ("network", _fault("eastmoney", "network", "503 Service Unavailable")),
    "dns": ("network", _fault("eastmoney", "network", "DNS 解析失败")),
    "tls": ("network", _fault("eastmoney", "network", "TLS 证书校验失败")),
    "timeout": ("network", _fault("eastmoney", "network", "读取超时")),
    "truncation": ("parse", _fault("eastmoney", "parse", "截断的 JSON 响应")),
    "field_drift": ("parse", _fault("eastmoney", "parse", "必需字段缺失/类型漂移")),
    "paging_mismatch": ("parse", _fault("eastmoney", "parse", "分页计数不一致")),
}


class HttpStatusClassificationTests(unittest.TestCase):
    def test_all_http_statuses_are_network_class(self):
        # OBSERVABILITY：network 含"HTTP 状态"，4xx/5xx 一律 network（内容契约错误另由 parse 抛）。
        for status in (400, 404, 408, 425, 429, 500, 502, 503):
            self.assertEqual(classify_http_status(status), "network")


class FaultMatrixTests(unittest.TestCase):
    """矩阵里的每种故障：单源即失败时，分类正确且失败结果不带数据。"""

    def _deadline(self):
        return Deadline.start(8.0, clock=_Clock())

    def test_each_fault_classifies_correctly_and_carries_no_data(self):
        for name, (expected_class, attempt) in FAULT_MATRIX.items():
            with self.subTest(fault=name):
                outcome = run_with_contract([attempt], deadline=self._deadline())
                self.assertFalse(outcome.succeeded, name)
                self.assertEqual(outcome.error_class, expected_class, name)
                self.assertIsNone(outcome.data, f"{name}: 失败结果竟带了数据（伪造回退）")

    def test_parse_faults_do_not_retry_other_sources(self):
        # parse（内容不满足契约）换源无意义：一旦某源 parse 失败，立即返回，不试后续源。
        attempts = [
            _fault("eastmoney", "parse", "截断的 JSON"),
            _ok("sina", ["不该走到这里"]),
        ]
        outcome = run_with_contract(attempts, deadline=self._deadline())
        self.assertFalse(outcome.succeeded)
        self.assertEqual(outcome.error_class, "parse")
        self.assertEqual(outcome.attempts, ("eastmoney",))  # sina 未被尝试

    def test_network_fault_falls_through_to_the_next_source(self):
        # 瞬时 network 错误才换下一个备用源；第二源成功即整体成功。
        attempts = [
            _fault("eastmoney", "network", "503"),
            _ok("sina", ["OK"]),
            _ok("tencent", ["不该走到这里"]),
        ]
        outcome = run_with_contract(attempts, deadline=self._deadline())
        self.assertTrue(outcome.succeeded)
        self.assertEqual(outcome.data, ["OK"])
        self.assertEqual(outcome.attempts, ("eastmoney", "sina"))  # tencent 未被尝试

    def test_all_sources_network_fail_returns_classified_failure_without_data(self):
        attempts = [
            _fault("eastmoney", "network", "503"),
            _fault("sina", "network", "超时"),
            _fault("tencent", "network", "断连"),
        ]
        outcome = run_with_contract(attempts, deadline=self._deadline())
        self.assertFalse(outcome.succeeded)
        self.assertEqual(outcome.error_class, "network")
        self.assertIsNone(outcome.data)
        self.assertEqual(outcome.attempts, ("eastmoney", "sina", "tencent"))


class DeadlineTests(unittest.TestCase):
    def test_expired_deadline_before_any_attempt_fails_network(self):
        clock = _Clock()
        deadline = Deadline.start(5.0, clock=clock)
        clock.advance(6.0)  # 预算已耗尽
        outcome = run_with_contract([_ok("eastmoney", [1])], deadline=deadline)
        self.assertFalse(outcome.succeeded)
        self.assertEqual(outcome.error_class, "network")
        self.assertIn("deadline", outcome.message)
        self.assertEqual(outcome.attempts, ())  # 一个源都没试

    def test_one_deadline_covers_all_sources_not_per_source(self):
        # ADR-0003：deadline 覆盖所有重试和备用源，不允许每源重获完整预算。
        clock = _Clock()
        deadline = Deadline.start(10.0, clock=clock)

        def slow_network_fail(label):
            def _raise():
                clock.advance(6.0)  # 每个源消耗 6s
                raise TransportError("network", f"{label} 超时")

            return (label, _raise)

        # 第一个源耗 6s（剩 4s），第二个源开始前 deadline 仍有 4s>0 会被试，它再耗 6s，
        # 第三个源开始前 deadline 已 -2s，必须不再尝试。
        attempts = [slow_network_fail("s1"), slow_network_fail("s2"), _ok("s3", [1])]
        outcome = run_with_contract(attempts, deadline=deadline)
        self.assertFalse(outcome.succeeded)
        self.assertEqual(outcome.attempts, ("s1", "s2"))  # s3 因总 deadline 耗尽未被尝试


class CancellationTests(unittest.TestCase):
    def test_cancel_before_attempt_returns_cancelled_without_data(self):
        cancel = ManualCancel()
        cancel.cancel()
        outcome = run_with_contract(
            [_ok("eastmoney", [1])],
            deadline=Deadline.start(8.0, clock=_Clock()),
            cancel_token=cancel,
        )
        self.assertFalse(outcome.succeeded)
        self.assertTrue(outcome.cancelled)
        self.assertIsNone(outcome.data)
        self.assertEqual(outcome.attempts, ())

    def test_cancel_between_sources_stops_the_chain(self):
        cancel = ManualCancel()

        def fail_then_cancel():
            cancel.cancel()  # 第一源失败后请求取消
            raise TransportError("network", "503")

        attempts = [("eastmoney", fail_then_cancel), _ok("sina", ["不该走到这里"])]
        outcome = run_with_contract(
            attempts, deadline=Deadline.start(8.0, clock=_Clock()), cancel_token=cancel
        )
        self.assertTrue(outcome.cancelled)
        self.assertEqual(outcome.attempts, ("eastmoney",))  # 取消后不再试 sina


class CompletenessTests(unittest.TestCase):
    def test_full_pages_is_complete(self):
        self.assertTrue(Completeness(expected=5, received=5).is_complete)
        self.assertTrue(Completeness().is_complete)  # 默认无分页信息即视为完整

    def test_missing_pages_or_short_count_is_incomplete(self):
        self.assertFalse(Completeness(expected=12, received=9).is_complete)
        self.assertFalse(Completeness(expected=5, received=5, missing_pages=(3,)).is_complete)

    def test_success_carries_completeness_through(self):
        outcome = run_with_contract(
            [_ok("eastmoney", ["rows"])],
            deadline=Deadline.start(8.0, clock=_Clock()),
            completeness=Completeness(expected=10, received=10),
        )
        self.assertTrue(outcome.succeeded)
        self.assertTrue(outcome.completeness.is_complete)


class ZeroFabricationStructuralTests(unittest.TestCase):
    def test_failed_constructor_has_no_way_to_carry_data(self):
        # 结构性保证：failed(...) 不接受 data 参数，失败 envelope 的 data 恒为 None。
        outcome = TransportOutcome.failed("network", "boom")
        self.assertIsNone(outcome.data)
        self.assertFalse(outcome.succeeded)


if __name__ == "__main__":
    unittest.main()
