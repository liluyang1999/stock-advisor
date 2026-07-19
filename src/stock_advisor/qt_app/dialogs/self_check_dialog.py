"""离线自检对话框（REQ-008 / REQ-031 / WI-018）。

跑一次 `services.self_check.run_self_check`——框架无关、离线、绝不外抛——把逐项通过/失败可视化。
与命令行 `--self-test` 共用同一份自检逻辑（`run_self_check`），一处实现两处调用，避免两份自检漂移。
自检全程用样例数据、不接受 provider（结构上不联网），耗时极短，故在打开时同步跑完即呈现。
"""

from __future__ import annotations

from html import escape

from PySide6 import QtWidgets

from ...domain.models import CORE_DISCLAIMER
from ...services.self_check import SelfCheckResult, run_self_check


def result_to_html(result: SelfCheckResult) -> str:
    """SelfCheckResult → 富文本：每项一行「✓/✗ 名称 — 明细」，通过项绿、失败项红。"""

    rows: list[str] = []
    for check in result.checks:
        mark = "✓" if check.passed else "✗"
        color = "#00742A" if check.passed else "#CC0000"  # tokens: down_green / up_red
        detail = f" — {escape(check.detail)}" if check.detail else ""
        rows.append(
            f'<p style="color:{color}">{mark} {escape(check.name)}'
            f'<span style="color:#122B3D">{detail}</span></p>'
        )
    return "\n".join(rows)


class SelfCheckDialog(QtWidgets.QDialog):
    """离线自检结果窗：摘要 + 逐项通过/失败 + 常驻免责声明。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("离线自检")
        self.resize(480, 520)

        # 离线、快、绝不外抛：在 GUI 线程同步跑完即可。结果留作字段供测试断言。
        self.result: SelfCheckResult = run_self_check()

        layout = QtWidgets.QVBoxLayout(self)

        self.summary = QtWidgets.QLabel(self.result.summary)
        layout.addWidget(self.summary)

        self.body = QtWidgets.QTextBrowser()
        self.body.setHtml(result_to_html(self.result))
        layout.addWidget(self.body)

        # REQ-031：结果窗常驻免责声明。
        self.disclaimer = QtWidgets.QLabel(CORE_DISCLAIMER)
        self.disclaimer.setWordWrap(True)
        layout.addWidget(self.disclaimer)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
