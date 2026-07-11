@echo off
REM ============================================================
REM  A-Share Strategy Assistant -- launch the GUI (dev mode).
REM  Requires Python 3.12+ on PATH. Runtime uses only the stdlib.
REM  Usage:
REM    run.bat              start the GUI
REM    run.bat --self-test  offline self-test (no network)
REM ============================================================
setlocal
cd /d "%~dp0"
python main.py %*
