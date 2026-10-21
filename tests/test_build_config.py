import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


import build_exe


class BuildConfigTests(unittest.TestCase):
    def test_dirty_source_is_rejected_before_removing_outputs(self):
        with patch.object(build_exe, "_source_is_clean", return_value=False, create=True):
            with patch.object(build_exe, "_remove_dir") as remove:
                with patch.object(build_exe, "_pyinstaller_available", return_value=True):
                    with patch.object(build_exe.subprocess, "run"):
                        self.assertEqual(build_exe.main(), 2)
                remove.assert_not_called()

    def test_cleanup_cannot_remove_project_root_or_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "src"
            source.mkdir()
            with patch.object(build_exe, "PROJECT_ROOT", root):
                for target in (root, source):
                    with self.subTest(target=target):
                        with self.assertRaises(RuntimeError):
                            build_exe._remove_dir(target)
                        self.assertTrue(source.is_dir())

    def test_ignored_importable_source_is_not_a_clean_build(self):
        from subprocess import CompletedProcess

        with patch.object(build_exe, "_git_commit", return_value="a" * 40):
            with patch.object(
                build_exe.subprocess,
                "run",
                side_effect=[
                    CompletedProcess([], 0, stdout=""),
                    CompletedProcess([], 0, stdout="src/hidden.py\n"),
                ],
            ):
                self.assertFalse(build_exe._source_is_clean())

    def test_runtime_inventory_covers_native_files_and_carries_licenses(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            (target / "sample.dll").write_bytes(b"example native payload")
            build_exe._write_runtime_metadata(target)
            info = json.loads((target / "RUNTIME_INVENTORY.json").read_text(encoding="utf-8"))
            self.assertEqual(info["native_files"][0]["path"], "sample.dll")
            self.assertEqual(len(info["native_files"][0]["sha256"]), 64)
            self.assertEqual(info["native_files"][0]["bytes"], 22)
            for name in ("Python-LICENSE.txt", "PyInstaller-COPYING.txt"):
                self.assertGreater((target / "_internal" / "licenses" / name).stat().st_size, 100)

    def test_build_outputs_requested_name_and_uses_theme_icon(self):
        self.assertEqual(build_exe.OUTPUT_NAME, "股市锦囊.exe")
        self.assertEqual(build_exe.ICON_PATH.name, "a_stock_strategy.ico")
        self.assertTrue(build_exe.ICON_PATH.exists())

    def test_deliverables_go_to_dist_and_intermediates_to_build(self):
        project = build_exe.PROJECT_ROOT.resolve()
        dist_dir = build_exe.DIST_DIR.resolve()
        build_dir = build_exe.BUILD_DIR.resolve()
        # 最终交付物在 dist/，构建中间产物在 build/，都在项目内，且不再有 outputs/。
        self.assertEqual(dist_dir, project / "dist")
        self.assertEqual(build_dir, project / "build")
        self.assertIn(project, dist_dir.parents)
        self.assertFalse(hasattr(build_exe, "OUTPUT_DIR"))
        # PyInstaller 原始产物留在 build/ 内，避免污染 dist/
        self.assertIn(build_dir, build_exe.PYI_DIST_DIR.resolve().parents)

    def test_windows_build_does_not_resolve_dlls_from_unrelated_tools(self):
        foreign = r"C:\unrelated-tools\poppler;C:\unrelated-tools\libheif"
        with patch.dict(
            os.environ,
            {"PATH": foreign, "SYSTEMROOT": r"C:\Windows", "BUILD_LABEL": "review"},
            clear=True,
        ):
            with patch.object(sys, "platform", "win32"):
                child = build_exe._pyinstaller_environment()
            self.assertEqual(os.environ["PATH"], foreign)
        paths = child["PATH"].split(os.pathsep)
        self.assertNotIn(r"C:\unrelated-tools\poppler", paths)
        self.assertNotIn(r"C:\unrelated-tools\libheif", paths)
        self.assertIn(str(Path(sys.executable).resolve().parent), paths)
        self.assertIn(str(Path(sys.base_prefix) / "DLLs"), paths)
        self.assertIn(str(Path(r"C:\Windows") / "System32"), paths)
        self.assertEqual(child["BUILD_LABEL"], "review")

    def test_windows_build_reports_missing_system_root(self):
        with patch.dict(os.environ, {"PATH": "unrelated"}, clear=True):
            with patch.object(sys, "platform", "win32"):
                with self.assertRaisesRegex(RuntimeError, "SystemRoot"):
                    build_exe._pyinstaller_environment()

    def test_other_platforms_keep_their_library_search_environment(self):
        with patch.dict(os.environ, {"PATH": "/usr/bin:/custom/bin"}, clear=True):
            with patch.object(sys, "platform", "linux"):
                child = build_exe._pyinstaller_environment()
            self.assertEqual(child, dict(os.environ))
            self.assertIsNot(child, os.environ)

    def test_build_also_emits_html_manual_into_dist(self):
        self.assertEqual(build_exe.MANUAL_NAME, "使用说明.html")
        self.assertTrue(hasattr(build_exe, "_write_manual"))


if __name__ == "__main__":
    unittest.main()
