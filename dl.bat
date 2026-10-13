@echo off
cd /d %~dp0
set HF_ENDPOINT=https://hf-mirror.com
.venv\Scripts\python.exe scripts\dl_model.py %*
pause
