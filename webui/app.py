# -*- coding: utf-8 -*-
"""
app.py —— pywebview 壳 + js_api（生图控制台）
=============================================
职责（照 Mictools 已跑通的壳的口径，业务层换成本项目引擎）：

  · 配置持久化：ROOT/config.json（整合包规则：一切都在本目录，删目录=清干净）
  · 引擎任务：模型载入/卸载、文生图 —— 全部后台线程，js_api 立刻返回
  · 日志环形缓冲 + 前端轮询游标（拉取式，刷新不丢）
  · 画廊：扫描输出目录，PIL 缩略转 data:（html= 内联页显示不了 file://）
  · 无框窗口：拖动/缩放交给 ui/js/core/win.js + window_guard 原生守卫

运行：  .venv\\Scripts\\python.exe webui\\app.py
预览：  MIC_DEV=1 时额外内联 mock.js，可直接用浏览器看界面（不连引擎）。
"""
import atexit
import base64
import copy
import ctypes
import io
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for _p in (_HERE, os.path.join(_HERE, "ui"), os.path.join(ROOT, "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LOG_DIR = os.path.join(ROOT, "logs")
RUN_LOG = os.path.join(LOG_DIR, "run.log")


class _Tee(io.TextIOBase):
    """控制台 + 落盘双写，且任何一路写坏都不反手把主流程带崩。

    用 pythonw 起（没有黑框）时 sys.stdout/stderr 直接是 None，第三方库的 traceback
    会无处可去 —— 这份日志就是唯一的现场，所以它必须在 import webview/torch 之前接好。
    """

    def __init__(self, stream, fh):
        self._s = stream
        self._f = fh

    def write(self, s):
        txt = s if isinstance(s, str) else str(s)
        for o in (self._f, self._s):
            try:
                if o is not None:
                    o.write(txt)
                    o.flush()
            except Exception:
                pass
        return len(txt)

    def flush(self):
        for o in (self._f, self._s):
            try:
                if o is not None:
                    o.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def _setup_streams():
    fh = None
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        if os.path.exists(RUN_LOG) and os.path.getsize(RUN_LOG) > 4 * 1024 * 1024:
            os.replace(RUN_LOG, RUN_LOG + ".1")      # 只留一代，日志目录不无限长
        fh = open(RUN_LOG, "a", encoding="utf-8", errors="replace", buffering=1)
        fh.write("\n===== %s 启动（%s）=====\n"
                 % (time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(sys.argv[1:3]) or "桌面"))
    except Exception:
        fh = None
    sys.stdout = _Tee(sys.__stdout__, fh)
    sys.stderr = _Tee(sys.__stderr__, fh)


_setup_streams()

# 界面完全本地、外部请求全在 Python 后端：WebView2 一律直连，不碰系统代理。
# 否则代理软件（Clash 等）一旦把 loopback 也劫持，内置服务会被超时拦掉、界面白屏。
os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--no-proxy-server")

try:
    import webview  # noqa: E402

    import assemble  # noqa: E402  # ui/assemble.py：css/js 拼装顺序的唯一来源
    import loadbar  # noqa: E402  # 把第三方库的文本进度条接成界面里的百分比
    import single_instance  # noqa: E402
    from window_guard import WindowCtl, install_guard  # noqa: E402
except Exception:
    # pythonw 起的时候这里断了连一行字都留不下：落盘 + 弹框，别让人对着「双击没反应」猜
    sys.stderr.write("导入失败：\n" + traceback.format_exc())
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                "生图控制台起不来：依赖导入失败，请先跑 setup.bat。\n\n"
                + traceback.format_exc()[-1200:] + "\n\n完整堆栈见 logs\\run.log",
                "Qwen 生图控制台", 0x10)
        except Exception:
            pass
    raise SystemExit(1)

APP_NAME = "Qwen 生图控制台"
APP_VERSION = "0.2.0-m2"
CFG_PATH = os.path.join(ROOT, "config.json")
# 无框窗口尺寸（逻辑像素，与前端 CSS px 同量纲）；min 与 win.js/win_set 下限同一份
WIN_W, WIN_H = 1280, 800
MIN_W, MIN_H = 980, 620

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
# pywebview 的过滤串：描述 + 括号内分号分隔的扩展名（空格分隔会被 parse_file_type 拒）
_IMG_FILTER = "图片 (*" + ";*".join(IMG_EXT) + ")"

DEFAULT_CFG = {
    "app_title": APP_NAME, "theme": "tide", "mode": "dark",
    "layout": "flat", "sidebar_min": False, "notify": True, "last_tab": "t_ov",
    "open": {},
    "console": {"model_dir": "models/Qwen-Image-2.1-Turbo", "output_dir": "outputs",
                "quant": "fp8", "offload": True},
    "gen": {"prompt": "", "negative": "", "size": "1024x1024", "steps": "8",
            "seed": -1, "count": 1, "kv_cache": True},
    "edit": {"prompt": "", "negative": "", "res": "512", "steps": "8",
             "seed": -1, "count": 1, "kv_cache": True},
    "inpaint": {"prompt": "", "negative": "", "res": "512", "steps": "8",
                "seed": -1, "count": 1, "kv_cache": True, "brush": 48},
    "rgba": {"prompt": "", "negative": "", "size": "1024x1024", "steps": "8",
             "seed": -1, "count": 1, "kv_cache": True},
    "api": {"enabled": False, "lan": False, "port": 8765,
            "token": ""},
    "nav": [
        {"id": "t_ov", "type": "tab", "name": "概览", "icon": "home", "page": "overview"},
        {"id": "t_gen", "type": "tab", "name": "文生图", "icon": "flower", "page": "t2i"},
        {"id": "t_edit", "type": "tab", "name": "图像编辑", "icon": "wand", "page": "edit"},
        {"id": "t_inp", "type": "tab", "name": "局部编辑", "icon": "brush", "page": "inpaint"},
        {"id": "t_rgba", "type": "tab", "name": "透明素材", "icon": "layers", "page": "rgba"},
        {"id": "t_gal", "type": "tab", "name": "画廊", "icon": "image", "page": "gallery"},
        {"id": "t_pe", "type": "tab", "name": "提示词工坊", "icon": "book", "page": "pe"},
        {"id": "t_mod", "type": "tab", "name": "模型管理", "icon": "db", "page": "models"},
        {"id": "t_api", "type": "tab", "name": "API 服务", "icon": "globe", "page": "api"},
        {"id": "t_set", "type": "tab", "name": "设置", "icon": "cog", "page": "settings"},
    ],
}


def _deep_merge(dst, src):
    for k, v in (src or {}).items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def _abs_path(p):
    """配置里的相对路径按项目根解释（整合包：整个目录搬到哪都能跑）。"""
    if not p:
        return ""
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def _to_int(v, default, lo=1, hi=10 ** 6):
    """前端传来的数字一律容错：坏值回落默认档，绝不能让 int() 把任务卡死在半路。"""
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _fd(name):
    """pywebview 6 用 FileDialog 枚举，旧版是 webview.XXX_DIALOG 常量；兼容取。"""
    fd = getattr(webview, "FileDialog", None)
    return getattr(fd, name) if fd is not None else getattr(webview, name + "_DIALOG")


def _checkerboard(size, cell=16):
    """给透明图铺的灰白棋盘底（PIL 无内置，手画一张 RGB）。"""
    from PIL import Image
    w, h = size
    bg = Image.new("RGB", (w, h), (255, 255, 255))
    px = bg.load()
    for y in range(h):
        for x in range(w):
            if ((x // cell) + (y // cell)) % 2:
                px[x, y] = (210, 210, 210)
    return bg


class App(WindowCtl):
    def __init__(self):
        self.cfg = json.loads(json.dumps(DEFAULT_CFG))
        self._load_cfg()
        self._lock = threading.Lock()
        self._task_lock = threading.Lock()   # 「查空闲 + 占位」必须一气呵成
        self._logs = []            # [seq, hh:mm:ss, text]
        self._seq = 0
        self._window = None
        self._thread = None
        self._stop = threading.Event()
        self.mgr = None            # PipelineMgr：第一次载入时才 import（拉 torch）
        self._api = None           # ApiServer：API 页开启时才 import（拉 fastapi）
        self._dl = None            # 模型下载线程（同一时间只允许一个）
        self._thumbs = {}          # (path, mtime) -> data url，缩略缓存
        from store import Store
        self.store = Store(os.path.join(ROOT, "data", "history.db"))
        self.store.init()
        self.st = {
            "running": None, "status": "就绪", "done": 0, "total": 0,
            "model_loaded": False, "model_name": "Qwen-Image-2.1-Turbo",
            "quant": self.cfg["console"].get("quant", "fp8"),
            "vram_used": 0.0, "vram_total": 12.0,
            "img_count": 0, "last_sec": 0.0, "last_image": "",
            "api_on": False, "api_url": "", "t_start": 0, "elapsed": 0,
            # 载入进度：黑框去掉后，权重加载这条唯一「看得见」的路就是这两个字段
            "load_pct": 0, "load_stage": "",
        }
        self._refresh_gallery_count()
        self._log("就绪 · %s" % APP_NAME)

    # ------------------------------------------------------------ 配置
    def _load_cfg(self):
        try:
            with open(CFG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            _deep_merge(self.cfg, saved)
            # 导航结构以整块为准（用户可能重排过），但缺的页要补回
            self._repair_nav()
        except (OSError, ValueError):
            pass

    def _repair_nav(self):
        known = {n["page"]: n for n in DEFAULT_CFG["nav"]}
        have = set()

        def walk(nodes):
            for n in nodes:
                if n.get("type") == "tab":
                    have.add(n.get("page"))
                walk(n.get("children") or [])
        walk(self.cfg.get("nav") or [])
        missing = [copy.deepcopy(n) for p, n in known.items() if p not in have]
        if missing:
            self.cfg.setdefault("nav", [])
            self.cfg["nav"] = missing + self.cfg["nav"]

    def _save_cfg(self):
        try:
            with open(CFG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=1)
        except OSError as e:
            self._log("⚠️ 配置没存上：%s" % e)

    # ------------------------------------------------------------ 日志
    def _log(self, text):
        with self._lock:
            self._seq += 1
            self._logs.append([self._seq, time.strftime("%H:%M:%S"), str(text)])
            if len(self._logs) > 3000:
                del self._logs[:len(self._logs) - 3000]

    # ------------------------------------------------------------ js_api：取数
    def boot(self):
        return {"cfg": self.cfg, "state": self._snap(),
                "version": APP_VERSION, "default_nav": DEFAULT_CFG["nav"]}

    def poll(self, cursor=0):
        with self._lock:                 # seq 和 logs 一次取齐：分两次读，中间新进的一条会被跳过
            seq = self._seq
            logs = [x for x in self._logs if x[0] > (cursor or 0)]
        self._sample_vram()
        return {"seq": seq, "logs": logs, "state": self._snap()}

    def refresh_stats(self):
        self._refresh_gallery_count()
        self._sample_vram()
        return {"ok": True, "state": self._snap()}

    def _snap(self):
        s = json.loads(json.dumps(self.st))
        if s.get("running") and s.get("t_start"):
            s["elapsed"] = round(time.time() - s["t_start"], 1)
        else:
            s["elapsed"] = 0
        return s

    def save_cfg(self, patch):
        _deep_merge(self.cfg, patch or {})
        self.st["quant"] = self.cfg["console"].get("quant", "fp8")
        self._save_cfg()
        return {"ok": True, "cfg": self.cfg}

    def set_title(self, title):
        self.cfg["app_title"] = title
        self._save_cfg()
        if self._window is not None:
            try:
                self._window.title = title
            except Exception:
                pass
        return {"ok": True, "title": title}

    # ------------------------------------------------------------ js_api：对话框
    def abs_path(self, p):
        """给 api_server 这类同进程模块用的路径基准：相对路径按项目根解释，不跟着 CWD 漂。"""
        return _abs_path(p)

    def pick(self, kind="file"):
        w = self._window
        if w is None:
            return ""
        # 目录框的兜底绝不能是「打开文件对话框」：那样会把一个文件路径填进目录字段
        if kind == "dir":
            try:
                r = w.create_file_dialog(_fd("FOLDER"))
            except Exception as e:
                self._log("⚠️ 目录对话框没打开：%s" % e)
                return ""
        else:
            # 合成一条过滤：拆多项时对话框默认项只放行一种扩展名，jpg 会被整个灰掉。
            # 多个扩展名必须用分号分隔——pywebview 的 parse_file_type 正则不认空格，
            # 传空格形式会抛 ValueError（被下面 except 吞掉，症状就是「点了没反应」）
            try:
                r = w.create_file_dialog(_fd("OPEN"),
                                         file_types=(_IMG_FILTER,))
            except Exception as e:
                self._log("⚠️ 文件对话框没打开：%s" % e)
                try:
                    r = w.create_file_dialog(_fd("OPEN"))   # 过滤串坏掉也要让人能选文件
                except Exception as e2:
                    self._log("⚠️ 重试也没打开：%s" % e2)
                    return ""
        if not r:
            return ""
        return r[0] if isinstance(r, (tuple, list)) else str(r)

    @staticmethod
    def _drop_variants(raw):
        """拖放候选串 → 路径候选。浏览器给的形式不统一：原生绝对路径、
        file:/// + 百分号编码（中文/空格名）、DownloadURL 带引号、或只有文件名。"""
        s = str(raw or "").strip().strip('"').strip("'").strip()
        if not s:
            return
        yield os.path.normpath(s)
        t = s
        if t.lower().startswith("file:"):
            t = urllib.parse.unquote(urllib.parse.urlparse(t).path or t[5:])
            if len(t) > 2 and t[0] == "/" and t[2] == ":":
                t = t[1:]                       # /C:/x → C:/x
        else:
            t = urllib.parse.unquote(t)
        t = os.path.normpath(t)
        if t != os.path.normpath(s):
            yield t

    def _find_by_name(self, name):
        """只剩文件名时（Chromium 系内核不给完整路径），去常见落点找一遍。"""
        if not name or ("/" in name) or ("\\" in name):
            return ""
        home = os.path.expanduser("~")
        for d in [_abs_path(self.cfg["console"].get("output_dir", ""))] + \
                [os.path.join(home, x) for x in ("Desktop", "Downloads", "Pictures")]:
            p = os.path.join(d or "", name)
            if d and os.path.exists(p):
                return os.path.normpath(p)
        return ""

    def drop_path(self, candidates, kind="file"):
        """拖进来的路径列表 → 挑一个真实存在的绝对路径（相对路径按项目根找）。"""
        for c in candidates or []:
            for p in self._drop_variants(c):
                if os.path.isabs(p) and os.path.exists(p):
                    return {"ok": True, "path": p}
                q = _abs_path(p)
                if os.path.exists(q):
                    return {"ok": True, "path": q}
            hit = self._find_by_name(os.path.basename(self._drop_decode(c)))
            if hit:
                return {"ok": True, "path": hit}
        return {"ok": False, "msg": "没找到拖进来的文件，请用「浏览」选"}

    @staticmethod
    def _drop_decode(raw):
        """取拖放串里最像路径的那个形态，只为拿文件名。"""
        for p in App._drop_variants(raw):
            if p.lower().startswith("file:") or "%" in p:
                continue
            return p
        return str(raw or "")

    def save_drop(self, name, data_url):
        """内核只给得出文件名、路径解析全落空时的兜底：前端把字节读出来交回来落盘。"""
        ext = os.path.splitext(str(name or ""))[1].lower()
        if ext not in IMG_EXT:
            return {"ok": False, "msg": "拖进来的不是图片（%s）" % (ext or "?")}
        if not data_url or "," not in str(data_url):
            return {"ok": False, "msg": "没读到文件内容，请用「浏览」选"}
        try:
            raw = base64.b64decode(str(data_url).split(",", 1)[1])
        except Exception as e:
            return {"ok": False, "msg": "解码失败：%s" % e}
        if not raw or len(raw) > 40 * 1024 * 1024:
            return {"ok": False, "msg": "文件为空或超过 40MB，请用「浏览」选"}
        out = _abs_path(self.cfg["console"].get("output_dir", ""))
        d = os.path.join(out, "drop_refs")
        os.makedirs(d, exist_ok=True)
        stem = re.sub(r"[^\w.\-]", "_", os.path.splitext(os.path.basename(str(name)))[0])[:60]
        p = os.path.join(d, "%s_%d%s" % (stem or "drop", int(time.time()), ext))
        try:
            with open(p, "wb") as fh:
                fh.write(raw)
        except OSError as e:
            return {"ok": False, "msg": "落盘失败：%s" % e}
        self._log("📥 拖放的文件已代收：%s（%.1f KB）" % (p, len(raw) / 1024.0))
        return {"ok": True, "path": p}

    # ------------------------------------------------------------ js_api：窗口
    def attach(self, window):
        self._window = window

    def on_closing(self):
        """关闭收尾：叫停后台线程 → 停 API 监听 → 存配置。绝不能 return False（=取消关闭）。"""
        self._stop.set()
        if self._api is not None:
            try:
                self._api.stop()
            except Exception:
                pass
        self._save_cfg()
        return None

    # ------------------------------------------------------------ js_api：引擎
    def _busy(self):
        return self.st["running"] is not None

    def _claim(self, key):
        """占位：pywebview 给每个 js_api 调用单起一个线程，「先查 _busy 再起线程」
        中间能被另一个调用插进来，两个任务会同踩同一个 pipeline。查+占放一把锁里。"""
        with self._task_lock:
            if self.st["running"] is not None:
                return False
            self.st["running"] = key
            self.st["t_start"] = time.time()
            self._stop.clear()       # 上一个任务留下的停止位不能顺延到新任务
            return True

    def _release(self):
        with self._task_lock:
            self.st["running"] = None

    def _launch(self, key, fn):
        if not self._claim(key):
            return False
        self._thread = threading.Thread(target=fn, daemon=True)
        self._thread.start()
        return True

    def _busy_msg(self):
        return "有任务在跑：" + str(self.st["running"])

    def _get_mgr(self):
        if self.mgr is None:
            from pipeline_mgr import PipelineMgr
            self.mgr = PipelineMgr(log=self._log)
        return self.mgr

    def load_model(self):
        if not self._launch("load", self._do_load):
            return {"ok": False, "msg": self._busy_msg()}
        return {"ok": True}

    def _report_load(self, pct, stage):
        self.st["load_pct"] = pct
        self.st["load_stage"] = stage

    def _do_load(self, chain_gen=None):
        try:
            c = self.cfg["console"]
            repo = _abs_path(c["model_dir"])
            self.st["status"] = "载入模型…"
            self._report_load(0, "准备载入")
            loadbar.silence_text_bars()   # 文本条一律关掉，进度改由界面进度条承担
            with loadbar.watch(repo, self._report_load) as bar:
                self._get_mgr().load(repo,
                                     offload=bool(c.get("offload", True)),
                                     quant=c.get("quant", "fp8"),
                                     on_stage=bar.note)
            self._report_load(100, "已就绪")
            self.st["model_loaded"] = True
            self.st["status"] = "模型已载入"
            self._log("✅ 模型已载入")
            if chain_gen:
                if self._stop.is_set():
                    self.st["status"] = "已停止"
                    self._log("⏹ 载入期间已请求停止：跳过本次生成")
                else:
                    self._do_gen(chain_gen)
                return
        except Exception as e:
            self._log("❌ 模型载入失败：%s" % e)
            self.st["status"] = "模型载入失败"
        finally:
            if self.st["running"] == "load":
                self._release()

    def unload_model(self):
        # 卸载也要占位：查空闲和真正放显存之间若有窗口，生成任务能插进来踩空
        if not self._claim("unload"):
            return {"ok": False, "msg": self._busy_msg()}
        try:
            if self.mgr is None or self.mgr.pipe is None:
                return {"ok": False, "msg": "模型本来就没在显存里"}
            self.mgr.unload()
            self.st["model_loaded"] = False
            self.st["status"] = "模型已卸载"
            self._log("已卸载模型 · 显存归还")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "msg": str(e)}
        finally:
            self._release()

    def start_gen(self, payload=None):
        g = dict(self.cfg.get("gen") or {})
        g.update(payload or {})
        if not str(g.get("prompt", "")).strip():
            return {"ok": False, "msg": "提示词是空的，先写点想要什么"}
        mode = str(g.get("mode") or "gen")
        if mode in ("edit", "inpaint") and not (g.get("images") or []):
            return {"ok": False, "msg": "编辑/局部编辑需要先选参考图"}
        # 参数一律容错解析：这里抛出去任务就没起跑、也没人把 running 归位，界面会永久卡在跑图中
        steps = _to_int(g.get("steps"), 8, 1, 100)
        self.st["total"] = steps
        need_load = self.mgr is None or self.mgr.pipe is None
        if need_load:
            launch = lambda: self._do_load(chain_gen=g)
        else:
            launch = lambda: self._do_gen(g)
        if not self._launch("load" if need_load else "gen", launch):
            return {"ok": False, "msg": self._busy_msg()}
        if need_load:
            self._log("模型未载入：先载入，随后自动开始生成")
        return {"ok": True, "total": steps}

    # -------------------------------------------------------- 参考图 / 蒙版
    @staticmethod
    def _mask_datauri_to_alpha(mask_uri, size):
        """把前端画布导出的涂抹蒙版（不透明处=要重绘）转成 alpha 数组。
        返回 PIL 'L' 图：涂到的地方 0（透明→模型重绘），其余 255（保留原图）。"""
        from PIL import Image
        if not mask_uri:
            return None
        b64 = str(mask_uri).split(",", 1)[1] if "," in str(mask_uri) else str(mask_uri)
        m = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA").resize(size)
        painted = m.getchannel("A").point(lambda a: 0 if a > 8 else 255)
        return painted

    def _build_input_image(self, g):
        """按 mode 组装 pipeline 的 image 参数：编辑=参考图列表，局部编辑=原图+涂抹区透明。
        透明素材页不需要输入图（靠提示词触发），返回 None。"""
        from PIL import Image
        mode = str(g.get("mode") or "gen")
        paths = [self._ref_path(p) for p in (g.get("images") or [])]
        paths = [p for p in paths if p]
        if mode == "gen" or not paths:
            return None
        if mode == "inpaint":
            base = Image.open(paths[0]).convert("RGBA")
            alpha = self._mask_datauri_to_alpha(g.get("mask"), base.size)
            if alpha is not None:
                base.putalpha(alpha)
            return base
        # edit：多参考图，逐张转 RGBA
        return [Image.open(p).convert("RGBA") for p in paths]

    def _ref_path(self, p):
        c = _abs_path(str(p).replace("file:///", "").replace("file://", ""))
        c = os.path.normpath(c)
        return c if os.path.isfile(c) else ""

    def _do_gen(self, g):
        self.st["running"] = "gen"
        self.st["done"] = 0
        try:
            # 全部参数解析放进 try：这里抛出去就永远到不了 finally，running 卡在 gen 再也点不动
            steps = _to_int(g.get("steps"), 8, 1, 100)
            mode = str(g.get("mode") or "gen")
            wh = str(g.get("size", "1024x1024")).lower().split("x")
            w, h = _to_int(wh[0], 1024, 64, 4096), _to_int(wh[1] if len(wh) > 1 else "", 1024, 64, 4096)
            count = _to_int(g.get("count"), 1, 1, 8)
            mgr = self._get_mgr()
            if mgr.pipe is None:
                mgr.load(_abs_path(self.cfg["console"]["model_dir"]),
                         offload=bool(self.cfg["console"].get("offload", True)),
                         quant=self.cfg["console"].get("quant", "fp8"))
                self.st["model_loaded"] = True
            out_dir = _abs_path(self.cfg["console"]["output_dir"])
            os.makedirs(out_dir, exist_ok=True)
            input_image = self._build_input_image(g)
            label = {"edit": "图像编辑", "inpaint": "局部编辑", "rgba": "透明素材"}.get(mode, "文生图")
            fit = mode in ("edit", "inpaint")
            res = _to_int(g.get("res"), 1024, 256, 2048)
            if fit:
                self._log("🚀 开始%s：跟随原图比例 · %d 画幅 · %d 步 × %d 张" % (label, res, steps, count))
            else:
                self._log("🚀 开始%s：%dx%d · %d 步 × %d 张" % (label, w, h, steps, count))

            def on_step(done_i, total_i):
                if not self._stop.is_set():
                    self.st["done"] = done_i
                    self.st["total"] = total_i
                    self.st["status"] = "去噪 %d/%d" % (done_i, total_i)

            def should_stop():
                return self._stop.is_set()

            for i in range(count):
                if self._stop.is_set():
                    self._log("⏹ 已停止（第 %d 张之前）" % (i + 1))
                    self.st["status"] = "已停止"
                    break
                seed = _to_int(g.get("seed"), -1, -1, 10 ** 12)
                if seed < 0:
                    seed = int(time.time()) % 10 ** 8
                self.st["done"] = 0
                t0 = time.time()
                common = dict(prompt=str(g.get("prompt", "")), image=input_image,
                              steps=None if steps == 8 else steps,
                              seed=seed, kv_cache=bool(g.get("kv_cache", True)),
                              on_step=on_step, should_stop=should_stop)
                if fit:
                    img = mgr.generate(resolution=res, **common)
                else:
                    img = mgr.generate(width=w, height=h, **common)
                dt = time.time() - t0
                # 中断时 pipeline 照样返回一张「半去噪」图：存进画廊就是张废图，别收
                if self._stop.is_set():
                    self._log("⏹ 已停止：第 %d 张是被中断的半成品，不落盘" % (i + 1))
                    self.st["status"] = "已停止"
                    break
                # 名字带序号：同一批多张不能挤在同一秒的同一个名上（会互相覆盖成一张）
                stem = "%s_%s" % ("gen" if mode == "gen" else mode,
                                  time.strftime("%Y%m%d_%H%M%S"))
                path = os.path.join(out_dir, "%s_%d.png" % (stem, i + 1))
                bump = 0
                while os.path.exists(path):      # 同一秒又点了一轮开始：加后缀顶开，别让新图盖掉旧图
                    bump += 1
                    path = os.path.join(out_dir, "%s_%d_x%d.png" % (stem, i + 1, bump))
                name = os.path.basename(path)
                img.save(path)  # RGBA 输出直接带 alpha 存进 PNG
                g.setdefault("_saved", []).append(path)
                self.store.add(path, mode=mode, prompt=str(g.get("prompt", "")),
                               negative=str(g.get("negative", "")),
                               size=("跟随输入图 · %d²" % res) if fit else ("%dx%d" % (w, h)),
                               steps=steps, seed=seed, sec=round(dt, 1))
                self.st["last_sec"] = round(dt, 1)
                self.st["last_image"] = path
                self._log("✅ (%d/%d) 已保存：%s · %.1f 秒" % (i + 1, count, name, dt))
                self._refresh_gallery_count()
            else:
                self.st["status"] = "✅ 完成"
                self._log("── 结束 ──")
        except Exception as e:
            self._log("❌ 生成失败：%s" % e)
            self.st["status"] = "生成失败"
        finally:
            self._release()

    def stop(self, key=None):
        if not self._busy():
            return {"ok": False, "msg": "没有运行中的任务"}
        self._stop.set()
        self.st["status"] = "停止中…"
        if self.st["running"] == "load":
            self._log("⏹ 已请求停止：模型载入是一次性动作，完成后将不再开始生成")
        else:
            self._log("⏹ 已请求停止：等当前这一步去噪完成后中断")
        return {"ok": True}

    # ------------------------------------------------------------ js_api：API 服务
    def api_state(self):
        return {"ok": True, "cfg": self.cfg["api"],
                "on": bool(self.st["api_on"]), "url": self.st["api_url"]}

    def api_set(self, patch=None):
        """改 API 配置并即时生效（开关/局域网/端口）。返回 api_state。"""
        p = patch or {}
        a = self.cfg["api"]
        if "enabled" in p:
            a["enabled"] = bool(p["enabled"])
        if "lan" in p:
            a["lan"] = bool(p["lan"])
        if "port" in p:
            try:
                a["port"] = max(1, min(65535, int(p["port"])))
            except (TypeError, ValueError):
                return {"ok": False, "msg": "端口要给数字", "state": self.api_state()}
        if a["enabled"] and not a.get("token"):
            import secrets
            a["token"] = secrets.token_hex(16)
            self._log("🔑 已生成 API 令牌")
        self._save_cfg()
        err = self._apply_api()
        return {"ok": err is None, "msg": err or "", "state": self.api_state()}

    def api_token_reset(self):
        import secrets
        self.cfg["api"]["token"] = secrets.token_hex(16)
        self._save_cfg()
        self._log("🔑 API 令牌已重新生成")
        return {"ok": True, "state": self.api_state()}

    def _lan_ip(self):
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return "127.0.0.1"

    def _apply_api(self):
        """按 cfg 重建监听：任何改动都先停旧再起新，端口/局域网不会漂移不生效。"""
        a = self.cfg["api"]
        if self._api is not None:
            self._api.stop()
            self._api = None
            self.st["api_on"] = False
            self.st["api_url"] = ""
        if not a.get("enabled"):
            return None
        try:
            from api_server import ApiServer
            host = "0.0.0.0" if a.get("lan") else "127.0.0.1"
            port = int(a.get("port") or 8765)
            self._api = ApiServer(self)
            disp = self._lan_ip() if a.get("lan") else "127.0.0.1"
            if self._api.start(host, port):
                self.st["api_on"] = True
                self.st["api_url"] = "http://%s:%d" % (disp, port)
                self._log("🌐 API 服务已启动：%s（Bearer 令牌鉴权）" % self.st["api_url"])
                if a.get("lan"):
                    self._log("⚠️ 局域网模式：若被 Windows 防火墙拦，管理员执行一次："
                              "netsh advfirewall firewall add rule name=QwenImgAPI "
                              "dir=in action=allow protocol=TCP localport=%d" % port)
                return None
            self._api.stop()
            self._api = None
            return "端口 %d 起不来（可能被别的程序占用），换个端口再试" % port
        except Exception as e:
            if self._api is not None:
                try:
                    self._api.stop()
                except Exception:
                    pass
            self._api = None
            self._log("❌ API 服务启动失败：%s" % e)
            return str(e)

    # ------------------------------------------------------------ js_api：画廊
    def _gallery_items(self, limit=120):
        out_dir = _abs_path(self.cfg["console"]["output_dir"])
        if not os.path.isdir(out_dir):
            return []
        files = []
        for name in os.listdir(out_dir):
            if name.lower().endswith(IMG_EXT):
                p = os.path.join(out_dir, name)
                try:
                    files.append((os.path.getmtime(p), p))
                except OSError:
                    pass
        files.sort(reverse=True)
        items = []
        for mt, p in files[:limit]:
            items.append({"file": p, "name": os.path.basename(p),
                          "t": time.strftime("%Y-%m-%d %H:%M", time.localtime(mt)),
                          "url": self._thumb(p, mt, 384)})
        return items

    def _thumb(self, path, mt, wide):
        key = (path, mt, wide)
        hit = self._thumbs.get(key)
        if hit:
            return hit
        url = ""
        try:
            from PIL import Image
            with Image.open(path) as im:
                im.thumbnail((wide, wide))
                if im.mode == "RGBA":
                    # 透明素材：贴到棋盘底上预览，一眼看出哪里是透明
                    bg = _checkerboard(im.size)
                    bg.paste(im, (0, 0), im)
                    im = bg.convert("RGB")
                elif im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=72)
                url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            self._log("⚠️ 缩略图没生成：%s" % e)
        if len(self._thumbs) > 240:
            self._thumbs.clear()
        self._thumbs[key] = url
        return url

    def gallery_list(self):
        items = self._gallery_items()
        metas = self.store.meta_map([it["file"] for it in items])
        for it in items:
            m = metas.get(it["file"])
            if m:
                it.update({k: m[k] for k in
                           ("mode", "prompt", "negative", "size", "steps", "seed", "sec", "fav")})
        self.st["img_count"] = len(items)
        return {"ok": True, "items": items, "stats": self.store.stats()}

    def gallery_fav(self, path, fav):
        p = os.path.normpath(str(path or ""))
        self.store.set_fav(p, bool(fav))
        return {"ok": True}

    def gallery_delete(self, path):
        p = self._in_output(path)
        if not p:
            return {"ok": False, "msg": "这个文件不在输出目录里，不动它"}
        try:
            os.remove(p)
            self.store.remove(p)
            self._log("已删除：" + os.path.basename(p))
            self._refresh_gallery_count()
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "msg": str(e)}

    def gallery_clear(self):
        out_dir = _abs_path(self.cfg["console"]["output_dir"])
        try:
            entries = os.listdir(out_dir)
        except OSError as e:
            return {"ok": False, "msg": "打不开输出目录：%s" % e}
        gone, left = 0, set()
        for name in entries:
            p = os.path.join(out_dir, name)
            if not name.lower().endswith(IMG_EXT) or not os.path.isfile(p):
                continue
            try:
                os.remove(p)     # 直接扫目录：走 _gallery_items 会给每张图现做缩略图，清空时白烧几十秒 CPU
                gone += 1
            except OSError:
                left.add(os.path.normpath(p))   # 删不掉的（正被占用）留在盘上，它的参数记录也得留着
        msg = "已清空输出目录：%d 张" % gone
        if left:
            msg += "，%d 张正被占用没删掉" % len(left)
        self._log(msg)
        self.store.prune(left)
        self._refresh_gallery_count()
        return {"ok": True, "removed": gone}

    def _in_output(self, path):
        """删除类操作只认输出目录里的图片路径（防止被当成任意文件删除器）。"""
        out_dir = os.path.normpath(_abs_path(self.cfg["console"]["output_dir"]))
        p = os.path.normpath(str(path or ""))
        if p.lower().endswith(IMG_EXT) and os.path.dirname(p) == out_dir and os.path.isfile(p):
            return p
        return None

    def thumb(self, path):
        p = os.path.normpath(str(path or ""))
        if not (p.lower().endswith(IMG_EXT) and os.path.isfile(p)):
            return {"ok": False, "msg": "图还没落盘"}
        return {"ok": True, "url": self._thumb(p, os.path.getmtime(p), 768)}

    # ------------------------------------------------------------ js_api：模型管理
    @staticmethod
    def _safe_name(name):
        return bool(re.fullmatch(r"[A-Za-z0-9._-]+", str(name or "")))

    def models_list(self):
        root = _abs_path("models")
        active = os.path.normpath(_abs_path(
            str((self.cfg["console"] or {}).get("model_dir", ""))))
        items = []
        try:
            names = sorted(os.listdir(root))
        except OSError:
            names = []
        for name in names:
            d = os.path.join(root, name)
            if not os.path.isdir(d):
                continue
            total, shards = 0, 0
            for base, _dirs, fs in os.walk(d):
                for f in fs:
                    try:
                        total += os.path.getsize(os.path.join(base, f))
                    except OSError:
                        pass
                    if f.endswith(".safetensors"):
                        shards += 1
            items.append({"name": name, "gb": round(total / 2**30, 1),
                          "shards": shards,
                          "index": os.path.isfile(os.path.join(d, "model_index.json")),
                          "active": os.path.normpath(d) == active})
        return {"ok": True, "items": items, "dir": root}

    def models_set_active(self, name):
        if not self._safe_name(name):
            return {"ok": False, "msg": "模型目录名只能是字母数字点横线下划线"}
        d = _abs_path(os.path.join("models", name))
        if not os.path.isdir(d):
            return {"ok": False, "msg": "这个目录不存在"}
        self.cfg["console"]["model_dir"] = "models/" + name
        self._save_cfg()
        self._log("已切换激活模型：%s%s" % (name,
                  "（显存里还是旧模型：重新载入才生效）" if self.st["model_loaded"] else ""))
        return {"ok": True, "cfg": self.cfg}

    def models_download(self, repo, name=""):
        """hf-mirror 断点续传下载：后台线程 + 每分钟进度日志，瞬断自动重连 20 次。"""
        if self._dl is not None and self._dl.is_alive():
            return {"ok": False, "msg": "已经有一个下载在跑，等它结束"}
        repo = str(repo or "").strip()
        name = str(name or "").strip() or repo.split("/")[-1]
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or not self._safe_name(name):
            return {"ok": False, "msg": "repo 格式要 org/name；目录名只允许字母数字点横线下划线"}
        target = _abs_path(os.path.join("models", name))
        os.makedirs(target, exist_ok=True)

        def dir_gb(p):
            t = 0
            for base, _dirs, fs in os.walk(p):
                for f in fs:
                    try:
                        t += os.path.getsize(os.path.join(base, f))
                    except OSError:
                        pass
            return t / 2**30

        def run():
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            import huggingface_hub
            self._log("📥 开始下载 %s → models/%s（hf-mirror，断点续传）" % (repo, name))
            t0 = time.time()
            stop_watch = threading.Event()

            def watch():
                while not stop_watch.wait(60):
                    self._log("…下载中：models/%s 当前 %.1f GB" % (name, dir_gb(target)))
            wt = threading.Thread(target=watch, daemon=True)
            wt.start()
            done = False
            try:
                for attempt in range(1, 21):
                    try:
                        huggingface_hub.snapshot_download(
                            repo_id=repo, local_dir=target, max_workers=4,
                            etag_timeout=60)
                        done = True
                        break
                    except Exception as e:
                        wait = min(5 * attempt, 30)
                        self._log("⚠️ 第 %d 次中断：%s · %d 秒后从断点续传" % (attempt, e, wait))
                        time.sleep(wait)
                if done:
                    self._log("✅ 下载完成 models/%s · 共 %.1f GB · 用时 %.1f 分钟"
                              % (name, dir_gb(target), (time.time() - t0) / 60))
                else:
                    self._log("❌ 下载失败：重试 20 次仍不通，检查网络或代理")
            finally:
                stop_watch.set()
        self._dl = threading.Thread(target=run, daemon=True)
        self._dl.start()
        return {"ok": True, "target": target}

    # ------------------------------------------------------------ js_api：杂项
    def open_path(self, path):
        p = _abs_path(str(path or ""))
        if os.name != "nt" or not p or not os.path.exists(p):
            return {"ok": False, "msg": "路径不存在：" + str(path)}
        try:
            os.startfile(p)  # noqa: S606
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "msg": str(e)}

    def open_url(self, url):
        import webbrowser
        webbrowser.open(str(url))
        return {"ok": True}

    # ------------------------------------------------------------ 状态采样
    def _sample_vram(self):
        try:
            import torch
            if torch.cuda.is_available():
                free, total = torch.cuda.mem_get_info()
                self.st["vram_used"] = round((total - free) / 2**30, 1)
                self.st["vram_total"] = round(total / 2**30, 1)
        except Exception:
            pass

    def _refresh_gallery_count(self):
        out_dir = _abs_path(self.cfg["console"]["output_dir"])
        try:
            self.st["img_count"] = sum(1 for n in os.listdir(out_dir)
                                       if n.lower().endswith(IMG_EXT))
        except OSError:
            self.st["img_count"] = 0


def build_html():
    """把 ui/shell.html + css/ + js/ 拼成单文件 HTML（顺序见 ui/assemble.py）。

    用 create_window(html=...) 而不是 url=file://...：实测 WebView2 加载 file:// +
    外链子资源首帧要 8 秒以上，内联后秒开；MIC_DEV=1 时额外内联 mock.js，
    便于直接用浏览器看界面、截图。产物阶段走 _html_bundle（构建期生成，不进版本库）。
    """
    try:
        from _html_bundle import HTML as bundled
    except ImportError:
        bundled = ""
    if bundled and not os.path.isdir(os.path.join(_HERE, "ui", "css")):
        return bundled
    return assemble.assemble(mock=bool(os.environ.get("MIC_DEV")))


def _say_already_running():
    if os.name != "nt":
        return
    box = ctypes.windll.user32.MessageBoxW
    box.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    box.restype = ctypes.c_int
    box(None, "生图控制台已经在运行了，已为你切换到已打开的窗口", APP_NAME, 0x40)


def _fatal(tb):
    if os.name != "nt":
        return
    tail = str(tb)[-1500:]
    box = ctypes.windll.user32.MessageBoxW
    box.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    box.restype = ctypes.c_int
    box(None, "程序没起来，最后一段错误：\n\n%s\n\n完整堆栈见 logs\\run.log" % tail,
        APP_NAME, 0x10)


def _lock_paths():
    base = os.path.join(os.environ.get("APPDATA") or ROOT, "QwenImgConsole")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "console_single.lock"), r"\\.\pipe\QwenImgConsole_Single"


def main():
    single_path, single_pipe = _lock_paths()
    single = single_instance.SingleInstance(path=single_path, pipe=single_pipe)
    if not single.acquire():
        single.notify_existing()
        _say_already_running()
        return
    app = App()
    if app.cfg["api"].get("enabled"):
        app.api_set({})          # 上次开着 API：这次启动自动恢复监听
    window = webview.create_window(
        app.cfg.get("app_title", APP_NAME),
        html=build_html(),
        js_api=app,
        width=WIN_W, height=WIN_H, min_size=(MIN_W, MIN_H),
        frameless=True, easy_drag=False, shadow=True, resizable=True,
        confirm_close=False,
        background_color="#03141f",
        text_select=True,
    )
    # Window 只挂在 _ 开头的属性上：pywebview 的 JS 桥扫描器会跳过下划线属性，
    # 否则会递归进 .NET 对象图，日志刷屏并拖慢启动
    app.attach(window)
    window.events.closing += app.on_closing
    window.events.shown += lambda: install_guard(window)
    single.serve(lambda: single.raise_to_front(_hwnd(window)))
    window.events.closing += single.release
    atexit.register(single.release)
    webview.start(gui=os.environ.get("QIC_GUI") or "edgechromium", private_mode=False)


def _hwnd(window):
    try:
        return int(window.native.Handle.ToInt32())
    except Exception:
        return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # pythonw 起的时候没有黑框：崩在半路也必须留现场 + 说句人话，
        # 否则用户看到的只是「双击了没反应」
        tb = traceback.format_exc()
        sys.stderr.write(tb)
        _fatal(tb)
        raise SystemExit(1)
