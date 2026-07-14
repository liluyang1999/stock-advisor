from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from .assets import app_asset_path
from .layout import (
    choose_centering_screen_size,
    compute_child_window_geometry,
    compute_main_geometry,
    compute_scaled_minimum,
    normalize_work_area_to_screen,
    ui_scale,
)
from .theme import (
    APP_ICON_FILENAME,
    CHILD_WINDOW_WORKAREA_MARGIN,
    MAIN_MIN_SIZE,
    POS_COLOR,
    WINDOW_MAX_SIZE,
    WINDOW_WORKAREA_MARGIN,
)

if TYPE_CHECKING:
    from ._app_members import AppMembers as _MembersBase
else:
    _MembersBase = object


class WindowGeometryMixin(_MembersBase):
    """窗口居中/缩放/DPI/图标/几何——从 StockAdvisorApp 抽出的窗口管理关注点。

    仅承载方法;所有实例状态(self.root/self._ui_scale 等)由 StockAdvisorApp 提供。
    """

    def _center_window(self, window: tk.Tk | tk.Toplevel) -> None:
        # 主窗口：在「屏幕工作区」（已排除任务栏）内按【外框】居中，四周（含底部任务栏一侧）
        # 留出 WINDOW_WORKAREA_MARGIN 的均匀空隙。两遍：先放一版让窗口实体化以量出标题栏/边框
        # 厚度，再带着外框厚度精确居中（窗口映射后还会在 _finalize_geometry 再校准一次）。
        self._apply_centered_geometry(window)
        window.update_idletasks()
        self._apply_centered_geometry(window)

    def _apply_centered_geometry(self, window: tk.Tk | tk.Toplevel) -> None:
        left, top, work_w, work_h = self._screen_work_area(window)
        frame_w, frame_h = self._frame_extents(window)
        factor = ui_scale(self._tk_scaling(window))
        win_w, win_h, x, y = compute_main_geometry(
            left,
            top,
            work_w,
            work_h,
            factor,
            MAIN_MIN_SIZE[0],
            MAIN_MIN_SIZE[1],
            WINDOW_MAX_SIZE[0],
            WINDOW_MAX_SIZE[1],
            WINDOW_WORKAREA_MARGIN,
            frame_w,
            frame_h,
        )
        window.geometry(f"{win_w}x{win_h}+{x}+{y}")

    def _apply_root_minimum(self) -> None:
        _left, _top, work_width, work_height = self._screen_work_area(self.root)
        frame_width, frame_height = self._frame_extents(self.root)
        self.root.minsize(
            *compute_scaled_minimum(
                work_width,
                work_height,
                self._ui_scale,
                MAIN_MIN_SIZE[0],
                MAIN_MIN_SIZE[1],
                margin=WINDOW_WORKAREA_MARGIN,
                frame_width=frame_width,
                frame_height=frame_height,
            )
        )

    def _tk_scaling(self, window: tk.Misc) -> float:
        try:
            return float(window.tk.call("tk", "scaling"))
        except tk.TclError, ValueError, TypeError:
            return 96 / 72

    def _sc(self, px: float) -> int:
        """把设计稿像素值按 self._ui_scale 换算为当前 DPI 下的实际像素——所有固定画布高/
        行高/装饰尺寸都经此换算，使其随字体一起放大，避免大屏下内容显得局促。"""
        return int(round(px * self._ui_scale))

    def _frame_extents(self, window: tk.Misc) -> tuple[int, int]:
        """量出窗口外框（标题栏 + 边框）比客户区多出的宽/高；窗口未实体化时返回 (0, 0)。"""
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = ctypes.windll.user32.GetAncestor(window.winfo_id(), 2)  # GA_ROOT
            rect = wintypes.RECT()
            if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                outer_w = rect.right - rect.left
                outer_h = rect.bottom - rect.top
                client_w, client_h = window.winfo_width(), window.winfo_height()
                if client_w > 1 and client_h > 1 and outer_w >= client_w and outer_h >= client_h:
                    return outer_w - client_w, outer_h - client_h
        except Exception:
            pass
        return 0, 0

    def _child_frame_extents(self, window: tk.Toplevel) -> tuple[int, int]:
        """子窗尚未实体化而量不到外框时，按主窗同类外框保守回退。"""
        frame_width, frame_height = self._frame_extents(window)
        if frame_width > 0 and frame_height > 0:
            return frame_width, frame_height
        root_width, root_height = self._frame_extents(self.root)
        return (
            frame_width if frame_width > 0 else root_width,
            frame_height if frame_height > 0 else root_height,
        )

    def _finalize_geometry(self) -> None:
        # 窗口映射后再按真实外框居中一次（此时能量准标题栏/边框），并把内容带按真实宽度居中。
        self._apply_root_minimum()
        self._apply_centered_geometry(self.root)
        self._relayout_content()

    def _screen_work_area(self, window: tk.Misc) -> tuple[int, int, int, int]:
        """返回屏幕工作区 (left, top, width, height)，已排除任务栏；失败回退到整屏。均为物理像素。"""
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        try:
            import ctypes
            from ctypes import wintypes

            primary_w = ctypes.windll.user32.GetSystemMetrics(0)  # SM_CXSCREEN
            primary_h = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN
            screen_w, screen_h = choose_centering_screen_size(
                screen_w, screen_h, primary_w, primary_h
            )

            rect = wintypes.RECT()
            # SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if width > 0 and height > 0:
                    return normalize_work_area_to_screen(
                        rect.left, rect.top, width, height, screen_w, screen_h
                    )
        except Exception:
            pass
        return 0, 0, screen_w, screen_h

    def _center_child_window(self, window: tk.Toplevel, size: tuple[int, int]) -> None:
        self.root.update_idletasks()

        def place(frame_width: int, frame_height: int) -> None:
            work_left, work_top, work_width, work_height = self._screen_work_area(window)
            width, height, x, y = compute_child_window_geometry(
                parent_left=self.root.winfo_x(),
                parent_top=self.root.winfo_y(),
                parent_width=self.root.winfo_width(),
                parent_height=self.root.winfo_height(),
                work_left=work_left,
                work_top=work_top,
                work_width=work_width,
                work_height=work_height,
                requested_width=size[0],
                requested_height=size[1],
                margin=self._sc(CHILD_WINDOW_WORKAREA_MARGIN),
                frame_width=frame_width,
                frame_height=frame_height,
            )
            window.geometry(f"{width}x{height}+{x}+{y}")

        # 先以主窗外框厚度给出稳定首帧，再在子窗实体化后用它自己的真实外框校准一次。
        frame_width, frame_height = self._frame_extents(self.root)
        place(frame_width, frame_height)
        window.update_idletasks()
        frame_width, frame_height = self._child_frame_extents(window)
        place(frame_width, frame_height)

    def _apply_child_minimum(self, window: tk.Toplevel, logical_size: tuple[int, int]) -> None:
        """DPI 放大子窗最小尺寸，但绝不让其外框越过当前屏幕工作区。"""
        _left, _top, work_width, work_height = self._screen_work_area(window)
        frame_width, frame_height = self._child_frame_extents(window)
        window.minsize(
            *compute_scaled_minimum(
                work_width,
                work_height,
                self._ui_scale,
                logical_size[0],
                logical_size[1],
                margin=CHILD_WINDOW_WORKAREA_MARGIN,
                frame_width=frame_width,
                frame_height=frame_height,
            )
        )

    def _set_window_icon(self, window: tk.Tk | tk.Toplevel) -> None:
        icon = app_asset_path(APP_ICON_FILENAME)
        if not icon.exists():
            return
        try:
            window.iconbitmap(str(icon))
        except tk.TclError:
            pass

    def _draw_logo(self, canvas: tk.Canvas) -> None:
        canvas.delete("all")
        width = max(1, int(canvas.cget("width")))
        height = max(1, int(canvas.cget("height")))
        scale = min(width, height) / 54
        x_offset = (width - 54 * scale) / 2
        y_offset = (height - 54 * scale) / 2

        def box(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float, float, float]:
            return (
                x_offset + x1 * scale,
                y_offset + y1 * scale,
                x_offset + x2 * scale,
                y_offset + y2 * scale,
            )

        def points(*coords: float) -> list[float]:
            return [
                (x_offset + value * scale) if index % 2 == 0 else (y_offset + value * scale)
                for index, value in enumerate(coords)
            ]

        stroke = max(1, round(3 * scale))
        canvas.create_oval(*box(4, 4, 50, 50), fill="#0f2f57", outline="")
        canvas.create_oval(*box(11, 11, 43, 43), fill="#163f73", outline="")
        canvas.create_polygon(
            *points(27, 13, 39, 40, 33, 40, 30, 32, 21, 32, 18, 40, 12, 40, 24, 13),
            fill="#ffffff",
            outline="",
        )
        canvas.create_line(*points(20, 29, 31, 29), fill="#0f2f57", width=stroke)
        canvas.create_line(
            *points(13, 39, 22, 31, 31, 34, 41, 20), fill=POS_COLOR, width=stroke, smooth=True
        )
        canvas.create_oval(*box(39, 18, 44, 23), fill=POS_COLOR, outline="")
