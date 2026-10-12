@echo off
cd /d "%~dp0"
if errorlevel 1 exit /b 1
wscript.exe "%~dp0Run-Hidden.vbs"
