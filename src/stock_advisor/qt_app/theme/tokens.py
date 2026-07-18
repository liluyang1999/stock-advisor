"""从机器权威真源 `loop/product/tokens.json` 加载设计 token（WI-005）。

Qt 侧**只读**这个文件，不另抄一份色值——tokens.json 是带 WCAG 对比度实测的权威色源，
任何在别处重复的颜色都会与它分叉。tokens.json 位于控制面（loop/），随包一起分发时由
`app_asset_path` 的同一套资源定位逻辑找到；开发期直接从仓库读。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# src/stock_advisor/qt_app/theme/tokens.py -> 上溯 5 层到仓库根，再进 loop/product。
# 打包场景下 tokens.json 作为数据文件随附，见 build_exe 的 --add-data（WI-006 收尾时接入）。
_REPO_TOKENS = Path(__file__).resolve().parents[4] / "loop" / "product" / "tokens.json"


@dataclass(frozen=True)
class DesignTokens:
    font_families: list[str]
    font_points: dict[str, float]
    spacing_dip: list[int]
    control_min_height_dip: int
    primary_control_height_dip: int
    table_row_height_dip: int
    border_radius_dip: int
    content_max_width_dip: int
    window_minimum_dip: list[int]
    colors: dict[str, str]
    state_colors: dict[str, str]


def _tokens_path() -> Path:
    from ...ui import assets

    bundled = assets.app_asset_path("tokens.json")
    if bundled is not None and bundled.exists():
        return bundled
    return _REPO_TOKENS


def load_tokens(path: Path | None = None) -> DesignTokens:
    raw = json.loads((path or _tokens_path()).read_text(encoding="utf-8"))
    return DesignTokens(
        font_families=list(raw["font_families"]),
        font_points=dict(raw["font_points"]),
        spacing_dip=list(raw["spacing_dip"]),
        control_min_height_dip=int(raw["control_min_height_dip"]),
        primary_control_height_dip=int(raw["primary_control_height_dip"]),
        table_row_height_dip=int(raw["table_row_height_dip"]),
        border_radius_dip=int(raw["border_radius_dip"]),
        content_max_width_dip=int(raw["content_max_width_dip"]),
        window_minimum_dip=list(raw["window_minimum_dip"]),
        colors=dict(raw["colors"]),
        state_colors=dict(raw["state_colors"]),
    )
