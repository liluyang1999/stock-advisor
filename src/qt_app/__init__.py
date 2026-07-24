"""PySide6 GUI —— 本产品唯一的出货界面（ADR-0001 的 Tkinter→Qt 迁移已由 WI-023 完成）。

分层同 ADR-0002/ADR-0007：本包只做呈现与编排，业务逻辑一律留在 `domain`/`data`/`services`。
`domain` 的 12 个核心模块被 `check_core_boundaries` 禁止导入 PySide6，边界由机器强制。

`ui/` 保留与界面框架无关的展示层（token 真源 `ui/theme.py`、格式化、说明书生成），本包从中取值；
`ui/app.py` 只是把 `run_gui` 委托到 `qt_app.app.run_qt_gui` 的薄入口。
"""
