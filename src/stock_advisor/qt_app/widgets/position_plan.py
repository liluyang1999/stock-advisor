"""仓位计划与回测工作台（REQ-004 / REQ-021 / WI-012）。

**纯展示**：把 `domain.policy.position_plan` 与 `domain.backtest.backtest_signals` 的既有输出如实
渲染，不自造任何数字、不改口径。回测的无未来泄漏由 domain 层与 WI-008 的 look-ahead 测试守住；
本部件只负责把结果（含成本、买入持有基线、样本量、caveats/免责说明）呈现给用户。

REQ-021：回测必须带"只用当日及之前数据、不预示未来"的说明——该说明由引擎放在 `BacktestReport.note`
里，此处原样透出，不改写。REQ-031：免责声明常驻。
"""

from __future__ import annotations

from PySide6 import QtWidgets

from ...domain.models import CORE_DISCLAIMER, BacktestReport, PositionPlan


class PositionPlanView(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel("仓位计划"))
        self.plan_label = QtWidgets.QLabel("—")
        self.plan_label.setWordWrap(True)
        layout.addWidget(self.plan_label)

        layout.addWidget(QtWidgets.QLabel("历史信号复盘"))
        self.backtest_label = QtWidgets.QLabel("—")
        self.backtest_label.setWordWrap(True)
        layout.addWidget(self.backtest_label)

        # REQ-031：结果视图常驻免责声明。
        self.disclaimer = QtWidgets.QLabel(CORE_DISCLAIMER)
        layout.addWidget(self.disclaimer)

    def show_plan(self, plan: PositionPlan) -> None:
        """渲染仓位计划。金额/报价是 Decimal（2 位），仓位/股数是 int，原样展示。"""

        self.plan_label.setText(
            f"建议仓位 {plan.fraction:.0%}｜{plan.shares} 股（{plan.lots} 手）\n"
            f"入场 {plan.entry}｜止损 {plan.stop_price}（-{plan.stop_pct:.1f}%）｜"
            f"目标 {plan.target_price}（+{plan.target_pct:.1f}%）\n"
            f"盈亏比 {plan.reward_risk}｜成本 {plan.cost}｜最大亏损 {plan.max_loss}"
            f"（{plan.max_loss_pct:.1f}%）\n{plan.note}"
        )

    def show_backtest(self, report: BacktestReport) -> None:
        """渲染回测复盘。样本不足/参数无效时引擎给的是 ok=False + message，如实显示，不编造。"""

        if not report.ok:
            self.backtest_label.setText(report.message)
            return
        lines = [
            f"样本 {report.sample_size} 次信号｜持有 {report.horizon} 日｜"
            f"买入持有基线 {report.buy_hold_return}%",
        ]
        for action, stat in report.stats.items():
            lines.append(
                f"{action}：{stat.count} 次，胜率 {stat.win_rate:.0%}，均收益 {stat.avg_return}%"
            )
        lines.append(report.note)  # REQ-021 的无未来泄漏 caveat，原样透出
        self.backtest_label.setText("\n".join(lines))

    def clear(self) -> None:
        self.plan_label.setText("—")
        self.backtest_label.setText("—")
        self.disclaimer.setText(CORE_DISCLAIMER)
