"""结果区动作与快捷键（REQ-005/009/010/017 / WI-035）。

守两类"说了却没做"的缺口：

1. **应用内的使用说明写了三组快捷键**（`ui/view_text.py` 的「数据与快捷操作」一节），但重构后只有
   Ctrl+Enter/F5 存在，且只挂在个股页上——切到选股页按 F5 毫无反应，而说明书写的是"在当前页
   开始分析或开始选股"。说明书不能骗人：这里逐条断言说明里提到的键真的接上了。
2. **老版结果区的「加入自选」与「复制解释」**在重构后没有任何入口。分析完 8 只想全部加自选，
   只能切到自选页把 8 个代码重敲一遍；而"完整解释"——这个产品真正的产出——根本无法复制。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtGui, qt_app, requires_qt, temp_settings, wait_for  # noqa: E402
from test_engine import FakeProvider  # noqa: E402

from ui.view_text import build_help_sections  # noqa: E402

try:
    from qt_app.app import AppWindow
except ImportError:  # pragma: no cover - PySide6 是可选的迁移期依赖
    AppWindow = None


def _shortcuts(widget) -> set[str]:
    """widget 及其子树上已注册的快捷键文本集合。"""

    return {
        s.key().toString(QtGui.QKeySequence.SequenceFormat.PortableText)
        for s in widget.findChildren(QtGui.QShortcut)
    }


@requires_qt
class ShortcutContractTests(unittest.TestCase):
    """使用说明里承诺的快捷键必须真的存在。"""

    def setUp(self):
        self.app = qt_app()
        self.window = AppWindow(FakeProvider(), settings=temp_settings(self))
        self.addCleanup(self.window.close)

    def test_every_shortcut_the_manual_promises_is_registered(self):
        keys = _shortcuts(self.window)
        manual = "\n".join(body for _title, body in build_help_sections())

        for promised in ("Ctrl+Enter", "F5", "Ctrl+L", "Ctrl+Shift+C"):
            self.assertIn(promised, manual, f"使用说明没提到 {promised}，本测试的前提变了")
            self.assertIn(promised, keys, f"使用说明承诺了 {promised}，但没有任何地方注册它")

    def test_run_shortcut_dispatches_to_the_active_tab(self):
        """同一个键在个股页是开始分析、在选股页是开始选股（老版 `_run_active_tab`）。"""
        self.window.tabs.setCurrentIndex(0)
        self.window.run_active_tab()
        self.assertFalse(self.window.individual_page.analyze_button.isEnabled())  # 已开跑
        wait_for(self.window.analysis.batch_finished)

        self.window.tabs.setCurrentIndex(1)
        self.window.run_active_tab()
        self.assertFalse(self.window.screener_page.screen_button.isEnabled())  # 选股开跑
        wait_for(self.window.screener.screen_finished)


@requires_qt
class ResultActionTests(unittest.TestCase):
    """结果区的加入自选 / 复制解释。"""

    def setUp(self):
        self.app = qt_app()
        self.settings = temp_settings(self)
        self.window = AppWindow(FakeProvider(), settings=self.settings)
        self.addCleanup(self.window.close)
        self.page = self.window.individual_page
        self.page.input.setPlainText("600000 000001")
        self.page._on_analyze()
        wait_for(self.window.analysis.batch_finished)

    def test_actions_are_disabled_until_there_are_results(self):
        fresh = AppWindow(FakeProvider(), settings=temp_settings(self))
        self.addCleanup(fresh.close)
        self.assertFalse(fresh.individual_page.watch_button.isEnabled())
        self.assertFalse(fresh.individual_page.copy_detail_button.isEnabled())

    def test_add_all_to_watchlist_adds_the_whole_batch_at_once(self):
        """老版一次加完整批；逐个重敲代码正是重构后丢掉这个按钮造成的退化。"""
        added = self.page.add_all_to_watchlist()

        self.assertEqual(added, 2)
        stored = {item.code for item in self.settings.config.watchlist}
        self.assertEqual(stored, {"sh600000", "sz000001"})

    def test_adding_twice_does_not_duplicate(self):
        self.page.add_all_to_watchlist()
        again = self.page.add_all_to_watchlist()

        self.assertEqual(again, 0)
        self.assertEqual(len(self.settings.config.watchlist), 2)

    def test_copy_current_detail_copies_the_whole_explanation(self):
        self.page.table.setCurrentIndex(self.page.model.index(0, 0))

        text = self.page.copy_current_detail()

        self.assertIn("核心结论", text)
        self.assertIn("判断拆解", text)
        self.assertEqual(QtGui.QGuiApplication.clipboard().text(), text)

    def test_copy_current_detail_says_so_when_nothing_is_selected(self):
        """没选中就如实提示，不静默无反应。"""
        self.page.table.clearSelection()
        self.page.table.setCurrentIndex(self.page.model.index(-1, -1))

        self.assertEqual(self.page.copy_current_detail(), "")
        self.assertIn("先选中", self.page.run_status.text())

    def test_fund_flow_carries_the_selected_symbol_across_pages(self):
        """老版「更多」菜单拿当前选中行去查资金流；重构后退化成"到另一页把代码再敲一遍"。"""
        self.page.table.setCurrentIndex(self.page.model.index(0, 0))
        code = self.page._current_code()

        self.page._request_fund_flow()

        self.assertEqual(self.window.tabs.currentWidget(), self.window.fund_flow_page)
        self.assertEqual(self.window.fund_flow_page.input.text(), code)
        wait_for(self.window.fund_flow.fund_flow_ready)


@requires_qt
class CrossPageNavigationTests(unittest.TestCase):
    """老版能把自选整份推回分析页；重构后只能对着自选表把代码逐个抄过去。"""

    def setUp(self):
        self.app = qt_app()
        self.settings = temp_settings(self)
        self.window = AppWindow(FakeProvider(), settings=self.settings)
        self.addCleanup(self.window.close)

    def test_loading_the_watchlist_fills_the_analysis_input_and_switches_tab(self):
        portfolio = self.window.portfolio_page
        portfolio.code_input.setText("600000")
        portfolio.add_current_input()

        text = portfolio._request_load_into_analysis()

        self.assertIn("600000", text)
        self.assertEqual(self.window.tabs.currentWidget(), self.window.individual_page)
        self.assertIn("600000", self.window.individual_page.input.toPlainText())

    def test_loading_does_not_auto_run(self):
        """载入只填输入框，不替用户消耗一次批量取数。"""
        portfolio = self.window.portfolio_page
        portfolio.code_input.setText("600000")
        portfolio.add_current_input()

        portfolio._request_load_into_analysis()

        self.assertTrue(self.window.individual_page.analyze_button.isEnabled())
        self.assertEqual(self.window.individual_page.model.rowCount(), 0)

    def test_empty_watchlist_says_so(self):
        self.assertEqual(self.window.portfolio_page._request_load_into_analysis(), "")
        self.assertIn("空的", self.window.portfolio_page.status.text())


@requires_qt
class ClearCancelsRunTests(unittest.TestCase):
    """跑到一半按清空要先取消，否则在途 worker 会把行追加回刚清空的表。"""

    def setUp(self):
        self.app = qt_app()
        self.window = AppWindow(FakeProvider(), settings=temp_settings(self))
        self.addCleanup(self.window.close)

    def test_clearing_mid_run_requests_cancellation(self):
        page = self.window.individual_page
        page.input.setPlainText("600000 000001 600519")
        page._on_analyze()

        page.clear_all()

        self.assertIn("停止", page.run_status.text())
        wait_for(self.window.analysis.batch_finished)
        self.assertEqual(page.model.rowCount(), 0, "取消后仍有行被追加回已清空的表")


if __name__ == "__main__":
    unittest.main()
