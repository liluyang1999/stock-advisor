"""Qt 应用组装：provider → 控制器 → 功能页 → 导航 → 主窗（REQ-011 / WI-023 / WI-029）。

这是 PySide6 版的**唯一生产入口装配点**：把真实行情 provider 注入五个异步控制器，各控制器驱动
自己的功能页，五页装进一个 QTabWidget 挂到主窗外壳上。壳（main_window）只管窗口/字体/菜单/
免责声明；本模块只管"谁连谁"，不含任何业务或线程逻辑（业务在 services，线程分发在 controllers）。

关闭时按 ADR-0003 生命周期依次 `shutdown()` 每个控制器：请求协作取消并在限时内排空线程池，
避免带着在途 worker 析构（QThreadPool 析构会阻塞等待）。
"""

from __future__ import annotations

from PySide6 import QtWidgets

from ..data.data_provider import EastmoneyProvider
from .controllers.alert_controller import AlertController
from .controllers.analysis_controller import AnalysisController
from .controllers.fund_flow_controller import FundFlowController
from .controllers.screener_controller import ScreenerController
from .main_window import MainWindow, build_application
from .pages.alerts_page import AlertsPage
from .pages.evidence_page import EvidencePage
from .pages.individual_page import IndividualPage
from .pages.portfolio_page import PortfolioPage
from .pages.screener_page import ScreenerPage
from .settings import Settings


class AppWindow(MainWindow):
    """主窗 + 五页导航。持有控制器，关闭时负责把它们排空。"""

    def __init__(self, provider, parent: QtWidgets.QWidget | None = None, settings=None) -> None:
        super().__init__(parent)
        self.analysis = AnalysisController(provider, self)
        self.screener = ScreenerController(provider, self)
        self.alerts = AlertController(provider, self)
        self.fund_flow = FundFlowController(provider, self)
        # 自选页自带一份分析控制器：与个股页共用会让两页的信号互相串扰，一页的取消也会打断另一页。
        self.portfolio = AnalysisController(provider, self)
        # 进程内唯一的配置持有者：各页共用，避免各存各的互相覆盖（REQ-009）。
        self.settings = settings if settings is not None else Settings.for_user()

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setAccessibleName("功能页导航")
        self.tabs.addTab(IndividualPage(self.analysis, self.settings), "个股分析")
        self.tabs.addTab(ScreenerPage(self.screener, self.settings), "全市场选股")
        self.tabs.addTab(PortfolioPage(self.portfolio, self.settings), "自选 / 持仓")
        self.tabs.addTab(AlertsPage(self.alerts), "条件预警")
        self.tabs.addTab(EvidencePage(self.fund_flow), "个股资金流")
        self.set_page(self.tabs)

    def controllers(self):
        return (self.analysis, self.screener, self.alerts, self.fund_flow, self.portfolio)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 事件命名
        """关闭即排空：先取消再等待线程池，避免在途 worker 撞上析构（ADR-0003）。"""
        for controller in self.controllers():
            controller.shutdown()
        super().closeEvent(event)


def build_app(
    argv: list[str] | None = None, provider=None, settings=None
) -> tuple[QtWidgets.QApplication, AppWindow]:
    """构造完整应用（QApplication + 装好五页的主窗）。返回二元组，便于测试不进事件循环。"""
    app, shell = build_application(argv)
    shell.deleteLater()  # build_application 造的是空壳；这里换成装好页的 AppWindow
    window = AppWindow(provider if provider is not None else EastmoneyProvider(), settings=settings)
    return app, window


def run_qt_gui(argv: list[str] | None = None) -> int:
    """生产入口：装配、显示、进入事件循环。"""
    app, window = build_app(argv)
    window.show()
    return app.exec()
