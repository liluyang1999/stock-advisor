"""Qt 运行期测试辅助（原先在各 test_qt_* 里各写一份的 _app/_wait_for/skipIf）。

不是测试模块：命名 `qt_test_helpers.py` 不匹配 `test*.py` 收集模式，故 `unittest discover` 与
pytest 都不会把它当用例；模块内也无 Test*/test_* 成员。各 Qt 测试从这里 import 共享辅助。

PySide6 是可选的迁移期依赖，import 用 try/except 守卫——缺失时 `requires_qt` 让相关用例整体 skip。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # pragma: no cover - Qt 是可选的迁移期依赖
    QtCore = QtGui = QtWidgets = None

# 单源的 skip 装饰器：PySide6 不可用则整类跳过（原先 9 个文件各硬编码一份同样的中文原因）。
requires_qt = unittest.skipIf(QtWidgets is None, "PySide6 未安装（pip install --group gui）")


def qt_app():
    """返回进程内唯一的 QApplication（已存在则复用）。"""
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def wait_for(signal, timeout_ms: int = 5000) -> list:
    """阻塞当前(测试)线程的事件循环直到 signal 触发，返回其参数元组列表。不使用 sleep。

    带一个单发看门狗定时器，signal 不来也会在 timeout 后退出循环（返回空列表），避免测试挂死。
    """
    loop = QtCore.QEventLoop()
    captured: list = []

    def _catch(*args):
        captured.append(args)
        loop.quit()

    signal.connect(_catch)
    guard = QtCore.QTimer()
    guard.setSingleShot(True)
    guard.timeout.connect(loop.quit)
    guard.start(timeout_ms)
    loop.exec()
    return captured


def temp_settings(case):
    r"""给测试一份指向临时文件的 `Settings`，随用例自动清理。

    存在的理由很具体：页面需要 `Settings`，而 `Settings` 的 path 是必填的——因为曾经它可选、
    缺省读用户真实的 `%APPDATA%\股市锦囊\config.json`，于是测试真的把 `level` 写进了用户配置。
    每个用例各写一遍临时目录样板迟早有人图省事跳过，所以在这里给一条最省事的正确路径。
    """
    import tempfile
    from pathlib import Path

    from qt_app.settings import Settings

    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    return Settings(Path(tmp.name) / "config.json")
