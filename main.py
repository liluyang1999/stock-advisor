from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Import must follow the sys.path bootstrap above.
from stock_advisor.ui.app import run_gui  # noqa: E402


def enable_dpi_awareness() -> None:
    """Ask Windows to render Tk at native DPI instead of bitmap-scaling the EXE."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
            return
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        pass


def _self_test() -> int:
    """离线自测：委托给 `services.self_check`，一份自检逻辑同时供命令行与 Qt 自检对话框（避免漂移）。"""
    from stock_advisor.services.self_check import self_check_cli_line

    ok, line = self_check_cli_line()
    if not ok:
        print(line, file=sys.stderr)
        return 1
    if sys.stdout is not None:
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in args:
        return _self_test()
    enable_dpi_awareness()
    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
