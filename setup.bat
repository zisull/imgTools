@echo off
rem Qwen-Image console one-click bootstrap (portable: everything stays in this folder).
rem What gets installed is driven by env.json - the same list the desktop app reads.
rem Usage: setup.bat        interactive, pauses at the end
rem        setup.bat /auto   no pause (called by the launcher on a fresh clone)
setlocal
cd /d %~dp0
set RC=0

if exist ".venv\Scripts\python.exe" goto havevenv
echo [setup] creating .venv ...
py -3.12 -m venv .venv 2>nul
if errorlevel 1 python -m venv .venv
:havevenv
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] no Python 3.12 found. Install it, then run setup.bat again.
  set RC=1
  goto end
)

".venv\Scripts\python.exe" -m pip install -U pip -i https://mirrors.aliyun.com/pypi/simple/
".venv\Scripts\python.exe" scripts\setup_env.py
if errorlevel 1 set RC=1
echo.
echo [setup] done. Model weights are NOT downloaded here (about 30 GB).
echo [setup] start the app and click the one-click fix on the env page,
echo [setup] or run: ".venv\Scripts\python.exe" scripts\setup_env.py --models

:end
if /I not "%~1"=="/auto" pause
endlocal & exit /b %RC%
