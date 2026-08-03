"""界面输入验证走域里那份被测过的实现（REQ-020 · WI-032）。

WI-032 要裁定 24 条 Tk 时代的 `pure_preserved` 契约「还有没有活的生产调用方」。查下来
`domain/input_validate.py` 的每个函数在 `src/` 里都零调用——但**不是因为它们过时了**，而是 Qt 页面
各自又写了一份本地副本，且副本比域里那份弱：

* `portfolio_page._optional_int` 的 `except (TypeError, ValueError)` 漏了 `OverflowError`，
  而 `int(float("inf"))` 正是抛它——持仓股数填 `inf` 会抛出未捕获异常；
* `alerts_page._optional_float` 少了 `math.isfinite` 检查，阈值填 `inf` 会建出一条**静默永不触发**的
  规则，而不是被明确拒绝。

所以正解是把页面接到域实现上（而不是删掉那份被测过的域代码），这两条缺陷随之消失，重复也消失。
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
    from qt_app.controllers.analysis_controller import AnalysisController
    from qt_app.pages.alerts_page import AlertsPage
    from qt_app.pages.portfolio_page import PortfolioPage


@requires_qt
class HoldingSharesInputTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _page(self):
        controller = AnalysisController(FakeProvider())
        self.addCleanup(controller.shutdown)
        page = PortfolioPage(controller, temp_settings(self))
        self.addCleanup(page.deleteLater)
        return page

    def test_non_finite_share_count_does_not_raise(self):
        """股数填 `inf` 必须被当成"没填"，而不是抛 OverflowError。"""
        page = self._page()
        page.code_input.setText("600519")
        for probe in ("inf", "-inf", "nan"):
            with self.subTest(probe=probe):
                page.shares_input.setText(probe)
                page.add_current_input()  # 不得抛异常
                self.assertTrue(True)

    def test_valid_share_count_still_works(self):
        page = self._page()
        page.code_input.setText("600519")
        page.shares_input.setText("200")
        page.add_current_input()
        shares = [item.shares for item in page._settings.config.watchlist]
        self.assertIn(200, shares)


@requires_qt
class AlertThresholdInputTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _page(self):
        from qt_app.controllers.alert_controller import AlertController

        controller = AlertController(FakeProvider())
        self.addCleanup(controller.shutdown)
        page = AlertsPage(controller, temp_settings(self))
        self.addCleanup(page.deleteLater)
        return page

    def test_non_finite_threshold_is_rejected_with_a_message(self):
        """阈值填 `inf` 要当场拒绝，而不是建出一条永远不会触发的规则。"""
        page = self._page()
        page.rule_code.setText("600519")
        for probe in ("inf", "-inf", "nan"):
            with self.subTest(probe=probe):
                page.rule_threshold.setText(probe)
                page.add_current_rule()
                self.assertEqual(
                    len(page._settings.config.alerts), 0, f"{probe} 竟被接受成合法阈值"
                )
                self.assertIn("有效", page.status.text())

    def test_valid_threshold_still_creates_the_rule(self):
        page = self._page()
        page.rule_code.setText("600519")
        page.rule_threshold.setText("12.5")
        page.add_current_rule()
        self.assertEqual(len(page._settings.config.alerts), 1)


@requires_qt
class TunableBoundsAreEnforcedByTheWidgetTests(unittest.TestCase):
    """参数范围由 QDoubleSpinBox 原生钳死——这是 11 条 Tk 契约在 Qt 侧的替代（WI-032）。

    老 Tk 版靠两个纯函数：`is_partial_number` 逐字符放行"构造中的数字"，`validate_tunable` 在提交
    时验范围并给出可读错误。Qt 的微调框把两件事都接管了：非法字符根本敲不进去，越界值被 setRange
    钳回边界。因此那两个纯函数在 Qt 版没有调用方——不是被遗忘，是被部件取代。取代要有断言兜住，
    否则"契约已由 Qt 承担"只是一句无人验证的说法。
    """

    def setUp(self):
        self.app = qt_app()

    def _page(self):
        from qt_app.controllers.screener_controller import ScreenerController
        from qt_app.pages.screener_page import ScreenerPage

        controller = ScreenerController(FakeProvider())
        self.addCleanup(controller.shutdown)
        page = ScreenerPage(controller, temp_settings(self))
        self.addCleanup(page.deleteLater)
        return page

    def test_each_tunable_spin_clamps_to_its_presets_declared_bounds(self):
        from domain.presets import PRESETS, get_preset

        page = self._page()
        preset = get_preset(page.preset_combo.currentData()) or PRESETS[0]
        self.assertTrue(preset.tunables, "预设没有可调参数，本用例无从验证钳制")
        for param in preset.tunables:
            with self.subTest(param=param.key):
                spin = page._spins[param.key]
                self.assertEqual(spin.minimum(), float(param.minimum))
                self.assertEqual(spin.maximum(), float(param.maximum))
                spin.setValue(float(param.maximum) + 1000)  # 越上界 → 钳回上界
                self.assertEqual(spin.value(), float(param.maximum))
                spin.setValue(float(param.minimum) - 1000)  # 越下界 → 钳回下界
                self.assertEqual(spin.value(), float(param.minimum))

    def test_recommendation_count_bounds_stay_five_to_thirty(self):
        """老契约 `test_recommendation_count_bounds_are_five_to_thirty` 的 Qt 侧对应。"""
        from domain.presets import PRESETS

        top_n = [p for preset in PRESETS for p in preset.tunables if p.key == "top_n"]
        self.assertTrue(top_n, "预设里找不到 top_n 参数")
        for param in top_n:
            self.assertEqual((param.minimum, param.maximum), (5, 30))


if __name__ == "__main__":
    unittest.main()
