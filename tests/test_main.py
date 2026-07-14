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

    def test_gui_mode_enables_dpi_awareness_before_launching_gui(self):
        calls = []
        original_enable = app_main.enable_dpi_awareness
        original_run_gui = app_main.run_gui
        try:
            app_main.enable_dpi_awareness = lambda: calls.append("dpi")
            app_main.run_gui = lambda: calls.append("gui")

            code = app_main.main([])
        finally:
            app_main.enable_dpi_awareness = original_enable
            app_main.run_gui = original_run_gui

        self.assertEqual(code, 0)
        self.assertEqual(calls, ["dpi", "gui"])


if __name__ == "__main__":
    unittest.main()
