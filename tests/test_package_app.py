"""Portable delivery must fail closed and restore the previous working bundle."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import package_app


class PackageAppTests(unittest.TestCase):
    def test_failed_build_restores_previous_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist = root / "dist"
            build = root / "build"
            dist.mkdir()
            build.mkdir()
            (dist / "previous.txt").write_text("working", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                with package_app.delivery_transaction(dist, build):
                    dist.mkdir()
                    (dist / "partial.txt").write_text("partial", encoding="utf-8")
                    raise RuntimeError("build failed")
            self.assertEqual((dist / "previous.txt").read_text(), "working")
            self.assertFalse((dist / "partial.txt").exists())
            self.assertEqual(list(build.iterdir()), [])

    def test_restore_failure_keeps_previous_bundle_for_manual_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist, build = root / "dist", root / "build"
            dist.mkdir()
            build.mkdir()
            (dist / "previous.txt").write_text("working", encoding="utf-8")
            original = Path.rename

            def cannot_restore(path, target):
                if path.parent.name.startswith("previous-delivery-"):
                    raise PermissionError("restore blocked")
                return original(path, target)

            with patch.object(Path, "rename", cannot_restore):
                with self.assertRaisesRegex(RuntimeError, "preserved"):
                    with package_app.delivery_transaction(dist, build):
                        dist.mkdir()
                        raise RuntimeError("build failed")
            backups = list(build.glob("previous-delivery-*/dist/previous.txt"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), "working")

    def test_success_replaces_bundle_and_removes_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist = root / "dist"
            build = root / "build"
            dist.mkdir()
            build.mkdir()
            (dist / "previous.txt").touch()
            with package_app.delivery_transaction(dist, build):
                dist.mkdir()
                (dist / "new.txt").touch()
            self.assertEqual([p.name for p in dist.iterdir()], ["new.txt"])
            self.assertEqual(list(build.iterdir()), [])

    def test_smoke_environment_excludes_developer_python_and_qt_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(
                os.environ,
                {
                    "PYTHONPATH": "foreign",
                    "QT_PLUGIN_PATH": "foreign",
                    "QT_QPA_PLATFORM": "offscreen",
                },
            ):
                env = package_app.smoke_environment(Path(folder))
            self.assertNotIn("PYTHONPATH", env)
            self.assertNotIn("QT_PLUGIN_PATH", env)
            self.assertNotIn("QT_QPA_PLATFORM", env)
            self.assertEqual(env["STOCK_ADVISOR_CONFIG"], str(Path(folder) / "config.json"))

    def test_unsupported_platform_fails_before_creating_environment(self):
        with patch.object(package_app.sys, "platform", "linux"):
            with patch.object(package_app.subprocess, "run") as builder:
                self.assertEqual(package_app.main([]), 2)
                builder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
