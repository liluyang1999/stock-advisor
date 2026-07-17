"""Qt 主窗外壳（REQ-011 / REQ-014 / REQ-031 / WI-004）。

只做外壳：窗口、标题栏身份、字体落地、免责声明常驻。业务逻辑不进这里（ADR-0002）——
各功能页在后续 WI（WI-010 起）以 page/controller 的形式挂进 `set_page`。
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..domain.models import CORE_DISCLAIMER
from ..ui import assets, theme
from .theme import fonts


class MainWindow(QtWidgets.QMainWindow):
    """应用外壳。

    REQ-014：应用图标与「股市锦囊」只出现在原生标题栏，内容区不得再重复一遍——
    Tk 版是自绘标题带，Qt 用原生标题栏即天然满足，故内容区刻意不放品牌头。
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(theme.APP_TITLE)
        self.setMinimumSize(QtCore.QSize(*theme.MAIN_MIN_SIZE))
        self._apply_window_icon()

        self._content = QtWidgets.QStackedWidget()
        self.setCentralWidget(self._build_central(self._content))
        self.statusBar().showMessage(CORE_DISCLAIMER)

    def _apply_window_icon(self) -> None:
        path = assets.app_asset_path(theme.APP_ICON_FILENAME)
        if path is not None and path.exists():
            self.setWindowIcon(QtGui.QIcon(str(path)))

    def _build_central(self, content: QtWidgets.QWidget) -> QtWidgets.QWidget:
        holder = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(holder)
        layout.setContentsMargins(
            theme.CONTENT_MARGIN, theme.CONTENT_MARGIN, theme.CONTENT_MARGIN, theme.CONTENT_MARGIN
        )
        layout.addWidget(content)
        # REQ-031：免责声明在结果视图常驻。状态栏是外壳级常驻位，页面切换不会带走它。
        return holder

    def set_page(self, page: QtWidgets.QWidget) -> None:
        """挂载一个功能页。后续 WI 的页面由此进入外壳。"""

        self._content.addWidget(page)
        self._content.setCurrentWidget(page)

    def report_font_fallback(self, note: str) -> None:
        """把字体回退可见地告知用户（REQ-033：不得静默用错字体渲染）。"""

        self.statusBar().showMessage(f"{note}　|　{CORE_DISCLAIMER}")


def build_application(argv: list[str] | None = None) -> tuple[QtWidgets.QApplication, MainWindow]:
    """构造 QApplication + 主窗，并落地字体契约。

    返回二元组而非直接 exec：测试要在不进事件循环的前提下检查外壳（pytest-qt 亦然）。
    """

    # QApplication.instance() 的静态类型是 QCoreApplication|None（它是 QCoreApplication 上的
    # 类方法），但在有 widgets 的进程里实例必然是 QApplication；显式收窄而非忽略类型。
    existing = QtWidgets.QApplication.instance()
    app = (
        existing
        if isinstance(existing, QtWidgets.QApplication)
        else QtWidgets.QApplication(argv or [])
    )
    resolved = fonts.apply_app_font(app)
    window = MainWindow()
    if resolved.fallback_note is not None:
        window.report_font_fallback(resolved.fallback_note)
    return app, window


def run_qt_gui(argv: list[str] | None = None) -> int:
    app, window = build_application(argv)
    window.show()
    return app.exec()
