"""The packaged smoke route must exercise Qt and require an isolated profile."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class GuiSmokeTests(unittest.TestCase):
    def test_smoke_rejects_missing_isolated_configuration(self):
        from qt_app.smoke import run_smoke

        original = os.environ.pop("STOCK_ADVISOR_CONFIG", None)
        try:
            self.assertEqual(run_smoke(), 2)
        finally:
            if original is not None:
                os.environ["STOCK_ADVISOR_CONFIG"] = original

    def test_windowed_interpreter_reports_diagnostic_marker(self):
        executable = (
            Path(sys.executable).with_name("pythonw.exe")
            if sys.platform == "win32"
            else Path(sys.executable)
        )
        result = subprocess.run(
            [
                str(executable),
                "-B",
                "-c",
                "import sys; sys.stdout=None; sys.stderr=None; import main; raise SystemExit(main.main(['--self-test']))",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SELF_TEST_OK", result.stdout)

    def test_complete_gui_startup_and_clean_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            env = dict(
                os.environ,
                STOCK_ADVISOR_CONFIG=str(Path(folder) / "config.json"),
                QT_QPA_PLATFORM="offscreen",
                PYTHONUTF8="1",
                PYTHONDONTWRITEBYTECODE="1",
            )
            result = subprocess.run(
                [sys.executable, "-B", "main.py", "--smoke-test"],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("GUI_SMOKE_OK", result.stdout)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
