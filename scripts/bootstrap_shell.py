# -*- coding: utf-8 -*-
"""只装「界面壳」的最小依赖，让窗口第一时间出来。

    由 启动.bat 在全新克隆上调用：.venv 不存在时建好它、只装 pywebview，随后立刻开界面。
    重依赖（torch/diffusers 那一串）和权重都不在这里下——那是「环境与模型」页上
    两个分区各自「一键补齐」的事：看得见进度、能断点续传，也不用对着黑框干等。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = "https://mirrors.aliyun.com/pypi/simple/"


def pip(pkgs):
    return subprocess.call([sys.executable, "-m", "pip", "install",
                            "--disable-pip-version-check", "--no-input",
                            "-i", MIRROR] + list(pkgs))


def shell_ready(py) -> bool:
    """.venv 里的解释器能不能撑起界面壳（只看 webview 进不进得来）。"""
    return (os.path.isfile(py)
            and subprocess.call([py, "-c", "import webview"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL) == 0)


def main() -> int:
    vdir = os.path.join(ROOT, ".venv")
    py = os.path.join(vdir, "Scripts" if os.name == "nt" else "bin",
                      "python.exe" if os.name == "nt" else "python")
    # 壳已经能起来：什么都不做，启动器随即开界面
    if shell_ready(py):
        return 0
    if not os.path.isfile(py):
        print("[壳] 创建 .venv …")
        if subprocess.call([sys.executable, "-m", "venv", vdir]):
            print("[错误] 建不了 .venv：装个 Python 3.11~3.13 再来")
            return 1
    code = 0
    if pip(["pywebview"]):
        print("[错误] 界面壳（pywebview）没装上：检查网络，或开着代理再点一次启动")
        code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
