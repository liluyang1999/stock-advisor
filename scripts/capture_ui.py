"""开发工具：把装配好的应用逐页截图，供人工视觉评审。

**不是产品代码**：不进 EXE（`build_exe.py` 只收 `src/`）、不进门禁（真实评审要真实字体，
而 CI 跑 offscreen）。它用生产的 `build_app` 装配整窗，喂一份自带的确定性假数据，再把每一页
`grab()` 成 PNG——改了 UI 想看效果时跑它，而不是靠脑补，也不必等打包。

    python scripts/capture_ui.py                         # 成功态五页 -> build/ui-review/
    python scripts/capture_ui.py --states success fail empty
    python scripts/capture_ui.py --out build/shots --size 1440x900

真实字体需要 Windows 平台插件（默认继承当前环境）；`QT_QPA_PLATFORM=offscreen` 也能跑，
只是字体回退成默认族——结构照样完整，适合让测试驱动它防腐。

自带的 `DemoProvider` 只依赖 `src/` 的产品类型，不 import `tests/`：截图工具与测试夹具各活各的，
谁也不该拖着谁。失败态由 `fail_codes` / `fund_flow_fails` 表达，让"单项失败不拖垮整批"和
"资金流可见降级"这两条真实路径能被看见。
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from domain.models import (  # noqa: E402
    DailyBar,
    FundFlow,
    MarketSnapshot,
    Quote,
    StockSymbol,
)

_DEMO_CODES = ("600519", "000001", "601318")


class DemoProvider:
    """确定性假数据源，满足四个 controller 用到的 provider 契约。

    走势是"两段涨一段回调 + 定值扰动"的伪随机游走（不依赖 random，截图可复现），让 K 线看得出
    蜡烛、均线与量柱的真实形态，而不是一条直线。`fail_codes` 里的代码在取行情时抛异常，用来展示
    个股批的失败行；`fund_flow_fails` 让资金流查询整体失败，展示可见降级。
    """

    def __init__(
        self, fail_codes: frozenset[str] = frozenset(), fund_flow_fails: bool = False
    ) -> None:
        self._fail_codes = {code.lstrip("shz.").upper() for code in fail_codes}
        self._fund_flow_fails = fund_flow_fails
        self.calls: list[str] = []

    def _should_fail(self, symbol: StockSymbol) -> bool:
        digits = "".join(ch for ch in symbol.normalized if ch.isdigit())
        return any(digits.endswith(code) for code in self._fail_codes)

    def fetch_quote(self, symbol: StockSymbol) -> Quote:
        self.calls.append(symbol.normalized)
        if self._should_fail(symbol):
            raise ValueError(f"{symbol.normalized} 行情不可用：所有源均超时")
        return Quote(
            symbol=symbol,
            name="演示标的",
            last=Decimal("31.20"),
            open=Decimal("30.80"),
            high=Decimal("31.60"),
            low=Decimal("30.50"),
            previous_close=Decimal("30.90"),
            volume=210000,
            amount=210000 * 31.2,
            turnover_rate=1.8,
            change_pct=0.97,
            timestamp="capture",
        )

    def fetch_history(self, symbol: StockSymbol, limit: int = 120) -> list[DailyBar]:
        del symbol
        bars: list[DailyBar] = []
        price = 30.0
        day = date(2026, 3, 10)
        for i in range(min(limit, 90)):
            drift = 0.12 if (i // 9) % 3 != 2 else -0.22
            wiggle = ((i * 7919) % 13 - 6) * 0.11
            open_p = price
            close_p = max(5.0, price + drift + wiggle * 0.4)
            high_p = max(open_p, close_p) + abs(wiggle) * 0.35 + 0.05
            low_p = min(open_p, close_p) - abs(wiggle) * 0.3 - 0.05
            volume = 150000 + (i * 104729) % 90000
            bars.append(
                DailyBar(
                    date=day.isoformat(),
                    open=Decimal(f"{open_p:.2f}"),
                    close=Decimal(f"{close_p:.2f}"),
                    high=Decimal(f"{high_p:.2f}"),
                    low=Decimal(f"{low_p:.2f}"),
                    volume=volume,
                    amount=float(volume) * price,
                    pct_change=(close_p - open_p) / open_p * 100,
                    turnover_rate=1.1,
                )
            )
            price = close_p
            day += timedelta(days=1)
        return bars

    def fetch_market_snapshot(
        self, page_size: int = 1000, max_pages: int = 12
    ) -> list[MarketSnapshot]:
        del page_size, max_pages
        rows: list[MarketSnapshot] = []
        for i in range(24):
            price = Decimal(f"{30 - i * 0.4:.2f}")
            rows.append(
                MarketSnapshot(
                    code=f"6000{20 - i:02d}",
                    market_id="1",
                    name="演示标的",
                    price=price,
                    change_pct=7.0 - i * 0.1,
                    change=Decimal("0.40"),
                    volume=210000 + i * 1000,
                    amount=float(price) * 210000,
                    amplitude=2.6,
                    turnover_rate=2.1 - i * 0.02,
                    pe_ttm=24.0,
                    volume_ratio=1.4,
                    total_cap=3.0e12,
                    float_cap=3.0e12,
                    speed=0.3,
                    pb=8.0,
                    change_60d=12.0,
                    change_ytd=18.0,
                )
            )
        return rows

    def fetch_fund_flow(self, symbol: StockSymbol, limit: int = 6) -> FundFlow:
        del limit
        if self._fund_flow_fails:
            raise ValueError("资金流暂不可用：所有源均不可用")
        recent = [(f"2026-07-{13 + i:02d}", (1.5 - i * 0.4) * 1e8) for i in range(5)]
        del symbol
        return FundFlow(today_main=1.5e8, main_5d=3.2e8, recent=recent)


def _wait(signal: object, timeout_ms: int = 8000) -> None:
    """把一个 Qt 信号等到发出或超时——截图前要让异步 controller 真的把结果算完。"""

    from PySide6 import QtCore

    loop = QtCore.QEventLoop()
    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    signal.connect(loop.quit)  # type: ignore[attr-defined]
    timer.start(timeout_ms)
    loop.exec()


def _settings():
    """一份指向临时文件的 Settings：截图工具绝不读写用户真实 %APPDATA% 配置。"""

    from qt_app.settings import Settings

    tmp = tempfile.mkdtemp(prefix="capture-ui-")
    return Settings(Path(tmp) / "config.json")


def _drive(window: object, app: object, state: str) -> None:
    """按 state 把数据喂进各页：success 跑真实流程，fail 触发失败路径，empty 保持空态。"""

    if state == "empty":
        return

    individual = window.individual_page  # type: ignore[attr-defined]
    individual.input.setPlainText(" ".join(_DEMO_CODES))
    individual._on_analyze()
    _wait(window.analysis.batch_finished)  # type: ignore[attr-defined]
    app.processEvents()  # type: ignore[attr-defined]
    individual.table.selectRow(0)
    app.processEvents()  # type: ignore[attr-defined]

    screener = window.screener_page  # type: ignore[attr-defined]
    screener._on_screen()
    _wait(window.screener.screen_finished)  # type: ignore[attr-defined]

    fund_flow = window.fund_flow_page  # type: ignore[attr-defined]
    fund_flow.input.setText(_DEMO_CODES[0])
    fund_flow._on_query()
    _wait(window.fund_flow.fund_flow_ready)  # type: ignore[attr-defined]
    app.processEvents()  # type: ignore[attr-defined]


_PAGE_TABS = ("individual", "screener", "portfolio", "alerts", "fundflow")


def capture(states: list[str], out_dir: Path, size: tuple[int, int]) -> list[Path]:
    """为每个 state 装配一次主窗、逐页抓图，返回写出的文件路径。"""

    from qt_app.app import build_app

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for state in states:
        provider = DemoProvider(
            fail_codes=frozenset(_DEMO_CODES[1:]) if state == "fail" else frozenset(),
            fund_flow_fails=state == "fail",
        )
        app, window = build_app([], provider=provider, settings=_settings())
        window.resize(*size)
        _drive(window, app, state)
        for index, name in enumerate(_PAGE_TABS):
            window.tabs.setCurrentIndex(index)  # type: ignore[attr-defined]
            app.processEvents()
            path = out_dir / f"{state}-{index + 1}-{name}.png"
            window.grab().save(str(path))  # type: ignore[attr-defined]
            written.append(path)
        window.close()  # type: ignore[attr-defined]
    return written


def _parse_size(text: str) -> tuple[int, int]:
    width, _, height = text.lower().partition("x")
    return int(width), int(height)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="截取应用各页面截图供视觉评审")
    parser.add_argument(
        "--states",
        nargs="+",
        default=["success"],
        choices=["success", "fail", "empty"],
        help="要截取的状态（可多选）",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "build" / "ui-review",
        help="输出目录（默认 build/ui-review）",
    )
    parser.add_argument("--size", default="1280x800", help="窗口尺寸 WxH（默认 1280x800）")
    args = parser.parse_args(argv)

    paths = capture(args.states, args.out, _parse_size(args.size))
    for path in paths:
        print("saved", path)
    print(f"{len(paths)} 张截图 -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
