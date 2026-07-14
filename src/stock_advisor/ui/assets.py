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
