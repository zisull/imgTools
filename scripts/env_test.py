# -*- coding: utf-8 -*-
"""env_check 回归：造一台「假机器」逐项体检，不装包、不碰真权重、不联网。

跑法： .venv\\Scripts\\python.exe scripts\\env_test.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))

import env_check as ec  # noqa: E402

RESULTS = []


def ok(name, cond, extra=""):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ((" · " + str(extra)) if extra else ""))


SPEC = {
    "python": {"min": "3.11", "max": "3.13", "best": "3.12"},
    "indexes": {"pypi": "https://mirrors.aliyun.com/pypi/simple/",
                "torch": "https://download.pytorch.org/whl/cu128"},
    "packages": [
        {"name": "torch", "version": "2.11.0", "index": "torch", "cuda": True},
        {"name": "diffusers", "commit": "916a5791ed5f29d966200d2eee53f06862ec4434",
         "repo": "https://github.com/huggingface/diffusers.git"},
        {"name": "uvicorn", "version": "0.54.0", "index": "pypi", "optional": True},
    ],
    "models": [{"key": "turbo", "label": "T", "repo": "o/turbo", "dir": "models/turbo",
                "gb": 30.3,
                "must": {"model_index.json": 10, "transformer/a.safetensors": 20}}],
    "dirs": [{"path": "outputs"}, {"path": "logs"}],
}

VENV = os.path.join(ROOT, ".venv")
GOOD = {"torch": "2.11.0+cu128", "diffusers": "0.41.0.dev0", "uvicorn": "0.54.0"}
GOOD_COMMIT = {"diffusers": "916a5791ed5f29d966200d2eee53f06862ec4434"}


def probe(**over):
    """一台假机器的全部探针，默认「啥都齐」，用例只覆盖自己关心的那一项。"""
    p = dict(py_version="3.12.10", prefix=VENV, pkg_version=lambda n: GOOD.get(n),
             cuda=(True, "12.8"), free_gb=500.0, git_commit=lambda n: GOOD_COMMIT.get(n))
    p.update(over)
    return p


def run(root, **over):
    return ec.check(root, spec=SPEC, **probe(**over))


def item(r, key):
    for x in r["items"]:
        if x["key"] == key:
            return x
    raise AssertionError("没有这项：" + key)


def fake_root(files, dirs=("outputs", "logs")):
    """按 {相对路径: 字节数} 造一棵假仓库根（dirs 控制要不要预建那几个目录）。"""
    import tempfile

    tmp = tempfile.mkdtemp(prefix="qic_env_")
    for rel, size in files.items():
        p = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b"\0" * size)
    for d in dirs:
        os.makedirs(os.path.join(tmp, d), exist_ok=True)
    return tmp


FULL = {"models/turbo/model_index.json": 10, "models/turbo/transformer/a.safetensors": 20}


def main():
    root = fake_root(FULL)

    r = run(root)
    ok("假机器全齐：可补 0 项", r["todo"] == [], r["todo"])
    ok("分组齐全（运行环境/依赖包/模型权重/目录）",
       {x["group"] for x in r["items"]} == {ec.G_PY, ec.G_PKG, ec.G_MODEL, ec.G_DIR})
    ok("每项都带 fix 结构", all("fix" in x and "kind" in x["fix"] for x in r["items"]))

    r = run(fake_root({}, dirs=()))
    ok("模型目录不存在 → miss", item(r, "model:turbo")["state"] == "miss")
    ok("模型 miss 进待补", "model:turbo" in r["todo"])
    ok("目录不存在 → miss", item(r, "dir:outputs")["state"] == "miss")

    r = run(root, pkg_version=lambda n: None)
    t = item(r, "pkg:torch")
    ok("torch 没装 → miss", t["state"] == "miss", t["detail"])
    ok("torch 的修复动作指向 cu128 索引", t["fix"]["index"].endswith("cu128")
       and t["fix"]["index_url"] is True, t["fix"])
    ok("可选包没装只提醒", item(r, "pkg:uvicorn")["state"] == "warn",
       item(r, "pkg:uvicorn")["detail"])
    ok("可选包不进待补", "pkg:uvicorn" not in r["todo"])

    t = item(run(root, cuda=(False, "12.8")), "pkg:torch")
    ok("CPU 轮子单独说清根因", t["state"] == "part" and "CPU" in t["detail"], t["detail"])
    t = item(run(root, cuda=(None, None)), "pkg:torch")
    ok("torch 装了但 import 不了 → 待补", t["state"] == "part" and "import" in t["detail"],
       t["detail"])

    t = item(run(root, pkg_version=lambda n: "2.9.0" if n == "torch" else GOOD.get(n)),
             "pkg:torch")
    ok("版本低于要求 → 待补", t["state"] == "part", t["detail"])

    r = run(root, git_commit=lambda n: "b1a2c3d4" + "0" * 32 if n == "diffusers" else None)
    t = item(r, "pkg:diffusers")
    ok("commit 不对 → 待补", t["state"] == "part" and "b1a2c3d4" in t["detail"], t["detail"])
    r = run(root, git_commit=lambda n: None)
    t = item(r, "pkg:diffusers")
    ok("commit 查不出 → 只提醒，不逼重装", t["state"] == "warn", t["detail"])
    ok("查不出 commit 不进待补", "pkg:diffusers" not in r["todo"])

    bad = dict(FULL)
    bad["models/turbo/transformer/a.safetensors"] = 19
    t = item(run(fake_root(bad)), "model:turbo")
    ok("分片字节数不对 → 待补且点名文件",
       t["state"] == "part" and "a.safetensors" in t["detail"], t["detail"])

    t = item(run(root, free_gb=10.0), "disk")
    ok("磁盘不够 → 提醒", t["state"] == "warn", t["detail"])
    ok("磁盘不够不进待补（补全解决不了腾地方）", "disk" not in run(root, free_gb=10.0)["todo"])
    ok("磁盘不足时仍列出要补的权重", "model:turbo" in run(fake_root({}, dirs=()), free_gb=10.0)["todo"])

    ok("Python 超区间 → 提醒", item(run(root, py_version="3.14.0"), "python")["state"] == "warn")
    ok("解释器不在 .venv → 提醒",
       item(run(root, prefix="C:/Python312"), "venv")["state"] == "warn")

    a = ec.pip_argv(item(run(root, pkg_version=lambda n: None), "pkg:torch"), python="PY")
    ok("pip 命令：torch 走 --index-url",
       a[:3] == ["PY", "-m", "pip"] and "--index-url" in a and "torch==2.11.0" in a, a)
    a = ec.pip_argv(item(run(root, pkg_version=lambda n: None), "pkg:uvicorn"), python="PY")
    ok("pip 命令：普通包走 -i 镜像",
       "-i" in a and any(x.startswith("https://mirrors.aliyun.com") for x in a), a)
    a = ec.pip_argv({"fix": {"kind": "pip", "spec": ec._pip_spec(SPEC["packages"][1])}}, "PY")
    ok("pip 命令：diffusers 钉死 commit 且不带索引",
       any("git+https://github.com/huggingface/diffusers.git@916a5791" in x for x in a)
       and "-i" not in a and "--index-url" not in a, a)

    keys = ["model:turbo", "pkg:torch"]
    got = [x["key"] for x in ec.fix_plan(run(fake_root({}, dirs=()), pkg_version=lambda n: None)["items"], keys)]
    ok("点名补：只出被点的项", set(got) == set(keys), got)
    ok("warn 项不给补", ec.fix_plan([{"state": "warn", "fix": {"kind": "pip"}, "key": "x"}]) == [])

    spec = ec.load_spec(ROOT)
    ok("真 env.json 解析通过", isinstance(spec["packages"], list) and spec["models"],
       "%d 个包 · %d 个模型" % (len(spec["packages"]), len(spec["models"])))
    real = ec.check(ROOT)
    ok("真机体检跑得通且无假告警（本机权重齐全）",
       item(real, "model:turbo")["state"] == "ok", item(real, "model:turbo")["detail"])
    # 体检看的是「当前解释器」里装了什么：用 .venv 的 python 跑才该全绿，
    # 用系统 python 跑就是真话（.venv 的包它一个也看不见）
    in_venv = ec._in_venv(sys.prefix, ROOT)
    if in_venv:
        ok("真机（.venv）清单里 torch 达标", item(real, "pkg:torch")["state"] == "ok",
           item(real, "pkg:torch")["detail"])
        ok("真机（.venv）不给「不在 venv」提醒",
           item(real, "venv")["state"] == "ok", item(real, "venv")["detail"])
    else:
        ok("非 .venv 解释器给出提醒", item(real, "venv")["state"] == "warn",
           item(real, "venv")["detail"])
        ok("非 .venv 解释器如实报告 torch 没装",
           item(real, "pkg:torch")["state"] == "miss", item(real, "pkg:torch")["detail"])
    try:
        ec.load_spec(os.path.join(ROOT, "nope"))
        ok("清单读不到要报错", False)
    except ec.SpecError as e:
        ok("清单读不到要报错", True, e)

    # 壳上的三道门：打包版 / 正在补 / 没得补 —— 都不该真去装东西
    from app import App

    a = App()
    ok("env_check 通", a.env_check()["ok"] is True)
    sys.frozen = True
    try:
        r = a.env_fix(None)
        ok("打包版拒绝改环境（并给出源码那条路）",
           not r["ok"] and "打包版" in r["msg"], r)
    finally:
        del sys.frozen
    a.st["env_busy"] = True
    try:
        r = a.env_fix(None)
        ok("补全在跑时不重复起", not r["ok"] and "还在跑" in r["msg"], r)
    finally:
        a.st["env_busy"] = False
    r = a.env_fix(["no-such-key"])
    ok("没有可补项就返回 0，不动 pip", r["ok"] and r["count"] == 0, r)
    ok("上面这道门没把 env_busy 挂上", a.st["env_busy"] is False)

    # 开机后台体检：概览页那条横幅的数就是它写的（真 import torch，慢十几秒）
    a.st["env_todo"] = None
    a.env_probe_bg()
    t0 = time.time()
    while a.st["env_todo"] is None and time.time() - t0 < 180:
        time.sleep(1)
    ok("后台体检把待补数写进状态", isinstance(a.st["env_todo"], int),
       "%s 项 · 等了 %.0fs" % (a.st["env_todo"], time.time() - t0))
    tail = " ".join(x[2] for x in a._logs[-6:])
    ok("体检结论进了日志（人不用点进环境页也知道差什么）", "环境体检" in tail, tail[-60:])

    import shutil

    shutil.rmtree(root, ignore_errors=True)
    bad_n = RESULTS.count(False)
    print("\nENV TEST %s（%d 项）" % ("PASS" if not bad_n else "FAIL " + str(bad_n), len(RESULTS)))
    return 1 if bad_n else 0


if __name__ == "__main__":
    sys.exit(main())
