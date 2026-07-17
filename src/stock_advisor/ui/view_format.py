"""行/表/剪贴板格式化与行/详情标签配色——纯函数。"""

from __future__ import annotations

import csv
import io
import re

from ..domain.formatting import (
    _finite_float,
    _fmt,
    _fmt_amount,
    _fmt_decimal,
    _fmt_percent_points,
    _fmt_percent_value,
    _fmt_plain_number,
    _fmt_score_value,
    _fmt_whole_percent,
    _looks_negative,
    _looks_positive,
    _looks_risky,
    _number_from_cell,
    _positive_finite_float,
    risk_level,
)
from ..domain.models import AnalysisResult, ComparisonRow, MarketSnapshot, Recommendation
from ..domain.numeric import positive_finite_int as _positive_finite_int
from ..domain.symbols import normalize_symbol
from .theme import (
    ACTION_ORDER,
    DETAIL_SECTION_TITLES,
    DISCLAIMER,
    FLAT_COLOR,
    NEG_COLOR,
    POS_COLOR,
    RISK_ORDER,
    TABLE_COLUMN_INDEX,
)


def watchlist_rows(watch: list, results_by_code: dict) -> list[tuple[str, str, str, str, str]]:
    """自选/持仓管理表行：代码、名称、成本、股数、浮动盈亏（该股已分析才算盈亏）。"""
    rows: list[tuple[str, str, str, str, str]] = []
    for item in watch:
        result = results_by_code.get(item.code)
        name = result.name if result is not None else "—"
        display = normalize_symbol(item.code).display
        cost = _positive_finite_float(item.cost)
        shares = _positive_finite_int(item.shares)
        last = _finite_float(result.last) if result is not None else None
        cost_text = f"{cost:.2f}" if cost is not None else "—"
        shares_text = str(shares) if shares is not None else "—"
        if cost is not None and result is not None and last is not None:
            pl_text = f"{(last - cost) / cost * 100:+.2f}%"
            if shares is not None:
                pl_text += f"（{(last - cost) * shares:+.0f}元）"
        elif cost is not None:
            pl_text = "未分析"
        else:
            pl_text = "—"
        rows.append((display, name, cost_text, shares_text, pl_text))
    return rows


def format_comparison_row(row: ComparisonRow) -> tuple[str, ...]:
    """横向对比表的一行（与列顺序一致）。"""
    cost = _positive_finite_float(row.cost)
    cost_text = f"{cost:.2f}" if cost is not None else "—"
    pl_pct = _finite_float(row.pl_pct)
    if pl_pct is None:
        pl_text = "—"
    else:
        pl_text = f"{pl_pct:+.2f}%"
        pl_amount = _finite_float(row.pl_amount)
        if pl_amount is not None:
            pl_text += f"（{pl_amount:+.0f}）"
    return (
        row.code,
        row.name,
        _fmt_decimal(row.last),
        _fmt_percent_points(row.change_pct, signed=True),
        _fmt_score_value(row.score, signed=True),
        _fmt_whole_percent(row.confidence),
        row.risk,
        _fmt_whole_percent(row.position),
        cost_text,
        pl_text,
        row.level_hint,
    )


def snapshot_display(snapshot: MarketSnapshot) -> str:
    if snapshot.market_id == "1":
        prefix = "SH"
    elif snapshot.code.startswith(("92", "8", "4")):
        prefix = "BJ"
    else:
        prefix = "SZ"
    return f"{prefix}.{snapshot.code}"


def format_recommendation_row(rec: Recommendation) -> tuple[str, str, str, str, str, str, str, str]:
    if rec.result is not None:
        return format_result_row(rec.result)
    snapshot = rec.snapshot
    if rec.error:
        label, risk = "深度失败", "高"
    else:
        label, risk = "快照", "—"
    return (
        snapshot_display(snapshot),
        snapshot.name,
        label,
        "—",
        "—",
        _fmt_decimal(snapshot.price),
        _fmt_percent_points(snapshot.change_pct, signed=True),
        risk,
    )


def build_snapshot_summary(rec: Recommendation) -> str:
    snapshot = rec.snapshot
    return (
        f"第{rec.rank}名 {snapshot_display(snapshot)} {snapshot.name}  "
        f"现价 {_fmt_decimal(snapshot.price)}  涨跌 {_fmt_percent_points(snapshot.change_pct, signed=True)}  {rec.board}"
    )


def build_snapshot_detail(rec: Recommendation) -> str:
    snapshot = rec.snapshot
    lines = [
        f"{snapshot_display(snapshot)} {snapshot.name}",
        "",
        "核心结论",
        f"- 选股入围：第 {rec.rank} 名（{rec.board}），入选评分 {_fmt_plain_number(rec.screen_score)}",
        f"- 最新价：{_fmt_decimal(snapshot.price)}    涨跌幅：{_fmt_percent_points(snapshot.change_pct, signed=True)}",
    ]
    if rec.error:
        lines.append(f"- 深度分析未完成：{rec.error}")
    lines.extend(
        [
            "",
            "快照特征",
            f"- 换手率：{_fmt_percent_value(snapshot.turnover_rate)}    量比：{_fmt(snapshot.volume_ratio)}    振幅：{_fmt_percent_value(snapshot.amplitude)}",
            f"- 市盈率：{_fmt(snapshot.pe_ttm)}    市净率：{_fmt(snapshot.pb)}",
            f"- 成交额：{_fmt_amount(snapshot.amount)}    总市值：{_fmt_amount(snapshot.total_cap)}",
            f"- 60日涨幅：{_fmt_percent_value(snapshot.change_60d)}    年初至今：{_fmt_percent_value(snapshot.change_ytd)}",
            "",
            "需要注意",
            (
                "- 深度分析失败，仅展示快照信息，请稍后重试。"
                if rec.error
                else "- 这是快照排序结果，未做逐项深度分析；如需买/持/卖判断请勾选“深度分析”重新选股。"
            ),
            DISCLAIMER,
        ]
    )
    return "\n".join(lines)


def format_result_row(result: AnalysisResult) -> tuple[str, str, str, str, str, str, str, str]:
    return (
        result.symbol.display,
        result.name,
        result.action_label,
        f"{_fmt_score_value(result.score)} 分",
        _fmt_whole_percent(result.confidence),
        _fmt_decimal(result.last),
        _fmt_percent_points(result.change_pct, signed=True),
        risk_level(result),
    )


def table_sort_key(column: str, row: tuple[str, ...] | list[str]) -> float | str:
    value = row[TABLE_COLUMN_INDEX.get(column, 0)] if row else ""
    if column == "score":
        return _number_from_cell(value, remove="分")
    if column == "confidence":
        return _number_from_cell(value, remove="%")
    if column in {"last", "change"}:
        return _number_from_cell(value, remove="%")
    if column == "risk":
        return RISK_ORDER.get(str(value), -1.0)
    if column == "action":
        return ACTION_ORDER.get(str(value), 99.0)
    return str(value)


def result_row_tags(result: AnalysisResult) -> tuple[str, ...]:
    risk_tag = {"低": "risk_low", "中": "risk_medium", "高": "risk_high"}.get(
        risk_level(result), "risk_medium"
    )
    return (risk_tag, f"action_{result.action.lower()}")


# Excel/WPS 把以这些字符开头的单元格当公式求值，`=cmd|' /C calc'!A0` 这类 DDE 载荷可执行
# 外部命令（REQ-032）。导出内容含股票名称等来自远端接口的字段，故视为不可信。
# TAB/CR 未被 REQ-032 逐一点名，但属同一触发类，一并堵住。
_FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")


def neutralize_export_cell(value: object) -> str:
    """把单元格中和成表格软件不会求值的文本（REQ-032）。

    加前缀而非删改：`'` 是 Excel 的"按文本处理"标记，单元格里不显示，原文完整保留。
    注意这会把合法的 `+1.53%`/`-1.53%` 涨跌幅一并转为文本——REQ-032 按字面要求中和这四个
    引导符，此处不做"看起来像数字就放行"的豁免：那要靠正则判别数字，多一个正则就多一个
    可被绕过的洞，而本函数是安全控制，宁可让涨跌幅在 Excel 里变文本。
    """

    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_FORMULA_LEADS) else text


def _safe_row(cells: object) -> list[str]:
    return [neutralize_export_cell(cell) for cell in cells]  # type: ignore[union-attr]


def format_results_for_clipboard(results: list[AnalysisResult]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(
        [
            "代码",
            "名称",
            "建议",
            "分数",
            "置信度",
            "最新价",
            "涨跌幅",
            "风险等级",
            "建议仓位",
            "预测说明",
            "主要依据",
        ]
    )
    for result in results:
        row = list(format_result_row(result))
        writer.writerow(
            _safe_row(
                [
                    *row,
                    _fmt_whole_percent(result.suggested_position),
                    result.forecast_label,
                    "；".join(result.reasons[:3]),
                ]
            )
        )
    return output.getvalue().strip()


def format_results_as_csv(results: list[AnalysisResult]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "代码",
            "名称",
            "建议",
            "分数",
            "置信度",
            "最新价",
            "涨跌幅",
            "风险等级",
            "建议仓位",
            "预测说明",
            "主要依据",
            "风险提示",
        ]
    )
    for result in results:
        row = list(format_result_row(result))
        writer.writerow(
            _safe_row(
                [
                    *row,
                    _fmt_whole_percent(result.suggested_position),
                    result.forecast_label,
                    "；".join(result.reasons[:3]),
                    "；".join(result.risks[:3]),
                ]
            )
        )
    return "\ufeff" + output.getvalue()


def format_table_rows_for_clipboard(rows: list[tuple[str, ...]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(["代码", "名称", "建议", "分数", "把握", "最新价", "涨跌幅", "风险"])
    writer.writerows(_safe_row(row) for row in rows)
    return output.getvalue().strip()


def format_table_rows_as_csv(rows: list[tuple[str, ...]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["代码", "名称", "建议", "分数", "把握", "最新价", "涨跌幅", "风险"])
    writer.writerows(_safe_row(row) for row in rows)
    return "\ufeff" + output.getvalue()


# 因子行形如「- 名称：+5分，中性。…」，按分数正负严格着色，避免描述里的“回撤/注意”
# 等词把正分行误标成红色。
_FACTOR_SCORE_RE = re.compile(r"：\s*([+-]?\d+)\s*分[，,。.]")


def detail_line_tags(line: str, is_first: bool) -> tuple[str, ...]:
    """返回某一行详情文本应使用的样式标签。

    判断拆解里的因子行按分数正负着色：正分=红、负分=绿、零分=中性；其余项目沿用
    关键词启发式（“需要注意”里的真实风险仍标红）。
    """
    stripped = line.strip()
    if is_first and stripped:
        return ("headline",)
    if stripped in DETAIL_SECTION_TITLES:
        return ("section",)
    if stripped.startswith("- "):
        match = _FACTOR_SCORE_RE.search(stripped)
        if match is not None:
            score = int(match.group(1))
            if score > 0:
                return ("bullet", "positive")
            if score < 0:
                return ("bullet", "negative")
            return ("bullet",)
        if _looks_risky(stripped):
            return ("risk",)
        if _looks_positive(stripped):
            return ("bullet", "positive")
        if _looks_negative(stripped):
            return ("bullet", "negative")
        return ("bullet",)
    return ("muted",)


def _score_color(score: int | float) -> str:
    value = _finite_float(score) or 0.0
    if value > 0:
        return POS_COLOR
    if value < 0:
        return NEG_COLOR
    return "#64748b"


def _action_color(action: str) -> str:
    if action == "BUY":
        return POS_COLOR
    if action == "SELL":
        return NEG_COLOR
    return FLAT_COLOR
