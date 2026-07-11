"""面向用户的文本构建与文案改写——纯函数。"""
from __future__ import annotations

from .formatting import (
    _finite_float, _safe_int,
    _fmt, _fmt_decimal, _fmt_percent, _fmt_percent_points, _fmt_percent_value,
    _fmt_plain_number, _fmt_rate_percent, _fmt_score_value, _fmt_whole_percent, _fmt_yi,
    _fmt_backtest_return, _fmt_backtest_excess, _flow_direction,
    risk_level,
)
from .models import (
    AnalysisResult,
    BacktestReport,
    FundFlow,
    PositionPlan,
    Recommendation,
    SpectrumCell,
)
from .policy import flip_hint, level_spec
from .symbols import parse_user_symbols
from .theme import DISCLAIMER, MAX_SYMBOLS


def level_summary(level: int) -> str:
    """当前决策强度档位的一句话摘要（用于滑杆旁的提示）。"""
    spec = level_spec(level)
    return (
        f"{spec.name}档 · 买入线 +{spec.t_buy} / 卖出线 {spec.t_sell} · "
        f"风险预算 {spec.risk_budget * 100:g}% · 仓位上限 {int(spec.position_cap * 100)}%"
    )


def build_position_plan_text(plan: PositionPlan, level_name: str) -> str:
    lines = [f"仓位 / 风控计算器（{level_name}档）"]
    if plan.shares <= 0:
        lines.append(f"- {plan.note or '本档不建议新建仓位。'}")
        if plan.stop_price > 0 and plan.stop_pct > 0:
            lines.append(f"- 参考止损价：{plan.stop_price:.2f}（-{plan.stop_pct:.1f}%）")
        return "\n".join(lines)
    lines.extend(
        [
            f"- 建议股数：{plan.shares} 股（{plan.lots} 手）    买入参考：{plan.entry:.2f}",
            f"- 止损价：{plan.stop_price:.2f}（-{plan.stop_pct:.1f}%）",
            f"- 止盈价：{plan.target_price:.2f}（+{plan.target_pct:.1f}%）    盈亏比：{plan.reward_risk:g} : 1",
            f"- 投入金额：约 {plan.cost:.0f} 元",
            f"- 单笔最大亏损：约 {plan.max_loss:.0f} 元（占本金 {plan.max_loss_pct * 100:.2f}%）",
        ]
    )
    if plan.note:
        lines.append(f"- {plan.note}")
    return "\n".join(lines)


def build_backtest_text(report: BacktestReport) -> str:
    if not report.ok:
        return f"可信度回测\n- {report.message}"
    lines = [f"可信度回测（{report.note}）"]
    buy = report.stats.get("BUY")
    sell = report.stats.get("SELL")
    if buy:
        lines.append(
            f"- 买入信号 {buy.count} 次，胜率 {_fmt_rate_percent(buy.win_rate)}，"
            f"平均{report.horizon}日收益 {_fmt_backtest_return(buy.avg_return)}"
        )
    if sell:
        lines.append(
            f"- 卖出信号 {sell.count} 次，事后下跌占比 {_fmt_rate_percent(sell.win_rate)}，"
            f"平均{report.horizon}日收益 {_fmt_backtest_return(sell.avg_return)}"
        )
    lines.append(f"- 买入持有基线：{_fmt_backtest_return(report.buy_hold_return)}")
    if buy:
        lines.append(f"- 买入信号相对基线超额：{_fmt_backtest_excess(buy.avg_return, report.buy_hold_return)}")
    lines.append("- 同股历史事后复盘，仅用当日及之前数据、计入简单成本；样本有限，不预示未来。")
    return "\n".join(lines)


def build_spectrum_text(cells: list[SpectrumCell]) -> str:
    label = {"BUY": "买入", "SELL": "卖出", "HOLD": "观望"}
    parts = []
    for cell in cells:
        mark = "●" if cell.is_current else ""
        parts.append(f"{cell.name}{mark}={label.get(cell.action, cell.action)}")
    return "决策强度光谱：" + "  ".join(parts) + "\n" + flip_hint(cells)


def build_fund_flow_text(flow: FundFlow, name: str = "") -> str:
    """主力资金流文本（净额以「亿」展示，正=净流入红向、负=净流出绿向）。"""
    today = _flow_direction(flow.today_main)
    cumulative = _flow_direction(flow.main_5d)
    lines = [
        f"主力资金流{('（' + name + '）') if name else ''}",
        f"- 今日主力净额：{_fmt_yi(flow.today_main)}（{today}）",
        f"- 近5日累计：{_fmt_yi(flow.main_5d)}（{cumulative}）",
    ]
    if flow.recent:
        days = "  ".join(f"{date[5:]} {_fmt_yi(value)}" for date, value in flow.recent[-5:])
        lines.append(f"- 近几日：{days}")
    lines.append("- 资金流数据源偶发不稳定，取不到时可稍后重试；仅供参考。")
    return "\n".join(lines)


def build_screener_overview(preset_name: str, total: int, matched: int, shown: int, failures: int = 0) -> str:
    failure_text = f"；深度失败 {failures} 只" if failures else ""
    return (
        f"选股概览（{preset_name}）：全市场扫描 {total} 只，符合条件 {matched} 只，"
        f"展示前 {shown} 只{failure_text}"
    )


def build_recommendation_header(rec: Recommendation) -> str:
    return f"选股入围：第 {rec.rank} 名 · {rec.board} · 入选评分 {_fmt_plain_number(rec.screen_score)}"


def build_visual_summary(result: AnalysisResult) -> str:
    return (
        f"今日建议：{result.action_label}（{_fmt_score_value(result.score, signed=True)}分）  "
        f"投入比例：{_fmt_whole_percent(result.suggested_position)}  "
        f"把握程度：{_fmt_whole_percent(result.confidence)}  "
        f"常见波动：{_fmt_percent_value(result.expected_move_pct)}  "
        f"风险：{risk_level(result)}"
    )


def build_detail_text(result: AnalysisResult) -> str:
    indicators = result.indicators
    lines = [
        f"{result.symbol.display} {result.name}",
        "",
        "核心结论",
        f"- 今日建议：{result.action_label}（综合分 {_fmt_score_value(result.score, signed=True)}）",
        f"- 投入比例：{_fmt_whole_percent(result.suggested_position)}    把握程度：{_fmt_whole_percent(result.confidence)}    风险：{risk_level(result)}",
        f"- 一句话说明：{_plain_text(result.forecast_label)}",
        f"- 最新价：{_fmt_decimal(result.last)}    涨跌幅：{_fmt_percent_points(result.change_pct, signed=True)}",
        "",
        "看懂结果",
        f"- 建议投入比例：{_fmt_whole_percent(result.suggested_position)}（越高代表越适合参与，越低代表越该谨慎）",
        f"- 把握程度：{_fmt_whole_percent(result.confidence)}（越高代表信号越一致）",
        f"- 常见上下波动：{_fmt_percent_value(result.expected_move_pct)}（短线价格可能来回波动的幅度）",
        f"- 近期支撑/压力：{_fmt(indicators.support)} / {_fmt(indicators.resistance)}（接近支撑要防跌破，接近压力要看能否放量突破）",
        f"- 近5天上涨天数占比：{_fmt_percent(indicators.five_day_win_rate)}",
        f"- 近20天最大回撤：{_fmt_percent_value(indicators.max_drawdown_20)}",
        "",
        "判断拆解",
    ]
    for factor in result.factor_scores:
        factor_score = _safe_int(factor.score)
        lines.append(
            f"- {_friendly_factor_name(factor.name)}：{factor_score:+d}分，{_friendly_verdict(factor.verdict)}。"
            f"{_plain_text(factor.detail)}"
        )
    lines.extend(["", "为什么这样判断"])
    lines.extend(f"- {_plain_text(reason)}" for reason in result.reasons)
    lines.extend(["", "需要注意"])
    lines.extend(f"- {_plain_text(risk)}" for risk in result.risks)
    return "\n".join(lines)


def summarize_results(results: list[AnalysisResult], failures: int = 0) -> str:
    buys = sum(1 for item in results if item.action == "BUY")
    sells = sum(1 for item in results if item.action == "SELL")
    holds = sum(1 for item in results if item.action == "HOLD")
    return f"完成 {len(results)} 只：买入 {buys} / 卖出 {sells} / 持有 {holds}；失败 {failures} 只"


def normalize_symbol_input_text(text: str, max_count: int = MAX_SYMBOLS) -> str:
    return ", ".join(symbol.display for symbol in parse_user_symbols(text, max_count=max_count))


def build_portfolio_overview(results: list[AnalysisResult], failures: int = 0) -> str:
    if not results and not failures:
        return "组合概览：暂无结果。输入代码后点击开始分析。"

    buys = [item for item in results if item.action == "BUY"]
    sells = [item for item in results if item.action == "SELL"]
    holds = [item for item in results if item.action == "HOLD"]
    high_risk = sum(1 for item in results if risk_level(item) == "高")
    confidences = [_finite_float(item.confidence) for item in results]
    valid_confidences = [value for value in confidences if value is not None]
    average_confidence = round(sum(valid_confidences) / len(valid_confidences)) if valid_confidences else 0
    focus = _focus_symbols(results)
    focus_text = f"；优先查看：{focus}" if focus else ""
    return (
        f"组合概览：完成 {len(results)} 只，买入 {len(buys)} / 持有 {len(holds)} / 卖出 {len(sells)}；"
        f"平均把握 {average_confidence}%；高风险 {high_risk} 只；失败 {failures} 只{focus_text}"
    )


def build_help_sections() -> list[tuple[str, str]]:
    return [
        (
            "怎么使用",
            "\n".join(
                [
                    "1. 在输入框里输入股票代码，例如 600519、000001、300750。多个代码可以用逗号、空格或换行分开。",
                    f"2. 单次最多分析 {MAX_SYMBOLS} 只股票。普通用户建议一次看 3 到 8 只，结果更容易比较。",
                    "3. 点击“开始分析”，结果会显示在表格里。点击任意一行，下方会出现图形和文字解释。",
                    "4. “复制结果”适合发给自己或朋友查看，“导出 CSV”适合以后保存记录。",
                ]
            ),
        ),
        (
            "怎么看结果",
            "\n".join(
                [
                    "先看建议，再看理由，最后看风险。",
                    "- 买入/加仓：表示当前走势、成交和风险综合看起来偏积极，但仍建议分批参与。",
                    "- 卖出/减仓：表示当前风险或走弱迹象更明显，先保护本金。",
                    "- 继续持有/观望：表示信号不够一致，等待方向更清楚。",
                ]
            ),
        ),
        (
            "几个重要数字",
            "\n".join(
                [
                    "- 投入比例：不是必须照做的仓位，只是给你一个保守参考。风险高时会自动压低。",
                    "- 把握程度：越高说明多个迹象越一致，越低说明分歧大。",
                    "- 常见波动：告诉你短线价格上下晃动可能比较大还是比较小。",
                    "- 风险等级：高风险不代表一定会跌，只代表更不适合重仓追买。",
                ]
            ),
        ),
        (
            "数据与快捷操作",
            "\n".join(
                [
                    "数据从哪里来：程序会优先获取主行情源的实时价格和日线数据。如果主行情源临时无响应，会自动切换备用行情；只要能拿到足够日线，就会按完整判断流程分析，不再只靠实时价格做保守判断。",
                    "- Ctrl+Enter 或 F5：在当前页开始分析（个股分析页）或开始选股（全市场选股页）。",
                    "- Ctrl+L：清空输入和结果。",
                    "- Ctrl+Shift+C：复制当前股票的解释文字。",
                    "- “整理代码”会自动去重并补上交易所前缀，适合从网页或表格复制后先统一格式。",
                ]
            ),
        ),
        (
            "图形与异常",
            "\n".join(
                [
                    "图形怎么看：绿色偏积极，红色偏谨慎，灰色代表暂时不明显。价格小图看最近走势是否顺滑；判断拆解看是哪些方面支持或拖累了结果。",
                    "遇到异常怎么办：如果某只股票显示失败，通常是代码错误、网络不稳定或所有行情源暂时无响应。可以稍后重试；一只失败不会影响其他股票。",
                ]
            ),
        ),
    ]


def build_manual_text() -> str:
    sections = [f"{title}\n{body}" for title, body in build_help_sections()]
    return "\n\n".join(sections) + "\n\n" + DISCLAIMER


def build_strategy_sections() -> list[tuple[str, str]]:
    return [
        (
            "总体思路",
            "\n".join(
                [
                    "当前策略采用透明的多因子评分，而不是只看一个指标或一句新闻。",
                    "系统会把趋势、成交、日内强弱、价格位置、波动和风险控制放在一起打分，再把总分转换为买入/加仓、继续持有/观望、卖出/减仓。",
                    "这种做法更适合作为短线辅助判断：它能把多个市场迹象放到同一张表里比较，但不能保证未来涨跌。",
                ]
            ),
        ),
        (
            "计算步骤",
            "\n".join(
                [
                    "1. 先拿实时行情和历史日线，确认最新价、涨跌幅、成交量、当日高低点，以及最近一段时间的收盘价。",
                    "2. 再计算短中期均价关系、近期上涨节奏、短线买卖力度、成交是否放大、当前价在日内区间的位置、价格是否接近上下沿、常态波动幅度等判断项。",
                    "3. 每个判断项给出正分、负分或中性分。多个积极迹象共振会提高分数；走势转弱、放量下跌、波动过大或跳空风险会扣分。",
                    "4. 总分达到偏积极阈值时给出买入/加仓，达到偏谨慎阈值时给出卖出/减仓，中间区域保持继续持有/观望。",
                ]
            ),
        ),
        (
            "风险控制",
            "\n".join(
                [
                    "策略不会只因为涨得快就追买。若短线过热、振幅过大、回撤较深或历史样本不足，会自动降低分数、把握程度和建议投入比例。",
                    "把握程度不是胜率承诺，而是表示数据是否足够、各类迹象是否一致、风险是否可控。",
                    "建议投入比例是保守参考，不是必须执行的仓位；风险越高，比例越低。",
                ]
            ),
        ),
        (
            "科学边界",
            "\n".join(
                [
                    "从数学逻辑看，多因子组合比单一指标更稳健，因为它降低了某一个指标失真的影响。",
                    "但证券市场受资金、政策、消息、流动性和情绪影响，没有任何公开技术指标能稳定给出确定答案。",
                    "因此本程序坚持可解释、可复核、带风险扣分的辅助决策定位。它适合帮助你筛查和复盘，不应替代公告核验、基本面判断和个人风控。",
                ]
            ),
        ),
    ]


def build_strategy_explanation_text() -> str:
    sections = [f"{title}\n{body}" for title, body in build_strategy_sections()]
    return "\n\n".join(sections)


def _focus_symbols(results: list[AnalysisResult]) -> str:
    buy_candidates = [item for item in results if item.action == "BUY" and risk_level(item) != "高"]
    candidates = buy_candidates or [item for item in results if item.action == "HOLD" and (_finite_float(item.score) or 0.0) > 0] or results
    ranked = sorted(
        candidates,
        key=lambda item: (_finite_float(item.score) or 0.0, _finite_float(item.confidence) or 0.0),
        reverse=True,
    )
    return "、".join(item.symbol.display for item in ranked[:3])


def _friendly_factor_name(name: str) -> str:
    mapping = {
        "均线结构": "中短线走势",
        "趋势质量": "最近走势节奏",
        "动量指标": "买卖力量",
        "量能确认": "成交配合",
        "日内位置": "当天表现",
        "布林位置": "价格位置",
        "支撑压力": "上下空间",
        "波动风险": "波动风险",
        "风控扣分": "额外风险",
    }
    return mapping.get(name, name)


def _friendly_verdict(verdict: str) -> str:
    mapping = {
        "偏多": "偏积极",
        "略偏多": "略积极",
        "偏空": "偏谨慎",
        "略偏空": "略谨慎",
        "强势": "表现较强",
        "弱势": "表现较弱",
        "偏弱": "略弱",
        "偏强": "略强",
        "过热": "涨得偏急",
        "破位": "位置偏弱",
        "健康偏强": "位置较好",
        "可控": "相对可控",
        "中高波动": "波动偏大",
        "高波动": "波动很大",
        "低量": "成交偏少",
        "样本不足": "数据不够",
        "无效": "暂不参考",
        "谨慎": "需要谨慎",
    }
    return mapping.get(verdict, verdict)


def _plain_text(text: str) -> str:
    replacements = {
        "模型": "系统",
        "置信度": "把握程度",
        "建议仓位": "建议投入比例",
        "仓位": "投入比例",
        "MACD柱线为正且快线强于信号线，动量确认偏多。": "短线买盘力量增强，走势得到确认。",
        "MACD柱线为负且快线弱于信号线，动量确认偏空。": "短线卖压更明显，走势偏弱。",
        "综合 RSI14 与 MACD 快慢线/柱线。": "综合观察短线涨跌力度。",
        "RSI14": "短线热度",
        "MACD": "短线力量",
        "ATR": "日常波动",
        "布林带": "价格区间",
        "布林": "价格区间",
        "均线": "平均价",
        "动量": "走势力度",
        "因子": "判断项",
        "信号": "迹象",
        "样本": "数据",
        "多空证据分歧": "上涨和下跌的迹象还不一致",
        "追高成本较敏感": "追着买容易买在偏高位置",
        "不构成投资建议": "不能替代你自己的判断",
        "技术": "",
    }
    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result
