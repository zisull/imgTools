# -*- coding: utf-8 -*-
"""check.py —— 按 envs/ 清单体检运行环境，并给出「缺什么、怎么补」
====================================================================
存在的意义：换电脑时只有代码是跟着 git 走的，`.venv/` 和几十 GB 的权重都不进版本库。
所以「跑起来需要什么」写成按环境拆开的清单（envs/index.json + envs/<id>/env.json），
由这里逐项核对，壳上的「环境」页据此按环境分区提供一键补齐。

三条口径：
  · 检测是纯函数 + 可注入探针（单测不装包、不碰真权重）
  · 状态分四种：ok / miss（压根没有）/ part（有但不对，能修）/ warn（修不了或只能提醒）
  · 文案要区分根因：torch「没装」和「装成了 CPU 版」是两回事，别写成同一句「环境异常」
"""
import json
import os
import re
import shutil
import sys

_WEBUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WEBUI not in sys.path:
    sys.path.insert(0, _WEBUI)

from envkit import spec as sp          # noqa: E402

# 分组名（前端按这个顺序显示）
G_PY = "运行环境"
G_PKG = "依赖包"
G_MODEL = "模型权重"
G_RUNTIME = "ComfyUI 运行时"
G_TOOL = "扩展工具"
G_DIR = "目录"
G_MOSS = G_RUNTIME                      # 旧名字，别处还在用


# ---------------------------------------------------------------- 探针（可注入）
def _pkg_version(name):
    """返回已装版本字符串，没装返回 None。"""
    import importlib.metadata as md

    try:
        return md.version(name)
    except Exception:
        return None


def _site_packages(python_exe):
    """从解释器路径推它的 site-packages：venv 建在 <根>/Scripts（Win）或 <根>/bin。"""
    import glob

    root = os.path.dirname(os.path.dirname(os.path.abspath(python_exe)))
    for pat in (os.path.join(root, "Lib", "site-packages"),
                os.path.join(root, "lib", "python*", "site-packages")):
        hit = sorted(glob.glob(pat))
        if hit:
            return hit[0]
    return ""


def torch_flavor(python_exe):
    """这个解释器里的 torch 装没装、是不是 CUDA 轮子——**故意不 import torch**。

    CPU 轮子的 site-packages/torch/version.py 里写的是 `cuda = None`，读文本就够判；
    而 import 一次 torch 要十几秒，环境体检不能为它付这个钱（体检是点一下就要出结果的）。
    """
    out = {"installed": False, "version": "", "cuda": ""}
    vf = os.path.join(_site_packages(python_exe), "torch", "version.py") if python_exe else ""
    try:
        with open(vf, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except OSError:
        return out
    ver = re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", txt, re.M)
    cud = re.search(r"^cuda\b[^=\n]*=\s*['\"]([^'\"]+)['\"]", txt, re.M)
    out["installed"] = True
    out["version"] = ver.group(1) if ver else ""
    out["cuda"] = cud.group(1) if cud else ""      # 空串 = CPU 轮子（Windows 上 PyPI 默认就是它）
    return out


_GPU_OK = None


def _has_gpu():
    """机器上有没有一块能用的 N 卡——用 nvidia-smi 问（实测 60ms，且等子进程时放开 GIL），
    不为这个 import torch。结果按进程缓存：显卡不会在运行中途凭空出现。"""
    global _GPU_OK
    if _GPU_OK is None:
        _GPU_OK = False
        try:
            import subprocess

            si = None
            if sys.platform == "win32":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW   # 别闪一个黑框出来
            r = subprocess.run(["nvidia-smi", "-L"], capture_output=True,
                               timeout=8, startupinfo=si)
            _GPU_OK = r.returncode == 0 and b"GPU" in (r.stdout or b"")
        except Exception:
            pass
    return _GPU_OK


def _cuda_state():
    """(是否可用, torch 编译时的 CUDA 版本)。torch 本身没装时返回 (None, None)。

    绝不 import torch：warm 机器要 1.5 秒、冷盘十几秒，而且这段时间 GIL 被独占，
    WebView2 的消息泵停在桥调用上——「启动卡界面」就是它。轮子是不是 CUDA 版读
    version.py（见 torch_flavor），有没有卡问 nvidia-smi；torch 已经热了才问它本人。
    """
    fl = torch_flavor(sys.executable)
    if not fl["installed"]:
        return None, None
    built = fl["cuda"]
    if not built:
        return False, ""                      # CPU 轮子：装上了也跑不了 CUDA
    t = sys.modules.get("torch")
    if t is not None:
        try:
            return bool(t.cuda.is_available()), built
        except Exception:
            return False, built
    return _has_gpu(), built


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
def _item(key, group, label, state, detail, fix=None, env=sp.BASE, optional=False, **extra):
    it = {"key": key, "group": group, "label": label, "state": state,
          "env": env, "optional": bool(optional), "detail": detail,
          "fix": fix or {"kind": "none"}}
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
                 d + " · 换解释器请用根目录的 启动.bat 重建 .venv")


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

    try:
        raw = md.distribution(name).read_text("direct_url.json")
        vi = (json.loads(raw or "{}") or {}).get("vcs_info") or {}
        return vi.get("commit_id") or None
    except Exception:
        return None


def _check_pkg(spec, name, have, cuda, gitc=None):
    """一个依赖包：没装=miss，装了但版本/来源不对=part，达标=ok。"""
    want = str(name.get("version") or "")
    minv = str(name.get("min") or want)
    pin = str(name.get("commit") or "")
    optional = bool(name.get("optional"))
    env = str(name.get("env") or sp.BASE)
    label = "%s %s" % (name["name"], pin[:8] if pin else want)
    key = "pkg:" + name["name"]
    idx = (spec.get("indexes") or {}).get(name.get("index") or "")
    fix = {"kind": "pip", "spec": _pip_spec(name), "index": idx or "",
           "index_url": bool(name.get("index") == "torch")}
    if have is None:
        return _item(key, G_PKG, label, "warn" if optional else "miss",
                     "没装" + ("（可选，点名可补）" if optional else ""),
                     fix, env=env)
    if pin:
        # 钉死 commit 的开发版：版本号（0.41.0.dev0）比不出任何东西，只能核对装的是哪个 commit
        got = (gitc or _git_commit)(name["name"])
        if not got:
            return _item(key, G_PKG, label, "warn",
                         "已装 %s，但查不出装的是哪个 commit（清单钉 %s）· "
                         "出图异常时点这项重装" % (have, pin[:8]), fix, env=env)
        if got[:len(pin)] != pin and pin[:len(got)] != got:
            return _item(key, G_PKG, label, "part",
                         "已装 %s，但 commit 是 %s，清单钉的是 %s" % (have, got[:8], pin[:8]),
                         fix, env=env)
        return _item(key, G_PKG, label, "ok", "已装 %s · commit %s" % (have, got[:8]), env=env)
    if not _ver_ge(have, minv):
        return _item(key, G_PKG, label, "part", "已装 %s，要求 ≥%s" % (have, minv), fix, env=env)
    if name.get("cuda"):
        ok_cuda, built = cuda
        if ok_cuda is None:
            return _item(key, G_PKG, label, "part", "已装 %s 但 import 不了" % have, fix, env=env)
        if not ok_cuda:
            return _item(key, G_PKG, label, "part",
                         "已装 %s，但 CUDA 用不了%s——多半是从 PyPI 默认索引装的 CPU 轮子，"
                         "得走 %s 重装" % (have, "（编译时 CUDA=%s）" % built if built else "",
                                          idx or "cu128 索引"), fix, env=env)
    return _item(key, G_PKG, label, "ok", "已装 %s" % have, env=env)


def _pip_spec(pkg):
    if pkg.get("commit"):
        return "git+%s@%s" % (pkg["repo"], pkg["commit"])
    v = pkg.get("version")
    return "%s==%s" % (pkg["name"], v) if v else pkg["name"]


def _model_key(m):
    return "model:" + str(m.get("key") or m.get("dir") or "?")


def _check_model(root, m, env=None, optional=False):
    rel = str(m.get("dir") or "")
    d = sp.model_dir(root, m)
    label = "%s（%s）" % (m.get("label") or rel, m.get("repo") or "")
    allow = sorted((m.get("must") or {}).keys()) or [str(a) for a in (m.get("allow") or [])]
    fix = {"kind": "model", "repo": m.get("repo"), "dir": rel, "allow": allow}
    env = env or m.get("env") or sp.BASE
    if not os.path.isdir(d):
        return _item(_model_key(m), G_MODEL, label, "miss",
                     "目录不存在：%s · 约 %s GB" % (rel, m.get("gb", "?")),
                     fix, env=env, optional=optional, gb=m.get("gb"))
    lost, bad = [], []
    for f, size in (m.get("must") or {}).items():
        p = os.path.join(d, *str(f).split("/"))
        try:
            got = os.path.getsize(p)
        except OSError:
            lost.append(f)
            continue
        if int(size) and got != int(size):
            bad.append("%s（%d / 应 %d）" % (f, got, int(size)))
    if lost or bad:
        bits = []
        if lost:
            bits.append("缺 %d 个文件（%s）" % (len(lost), "、".join(lost[:2])))
        if bad:
            bits.append("%d 个文件字节数不对（%s）" % (len(bad), bad[0]))
        return _item(_model_key(m), G_MODEL, label, "part",
                     "权重不完整：" + "；".join(bits) + " · 续传补齐即可",
                     fix, env=env, optional=optional, gb=m.get("gb"))
    return _item(_model_key(m), G_MODEL, label, "ok",
                 "权重齐全（%d 项校验过）" % len(m.get("must") or {}),
                 fix, env=env, optional=optional, gb=m.get("gb"))


def _abs(root, rel):
    return os.path.join(root, *str(rel).split("/"))


def _comfyui_version(d):
    """读 comfyui_version.py 里的 __version__（纯文本，不 import 它的代码）。"""
    try:
        with open(os.path.join(d, "comfyui_version.py"), "r",
                  encoding="utf-8", errors="replace") as f:
            m = re.search(r"""['"](\d+\.\d+\.\d+)['"]""", f.read())
            return m.group(1) if m else ""
    except OSError:
        return ""


def _check_runtime(root, spec):
    rt = (spec.get("runtimes") or {}).get("comfyui") or {}
    env = str(rt.get("env") or "moss")
    d = sp.runtime_dir(root, spec)
    rel = os.path.relpath(d, root).replace("\\", "/")
    fix = {"kind": "comfyui", "repo": rt.get("repo"), "branch": rt.get("branch"),
           "dir": rel}
    label = "%s（%s）" % (rt.get("label") or "ComfyUI 运行时", rel)
    if os.path.isfile(os.path.join(d, "main.py")):
        # 「main.py 在」不等于「认得 moss_image」：原生支持是 v0.42.0 才进的（PR#17095）。
        # 拿 min_commit 做 git 祖先判断又慢又脆（用户可能不用 git 方式拿代码），
        # 直接看那个节点文件在不在最准——缺它的版本一起步就会在出图时报「未知 class_type」。
        if not os.path.isfile(os.path.join(d, "comfy_extras", "nodes_moss_image.py")):
            return _item("comfy:app", G_RUNTIME, label, "part",
                         "已有 ComfyUI（版本 %s）但不认 moss_image：原生支持要 v0.42+，"
                         "一键补全会拉到 %s" % (_comfyui_version(d) or "未知",
                                                rt.get("branch") or "v0.42.1"), fix, env=env)
        return _item("comfy:app", G_RUNTIME, label, "ok",
                     "main.py 就位 · %s · 含 moss_image 节点" % (
                         _comfyui_version(d) and "v" + _comfyui_version(d)
                         or "版本未知"), env=env)
    return _item("comfy:app", G_RUNTIME, label, "miss",
                 "还没 clone（约 100MB · %s）" % (rt.get("repo") or "Comfy-Org/ComfyUI"),
                 fix, env=env)


def _check_runtime_venv(root, spec):
    rt = (spec.get("runtimes") or {}).get("comfyui") or {}
    env = str(rt.get("env") or "moss")
    d = sp.runtime_dir(root, spec)
    vrel = str(rt.get("venv") or "comfyui/.venv")
    py = _abs(root, os.path.join(vrel, "Scripts" if os.name == "nt" else "bin",
                                 "python.exe" if os.name == "nt" else "python"))
    fix = {"kind": "comfyvenv", "dir": vrel,
           "requirements": rt.get("requirements") or "comfyui/requirements.txt"}
    label = "%s · 独立 venv" % (rt.get("label") or "ComfyUI 运行时")
    if os.path.isfile(py):
        # 「有 python.exe」不等于「能用」：Windows 上按 ComfyUI 的 requirements 直装
        # 会拿到 CPU 版 torch，ComfyUI 一起步就 AssertionError 崩掉——所以这里必须看轮子颜色。
        fl = torch_flavor(py)
        if not fl["installed"]:
            return _item("comfy:venv", G_RUNTIME, label, "part",
                         ".venv 建好了但依赖没装（里面没有 torch）", fix, env=env)
        if not fl["cuda"]:
            return _item("comfy:venv", G_RUNTIME, label, "part",
                         "torch 装成了 CPU 版（%s）：ComfyUI 起不来，点补齐换 CUDA 轮子"
                         % (fl["version"] or "版本未知"), fix, env=env)
        return _item("comfy:venv", G_RUNTIME, label, "ok",
                     ".venv 已建 · torch %s（CUDA %s）" % (fl["version"], fl["cuda"]), env=env)
    if not os.path.isfile(os.path.join(d, "main.py")):
        return _item("comfy:venv", G_RUNTIME, label, "miss",
                     "要先有 ComfyUI 本体才能建它的环境", fix, env=env)
    return _item("comfy:venv", G_RUNTIME, label, "miss",
                 "ComfyUI 已在但没建 .venv（装它自己的 torch/依赖）", fix, env=env)


def _check_tool(root, t, env=None, optional=False):
    """可选扩展工具（ffmpeg 这类）：只看可执行文件在不在，不跑它。

    工具不是模型：缺了不影响出图出片，只影响「多段合成」这种增强功能，
    所以 state=miss 也带 optional，默认不进待补总数，点名了才装。
    """
    env = env or t.get("env") or sp.BASE
    dest = str(t.get("dest") or ("envs/%s" % env))
    names = [str(x) for x in (t.get("files") or [])]
    base = _abs(root, dest)
    have = [n for n in names if os.path.isfile(os.path.join(base, *n.split("/")))]
    fix = {"kind": "tool", "key": str(t.get("key") or ""), "dest": dest,
           "files": names, "urls": list(t.get("urls") or [])}
    label = str(t.get("label") or t.get("key") or "扩展工具")
    mb = t.get("size_mb")
    size = "约 %s MB" % mb if mb else ""
    if names and len(have) == len(names):
        return _item("tool:" + str(t.get("key") or env), G_TOOL, label, "ok",
                     "已装 · %s" % dest, fix, env=env, optional=optional)
    if have:
        return _item("tool:" + str(t.get("key") or env), G_TOOL, label, "part",
                     "只装到 %d/%d 个文件（%s）· 重装一次补齐" % (len(have), len(names), dest),
                     fix, env=env, optional=optional)
    return _item("tool:" + str(t.get("key") or env), G_TOOL, label, "miss",
                 "没装%s · %s" % (("（%s）" % size) if size else "",
                                 t.get("note") or "点这项补上"),
                 fix, env=env, optional=optional)


def _check_dir(root, d):
    p = _abs(root, d["path"])
    env = str(d.get("env") or sp.BASE)
    fix = {"kind": "dir", "path": d["path"]}
    if os.path.isdir(p):
        try:
            probe = os.path.join(p, ".qic_write")
            with open(probe, "w") as f:
                f.write("x")
            os.remove(probe)
        except OSError as e:
            return _item("dir:" + d["path"], G_DIR, d["path"] + "/", "warn",
                         "目录在但写不进去：%s" % e, fix, env=env)
        return _item("dir:" + d["path"], G_DIR, d["path"] + "/", "ok", "可写", fix, env=env)
    return _item("dir:" + d["path"], G_DIR, d["path"] + "/", "miss",
                 "还没有这个目录（%s）" % (d.get("note") or ""), fix, env=env)


def _check_disk(root, spec, free_gb, need=None):
    """磁盘只算「这次真要装的」：已在盘上的权重不重复占额度，可选环境没装也不占。

    need 传 None 时按清单总额估算（给不跑完整体检的场景兜底）。
    """
    if need is None:
        installed = {e["id"] for e in spec.get("envs") or []
                     if sp.env_installed(root, spec, e["id"])}
        need = 0.0
        for m in spec.get("models") or []:
            env = m.get("env") or sp.BASE
            meta = sp.env_meta(spec, env)
            if meta.get("optional") and env not in installed:
                continue
            need += float(m.get("gb") or 0)
    f = float(free_gb or 0)
    if f >= need * 1.15:
        return _item("disk", G_PY, "磁盘空间", "ok",
                     "本盘剩余 %.1f GB（待补权重约 %.1f GB）" % (f, need))
    return _item("disk", G_PY, "磁盘空间", "warn",
                 "剩余 %.1f GB，装不下约 %.1f GB 的权重 · 先腾地方再补全" % (f, need))


# ---------------------------------------------------------------- 主入口
def check(root, spec=None, py_version=None, prefix=None, pkg_version=None,
          cuda=None, free_gb=None, git_commit=None):
    """体检一遍。所有探针都能注入，单测据此造「假机器」。"""
    spec = spec or sp.load_spec(root)
    pv = pkg_version or _pkg_version
    cu = cuda() if callable(cuda) else (cuda or _cuda_state())
    if free_gb is None:
        try:
            free_gb = shutil.disk_usage(root).free / 2 ** 30
        except OSError:
            free_gb = 0.0
    opt = {e["id"] for e in spec.get("envs") or [] if e.get("optional")}
    installed = {e["id"] for e in spec.get("envs") or []
                 if sp.env_installed(root, spec, e["id"])}
    items = [
        _check_python(root, spec, py_version),
        _check_venv(root, prefix or sys.prefix),
    ]
    for pkg in spec.get("packages") or []:
        items.append(_check_pkg(spec, pkg, pv(pkg["name"]), cu, gitc=git_commit))
    for m in spec.get("models") or []:
        env = m.get("env") or sp.BASE
        items.append(_check_model(root, m, env=env, optional=env in opt))
    for t in spec.get("tools") or []:
        env = t.get("env") or sp.BASE
        items.append(_check_tool(root, t, env=env, optional=env in opt))
    if spec.get("runtimes"):
        env = str(((spec.get("runtimes") or {}).get("comfyui") or {}).get("env") or "moss")
        items.append(_check_runtime(root, spec))
        items.append(_check_runtime_venv(root, spec))
        for it in items:
            if it["key"].startswith("comfy:"):
                it["optional"] = env in opt
    for d in spec.get("dirs") or []:
        items.append(_check_dir(root, d))
    # 磁盘额度只看「还没在盘上的」：已装的权重不重复占，没装的 H3 也不占
    need = 0.0
    for it in items:
        if it["group"] != G_MODEL or it["state"] == "ok":
            continue
        if it.get("optional") and it["env"] not in installed:
            continue
        need += float(it.get("gb") or 0)
    items.insert(2, _check_disk(root, spec, free_gb, need))
    todo = fix_plan(items)
    return {"ok": True, "items": items, "todo": [x["key"] for x in todo],
            "gb": round(sum(float(x.get("gb") or 0) for x in todo), 1),
            "envs": sp.envs_meta(spec), "spec": spec.get("spec") or sp.INDEX}


def fix_plan(items, keys=None, include_optional=False):
    """挑出「能自动补」的条目。

    keys=None 表示「全部该补的」，默认跳过可选环境（H3 这类）——
    不想要视频功能的人不该一直被提示「还差 41 GB」。
    """
    want = None if keys is None else set(keys)
    out = []
    for it in items:
        named = want is not None and it["key"] in want
        if it["state"] not in ("miss", "part"):
            # 可选包没装只是 warn：一键补齐/分区补齐不碰它，点名了才装
            if not (named and it["state"] == "warn"):
                continue
        if it["fix"]["kind"] == "none":
            continue
        if want is not None:
            if not named:
                continue
        elif it.get("optional") and not include_optional:
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


if __name__ == "__main__":  # 命令行体检：python webui/envkit/check.py [root]
    root = os.path.dirname(_WEBUI)
    if len(sys.argv) > 1:
        root = os.path.abspath(sys.argv[1])
    r = check(root)
    for it in r["items"]:
        print("%-5s %-6s %-8s %-34s %s"
              % (it["state"].upper(), it["env"], it["group"], it["label"], it["detail"]))
    print("\n可自动补齐 %d 项：%s" % (len(r["todo"]), "、".join(r["todo"]) or "无"))
