import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


import main as app_main


class SelfTestModeTests(unittest.TestCase):
    def test_self_test_runs_both_pipelines_offline_and_returns_zero(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = app_main.main(["--self-test"])
        output = buffer.getvalue()

        self.assertEqual(code, 0)
        self.assertIn("SELF_TEST_OK", output)
        self.assertIn("action=", output)
        self.assertIn("screen_candidates=", output)

    def test_gui_mode_configures_logging_before_launching_gui(self):
        calls = []
        original_run_gui = app_main.run_gui
        original_configure = app_main.configure_logging
        try:
            # 打桩 configure_logging：避免测试往真实 %APPDATA% 写日志目录；顺带断言它被调用。
            app_main.configure_logging = lambda *a, **k: calls.append("log")
            app_main.run_gui = lambda: calls.append("gui")

            code = app_main.main([])
        finally:
            app_main.run_gui = original_run_gui
            app_main.configure_logging = original_configure

        self.assertEqual(code, 0)
        # 先配置日志再启动 GUI（WI-023 起不再手动置 DPI 感知，交给 Qt6 的 Per-Monitor-V2）。
        self.assertEqual(calls, ["log", "gui"])

    def test_gui_entry_delegates_to_the_pyside6_assembly(self):
        """REQ-011 / WI-023：ui.app 退化为薄入口，把 run_gui 委托给 qt_app 装配。

        生产源零 tkinter import 的全量静态扫描见 test_qt_app_assembly.py（TEST-ARCH-002）。
        """
        import inspect

        from ui import app as ui_app

        self.assertIn("run_qt_gui", inspect.getsource(ui_app.run_gui))


if __name__ == "__main__":
    unittest.main()
