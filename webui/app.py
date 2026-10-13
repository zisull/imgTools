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
import ctypes
import io
import json
import os
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for _p in (_HERE, os.path.join(_HERE, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 界面完全本地、外部请求全在 Python 后端：WebView2 一律直连，不碰系统代理。
# 否则代理软件（Clash 等）一旦把 loopback 也劫持，内置服务会被超时拦掉、界面白屏。
os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--no-proxy-server")

import webview  # noqa: E402

import assemble  # noqa: E402  # ui/assemble.py：css/js 拼装顺序的唯一来源
import single_instance  # noqa: E402
from window_guard import WindowCtl, install_guard  # noqa: E402

APP_NAME = "Qwen 生图控制台"
APP_VERSION = "0.2.0-m2"
CFG_PATH = os.path.join(ROOT, "config.json")
# 无框窗口尺寸（逻辑像素，与前端 CSS px 同量纲）；min 与 win.js/win_set 下限同一份
WIN_W, WIN_H = 1280, 800
MIN_W, MIN_H = 980, 620

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")

DEFAULT_CFG = {
    "app_title": APP_NAME, "theme": "tide", "mode": "dark",
    "layout": "flat", "sidebar_min": False, "notify": True, "last_tab": "t_ov",
    "open": {},
    "console": {"model_dir": "models/Qwen-Image-2.1-Turbo", "output_dir": "outputs",
                "quant": "fp8", "offload": True},
    "gen": {"prompt": "", "negative": "", "size": "1024x1024", "steps": "8",
            "seed": -1, "count": 1, "kv_cache": True},
    "api": {"enabled": False, "host": "127.0.0.1", "port": 8765, "token": ""},
    "nav": [
        {"id": "t_ov", "type": "tab", "name": "概览", "icon": "home", "page": "overview"},
        {"id": "t_gen", "type": "tab", "name": "文生图", "icon": "flower", "page": "t2i"},
        {"id": "t_gal", "type": "tab", "name": "画廊", "icon": "image", "page": "gallery"},
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


def _fd(name):
    """pywebview 6 用 FileDialog 枚举，旧版是 webview.XXX_DIALOG 常量；兼容取。"""
    fd = getattr(webview, "FileDialog", None)
    return getattr(fd, name) if fd is not None else getattr(webview, name + "_DIALOG")


class App(WindowCtl):
    def __init__(self):
        self.cfg = json.loads(json.dumps(DEFAULT_CFG))
        self._load_cfg()
        self._lock = threading.Lock()
        self._logs = []            # [seq, hh:mm:ss, text]
        self._seq = 0
        self._window = None
        self._thread = None
        self._stop = threading.Event()
        self.mgr = None            # PipelineMgr：第一次载入时才 import（拉 torch）
        self._thumbs = {}          # (path, mtime) -> data url，缩略缓存
        self.st = {
            "running": None, "status": "就绪", "done": 0, "total": 0,
            "model_loaded": False, "model_name": "Qwen-Image-2.1-Turbo",
            "quant": self.cfg["console"].get("quant", "fp8"),
            "vram_used": 0.0, "vram_total": 12.0,
            "img_count": 0, "last_sec": 0.0, "last_image": "",
            "api_on": False, "api_url": "",
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
        missing = [json.deepcopy(n) for p, n in known.items() if p not in have]
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

    def _logs_since(self, cursor):
        with self._lock:
            return [x for x in self._logs if x[0] > (cursor or 0)]

    # ------------------------------------------------------------ js_api：取数
    def boot(self):
        return {"cfg": self.cfg, "state": self._snap(),
                "version": APP_VERSION, "default_nav": DEFAULT_CFG["nav"]}

    def poll(self, cursor=0):
        self._sample_vram()
        return {"seq": self._seq, "logs": self._logs_since(cursor), "state": self._snap()}

    def refresh_stats(self):
        self._refresh_gallery_count()
        self._sample_vram()
        return {"ok": True, "state": self._snap()}

    def _snap(self):
        return json.loads(json.dumps(self.st))

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
    def pick(self, kind="file"):
        w = self._window
        if w is None:
            return ""
        try:
            if kind == "dir":
                r = w.create_file_dialog(_fd("FOLDER"))
            else:
                r = w.create_file_dialog(_fd("OPEN"), file_types=tuple("图片 (*%s)" % e for e in IMG_EXT))
        except Exception as e:
            self._log("⚠️ 文件对话框没打开：%s" % e)
            return ""
        if not r:
            return ""
        return r[0] if isinstance(r, (tuple, list)) else str(r)

    def drop_path(self, candidates, kind="file"):
        """拖进来的路径列表 → 挑一个真实存在的绝对路径（相对路径按项目根找）。"""
        for c in candidates or []:
            p = str(c).replace("file:///", "").replace("file://", "")
            p = os.path.normpath(p)
            if os.path.isabs(p) and os.path.exists(p):
                return {"ok": True, "path": p}
            q = _abs_path(p)
            if os.path.exists(q):
                return {"ok": True, "path": q}
        return {"ok": False, "msg": "没找到拖进来的文件，请用「浏览」选"}

    # ------------------------------------------------------------ js_api：窗口
    def attach(self, window):
        self._window = window

    def on_closing(self):
        """关闭收尾：叫停后台线程 → 存配置。绝不能 return False（=取消关闭）。"""
        self._stop.set()
        self._save_cfg()
        return None

    # ------------------------------------------------------------ js_api：引擎
    def _busy(self):
        return self.st["running"] is not None

    def _launch(self, key, fn):
        self.st["running"] = key
        self._stop.clear()
        self._thread = threading.Thread(target=fn, daemon=True)
        self._thread.start()

    def _get_mgr(self):
        if self.mgr is None:
            from pipeline_mgr import PipelineMgr
            self.mgr = PipelineMgr(log=self._log)
        return self.mgr

    def load_model(self):
        if self._busy():
            return {"ok": False, "msg": "有任务在跑：" + str(self.st["running"])}
        self._launch("load", self._do_load)
        return {"ok": True}

    def _do_load(self, chain_gen=None):
        try:
            c = self.cfg["console"]
            self.st["status"] = "载入模型…"
            self._get_mgr().load(_abs_path(c["model_dir"]),
                                 offload=bool(c.get("offload", True)),
                                 quant=c.get("quant", "fp8"))
            self.st["model_loaded"] = True
            self.st["status"] = "模型已载入"
            self._log("✅ 模型已载入")
            if chain_gen:
                self._do_gen(chain_gen)
                return
        except Exception as e:
            self._log("❌ 模型载入失败：%s" % e)
            self.st["status"] = "模型载入失败"
        finally:
            if self.st["running"] == "load":
                self.st["running"] = None

    def unload_model(self):
        if self._busy():
            return {"ok": False, "msg": "有任务在跑：" + str(self.st["running"])}
        if self.mgr is None or self.mgr.pipe is None:
            return {"ok": False, "msg": "模型本来就没在显存里"}
        try:
            self.mgr.unload()
            self.st["model_loaded"] = False
            self.st["status"] = "模型已卸载"
            self._log("已卸载模型 · 显存归还")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def start_gen(self, payload=None):
        if self._busy():
            return {"ok": False, "msg": "有任务在跑：" + str(self.st["running"])}
        g = dict(self.cfg.get("gen") or {})
        g.update(payload or {})
        if not str(g.get("prompt", "")).strip():
            return {"ok": False, "msg": "提示词是空的，先写点想要什么"}
        steps = int(g.get("steps") or 8)
        self.st["total"] = steps
        if self.mgr is None or self.mgr.pipe is None:
            self._log("模型未载入：先载入，随后自动开始生成")
            self._launch("load", lambda: self._do_load(chain_gen=g))
            return {"ok": True, "total": steps}
        self._launch("gen", lambda: self._do_gen(g))
        return {"ok": True, "total": steps}

    def _do_gen(self, g):
        self.st["running"] = "gen"
        steps = int(g.get("steps") or 8)
        try:
            w, h = (int(x) for x in str(g.get("size", "1024x1024")).lower().split("x"))
        except ValueError:
            w = h = 1024
        count = max(1, int(g.get("count") or 1))
        est = 4.0 if w * h <= 1024 * 1024 else 10.0   # 进度条的估时（M3 换成引擎回调）
        ticker_stop = threading.Event()

        def tick():
            t0 = time.time()
            while not ticker_stop.wait(0.5):
                self.st["done"] = min(steps - 1, int((time.time() - t0) / (est / 1.0)))
                self.st["status"] = "去噪 %d/%d" % (self.st["done"], steps)
        threading.Thread(target=tick, daemon=True).start()
        try:
            mgr = self._get_mgr()
            if mgr.pipe is None:
                mgr.load(_abs_path(self.cfg["console"]["model_dir"]),
                         offload=bool(self.cfg["console"].get("offload", True)),
                         quant=self.cfg["console"].get("quant", "fp8"))
                self.st["model_loaded"] = True
            out_dir = _abs_path(self.cfg["console"]["output_dir"])
            os.makedirs(out_dir, exist_ok=True)
            self._log("🚀 开始生成：%dx%d · %d 步 × %d 张" % (w, h, steps, count))
            for i in range(count):
                if self._stop.is_set():
                    self._log("⏹ 已停止（第 %d 张之后）" % (i + 1))
                    self.st["status"] = "已停止"
                    break
                seed = int(g.get("seed") if g.get("seed") is not None else -1)
                if seed < 0:
                    seed = int(time.time()) % 10 ** 8
                t0 = time.time()
                img = mgr.generate(str(g.get("prompt", "")), width=w, height=h,
                                   steps=None if steps == 8 else steps,
                                   seed=seed, kv_cache=bool(g.get("kv_cache", True)))
                dt = time.time() - t0
                name = "gen_%s.png" % time.strftime("%Y%m%d_%H%M%S")
                path = os.path.join(out_dir, name)
                img.save(path)
                self.st["last_sec"] = round(dt, 1)
                self.st["last_image"] = path
                self.st["done"] = steps
                self._log("✅ (%d/%d) 已保存：%s · %.1f 秒" % (i + 1, count, name, dt))
                self._refresh_gallery_count()
            else:
                self.st["status"] = "✅ 完成"
                self._log("── 结束 ──")
        except Exception as e:
            self._log("❌ 生成失败：%s" % e)
            self.st["status"] = "生成失败"
        finally:
            ticker_stop.set()
            self.st["running"] = None

    def stop(self, key=None):
        if not self._busy():
            return {"ok": False, "msg": "没有运行中的任务"}
        self._stop.set()
        self._log("⏹ 已请求停止：当前这张完成后中断")
        return {"ok": True}

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
                if im.mode not in ("RGB", "L"):
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
        self.st["img_count"] = len(items)
        return {"ok": True, "items": items}

    def gallery_delete(self, path):
        p = self._in_output(path)
        if not p:
            return {"ok": False, "msg": "这个文件不在输出目录里，不动它"}
        try:
            os.remove(p)
            self._log("已删除：" + os.path.basename(p))
            self._refresh_gallery_count()
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "msg": str(e)}

    def gallery_clear(self):
        out_dir = _abs_path(self.cfg["console"]["output_dir"])
        n = 0
        for it in self._gallery_items(limit=10000):
            try:
                os.remove(it["file"])
                n += 1
            except OSError:
                pass
        self._log("已清空输出目录：%d 张" % n)
        self._refresh_gallery_count()
        return {"ok": True, "removed": n}

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
    main()
