from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "AStockIntradayAdvisor"
OUTPUT_NAME = "股市锦囊.exe"
APP_DIR_NAME = "股市锦囊"  # onedir 交付目录名（ADR-0004）
MANUAL_NAME = "使用说明.html"
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # scripts/ 的上一级才是仓库根
# build/ 只放构建中间产物；dist/ 只放最终交付物（应用目录 + HTML 说明）。不再使用 outputs/。
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"
PYI_DIST_DIR = BUILD_DIR / "pyinstaller"  # PyInstaller 原始产物，留在 build/ 内
ENTRY = PROJECT_ROOT / "main.py"
ICON_PATH = PROJECT_ROOT / "assets" / "a_stock_strategy.ico"
# 设计 token 真源随包分发：打包后仓库路径不存在，Qt 主题只能从 assets/ 取（ui.assets.tokens_path）。
TOKENS_PATH = PROJECT_ROOT / "loop" / "product" / "tokens.json"


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
        # ADR-0004：onedir 而非 onefile —— onefile 每次启动重解压约 100MB（热启动 2.9s，超
        # warm_start 2.5s 预算），且把 Qt DLL 压进单文件会架空 LGPL-3.0 §4(d) 的重链接义务。
        "--onedir",
        "--windowed",
        "--disable-windowed-traceback",
        "--icon",
        str(ICON_PATH),
        "--add-data",
        f"{ICON_PATH}{os.pathsep}assets",
        "--add-data",
        f"{TOKENS_PATH}{os.pathsep}assets",
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

    built_dir = PYI_DIST_DIR / APP_NAME
    built_exe = built_dir / f"{APP_NAME}.exe"
    if not built_exe.exists():
        raise FileNotFoundError(f"Expected PyInstaller output not found: {built_exe}")

    # onedir 交付：整个应用目录搬到 dist/股市锦囊/，可执行文件改成中文交付名。
    target_dir = DIST_DIR / APP_DIR_NAME
    shutil.copytree(built_dir, target_dir)
    (target_dir / f"{APP_NAME}.exe").rename(target_dir / OUTPUT_NAME)
    target = target_dir / OUTPUT_NAME
    size_mib = target.stat().st_size / 1048576
    folder_mib = sum(p.stat().st_size for p in target_dir.rglob("*") if p.is_file()) / 1048576
    print(f"App written to: {target_dir}")
    print(f"  EXE: {target.name} ({size_mib:.1f} MiB); folder total {folder_mib:.1f} MiB")

    info_path = _write_build_info(target_dir)
    print(f"Build info written to: {info_path.name} (commit {_git_commit() or '未知'})")

    manual_path = _write_manual()
    print(f"Manual written to: {manual_path}")
    return 0


def _write_build_info(target_dir: Path) -> Path:
    """把构建时的源提交写进应用目录。

    没有这一条，产物就无法自证来历：清单是事后扫 dist/ 生成的，它只知道"生成清单时仓库在哪个提交"，
    而那未必是"构建出这个二进制的提交"——中间只要有一次提交或改动，清单就会把错误的来源写进发布
    元数据。这个文件让 make_release_manifest.py 能把两者对上，对不上就拒绝出清单。
    """
    info = {
        "commit": _git_commit(),
        "python": sys.version.split()[0],
        "packaging_mode": "onedir (ADR-0004)",
    }
    path = target_dir / "BUILD_INFO.json"
    path.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None


def _write_manual() -> Path:
    src_dir = PROJECT_ROOT / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    from ui.manual import build_manual_html

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
