"""帮助 / 策略 / 离线自检对话框 + 菜单接线（REQ-008/016/031 / WI-018 / TEST-QT-HELP-001）。

对话框只呈现、不含业务逻辑：帮助/策略复用 view_text 文案，自检复用 services.self_check。三者
底部都常驻免责声明（REQ-031）。菜单三项都带键盘快捷键，且触发即弹出对应窗（离屏 Qt 亦然）。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import qt_app, requires_qt

from domain.models import CORE_DISCLAIMER

if True:
    try:
        from PySide6 import QtGui

        from qt_app.dialogs import HelpDialog, SelfCheckDialog, StrategyDialog
        from qt_app.main_window import MainWindow
    except ImportError:  # pragma: no cover
        QtGui = HelpDialog = SelfCheckDialog = StrategyDialog = MainWindow = None


@requires_qt
class HelpDialogTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _dialog(self, cls):
        dialog = cls()
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_help_renders_usage_sections(self):
        dialog = self._dialog(HelpDialog)
        text = dialog.body.toPlainText()
        self.assertIn("怎么使用", text)
        self.assertIn("怎么看结果", text)

    def test_help_disclaimer_is_resident(self):
        dialog = self._dialog(HelpDialog)
        self.assertIn(CORE_DISCLAIMER, dialog.disclaimer.text())  # REQ-031

    def test_strategy_renders_strategy_sections(self):
        dialog = self._dialog(StrategyDialog)
        text = dialog.body.toPlainText()
        self.assertIn("总体思路", text)
        self.assertIn("计算步骤", text)

    def test_strategy_disclaimer_is_resident(self):
        dialog = self._dialog(StrategyDialog)
        self.assertIn(CORE_DISCLAIMER, dialog.disclaimer.text())  # REQ-031


@requires_qt
class SelfCheckDialogTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def _dialog(self):
        dialog = SelfCheckDialog()
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_runs_offline_self_check_and_passes(self):
        dialog = self._dialog()
        self.assertTrue(dialog.result.ok, dialog.result.summary)
        self.assertEqual(len(dialog.result.checks), 8)

    def test_summary_and_each_check_name_are_shown(self):
        dialog = self._dialog()
        self.assertIn("自检", dialog.summary.text())
        body = dialog.body.toPlainText()
        for check in dialog.result.checks:
            self.assertIn(check.name, body)

    def test_disclaimer_is_resident(self):
        dialog = self._dialog()
        self.assertIn(CORE_DISCLAIMER, dialog.disclaimer.text())  # REQ-031


@requires_qt
class HelpMenuWiringTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)

    def test_help_action_has_f1_shortcut(self):
        expected = QtGui.QKeySequence(QtGui.QKeySequence.StandardKey.HelpContents)
        self.assertEqual(self.window.help_action.shortcut(), expected)

    def test_strategy_and_self_check_actions_have_shortcuts(self):
        # 快捷键存在且非空（TEST-QT-HELP-001：快捷键可用）。
        self.assertFalse(self.window.strategy_action.shortcut().isEmpty())
        self.assertFalse(self.window.self_check_action.shortcut().isEmpty())

    def test_triggering_help_action_opens_help_dialog(self):
        self.window.help_action.trigger()
        dialogs = [d for d in self.window._open_dialogs if isinstance(d, HelpDialog)]
        self.assertEqual(len(dialogs), 1)
        self.assertTrue(dialogs[0].isVisible())
        for dialog in list(self.window._open_dialogs):
            dialog.close()

    def test_open_self_check_returns_visible_dialog(self):
        dialog = self.window.open_self_check()
        self.addCleanup(dialog.close)
        self.assertIsInstance(dialog, SelfCheckDialog)
        self.assertTrue(dialog.isVisible())


if __name__ == "__main__":
    unittest.main()
