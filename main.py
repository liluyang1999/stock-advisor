from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Import must follow the sys.path bootstrap above.
from stock_advisor.observability import configure_logging  # noqa: E402
from stock_advisor.services.store import log_dir  # noqa: E402
from stock_advisor.ui.app import run_gui  # noqa: E402


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
    # 不再手动置进程 DPI 感知：Qt6 默认 Per-Monitor-V2，若在 QApplication 之前先调
    # SetProcessDpiAwareness(系统级)，awareness 只能设一次，反而会把 Qt 降级成系统 DPI 感知
    # （多显示器异构 DPI 下发虚）。这条是 Tk 时代的补丁，随 Tk 生产层一并移除（WI-023）。
    # GUI 启动即配置结构化日志：无控制台 EXE 下 rotating file 是用户唯一可诊断的持久 sink
    # （OBSERVABILITY.md）。日志目录不可写不得挡住启动，退回 last-resort/stderr。
    try:
        configure_logging(log_dir())
    except OSError:
        pass
    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
