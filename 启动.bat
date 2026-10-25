@echo off
rem Launch Qwen-Image console (desktop shell).
rem pythonw = GUI subsystem: no black console window behind the UI.
rem stdout/stderr are teed into logs\run.log by webui\app.py; a startup
rem failure (import error or crash inside main) pops a native message box.
rem On a fresh clone (.venv missing) it bootstraps first, then launches.
cd /d %~dp0
if exist ".venv\Scripts\pythonw.exe" goto run

echo [launch] .venv not found - running first-time setup.
echo [launch] This installs the python packages only and may take a few minutes.
call setup.bat /auto
if not exist ".venv\Scripts\pythonw.exe" (
  echo [ERROR] setup did not finish. Run setup.bat to see why.
  pause
  exit /b 1
)

:run
start "" ".venv\Scripts\pythonw.exe" webui\app.py
exit /b 0
