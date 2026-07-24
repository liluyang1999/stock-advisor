"""Qt 应用装配与架构边界（REQ-011 / WI-023 / TEST-ARCH-002 / AC-001 / AC-002）。

两件事：
1. **装配**：生产入口把 provider→四个控制器→四个功能页→导航装进主窗，关闭时排空线程池。
2. **边界（TEST-ARCH-002）**：生产源零 tkinter import（AST 静态扫描，不受注释/文档串干扰）；
   核心不 import Qt 的另一半由 G-CORE（check_core_boundaries 的 manifest）逐次门禁强制，
   这里做一次同向复核，两边一致才算迁移干净。
"""

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qt_test_helpers import QtWidgets, qt_app, requires_qt
from test_engine import FakeProvider

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"

if True:
    try:
        from qt_app.app import AppWindow, build_app
    except ImportError:  # pragma: no cover
        AppWindow = build_app = None


def _imported_roots(path: Path) -> set[str]:
    """该文件 import 的顶级包名集合（AST，不看注释/字符串）。"""
    roots: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@requires_qt
class AppAssemblyTests(unittest.TestCase):
    """装配契约：五页导航齐备、控制器接上、关键功能部件真的挂上了、关闭即排空。"""

    def setUp(self):
        self.app = qt_app()

    def _window(self):
        _app, window = build_app([], provider=FakeProvider())
        self.addCleanup(window.deleteLater)
        return window

    def test_every_feature_page_is_navigable(self):
        window = self._window()
        labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        self.assertEqual(
            labels, ["个股分析", "全市场选股", "自选 / 持仓", "条件预警", "个股资金流"]
        )

    def test_every_page_has_its_controller_wired(self):
        window = self._window()
        self.assertEqual(len(window.controllers()), len(set(window.controllers())))
        self.assertEqual(len(window.controllers()), 5)
        for controller in window.controllers():
            self.assertFalse(controller.is_running())  # 装配后处于空闲态

    def test_every_delivered_feature_widget_is_actually_reachable(self):
        """部件存在且有测试 ≠ 用户点得到。

        这条守的是一类真实发生过的缺陷：TierSelector / FactorBars / DetailView /
        ComparisonView 四个部件写好了、单测齐全、却从没被挂进任何页面——于是"五档决策强度""证据""
        仓位计算器""横向对比"在交付物里根本不存在，而需求和变更日志都声称它们已交付。单元测试
        直接构造部件，永远发现不了这件事；只有从装好的主窗往下找才能。
        """
        from qt_app.widgets.candlestick_chart import CandlestickChart
        from qt_app.widgets.detail_view import DetailView
        from qt_app.widgets.factor_bars import FactorBars
        from qt_app.widgets.spectrum_strip import SpectrumStrip
        from qt_app.widgets.tier_selector import TierSelector

        window = self._window()
        for widget_type, feature in (
            (TierSelector, "五档决策强度切换（REQ-003）"),
            (FactorBars, "因子拆解证据（REQ-004）"),
            (DetailView, "理由/风险与仓位风控计算器（REQ-004）"),
            (SpectrumStrip, "决策强度光谱对照（REQ-003/REQ-015）"),
            (CandlestickChart, "K 线（REQ-004）"),
        ):
            with self.subTest(feature=feature):
                self.assertTrue(
                    window.findChildren(widget_type),
                    f"{widget_type.__name__} 没有挂进任何页面——{feature} 用户根本点不到",
                )

        # 横向对比不再是一个独立部件：WI-035 把 ComparisonView 并回自选页的十一列对比表，与老
        # Tkinter 版同形。保证不变（用户点得到横向对比），落点从"部件类"换成"那张表的可访问名"。
        named_tables = {
            table.accessibleName() for table in window.findChildren(QtWidgets.QTableView)
        }
        with self.subTest(feature="自选/持仓横向对比（REQ-005）"):
            self.assertIn(
                "自选持仓横向对比表",
                named_tables,
                "横向对比表没有挂进任何页面——自选/持仓横向对比（REQ-005）用户根本点不到",
            )

    def test_disclaimer_is_resident_in_the_shell(self):
        window = self._window()
        self.assertIn("不构成投资建议", window.statusBar().currentMessage())  # REQ-031

    def test_closing_drains_every_controller(self):
        window = self._window()
        window.show()
        window.close()  # closeEvent → 逐个 shutdown（ADR-0003 生命周期）
        for controller in window.controllers():
            self.assertFalse(controller.is_running())

    def test_help_menu_survives_the_assembly(self):
        window = self._window()
        self.assertFalse(window.help_action.shortcut().isEmpty())  # F1 仍可用


class ArchitectureBoundaryTests(unittest.TestCase):
    """TEST-ARCH-002：静态 import 扫描——生产零 tkinter，核心零 Qt。"""

    def test_production_source_imports_no_tkinter(self):
        offenders = sorted(
            str(p.relative_to(SRC)) for p in SRC.rglob("*.py") if "tkinter" in _imported_roots(p)
        )
        self.assertEqual(offenders, [], f"生产源仍 import tkinter：{offenders}")

    def test_entry_points_import_no_tkinter(self):
        for entry in ("main.py", "scripts/build_exe.py"):
            path = PROJECT_ROOT / entry
            if path.exists():
                with self.subTest(entry=entry):
                    self.assertNotIn("tkinter", _imported_roots(path))

    def test_core_domain_imports_no_qt(self):
        # 与 G-CORE 同向复核：领域核心不得依赖任何 GUI 框架。
        core = SRC / "domain"
        offenders = sorted(
            str(p.relative_to(SRC))
            for p in core.rglob("*.py")
            if {"PySide6", "shiboken6", "tkinter"} & _imported_roots(p)
        )
        self.assertEqual(offenders, [], f"核心域引入了 GUI 框架：{offenders}")


if __name__ == "__main__":
    unittest.main()
