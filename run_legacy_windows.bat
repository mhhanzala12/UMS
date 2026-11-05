@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run run_windows.bat once to install the application dependencies.
  pause
  exit /b 1
)
.venv\Scripts\python.exe legacy_app.py
if errorlevel 1 pause
