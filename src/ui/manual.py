from __future__ import annotations

import json
from html import escape

from domain.presets import PRESETS
from domain.screener import OBJECTIVE_LABELS
from version import __version__

from .assets import tokens_path
from .theme import DISCLAIMER
from .view_text import build_help_sections, build_strategy_sections


def _manual_font_stack() -> str:
    """说明书正文的 CSS 字体栈，取自 `tokens.json` 的 `font_families`（与 Qt QSS/字体契约同一真源）。

    HTML 说明书不另抄一份字体名，否则会像 WI-005 那样与应用分叉。TEST-FONT-002 要求说明书正文
    字体为微软雅黑、且无 UI 体或等宽体例外——只要 tokens 的 `font_families` 保持「Microsoft
    YaHei」，此处生成的字体栈就自动满足；追加一个通用 `sans-serif` 作最终兜底。
    """

    families = json.loads(tokens_path().read_text(encoding="utf-8"))["font_families"]
    return ",".join(f"'{name}'" for name in families) + ",sans-serif"


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
        "<p>股市锦囊围绕两种核心能力组织成五个页面（顶部页签切换）：</p>"
        "<ul>"
        "<li><strong>个股分析</strong>：输入一个或多个股票代码，得到当日方向、理由、风险与保守投入参考；"
        "点击结果行可展开摘要、因子拆解、K 线与整篇解释。</li>"
        "<li><strong>全市场选股</strong>：选择策略预设、微调关键参数，从当前全市场实时行情中自动挑选符合特征的股票；"
        "「深度分析」开关打开时，对入选股继续给出与个股分析一致的买/持/卖判断。</li>"
        "<li><strong>自选 / 持仓</strong>：维护关注列表与持仓成本，结合已分析行情计算浮动盈亏，并做横向对比。</li>"
        "<li><strong>条件预警</strong>：为股票设置价格 / 涨跌幅 / 综合分的越线提醒。</li>"
        "<li><strong>个股资金流</strong>：按需查询主力净流入（今日与近 5 日）。</li>"
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
        "<p>每个预设都内置一组证券特征范围，可在界面上微调几个关键参数（今日涨幅下限、量比下限、成交额下限、推荐数量）。</p>"
        f"<ul>{preset_items}</ul>"
    )

    characteristic_items = "".join(
        f"<li><strong>{escape(name)}</strong>：{escape(desc)}</li>"
        for name, desc in CHARACTERISTICS
    )
    sections.append(
        "<h2>可筛选的证券特征</h2>"
        "<p>筛选特征来自本次行情快照，缺失字段和取数失败会影响可用结果；资金流是独立查询，ROE 尚未纳入筛选。</p>"
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
        "<h2>自选 / 持仓与横向对比</h2>"
        "<ul>"
        "<li><strong>加入自选</strong>：在个股分析页点「加入自选」把当前结果存起来；也可在自选 / 持仓页下方直接输入代码添加。"
        "填上<strong>持仓成本</strong>与股数并点「保存持仓」，该股分析后即显示<strong>浮动盈亏</strong>（百分比与金额）。"
        "自选、本金、决策强度、选股预设都会自动保存，下次打开自动恢复。</li>"
        "<li><strong>横向对比</strong>：在自选 / 持仓页选中标的后点「载入分析」，完成深度分析的股票会进入下方对比表，"
        "并排比较综合分、把握、风险、建议仓位、持仓盈亏与「各档买卖翻转点」提示；「刷新对比」按当前档位重算。</li>"
        "<li><strong>K 线十字光标</strong>：把鼠标放到 K 线图上，会显示十字线和当根的开/高/低/收与涨跌幅；"
        "图上叠加 MA5 / MA10 / MA20 三条均线，右侧为价格刻度，底部标注起止日期。</li>"
        "</ul>"
    )

    sections.append(
        "<h2>条件预警</h2>"
        "<p>在条件预警页下方选好<strong>代码、字段（价格 / 涨跌幅 / 综合分）、条件（≥ 或 ≤）与阈值</strong>，"
        "点「添加」即成一条规则；「启用 / 停用」「删除选中」管理已有规则。开启「实时预警」后，程序开着时每 60 秒"
        "检查一次已启用规则，越线即个股分析页警示横幅 + 状态栏 + 提示音三路提醒"
        "（条件由不满足变为满足才提醒一次，回落后可再次触发）。</p>"
    )

    sections.append(
        "<h2>个股资金流</h2>"
        "<p>在个股资金流页输入代码点「查询资金流」，查看主力净流入（今日与近 5 日累计，红=净流入、绿=净流出）；"
        "也可在个股分析页选中一行后走「更多 → 查看当前标的资金流」直接跳转查询。"
        "该数据源偶发不稳定，取不到时页面会以警示横幅如实降级并提示稍后重试，不影响其它功能。</p>"
    )

    sections.append(
        "<h2>表格通用操作</h2>"
        "<ul>"
        "<li><strong>点表头排序</strong>：每张结果表都支持点击表头按该列排序；分数、把握、涨跌幅、风险这类"
        "「越大越该先看」的列，首次点击即从高到低。</li>"
        "<li><strong>空表指引</strong>：表格为空时，中央会写明下一步操作入口。</li>"
        "<li><strong>失败行</strong>：分析失败的行在「风险」列给出原因；悬停该行任意位置可读完整原因，"
        "选中该行时摘要区也会显示全文。</li>"
        "</ul>"
    )

    for title, body in build_help_sections():
        sections.append(_render_section(title, body))

    sections.append(
        "<h2>交付文件与安全核验</h2>"
        "<p>当前构建未经代码签名。请保留整个应用目录，不要只复制 EXE；配套文件包括本说明书、"
        "RELEASE_MANIFEST.json、SBOM.json、THIRD_PARTY_NOTICES.md 和 licenses 目录。</p>"
        "<p>维护者可用 scripts/make_release_manifest.py --verify 核对完整交付文件。"
        "SHA-256 用于发现文件变化，不能单独证明发布者身份；清单也应来自可信来源。"
        "遇到系统安全提示，请先核实来源，不要关闭系统防护。</p>"
        "<p>离线自检不证明真实行情接口此刻可用；测试通过也不代表已经完成正式发布审批。</p>"
    )
    for title, body in build_strategy_sections():
        sections.append(_render_section(title, body))

    body_html = "\n".join(sections)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>股市锦囊 使用说明</title>\n"
        "<style>\n"
        f"body{{font-family:{_manual_font_stack()};line-height:1.7;"
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
        # 版本号取自唯一真源（__version__）。说明书随构建生成并随交付物分发，
        # 是用户手边唯一能对出"我拿到的是哪一版"的东西——出问题时这一行决定了能不能复现。
        f'<p class="subtitle">版本 {escape(__version__)}</p>\n'
        f"{body_html}\n"
        f'<div class="disclaimer">{escape(DISCLAIMER)}</div>\n'
        "</body>\n</html>\n"
    )
