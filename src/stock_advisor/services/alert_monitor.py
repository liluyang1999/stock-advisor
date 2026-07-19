"""预警监控编排（REQ-006/010 / WI-016）。

框架无关：刷新各规则涉及的 code 的分析结果，跑 `domain.alerts.check_rules`（边沿触发纯函数），
推进 fired 状态。**单只刷新失败被隔离**——某 code 取不到就跳过该 code，其余规则照常评估，
一条规则/一只失败绝不停掉整轮监控（REQ-010）。QTimer 驱动与 generation 丢弃迟到结果由 Qt 层负责。
"""

from __future__ import annotations

from ..domain.alerts import check_rules
from ..domain.models import STANDARD_LEVEL, AlertRule
from .workflow import MarketDataProvider, analyze_symbol


def run_alert_cycle(
    rules: list[AlertRule],
    provider: MarketDataProvider,
    fired: set,
    *,
    level: int = STANDARD_LEVEL,
) -> tuple[list[AlertRule], set]:
    """跑一轮监控：刷新启用规则涉及的 code，边沿触发判定，返回（本轮新触发规则，更新后 fired）。

    fired 是调用方持有的边沿状态（跨轮传递）；本函数不持久化任何状态。
    """

    codes = {rule.code for rule in rules if rule.enabled}
    results_by_code: dict[str, object] = {}
    for code in codes:
        from ..domain.symbols import normalize_symbol

        try:
            symbol = normalize_symbol(code)
            outcome = analyze_symbol(symbol, provider, level)
        except Exception:  # noqa: BLE001 - 单只刷新失败被隔离，不停整轮监控（REQ-010）
            continue
        if outcome.ok and outcome.result is not None:
            results_by_code[code] = outcome.result
        # 失败/无结果的 code 不进 results_by_code；check_rules 缺该 code 结果即跳过、不改状态。

    return check_rules(rules, results_by_code, fired)
