"""自选 / 持仓页（REQ-005 / REQ-009 / WI-015 / WI-029）。

一张自选表（可填成本与股数）+ 一次刷新 = 横向对比。**盈亏由 `domain.compare` 算，本页不自造数字**；
没填成本就没有盈亏，表里显示破折号而不是 0——把"没填"显示成"不赚不亏"是伪造。

持久化复用 `services.store`：自选股与持仓成本/股数跨会话保留（REQ-009），改动即存盘，因此用户不必
记得点保存。分析复用 `AnalysisController`——本页持有自己的实例而不是与个股页共用，两页各自的信号
互不串扰，取消也互不影响。
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...domain import money
from ...domain.models import CORE_DISCLAIMER
from ...services import store
from ...services.batch import BatchReport
from ...services.workflow import AnalysisOutcome
from ..controllers.analysis_controller import AnalysisController
from ..settings import Settings
from ..widgets.comparison_view import ComparisonView
from ..widgets.table_utils import make_readonly_table

_HEADERS = ["代码", "成本", "股数"]


class PortfolioPage(QtWidgets.QWidget):
    def __init__(
        self,
        controller: AnalysisController,
        settings: Settings,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._settings = settings
        self._outcomes: dict[str, AnalysisOutcome] = {}
        self._build_ui()
        self._connect()
        self._reload_table()

    # --- 构建 ---

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        row = QtWidgets.QHBoxLayout()
        self.code_input = QtWidgets.QLineEdit()
        self.code_input.setPlaceholderText("股票代码")
        self.code_input.setAccessibleName("自选股代码输入")
        self.cost_input = QtWidgets.QLineEdit()
        self.cost_input.setPlaceholderText("持仓成本（可空）")
        self.cost_input.setAccessibleName("持仓成本输入")
        self.shares_input = QtWidgets.QLineEdit()
        self.shares_input.setPlaceholderText("股数（可空）")
        self.shares_input.setAccessibleName("持仓股数输入")
        self.add_button = QtWidgets.QPushButton("加入自选")
        self.remove_button = QtWidgets.QPushButton("移除选中")
        row.addWidget(self.code_input, 2)
        row.addWidget(self.cost_input, 1)
        row.addWidget(self.shares_input, 1)
        row.addWidget(self.add_button)
        row.addWidget(self.remove_button)
        layout.addLayout(row)

        self.model, self.table = make_readonly_table(_HEADERS)
        self.table.setAccessibleName("自选持仓表")
        self.table.setMaximumHeight(160)
        layout.addWidget(self.table)

        action_row = QtWidgets.QHBoxLayout()
        self.refresh_button = QtWidgets.QPushButton("刷新对比")
        self.stop_button = QtWidgets.QPushButton("停止")
        self.stop_button.setEnabled(False)
        action_row.addStretch(1)
        action_row.addWidget(self.refresh_button)
        action_row.addWidget(self.stop_button)
        layout.addLayout(action_row)

        self.comparison = ComparisonView()
        layout.addWidget(self.comparison, 1)

        self.status = QtWidgets.QLabel(CORE_DISCLAIMER)
        layout.addWidget(self.status)

    def _connect(self) -> None:
        self.add_button.clicked.connect(self.add_current_input)
        self.remove_button.clicked.connect(self.remove_selected)
        self.refresh_button.clicked.connect(self.refresh)
        self.stop_button.clicked.connect(self._controller.cancel)
        self._controller.symbol_analyzed.connect(self._on_symbol)
        self._controller.batch_finished.connect(self._on_finished)

    # --- 自选维护（改动即存盘）---

    def add_current_input(self) -> None:
        code = self.code_input.text().strip()
        if not code:
            return
        item = store.WatchItem(
            code=code,
            cost=money.positive_money(self.cost_input.text()),
            shares=_optional_int(self.shares_input.text()),
        )
        # 同一只票再次加入视为更新成本/股数，而不是产生第二行。
        kept = [w for w in self._config.watchlist if w.code.lower() != code.lower()]
        self._persist([*kept, item])
        self.code_input.clear()
        self.cost_input.clear()
        self.shares_input.clear()
        self._reload_table()

    def remove_selected(self) -> None:
        index = self.table.currentIndex()
        if not index.isValid():
            return
        cell = self.model.item(index.row(), 0)
        if cell is None:
            return
        code = cell.text()
        self._persist([w for w in self._config.watchlist if w.code != code])
        self._outcomes.pop(code, None)
        self._reload_table()
        self._render_comparison()

    @property
    def _config(self) -> store.AppConfig:
        return self._settings.config

    def _persist(self, watchlist: list[store.WatchItem]) -> None:
        """经共享 Settings 做读-改-写：只动 watchlist，不会把别的页刚存的本金/档位覆盖掉。

        存盘失败不该让界面崩，也不该假装成功：update 返回 False 时如实提示。
        """
        if not self._settings.update(watchlist=watchlist):
            self.status.setText(f"自选保存失败（配置文件不可写）　|　{CORE_DISCLAIMER}")

    def _reload_table(self) -> None:
        self.model.removeRows(0, self.model.rowCount())
        for watch in self._config.watchlist:
            cells = [
                watch.code,
                "—" if watch.cost is None else f"{watch.cost:.2f}",
                "—" if watch.shares is None else str(watch.shares),
            ]
            self.model.appendRow([QtGui.QStandardItem(text) for text in cells])

    # --- 刷新对比 ---

    def refresh(self) -> None:
        if not self._config.watchlist:
            self.status.setText(f"自选为空，先加入股票代码　|　{CORE_DISCLAIMER}")
            return
        self._outcomes.clear()
        self.refresh_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("刷新中…")
        self._controller.start(" ".join(w.code for w in self._config.watchlist))

    def _on_symbol(self, outcome: AnalysisOutcome) -> None:
        self._outcomes[outcome.symbol.normalized] = outcome

    def _on_finished(self, report: BatchReport) -> None:
        del report
        self.refresh_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._render_comparison()

    def _render_comparison(self) -> None:
        """把分析结果与自选里的成本/股数配对后交给 domain 组装对比行。

        没有 measurement 的项先过滤掉——`build_comparison_rows` 的契约要求调用方这么做，失败的票
        不该以一行空数据混进对比表。
        """
        by_code = {w.code.lower(): w for w in self._config.watchlist}
        entries = []
        for outcome in self._outcomes.values():
            if not outcome.ok or outcome.result is None or outcome.measurement is None:
                continue
            watch = by_code.get(outcome.symbol.normalized.lower()) or by_code.get(
                outcome.result.symbol.display.lower()
            )
            entries.append(
                {
                    "result": outcome.result,
                    "measurement": outcome.measurement,
                    "risk": outcome.quality.level,
                    "cost": None if watch is None else watch.cost,
                    "shares": None if watch is None else watch.shares,
                }
            )
        self.comparison.set_entries(entries)
        shown = len(entries)
        missing = len(self._outcomes) - shown
        note = f"对比 {shown} 只" + (f"，{missing} 只取数失败未纳入" if missing else "")
        self.status.setText(f"{note}　|　{CORE_DISCLAIMER}")


def _optional_int(text: str) -> int | None:
    try:
        value = int(float(text.strip()))
    except TypeError, ValueError:
        return None
    return value if value > 0 else None


_ = QtCore  # 保留导入以备后续信号扩展；显式引用避免 lint 误报
