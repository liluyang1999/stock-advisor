"""截图工具的防腐测试（scripts/capture_ui.py）。

它是开发工具、不进门禁，但仍需一层测试挡住 bit-rot：一旦页面属性名（`page.input`、`_on_analyze`）、
controller 信号名或 provider 契约变了，工具就会静默失效——真到要看 UI 时才发现它跑不了。这里在
offscreen 下真的驱动它跑一遍，把这些接口点全部踩到。

DemoProvider 的契约独立测：它必须满足 controller 实际调用的四个 `fetch_*`，且走势非单调
（一条直线的 K 线看不出蜡烛，等于没有演示价值）。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import capture_ui  # noqa: E402
from qt_test_helpers import qt_app, requires_qt  # noqa: E402

from domain.models import DailyBar, FundFlow, MarketSnapshot, Quote  # noqa: E402
from domain.symbols import normalize_symbol  # noqa: E402


class DemoProviderContractTests(unittest.TestCase):
    """DemoProvider 必须满足 controller 依赖的 provider 契约。"""

    def test_quote_history_snapshot_and_flow_have_the_right_shapes(self):
        provider = capture_ui.DemoProvider()
        symbol = normalize_symbol("600519")

        self.assertIsInstance(provider.fetch_quote(symbol), Quote)

        history = provider.fetch_history(symbol)
        self.assertTrue(history)
        self.assertTrue(all(isinstance(bar, DailyBar) for bar in history))

        snapshot = provider.fetch_market_snapshot()
        self.assertTrue(snapshot)
        self.assertTrue(all(isinstance(row, MarketSnapshot) for row in snapshot))

        self.assertIsInstance(provider.fetch_fund_flow(symbol), FundFlow)

    def test_history_is_not_a_straight_line(self):
        """K 线要有起伏才有演示价值：收盘价必须既有上涨日也有下跌日。"""
        bars = capture_ui.DemoProvider().fetch_history(normalize_symbol("600519"))
        deltas = [float(bars[i].close) - float(bars[i - 1].close) for i in range(1, len(bars))]
        self.assertTrue(any(d > 0 for d in deltas), "没有上涨日")
        self.assertTrue(any(d < 0 for d in deltas), "没有下跌日")

    def test_fail_codes_make_those_symbols_raise(self):
        provider = capture_ui.DemoProvider(fail_codes=frozenset({"000001"}))
        provider.fetch_quote(normalize_symbol("600519"))  # 不在失败集，正常
        with self.assertRaises(ValueError):
            provider.fetch_quote(normalize_symbol("000001"))

    def test_fund_flow_failure_flag_raises(self):
        provider = capture_ui.DemoProvider(fund_flow_fails=True)
        with self.assertRaises(ValueError):
            provider.fetch_fund_flow(normalize_symbol("600519"))


@requires_qt
class CaptureSmokeTests(unittest.TestCase):
    """真的驱动 capture 跑一遍，踩到所有页面接口点。"""

    def setUp(self):
        self.app = qt_app()

    def _out(self) -> Path:
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_empty_state_writes_five_page_pngs(self):
        out = self._out()
        paths = capture_ui.capture(["empty"], out, (900, 640))
        self.assertEqual(len(paths), 5)
        for path in paths:
            self.assertTrue(path.exists() and path.stat().st_size > 0, path)

    def test_success_state_drives_every_page_without_crashing(self):
        """success 态会触碰 page.input / _on_analyze / 各 controller 信号——接口漂移即在此失败。"""
        out = self._out()
        paths = capture_ui.capture(["success"], out, (900, 640))
        self.assertEqual(len(paths), 5)
        self.assertTrue(all(p.exists() for p in paths))


if __name__ == "__main__":
    unittest.main()
