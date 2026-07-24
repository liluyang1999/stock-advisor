"""生产 GUI 入口（REQ-011 / WI-023）：PySide6。

历史上本模块是 Tkinter 的 `StockAdvisorApp`（连同 `app_*.py` 一组 mixin）。WI-023 完成迁移后
Tk 生产层整体移除，本模块退化为一层**薄入口**：把 `run_gui()` 委托给 `qt_app.app` 的装配
（provider → 控制器 → 四个功能页 → 主窗）。

保留 `run_gui` 这个名字与签名，是为了让 `main.py` 与既有调用方无需改动——入口契约不变，
背后的框架换掉了。真正的装配逻辑见 `qt_app/app.py`，业务在 `services/`，线程分发在
`qt_app/controllers/`；本文件刻意不含任何业务或界面代码，也不再依赖 Tk。
"""

from __future__ import annotations


def run_gui() -> None:
    """启动 PySide6 桌面应用（唯一生产 GUI 入口）。阻塞直到用户关闭窗口。"""

    from qt_app.app import run_qt_gui

    run_qt_gui()
