from __future__ import annotations

from html import escape

from .app import DISCLAIMER, build_help_sections, build_strategy_sections
from ..domain.presets import PRESETS
from ..domain.screener import OBJECTIVE_LABELS


CHARACTERISTICS: tuple[tuple[str, str], ...] = (
    ("板块", "沪市主板 / 深市主板 / 创业板 / 科创板 / 北交所，可多选限定选股范围。"),
    ("剔除 ST / 退市风险", "名称含 ST、*ST、退 的风险警示股可一键剔除。"),
    ("价格区间", "限定最新价范围，避开过低或过高价位。"),
    ("当日涨跌幅", "今日涨跌幅区间，区分强势、企稳或回调。"),
    ("振幅", "当日最高最低之间的波动幅度，衡量当日活跃与风险。"),
    ("换手率", "成交量占流通股比例，越高代表交投越活跃。"),
    ("量比", "当前成交相对近期平均的放大倍数，识别异动放量。"),
    ("涨速", "短时间内的价格变动速度。"),
    ("60 日涨幅", "近 60 个交易日的中期涨跌，衡量趋势强弱。"),
    ("年初至今涨幅", "今年以来的累计涨跌。"),
    ("成交额下限", "流动性门槛，过滤成交太小、买卖困难的股票。"),
    ("总市值 / 流通市值", "公司规模档位，区分大盘、中盘、小盘。"),
    ("市盈率 PE", "估值高低，可剔除亏损（负 PE）股票。"),
    ("市净率 PB", "价格相对每股净资产的高低。"),
)


def _render_section(title: str, body: str) -> str:
    parts = [f"<h2>{escape(title)}</h2>"]
    bullets: list[str] = []

    def flush() -> None:
        if bullets:
            items = "".join(f"<li>{escape(item)}</li>" for item in bullets)
            parts.append(f"<ul>{items}</ul>")
            bullets.clear()

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith("- "):
            bullets.append(stripped[2:])
        elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == ".":
            bullets.append(stripped)
        else:
            flush()
            parts.append(f"<p>{escape(stripped)}</p>")
    flush()
    return "\n".join(parts)


def build_manual_html() -> str:
    sections: list[str] = []

    intro = (
        "<p>股市锦囊提供两种使用方式：</p>"
        "<ul>"
        "<li><strong>个股分析</strong>：输入一个或多个股票代码，得到当日方向、理由、风险与保守投入参考。</li>"
        "<li><strong>全市场选股</strong>：选择策略预设、微调关键参数，从当前全市场实时行情中自动挑选符合特征的股票，"
        "并对入选股做与个股分析一致的深度判断。</li>"
        "</ul>"
    )
    sections.append(f"<h2>这是什么</h2>{intro}")

    preset_items = "".join(
        f"<li><strong>{escape(preset.name)}</strong>：{escape(preset.description)}"
        f"（排序：{escape(OBJECTIVE_LABELS.get(preset.objective, preset.objective))}）</li>"
        for preset in PRESETS
    )
    sections.append(
        "<h2>选股策略预设</h2>"
        "<p>每个预设都内置一组证券特征范围，可在界面上微调几个关键参数（如涨幅、量比、成交额、市值、推荐数量）。</p>"
        f"<ul>{preset_items}</ul>"
    )

    characteristic_items = "".join(
        f"<li><strong>{escape(name)}</strong>：{escape(desc)}</li>"
        for name, desc in CHARACTERISTICS
    )
    sections.append(
        "<h2>可筛选的证券特征</h2>"
        "<p>当前版本的特征均来自一次实时行情快照，稳定可靠；资金流向、ROE 等基本面特征列入后续版本。</p>"
        f"<ul>{characteristic_items}</ul>"
    )

    sections.append(
        "<h2>决策强度（稳健 ↔ 激进）</h2>"
        "<p>顶部有一排五档「决策强度」分段按钮：稳健 · 稳进 · 标准 · 积极 · 激进。它不改变对行情的客观测量，"
        "只调整决策策略——越激进越早出手、仓位越大、对风险越宽容；越稳健越要求强确认、仓位越小、更快减仓护本。"
        "点选档位，结论与仓位会即时重算，不重新联网。</p>"
        "<ul>"
        "<li><strong>决策强度光谱</strong>：同一只股票，五档分别会给出买入/观望/卖出，一眼看出它是「各档都买」还是「只有激进才买」。</li>"
        "<li><strong>仓位 / 风控计算器</strong>：填入可用本金，按风险预算加止损距离算出建议股数（按手取整）、止损价、止盈价、盈亏比与单笔最大亏损额。</li>"
        "<li><strong>可信度回测</strong>：用该股历史做事后复盘——只用当日及之前的数据生成信号，统计买入信号未来若干日的胜率与平均收益，"
        "并与买入持有基线对比。样本有限、计入简单成本、不预示未来。</li>"
        "</ul>"
        "<p>配色采用 A 股本土习惯：<strong>红=上涨/买入/积极，绿=下跌/卖出/谨慎</strong>。</p>"
    )

    sections.append(
        "<h2>工作台：自选 / 持仓 / 对比</h2>"
        "<ul>"
        "<li><strong>自选股 / 持仓</strong>：点「加入自选」把当前分析的股票存起来；在「自选股」窗里可填<strong>持仓成本</strong>与股数，"
        "该股分析后即显示<strong>浮动盈亏</strong>（百分比与金额）。自选、本金、决策强度、选股预设都会自动保存，下次打开自动恢复。</li>"
        "<li><strong>横向对比</strong>：点「横向对比」把已分析的股票放进一张表，比较综合分、把握、风险、建议仓位、持仓盈亏，"
        "以及每只股票「各档买卖翻转点」的提示。</li>"
        "<li><strong>K 线十字光标</strong>：把鼠标放到 K 线图上，会显示十字线和当根的开/高/低/收与涨跌幅。</li>"
        "<li><strong>条件预警</strong>：点「预警」给某股设规则（价格 / 涨跌幅 / 综合分，≥ 或 ≤ 阈值），开启「实时预警」后，"
        "程序开着时每 60 秒检查一次，越线即顶部横幅 + 提示音提醒（条件由不满足变为满足才提醒，回落后可再次触发）。</li>"
        "<li><strong>个股资金流</strong>：选中一只已分析的股票后点「资金流」，查询主力净流入（今日与近 5 日累计）。"
        "该数据源偶发不稳定，取不到时会提示稍后重试，不影响其它功能。</li>"
        "</ul>"
    )

    for title, body in build_help_sections():
        sections.append(_render_section(title, body))
    for title, body in build_strategy_sections():
        sections.append(_render_section(title, body))

    body_html = "\n".join(sections)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>股市锦囊 使用说明</title>\n"
        "<style>\n"
        "body{font-family:'Microsoft YaHei UI','Microsoft YaHei',sans-serif;line-height:1.7;"
        "color:#1f2937;max-width:880px;margin:0 auto;padding:32px 24px;background:#f7faff;}\n"
        "h1{color:#0b1f3a;font-size:28px;margin-bottom:4px;}\n"
        "h2{color:#123b6d;font-size:19px;margin-top:28px;border-left:4px solid #1f6feb;padding-left:10px;}\n"
        "p,li{font-size:15px;}\n"
        "ul{padding-left:22px;}\n"
        ".disclaimer{margin-top:28px;padding:14px 16px;background:#fff4f4;border:1px solid #f0c2c2;"
        "border-radius:8px;color:#b42318;font-size:14px;}\n"
        ".subtitle{color:#667a99;margin-top:0;}\n"
        "</style>\n</head>\n<body>\n"
        "<h1>股市锦囊 使用说明</h1>\n"
        '<p class="subtitle">个股分析 + 全市场实时选股推荐 · 五档决策强度 · 可解释的多因子辅助判断</p>\n'
        f"{body_html}\n"
        f'<div class="disclaimer">{escape(DISCLAIMER)}</div>\n'
        "</body>\n</html>\n"
    )
