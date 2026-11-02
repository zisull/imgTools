# -*- coding: utf-8 -*-
"""setup_all.py —— 唯一的启动入口：缺什么补什么，补完直接开界面
================================================================
双击根目录的 启动.bat 就会走到这里（它只负责建 .venv）。
本脚本按 envs/ 清单体检，按顺序补：目录 → 界面壳 → 依赖包 → ComfyUI 代码 →
ComfyUI 独立环境 → 各环境权重 → 复检，最后拉起界面。

进度：每一步有编号；下载显示百分比、已下/总量、速度、剩余时间；
所有输出同时写 logs/setup.log。随时中断都行，重跑从断点继续。

常用参数：
    --no-models        只补依赖和环境，不下载权重
    --models-only      只下载权重
    --env qwen|moss|h3|all  只补某个环境（默认 all，H3 是可选项不会自动下）
    --engine ...       旧参数名，等同 --env
    --jobs 8           下载线程数（默认取 envs/index.json 的 download.jobs）
    --endpoint URL     优先使用这个镜像
    --no-launch        补完不打开界面
    --dry-run          只打印计划，不动任何东西
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBUI = os.path.join(ROOT, "webui")
sys.path.insert(0, WEBUI)

from envkit import check as ec     # noqa: E402
from envkit import download as hd  # noqa: E402
from envkit import install as ei   # noqa: E402
from envkit import spec as sp      # noqa: E402

ENVS = ("all", "qwen", "moss", "h3")


# ---------------------------------------------------------------- 控制台
class Console:
    """TTY 下原地刷新的进度行；非 TTY（管道/重定向）每 10 秒打一行。"""

    C = {
        "dim": "\033[2m", "b": "\033[1m", "cy": "\033[36m",
        "gr": "\033[32m", "ye": "\033[33m", "re": "\033[31m", "rs": "\033[0m",
    }

    def __init__(self, log_path):
        self.tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
        self.ansi = self.tty and self._enable_ansi()
        self._lock = threading.Lock()
        self._detail = ""
        self._live_len = 0
        self._done = threading.Event()
        self._last_print = 0.0
        self._last_file = 0.0
        self._spin_i = 0
        self.log_path = log_path
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n===== %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        except OSError:
            self.log_path = ""
        threading.Thread(target=self._spin, daemon=True).start()

    @staticmethod
    def _enable_ansi():
        if os.name != "nt":
            return True
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            mode = ctypes.c_uint()
            if not k.GetConsoleMode(h, ctypes.byref(mode)):
                return False
            k.SetConsoleMode(h, mode.value | 0x0004)
            return True
        except Exception:
            return False

    def color(self, text, key):
        if not self.ansi:
            return text
        return self.C.get(key, "") + text + self.C["rs"]

    def _to_file(self, text, force=False):
        now = time.time()
        if not self.log_path or (not force and now - self._last_file < 15):
            return
        self._last_file = now
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), text))
        except OSError:
            pass

    def _clear(self):
        if self.tty and self._live_len:
            sys.stdout.write("\r" + " " * self._live_len + "\r")
            self._live_len = 0

    def _draw(self, text):
        if not self.tty:
            return
        text = "  " + text
        try:
            cols = shutil.get_terminal_size().columns
        except OSError:
            cols = 120
        if len(text) > cols - 1:
            text = text[:max(10, cols - 2)] + "…"
        with self._lock:
            pad = max(0, self._live_len - len(text))
            sys.stdout.write("\r" + text + " " * pad)
            sys.stdout.flush()
            self._live_len = len(text)

    def _spin(self):
        marks = "|/-\\"
        while not self._done.wait(0.4):
            if not self._detail:
                continue
            if time.time() - self._last_file >= 15:
                self._to_file(self._detail)
            if self.tty:
                self._spin_i = (self._spin_i + 1) % len(marks)
                self._draw("%s %s" % (self._detail, marks[self._spin_i]))
            elif time.time() - self._last_print >= 10:
                self._last_print = time.time()
                print("  … " + self._detail, flush=True)

    def set(self, text):
        self._detail = text

    def line(self, text="", color=""):
        with self._lock:
            self._clear()
            if color:
                text = self.color(text, color)
            print(text, flush=True)
            self._live_len = 0
            self._detail = ""
        self._to_file(re.sub(r"\033\[[0-9;]*m", "", text), force=True)

    def log(self, text):
        self.line(text)

    def note(self, text):
        self.line(self.color(text, "dim"))

    def step(self, i, n, label):
        self.line("")
        self.line(self.color("[%d/%d] %s" % (i, n, label), "b"))

    def download(self, ev):
        if ev.get("busy") is False:
            return
        done, total = int(ev.get("done") or 0), int(ev.get("total") or 0)
        pct = int(round(done * 100.0 / total)) if total else 0
        pct = max(0, min(100, pct))
        width = 18
        fill = int(round(width * pct / 100.0))
        bar = ("█" * fill + "░" * (width - fill)) if self.ansi else ("#" * fill + "-" * (width - fill))
        f = os.path.basename(str(ev.get("file") or ""))[:22]
        left = "%s/%s" % (hd.fmt_bytes(done), hd.fmt_bytes(total)) if total else hd.fmt_bytes(done)
        sp = float(ev.get("speed") or 0)
        eta = hd.fmt_eta(ev.get("eta") or 0)
        tag = "hub兜底" if ev.get("phase") == "hub" else ("%d/%d 文件" % (
            int(ev.get("files_done") or 0), int(ev.get("files_total") or 0)))
        bits = ["[%s] %3d%%" % (bar, pct), left]
        if sp > 0:
            bits.append("%s/s" % hd.fmt_bytes(sp))
        if eta:
            bits.append("剩 " + eta)
        bits.append(tag)
        if f:
            bits.append(f)
        self.set(" · ".join(bits))

    def close(self):
        self._done.set()
        with self._lock:
            self._clear()


# ---------------------------------------------------------------- 计划
def env_set(env):
    """--env 选到哪些分区。H3 依赖 Moss 的 ComfyUI 运行时，补 H3 时把运行时装上。"""
    if env == "all":
        return None
    if env == "h3":
        return {"base", "moss", "h3"}
    return {"base", env}


def wanted(it, env):
    want = env_set(env)
    return want is None or str(it.get("env") or "base") in want


def _pkg_name(it):
    return str(it.get("key") or "").split(":", 1)[-1]


MODEL_STEPS = (("qwen", "千问权重"), ("moss", "Moss 权重"), ("h3", "H3 视频权重"))


def build_plan(items, env, with_models, models_only, full=False):
    """默认只备「界面能显示」：目录 + 界面壳；--full 才碰依赖、ComfyUI 与权重。

    权重下载统一回软件里做（环境页分区、明细与进度都在那边），BAT 不背这口锅。
    """
    steps = []
    full = bool(full or models_only)

    def add(key, label, kind, entries):
        if entries:
            steps.append({"key": key, "label": label, "kind": kind, "items": entries})

    mine = [it for it in items if wanted(it, env)]

    dirs = [it for it in mine
            if it.get("fix", {}).get("kind") == "dir" and it.get("state") != "ok"]
    add("dirs", "目录", "dir", dirs)

    pips = [it for it in mine
            if it.get("fix", {}).get("kind") == "pip"
            and it.get("state") in ("miss", "part", "warn")]
    if not models_only:
        shell = [it for it in pips if _pkg_name(it) == "pywebview"]
        add("shell", "界面壳", "pip", shell)

    if full and not models_only:
        rest = [it for it in pips if _pkg_name(it) != "pywebview"]
        add("deps", "依赖包", "pip", rest)
        if env in ("all", "moss", "h3"):
            comfy = [it for it in mine
                     if it.get("fix", {}).get("kind") == "comfyui"
                     and it.get("state") != "ok"]
            venv = [it for it in mine
                    if it.get("fix", {}).get("kind") == "comfyvenv"
                    and it.get("state") != "ok"]
            add("comfyui", "ComfyUI 代码", "comfyui", comfy)
            add("comfyvenv", "ComfyUI 独立环境", "comfyvenv", venv)

    if full and with_models:
        for eid, label in MODEL_STEPS:
            if env != "all" and eid not in (env_set(env) or set()):
                continue
            # 可选环境（H3）只有在明确点名时才下，--env all 不把 41 GB 悄悄带上
            if env == "all" and eid == "h3":
                continue
            entries = [it for it in mine
                       if it.get("fix", {}).get("kind") == "model"
                       and it.get("env") == eid and it.get("state") != "ok"]
            add(eid + "_models", label, "models", entries)

    steps.append({"key": "recheck", "label": "收尾复检", "kind": "recheck",
                  "items": []})
    return steps


def _gb(entries):
    return round(sum(float(it.get("gb") or 0) for it in entries), 1)


# ---------------------------------------------------------------- 执行
class Runner:
    def __init__(self, root, con, args, spec):
        self.root = root
        self.con = con
        self.args = args
        self.spec = spec
        self.results = []
        self.new_bytes = 0
        self.fatal = False
        self.comfy_ok = os.path.isfile(os.path.join(sp.runtime_dir(root, spec), "main.py"))

    def record(self, ok, label, detail, secs):
        self.results.append({"ok": ok, "label": label, "detail": detail,
                             "secs": secs})
        tag = self.con.color("✅", "gr") if ok else self.con.color("⚠️", "ye")
        self.con.line("%s %s · %s · %s" % (tag, label, detail, _secs(secs)))

    def run(self, steps):
        total = len(steps)
        for i, st in enumerate(steps, 1):
            if self.fatal:
                break
            self.con.step(i, total, st["label"])
            t0 = time.time()
            kind = st["kind"]
            if kind == "recheck":
                continue
            if kind == "dir":
                ok = True
                for it in st["items"]:
                    ei.install_dir(self.root, it["fix"]["path"])
                self.record(ok, st["label"], "%d 个目录" % len(st["items"]), time.time() - t0)
            elif kind == "pip":
                ok, done, bad = self._pip_step(st["items"])
                if st["key"] == "shell" and not ok:
                    self.fatal = True
                    self.con.line(self.con.color(
                        "❌ 界面壳没装上，后面的先不做了：修好网络再双击 启动.bat", "re"))
                self.record(ok, st["label"],
                            "%d/%d 个包" % (done, len(st["items"]))
                            + ("" if not bad else " · 失败 %d" % bad),
                            time.time() - t0)
            elif kind == "comfyui":
                fix = st["items"][0]["fix"]
                ok = ei.clone_comfyui(self.root, fix, self.con.log)
                self.comfy_ok = ok
                self.record(ok, st["label"], "已就位" if ok else "拉取失败",
                            time.time() - t0)
            elif kind == "comfyvenv":
                if not self.comfy_ok:
                    self.record(False, st["label"], "ComfyUI 代码没就位，跳过",
                                time.time() - t0)
                    continue
                fix = st["items"][0]["fix"]
                ok = ei.ensure_comfyui_venv(self.root, fix, self.con.log,
                                            python=sys.executable)
                self.record(ok, st["label"], "已就位" if ok else "安装失败",
                            time.time() - t0)
            elif kind == "models":
                if st["key"] in ("moss_models", "h3_models") and not self.comfy_ok:
                    self.record(False, st["label"], "ComfyUI 代码没就位，跳过",
                                time.time() - t0)
                    continue
                ok, detail = self._model_step(st["items"])
                self.record(ok, st["label"], detail, time.time() - t0)

    def _pip_step(self, items):
        ok_n, bad_n = 0, 0
        for k, it in enumerate(items, 1):
            label = it["label"]
            self.con.set("装 %s（%d/%d）…" % (label, k, len(items)))
            t0 = time.time()
            argv = ec.pip_argv(it, python=sys.executable)

            def on_line(line, label=label):
                if line.startswith("Collecting "):
                    self.con.set("装 %s · %s（%d/%d）"
                                 % (label, line[11:][:46], k, len(items)))
                elif "Downloading" in line:
                    m = re.search(r"\(([\d.]+\s*[KMG]B)\)", line, re.I)
                    if m:
                        self.con.set("装 %s · 下载 %s（%d/%d）"
                                     % (label, m.group(1), k, len(items)))
                elif line.startswith("Installing collected"):
                    self.con.set("装 %s · 落盘安装…（%d/%d）"
                                 % (label, k, len(items)))
            rc = ei.run_stream(argv, cwd=self.root, keep=ei.PIP_KEEP,
                               log=self.con.log, on_line=on_line)
            secs = time.time() - t0
            if rc == 0:
                ok_n += 1
                self.con.line("  ✅ %s · %s" % (label, _secs(secs)))
            else:
                bad_n += 1
                self.con.line("  ⚠️ %s 装失败（退出码 %s）· 网络不稳就开代理重跑"
                              % (label, rc))
                if "diffusers" in label:
                    self.con.note("     diffusers 从 github 装：直连不稳时先开代理")
        return bad_n == 0, ok_n, bad_n

    def _model_step(self, items):
        ok_n = bad_n = 0
        step_start = self.new_bytes
        for k, it in enumerate(items, 1):
            fx = it["fix"]
            repo = fx.get("repo")
            target = sp._abs(self.root, fx.get("dir") or "")
            if not repo or not target:
                bad_n += 1
                continue
            allow = fx.get("allow") or None
            os.makedirs(target, exist_ok=True)
            self.con.line("")
            self.con.line("  📦 [%d/%d] %s（约 %s GB）"
                          % (k, len(items), it["label"], it.get("gb", "?")))
            cfg = dict(self.spec.get("download") or {})
            if self.args.jobs:
                cfg["jobs"] = self.args.jobs
            res = hd.download(
                repo, target, allow=allow,
                jobs=int(cfg.get("jobs") or 8),
                chunk_mb=int(cfg.get("chunk_mb") or 64),
                retries=int(cfg.get("retries") or 20),
                timeout=int(cfg.get("timeout") or 60),
                probe_timeout=int(cfg.get("probe_timeout") or 8),
                endpoints=cfg.get("endpoints"),
                endpoint=self.args.endpoint or None,
                config=cfg, on_progress=self.con.download,
                on_log=self.con.log)
            bad = self._verify(it)
            ok = bool(res.get("ok")) and not bad
            if ok:
                ok_n += 1
                new = max(0, int(res.get("bytes") or 0) - int(res.get("resumed") or 0))
                self.new_bytes += new
                self.con.line("  ✅ %s · %s · %s"
                              % (it["label"], hd.fmt_bytes(res.get("bytes") or 0),
                                 _secs(res.get("seconds") or 0)))
            else:
                bad_n += 1
                why = res.get("error") or ("校验没通过：%s" % "、".join(bad[:2]))
                self.con.line("  ⚠️ %s 没下完：%s" % (it["label"], why))
        return bad_n == 0, "%d/%d 个权重 · 本次新下 %s" % (
            ok_n, len(items), hd.fmt_bytes(self.new_bytes - step_start))

    def _verify(self, it):
        """按清单里的 must 校验大小；下载器只保证写够，文件对不对要再核一遍。"""
        fx = it["fix"]
        must, base = {}, ""
        for m in self.spec.get("models") or []:
            if m.get("repo") == fx.get("repo") and m.get("dir") == fx.get("dir"):
                must = m.get("must") or {}
                base = sp.model_dir(self.root, m)
                break
        bad = []
        for rel, size in must.items():
            p = os.path.join(base, *str(rel).split("/"))
            try:
                got = os.path.getsize(p)
            except OSError:
                bad.append(rel)
                continue
            if int(size) and got != int(size):
                bad.append("%s（%d/%d）" % (rel, got, int(size)))
        return bad


# ---------------------------------------------------------------- 入口辅助
def _secs(sec):
    sec = float(sec or 0)
    if sec < 60:
        return "%d 秒" % round(sec)
    if sec < 3600:
        return "%d 分 %d 秒" % (int(sec // 60), int(sec % 60))
    return "%d 小时 %d 分" % (int(sec // 3600), int((sec % 3600) // 60))


def venv_python(root):
    return os.path.join(root, ".venv", "Scripts" if os.name == "nt" else "bin",
                        "python.exe" if os.name == "nt" else "python")


def _same(path, exe):
    try:
        return os.path.normcase(os.path.abspath(path)) == \
            os.path.normcase(os.path.abspath(exe))
    except (TypeError, ValueError):
        return False


def ensure_venv(root):
    """返回 (venv python 路径, 是否需要重开自己)。BAT 通常已经建好，这里只兜底。"""
    py = venv_python(root)
    if os.path.isfile(py):
        return py, not _same(py, sys.executable)
    print("[准备] 第一次启动：创建 .venv …", flush=True)
    vdir = os.path.join(root, ".venv")
    for cmd in (["py", "-3.12"], ["py", "-3"], ["python"]):
        try:
            rc = subprocess.call(cmd + ["-m", "venv", vdir])
        except OSError:
            continue
        if rc == 0 and os.path.isfile(py):
            return py, True
    print("[错误] 建不了 .venv：请先安装 Python 3.11~3.13（安装时勾选 Add to PATH）。",
          flush=True)
    return "", False


def shell_ok(py):
    if not py or not os.path.isfile(py):
        return False
    return subprocess.call([py, "-c", "import webview"],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL) == 0


def launch_ui(root, con):
    py = venv_python(root)
    if not shell_ok(py):
        con.line(con.color("❌ 界面壳（pywebview）没就绪，先不打开界面。", "re"))
        return False
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe" if os.name == "nt" else "")
    exe = pyw if os.path.isfile(pyw) else py
    con.line(con.color("🚀 打开界面…", "gr"))
    time.sleep(1.5)
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200     # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen([exe, os.path.join(root, "webui", "app.py")],
                         cwd=root, close_fds=True, creationflags=flags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError as e:
        con.line(con.color("❌ 拉不起界面：%s" % e, "re"))
        return False


def print_plan(con, steps, full=True):
    todo = [s for s in steps if s["kind"] != "recheck"]
    if not todo:
        con.line("环境已经齐了，不用补。" if full else "界面壳已就绪，直接打开软件。")
        return
    con.line("要补 %d 步：" % len(todo))
    for i, s in enumerate(todo, 1):
        names = "、".join(it["label"] for it in s["items"][:3])
        more = "" if len(s["items"]) <= 3 else " 等 %d 项" % len(s["items"])
        gb = _gb(s["items"])
        con.line("  %d. %-12s %s%s%s"
                 % (i, s["label"], names, more, ("（约 %.1f GB）" % gb) if gb else ""))
    total_gb = _gb([it for s in steps for it in s["items"]])
    if total_gb:
        free = shutil.disk_usage(ROOT).free / 2**30
        con.note("清单估算权重约 %.1f GB · 本盘剩余 %.1f GB" % (total_gb, free))


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True,
                                 description="准备界面环境并启动（默认只备到能显示）")
    ap.add_argument("--full", action="store_true",
                    help="连依赖、ComfyUI 与权重一起补（默认只装界面壳）")
    ap.add_argument("--no-models", action="store_true", help="配合 --full：不下权重")
    ap.add_argument("--models-only", action="store_true", help="只下权重（含 --full）")
    ap.add_argument("--env", choices=ENVS, default=None,
                    help="配合 --full：补哪个环境（all/qwen/moss/h3；H3 默认不下）")
    ap.add_argument("--engine", choices=ENVS, default=None,
                    help="旧参数名，等同 --env")
    ap.add_argument("--jobs", type=int, default=0, help="下载线程数（0=用 envs/index.json）")
    ap.add_argument("--endpoint", default="", help="优先使用的镜像地址")
    ap.add_argument("--no-launch", action="store_true", help="补完不打开界面")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划")
    args = ap.parse_args(argv)
    env = args.env or args.engine or "all"
    full = args.full or args.models_only
    if args.no_models and args.models_only:
        ap.error("--no-models 和 --models-only 是反的，只能留一个")

    if not args.dry_run:
        py, need_restart = ensure_venv(ROOT)
        if not py:
            return 1
        if need_restart:
            return subprocess.call([py, os.path.abspath(__file__)] + list(argv or sys.argv[1:]))

    con = Console(os.path.join(ROOT, "logs", "setup.log"))
    try:
        v = sys.version_info
        if not (3, 11) <= v[:2] <= (3, 13):
            con.line(con.color("⚠️ 当前 Python %d.%d 不在验证范围（3.11~3.13），"
                               "建议用 3.12 重建 .venv" % v[:2], "ye"))
        try:
            spec = sp.load_spec(ROOT)
        except Exception as e:
            con.line(con.color("❌ 读不了环境清单：%s" % e, "re"))
            return 1
        # 旧布局（根 models/、comfyui/models）先迁到 envs/<id>/models，再体检；
        # 否则会把「已经下好的 15GB」当成缺项。同盘 move 是改名，不复制。
        acts = sp.migrate_layout(ROOT, spec=spec, dry_run=args.dry_run, log=con.log)
        if acts:
            if args.dry_run:
                con.note("旧目录迁移（dry-run）：%s" % "；".join(acts[:4]))
            else:
                con.note("已整理旧目录：%d 项（详情见上面）" % len(acts))
        try:
            r = ec.check(ROOT, spec=spec)
        except Exception as e:
            con.line(con.color("❌ 体检没跑成：%s" % e, "re"))
            return 1
        steps = build_plan(r["items"], env, not args.no_models, args.models_only, full)
        left = r["todo"]
        con.line(con.color("Moss 生图控制台 · " + ("环境补全" if full else "界面准备"), "b"))
        con.line("体检：%s" % ("已就绪" if not left else "还差 %d 项" % len(left)))
        if not full:
            con.note("本次只备界面壳；依赖与权重打开软件后在「环境」页下（明细与进度都在那里）。")
            if args.env or args.engine:
                con.note("--env 只在 --full 下选环境；这里不带权重。")
        if args.dry_run:
            print_plan(con, steps, full)
            return 0
        print_plan(con, steps, full)
        con.line("")
        t0 = time.time()
        runner = Runner(ROOT, con, args, spec)
        runner.run(steps)
        secs = time.time() - t0

        con.line("")
        con.line(con.color("━━ 本次补全 ━━", "b"))
        for x in runner.results:
            tag = con.color("✅", "gr") if x["ok"] else con.color("⚠️", "ye")
            con.line("  %s %-14s %s · %s"
                     % (tag, x["label"], x["detail"], _secs(x["secs"])))
        con.line("总用时 %s · 新下载 %s"
                 % (_secs(secs), hd.fmt_bytes(runner.new_bytes)))

        try:
            sp.write_extra_model_paths(ROOT, spec, con.log)
        except Exception as e:
            con.note("⚠️ 没写进 ComfyUI 的权重路径：%s" % e)

        try:
            after = ec.check(ROOT, spec=spec)
            left = after["todo"]
        except Exception:
            left = []
        if left:
            if full:
                con.line(con.color("还差 %d 项：%s" % (
                    len(left), "、".join(dict.fromkeys(
                        str(k) for k in left))[:180]), "ye"))
                con.note("打开控制台，在「环境」页点对应分区的「一键补齐」即可继续。")
            else:
                con.note("界面已备好；其余 %d 项（依赖/权重）进软件后在「环境」页按分区补。"
                         % len(left))
        else:
            con.line(con.color("环境已齐，可以出图了。", "gr"))

        failures = [x for x in runner.results if not x["ok"]]
        if not args.no_launch:
            launch_ui(ROOT, con)
        return 1 if (failures or runner.fatal) else 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
