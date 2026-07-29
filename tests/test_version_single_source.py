"""版本号只有一个来源，且必须是两段式（loop/governance/VERSION_AND_CHANGE_CONTROL.md）。

这套测试守的是一条容易悄悄失效的约定。此前 `pyproject.toml` 抄了一份字面量，注释还写着
"mirrors src/version.py::__version__"——两处手工同步，迟早对不上，而对不上时
没有任何东西会响。

真源为什么是包而不是 pyproject：本项目没有 `[build-system]`，从不被 pip 安装，因此没有 dist-info，
`importlib.metadata.version()` 在开发期与冻结后的 EXE 里都取不到值。运行期唯一取得到的版本号只能
来自被 import 的模块。pyproject 用 PEP 621 的 `dynamic = ["version"]` 声明"版本不静态写在这里"，
这是标准里专为此准备的表达方式，而不是再抄一遍。
"""

from __future__ import annotations

import re
import sys
import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import version

# 两段式 大版本.小版本，不允许第三段。
_TWO_PART = re.compile(r"^\d+\.\d+$")


def _pyproject() -> dict:
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


class VersionFormatTests(unittest.TestCase):
    def test_version_is_two_part_major_minor(self):
        """`x.x`。三段式（1.0.0）在这个项目里是数据格式版本的形状，不是应用版本的形状。"""
        self.assertRegex(version.__version__, _TWO_PART)

    def test_version_carries_no_stray_characters(self):
        value = version.__version__

        self.assertEqual(value, value.strip())
        for junk in ("#", '"', "'", " "):
            self.assertNotIn(junk, value)


class SingleSourceTests(unittest.TestCase):
    """真源唯一：任何第二处字面量都会被这几条拦下。"""

    def test_pyproject_declares_the_version_dynamic_instead_of_copying_it(self):
        project = _pyproject()["project"]

        self.assertIn("version", project.get("dynamic", []))
        self.assertNotIn(
            "version",
            project,
            "pyproject 又抄了一份版本号字面量；真源是 version.__version__，"
            "这里应当只用 dynamic 引用它",
        )

    def test_the_package_assigns_version_exactly_once(self):
        """`__version__` 在 src/ 下只能被赋值一次——多一处就是多一个真源。"""
        assignments = [
            f"{path.relative_to(PROJECT_ROOT).as_posix()}:{number}"
            for path in (PROJECT_ROOT / "src").rglob("*.py")
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if re.match(r"^__version__\s*=", line)
        ]

        self.assertEqual(
            assignments,
            ["src/version.py:3"],
            f"__version__ 的赋值点不止一个：{assignments}",
        )

    def test_release_manifest_reports_the_same_version_the_app_runs(self):
        """交付清单与 SBOM 写的版本号，必须就是运行期那一个。"""
        import make_release_manifest

        self.assertEqual(make_release_manifest._app_version(), version.__version__)


class UserFacingVersionTests(unittest.TestCase):
    """用户手边能看到的版本号必须来自同一个真源。"""

    def test_generated_manual_shows_the_running_version(self):
        """说明书随交付物分发，是用户唯一能对出"我拿到的是哪一版"的地方——出问题时决定能否复现。"""
        from ui.manual import build_manual_html

        self.assertIn(f"版本 {version.__version__}", build_manual_html())


class ChangelogTests(unittest.TestCase):
    """治理文档要求面向用户的变更日志存在且与版本号对得上。"""

    def setUp(self):
        # 变更日志与其余工程治理文档一同收拢在 loop/ 下；根目录不再保留副本。
        self.path = PROJECT_ROOT / "loop" / "CHANGELOG.md"

    def test_changelog_exists(self):
        self.assertTrue(
            self.path.is_file(), "VERSION_AND_CHANGE_CONTROL.md 要求 loop/CHANGELOG.md 存在"
        )

    def test_no_stray_changelog_at_repository_root(self):
        """根目录不得再出现第二份变更日志——两份并存正是此前漂移的来源。"""
        self.assertFalse(
            (PROJECT_ROOT / "CHANGELOG.md").exists(),
            "变更日志的唯一位置是 loop/CHANGELOG.md，根目录不应再有副本",
        )

    def test_changelog_documents_the_current_version(self):
        text = self.path.read_text(encoding="utf-8")

        self.assertIn(f"[{version.__version__}]", text)

    def test_every_changelog_release_heading_is_two_part(self):
        """变更日志里的发布标题同样受两段式约束——它是版本号最显眼的对外露出。"""
        text = self.path.read_text(encoding="utf-8")
        headings = re.findall(r"^## \[([^\]]+)\]", text, re.MULTILINE)

        self.assertTrue(headings, "CHANGELOG.md 没有任何发布标题")
        for heading in headings:
            if heading == "Unreleased":
                continue
            self.assertRegex(heading, _TWO_PART, f"CHANGELOG 标题 {heading!r} 不是两段式")


if __name__ == "__main__":
    unittest.main()
