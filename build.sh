#!/usr/bin/env bash
# ============================================================
#  股市锦囊 —— 打包成单文件 EXE，输出到 dist/
#  会先安装唯一的构建期依赖 PyInstaller，再执行打包。
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/2] 安装构建依赖 (PyInstaller)..."
python -m pip install -r requirements-build.txt

echo "[2/2] 开始打包..."
python build_exe.py

echo "打包完成，产物在 dist/ 目录（股市锦囊.exe 与使用说明.html）。"
