"""字体契约：请求 token 真源里的字体，并如实报告实际拿到的是什么（REQ-016 / REQ-033）。

要点：`QFont("随便什么名字")` **永远不会失败**——字体不存在时 Qt 会静默换一个最接近的，界面
照常渲染，只是字全错了。只有 `QFontInfo` 会说出实际解析到的字体族。REQ-033 明确禁止这种静默
替换，要求"可见失败或文档化回退"，因此本模块的职责是把"要的"和"实际得到的"一起交出去，让
外壳能把差异呈现给用户，而不是自己吞掉。

陷阱（实测）：即便字体族完全正确，`QFontInfo.exactMatch()` 仍常为 False（字号/字重与实际
可用字形不完全一致）。用它做判据会把正确的字体误报为缺失，所以判据是 `family()` 相等。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtGui

from ...ui import theme

# 文档化回退链（REQ-033）：雅黑家族内部先退，再退到 Qt 的通用无衬线。
# 顺序即优先级；`Microsoft YaHei UI` 是 token 真源 `theme.UI_FONT` 的当前取值。
FALLBACK_CHAIN: tuple[str, ...] = ("Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "sans-serif")

DEFAULT_POINT_SIZE = 10


@dataclass(frozen=True)
class ResolvedFont:
    """一次字体解析的完整结果——包含"没拿到"这个事实本身。"""

    font: QtGui.QFont
    requested_family: str
    actual_family: str
    is_exact: bool
    fallback_note: str | None
    """未拿到请求字体时的可呈现说明；拿到了则为 None。外壳据此决定如何可见地告知用户。"""


def resolve_ui_font(
    requested: str | None = None, point_size: int = DEFAULT_POINT_SIZE
) -> ResolvedFont:
    """解析界面字体，并把实际结果如实带出。

    `requested` 缺省取 `ui/theme.py::UI_FONT`——Qt 侧不另存一份字体名，否则 token 真源分叉。
    """

    family = requested if requested is not None else theme.UI_FONT
    font = QtGui.QFont(family, point_size)
    actual = QtGui.QFontInfo(font).family()
    if actual == family:
        return ResolvedFont(font, family, actual, True, None)

    note = (
        f"字体「{family}」在本机不可用，已回退为「{actual}」；"
        f"文档化回退链：{' → '.join(FALLBACK_CHAIN)}。界面文字外观将与设计稿不同。"
    )
    return ResolvedFont(font, family, actual, False, note)


def apply_app_font(
    app: QtGui.QGuiApplication, point_size: int = DEFAULT_POINT_SIZE
) -> ResolvedFont:
    """把界面字体设为应用级默认，使每个可见控件都继承它（REQ-016）。

    返回解析结果而非布尔值：调用方必须能拿到 `fallback_note` 并可见地呈现，这正是 REQ-033
    要求的"不静默"。
    """

    resolved = resolve_ui_font(point_size=point_size)
    app.setFont(resolved.font)
    return resolved
