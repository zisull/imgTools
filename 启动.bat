@echo off
rem Launch Qwen-Image console (desktop shell).
rem pythonw = GUI subsystem: no black console window behind the UI.
rem stdout/stderr are teed into logs\run.log by webui\app.py; a startup
rem failure (import error or crash inside main) pops a native message box.
rem
rem 铁律：界面先出来。这里只保证「壳」能跑（.venv + pywebview，几秒），
rem 重依赖（torch/diffusers…）和 30GB/15GB 权重一律不在开机前偷偷下——
rem 那些都是打开「环境与模型」页后，按分区点「一键补齐」的活：看得见进度、断点续传。
cd /d %~dp0

rem 1) 壳已就绪（.venv 里有 webview）→ 脚本秒退，直接开界面
py -3 scripts\bootstrap_shell.py 2>nul
if errorlevel 1 python scripts\bootstrap_shell.py
if errorlevel 1 (
  echo [ERROR] 界面壳起不来：装 Python 3.12 或开代理后重试。
  echo [ERROR] 想手动来：先跑 python -m venv .venv ^&^& .venv\Scripts\python -m pip install pywebview
  pause
  exit /b 1
)

if not exist ".venv\Scripts\pythonw.exe" (
  echo [ERROR] .venv 没建好：重跑一次 启动.bat，或直接双击 setup.bat 看报什么。
  pause
  exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" webui\app.py
exit /b 0
