@echo off
rem Launch Qwen-Image console (desktop shell)
cd /d %~dp0
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" webui\app.py
if errorlevel 1 (
  echo.
  echo [ERROR] Program exited with an error. See messages above.
  pause
)
