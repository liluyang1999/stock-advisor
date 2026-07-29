"""生产 provider 切到有界传输后的合同（REQ-024/025/026 · WI-033）。

`BoundedUrllibProvider` 返回 envelope，而编排层（`services.workflow` / `services.fund_flow`）要的是
「拿到数据 or 抛 `MarketDataError`」。适配器负责这层翻译，于是**整条出货路径**拿到总 deadline、
协作取消、字节上限与**真实的分页完整度**，而调用方一行不用改。

这里盯死三件事：
1. 成功解包出数据本身，不把 envelope 泄漏给调用方；
2. 失败一律抛 `MarketDataError`，**绝不返回半真数据**（REQ-024 零伪造）；
3. `market_completeness()` 如实报告残缺——旧 provider 没有这个方法，`workflow._provider_completeness`
   于是默认「完整」，残缺的全市场被当作完整市场拿去排序，REQ-026 的警告永远不会触发。
"""

from __future__ import annotations

import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bounded_transport import _clist_payload, _http_error, _Opener, _quote_payload

from data.bounded_adapter import BoundedMarketDataProvider
from data.data_provider import MarketDataError
from domain.symbols import normalize_symbol
from ports import ManualCancel

SYMBOL = normalize_symbol("600000")


def _provider(*script: object) -> BoundedMarketDataProvider:
    from data.bounded_transport import BoundedUrllibProvider

    return BoundedMarketDataProvider(BoundedUrllibProvider(opener=_Opener(*script)))


class UnwrapSuccessTests(unittest.TestCase):
    def test_fetch_quote_returns_the_quote_not_the_envelope(self):
        provider = _provider(_quote_payload())
        quote = provider.fetch_quote(SYMBOL)
        self.assertEqual(quote.symbol.normalized, SYMBOL.normalized)
        self.assertEqual(quote.name, "浦发银行")

    def test_fetch_market_snapshot_returns_the_rows(self):
        provider = _provider(_clist_payload(["600000", "600001"], total=2))
        rows = provider.fetch_market_snapshot()
        self.assertEqual([row.code for row in rows], ["600000", "600001"])


class ZeroFabricationTests(unittest.TestCase):
    """失败路径必须抛错。envelope 的失败结构上不带 data，适配器不得把它翻译成空列表/零值。"""

    def test_fetch_quote_raises_when_every_source_fails(self):
        provider = _provider(_http_error(503), _http_error(503))
        with self.assertRaises(MarketDataError):
            provider.fetch_quote(SYMBOL)

    def test_fetch_history_raises_when_every_source_fails(self):
        provider = _provider(*[_http_error(503)] * 4)
        with self.assertRaises(MarketDataError):
            provider.fetch_history(SYMBOL)

    def test_fetch_fund_flow_raises_when_every_host_fails(self):
        provider = _provider(*[urllib.error.URLError("dns")] * 4)
        with self.assertRaises(MarketDataError):
            provider.fetch_fund_flow(SYMBOL)

    def test_fetch_market_snapshot_raises_when_the_first_page_fails(self):
        provider = _provider(_http_error(500))
        with self.assertRaises(MarketDataError):
            provider.fetch_market_snapshot()

    def test_error_message_survives_into_the_exception(self):
        provider = _provider(_http_error(429, "too many"))
        with self.assertRaises(MarketDataError) as caught:
            provider.fetch_quote(SYMBOL)
        self.assertTrue(str(caught.exception), "失败必须带上可读原因，不能是空串")


class CompletenessTests(unittest.TestCase):
    """WI-033 的核心用户价值：残缺的全市场不再冒充完整。"""

    def test_completeness_is_complete_before_any_snapshot(self):
        # 还没拉过全市场时不该谎报残缺——默认「无信息即完整」与 Completeness 的语义一致。
        self.assertTrue(_provider().market_completeness().is_complete)

    def test_full_market_reports_complete(self):
        provider = _provider(_clist_payload(["600000", "600001"], total=2))
        provider.fetch_market_snapshot(page_size=2)
        self.assertTrue(provider.market_completeness().is_complete)

    def test_truncated_market_reports_incomplete_with_the_missing_page(self):
        # 第 1 页成功、第 2 页失败：旧路径静默返回半个市场且报告「完整」。
        provider = _provider(
            _clist_payload(["600000", "600001"], total=4),
            _http_error(500),
        )
        provider.fetch_market_snapshot(page_size=2)
        completeness = provider.market_completeness()
        self.assertFalse(completeness.is_complete, "残缺的全市场谎称完整——REQ-026 的警告将不会触发")
        self.assertEqual(completeness.missing_pages, (2,))
        self.assertEqual(completeness.expected, 4)
        self.assertEqual(completeness.received, 2)

    def test_a_later_full_snapshot_clears_the_stale_incomplete_state(self):
        provider = _provider(
            _clist_payload(["600000", "600001"], total=4),
            _http_error(500),
            _clist_payload(["600000", "600001"], total=2),
        )
        provider.fetch_market_snapshot(page_size=2)
        self.assertFalse(provider.market_completeness().is_complete)
        provider.fetch_market_snapshot(page_size=2)
        self.assertTrue(provider.market_completeness().is_complete, "上一轮的残缺状态没有被清掉")


class CancellationTests(unittest.TestCase):
    def test_cancelled_fetch_raises_instead_of_returning_data(self):
        cancel = ManualCancel()
        cancel.cancel()
        provider = _provider(_quote_payload())
        provider.set_cancel_token(cancel)
        with self.assertRaises(MarketDataError):
            provider.fetch_quote(SYMBOL)

    def test_clearing_the_token_restores_normal_fetching(self):
        cancel = ManualCancel()
        cancel.cancel()
        provider = _provider(_quote_payload())
        provider.set_cancel_token(cancel)
        with self.assertRaises(MarketDataError):
            provider.fetch_quote(SYMBOL)
        provider.set_cancel_token(None)
        self.assertEqual(provider.fetch_quote(SYMBOL).name, "浦发银行")


if __name__ == "__main__":
    unittest.main()
