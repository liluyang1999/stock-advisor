"""Qt 应用组装：provider → 控制器 → 功能页 → 导航 → 主窗（REQ-011 / WI-023 / WI-029）。

这是 PySide6 版的**唯一生产入口装配点**：把真实行情 provider 注入五个异步控制器，各控制器驱动
自己的功能页，五页装进一个 QTabWidget 挂到主窗外壳上。壳（main_window）只管窗口/字体/菜单/
免责声明；本模块只管"谁连谁"，不含任何业务或线程逻辑（业务在 services，线程分发在 controllers）。

关闭时按 ADR-0003 生命周期依次 `shutdown()` 每个控制器：请求协作取消并在限时内排空线程池，
避免带着在途 worker 析构（QThreadPool 析构会阻塞等待）。
"""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from data.bounded_adapter import BoundedMarketDataProvider
from domain.alerts import rule_summary

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

        # 具名持有各页：跨页联动（预警横幅、把自选载入分析输入框）需要拿到具体页面，
        # 靠 `tabs.widget(i)` 的下标取页面既脆又读不出意图。
        self.individual_page = IndividualPage(self.analysis, self.settings)
        self.screener_page = ScreenerPage(self.screener, self.settings)
        self.portfolio_page = PortfolioPage(self.portfolio, self.settings)
        self.alerts_page = AlertsPage(self.alerts, self.settings)
        self.fund_flow_page = EvidencePage(self.fund_flow)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setAccessibleName("功能页导航")
        self.tabs.addTab(self.individual_page, "个股分析")
        self.tabs.addTab(self.screener_page, "全市场选股")
        self.tabs.addTab(self.portfolio_page, "自选 / 持仓")
        self.tabs.addTab(self.alerts_page, "条件预警")
        self.tabs.addTab(self.fund_flow_page, "个股资金流")
        self.set_page(self.tabs)
        self._wire_cross_page()
        self._wire_shortcuts()

    def _wire_shortcuts(self) -> None:
        """「开始分析 / 开始选股」按当前页派发（老版 `_run_active_tab`）。

        挂在主窗而不是各页：老版的 Ctrl+Enter/F5 在个股分析页是开始分析、在全市场选股页是
        开始选股，同一个键随页改变含义——这只能由同时看得见两页的一层来决定。此前它挂在个股页上，
        于是切到选股页后按 F5 毫无反应，而应用内的使用说明却写着"在当前页开始分析或开始选股"。
        """

        for sequence in ("Ctrl+Return", "Ctrl+Enter", "F5"):
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence), self)
            shortcut.activated.connect(self.run_active_tab)

    def run_active_tab(self) -> None:
        """触发当前页的主操作；当前页没有主操作就什么都不做。"""

        page = self.tabs.currentWidget()
        action = getattr(page, "_on_analyze", None) or getattr(page, "_on_screen", None)
        if callable(action):
            action()

    def _wire_cross_page(self) -> None:
        """跨页联动：装配点是唯一同时看得见所有页的地方，联动只能接在这里（ADR-0002）。"""

        # 预警触发必须**在哪一页都看得见**。此前它只往「条件预警」页的触发记录里追加一行：
        # 用户坐在个股分析页时，价格预警响了也永远不会知道——而"及时告诉你"正是这个功能的全部意义。
        # 老 Tk 版同时做三件事：结果区弹警示横幅、状态行同文、响一声。这里逐一对应。
        self.alerts.alerts_triggered.connect(self._on_alerts_triggered)
        # 从个股结果直接查资金流：老版是「更多」菜单里拿当前选中行去查，重构后退化成"请到另一页
        # 把刚选中的代码再敲一遍"。页面之间互不认识，联动由此处接。
        self.individual_page.fund_flow_requested.connect(self._show_fund_flow)
        # 自选 → 个股分析：老版自选窗的「载入到输入框」，载入后自动切到分析页。
        self.portfolio_page.load_into_analysis_requested.connect(self._load_into_analysis)

    def _show_fund_flow(self, code: str) -> None:
        self.fund_flow_page.input.setText(code)
        self.tabs.setCurrentWidget(self.fund_flow_page)
        self.fund_flow_page._on_query()

    def _load_into_analysis(self, codes: str) -> None:
        """把代码填进分析页并切过去，但**不自动开跑**——是否消耗一次批量取数由用户决定。"""

        self.individual_page.input.setPlainText(codes)
        self.tabs.setCurrentWidget(self.individual_page)

    def _on_alerts_triggered(self, rules: object) -> None:
        if not isinstance(rules, list) or not rules:
            return
        message = "【预警触发】" + "；".join(rule_summary(rule) for rule in rules)
        self.individual_page.show_alert(message)  # 结果区横幅（老版同一位置与配色）
        self.notify_alert(message)  # 外壳状态栏：切到哪一页都还在
        QtWidgets.QApplication.beep()

    def controllers(self):
        return (self.analysis, self.screener, self.alerts, self.fund_flow, self.portfolio)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 事件命名
        """关闭即排空：先取消再等待线程池，避免在途 worker 撞上析构（ADR-0003）。"""
        for controller in self.controllers():
            controller.shutdown()
        super().closeEvent(event)


def default_provider() -> BoundedMarketDataProvider:
    """出货用的行情 provider（WI-033）。

    有界传输 + 老合同的适配器：整条路径由此拿到总 deadline、协作取消、响应字节上限，以及**真实的
    分页完整度**——老 `EastmoneyProvider` 没有 `market_completeness`，`workflow._provider_completeness`
    便默认「完整」，后续页失败时半个市场会被当作完整市场拿去排序，REQ-026 的警告永不触发。
    """

    return BoundedMarketDataProvider()


def build_app(
    argv: list[str] | None = None, provider=None, settings=None
) -> tuple[QtWidgets.QApplication, AppWindow]:
    """构造完整应用（QApplication + 装好五页的主窗）。返回二元组，便于测试不进事件循环。"""
    app, shell = build_application(argv)
    shell.deleteLater()  # build_application 造的是空壳；这里换成装好页的 AppWindow
    window = AppWindow(provider if provider is not None else default_provider(), settings=settings)
    return app, window


def run_qt_gui(argv: list[str] | None = None) -> int:
    """生产入口：装配、显示、进入事件循环。"""
    app, window = build_app(argv)
    window.show()
    return app.exec()
