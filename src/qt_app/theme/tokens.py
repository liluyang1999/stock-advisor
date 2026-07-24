"""从机器权威真源 `loop/product/tokens.json` 加载设计 token（WI-005）。

Qt 侧**只读**这个文件，不另抄一份色值——tokens.json 是带 WCAG 对比度实测的权威色源，
任何在别处重复的颜色都会与它分叉。tokens.json 位于控制面（loop/），随包一起分发时由
`app_asset_path` 的同一套资源定位逻辑找到；开发期直接从仓库读。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class DesignTokens:
    font_families: list[str]
    font_points: dict[str, float]
    spacing_dip: list[int]
    control_min_height_dip: int
    primary_control_height_dip: int
    button_min_width_dip: int
    table_row_height_dip: int
    border_radius_dip: int
    content_max_width_dip: int
    window_minimum_dip: list[int]
    colors: dict[str, str]
    state_colors: dict[str, str]
    surfaces: dict[str, str]

    def colour(self, name: str) -> str:
        """按名取色，跨 colors/state_colors/surfaces 三组查找。

        画布类部件（K 线、因子条、光谱条）要按语义名取色，但不该关心某个色住在哪一组——
        分组是给 QSS 生成用的，不是给调用方记的。取不到就抛 KeyError，不静默回退成某个
        看起来还行的颜色（那会让配错的色悄悄上线）。
        """

        for group in (self.colors, self.state_colors, self.surfaces):
            if name in group:
                return group[name]
        raise KeyError(f"tokens.json 中没有名为 {name!r} 的颜色")


@lru_cache(maxsize=8)
def load_tokens(path: Path | None = None) -> DesignTokens:
    """加载并缓存设计 token。

    tokens.json 在进程生命周期内不变（打包后随包只读，开发期也不会边跑边改），所以按路径缓存：
    `make_row` 每行调一次、图表/空态提示每次 resize 调一次——不缓存就等于把 tokens.json 逐行、
    逐帧重新解析一遍。`DesignTokens` 是 frozen dataclass，缓存同一实例安全。maxsize=8 覆盖默认
    路径外加测试可能传入的少量临时路径。
    """

    from ui import assets

    raw = json.loads((path or assets.tokens_path()).read_text(encoding="utf-8"))
    return DesignTokens(
        font_families=list(raw["font_families"]),
        font_points=dict(raw["font_points"]),
        spacing_dip=list(raw["spacing_dip"]),
        control_min_height_dip=int(raw["control_min_height_dip"]),
        primary_control_height_dip=int(raw["primary_control_height_dip"]),
        button_min_width_dip=int(raw["button_min_width_dip"]),
        table_row_height_dip=int(raw["table_row_height_dip"]),
        border_radius_dip=int(raw["border_radius_dip"]),
        content_max_width_dip=int(raw["content_max_width_dip"]),
        window_minimum_dip=list(raw["window_minimum_dip"]),
        colors=dict(raw["colors"]),
        state_colors=dict(raw["state_colors"]),
        surfaces=dict(raw["surfaces"]),
    )
