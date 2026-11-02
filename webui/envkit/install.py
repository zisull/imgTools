# -*- coding: utf-8 -*-
"""install.py —— 装环境时真正动手的那几个动作
================================================================
「按 envs/ 清单补什么」由 check 定；「怎么装」放这里，界面（app.py）和
命令行（scripts/setup_all.py）共用同一份实现，免得两边各修各的。

所有函数都通过参数拿 log/on_line 回调，不直接 print 也不直接写 app 的日志。
"""
import codecs
import os
import re
import subprocess
import sys

from envkit import check as ec
from envkit import spec as sp

NO_CONS = 0x08000000 if os.name == "nt" else 0     # CREATE_NO_WINDOW


def _iter_stream(stream):
    """按 \\r 和 \\n 一起切行：pip/git 的进度条只用 \\r 回头，按行读会憋到最后。"""
    dec = codecs.getincrementaldecoder("utf-8")("replace")
    buf = ""
    fd = stream.fileno()
    while True:
        raw = os.read(fd, 4096)
        if not raw:
            break
        buf += dec.decode(raw)
        parts = re.split(r"\r\n|\r|\n", buf)
        buf = parts.pop()
        for line in parts:
            yield line
    buf += dec.decode(b"", True)
    if buf:
        yield buf


def run_stream(argv, cwd=None, keep=None, log=None, on_line=None, env=None):
    """跑一条命令，逐行喂给 on_line；命中 keep 的行交给 log。返回退出码，起不了返回 -1。"""
    try:
        p = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             env=env or dict(os.environ, PYTHONIOENCODING="utf-8",
                                             PYTHONUTF8="1"),
                             creationflags=NO_CONS)
    except OSError as e:
        if log:
            log("❌ 起不了命令：%s" % e)
        return -1
    for line in _iter_stream(p.stdout):
        line = line.rstrip()
        if not line:
            continue
        if on_line:
            try:
                on_line(line)
            except Exception:
                pass
        if keep is None or keep.search(line):
            if log:
                log(line)
    return p.wait()


def torch_gpu_specs(root):
    """摘出主环境那套 CUDA torch 的版本与索引，给内嵌 ComfyUI 复用。

    只取 index=="torch" 的包（走 --index-url 的 cuNNN 索引），版本钉死：
    不钉版本的话 pip 看见已装的 2.14.1+cpu 会当成「Requirement already satisfied」，
    换不动轮子，CPU 版就一直留在那儿。
    """
    try:
        spec = sp.load_spec(root)
        idx = str((spec.get("indexes") or {}).get("torch") or "")
        rt = (spec.get("runtimes") or {}).get("comfyui") or {}
        mine = str(rt.get("torch_index") or "")
        pkgs = ["%s==%s" % (p["name"], p["version"])
                for p in spec.get("packages") or []
                if p.get("index") == "torch" and p.get("version")]
        return (mine or idx), pkgs
    except Exception:
        return "", []


def clone_comfyui(root, fix, log, on_line=None):
    """把 ComfyUI 代码拉到 <root>/comfyui；已有则跳过，半截 clone 则接着拉。"""
    target = sp._abs(root, fix.get("dir") or "comfyui")
    repo = str(fix.get("repo") or "https://github.com/Comfy-Org/ComfyUI.git")
    branch = str(fix.get("branch") or "master")
    rel = os.path.relpath(target, root).replace("\\", "/")
    if os.path.isfile(os.path.join(target, "main.py")):
        log("ComfyUI 已在 %s/，跳过 clone" % rel)
        return True
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True,
                       creationflags=NO_CONS)
    except (OSError, subprocess.SubprocessError):
        log("❌ 系统里没有 git：装好 Git 再试（内嵌 ComfyUI 用 git clone 拉取）")
        return False
    keep = re.compile(r"Cloning|fatal|error|HEAD is now", re.I)
    if os.path.isdir(os.path.join(target, ".git")):
        log("🌿 %s/ 里有半截 clone，接着拉 %s …" % (rel, branch))
        rc = run_stream(["git", "-C", target, "fetch", "--depth", "1",
                         "--progress", "origin", branch],
                        cwd=root, keep=keep, log=log, on_line=on_line)
        if rc == 0:
            rc = run_stream(["git", "-C", target, "checkout", "-f", "FETCH_HEAD"],
                            cwd=root, keep=keep, log=log)
        return rc == 0 and os.path.isfile(os.path.join(target, "main.py"))
    if os.path.isdir(target) and os.listdir(target):
        log("❌ %s/ 里有东西但没有 main.py，不敢直接清：请手动挪走后重试" % rel)
        return False
    os.makedirs(os.path.dirname(target), exist_ok=True)
    log("🌿 clone ComfyUI（%s → %s/，约 100MB，只拉代码不拉权重）…" % (branch, rel))
    argv = ["git", "clone", "--depth", "1", "--progress",
            "--branch", branch, repo, target]
    rc = run_stream(argv, cwd=root, keep=keep, log=log, on_line=on_line)
    if rc != 0:
        log("⚠️ 直连 github 不稳：挂代理再试，或把 envs/index.json 的 "
            "runtimes.comfyui.branch 换成镜像分支")
        return False
    return os.path.isfile(os.path.join(target, "main.py"))


PIP_KEEP = re.compile(r"Collecting|Downloading|Download|Installing|Successfully|"
                      r"Requirement already|Building|Uninstalling|ERROR|error:|"
                      r"Getting requirements", re.I)


def ensure_comfyui_venv(root, fix, log, on_line=None, python=None):
    """建 comfyui/.venv 并装它自己的依赖；torch 必须先钉 CUDA 轮子。"""
    python = python or sys.executable
    try:
        rt = (sp.load_spec(root).get("runtimes") or {}).get("comfyui") or {}
    except Exception:
        rt = {}
    target = sp._abs(root, rt.get("dir") or "comfyui")
    vrel = str(fix.get("dir") or rt.get("venv") or "comfyui/.venv")
    vdir = sp._abs(root, vrel)
    req = sp._abs(root, rt.get("requirements") or "comfyui/requirements.txt")
    py = os.path.join(vdir, "Scripts" if os.name == "nt" else "bin",
                      "python.exe" if os.name == "nt" else "python")
    if not os.path.isfile(req):
        log("❌ 找不到 %s：ComfyUI 本体还没 clone 好" % req)
        return False
    if not os.path.isfile(py):
        log("🐍 给内嵌 ComfyUI 建独立 .venv（与千问环境完全隔离）…")
        if run_stream([python, "-m", "venv", vdir], cwd=root, log=log) != 0:
            return False
    idx, gpu_pkgs = torch_gpu_specs(root)
    fl = ec.torch_flavor(py)
    want = re.search(r"cu\d+", str(idx or ""))
    stale = bool(fl["cuda"]) and bool(want) and want.group(0) not in str(fl["version"])
    if fl["cuda"] and not stale:
        log("🔧 ComfyUI 的 torch 已是 CUDA 版（%s），跳过" % fl["version"])
    elif not (idx and gpu_pkgs):
        log("❌ 清单里没有 index=torch 的包：装不出 CUDA 版 torch，ComfyUI 起不来")
        return False
    else:
        if not fl["installed"]:
            why = "还没装"
        elif not fl["cuda"]:
            why = "现有的是 CPU 版 " + (fl["version"] or "?")
        else:
            why = "现有 %s 跑不动 int8/w4a8 内核，换 %s" % (fl["version"], want.group(0))
        log("🔧 给内嵌 ComfyUI 装 CUDA 版 torch（%s：%s）…" % (why, " ".join(gpu_pkgs)))
        argv = [py, "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
                "--index-url", idx] + gpu_pkgs
        if stale:
            argv += ["--force-reinstall", "--no-deps"]
        if run_stream(argv, cwd=target, keep=PIP_KEEP, log=log,
                      on_line=on_line) != 0:
            log("❌ CUDA 版 torch 没装上：download.pytorch.org 不稳就开代理再试")
            return False
        if not ec.torch_flavor(py)["cuda"]:
            log("❌ 装完还是 CPU 轮子：多半是索引被 pip 缓存/镜像劫了")
            return False
    mirror = ""
    try:
        mirror = (sp.load_spec(root).get("indexes") or {}).get("aliyun", "")
    except Exception:
        pass
    argv = [py, "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
            "-r", req]
    if mirror:
        argv += ["-i", mirror]
    log("📦 装 ComfyUI 其余依赖（torch 已就位，不会再被 CPU 版覆盖）…")
    if run_stream(argv, cwd=target, keep=PIP_KEEP, log=log, on_line=on_line) != 0:
        log("❌ ComfyUI 依赖没装完：看上面报错，网络不稳就开代理再试")
        return False
    log("✅ ComfyUI 独立环境就绪：%s" % os.path.relpath(py, root))
    return os.path.isfile(py)


def install_dir(root, rel):
    os.makedirs(sp._abs(root, rel), exist_ok=True)
