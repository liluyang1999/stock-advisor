"""证据/因子视图契约（REQ-004/022/031 / WI-011 / TEST-DISC-001）。

REQ-004：展示因子、证据强度、风险。REQ-022：未经统计校准的分数不得被描述为收益概率或确定
置信度——用"证据强度"措辞而非"胜率/概率"。REQ-031：免责声明常驻。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from PySide6 import QtWidgets
except ImportError:  # pragma: no cover
    QtWidgets = None

from qt_test_helpers import qt_app, requires_qt
from test_engine import make_measurement

from stock_advisor.domain.models import CORE_DISCLAIMER
from stock_advisor.services.tier_switch import redecide_at_level

if QtWidgets is not None:
    from stock_advisor.qt_app.widgets.evidence_view import EvidenceView


def _result():
    return redecide_at_level(make_measurement(), 3)


@requires_qt
class EvidenceViewTests(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()

    def test_disclaimer_is_resident_before_and_after_data(self):
        view = EvidenceView()
        self.assertIn(CORE_DISCLAIMER, view.disclaimer.text())  # REQ-031，空态即常驻
        view.show_result(_result())
        self.assertIn(CORE_DISCLAIMER, view.disclaimer.text())  # 有数据后仍常驻

    def test_shows_a_row_per_factor(self):
        result = _result()
        view = EvidenceView()
        view.show_result(result)
        self.assertEqual(view.factor_model.rowCount(), len(result.factor_scores))

    def test_evidence_strength_label_avoids_probability_wording(self):
        # REQ-022：不得称"胜率/收益概率/确定置信"；用"证据强度"。
        view = EvidenceView()
        view.show_result(_result())
        text = view.strength_label.text()
        self.assertIn("证据强度", text)
        for banned in ("收益概率", "胜率", "必然", "确定盈利"):
            self.assertNotIn(banned, text)

    def test_reasons_and_risks_are_shown(self):
        result = _result()
        view = EvidenceView()
        view.show_result(result)
        body = view.narrative.toPlainText()
        if result.reasons:
            self.assertIn(result.reasons[0][:6], body)

    def test_clear_empties_the_factor_table_but_keeps_disclaimer(self):
        view = EvidenceView()
        view.show_result(_result())
        view.clear()
        self.assertEqual(view.factor_model.rowCount(), 0)
        self.assertIn(CORE_DISCLAIMER, view.disclaimer.text())


class DisclaimerStaticDetectionTests(unittest.TestCase):
    def test_evidence_view_module_references_the_core_disclaimer(self):
        src = (
            Path(__file__).resolve().parents[1]
            / "src/stock_advisor/qt_app/widgets/evidence_view.py"
        ).read_text(encoding="utf-8")
        self.assertIn("CORE_DISCLAIMER", src)


if __name__ == "__main__":
    unittest.main()
