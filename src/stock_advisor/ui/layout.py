"""窗口居中、工作区归一、内容带几何——纯数学,零依赖,便于单测。"""
from __future__ import annotations


def compute_centered_geometry(outer_w: int, outer_h: int, win_w: int, win_h: int) -> tuple[int, int]:
    """返回让窗口在 outer 区域内居中的左上角坐标，四边留白由 (outer-win)/2 对称给出。"""
    x = max(0, (int(outer_w) - int(win_w)) // 2)
    y = max(0, (int(outer_h) - int(win_h)) // 2)
    return x, y


def compute_window_position(
    work_left: int, work_top: int, work_w: int, work_h: int, win_w: int, win_h: int
) -> tuple[int, int]:
    """在「屏幕工作区」（已排除任务栏）内居中：四周留白均匀，原点为工作区左上角。"""
    offset_x, offset_y = compute_centered_geometry(work_w, work_h, win_w, win_h)
    return int(work_left) + offset_x, int(work_top) + offset_y


def compute_child_window_geometry(
    parent_left: int,
    parent_top: int,
    parent_width: int,
    parent_height: int,
    work_left: int,
    work_top: int,
    work_width: int,
    work_height: int,
    requested_width: int,
    requested_height: int,
    margin: int = 0,
    frame_width: int = 0,
    frame_height: int = 0,
) -> tuple[int, int, int, int]:
    """让子窗口相对主窗口居中，并把完整外框夹在屏幕工作区内。

    首选尺寸大于工作区时只缩小客户区，不改变调用方按 DPI 计算首选尺寸的语义。返回
    ``(客户区宽, 客户区高, 外框绝对 x, 外框绝对 y)``。
    """
    work_width = max(1, int(work_width))
    work_height = max(1, int(work_height))
    frame_width = max(0, int(frame_width))
    frame_height = max(0, int(frame_height))
    requested_width = max(1, int(requested_width))
    requested_height = max(1, int(requested_height))
    requested_margin = max(0, int(margin))

    # 极小工作区下先保住至少 1px 客户区；横纵边距分别夹制，避免负的可用尺寸。
    margin_x = min(requested_margin, max(0, (work_width - frame_width - 1) // 2))
    margin_y = min(requested_margin, max(0, (work_height - frame_height - 1) // 2))
    available_width = max(1, work_width - 2 * margin_x - frame_width)
    available_height = max(1, work_height - 2 * margin_y - frame_height)
    width = min(requested_width, available_width)
    height = min(requested_height, available_height)

    desired_x = int(parent_left) + (max(1, int(parent_width)) - width) // 2
    desired_y = int(parent_top) + (max(1, int(parent_height)) - height) // 2
    minimum_x = int(work_left) + margin_x
    minimum_y = int(work_top) + margin_y
    maximum_x = int(work_left) + work_width - margin_x - frame_width - width
    maximum_y = int(work_top) + work_height - margin_y - frame_height - height
    x = max(minimum_x, min(desired_x, maximum_x))
    y = max(minimum_y, min(desired_y, maximum_y))
    return width, height, x, y


def normalize_work_area_to_screen(
    left: int, top: int, width: int, height: int, screen_width: int, screen_height: int
) -> tuple[int, int, int, int]:
    """Keep centering on the current Tk screen when Windows reports a virtual desktop work area."""
    width = int(width)
    height = int(height)
    screen_width = max(1, int(screen_width))
    screen_height = max(1, int(screen_height))
    if width > int(screen_width * 1.2) or height > int(screen_height * 1.2):
        return 0, 0, screen_width, screen_height
    if int(left) >= screen_width or int(top) >= screen_height:
        return 0, 0, screen_width, screen_height
    return int(left), int(top), width, height


def choose_centering_screen_size(
    tk_screen_width: int, tk_screen_height: int, primary_width: int, primary_height: int
) -> tuple[int, int]:
    """Prefer the primary monitor when Tk reports a multi-monitor virtual screen."""
    tk_w = max(1, int(tk_screen_width))
    tk_h = max(1, int(tk_screen_height))
    primary_w = int(primary_width)
    primary_h = int(primary_height)
    if primary_w > 0 and primary_h > 0:
        if tk_w > int(primary_w * 1.2) or tk_h > int(primary_h * 1.2):
            return primary_w, primary_h
    return tk_w, tk_h


def compute_centered_window(
    work_w: int, work_h: int, margin: int, max_w: int, max_h: int, min_w: int, min_h: int,
    frame_w: int = 0, frame_h: int = 0,
) -> tuple[int, int, int, int]:
    """主窗口在工作区内居中，四周（含底部任务栏一侧）留出 margin 的均匀空隙。

    返回 (客户区宽, 客户区高, 外框相对工作区原点的 x 偏移, y 偏移)。frame_w/frame_h 是
    标题栏与边框比客户区多出的宽/高——按「外框」而非客户区居中，否则标题栏会把底部空隙吃掉、
    使窗口下沿贴近任务栏。客户区尺寸夹在 [min, max] 与工作区之间。
    """
    work_w, work_h = int(work_w), int(work_h)
    margin = int(margin)
    frame_w, frame_h = max(0, int(frame_w)), max(0, int(frame_h))
    # 客户区 = 期望外框（工作区减两侧 margin）减去外框厚度；当缩放后的最小尺寸本身
    # 大于工作区时，硬上限始终是 work-frame，绝不让外框越过屏幕。
    available_w = max(1, work_w - frame_w)
    available_h = max(1, work_h - frame_h)
    win_w = min(int(max_w), work_w - 2 * margin - frame_w)
    win_h = min(int(max_h), work_h - 2 * margin - frame_h)
    min_width = min(max(1, int(min_w)), available_w)
    min_height = min(max(1, int(min_h)), available_h)
    win_w = max(min_width, min(win_w, available_w))
    win_h = max(min_height, min(win_h, available_h))
    outer_w, outer_h = win_w + frame_w, win_h + frame_h
    x = max(0, (work_w - outer_w) // 2)
    y = max(0, (work_h - outer_h) // 2)
    return win_w, win_h, x, y


def active_mode_action(tab_index: int) -> str:
    """当前选项卡对应的主操作：0=个股分析→analyze，其余（全市场选股）→screen。"""
    return "screen" if int(tab_index) == 1 else "analyze"


def compute_content_band(viewport_w: int, max_content_w: int, min_margin: int) -> tuple[int, int]:
    """计算居中内容带：内容宽度不超过上限，水平居中且左右留白相等。"""
    viewport_w = int(viewport_w)
    content_w = max(1, min(viewport_w - 2 * int(min_margin), int(max_content_w)))
    x_offset = max(int(min_margin), (viewport_w - content_w) // 2)
    return x_offset, content_w


def compute_workspace_columns(
    total_width: int,
    gap: int = 1,
    visual_share: float = 0.36,
) -> tuple[int, int]:
    """按稳定比例分配「因子拆解 | K 线」宽度，返回两列实际宽度。

    K 线承载蜡烛、三条均线与成交量，信息密度明显高于因子条，因此默认占 64%；窄窗口也
    保持同一信息优先级，而不是退回两个等宽面板。结果始终满足 left + right + gap = total。
    """
    total = max(3, int(total_width))
    divider = max(0, min(int(gap), total - 2))
    available = total - divider
    share = max(0.25, min(float(visual_share), 0.45))
    visual_width = max(1, min(available - 1, round(available * share)))
    chart_width = available - visual_width
    return visual_width, chart_width


def compute_scaled_minimum(
    work_width: int,
    work_height: int,
    scale: float,
    minimum_width: int,
    minimum_height: int,
    margin: int = 0,
    frame_width: int = 0,
    frame_height: int = 0,
) -> tuple[int, int]:
    """把逻辑最小尺寸按 DPI 放大，并为工作区留出外框与双侧边距。"""
    factor = max(1.0, float(scale))
    inset = max(0, round(int(margin) * factor)) * 2
    usable_width = max(1, int(work_width) - inset - max(0, int(frame_width)))
    usable_height = max(1, int(work_height) - inset - max(0, int(frame_height)))
    width = min(usable_width, max(1, round(int(minimum_width) * factor)))
    height = min(usable_height, max(1, round(int(minimum_height) * factor)))
    return width, height


def ui_scale(tk_scaling: float) -> float:
    """Windows DPI 缩放因子:Tk scaling(点→像素)换算,96 DPI=1.0,按 0.25 档位取整。"""
    try:
        raw = float(tk_scaling) * 72.0 / 96.0
    except (TypeError, ValueError):
        return 1.0
    if raw <= 1.05:
        return 1.0
    return max(1.0, round(raw * 4) / 4)


def stacked_text_y(top: int, line_height: int, count: int) -> list[int]:
    """从 top 起、按 line_height 依次下移的纵向坐标序列，用于把画布上多行堆叠文字按
    字体的实际行高（而非设计稿假定的固定像素差）排布：第 i 行 = top + i*line_height，
    保证相邻两行间距恒等于 line_height，不会被高 DPI 下放大的字体撑破而重叠。"""
    return [int(top) + i * int(line_height) for i in range(int(count))]


def compute_main_geometry(
    work_left: int, work_top: int, work_w: int, work_h: int, ui_scale_factor: float,
    min_w: int, min_h: int, max_w: int, max_h: int, margin: int,
    frame_w: int = 0, frame_h: int = 0,
) -> tuple[int, int, int, int]:
    """DPI 感知进程里 geometry 单位=物理像素:在物理工作区内按外框居中,逻辑尺寸常量
    (min/max/margin)先乘 ui_scale_factor 再夹制,使窗口随 DPI 成比例填满而非缩成逻辑像素。
    返回 (客户区宽, 客户区高, 外框左上角绝对 x, 绝对 y)。"""
    s = max(1.0, float(ui_scale_factor))
    win_w, win_h, off_x, off_y = compute_centered_window(
        work_w, work_h, round(margin * s),
        round(max_w * s), round(max_h * s), round(min_w * s), round(min_h * s),
        frame_w, frame_h,
    )
    return win_w, win_h, int(work_left) + off_x, int(work_top) + off_y
