#!/usr/bin/env bash
# ============================================================
#  股市锦囊 —— 启动图形界面（开发模式）
#  需本机已装 Python 3.14+ 与 Qt 运行时：python -m pip install --group gui
#  用法:
#    ./run.sh              启动图形界面
#    ./run.sh --self-test  离线自测（不触网，跑通核心逻辑）
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"
exec python main.py "$@"
