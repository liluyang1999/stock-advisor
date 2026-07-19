"""预警监控页（REQ-006/010/013 / REQ-031 / WI-016）。

薄视图：规则表 + 监控开关 + 触发记录 + 状态行，连 `AlertController`。页面不含监控或线程逻辑——
点"开始监控"就 `controller.start()`，新触发经信号回来追加到触发记录。QTimer/generation/失败隔离
都在控制器/编排层。
"""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from ...domain.alerts import rule_summary
from ...domain.models import CORE_DISCLAIMER, AlertRule
from ..controllers.alert_controller import AlertController
from ..widgets.table_utils import make_readonly_table

_RULE_HEADERS = ["规则", "启用"]


class AlertsPage(QtWidgets.QWidget):
    def __init__(
        self, controller: AlertController, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._build_ui()
        self._connect()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        self.rule_model, self.rule_table = make_readonly_table(_RULE_HEADERS)
        self.rule_table.setAccessibleName("预警规则表")  # REQ-017 可访问名
        layout.addWidget(self.rule_table)

        row = QtWidgets.QHBoxLayout()
        self.monitor_button = QtWidgets.QPushButton("开始监控")
        self.monitor_button.setCheckable(True)
        row.addWidget(self.monitor_button)
        row.addStretch(1)
        layout.addLayout(row)

        layout.addWidget(QtWidgets.QLabel("触发记录"))
        self.triggered = QtWidgets.QPlainTextEdit()
        self.triggered.setReadOnly(True)
        layout.addWidget(self.triggered)

        # REQ-031：结果视图常驻免责声明。
        self.status = QtWidgets.QLabel(CORE_DISCLAIMER)
        layout.addWidget(self.status)

    def _connect(self) -> None:
        self.monitor_button.toggled.connect(self._on_monitor_toggled)
        self._controller.alerts_triggered.connect(self._on_triggered)

    def set_rules(self, rules: list[AlertRule]) -> None:
        self._controller.set_rules(rules)
        self.rule_model.removeRows(0, self.rule_model.rowCount())
        for rule in rules:
            cells = [rule_summary(rule), "是" if rule.enabled else "否"]
            self.rule_model.appendRow([QtGui.QStandardItem(text) for text in cells])

    def _on_monitor_toggled(self, checked: bool) -> None:
        if checked:
            self.monitor_button.setText("停止监控")
            self.status.setText(f"监控中…　|　{CORE_DISCLAIMER}")
            self._controller.start()
        else:
            self.monitor_button.setText("开始监控")
            self.status.setText(f"已停止监控　|　{CORE_DISCLAIMER}")
            self._controller.stop()

    def _on_triggered(self, rules: list[AlertRule]) -> None:
        for rule in rules:
            self.triggered.appendPlainText(f"⚠ {rule_summary(rule)}")
