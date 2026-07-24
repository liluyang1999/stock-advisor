"""离线自检的结构化封装（REQ-008 / WI-018）。

把原先散在 `main.py::_self_test` 里的离线自检提炼成**框架无关、返回结构化结果**的 `run_self_check`，
供命令行（`main.py --self-test`）与 Qt 自检对话框共用——一份逻辑、两处调用，避免两份自检漂移。

**不接受 provider、不联网**：全程用 `data.sample_data` 的样例数据走通引擎/决策/仓位/回测/持久化/
对比/预警/选股管线；任何异常被收敛进对应检查项，`run_self_check` 绝不外抛。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class CheckItem:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class SelfCheckResult:
    checks: list[CheckItem] = field(default_factory=list)
    summary: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)


def run_self_check() -> SelfCheckResult:
    """离线跑通全部核心管线，返回逐项结果。绝不联网、绝不外抛。"""

    checks = [
        _guard("个股分析", _check_analysis),
        _guard("决策强度切档", _check_tiers),
        _guard("仓位计划", _check_position_plan),
        _guard("历史回测", _check_backtest),
        _guard("配置持久化", _check_persistence),
        _guard("横向对比", _check_compare),
        _guard("条件预警", _check_alerts),
        _guard("全市场选股", _check_screener),
    ]
    passed_n = sum(1 for c in checks if c.passed)
    return SelfCheckResult(checks=checks, summary=f"离线自检：{passed_n}/{len(checks)} 项通过")


def _guard(name: str, fn) -> CheckItem:
    try:
        passed, detail = fn()
    except Exception as exc:  # noqa: BLE001 - 自检把失败收敛成结果项，不外抛
        return CheckItem(name, False, f"异常：{exc}")
    return CheckItem(name, bool(passed), detail)


# --- 各管线的离线检查（全部用样例数据，无 provider、无网络）---


def _check_analysis() -> tuple[bool, str]:
    from data.sample_data import make_sample_analysis
    from ui.view_text import build_detail_text

    result = make_sample_analysis()
    build_detail_text(result)  # 详情文本可生成
    return result.action in ("BUY", "SELL", "HOLD"), f"{result.symbol.display} {result.action}"


def _check_tiers() -> tuple[bool, str]:
    from data.sample_data import make_sample_measurement
    from domain.policy import decide

    m = make_sample_measurement()
    c, a = decide(m, 1), decide(m, 5)
    return bool(c.action and a.action), f"L1={c.action} L5={a.action}"


def _check_position_plan() -> tuple[bool, str]:
    from data.sample_data import make_sample_measurement
    from domain.policy import position_plan

    plan = position_plan(make_sample_measurement(), 3, Decimal("100000.00"))
    return plan.shares >= 0, f"{plan.shares} 股"


def _check_backtest() -> tuple[bool, str]:
    from data.sample_data import make_sample_history
    from domain.backtest import backtest_signals

    report = backtest_signals(make_sample_history(), level=3)
    return report.ok, report.note if report.ok else report.message


def _check_persistence() -> tuple[bool, str]:
    from domain.models import AlertRule, AppConfig, WatchItem
    from services.store import config_to_dict, parse_config

    cfg = parse_config(
        config_to_dict(
            AppConfig(
                watchlist=(WatchItem("sh600519", Decimal("20.00"), 100),),
                level=5,
                alerts=(AlertRule("sh600519", "price", ">=", 10.0),),
            )
        )
    )
    ok = cfg.level == 5 and len(cfg.watchlist) == 1 and len(cfg.alerts) == 1
    return ok, f"watchlist={len(cfg.watchlist)} alerts={len(cfg.alerts)}"


def _check_compare() -> tuple[bool, str]:
    from data.sample_data import make_sample_analysis, make_sample_measurement
    from domain.compare import build_comparison_rows

    rows = build_comparison_rows(
        [
            {
                "result": make_sample_analysis(),
                "measurement": make_sample_measurement(),
                "risk": "低",
                "cost": 20.0,
                "shares": 100,
            }
        ]
    )
    ok = bool(rows) and rows[0].pl_pct is not None
    return ok, f"{len(rows)} 行"


def _check_alerts() -> tuple[bool, str]:
    from data.sample_data import make_sample_analysis
    from domain.alerts import check_rules
    from domain.models import AlertRule

    result = make_sample_analysis()
    rule = AlertRule(result.symbol.normalized, "price", ">=", float(result.last) - 1.0)
    fired, _ = check_rules([rule], {result.symbol.normalized: result}, set())
    return bool(fired), f"触发 {len(fired)} 条"


def _check_screener() -> tuple[bool, str]:
    recommendations = screen_candidates()
    return bool(recommendations), f"{len(recommendations)} 只候选"


def screen_candidates() -> list:
    """离线跑一次样例全市场选股，返回推荐列表（供自检与命令行摘要共用）。"""

    from domain.models import MarketSnapshot
    from domain.presets import apply_tunables, default_values, get_preset
    from domain.screener import recommend

    snapshots = [
        MarketSnapshot(
            code=code,
            market_id="1",
            name=name,
            price=price,
            change_pct=change_pct,
            change=Decimal("0.30"),
            volume=200000,
            amount=3.0e8,
            amplitude=3.0,
            turnover_rate=4.0,
            pe_ttm=18.0,
            volume_ratio=1.6,
            total_cap=8.0e10,
            float_cap=6.0e10,
            speed=0.4,
            pb=2.5,
            change_60d=12.0,
            change_ytd=20.0,
        )
        for code, name, price, change_pct in (
            ("600000", "样例甲", Decimal("12.00"), 5.0),
            ("600001", "样例乙", Decimal("18.00"), 3.5),
            ("600002", "样例丙", Decimal("9.00"), 2.6),
        )
    ]
    preset = get_preset("momentum_strong")
    criteria, top_n = apply_tunables(preset, default_values(preset))
    return recommend(snapshots, criteria, preset.objective, top_n=top_n)


def self_check_cli_line() -> tuple[bool, str]:
    """返回 (ok, 单行摘要)。沿用既有 SELF_TEST_OK/SELF_TEST_FAIL 前缀，兼容 G-EXE 门禁。"""

    from data.sample_data import (
        make_sample_analysis,
        make_sample_history,
        make_sample_measurement,
    )
    from domain.backtest import backtest_signals
    from domain.policy import decide, position_plan

    recommendations = screen_candidates()
    if not recommendations:
        return False, "SELF_TEST_FAIL screener produced no candidates"

    result = make_sample_analysis()
    measurement = make_sample_measurement()
    conservative = decide(measurement, 1)
    aggressive = decide(measurement, 5)
    plan = position_plan(measurement, 3, Decimal("100000.00"))
    backtest = backtest_signals(make_sample_history(), level=3)
    full = run_self_check()
    line = (
        "SELF_TEST_OK "
        f"symbol={result.symbol.display} action={result.action} "
        f"score={result.score} confidence={result.confidence} "
        f"L1={conservative.action} L5={aggressive.action} "
        f"plan_shares={plan.shares} backtest_ok={backtest.ok} "
        f"self_check={full.ok} checks={sum(1 for c in full.checks if c.passed)}/{len(full.checks)} "
        f"screen_candidates={len(recommendations)} top={recommendations[0].snapshot.code}"
    )
    return full.ok, line
