@echo off
rem Launch Qwen-Image console (desktop shell).
rem pythonw = GUI subsystem: no black console window behind the UI.
rem stdout/stderr are teed into logs\run.log by webui\app.py; a startup
rem failure (import error or crash inside main) pops a native message box.
cd /d %~dp0
if not exist ".venv\Scripts\pythonw.exe" (
  echo [ERROR] .venv not found. Run setup.bat first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" webui\app.py
exit /b 0
