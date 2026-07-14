from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "AStockIntradayAdvisor"
OUTPUT_NAME = "股市锦囊.exe"
MANUAL_NAME = "使用说明.html"
PROJECT_ROOT = Path(__file__).resolve().parent
# build/ 只放构建中间产物；dist/ 只放最终交付物（EXE + HTML 报告）。不再使用 outputs/。
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"
PYI_DIST_DIR = BUILD_DIR / "pyinstaller"  # PyInstaller 原始产物，留在 build/ 内
ENTRY = PROJECT_ROOT / "main.py"
ICON_PATH = PROJECT_ROOT / "assets" / "a_stock_strategy.ico"


def main() -> int:
    if not _pyinstaller_available():
        print(
            "PyInstaller is not installed. Run: python -m pip install pyinstaller", file=sys.stderr
        )
        return 2

    _remove_dir(BUILD_DIR)
    _remove_dir(DIST_DIR)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--disable-windowed-traceback",
        "--icon",
        str(ICON_PATH),
        "--add-data",
        f"{ICON_PATH}{os.pathsep}assets",
        "--optimize",
        "2",
        "--exclude-module",
        "unittest",
        "--exclude-module",
        "pydoc",
        "--exclude-module",
        "doctest",
        "--exclude-module",
        "pdb",
        "--exclude-module",
        "idlelib",
        "--name",
        APP_NAME,
        "--paths",
        str(PROJECT_ROOT / "src"),
        "--distpath",
        str(PYI_DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(BUILD_DIR),
        str(ENTRY),
    ]
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)

    built = PYI_DIST_DIR / f"{APP_NAME}.exe"
    if not built.exists():
        raise FileNotFoundError(f"Expected PyInstaller output not found: {built}")

    target = DIST_DIR / OUTPUT_NAME
    shutil.copy2(built, target)
    print(f"EXE written to: {target}")

    manual_path = _write_manual()
    print(f"Manual written to: {manual_path}")
    return 0


def _write_manual() -> Path:
    src_dir = PROJECT_ROOT / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    from stock_advisor.ui.manual import build_manual_html

    manual_path = DIST_DIR / MANUAL_NAME
    manual_path.write_text(build_manual_html(), encoding="utf-8")
    return manual_path


def _pyinstaller_available() -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _remove_dir(path: Path) -> None:
    resolved = path.resolve()
    project = PROJECT_ROOT.resolve()
    if project not in resolved.parents and resolved != project:
        raise RuntimeError(f"Refusing to remove path outside project: {resolved}")
    if path.exists():
        shutil.rmtree(path)


if __name__ == "__main__":
    raise SystemExit(main())
