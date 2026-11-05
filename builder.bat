
@echo off
setlocal EnableExtensions

title Universal Media Studio - Builder

cd /d "%~dp0"

set "APP_NAME=Universal Media Studio"
set "PYTHON=python"
set "VENV=%CD%\.venv"
set "PY=%VENV%\Scripts\python.exe"
set "TOOL_DIR=%CD%\.build_tools"
set "BINARY_ARG="
set "EXTRA_DATA="

echo.
echo ==========================================
echo   Universal Media Studio - Build
echo ==========================================
echo.

REM Check entry point
if not exist "app.py" (
    echo ERROR: app.py was not found.
    goto :error
)

REM Check Python
where %PYTHON% >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    goto :error
)

REM Create virtual environment
if not exist "%PY%" (
    echo Creating virtual environment...
    %PYTHON% -m venv "%VENV%"
    if errorlevel 1 goto :error
)

REM Install dependencies
echo Installing dependencies...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto :error

if exist "requirements.txt" (
    "%PY%" -m pip install -r requirements.txt
) else (
    "%PY%" -m pip install PySide6 yt-dlp mutagen
)
if errorlevel 1 goto :error

REM Install PyInstaller
"%PY%" -m pip install --upgrade pyinstaller
if errorlevel 1 goto :error

REM Prepare bundled executable tools
if exist "%TOOL_DIR%" rmdir /s /q "%TOOL_DIR%"
mkdir "%TOOL_DIR%"

echo Searching for FFmpeg...

for /r %%F in (ffmpeg.exe) do call :copytool "%%~fF" ffmpeg.exe
for /r %%F in (ffprobe.exe) do call :copytool "%%~fF" ffprobe.exe

if exist "%TOOL_DIR%\ffmpeg.exe" (
    echo Found ffmpeg.exe
    set "BINARY_ARG=--add-binary .build_tools;."
) else (
    echo WARNING: ffmpeg.exe was not found.
)

if exist "%TOOL_DIR%\ffprobe.exe" (
    echo Found ffprobe.exe
    if not defined BINARY_ARG set "BINARY_ARG=--add-binary .build_tools;."
)

REM Optional application assets
if exist "assets" set "EXTRA_DATA=--add-data assets;assets"

REM Clean previous builds
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

echo.
echo Building application...
echo.

REM IMPORTANT: Keep this PyInstaller command on ONE physical line.
"%PY%" -m PyInstaller --noconfirm --clean --onedir --name "%APP_NAME%" --distpath dist --workpath build --windowed --collect-all PySide6 --collect-all yt_dlp --hidden-import PySide6.QtQml --hidden-import PySide6.QtQuick --hidden-import PySide6.QtQuickControls2 --hidden-import PySide6.QtMultimedia --hidden-import PySide6.QtSvg --add-data "ums/qml;ums/qml" --add-data "ums/fonts;ums/fonts" %EXTRA_DATA% %BINARY_ARG% app.py

if errorlevel 1 goto :error

echo.
echo ==========================================
echo BUILD SUCCESSFUL!
echo ==========================================
echo.
echo Executable:
echo dist\%APP_NAME%\%APP_NAME%.exe
echo.
echo Distribute the ENTIRE folder:
echo dist\%APP_NAME%
echo.
pause
exit /b 0

:copytool
if not exist "%TOOL_DIR%\%~2" (
    copy /y "%~1" "%TOOL_DIR%\%~2" >nul
)
exit /b 0

:error
echo.
echo ==========================================
echo BUILD FAILED!
echo ==========================================
echo Check the error messages above.
echo.
pause
exit /b 1
