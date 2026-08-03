"""在途取消能真正抵达传输层，且不会跨页误伤（REQ-013/025 · ADR-0003 · WI-033）。

有界 provider 持有一个协作取消令牌；`run_with_contract` 在每个可中断点查询它，所以令牌一翻，
**在途请求**就会中止——这正是「停止」按钮与关窗要的东西（此前取消只在两只股票之间被检查，
一次最坏 100 s 的取数链根本停不下来）。

要让这件事成立，两个条件缺一不可：
1. 每轮开跑时，本轮的取消原语必须**绑到该控制器自己的 provider 上**；
2. 五个控制器必须各自持有**独立的 provider 实例**——共用一个，个股页按「停止」就会连带打断
   预警轮询与选股的在途请求。这与 `app.py` 里「自选页自带一份 AnalysisController」是同一个理由。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtWidgets, qt_app, requires_qt, temp_settings
from test_engine import FakeProvider

if QtWidgets is not None:
    from qt_app.app import build_app
    from qt_app.controllers.analysis_controller import AnalysisController
    from qt_app.controllers.screener_controller import ScreenerController


class _SpyProvider(FakeProvider):
    """FakeProvider + 记录被绑上来的取消令牌（真 provider 的 `set_cancel_token` 同名同义）。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.token = None

    def set_cancel_token(self, token) -> None:
        self.token = token

    def fetch_market_snapshot(self, page_size: int = 500, max_pages: int = 20):
        return []  # 让筛选 worker 干净收尾；本用例只关心取消令牌，不关心筛选结果


@requires_qt
class CancelReachesTheTransportTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _controller(self, provider):
        controller = AnalysisController(provider)
        self.addCleanup(controller.shutdown)
        return controller

    def test_starting_a_run_binds_that_runs_token_to_the_provider(self):
        provider = _SpyProvider()
        controller = self._controller(provider)
        controller.start("600519", level=3)
        self.assertIsNotNone(provider.token, "开跑没有把本轮取消令牌交给传输层：在途请求无法中断")
        self.assertFalse(provider.token.is_cancelled())

    def test_cancel_flips_the_token_the_provider_is_holding(self):
        provider = _SpyProvider()
        controller = self._controller(provider)
        controller.start("600519", level=3)
        controller.cancel()
        self.assertTrue(
            provider.token.is_cancelled(), "取消没有传到传输层，在途请求会一直跑到 deadline"
        )

    def test_one_controllers_cancel_does_not_touch_another_controllers_provider(self):
        analysis_provider = _SpyProvider()
        screener_provider = _SpyProvider()
        analysis = self._controller(analysis_provider)
        screener = ScreenerController(screener_provider)
        self.addCleanup(screener.shutdown)

        analysis.start("600519", level=3)
        screener.start("momentum", {}, deep=False, level=3)
        analysis.cancel()

        self.assertTrue(analysis_provider.token.is_cancelled())
        self.assertFalse(
            screener_provider.token.is_cancelled(),
            "一页的取消打断了另一页的在途请求——provider 被共用了",
        )


@requires_qt
class AlertMonitoringCancelTests(unittest.TestCase):
    """周期预警也要能打断在途轮询——否则关窗时 `shutdown()` 要等它跑到 deadline 才排空得掉。"""

    def setUp(self):
        self.app = qt_app()

    def test_start_binds_a_token_and_stop_flips_it(self):
        from qt_app.controllers.alert_controller import AlertController

        provider = _SpyProvider()
        controller = AlertController(provider)
        self.addCleanup(controller.shutdown)

        controller.start(interval_ms=10_000)
        self.assertIsNotNone(provider.token, "预警监控没有把取消令牌交给传输层")
        self.assertFalse(provider.token.is_cancelled())

        controller.stop()
        self.assertTrue(
            provider.token.is_cancelled(), "停止监控没有打断在途轮询：关窗要等它跑完才排空"
        )


@requires_qt
class ShippedAssemblyGivesEachControllerItsOwnProviderTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def test_each_controller_owns_a_distinct_provider(self):
        # 走**出货装配**（不注入 provider），否则测得的是测试替身的接线而不是真装配。
        _app, window = build_app([], settings=temp_settings(self))
        self.addCleanup(window.deleteLater)
        providers = [controller._provider for controller in window.controllers()]
        self.assertEqual(len(providers), 5)
        self.assertEqual(
            len({id(provider) for provider in providers}),
            5,
            "控制器共用了同一个 provider：一页的取消会打断其它页的在途请求",
        )


if __name__ == "__main__":
    unittest.main()
