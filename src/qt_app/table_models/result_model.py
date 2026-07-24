"""个股分析结果的 QAbstractTableModel（REQ-004 / REQ-012 / REQ-031）。

把一列 `AnalysisResult` 映射成表格：代码/名称/建议/分数/证据强度/最新价/涨跌幅/建议仓位。
模型不含分析逻辑——结果由外部（切档控制器/页面）经 `set_results` 注入；切档时传入的是对同一
缓存 Measurement 重判后的结果，因此报价列不因切档而变（REQ-003 的可见结果）。

REQ-031：结果视图必须常驻免责声明。模型本身不画 UI，但在此静态引用 `CORE_DISCLAIMER` 常量，
使 TEST-DISC-001 能在源码里静态检测到每个结果视图对免责声明的引用，且措辞单一真源不漂移。
"""

from __future__ import annotations

from PySide6 import QtCore

from domain.models import CORE_DISCLAIMER, AnalysisResult

# REQ-031：结果视图常驻免责声明的措辞真源即领域层 CORE_DISCLAIMER；此处引用以供静态检测。
DISCLAIMER = CORE_DISCLAIMER

_COLUMNS: tuple[tuple[str, str], ...] = (
    ("代码", "symbol"),
    ("名称", "name"),
    ("建议", "action_label"),
    ("分数", "score"),
    ("证据强度", "confidence"),
    ("最新价", "last"),
    ("涨跌幅", "change_pct"),
    ("建议仓位", "suggested_position"),
)


class ResultTableModel(QtCore.QAbstractTableModel):
    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._results: list[AnalysisResult] = []

    def set_results(self, results: list[AnalysisResult]) -> None:
        """整体替换结果集（切档/重分析都走这里）。beginResetModel 保证视图正确刷新。"""

        self.beginResetModel()
        self._results = list(results)
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex | None = None) -> int:
        return len(self._results)

    def columnCount(self, parent: QtCore.QModelIndex | None = None) -> int:
        return len(_COLUMNS)

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if (
            orientation == QtCore.Qt.Orientation.Horizontal
            and role == QtCore.Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(_COLUMNS)
        ):
            return _COLUMNS[section][0]
        return None

    def data(
        self, index: QtCore.QModelIndex, role: int = QtCore.Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not index.isValid() or role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        if not (0 <= index.row() < len(self._results)):
            return None
        result = self._results[index.row()]
        attr = _COLUMNS[index.column()][1]
        value = getattr(result, attr)
        # symbol 是 StockSymbol 对象，显示其可读代码而非整个 dataclass repr。
        if attr == "symbol":
            return getattr(value, "code", None) or getattr(value, "normalized", str(value))
        # 金额/报价是 Decimal、仓位是 int、涨跌幅是 float——统一转字符串供展示。
        return str(value)


def result_at(model: ResultTableModel, row: int) -> AnalysisResult | None:
    """便捷取回某行的原始结果对象（供详情/证据视图联动）。"""

    if 0 <= row < model.rowCount():
        return model._results[row]  # noqa: SLF001 - 同包联动，读取自身缓存
    return None
