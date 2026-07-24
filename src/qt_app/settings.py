"""应用设置的单一持有者（REQ-009 / WI-030）。

为什么需要它，而不是每页各自 `load_config()` / `save_config()`：`AppConfig` 是一个整体，存盘是整份
覆写。若个股页持有一份副本存本金、自选页持有另一份副本存自选，后存的那份会用自己的陈旧字段把先存的
覆盖掉——用户改了自选、又改了本金，重启后发现丢了一个。这类缺陷不会报错，只会静默丢数据。

所以进程内只有一份 `AppConfig`，所有改动走 `update()` 做读-改-写，页面只声明"我改了哪个字段"。

存盘失败不抛异常（`store.save_config` 返回 False），由调用方决定怎么告诉用户——设置写不进磁盘不该
让界面崩掉，但也绝不能假装存上了。
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any

from services import store


class Settings:
    """进程内唯一的 AppConfig 持有者。非线程安全：只在 GUI 线程使用。

    **`path` 是必填的，没有"默认读用户真实配置"这条路。** 曾经它可选、缺省读 `%APPDATA%`，结果任何
    构造页面的测试都会读写用户的真实配置——实测把 `level` 写成了 5。默认值本身就是那个缺陷：它让
    "碰到真实用户数据"成为不写参数时的行为。现在生产用 `Settings.for_user()` 显式表态，测试传临时
    路径，两者都说得出自己在动哪个文件。
    """

    def __init__(self, path: Path, loader: Callable[..., Any] | None = None) -> None:
        self._path = path
        self._load = loader or store.load_config
        self._config = self._load(path)

    @classmethod
    def for_user(cls) -> Settings:
        """生产入口：读当前用户的 %APPDATA% 配置。只应由应用装配处调用。"""
        return cls(store.config_path())

    @property
    def config(self) -> store.AppConfig:
        return self._config

    def update(self, **fields: object) -> bool:
        """读-改-写：只替换指定字段，其余保持当前值。返回是否存盘成功。

        未知字段直接抛错而不是静默忽略——写错字段名却"看起来存上了"，比立刻失败难查得多。
        """
        known = {f.name for f in dataclasses.fields(store.AppConfig)}
        unknown = set(fields) - known
        if unknown:
            raise KeyError(f"AppConfig 没有这些字段：{sorted(unknown)}")
        self._config = dataclasses.replace(self._config, **fields)  # type: ignore[arg-type]
        return store.save_config(self._path, self._config)
