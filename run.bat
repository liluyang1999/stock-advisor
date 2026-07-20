@echo off
REM ============================================================
REM  A-Share Strategy Assistant -- launch the GUI (dev mode).
REM  Requires Python 3.14+ on PATH and the Qt runtime:
REM    python -m pip install --group gui
REM  Usage:
REM    run.bat              start the GUI
REM    run.bat --self-test  offline self-test (no network)
REM ============================================================
setlocal
cd /d "%~dp0"
python main.py %*
