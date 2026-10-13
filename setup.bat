@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe "C:\Program Files\Python312\python.exe" -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip -i https://mirrors.aliyun.com/pypi/simple/
.venv\Scripts\python.exe -m pip install torch "transformers>=5.17" accelerate pillow "huggingface_hub" -i https://mirrors.aliyun.com/pypi/simple/
.venv\Scripts\python.exe -m pip install "git+https://github.com/huggingface/diffusers.git"
echo SETUP DONE
pause
