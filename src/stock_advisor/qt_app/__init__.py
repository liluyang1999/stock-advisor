"""PySide6 GUI（ADR-0001 的 Tkinter→Qt 迁移目标）。

分层同 ADR-0002/ADR-0007：本包只做呈现与编排，业务逻辑一律留在 `domain`/`data`/`services`。
`domain` 的 12 个核心模块被 `check_core_boundaries` 禁止导入 PySide6，边界由机器强制。

迁移期内本包与 `ui/`（Tkinter，仍是出货 GUI）并存；`ui/theme.py` 是两者共用的 token 单一真源。
"""
