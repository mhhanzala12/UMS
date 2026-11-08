@echo off
setlocal
cd /d "%~dp0"
echo =============================================
echo       Universal Media Studio - Setup
echo =============================================
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher was not found. Install Python 3.10+ from https://www.python.org/downloads/
  echo Make sure to enable "Add Python to PATH".
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto :error
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto :error
) else (
  .venv\Scripts\python.exe -c "import PySide6, yt_dlp, mutagen" >nul 2>nul
  if errorlevel 1 (
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 goto :error
  )
)
.venv\Scripts\python.exe app.py
if errorlevel 1 goto :error
exit /b 0
:error
echo.
echo Setup or startup failed. Check the message above.
pause
exit /b 1
