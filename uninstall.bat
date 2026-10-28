@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Nothing to uninstall.
  pause
  exit /b 0
)
".venv\Scripts\python.exe" main.py --uninstall
echo.
echo Autostart removed. Quit the running server from the Pulse tray icon (Exit).
pause
