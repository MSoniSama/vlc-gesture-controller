@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1
if not exist ".venv\Scripts\python.exe" (
    echo Missing project virtual environment.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -u "%~dp0stop_controller.py"
if errorlevel 1 (
    echo Shutdown request failed. Review the error above.
    pause
    exit /b 1
)
