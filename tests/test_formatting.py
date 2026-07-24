"""formatting.py 低层格式化 / 风险分级纯函数的行为锁定测试。

补齐 test_ui_polish.py / test_app_helpers.py 未覆盖的“有值”“空串/非数”“非有限”分支。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from domain.formatting import (
    _fmt_amount,
    _fmt_percent,
    _fmt_plain_number,
    _format_number,
    _number_from_cell,
    risk_level,
)
from domain.models import AnalysisResult, IndicatorSnapshot
from domain.symbols import normalize_symbol


def _result(confidence, change_pct, score, risks):
    # risk_level 只读 confidence/change_pct/score/risks；指标位可全 None。
    return AnalysisResult(
        symbol=normalize_symbol("600519"),
        name="测试",
        action="HOLD",
        action_label="观望",
        score=score,
        confidence=confidence,
        last=10.0,
        change_pct=change_pct,
        suggested_position=0,
        forecast_label="",
        expected_move_pct=None,
        indicators=IndicatorSnapshot(*([None] * 15)),
        risks=list(risks),
    )


class LowLevelFormatTests(unittest.TestCase):
    def test_fmt_plain_number_non_integer_uses_general_format(self):
        self.assertEqual(_fmt_plain_number(3.14), "3.14")

    def test_fmt_amount_below_ten_thousand_prints_plain_integer(self):
        self.assertEqual(_fmt_amount(5000), "5000")

    def test_format_number_returns_empty_string_for_non_finite(self):
        self.assertEqual(_format_number(float("nan")), "")
        self.assertEqual(_format_number(float("inf")), "")

    def test_number_from_cell_defaults_to_zero(self):
        self.assertEqual(_number_from_cell(""), 0.0)  # 空串
        self.assertEqual(_number_from_cell("%"), 0.0)  # 去掉%后为空串
        self.assertEqual(_number_from_cell("abc"), 0.0)  # 非数字

    def test_fmt_percent_scales_finite_ratio_else_missing(self):
        self.assertEqual(_fmt_percent(0.05), "5.0%")  # 有值：比率*100，一位小数
        self.assertEqual(_fmt_percent(float("inf")), "样本不足")  # 非有限 → 缺失占位


class RiskLevelTests(unittest.TestCase):
    """风险分级三档口径：低置信度/多风险/大涨跌 → 高；次一档 → 中；否则 → 低；缺失字段 → 高。"""

    def test_low_confidence_is_high_risk(self):
        self.assertEqual(risk_level(_result(40, 1.0, 30, [])), "高")

    def test_mid_band_confidence_is_medium_risk(self):
        # 置信度 60 落在 [50,68)：躲过“高”档，命中“中”档的 confidence<68。
        self.assertEqual(risk_level(_result(60, 1.0, 30, [])), "中")

    def test_strong_signal_high_confidence_is_low_risk(self):
        self.assertEqual(risk_level(_result(80, 1.0, 30, [])), "低")

    def test_non_finite_confidence_falls_back_to_high(self):
        self.assertEqual(risk_level(_result(float("nan"), 1.0, 30, [])), "高")


if __name__ == "__main__":
    unittest.main()
