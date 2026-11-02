@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Moss 生图控制台

if exist ".venv\Scripts\python.exe" goto run

echo [准备] 第一次启动，正在创建 .venv ...
py -3.12 -m venv .venv >nul 2>&1
if errorlevel 1 py -3 -m venv .venv >nul 2>&1
if errorlevel 1 python -m venv .venv

if not exist ".venv\Scripts\python.exe" goto nopython

:run
".venv\Scripts\python.exe" scripts\setup_all.py %*
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo.
  echo [未完成] 看上面的提示。已经下载的会续传，修好后重跑本文件即可。
  pause
)
exit /b %RC%

:nopython
echo.
echo [错误] 没找到 Python 3.11-3.13。
echo        先装 Python 3.12，安装时勾选 "Add Python to PATH"：
echo        https://www.python.org/downloads/
pause
exit /b 1
