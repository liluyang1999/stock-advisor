"""Qt 异步工作生命周期原语（WI-019）：世代守卫等，用于取消/迟到/销毁/重复启动收敛。"""

from __future__ import annotations

from .generation_guard import GenerationGuard

__all__ = ["GenerationGuard"]
