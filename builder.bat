@echo off
setlocal EnableExtensions EnableDelayedExpansion

title Universal Media Studio - Builder
cd /d "%~dp0"

set "APP_NAME=Universal Media Studio"
set "VENV=%CD%\.venv"
set "PY=%VENV%\Scripts\python.exe"
set "TOOL_DIR=%CD%\.build_tools"
set "EXE=%CD%\dist\%APP_NAME%.exe"
set "FFMPEG_URL1=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
set "FFMPEG_URL2=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
set "PKGARGS="
set "ICON_ARGS="
set "PYTHON="

REM Qt modules this app never imports. Leaving them out keeps the single EXE small,
REM which directly shortens the unpack time on every launch.
set "EXCLUDES=--exclude-module tkinter"
for %%X in (QtWebEngineCore QtWebEngineWidgets QtWebEngineQuick QtWebChannel QtWebSockets QtWebView Qt3DCore Qt3DRender Qt3DInput Qt3DLogic Qt3DAnimation Qt3DExtras QtCharts QtDataVisualization QtGraphs QtQuick3D QtDesigner QtUiTools QtHelp QtTest QtSql QtBluetooth QtNfc QtSensors QtSerialPort QtSerialBus QtPositioning QtLocation QtRemoteObjects QtScxml QtTextToSpeech QtHttpServer QtPdf QtPdfWidgets QtSpatialAudio) do set "EXCLUDES=!EXCLUDES! --exclude-module PySide6.%%X"

echo.
echo ==========================================
echo   Universal Media Studio - Single EXE Build
echo ==========================================
echo.

REM ---- Check entry point ----
if not exist "app.py" (
    echo ERROR: app.py was not found. Run this file from the repo folder.
    goto :error
)

REM ---- Find a real Python 3.10+ (the Microsoft Store stub is skipped) ----
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3"
if not defined PYTHON (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON=python"
)
if not defined PYTHON (
    echo ERROR: Python 3.10 or newer was not found. Install it from python.org and tick "Add Python to PATH".
    goto :error
)

REM ---- Virtual environment ----
if not exist "%PY%" (
    echo Creating virtual environment...
    %PYTHON% -m venv "%VENV%"
    if errorlevel 1 goto :error
)

REM ---- Dependencies ----
echo Installing dependencies...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto :error

if exist "requirements.txt" (
    "%PY%" -m pip install -r requirements.txt
) else (
    "%PY%" -m pip install PySide6 "yt-dlp[default]" mutagen
)
if errorlevel 1 goto :error

"%PY%" -m pip install --upgrade pyinstaller
if errorlevel 1 goto :error

REM ---- FFmpeg + FFprobe (bundled INSIDE the exe) ----
if not exist "%TOOL_DIR%" mkdir "%TOOL_DIR%"

REM A copy dropped next to builder.bat is used first
if not exist "%TOOL_DIR%\ffmpeg.exe" if exist "%CD%\ffmpeg.exe" copy /y "%CD%\ffmpeg.exe" "%TOOL_DIR%\ffmpeg.exe" >nul
if not exist "%TOOL_DIR%\ffprobe.exe" if exist "%CD%\ffprobe.exe" copy /y "%CD%\ffprobe.exe" "%TOOL_DIR%\ffprobe.exe" >nul

if exist "%TOOL_DIR%\ffmpeg.exe" if exist "%TOOL_DIR%\ffprobe.exe" goto :tools_ready

echo.
echo FFmpeg not found locally. Downloading a static build...
call :download_ffmpeg "%FFMPEG_URL1%"
if exist "%TOOL_DIR%\ffmpeg.exe" if exist "%TOOL_DIR%\ffprobe.exe" goto :tools_ready
echo First source failed, trying backup source...
call :download_ffmpeg "%FFMPEG_URL2%"

:tools_ready
if not exist "%TOOL_DIR%\ffmpeg.exe" (
    echo ERROR: Could not get ffmpeg.exe. Put ffmpeg.exe and ffprobe.exe next to builder.bat and run again.
    goto :error
)
if not exist "%TOOL_DIR%\ffprobe.exe" (
    echo ERROR: Could not get ffprobe.exe. Put ffmpeg.exe and ffprobe.exe next to builder.bat and run again.
    goto :error
)

REM A broken or DLL-dependent ffmpeg would not work once bundled, so test it now
"%TOOL_DIR%\ffmpeg.exe" -version >nul 2>&1
if errorlevel 1 (
    echo ERROR: The ffmpeg.exe found is not a standalone build. Delete .build_tools and run again.
    goto :error
)
"%TOOL_DIR%\ffprobe.exe" -version >nul 2>&1
if errorlevel 1 (
    echo ERROR: The ffprobe.exe found is not a standalone build. Delete .build_tools and run again.
    goto :error
)
echo FFmpeg and FFprobe ready.

REM ---- Optional extras (only added if installed) ----
for %%M in (yt_dlp_ejs curl_cffi certifi websockets brotli mutagen) do call :addpkg %%M

REM ---- Icon: output.ico is the EXE icon and is also bundled for the window/taskbar icon ----
if exist "output.ico" (
    set "ICON_ARGS=--icon output.ico --add-data output.ico;."
) else (
    echo WARNING: output.ico was not found, building without a custom icon.
)

REM ---- Build: lean first, full Qt only if the lean EXE fails its self-test ----
call :build lean
if errorlevel 1 goto :error
call :smoke
if not errorlevel 1 goto :success

echo.
echo The lean build failed the self-test. Rebuilding with the complete Qt package...
call :build full
if errorlevel 1 goto :error
call :smoke
if errorlevel 1 goto :error

:success
if exist "build" rmdir /s /q "build"
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"
set "SIZE=0"
for %%F in ("%EXE%") do set "SIZE=%%~zF"
set /a MB=SIZE/1048576
echo.
echo ==========================================
echo  BUILD SUCCESSFUL!
echo ==========================================
echo.
echo  %EXE%
echo  Size: about !MB! MB, one file.
echo.
echo  This single EXE contains FFmpeg, FFprobe, yt-dlp, fonts, the interface and the icon.
echo  It was copied to a different folder and started with a clean PATH as a final test,
echo  so it can be moved or copied anywhere. Settings are kept in your user profile.
echo  The first launch can take a few seconds while the EXE unpacks itself.
echo.
pause
exit /b 0

REM ==========================================
:build
REM %1 = lean or full
set "QT_ARGS=%EXCLUDES%"
if /i "%~1"=="full" set "QT_ARGS=--collect-all PySide6"

if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

echo.
echo Building single-file EXE [%~1] - this can take several minutes...
echo.

REM IMPORTANT: Keep this PyInstaller command on ONE physical line.
"%PY%" -m PyInstaller --noconfirm --clean --onefile --name "%APP_NAME%" --distpath dist --workpath build --windowed --noupx --collect-all yt_dlp %PKGARGS% --hidden-import PySide6.QtQml --hidden-import PySide6.QtQuick --hidden-import PySide6.QtQuickControls2 --hidden-import PySide6.QtMultimedia --hidden-import PySide6.QtSvg --hidden-import PySide6.QtWidgets %QT_ARGS% --add-data "ums/qml;ums/qml" --add-data "ums/fonts;ums/fonts" --add-binary "%TOOL_DIR%\ffmpeg.exe;." --add-binary "%TOOL_DIR%\ffprobe.exe;." %ICON_ARGS% app.py
if errorlevel 1 exit /b 1

if not exist "%EXE%" (
    echo ERROR: PyInstaller finished but the exe was not created.
    exit /b 1
)
exit /b 0

REM ==========================================
:smoke
REM Copies the EXE to a fresh folder (with a space in its name) and runs it with a PATH that
REM contains no ffmpeg, in self-test mode. Exit code 0 means the interface loaded and every
REM bundled part (ffmpeg, ffprobe, yt-dlp, Qt Multimedia, fonts, icon, SVG/ICO support) works.
setlocal
set "TESTBASE=%TEMP%\ums_portable_test_%RANDOM%%RANDOM%"
set "TESTDIR=%TESTBASE%\moved folder"
mkdir "%TESTDIR%" >nul 2>&1
copy /y "%EXE%" "%TESTDIR%\%APP_NAME%.exe" >nul
if errorlevel 1 (
    echo ERROR: Could not copy the EXE for the self-test.
    exit /b 1
)
echo.
echo Running self-test on the moved EXE - a window may flash for a moment...
set "PATH=%SystemRoot%\system32;%SystemRoot%"
set "UMS_SELFTEST=1"
start "" /wait "%TESTDIR%\%APP_NAME%.exe"
set "RC=!errorlevel!"
set "UMS_SELFTEST="
rmdir /s /q "%TESTBASE%" >nul 2>&1
if "!RC!"=="0" (
    echo Self-test passed.
    exit /b 0
)
echo Self-test FAILED with exit code !RC!. Last lines of the startup log:
powershell -NoProfile -Command "Get-Content -Tail 15 -ErrorAction SilentlyContinue \"$env:USERPROFILE\.universal_media_studio\startup.log\""
exit /b 1

REM ==========================================
:download_ffmpeg
set "ZIP=%TEMP%\ums_ffmpeg.zip"
set "EXD=%TEMP%\ums_ffmpeg_extract"
if exist "%ZIP%" del /q "%ZIP%"
if exist "%EXD%" rmdir /s /q "%EXD%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -Uri '%~1' -OutFile '%ZIP%' -UseBasicParsing; Expand-Archive -Path '%ZIP%' -DestinationPath '%EXD%' -Force; $f=Get-ChildItem -Path '%EXD%' -Recurse -Filter ffmpeg.exe | Select-Object -First 1; $p=Get-ChildItem -Path '%EXD%' -Recurse -Filter ffprobe.exe | Select-Object -First 1; if ($f -and $p) { Copy-Item $f.FullName '%TOOL_DIR%\ffmpeg.exe' -Force; Copy-Item $p.FullName '%TOOL_DIR%\ffprobe.exe' -Force } } catch { Write-Host $_.Exception.Message }"
if exist "%ZIP%" del /q "%ZIP%"
if exist "%EXD%" rmdir /s /q "%EXD%"
exit /b 0

:addpkg
"%PY%" -c "import %~1" >nul 2>&1
if not errorlevel 1 set "PKGARGS=%PKGARGS% --collect-all %~1"
exit /b 0

:error
echo.
echo ==========================================
echo  BUILD FAILED!
echo ==========================================
echo Check the error messages above.
echo.
pause
exit /b 1
