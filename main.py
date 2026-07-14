from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Import must follow the sys.path bootstrap above.
from stock_advisor.ui.app import build_detail_text, make_sample_analysis, run_gui  # noqa: E402


def enable_dpi_awareness() -> None:
    """Ask Windows to render Tk at native DPI instead of bitmap-scaling the EXE."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
            return
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        pass


def _self_test() -> int:
    """离线自测：验证个股分析引擎、决策强度、仓位/回测与全市场选股管线，不触网。"""
    from stock_advisor.domain.backtest import backtest_signals
    from stock_advisor.domain.models import MarketSnapshot
    from stock_advisor.domain.policy import decide, position_plan
    from stock_advisor.domain.presets import apply_tunables, default_values, get_preset
    from stock_advisor.domain.screener import recommend
    from stock_advisor.ui.app import make_sample_history, make_sample_measurement

    result = make_sample_analysis()
    _ = build_detail_text(result)  # 确认详情文本可生成

    # 决策强度：同一客观测量在不同档位走通决策、仓位与回测
    measurement = make_sample_measurement()
    conservative = decide(measurement, 1)
    aggressive = decide(measurement, 5)
    plan = position_plan(measurement, 3, 100000.0)
    backtest = backtest_signals(make_sample_history(), level=3)

    # 二期 2A：持久化 + 横向对比 离线自检
    from stock_advisor.domain.alerts import check_rules
    from stock_advisor.domain.compare import build_comparison_rows
    from stock_advisor.domain.models import AlertRule, AppConfig, WatchItem
    from stock_advisor.services.store import config_to_dict, parse_config

    alert = AlertRule(result.symbol.normalized, "price", ">=", result.last - 1.0)
    cfg = parse_config(
        config_to_dict(
            AppConfig(
                watchlist=(WatchItem("sh600519", 20.0, 100),),
                level=5,
                alerts=(alert,),
            )
        )
    )
    compare_rows = build_comparison_rows(
        [{"result": result, "measurement": measurement, "risk": "低", "cost": 20.0, "shares": 100}]
    )
    fired, _ = check_rules([alert], {result.symbol.normalized: result}, set())
    config_ok = cfg.level == 5 and len(cfg.watchlist) == 1 and len(cfg.alerts) == 1
    compare_ok = bool(compare_rows) and compare_rows[0].pl_pct is not None
    alert_ok = bool(fired)

    snapshots = [
        MarketSnapshot(
            code=code,
            market_id="1",
            name=name,
            price=price,
            change_pct=change_pct,
            change=0.3,
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
            ("600000", "样例甲", 12.0, 5.0),
            ("600001", "样例乙", 18.0, 3.5),
            ("600002", "样例丙", 9.0, 2.6),
        )
    ]
    preset = get_preset("momentum_strong")
    criteria, top_n = apply_tunables(preset, default_values(preset))
    recommendations = recommend(snapshots, criteria, preset.objective, top_n=top_n)
    if not recommendations:
        print("SELF_TEST_FAIL screener produced no candidates", file=sys.stderr)
        return 1

    message = (
        "SELF_TEST_OK "
        f"symbol={result.symbol.display} action={result.action} "
        f"score={result.score} confidence={result.confidence} "
        f"L1={conservative.action} L5={aggressive.action} "
        f"plan_shares={plan.shares} backtest_ok={backtest.ok} "
        f"config_ok={config_ok} compare_ok={compare_ok} alert_ok={alert_ok} "
        f"screen_candidates={len(recommendations)} top={recommendations[0].snapshot.code}"
    )
    if sys.stdout is not None:
        print(message)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in args:
        return _self_test()
    enable_dpi_awareness()
    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
