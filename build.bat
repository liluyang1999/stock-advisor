@echo off
setlocal
cd /d "%~dp0"
REM Isolated, hash-locked Windows build; verifies and restores on failure.
python -B scripts/package_app.py %*
exit /b %errorlevel%
