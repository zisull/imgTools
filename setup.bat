@echo off
rem Qwen-Image console one-click setup (portable, all inside this folder)
cd /d %~dp0
if not exist .venv\Scripts\python.exe "C:\Program Files\Python312\python.exe" -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip -i https://mirrors.aliyun.com/pypi/simple/
rem torch MUST come from pytorch cu128 index, PyPI default wheel on Windows is CPU-only
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
.venv\Scripts\python.exe -m pip install "transformers>=5.17" accelerate pillow huggingface_hub -i https://mirrors.aliyun.com/pypi/simple/
rem diffusers needs git build; if clone fails retry with HTTPS_PROXY=127.0.0.1:7897
.venv\Scripts\python.exe -m pip install "git+https://github.com/huggingface/diffusers.git"
.venv\Scripts\python.exe -m pip install pywebview -i https://mirrors.aliyun.com/pypi/simple/
.venv\Scripts\python.exe -m pip install fastapi uvicorn python-multipart -i https://mirrors.aliyun.com/pypi/simple/
echo SETUP DONE
pause
