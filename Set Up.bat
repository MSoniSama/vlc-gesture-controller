@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto failed
title VLC Gesture Controller - First-time Setup

choice /c YN /n /m "Is this the first-time setup? Press Y to begin or N to cancel: "
if errorlevel 2 goto cancelled
if errorlevel 1 goto begin
goto cancelled

:begin
echo.
echo Setting up VLC Gesture Controller in:
echo %CD%
echo Python 3.14 must already be installed. Internet access is required.
echo.

if not exist "requirements.txt" (
    echo ERROR: requirements.txt is missing from this folder.
    goto failed
)
if exist ".venv\Scripts\python.exe" goto check_python

echo Creating local .venv with Python 3.14...
py -3.14 -m venv .venv
if errorlevel 1 (
    echo ERROR: Could not create .venv. Install Python 3.14 with the Python launcher, then retry.
    goto failed
)

:check_python
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)"
if errorlevel 1 (
    echo ERROR: The existing .venv must use Python 3.14. Rename it and run setup again.
    goto failed
)

echo Installing project dependencies into .venv...
".venv\Scripts\python.exe" -m pip install --only-binary=:all: -r requirements.txt
if errorlevel 1 (
    echo ERROR: Dependency installation failed. Review the output above.
    goto failed
)

if not exist "models" mkdir "models"
if errorlevel 1 goto failed
if exist "models\hand_landmarker.task" goto complete

echo Downloading the hand model for offline operation...
powershell.exe -NoProfile -Command "$ErrorActionPreference = 'Stop'; try { Invoke-WebRequest -UseBasicParsing -Uri 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task' -OutFile 'models\hand_landmarker.task.download'; Move-Item -LiteralPath 'models\hand_landmarker.task.download' -Destination 'models\hand_landmarker.task' -Force } catch { Write-Error $_; exit 1 }"
if errorlevel 1 (
    echo ERROR: Model download failed. Check your internet connection and retry setup.
    goto failed
)

:complete
echo.
echo Setup complete. Double-click Run.bat, then bring VLC to foreground.
pause
exit /b 0

:cancelled
echo.
echo Setup cancelled. No setup changes were made.
pause
exit /b 0

:failed
echo.
echo Setup did not complete. Review the error above; this window will stay open.
pause
exit /b 1
