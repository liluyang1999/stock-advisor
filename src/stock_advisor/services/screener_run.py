"""全市场筛选的编排包装（REQ-002 / WI-013）。

`screen_and_recommend` 是编排核心；本模块提供一层薄包装 `run_screen`，把 UI 侧的"预设 key +
用户微调值"解析成有效 `FilterCriteria` 与 TopN，再调编排。这样 Qt 页与 Tk 页共用同一入口，
参数解析/校验/TopN 钳制（5–30，由 `apply_tunables` 的 TunableParam 边界保证）只在此一处。

框架无关：不依赖 PySide6，可离线确定性测试。取消沿用 `screen_and_recommend` 的 `is_set()` 协议
（`ports.ManualCancel` 同时提供 `is_set`/`is_cancelled`，故一个原语横跨批量与筛选）。
"""

from __future__ import annotations

from ..domain.models import STANDARD_LEVEL
from ..domain.presets import apply_tunables, get_preset
from .workflow import CancelToken, ScreeningProvider, ScreenReport, screen_and_recommend


def run_screen(
    provider: ScreeningProvider,
    preset_key: str,
    tunables: dict[str, float],
    *,
    deep: bool = True,
    cancel_token: CancelToken | None = None,
    level: int = STANDARD_LEVEL,
    progress_cb=None,
) -> ScreenReport:
    """按预设 + 微调值跑一次全市场筛选。

    未知预设 key 是输入错误（返回带 error 的 ScreenReport，不抛）；非法微调值由 `apply_tunables`
    忽略并回退预设默认（不崩溃）。
    """

    try:
        preset = get_preset(preset_key)
    except KeyError:
        return ScreenReport(
            total=0, matched=0, recommendations=[], error=f"未知筛选预设：{preset_key}"
        )

    criteria, top_n = apply_tunables(preset, tunables)
    return screen_and_recommend(
        provider,
        criteria,
        preset.objective,
        top_n=top_n,
        deep=deep,
        cancel_event=cancel_token,
        progress_cb=progress_cb,
        level=level,
    )
