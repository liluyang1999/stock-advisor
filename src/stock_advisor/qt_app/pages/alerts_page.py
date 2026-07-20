"""预警监控页（REQ-006/010/013 / REQ-031 / WI-016）。

薄视图：规则表 + 监控开关 + 触发记录 + 状态行，连 `AlertController`。页面不含监控或线程逻辑——
点"开始监控"就 `controller.start()`，新触发经信号回来追加到触发记录。QTimer/generation/失败隔离
都在控制器/编排层。
"""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from ...domain.alerts import FIELD_KEYS_BY_LABEL, FIELD_LABELS, OPS, rule_summary
from ...domain.models import CORE_DISCLAIMER, AlertRule
from ..controllers.alert_controller import AlertController
from ..settings import Settings
from ..widgets.table_utils import make_readonly_table

_RULE_HEADERS = ["规则", "启用"]


class AlertsPage(QtWidgets.QWidget):
    def __init__(
        self,
        controller: AlertController,
        settings: Settings,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._settings = settings
        self._build_ui()
        self._connect()
        # 规则跨会话保留（REQ-009）。此前没有任何生产代码调用 set_rules，规则表永远是空的，
        # 界面上也没有新建规则的入口——条件预警因此实际不可用。
        self.set_rules(list(self._settings.config.alerts))

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        self.rule_model, self.rule_table = make_readonly_table(_RULE_HEADERS, "预警规则表")
        layout.addWidget(self.rule_table)

        # 新建规则：代码 + 字段 + 比较 + 阈值。字段下拉显示中文标签，写库时映射回 domain 的键。
        editor = QtWidgets.QHBoxLayout()
        self.rule_code = QtWidgets.QLineEdit()
        self.rule_code.setPlaceholderText("股票代码")
        self.rule_code.setAccessibleName("预警股票代码输入")
        self.rule_field = QtWidgets.QComboBox()
        self.rule_field.setAccessibleName("预警字段选择")
        for label in FIELD_LABELS.values():
            self.rule_field.addItem(label)
        self.rule_op = QtWidgets.QComboBox()
        self.rule_op.setAccessibleName("预警比较方式选择")
        for op in OPS:
            self.rule_op.addItem(op)
        self.rule_threshold = QtWidgets.QLineEdit()
        self.rule_threshold.setPlaceholderText("阈值")
        self.rule_threshold.setAccessibleName("预警阈值输入")
        self.add_rule_button = QtWidgets.QPushButton("添加规则")
        self.remove_rule_button = QtWidgets.QPushButton("删除选中")
        for widget in (
            self.rule_code,
            self.rule_field,
            self.rule_op,
            self.rule_threshold,
            self.add_rule_button,
            self.remove_rule_button,
        ):
            editor.addWidget(widget)
        layout.addLayout(editor)

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
        self.add_rule_button.clicked.connect(self.add_current_rule)
        self.remove_rule_button.clicked.connect(self.remove_selected_rule)
        self.monitor_button.toggled.connect(self._on_monitor_toggled)
        self._controller.alerts_triggered.connect(self._on_triggered)

    def add_current_rule(self) -> None:
        """新建一条规则并落盘。代码或阈值不合法就明说，不静默吞掉用户的输入。"""
        code = self.rule_code.text().strip()
        threshold = _optional_float(self.rule_threshold.text())
        if not code or threshold is None:
            self.status.setText(f"请填写股票代码与数字阈值　|　{CORE_DISCLAIMER}")
            return
        rule = AlertRule(
            code=code,
            field=FIELD_KEYS_BY_LABEL[self.rule_field.currentText()],
            op=self.rule_op.currentText(),
            threshold=threshold,
        )
        self._persist([*self._settings.config.alerts, rule])
        self.rule_code.clear()
        self.rule_threshold.clear()

    def remove_selected_rule(self) -> None:
        index = self.rule_table.currentIndex()
        if not index.isValid():
            return
        remaining = [
            rule for i, rule in enumerate(self._settings.config.alerts) if i != index.row()
        ]
        self._persist(remaining)

    def _persist(self, rules: list[AlertRule]) -> None:
        """经共享 Settings 读-改-写，只动 alerts；存盘失败如实提示，不假装存上了。"""
        if not self._settings.update(alerts=rules):
            self.status.setText(f"预警保存失败（配置文件不可写）　|　{CORE_DISCLAIMER}")
        self.set_rules(list(self._settings.config.alerts))

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


def _optional_float(text: str) -> float | None:
    try:
        return float(text.strip())
    except TypeError, ValueError:
        return None
