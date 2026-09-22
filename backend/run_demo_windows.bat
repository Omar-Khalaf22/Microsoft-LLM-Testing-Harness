@echo off
title LLM Testing Harness
cd /d "%~dp0"
set "PORT=8020"

where py >nul 2>nul
if %errorlevel%==0 goto use_py

where python >nul 2>nul
if %errorlevel%==0 goto use_python

echo Python was not found on this computer.
echo Install Python from python.org and select Add Python to PATH during installation.
echo Then run this file again.
pause
exit /b 1

:use_py
start "LLM Testing Harness Server" cmd /k "py app.py"
goto open_browser

:use_python
start "LLM Testing Harness Server" cmd /k "python app.py"

:open_browser
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8020/?version=3
exit /b
