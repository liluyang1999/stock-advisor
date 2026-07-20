"""TEST-REL-001：发布清单机制（REQ-029/REQ-030 / AC-010）。

这套测试守的是"发布产物本身可信"这件事，而不是某一次构建的具体数字：
- 许可证正文缺失时必须以非零码退出、并把 `complete` 记成 false（不合规不能看起来像绿的）；
- 通知文件必须写明选用 LGPL-3.0、未修改 Qt、以及第 4(d) 条的重新链接途径；
- 目录合并哈希必须对内容改动和文件改名都敏感——它是回滚时"是不是同一份产物"的判据。

用临时目录冒充 dist/，因此不需要先跑 PyInstaller。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import make_release_manifest as rel


class _StagedDist:
    """在临时目录里搭一个最小交付布局，并把脚本的路径常量指过去。"""

    def __init__(self, root: Path) -> None:
        self.dist = root / "dist"
        self.app = self.dist / "股市锦囊"
        self.licenses_src = root / "licenses"
        self.app.mkdir(parents=True)
        self.licenses_src.mkdir()
        (self.app / "股市锦囊.exe").write_bytes(b"MZ fake executable")
        (self.app / "_internal").mkdir()
        (self.app / "_internal" / "Qt6Core.dll").write_bytes(b"fake qt core")
        (self.dist / "使用说明.html").write_text("<html>说明</html>", encoding="utf-8")

    def patches(self) -> list[Any]:
        return [
            mock.patch.object(rel, "DIST_DIR", self.dist),
            mock.patch.object(rel, "APP_DIR", self.app),
            mock.patch.object(rel, "LICENSES_SRC", self.licenses_src),
            mock.patch.object(rel, "LICENSES_OUT", self.dist / "licenses"),
            mock.patch.object(rel, "MANIFEST_PATH", self.dist / "RELEASE_MANIFEST.json"),
            mock.patch.object(rel, "SBOM_PATH", self.dist / "SBOM.json"),
            mock.patch.object(rel, "NOTICES_PATH", self.dist / "THIRD_PARTY_NOTICES.md"),
        ]

    def write_all_licenses(self) -> None:
        for name in rel.REQUIRED_LICENSE_TEXTS:
            (self.licenses_src / name).write_text(f"{name} 正文", encoding="utf-8")

    def write_build_info(self, commit: str) -> None:
        """冒充 build_exe.py 落在应用目录里的来源标记。"""
        (self.app / "BUILD_INFO.json").write_text(
            json.dumps({"commit": commit, "python": "3.14.4"}), encoding="utf-8"
        )


class ReleaseManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.staged = _StagedDist(Path(self._tmp.name))
        for patch in self.staged.patches():
            patch.start()
            self.addCleanup(patch.stop)
        # 默认铺成一份"来历正常"的交付：来源标记与仓库当前提交一致。来源相关的用例各自推翻它。
        head = rel._git("rev-parse", "HEAD")
        if head is not None:
            self.staged.write_build_info(head)

    def _run(self) -> int:
        return self._run_args([])

    def _run_args(self, args: list[str]) -> int:
        import io
        from contextlib import redirect_stderr, redirect_stdout

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return rel.main(args)

    def _manifest(self) -> dict:
        return json.loads((self.staged.dist / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))

    def test_missing_license_text_fails_the_run_and_is_recorded_as_incomplete(self):
        """缺许可证正文 = 不合规。必须非零退出，且清单里明确记成未完成。"""
        (self.staged.licenses_src / "LGPL-3.0.txt").write_text("LGPL 正文", encoding="utf-8")

        code = self._run()

        self.assertEqual(code, 1)
        compliance = self._manifest()["license_compliance"]
        self.assertFalse(compliance["complete"])
        self.assertIn("GPL-3.0.txt", compliance["texts_missing"])
        self.assertIn("LGPL-3.0.txt", compliance["texts_present"])

    def test_complete_license_set_passes_and_stages_every_text_into_dist(self):
        self.staged.write_all_licenses()

        code = self._run()

        self.assertEqual(code, 0)
        compliance = self._manifest()["license_compliance"]
        self.assertTrue(compliance["complete"])
        self.assertEqual(compliance["texts_missing"], [])
        for name in rel.REQUIRED_LICENSE_TEXTS:
            self.assertTrue((self.staged.dist / "licenses" / name).is_file(), name)

    def test_missing_build_output_refuses_to_write_a_manifest(self):
        """没有交付目录就没有可描述的对象——必须拒绝，而不是产出一份空清单。"""
        import shutil

        shutil.rmtree(self.staged.app)

        code = self._run()

        self.assertEqual(code, 2)
        self.assertFalse((self.staged.dist / "RELEASE_MANIFEST.json").exists())

    def test_notices_state_the_lgpl_election_and_the_relink_route(self):
        """LGPL-3.0 第 4 条的三项义务（正文、声明、可重新链接）必须逐条落在通知文件里。"""
        self.staged.write_all_licenses()

        self._run()
        notices = (self.staged.dist / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

        self.assertIn("LGPL-3.0-only", notices)
        self.assertIn("未修改 Qt", notices)
        self.assertIn("4(d)", notices)
        self.assertIn("PySide6", notices)

    def test_tree_digest_changes_when_any_shipped_byte_changes(self):
        """合并哈希是回滚判据：内容变了就必须变。"""
        self.staged.write_all_licenses()
        self._run()
        before = self._manifest()["artifacts"]["tree_sha256"]

        (self.staged.app / "_internal" / "Qt6Core.dll").write_bytes(b"fake qt core PATCHED")
        self._run()

        self.assertNotEqual(before, self._manifest()["artifacts"]["tree_sha256"])

    def test_tree_digest_changes_when_a_file_is_renamed(self):
        """只哈希内容会漏掉改名；路径必须一起进摘要。"""
        self.staged.write_all_licenses()
        self._run()
        before = self._manifest()["artifacts"]["tree_sha256"]

        (self.staged.app / "_internal" / "Qt6Core.dll").rename(
            self.staged.app / "_internal" / "Qt6Core_renamed.dll"
        )
        self._run()

        self.assertNotEqual(before, self._manifest()["artifacts"]["tree_sha256"])

    def test_manifest_hashes_every_shipped_file_including_the_manual(self):
        self.staged.write_all_licenses()

        self._run()
        files = self._manifest()["artifacts"]["files"]

        paths = {f["path"] for f in files}
        self.assertIn("股市锦囊/股市锦囊.exe", paths)
        self.assertIn("股市锦囊/_internal/Qt6Core.dll", paths)
        self.assertIn("使用说明.html", paths)
        for entry in files:
            self.assertEqual(len(entry["sha256"]), 64, entry["path"])
            self.assertGreater(entry["bytes"], 0, entry["path"])

    def test_sbom_is_cyclonedx_and_carries_a_license_expression_per_component(self):
        self.staged.write_all_licenses()

        self._run()
        sbom = json.loads((self.staged.dist / "SBOM.json").read_text(encoding="utf-8"))

        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        self.assertEqual(sbom["specVersion"], "1.5")
        self.assertTrue(sbom["components"], "SBOM 不能没有组件")
        for component in sbom["components"]:
            self.assertTrue(component["licenses"][0]["expression"])
            self.assertTrue(component["purl"].startswith("pkg:pypi/"))

    def test_shipped_components_are_the_qt_runtime_not_the_dev_toolchain(self):
        """开发期工具不在用户机器上运行，不能混进交付 SBOM。"""
        components = rel._collect_components()
        names = {c["normalized_name"] for c in components}

        self.assertIn("pyside6-essentials", names)
        self.assertIn("shiboken6", names)
        # purl 必须用 PEP 503 规范名（安装元数据报的是 PySide6_Essentials，下划线形式会漏匹配）。
        for component in components:
            self.assertEqual(
                component["purl"], f"pkg:pypi/{component['normalized_name']}@{component['version']}"
            )
            self.assertNotIn("_", component["purl"])
        for dev_only in ("ruff", "pyright", "pytest", "pyinstaller"):
            self.assertNotIn(dev_only, names)

    def test_verify_passes_against_an_untouched_delivery(self):
        """回滚演练的正路：产物没动过，校验就得通过。"""
        self.staged.write_all_licenses()
        self._run()

        self.assertEqual(self._run_args(["--verify"]), 0)

    def test_verify_detects_changed_missing_and_unexpected_files(self):
        """三类偏差都要抓：改内容、少文件、以及多出来的文件（dist 只能有批准产物）。"""
        self.staged.write_all_licenses()
        self._run()

        (self.staged.app / "股市锦囊.exe").write_bytes(b"MZ tampered")
        self.assertEqual(self._run_args(["--verify"]), 1)

        self._run()
        (self.staged.app / "_internal" / "Qt6Core.dll").unlink()
        self.assertEqual(self._run_args(["--verify"]), 1)

        self._run()
        (self.staged.app / "_internal" / "hitchhiker.dll").write_bytes(b"unapproved hitchhiker")
        self.assertEqual(self._run_args(["--verify"]), 1)

    def test_verify_without_a_baseline_manifest_refuses_rather_than_passing(self):
        self.staged.write_all_licenses()

        self.assertEqual(self._run_args(["--verify"]), 2)

    def test_manifest_records_the_source_commit_so_a_build_is_traceable(self):
        self.staged.write_all_licenses()

        self._run()
        source = self._manifest()["source"]

        # 仓库存在时必须记到 commit；不在仓库里跑则记 None，但键本身必须在。
        self.assertIn("commit", source)
        self.assertIn("branch", source)
        if source["commit"] is not None:
            self.assertEqual(len(source["commit"]), 40)

    def test_a_delivery_built_from_another_commit_is_refused(self):
        """清单不能给来历不明的产物盖章：构建提交和仓库提交对不上就拒绝转绿。"""
        self.staged.write_all_licenses()
        self.staged.write_build_info("0" * 40)

        code = self._run()
        source = self._manifest()["source"]

        self.assertEqual(code, 1)
        self.assertFalse(source["build_matches_repo"])
        self.assertEqual(source["build_commit"], "0" * 40)
        self.assertNotEqual(source["repo_commit"], source["build_commit"])

    def test_a_delivery_without_build_info_cannot_prove_its_origin(self):
        """缺 BUILD_INFO.json 就无从证明产物出自哪次构建——同样不能转绿。"""
        self.staged.write_all_licenses()
        (self.staged.app / "BUILD_INFO.json").unlink(missing_ok=True)

        code = self._run()

        self.assertEqual(code, 1)
        self.assertIsNone(self._manifest()["source"]["build_commit"])

    def test_matching_build_and_repo_commits_pass(self):
        self.staged.write_all_licenses()
        head = rel._git("rev-parse", "HEAD")
        if head is None:
            self.skipTest("不在 git 仓库中，无法比对提交")

        code = self._run()
        source = self._manifest()["source"]

        self.assertEqual(code, 0)
        self.assertTrue(source["build_matches_repo"])
        self.assertEqual(source["commit"], head)


if __name__ == "__main__":
    unittest.main()
