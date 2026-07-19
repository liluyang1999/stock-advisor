"""资源路径解析:开发态用源码 assets 目录,PyInstaller 单文件态用 _MEIPASS 解包目录。仅依赖标准库。"""

from __future__ import annotations

import sys
from pathlib import Path

from .theme import ASSET_DIR


def app_asset_path(filename: str) -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "assets" / filename
    return ASSET_DIR / filename


# src/stock_advisor/ui/assets.py -> 上溯 3 层到仓库根。
_REPO_ROOT = Path(__file__).resolve().parents[3]


def tokens_path() -> Path:
    """设计 token 真源 `loop/product/tokens.json` 的单一定位。

    打包态随 `--add-data` 附在 assets/ 下，开发态从仓库控制面读。Qt 主题（QSS/字体契约）与
    HTML 说明书共用**这一个**解析，谁都不另抄一份路径或字体名，避免像 WI-005 那样各用各的
    字体来源而分叉。`assets` 是 ui 与 qt_app 都依赖的共同底座，故解析落在此处。
    """

    bundled = app_asset_path("tokens.json")
    if bundled.exists():
        return bundled
    return _REPO_ROOT / "loop" / "product" / "tokens.json"
