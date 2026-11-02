# -*- coding: utf-8 -*-
"""envkit 体检回归：造一台「假机器」逐项体检，不装包、不碰真权重、不联网。

跑法： .venv\\Scripts\\python.exe scripts\\env_test.py
"""
import atexit
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))

from envkit import check as ec  # noqa: E402
from envkit import spec as sp  # noqa: E402

# 下面 `App()` 一构造就把换代后的导航写回 config.json——那是用户那一份。
# 十八轮给 task/api/drop 三个测试各配了临时 config，env_test 是漏掉的那个（本轮实测抓到它把
# 用户 config.json 改了）：这里同样在 import app 之前把 QIC_CONFIG 指到临时目录。
_CFG_DIR = tempfile.mkdtemp(prefix="qic_env_cfg_")
os.environ["QIC_CONFIG"] = os.path.join(_CFG_DIR, "config.json")
atexit.register(shutil.rmtree, _CFG_DIR, True)

RESULTS = []
_FAKE_ROOTS = []


@atexit.register
def _sweep():
    """假仓库根留在 TEMP 里就是垃圾：断言失败提前退出也得带走。"""
    for d in _FAKE_ROOTS:
        shutil.rmtree(d, ignore_errors=True)


def ok(name, cond, extra=""):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ((" · " + str(extra)) if extra else ""))


SPEC = {
    "python": {"min": "3.11", "max": "3.13", "best": "3.12"},
    "indexes": {"pypi": "https://mirrors.aliyun.com/pypi/simple/",
                "torch": "https://download.pytorch.org/whl/cu128"},
    "envs": [{"id": "qwen", "label": "千问", "icon": "flower", "engine": "qwen",
              "optional": False, "title": "千问环境", "desc": "",
              "models_dir": "qwen/models"}],
    "runtimes": {},
    "packages": [
        {"name": "torch", "version": "2.11.0", "index": "torch", "cuda": True},
        {"name": "diffusers", "commit": "916a5791ed5f29d966200d2eee53f06862ec4434",
         "repo": "https://github.com/huggingface/diffusers.git"},
        {"name": "uvicorn", "version": "0.54.0", "index": "pypi", "optional": True},
    ],
    "models": [{"key": "turbo", "label": "T", "repo": "o/turbo",
                "dir": "envs/qwen/models/turbo", "env": "qwen", "gb": 30.3,
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
    tmp = tempfile.mkdtemp(prefix="qic_env_")
    _FAKE_ROOTS.append(tmp)
    for rel, size in files.items():
        p = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b"\0" * size)
    for d in dirs:
        os.makedirs(os.path.join(tmp, d), exist_ok=True)
    return tmp


FULL = {"envs/qwen/models/turbo/model_index.json": 10,
        "envs/qwen/models/turbo/transformer/a.safetensors": 20}


def main():
    root = fake_root(FULL)

    r = run(root)
    ok("假机器全齐：可补 0 项", r["todo"] == [], r["todo"])
    ok("分组齐全（运行环境/依赖包/模型权重/目录）",
       {x["group"] for x in r["items"]} == {ec.G_PY, ec.G_PKG, ec.G_MODEL, ec.G_DIR})
    ok("每项都带 fix 结构", all("fix" in x and "kind" in x["fix"] for x in r["items"]))
    ok("模型项带环境归属", item(r, "model:turbo")["env"] == "qwen")
    ok("环境注册表进体检结果", [e["id"] for e in r["envs"]] == ["base", "qwen"],
       [e["id"] for e in r["envs"]])

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
    ok("点名仍可补可选包",
       [x["key"] for x in ec.fix_plan(r["items"], ["pkg:uvicorn"])] == ["pkg:uvicorn"])

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
    bad["envs/qwen/models/turbo/transformer/a.safetensors"] = 19
    t = item(run(fake_root(bad)), "model:turbo")
    ok("分片字节数不对 → 待补且点名文件",
       t["state"] == "part" and "a.safetensors" in t["detail"], t["detail"])

    # 磁盘额度只算「还没在盘上的」：全都装好时剩余再少也不该报缺
    t = item(run(root, free_gb=10.0), "disk")
    ok("权重齐了就不拿「总容量」吓人", t["state"] == "ok", t["detail"])
    t = item(run(fake_root({}, dirs=()), free_gb=10.0), "disk")
    ok("缺 30.3 GB 而只剩 10 GB → 提醒", t["state"] == "warn", t["detail"])
    ok("磁盘不够不进待补（补全解决不了腾地方）",
       "disk" not in run(fake_root({}, dirs=()), free_gb=10.0)["todo"])
    ok("磁盘不足时仍列出要补的权重",
       "model:turbo" in run(fake_root({}, dirs=()), free_gb=10.0)["todo"])

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
    opt = {"key": "model:h3", "state": "miss", "optional": True, "env": "h3",
           "fix": {"kind": "model"}}
    ok("可选环境默认不进待补", ec.fix_plan([dict(opt)]) == [])
    ok("点名补可选环境", len(ec.fix_plan([dict(opt)], ["model:h3"])) == 1)

    spec = sp.load_spec(ROOT)
    ok("真 envs/index.json 解析通过", isinstance(spec["packages"], list) and spec["models"],
       "%d 个包 · %d 个模型 · %d 个环境"
       % (len(spec["packages"]), len(spec["models"]), len(spec["envs"])))
    ok("三个环境都在注册表里（qwen/moss/h3）",
       [e["id"] for e in spec["envs"]] == ["qwen", "moss", "h3"],
       [e["id"] for e in spec["envs"]])
    real = ec.check(ROOT, spec=spec)
    moss_it = item(real, "model:moss-comfy")
    ok("Moss 权重按 envs/moss/models 找到", moss_it["state"] == "ok", moss_it["detail"])
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
        sp.load_spec(os.path.join(ROOT, "nope"))
        ok("清单读不到要报错", False)
    except sp.SpecError as e:
        ok("清单读不到要报错", True, e)

    # 壳上的三道门：打包版 / 正在补 / 没得补 —— 都不该真去装东西
    # 这一段要真起 webview 壳，只能在装了依赖的 .venv 里跑；无显示/无 webview 的
    # 纯体检自测就跳过它，前面的 env_check 断言不受影响。
    try:
        from app import App
    except BaseException as e:
        # app.py 起不来会 raise SystemExit（不是 Exception），这里一并兜住：
        # 无 webview/无显示的自测环境跳过壳上的门，前面的 env_check 断言照常计分。
        print("SKIP 壳上三道门（起不了 webview：%r）—— 无显示环境属正常" % (e,))
        shutil.rmtree(root, ignore_errors=True)
        return _finish()

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

    # 开机后台体检：环境页那条「还差 N 项」的数就是它写的
    # （体检不 import torch，一百多毫秒出数——桥线程不会被它冻住，见十九轮）
    a.st["env_todo"] = None
    a.env_probe_bg()
    t0 = time.time()
    while a.st["env_todo"] is None and time.time() - t0 < 180:
        time.sleep(1)
    ok("后台体检把待补数写进状态", isinstance(a.st["env_todo"], int),
       "%s 项 · 等了 %.0fs" % (a.st["env_todo"], time.time() - t0))
    by = a.st["env_todo_by"] or {}
    ok("待补数按环境拆一份（每页只说自己那一差几项）",
       set(by) >= {"base", "qwen", "moss", "h3"} and a.st["env_todo"] == sum(by.values()),
       "合计 %s = %s" % (a.st["env_todo"], by))
    ok("体检全程没把 torch 拉进来", "torch" not in sys.modules)
    tail = " ".join(x[2] for x in a._logs[-6:])
    ok("体检结论进了日志（人不用点进环境页也知道差什么）", "环境体检" in tail, tail[-60:])

    # 开关就是用户反馈的那件事：「关掉还在提醒千问缺模型」必须从此不成立。
    # 关掉 = 这一路的体检项根本不出现（待补数、横幅、功能页都从这一份 items 派生）。
    before = len(a.env_check()["items"])
    r = a.env_set("qwen", False)
    ok("开关落盘并回最新一张表", r["ok"] and r["env_on"]["qwen"] is False, r.get("env_on"))
    left = a.env_check()
    ok("关掉的那路一项都不检（不是只在界面上藏起来）",
       all(str(x.get("env") or "base") != "qwen" for x in left["items"])
       and len(left["items"]) < before,
       "%d → %d 项" % (before, len(left["items"])))
    ok("关掉的那路待补数归零", a.st["env_todo_by"]["qwen"] == 0, a.st["env_todo_by"])
    ok("关着的环境不许悄悄落进配置", a.cfg["env_on"]["qwen"] is False)
    g = a._engine_gate("qwen")
    ok("关着的引擎点开始要给一句话（不是默默失败）", bool(g) and "环境已关闭" in g, g)
    ok("基础那一路不给关（壳自己得活着）", a.env_set("base", False)["ok"] is False)
    ok("没有这个环境就拒绝", a.env_set("nope", True)["ok"] is False)
    a.env_set("qwen", True)
    ok("重新开启后体检项回来了",
       any(str(x.get("env") or "base") == "qwen" for x in a.env_check()["items"]))

    # 首启（盘上还没有 config.json）：开关表也得是齐全的。
    # 早退一步就够呛——空表在体检里按「没写＝开」数待补、在拆给各环境那一格
    # 按「没写＝关」归零，界面那句「还差几项」永远不亮，更要命的是新机器一上来
    # 就被判「千问环境已关闭」，连开始按钮都按不动。
    import app as webapp
    tmp_cfg_dir = tempfile.mkdtemp(prefix="moss_first_")
    old_cfg_path = webapp.CFG_PATH
    try:
        webapp.CFG_PATH = os.path.join(tmp_cfg_dir, "config.json")
        fresh = App()
        ok("首启就把每个环境都落成明确的开/关",
           set(fresh.cfg["env_on"]) >= {"qwen", "moss", "h3"}, fresh.cfg["env_on"])
        f_by = fresh.st["env_todo_by"] or {}
        fresh.env_check()
        f_by = fresh.st["env_todo_by"] or {}
        ok("首启的合计与按环境拆的那格自洽",
           fresh.st["env_todo"] == sum(f_by.values()) and set(f_by) >= {"qwen", "moss", "h3"},
           "合计 %s = %s" % (fresh.st["env_todo"], f_by))
        ok("首启不拦千问的开始（关着才拦）", fresh._engine_gate("qwen") == "",
           fresh._engine_gate("qwen"))
    finally:
        webapp.CFG_PATH = old_cfg_path
        shutil.rmtree(tmp_cfg_dir, ignore_errors=True)

    # 老配置换代：console_mode 推一遍 env_on，顺手把欢迎页放回来问一次
    # （老 welcomed 早就为真，不重置的话新的一屏三颗开关永远看不到）
    tmp_mig = tempfile.mkdtemp(prefix="moss_migrate_")
    old_cfg = webapp.CFG_PATH
    try:
        mig = os.path.join(tmp_mig, "config.json")
        with open(mig, "w", encoding="utf-8") as f:
            json.dump({"console_mode": "moss", "welcomed": True,
                       "nav_ver": webapp.NAV_VER}, f)
        webapp.CFG_PATH = mig
        old = App()
        ok("老配置按 console_mode 推出开关表（仅 Moss＝千问关）",
           old.cfg["env_on"].get("qwen") is False and old.cfg["env_on"].get("moss") is True,
           old.cfg["env_on"])
        ok("开关表换代时欢迎页放回来问一次", old.cfg["welcomed"] is False, old.cfg["welcomed"])
        old.cfg["welcomed"] = True
        old._save_cfg()
        ok("答过之后不再重置（env_on 已在盘上就不再算换代）",
           App().cfg["welcomed"] is True)
    finally:
        webapp.CFG_PATH = old_cfg
        shutil.rmtree(tmp_mig, ignore_errors=True)

    shutil.rmtree(root, ignore_errors=True)
    return _finish()


def _finish():
    bad_n = RESULTS.count(False)
    print("\nENV TEST %s（%d 项）" % ("PASS" if not bad_n else "FAIL " + str(bad_n), len(RESULTS)))
    return 1 if bad_n else 0


if __name__ == "__main__":
    sys.exit(main())
