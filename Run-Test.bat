@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1
title VLC Gesture Controller - Test
if not exist ".venv\Scripts\python.exe" (
    echo Missing .venv. Follow README.md setup instructions using Python 3.14.
    pause
    exit /b 1
)
choice /c YN /n /m "Enable debug preview? Y = preview without VLC commands, N = normal control: "
if errorlevel 3 exit /b 1
if errorlevel 2 goto normal
if errorlevel 1 goto preview
exit /b 1

:preview
echo Starting debug preview. VLC commands are disabled. Q/Esc or Ctrl+C stops.
".venv\Scripts\python.exe" -u "%~dp0main.py" --debug-preview
goto stopped

:normal
echo Starting VLC Gesture Controller. Keep this console open. Ctrl+C stops.
".venv\Scripts\python.exe" -u "%~dp0main.py"
:stopped
set "CONTROLLER_EXIT=%ERRORLEVEL%"
echo.
if not "%CONTROLLER_EXIT%"=="0" (
    echo Controller exited with error code %CONTROLLER_EXIT%. Review the error above and logs.
) else (
    echo Controller stopped.
)
pause
exit /b %CONTROLLER_EXIT%
