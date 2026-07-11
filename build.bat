@echo off
REM ============================================================
REM  A-Share Strategy Assistant -- build the single-file EXE.
REM  Installs the only build dependency (PyInstaller), then packages.
REM  Intermediates go to build\, deliverables to dist\.
REM ============================================================
setlocal
cd /d "%~dp0"

echo [1/2] Installing build dependency (PyInstaller)...
python -m pip install -r requirements-build.txt || goto :error

echo [2/2] Building the single-file EXE...
python build_exe.py || goto :error

echo.
echo Done. The EXE and HTML manual are in the dist\ folder.
goto :eof

:error
echo.
echo Build failed. See the error messages above.
exit /b 1
