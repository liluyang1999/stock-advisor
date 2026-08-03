"""条件预警页（REQ-006/009/010/013/031 / WI-016 / WI-035）。

薄视图：规则表 + 新建规则 + 监控开关 + 触发记录 + 状态行，连 `AlertController`。页面不含监控或
线程逻辑——点开关就 `controller.start()/stop()`，新触发经信号回来追加到触发记录。QTimer/generation/
失败隔离都在控制器与编排层。

**版式复刻 WI-023 之前的 Tkinter 版**（WI-035）。老版这一块是一个对话框，装进一页后是两张卡：

    条件预警  —— 规则/启用/触发/监控 四格指标条 + 两列规则表 + 新建规则行 + 实时预警开关
    触发记录  —— 只读文本，逐条记下本次会话里跨过阈值的规则

重构前这一页是一个扁平的 QVBoxLayout：一张无格式的规则表、一行挤在一起的新建控件、一个写着
"开始监控"的普通按钮、一个无标题的文本框。老版最有用的那条四格指标条（尤其是"监控 开/关"这个
一眼可见的状态）整个不见了，开关也退化成一颗看不出当前状态的按钮。
"""

from __future__ import annotations

from dataclasses import replace

from PySide6 import QtCore, QtWidgets

from domain.alerts import (
    FIELD_KEYS_BY_LABEL,
    FIELD_LABELS,
    OPS,
    rule_key,
    rule_summary,
)
from domain.input_validate import parse_alert_threshold
from domain.models import CORE_DISCLAIMER, AlertRule
from domain.symbols import normalize_symbol

from ..controllers.alert_controller import AlertController
from ..settings import Settings
from ..widgets.cards import Card, StatStrip, divider, gap, label, scrolling_page
from ..widgets.table_utils import Column, make_readonly_table, make_row, table_height

_LEFT = QtCore.Qt.AlignmentFlag.AlignLeft
_CENTRE = QtCore.Qt.AlignmentFlag.AlignHCenter

# 两列，列名/宽度/对齐沿用老版预警窗的 Treeview（app_alerts.py 的 rule/enabled 两列）。
RULE_COLUMNS: list[Column] = [
    Column("rule", "规则", 440, _LEFT),
    Column("enabled", "启用", 80, _CENTRE),
]

_ALERT_CELLS = ["规则", "启用", "触发", "监控"]


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
        self._rules: list[AlertRule] = []
        # 本次会话已触发过的规则键。老版直接读监控循环的 `_fired` 集合；Qt 版的 fired 状态住在
        # 控制器里（跨轮边沿判定要用），页面另记一份只为四格指标里的"触发"计数，不参与判定。
        self._fired: set = set()
        self._build_ui()
        self._connect()
        # 规则跨会话保留（REQ-009）。此前没有任何生产代码调用 set_rules，规则表永远是空的，
        # 界面上也没有新建规则的入口——条件预警因此实际不可用。
        self.set_rules(list(self._settings.config.alerts))

    # ---------------- 构建 ----------------

    def _build_ui(self) -> None:
        layout = scrolling_page(self)

        layout.addWidget(self._build_rules_card())
        layout.addWidget(self._build_log_card())

        # REQ-031：结果视图常驻免责声明，整页只此一处。
        self.status = label(CORE_DISCLAIMER, "hint", wrap=True)
        layout.addWidget(self.status)
        layout.addStretch(1)

    def _build_rules_card(self) -> Card:
        card = Card("条件预警", "价格、涨跌幅或综合分越过阈值时提醒；仅在程序开启且空闲时轮询。")
        self.stats = StatStrip(_ALERT_CELLS)
        card.body().addWidget(self.stats)
        card.body().addWidget(divider())

        self.rule_model, self.rule_table = make_readonly_table(
            RULE_COLUMNS,
            "预警规则表",
            empty_hint="还没有预警规则。在下方选好字段、条件与阈值，点「添加」。",
        )
        # 至少放得下四行，超过九行转内部滚动——老版这张 Treeview 是 height=9 的固定高度。
        self.rule_table.setMinimumHeight(table_height(4))
        self.rule_table.setMaximumHeight(table_height(9))
        card.body().addWidget(self.rule_table)

        card.body().addLayout(self._build_editor_row())
        card.body().addLayout(self._build_monitor_row())
        return card

    def _build_editor_row(self) -> QtWidgets.QHBoxLayout:
        """新建规则行：代码 / 字段 / 条件 / 阈值 + 添加 / 删除选中，与老版表单同序同文案。

        字段下拉显示中文标签，写库时映射回 domain 的键（求值与展示都按键索引，不受文案影响）。
        """

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(gap(0))

        self.rule_code = QtWidgets.QLineEdit()
        self.rule_code.setPlaceholderText("股票代码")
        # REQ-017 可访问名：输入框/下拉无文本，屏幕阅读器需显式名（按钮由文本自动取名）。
        self.rule_code.setAccessibleName("预警股票代码输入")
        self.rule_code.setFixedWidth(110)
        self.rule_field = QtWidgets.QComboBox()
        self.rule_field.setAccessibleName("预警字段选择")
        self.rule_field.setFixedWidth(96)
        for text in FIELD_LABELS.values():
            self.rule_field.addItem(text)
        self.rule_op = QtWidgets.QComboBox()
        self.rule_op.setAccessibleName("预警比较方式选择")
        self.rule_op.setFixedWidth(72)
        for op in OPS:
            self.rule_op.addItem(op)
        self.rule_threshold = QtWidgets.QLineEdit()
        self.rule_threshold.setPlaceholderText("阈值")
        self.rule_threshold.setAccessibleName("预警阈值输入")
        self.rule_threshold.setFixedWidth(96)
        for caption, field in (
            ("代码", self.rule_code),
            ("字段", self.rule_field),
            ("条件", self.rule_op),
            ("阈值", self.rule_threshold),
        ):
            row.addWidget(label(caption, "hint"))
            row.addWidget(field)

        row.addWidget(divider(QtCore.Qt.Orientation.Vertical))
        self.add_rule_button = QtWidgets.QPushButton("添加")
        self.add_rule_button.setProperty("role", "primary")
        self.remove_rule_button = QtWidgets.QPushButton("删除选中")
        row.addWidget(self.add_rule_button)
        # 「启用」列一直显示是/否，却没有任何地方能改它——`AlertRule.enabled` 默认 True，于是那一列
        # 恒为「是」，想临时静音一条规则只能删掉、以后再重新敲一遍。老版在「更多操作」里有这一项。
        self.toggle_rule_button = QtWidgets.QPushButton("启用 / 停用")
        row.addWidget(self.toggle_rule_button)
        row.addWidget(self.remove_rule_button)
        row.addStretch(1)
        return row

    def _build_monitor_row(self) -> QtWidgets.QHBoxLayout:
        """实时预警开关：一颗可切换按钮，文案自带当前状态（老版的反相药丸 Checkbutton）。

        默认关。此前它是一颗写着"开始监控"的普通按钮——按下去之后它到底开着没有，界面上没有
        任何地方说得出来。
        """

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(gap(0))
        self.monitor_button = QtWidgets.QPushButton("实时预警 关")
        self.monitor_button.setProperty("role", "switch")
        self.monitor_button.setCheckable(True)
        row.addWidget(self.monitor_button)
        row.addWidget(label("开启后每 60 秒检查一次已启用的规则；程序关闭即停止。", "hint"))
        row.addStretch(1)
        return row

    def _build_log_card(self) -> Card:
        card = Card("触发记录", "规则由未满足跨到满足时记一条；持续满足不会重复刷屏。")
        self.triggered = QtWidgets.QPlainTextEdit()
        self.triggered.setReadOnly(True)
        self.triggered.setAccessibleName("预警触发记录")
        self.triggered.setPlaceholderText(
            "尚无触发记录。开启实时预警后，跨过阈值的规则会逐条出现在这里。"
        )
        self.triggered.setMinimumHeight(140)
        card.body().addWidget(self.triggered)
        return card

    def _connect(self) -> None:
        self.add_rule_button.clicked.connect(self.add_current_rule)
        self.remove_rule_button.clicked.connect(self.remove_selected_rule)
        self.toggle_rule_button.clicked.connect(self.toggle_selected_rule)
        self.monitor_button.toggled.connect(self._on_monitor_toggled)
        self._controller.alerts_triggered.connect(self._on_triggered)

    # ---------------- 规则维护（改动即存盘）----------------

    def add_current_rule(self) -> None:
        """新建一条规则并落盘。代码或阈值不合法就明说，不静默吞掉用户的输入。"""
        code = _normalized_code(self.rule_code.text())
        threshold = parse_alert_threshold(self.rule_threshold.text())
        if code is None or threshold is None:
            self.status.setText(f"请填写有效的股票代码与数字阈值　|　{CORE_DISCLAIMER}")
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

    def toggle_selected_rule(self) -> bool | None:
        """把选中规则的启用状态翻一下并落盘；返回翻转后的状态供测试断言。

        停用后监控周期会跳过它（`run_alert_cycle` 只看 enabled 的规则），但规则本身留着，
        不必为了静音一会儿就把它删掉。
        """

        index = self.rule_table.currentIndex()
        if not index.isValid():
            return None
        rules = list(self._settings.config.alerts)
        target = rules[index.row()]
        flipped = replace(target, enabled=not target.enabled)
        rules[index.row()] = flipped
        self._persist(rules)
        # 存盘后重建了表格，选中行会丢——把用户的选择放回去，方便连续操作。
        self.rule_table.setCurrentIndex(self.rule_model.index(index.row(), 0))
        return flipped.enabled

    def _persist(self, rules: list[AlertRule]) -> None:
        """经共享 Settings 读-改-写，只动 alerts；存盘失败如实提示，不假装存上了。"""
        if not self._settings.update(alerts=rules):
            self.status.setText(f"预警保存失败（配置文件不可写）　|　{CORE_DISCLAIMER}")
        self.set_rules(list(self._settings.config.alerts))

    def set_rules(self, rules: list[AlertRule]) -> None:
        """规则列表落进表格，并同步交给控制器——只存不给控制器，监控就永远不会触发。"""

        self._rules = list(rules)
        self._controller.set_rules(self._rules)
        self.rule_model.removeRows(0, self.rule_model.rowCount())
        for rule in self._rules:
            # 「启用」列就是字面的 是 / 否，与老版一致；行不着色（规则不是买卖结论）。
            cells = [rule_summary(rule), "是" if rule.enabled else "否"]
            self.rule_model.appendRow(make_row(cells, RULE_COLUMNS))
        self._update_stats()

    # ---------------- 监控与触发 ----------------

    def _on_monitor_toggled(self, checked: bool) -> None:
        self.monitor_button.setText("实时预警 开" if checked else "实时预警 关")
        if checked:
            # 控制器 start() 会清空自己的 fired 边沿状态，页面这份计数跟着归零，两边不错位。
            self._fired.clear()
            self.status.setText(f"实时预警已开启（每 60 秒检查一次）　|　{CORE_DISCLAIMER}")
            self._controller.start()
        else:
            self.status.setText(f"实时预警已关闭　|　{CORE_DISCLAIMER}")
            self._controller.stop()
        self._update_stats()

    def _on_triggered(self, rules: list[AlertRule]) -> None:
        for rule in rules:
            self._fired.add(rule_key(rule))
            self.triggered.appendPlainText(f"⚠ {rule_summary(rule)}")
        self._update_stats()

    def _update_stats(self) -> None:
        """四格指标：规则几条、其中几条启用、本次会话触发过几条、监控开着没有。"""

        self.stats.set_value("规则", str(len(self._rules)))
        self.stats.set_value("启用", str(sum(1 for rule in self._rules if rule.enabled)))
        self.stats.set_value("触发", str(len(self._fired)))
        self.stats.set_value("监控", "开" if self.monitor_button.isChecked() else "关")


def _normalized_code(text: str) -> str | None:
    """把用户输入规范化成 `AlertRule` 约定的形式（`sh600519`）；无效返回 None。

    老版同样是先 `normalize_symbol` 再入库。此前 Qt 版直接存原样输入，于是内存里是 `600000`、
    `store` 落盘时又规范成 `sh600000`——重启前后同一条规则看起来像两条。
    """

    try:
        return normalize_symbol(text.strip()).normalized
    except ValueError:
        return None


# 阈值解析用域里那份（`domain.input_validate.parse_alert_threshold`），不再在页面里另写。
# 曾经的本地副本少了 `math.isfinite` 检查：阈值填 `inf` 会被当成合法值建出一条规则，而
# `alerts.evaluate_rule` 又用 `finite_float` 把它读成 None——于是那条规则**静默地永不触发**，
# 用户既没被拒绝也等不到提醒（WI-032）。
