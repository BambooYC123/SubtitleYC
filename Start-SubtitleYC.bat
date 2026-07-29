@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 or newer is required.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto fail
)

".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto fail

".venv\Scripts\python.exe" -m subtitleyc.desktop
exit /b 0

:fail
echo.
echo SubtitleYC could not start. Check the error above.
pause
exit /b 1
