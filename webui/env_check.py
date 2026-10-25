# -*- coding: utf-8 -*-
"""
env_check.py —— 按 env.json 清单体检运行环境，并给出「缺什么、怎么补」
====================================================================
存在的意义：换电脑时只有代码是跟着 git 走的，`.venv/` 和 30GB 的 `models/` 都不进版本库。
所以「跑起来需要什么」必须写成一份机器可读的清单（ROOT/env.json），由这里逐项核对，
壳上的「环境与模型」页据此提供一键补齐。

三条口径：
  · 检测是纯函数 + 可注入探针（单测不装包、不碰真权重）
  · 状态分四种：ok / miss（压根没有）/ part（有但不对，能修）/ warn（修不了或只能提醒）
  · 文案要区分根因：torch「没装」和「装成了 CPU 版」是两回事，别写成同一句「环境异常」
"""
import json
import os
import shutil
import sys

SPEC_FILE = "env.json"

# 分组名（前端按这个顺序显示）
G_PY = "运行环境"
G_PKG = "依赖包"
G_MODEL = "模型权重"
G_DIR = "目录"


class SpecError(Exception):
    """env.json 读不了或不成形。"""


def load_spec(root):
    p = os.path.join(root, SPEC_FILE)
    try:
        with open(p, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except OSError as e:
        raise SpecError("读不到 %s：%s" % (p, e))
    except ValueError as e:
        raise SpecError("%s 不是合法 JSON：%s" % (SPEC_FILE, e))
    if not isinstance(spec.get("packages"), list) or not isinstance(spec.get("models"), list):
        raise SpecError("%s 缺 packages 或 models 段" % SPEC_FILE)
    return spec


# ---------------------------------------------------------------- 探针（可注入）
def _pkg_version(name):
    """返回已装版本字符串，没装返回 None。"""
    import importlib.metadata as md

    try:
        return md.version(name)
    except Exception:
        return None


def _cuda_state():
    """(是否可用, torch 编译时的 CUDA 版本)。torch 本身没装时返回 (None, None)。"""
    try:
        import torch
    except Exception:
        return None, None
    try:
        return bool(torch.cuda.is_available()), (torch.version.cuda or "")
    except Exception:
        return False, ""


def _v(name):
    """把 '2.11.0+cu128' 拆成可比较的 (2,11,0)；非数字尾巴忽略。"""
    out = []
    for part in str(name or "").replace("+", ".").split("."):
        if part.isdigit():
            out.append(int(part))
        else:
            break
    return tuple(out)


def _ver_ge(have, want):
    h, w = _v(have), _v(want)
    return bool(h) and bool(w) and h >= w


# ---------------------------------------------------------------- 单项检测
def _item(key, group, label, state, detail, fix=None, **extra):
    it = {"key": key, "group": group, "label": label, "state": state,
          "detail": detail, "fix": fix or {"kind": "none"}}
    it.update(extra)
    return it


def _check_python(root, spec, py_version):
    want = spec.get("python") or {}
    lo, hi, best = want.get("min"), want.get("max"), want.get("best") or want.get("min")
    cur = py_version or "%d.%d.%d" % sys.version_info[:3]
    cv = _v(cur)
    if not cv:
        return _item("python", G_PY, "Python 解释器", "warn", "版本号读不出来：%s" % cur)
    if lo and cv < _v(lo):
        st, d = "warn", "当前 %s，低于要求的 %s" % (cur, lo)
    elif hi and cv > _v(hi):
        st, d = "warn", "当前 %s，超出验证过的 %s（%s 实测可用）" % (cur, hi, best)
    else:
        st, d = "ok", "当前 %s（要求 %s~%s）" % (cur, lo or "-", hi or "-")
    return _item("python", G_PY, "Python 解释器", st,
                 d + " · 换解释器请用 setup.bat 建 .venv")


def _in_venv(prefix, root):
    venv = os.path.normpath(os.path.join(root, ".venv"))
    pre = os.path.normpath(prefix or "")
    return pre.lower().startswith(venv.lower() + os.sep) or pre.lower() == venv.lower()


def _check_venv(root, prefix):
    if _in_venv(prefix, root):
        return _item("venv", G_PY, "虚拟环境", "ok", "用的就是本目录 .venv")
    return _item("venv", G_PY, "虚拟环境", "warn",
                 "当前解释器不在本目录 .venv 里（%s）· 用 启动.bat 或 .venv\\Scripts\\pythonw.exe 起"
                 % os.path.normpath(prefix or ""))


def _git_commit(name):
    """装包时记录的 git commit（pip 从 git+URL 装才会有）；查不到返回 None。"""
    import importlib.metadata as md
    import json as _json

    try:
        raw = md.distribution(name).read_text("direct_url.json")
        vi = (_json.loads(raw or "{}") or {}).get("vcs_info") or {}
        return vi.get("commit_id") or None
    except Exception:
        return None


def _check_pkg(spec, name, have, cuda, gitc=None):
    """一个依赖包：没装=miss，装了但版本/来源不对=part，达标=ok。"""
    want = str(name.get("version") or "")
    minv = str(name.get("min") or want)
    pin = str(name.get("commit") or "")
    optional = bool(name.get("optional"))
    label = "%s %s" % (name["name"], pin[:8] if pin else want)
    key = "pkg:" + name["name"]
    idx = (spec.get("indexes") or {}).get(name.get("index") or "")
    fix = {"kind": "pip", "spec": _pip_spec(name), "index": idx or "",
           "index_url": bool(name.get("index") == "torch")}
    if have is None:
        return _item(key, G_PKG, label, "warn" if optional else "miss",
                     "没装" + ("（可选，只影响 API 服务页）" if optional else ""), fix)
    if pin:
        # 钉死 commit 的开发版：版本号（0.41.0.dev0）比不出任何东西，只能核对装的是哪个 commit
        got = (gitc or _git_commit)(name["name"])
        if not got:
            return _item(key, G_PKG, label, "warn",
                         "已装 %s，但查不出装的是哪个 commit（清单钉 %s）· "
                         "出图异常时点这项重装" % (have, pin[:8]), fix)
        if got[:len(pin)] != pin and pin[:len(got)] != got:
            return _item(key, G_PKG, label, "part",
                         "已装 %s，但 commit 是 %s，清单钉的是 %s" % (have, got[:8], pin[:8]), fix)
        return _item(key, G_PKG, label, "ok", "已装 %s · commit %s" % (have, got[:8]))
    if not _ver_ge(have, minv):
        return _item(key, G_PKG, label, "part", "已装 %s，要求 ≥%s" % (have, minv), fix)
    if name.get("cuda"):
        ok_cuda, built = cuda
        if ok_cuda is None:
            return _item(key, G_PKG, label, "part", "已装 %s 但 import 不了" % have, fix)
        if not ok_cuda:
            return _item(key, G_PKG, label, "part",
                         "已装 %s，但 CUDA 用不了%s——多半是从 PyPI 默认索引装的 CPU 轮子，"
                         "得走 %s 重装" % (have, "（编译时 CUDA=%s）" % built if built else "",
                                          idx or "cu128 索引"), fix)
    return _item(key, G_PKG, label, "ok", "已装 %s" % have)


def _pip_spec(pkg):
    if pkg.get("commit"):
        return "git+%s@%s" % (pkg["repo"], pkg["commit"])
    v = pkg.get("version")
    return "%s==%s" % (pkg["name"], v) if v else pkg["name"]


def _check_model(root, m):
    rel = str(m.get("dir") or "")
    d = os.path.join(root, *rel.split("/"))
    label = "%s（%s）" % (m.get("label") or rel, m.get("repo") or "")
    fix = {"kind": "model", "repo": m.get("repo"), "name": os.path.basename(rel.rstrip("/"))}
    if not os.path.isdir(d):
        return _item("model:" + str(m.get("key") or rel), G_MODEL, label, "miss",
                     "目录不存在：%s · 约 %s GB" % (rel, m.get("gb", "?")), fix, gb=m.get("gb"))
    bad, lost = [], []
    for f, size in (m.get("must") or {}).items():
        p = os.path.join(d, *f.split("/"))
        try:
            got = os.path.getsize(p)
        except OSError:
            lost.append(f)
            continue
        if int(size) and got != int(size):
            bad.append("%s（%d / 应 %d 字节）" % (f, got, int(size)))
    if lost or bad:
        bits = []
        if lost:
            bits.append("缺 %d 个文件（%s）" % (len(lost), "、".join(lost[:2])))
        if bad:
            bits.append("%d 个文件字节数不对（%s）" % (len(bad), bad[0]))
        return _item("model:" + str(m.get("key") or rel), G_MODEL, label, "part",
                     "权重不完整：" + "；".join(bits) + " · 续传补齐即可", fix)
    return _item("model:" + str(m.get("key") or rel), G_MODEL, label, "ok",
                 "文件齐全（%d 项校验过）" % len(m.get("must") or {}), fix)


def _check_dir(root, d):
    p = os.path.join(root, *str(d["path"]).split("/"))
    fix = {"kind": "dir", "path": d["path"]}
    if os.path.isdir(p):
        try:
            with open(os.path.join(p, ".qic_write"), "w") as f:
                f.write("x")
            os.remove(os.path.join(p, ".qic_write"))
        except OSError as e:
            return _item("dir:" + d["path"], G_DIR, d["path"] + "/", "warn",
                         "目录在但写不进去：%s" % e, fix)
        return _item("dir:" + d["path"], G_DIR, d["path"] + "/", "ok", "可写", fix)
    return _item("dir:" + d["path"], G_DIR, d["path"] + "/", "miss",
                 "还没有这个目录（%s）" % (d.get("note") or ""), fix)


def _check_disk(root, spec, free_gb):
    need = sum(float(m.get("gb") or 0) for m in spec.get("models") or [])
    f = float(free_gb or 0)
    if f >= need * 1.15:
        return _item("disk", G_PY, "磁盘空间", "ok", "本盘剩余 %.1f GB（权重共约 %.1f GB）" % (f, need))
    return _item("disk", G_PY, "磁盘空间", "warn",
                 "剩余 %.1f GB，装不下约 %.1f GB 的权重 · 先腾地方再补全" % (f, need))


# ---------------------------------------------------------------- 主入口
def check(root, spec=None, py_version=None, prefix=None, pkg_version=None,
          cuda=None, free_gb=None, git_commit=None):
    """体检一遍。所有探针都能注入，单测据此造「假机器」。"""
    spec = spec or load_spec(root)
    pv = pkg_version or _pkg_version
    cu = cuda() if callable(cuda) else (cuda or _cuda_state())
    if free_gb is None:
        try:
            free_gb = shutil.disk_usage(root).free / 2 ** 30
        except OSError:
            free_gb = 0.0
    items = [
        _check_python(root, spec, py_version),
        _check_venv(root, prefix or sys.prefix),
        _check_disk(root, spec, free_gb),
    ]
    for pkg in spec.get("packages") or []:
        items.append(_check_pkg(spec, pkg, pv(pkg["name"]), cu, gitc=git_commit))
    for m in spec.get("models") or []:
        items.append(_check_model(root, m))
    for d in spec.get("dirs") or []:
        items.append(_check_dir(root, d))
    todo = fix_plan(items)
    return {"ok": True, "items": items, "todo": [x["key"] for x in todo],
            "gb": round(sum(float(x.get("gb") or 0) for x in todo), 1),
            "spec": SPEC_FILE}


def fix_plan(items, keys=None):
    """挑出「能自动补」的条目；keys=None 表示全部。"""
    want = None if keys is None else set(keys)
    out = []
    for it in items:
        if it["state"] not in ("miss", "part"):
            continue
        if it["fix"]["kind"] == "none":
            continue
        if want is not None and it["key"] not in want:
            continue
        out.append(it)
    return out


def pip_argv(item, python=None):
    """把一条 pip 修复动作拼成命令行（index 与 --index-url 语义不同，不能混用）。"""
    fx = item["fix"]
    argv = [python or sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
            "--no-input", fx["spec"]]
    if fx.get("index"):
        argv += ["--index-url" if fx.get("index_url") else "-i", fx["index"]]
    return argv


if __name__ == "__main__":  # 命令行体检：python webui/env_check.py [root]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if len(sys.argv) > 1:
        root = os.path.abspath(sys.argv[1])
    r = check(root)
    for it in r["items"]:
        print("%-5s %-6s %-34s %s" % (it["state"].upper(), it["group"], it["label"], it["detail"]))
    print("\n可自动补齐 %d 项：%s" % (len(r["todo"]), "、".join(r["todo"]) or "无"))
