@echo off
REM ============================================================
REM  A-Share Strategy Assistant -- build the Windows deliverable (onedir, ADR-0004).
REM  Installs the only build dependency (PyInstaller), then packages.
REM  Intermediates go to build\, deliverables to dist\.
REM ============================================================
setlocal
cd /d "%~dp0"

echo [1/2] Installing build dependency (PyInstaller, pinned in pyproject)...
python -m pip install --group build || goto :error

echo [2/2] Building the app folder...
python build_exe.py || goto :error

echo.
echo Done. dist\股市锦囊\ (double-click 股市锦囊.exe) plus the HTML manual are in dist\.
goto :eof

:error
echo.
echo Build failed. See the error messages above.
exit /b 1
