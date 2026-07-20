#!/usr/bin/env bash
# ============================================================
#  股市锦囊 —— 打包成免安装应用目录（onedir，见 ADR-0004），输出到 dist/
#  会先安装唯一的构建期依赖 PyInstaller，再执行打包。
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/2] 安装构建依赖 (PyInstaller)..."
python -m pip install -r requirements-build.txt

echo "[2/2] 开始打包..."
python build_exe.py

echo "打包完成：dist/股市锦囊/（双击其中的 股市锦囊.exe 运行）与 dist/使用说明.html。"
