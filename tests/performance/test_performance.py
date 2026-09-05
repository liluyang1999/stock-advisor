"""性能与资源预算（REQ-013/028/034 / WI-022 / TEST-PERF-001 / performance-budgets.json）。

对可离屏自动化的预算逐项测量并断言不超预算，阈值单一真源取自 performance-budgets.json。RSS/内存
增长为 Windows-only（ctypes 读，产品目标平台）；表格滚动 fps（需真实合成器/vsync）与 onefile EXE
体积（TEST-PKG-002，随 WI-024 的构建）不在离屏范围，由 CI/构建门禁覆盖。
"""

import os
import pathlib
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/ → qt_test_helpers
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))  # tests/performance/ → bench_util

from bench_util import load_budgets, percentile, rss_mib, time_ms
from qt_test_helpers import QtCore, QtGui, QtWidgets, qt_app, requires_qt

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BUDGETS = load_budgets()
_WINDOWS_ONLY = unittest.skipUnless(sys.platform == "win32", "RSS 测量为 Windows-only（ctypes）")

if QtWidgets is not None:
    from qt_app.dialogs import HelpDialog


def _model_5000():
    model = QtGui.QStandardItemModel(5000, 6)
    for row in range(5000):
        model.setItem(row, 3, QtGui.QStandardItem(str((row * 7919) % 5000)))  # 分数列乱序
    return model


@requires_qt
class ComputeAndMemoryBudgetTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def test_table_5000_sort_within_p95_budget(self):
        model = _model_5000()
        samples = [time_ms(model.sort, 3, QtGui.Qt.SortOrder.AscendingOrder) for _ in range(20)]
        p95 = percentile(samples, 95)
        self.assertLessEqual(
            p95, _BUDGETS["table_5000_sort_filter_ms"]["p95_max"], f"p95={p95:.1f}ms"
        )

    def test_gui_event_handler_within_p95_budget(self):
        # 用一个代表性槽（往结果模型追加一行）代表事件处理开销。
        model = QtGui.QStandardItemModel(0, 6)

        def handler():
            model.appendRow([QtGui.QStandardItem("x") for _ in range(6)])

        samples = [time_ms(handler) for _ in range(50)]
        p95 = percentile(samples, 95)
        self.assertLessEqual(p95, _BUDGETS["gui_event_handler_ms"]["p95_max"], f"p95={p95:.2f}ms")

    @_WINDOWS_ONLY
    def test_idle_rss_within_budget(self):
        _app, window = _assembled_window(self)
        self.addCleanup(window.deleteLater)
        window.show()
        self.app.processEvents()
        rss = rss_mib()
        self.assertIsNotNone(rss)
        self.assertLessEqual(rss, _BUDGETS["idle_rss_mib"]["max"], f"idle RSS={rss:.1f}MiB")

    @_WINDOWS_ONLY
    def test_dialog_100_cycles_rss_growth_within_budget(self):
        _app, window = _assembled_window(self)
        self.addCleanup(window.deleteLater)
        window.show()
        self.app.processEvents()
        before = rss_mib()
        for _ in range(100):
            dialog = HelpDialog(window)
            dialog.show()
            self.app.processEvents()
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()
            # processEvents 默认不处理 DeferredDelete；显式清掉，否则 100 个对话框只是攒着没释放，
            # 量到的是"延迟删除积压"而非真实增长。
            self.app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        growth = rss_mib() - before
        self.assertLessEqual(
            growth, _BUDGETS["dialog_100_cycles_rss_growth_mib"]["max"], f"growth={growth:.1f}MiB"
        )


def _assembled_window(case):
    """装好五页的真主窗。

    此前性能用例量的是 `build_application([])`——main_window 的空壳。数字没有造假，但量错了对象：
    预算文档声称描述"应用"，而空壳里没有页面、没有表格、没有图。RSS 与启动时间都会因此系统性偏低。
    """
    import tempfile

    from test_engine import FakeProvider

    from qt_app.app import build_app
    from qt_app.settings import Settings

    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    settings = Settings(pathlib.Path(tmp.name) / "config.json")
    return build_app([], provider=FakeProvider(), settings=settings)


@requires_qt
class StartupBudgetTests(unittest.TestCase):
    """冷/热启动：子进程从启动到主窗首次 show 的墙钟时间（离屏；真实渲染冷启动的下界代理）。"""

    @staticmethod
    def _launch_seconds() -> float:
        import time

        # 起的必须是装好五页的真应用。此前这里 build_application([]) 起的是空壳——数字是真的，
        # 量的却不是产品：用户等待的是页面、表格与图都构建完成，不是一个空窗口显示出来。
        code = (
            "import sys, tempfile, pathlib; sys.path.insert(0, r'"
            + str(PROJECT_ROOT / "src")
            + "'); "
            "from qt_app.app import build_app; "
            "from qt_app.settings import Settings; "
            "tmp = tempfile.TemporaryDirectory(); "
            "a, w = build_app([], settings=Settings(pathlib.Path(tmp.name) / 'config.json')); "
            "w.show(); w.close(); tmp.cleanup()"
        )
        env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
        start = time.perf_counter()
        subprocess.run(
            [sys.executable, "-c", code], env=env, check=True, capture_output=True, timeout=30
        )
        return time.perf_counter() - start

    def test_cold_and_warm_start_within_p95_budget(self):
        runs = [self._launch_seconds() for _ in range(5)]
        cold = runs[0]  # 首次：进程/解释器/Qt 冷载
        warm_p95 = percentile(runs[1:], 95)  # 其后：OS 文件缓存热
        self.assertLessEqual(cold, _BUDGETS["cold_start_seconds"]["p95_max"], f"cold={cold:.2f}s")
        self.assertLessEqual(
            warm_p95, _BUDGETS["warm_start_seconds"]["p95_max"], f"warm p95={warm_p95:.2f}s"
        )


if __name__ == "__main__":
    unittest.main()
