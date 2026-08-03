"""编排层直接消费 `TransportOutcome`（REQ-024/025/026 · WI-033 的 DoD 收尾）。

此前编排层只看得见异常，于是两件事只能靠猜或者干脆丢失：

* **错误分类**靠 `isinstance(exc, MarketDataError)` 推断——是 `MarketDataError` 就记 network，否则记
  parse。可传输层自己早就分好类了（`run_with_contract` 按 network/parse/validation 归类），经异常一
  压扁就只剩"network 或 parse"两种猜测，日志里的 `error_class` 因此可能与真实原因不符。
* **取消**与失败无从区分：取消的取数同样抛 `MarketDataError`，界面只能说"获取失败"。全市场筛选的
  `ScreenReport` 明明有 `cancelled` 字段，却永远为 False。

现在编排层统一走 envelope：provider 提供 `<name>_outcome` 就直接用它的 envelope，老式 provider 与
测试替身仍按异常包成等价失败信封——**一条代码路径**，不必改 Protocol，也不必动任何 FakeProvider。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_engine import FakeProvider, fake_quote, make_history

from data.data_provider import MarketDataError
from domain.symbols import normalize_symbol
from ports import TransportOutcome
from services.workflow import analyze_symbol, screen_and_recommend

SYMBOL = normalize_symbol("600519")


class _EnvelopeProvider:
    """暴露 envelope 版取数口的 provider（出货适配器就是这个形状）。"""

    def __init__(self, quote_outcome=None, history_outcome=None, snapshot_outcome=None) -> None:
        self._quote = quote_outcome
        self._history = history_outcome
        self._snapshot = snapshot_outcome

    def fetch_quote_outcome(self, symbol):
        return self._quote or TransportOutcome.ok(fake_quote(symbol))

    def fetch_history_outcome(self, symbol, limit: int = 120):
        return self._history or TransportOutcome.ok(make_history())

    def fetch_market_snapshot_outcome(self, page_size: int = 500, max_pages: int = 20):
        return self._snapshot or TransportOutcome.ok([])

    # 老合同同时保留：编排层优先用 envelope，但 provider 不必因此失去原接口。
    def fetch_quote(self, symbol):
        return fake_quote(symbol)

    def fetch_history(self, symbol, limit: int = 120):
        return make_history()

    def fetch_market_snapshot(self, page_size: int = 500, max_pages: int = 20):
        return []


class ErrorClassSurvivesTests(unittest.TestCase):
    """传输层的分类原样抵达日志，不再被"是不是 MarketDataError"这个二选一压扁。"""

    def test_parse_failure_is_logged_as_parse_not_network(self):
        provider = _EnvelopeProvider(
            quote_outcome=TransportOutcome.failed("parse", "字段漂移：缺 f43")
        )
        with self.assertLogs("stock_advisor.workflow", level="WARNING") as captured:
            outcome = analyze_symbol(SYMBOL, provider)
        self.assertFalse(outcome.ok)
        self.assertEqual(captured.records[0].error_class, "parse")

    def test_network_failure_is_still_network(self):
        provider = _EnvelopeProvider(quote_outcome=TransportOutcome.failed("network", "所有源超时"))
        with self.assertLogs("stock_advisor.workflow", level="WARNING") as captured:
            analyze_symbol(SYMBOL, provider)
        self.assertEqual(captured.records[0].error_class, "network")


class CancellationIsDistinguishableTests(unittest.TestCase):
    def test_cancelled_quote_says_cancelled_rather_than_failed(self):
        provider = _EnvelopeProvider(
            quote_outcome=TransportOutcome.failed("network", "已取消", cancelled=True)
        )
        outcome = analyze_symbol(SYMBOL, provider)
        self.assertFalse(outcome.ok)
        self.assertIn("取消", outcome.error)

    def test_cancelled_snapshot_marks_the_report_cancelled_not_errored(self):
        """`ScreenReport.cancelled` 此前永远是 False——取消的全市场抓取只会变成一条泛化错误。"""
        provider = _EnvelopeProvider(
            snapshot_outcome=TransportOutcome.failed("network", "已取消", cancelled=True)
        )
        report = screen_and_recommend(provider, criteria=None, objective="momentum")
        self.assertTrue(report.cancelled, "取消的全市场抓取没有被标成 cancelled")


class LegacyProvidersStillWorkTests(unittest.TestCase):
    """老式 provider（抛异常、没有 *_outcome）必须原样工作——测试替身与旧适配器都靠这条。"""

    def test_raising_provider_is_wrapped_into_a_failure_envelope(self):
        class _Raising(FakeProvider):
            def fetch_quote(self, symbol):
                raise MarketDataError("所有源超时")

        outcome = analyze_symbol(SYMBOL, _Raising())
        self.assertFalse(outcome.ok)
        self.assertIn("超时", outcome.error)

    def test_healthy_legacy_provider_still_analyses(self):
        outcome = analyze_symbol(SYMBOL, FakeProvider())
        self.assertTrue(outcome.ok)


if __name__ == "__main__":
    unittest.main()
