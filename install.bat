@echo off
setlocal
cd /d "%~dp0"
title Pulse installer

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 or newer was not found.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create the virtual environment.
    pause
    exit /b 1
  )
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed.
  pause
  exit /b 1
)

echo Enabling autostart and firewall rules (confirm the Windows UAC prompt)...
".venv\Scripts\python.exe" main.py --install

echo Starting Pulse in the background...
start "" ".venv\Scripts\pythonw.exe" main.py --background
timeout /t 4 >nul

echo.
".venv\Scripts\python.exe" main.py --token
echo.
echo Done. The Pulse icon appears in the system tray.
echo Open http://localhost:8765 on this PC to see the control panel.
pause
