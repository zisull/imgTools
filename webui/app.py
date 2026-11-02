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
import shutil
import sys
import threading
import time
import traceback
import urllib.parse
from collections import OrderedDict

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for _p in (_HERE, os.path.join(_HERE, "ui"), os.path.join(ROOT, "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LOG_DIR = os.path.join(ROOT, "logs")
RUN_LOG = os.path.join(LOG_DIR, "run.log")

# pythonw.exe 自己没有控制台。不传这个创建标志，Windows 会给每个子进程
# （pip / git / venv）单独开一个空终端窗口——用户看到的「补全时弹终端」就是这个。
NO_CONS = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW


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
    # 只在「双击启动的主程序」时弹框；被单测/自测脚本 import 时绝不弹——
    # MessageBoxW 会阻塞，无显示环境的自测会卡在这里出不来。
    if os.name == "nt" and __name__ == "__main__":
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                "生图控制台起不来：依赖导入失败，请先双击根目录的 启动.bat 补环境。\n\n"
                + traceback.format_exc()[-1200:] + "\n\n完整堆栈见 logs\\run.log",
                "Qwen 生图控制台", 0x10)
        except Exception:
            pass
    raise SystemExit(1)

APP_NAME = "Qwen 生图控制台"
APP_VERSION = "0.2.0-m2"
# 测试用 QIC_CONFIG 指到自己的临时文件：回归脚本会改 cfg 再落盘，
# 不能让它们在用户正在用的 config.json 里留下临时目录。
CFG_PATH = os.environ.get("QIC_CONFIG") or os.path.join(ROOT, "config.json")
# 无框窗口尺寸（逻辑像素，与前端 CSS px 同量纲）；min 与 win.js/win_set 下限同一份
WIN_W, WIN_H = 1280, 800
MIN_W, MIN_H = 980, 620

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
# H3 出片走 SaveVideo(format=auto) → mp4；其余几种是给人手动丢进输出目录的存量片也一起认
VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv")
MEDIA_EXT = IMG_EXT + VIDEO_EXT
# pywebview 的过滤串：描述 + 括号内分号分隔的扩展名（空格分隔会被 parse_file_type 拒）
_IMG_FILTER = "图片 (*" + ";*".join(IMG_EXT) + ")"

# 导航结构版本：v3 起概览/透明素材/提示词工坊/API 服务四页并进了别的页，日志单开一页；
# v4 把 Moss 生图并进生图页、导航改成不套分组的两字名称；
# v5 按用户要求把分组收回来（名称仍统一两字，只归组、不改叫法）；
# v6 词库并进生图页（灵感行 + 全览面板），少一页；
# v7 加「视频」页（本地 H3），环境从一页拆成按模型的一组图；
# v8 加「云端」页：多账号登录态与浏览器保活（生成仍走协议，浏览器只负责登录）。
# v9 改叫「H3云端」（这页服务的是 H3/RunningHub 那条线）。
# 比它旧的配置在载入时按新默认表重排一次（只把用户改过的标签名带过去），见 _restructure_nav。
NAV_VER = 9

# 各版默认表用过的标签名。换代重排时，名字落在这张表里说明「用户没自己改过」，
# 直接换成新默认名；不在表里的才是他改的，原样保留。
LEGACY_TAB_NAMES = {
    "概览", "文生图", "透明素材", "图像编辑", "局部编辑", "提示词工坊", "Moss 生图",
    "画廊", "环境与模型", "模型管理", "日志", "设置", "API 服务",
    "生图", "编辑", "重绘", "词库", "环境",
    "视频", "基础", "千问",
    "云端",
}

# 反向提示词的出厂默认：以前出厂是空的，多数人不会填，图就照着常见失败出。
# 这一串必须与前端 webui/ui/js/core/prompts.js 的 NEG_BASE 一字不差。
NEG_DEFAULT = "低画质，模糊，噪点，压缩失真，水印，签名，文字，多余手指，肢体畸形，面部扭曲，比例失衡，过曝，死黑，裁切"

# Moss 三档质量。极速档靠 DMD LoRA（LoRA 是结构性节点，strength=0 也照样加载合并），
# 所以必须走 fast 模板；均衡/精修都不挂 LoRA、只差步数，共用 full 模板。
MOSS_TIERS = {
    "fast": {"label": "极速 8 步", "template": "workflow_fast.json", "steps": 8, "cfg": 1.0},
    "mid": {"label": "均衡 25 步", "template": "workflow_full.json", "steps": 25, "cfg": 3.0},
    "full": {"label": "精修 50 步", "template": "workflow_full.json", "steps": 50, "cfg": 3.0},
}

DEFAULT_CFG = {
    "app_title": APP_NAME, "theme": "tide", "mode": "dark",
    "layout": "tree", "sidebar_min": False, "notify": True, "last_tab": "t_gen",
    "nav_ver": NAV_VER, "open": {},
    # 首启欢迎页：没选过引擎就先把这一屏挡在生图页前面，选完落 true；设置页留一颗「重看欢迎页」
    "welcomed": False,
    # 当前激活的生图引擎：qwen（diffusers）| moss（内嵌 ComfyUI）。同一时间只有一个常驻显存。
    "engine": "qwen",
    # 环境开关：{环境 id: true/false}。关掉的环境不体检、不进待补、不提醒，功能页一并收起。
    # 这张表只管「人想要哪几路」，默认值由后端按清单算（必选=开，可选=装过才开），见 _env_on。
    # 取代了旧的 console_mode（both/qwen/moss 三态表达不了「H3 单独开」）。
    "env_on": {},
    "console": {"model_dir": "envs/qwen/models/Qwen-Image-2.1-Turbo", "output_dir": "outputs",
                "quant": "fp8", "offload": True},
    # Moss 引擎（MOSS-Image via ComfyUI）：档位 daily=日常质量档 / yield=让出显存档
    # size=custom 时走 cw/ch（前端折成 16 倍数的 WxH 再发）
    "moss": {"comfyui_dir": "comfyui", "port": 8876, "tier": "daily", "extra_args": [],
             "output_dir": "outputs",
             "prompt": "", "negative": NEG_DEFAULT, "size": "1024x1024", "cw": 1024, "ch": 1024,
             "seed": -1, "count": 1,
             "quality": "fast"},  # quality: fast=8 步 DMD 极速 / mid=25 步均衡 / full=50 步精修
    # 千问出图：mode=gen 普通 / rgba 透明底（原「透明素材」页并到这里，只差后端那一个 mode）
    "gen": {"mode": "gen", "prompt": "", "negative": NEG_DEFAULT, "size": "1024x1024",
            "cw": 1024, "ch": 1024,
            "steps": "8", "seed": -1, "count": 1, "kv_cache": True},
    "edit": {"prompt": "", "negative": NEG_DEFAULT, "res": "512", "steps": "8",
             "seed": -1, "count": 1, "kv_cache": True},
    "inpaint": {"prompt": "", "negative": NEG_DEFAULT, "res": "512", "steps": "8",
                "seed": -1, "count": 1, "kv_cache": True, "brush": 48},
    # 本地 H3 视频：秒数是模型帧数网格上的取值（24fps、17k+5），参考图留空＝文生视频
    # exec=local 走本机 ComfyUI（占显存）；cloud 走 RunningHub 那份工作流（不占显存，要登录）
    # 两条通道共用上面这四个键：换通道只换「在哪跑」，不换「跑什么」
    # 尺寸只有一个来源＝size（WxH，界面那对 P 档×朝向落它）；老配置里的 tier/ratio 仍认，但不再写
    "video": {"prompt": "", "seconds": 5, "size": "1344x768", "cw": 1344, "ch": 768,
              "first": "", "seed": -1, "exec": "local", "cloud_acct": ""},
    "lib": {"cat": "person"},           # 生图页灵感行与词库全览共用的当前分类
    "api": {"enabled": False, "lan": False, "port": 8765,
            "token": "", "no_token": False,
            # API 不传 engine/model 时用谁：follow=跟随控制台当前激活的引擎
            "def_engine": "follow", "def_size": "1024x1024"},
    # 云端账号：一只调试浏览器 + 多份登录态快照（data/cloud/），浏览器只负责登录与保活
    # workflow=云端出片用的那份 H3 工作流（必须是这个号在网页上跑通过的）
    "cloud": {"port": 9333, "base": "https://www.runninghub.cn", "login_url": "",
              "browser": "", "domains": ["runninghub.cn"],
              "keep": True, "keep_min": 30, "concurrency": 1,
              "workflow": "", "wf_host": "", "exec_tag": "Plus", "poll_sec": 5, "gen_timeout": 1800},
    # 导航：分组套一页一个标签；组名与标签名统一两字，竖排对齐
    "nav": [
        {"id": "g_out", "type": "group", "name": "出图", "icon": "flower", "children": [
            {"id": "t_gen", "type": "tab", "name": "生图", "icon": "flower", "page": "t2i"},
            {"id": "t_edit", "type": "tab", "name": "编辑", "icon": "wand", "page": "edit"},
            {"id": "t_inp", "type": "tab", "name": "重绘", "icon": "brush", "page": "inpaint"},
            {"id": "t_vid", "type": "tab", "name": "视频", "icon": "film", "page": "video"},
        ]},
        # 环境按模型一页一个：开关、明细、补齐都在自己那页，不再挤成一长串分区
        {"id": "g_env", "type": "group", "name": "环境", "icon": "db", "children": [
            {"id": "t_envb", "type": "tab", "name": "基础", "icon": "db", "page": "env_base"},
            {"id": "t_envq", "type": "tab", "name": "千问", "icon": "flower", "page": "env_qwen"},
            {"id": "t_envm", "type": "tab", "name": "Moss", "icon": "wave", "page": "env_moss"},
            {"id": "t_envh", "type": "tab", "name": "H3", "icon": "film", "page": "env_h3"},
        ]},
        {"id": "g_sys", "type": "group", "name": "系统", "icon": "cog", "children": [
            {"id": "t_gal", "type": "tab", "name": "画廊", "icon": "image", "page": "gallery"},
            {"id": "t_cloud", "type": "tab", "name": "H3云端", "icon": "globe", "page": "cloud"},
            {"id": "t_log", "type": "tab", "name": "日志", "icon": "hist", "page": "logs"},
            {"id": "t_set", "type": "tab", "name": "设置", "icon": "cog", "page": "settings"},
        ]},
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


def _snap16(x, lo=16, hi=2048):
    """贴到 16 的倍数，四舍五入——必须和界面里的 C.a16 同一套舍入。

    Python 的 round() 是「.5 向偶数」：宽填 840 时后端给 832、界面写 848，
    差的那 16 像素正好落在「界面承诺」和「实际出片」之间，最难查。
    """
    return max(lo, min(hi, int(float(x) / 16.0 + 0.5) * 16))


_seed_lock = threading.Lock()
_seed_seq = [0]


def _rand_seed():
    """「随机种子」= 毫秒时间 + 进程内自增序号。

    以前用 int(time.time()) % 1e8（只有秒），连点两下开始很可能落在同一秒：
    同一组参数 + 同一个种子 = 同一张图（ComfyUI 还会命中节点缓存秒回），
    用户看到的就是「重复生图没出新图、画面还是上一张」。
    """
    with _seed_lock:
        _seed_seq[0] += 1
        n = _seed_seq[0]
    return (int(time.time() * 1000) * 1000 + n) % 10 ** 12


def _same_file(a, b):
    """两张图字节级相同？用来识别「固定种子 + 同参数」重跑出来的同一张。"""
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False


def _fd(name):
    """pywebview 6 用 FileDialog 枚举，旧版是 webview.XXX_DIALOG 常量；兼容取。"""
    fd = getattr(webview, "FileDialog", None)
    return getattr(fd, name) if fd is not None else getattr(webview, name + "_DIALOG")


def _checkerboard(size, cell=16):
    """给透明图铺的灰白棋盘底（PIL 无内置，手画一张 RGB）。

    先画 2×2 格的小块，再横着拼成一条、竖着铺满：逐像素 set 在 1024² 上是 100 万次
    Python 循环，一张透明缩略图能吃掉几十毫秒，画廊一刷就是几百张。
    """
    from PIL import Image
    w, h = max(1, int(size[0])), max(1, int(size[1]))
    tile = Image.new("RGB", (cell * 2, cell * 2), (255, 255, 255))
    gray = Image.new("RGB", (cell, cell), (210, 210, 210))
    tile.paste(gray, (cell, 0))
    tile.paste(gray, (0, cell))
    strip = Image.new("RGB", (w, cell * 2), (255, 255, 255))
    for x in range(0, w, cell * 2):
        strip.paste(tile, (x, 0))
    bg = Image.new("RGB", (w, h))
    for y in range(0, h, cell * 2):
        bg.paste(strip, (0, y))          # 最后一条超出底边会被 PIL 自己裁掉
    return bg


class App(WindowCtl):
    def __init__(self):
        self.cfg = json.loads(json.dumps(DEFAULT_CFG))
        # 锁要在读配置之前：导航换代（NAV_VER 涨了）会让 _load_cfg 当场回写一次盘
        self._cfg_lock = threading.RLock()   # 写 config.json：同一时刻只许一个线程碰 .tmp
        self._env_spec = None    # 环境清单缓存：_load_cfg 要把开关默认值落到配置里，得先能读清单
        self._load_cfg()
        self._lock = threading.Lock()
        self._task_lock = threading.Lock()   # 「查空闲 + 占位」必须一气呵成
        self._logs = []            # [seq, hh:mm:ss, text]
        self._seq = 0
        self._window = None
        self._thread = None
        self._stop = threading.Event()
        self.mgr = None            # PipelineMgr：第一次载入时才 import（拉 torch）
        self.moss = None           # MossManager：切到 Moss 引擎时才建（拉 moss_mgr，纯 stdlib）
        self._api = None           # ApiServer：API 页开启时才 import（拉 fastapi）
        self._dl = None            # 模型下载线程（同一时间只允许一个）
        self._cloudx = None        # 云端账号：DrissionPage/浏览器都在第一次用云端的页时才起
        self._cloud_lock = threading.RLock()   # 账号操作互斥：并发固定 1（一只浏览器）
        # 云端出片占着那只共用浏览器（点运行 + 轮询），这期间账号操作一律让路
        self._cloud_gen = threading.Event()
        self._h3cloud = None       # cloudkit.gen.CloudH3：真要用云端才建
        self._thumbs = OrderedDict()  # (path, mtime, wide) -> data url，缩略缓存（LRU 逐出）
        from store import Store
        self.store = Store(os.path.join(ROOT, "data", "history.db"))
        self.store.init()
        # 删除撤销：文件先移进回收站而不是真删，栈里记着原路径与历史参数
        self._trash_dir = os.path.join(ROOT, "data", "trash")
        self._trash = []
        self._trash_lock = threading.Lock()
        self._trash_purge()
        self.st = {
            "running": None, "status": "就绪", "done": 0, "total": 0,
            "model_loaded": False, "model_name": "Qwen-Image-2.1-Turbo",
            "quant": self.cfg["console"].get("quant", "fp8"),
            "vram_used": 0.0, "vram_total": 12.0,
            "img_count": 0, "last_sec": 0.0, "last_image": "",
            # dup_last：这一张和上一张字节相同（固定种子）；last_fail：上一轮为什么没出图
            "dup_last": False, "last_fail": "",
            "api_on": False, "api_url": "", "t_start": 0, "elapsed": 0,
            # 载入进度：黑框去掉后，权重加载这条唯一「看得见」的路就是这两个字段
            "load_pct": 0, "load_stage": "",
            # 环境补全：换电脑 clone 后缺包缺权重，靠这一项在界面上补齐
            # env_todo_by 按环境拆：欢迎页与每个环境子页各读自己那一格；
            # 关掉的环境恒为 0（体检那一步就没算它）。
            # env_on 也当状态维护（改动时同步一次，不在每轮快照里现算）：
            # 这张表决定导航里哪些功能页存在，界面每一处都读同一份。
            "env_busy": False, "env_todo": None, "env_todo_by": {}, "env_on": {},
            # 补全到第几步、这一步叫什么；dl 是当前下载的字节进度（由 envkit/download 回调写）
            "env_step": 0, "env_steps": 0, "env_label": "", "dl": {},
            # 引擎与 Moss 档位：running/done/total/model_loaded/last_image 这些两引擎共用
            # moss_installed 三态：None=还没查过（界面不许拿它下结论）、True/False=查过
            "engine": "qwen", "moss_tier": "daily", "moss_installed": None,
            "comfyui_on": False, "comfyui_url": "", "comfyui_loaded": False,
            # 云端账号：busy=正在做什么（空=闲），msg=上一条结果/错误（界面原样显示）
            "cloud_busy": "", "cloud_msg": "",
        }
        self._refresh_gallery_count()
        self._sync_env_on()
        self._prepare_envs()
        self._log("就绪 · %s" % APP_NAME)

    # ------------------------------------------------------------ 配置
    def _load_cfg(self):
        try:
            with open(CFG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            # 盘上还没有配置（首启／换机）：不能就此早退，否则 env_on 停在空表——
            # 空表在体检里按「没写＝开」数待补、在开关那格按「没写＝关」归零，
            # 两边对不上，连「千问环境已关闭」这句拦路话都会在首启冒出来。
            saved = {}
        if saved:
            _deep_merge(self.cfg, saved)
            # 透明素材并进文生图（gen.mode）后这一块没用了；老配置里留着只会让人以为还有那页
            self.cfg.pop("rgba", None)
        self._migrate_env_on(saved)
        # 导航结构以整块为准（用户可能重排过），但结构换代要按新默认表重排一次
        if int(saved.get("nav_ver") or 1) < NAV_VER and self._restructure_nav():
            self.cfg["nav_ver"] = NAV_VER
            self._save_cfg()
        self._repair_nav()

    # ------------------------------------------------------------ 环境开关
    def _migrate_env_on(self, saved):
        """把旧的三态 console_mode 换成按环境逐个开的 env_on，并把默认值落实。

        console_mode 表达不了「生图两路都要、但视频先关着」，而且它只管显示不管体检：
        界面收走了功能页，环境页照旧提醒「还差 41 GB」——用户要的开关是「关掉就当它不存在」。
        这里只在配置里从没写过 env_on 时按老值推一次，之后 env_on 就是唯一真源。
        """
        mode = str(self.cfg.pop("console_mode", "") or "")
        raw = self.cfg.get("env_on")
        if not isinstance(raw, dict):
            raw = {}
        on = dict(raw)
        if not on:
            want = {"both": ("qwen", "moss"), "qwen": ("qwen",), "moss": ("moss",)}.get(mode)
            if want is not None:
                for eid in ("qwen", "moss"):
                    on[eid] = eid in want
            # 开关表换代：老配置里那三种模式答不了新的欢迎页（三路各一颗开关），
            # 把这一屏放回来问一次——老配置里 welcomed 早就为真，不重置就永远看不到。
            self.cfg["welcomed"] = False
        self.cfg["env_on"] = self._env_defaults(on)

    def _env_defaults(self, on=None):
        """开关表的完整形态：清单里每个环境一行，缺的按「必选=开 / 可选=装过才开」补。

        落实成具体的 true/false 写回配置，是为了让 _snap 每 0.8 秒带出去时不必再碰盘，
        也让 config.json 打开就能看懂自己开着哪几路。
        """
        on = dict(on or {})
        try:
            from envkit import spec as sp
            spec = self._spec()
        except Exception:
            return on
        for e in spec.get("envs") or []:
            eid = e["id"]
            if eid in on:
                on[eid] = bool(on[eid])
                continue
            default = not e.get("optional")
            if e.get("optional"):
                try:
                    default = sp.env_installed(ROOT, spec, eid)
                except Exception:
                    default = False
            on[eid] = bool(default)
        return on

    def _env_on(self):
        """当前开着的环境表（含 base 恒开）。配置里多出清单没有的 id 会被忽略。"""
        out = {"base": True}
        out.update({str(k): bool(v) for k, v in (self.cfg.get("env_on") or {}).items()})
        return out

    def _sync_env_on(self):
        """把开关表刷进状态：_snap 每 0.8 秒原样带出去，不在这条路上现算。

        只在配置真的改动时调（启动落实默认值、开关按下去、体检跑完）；
        表整体换成一个新 dict，绝不原地改，快照那份共享引用才不会被后续改动带跑。
        """
        self.st["env_on"] = self._env_on()

    # ------------------------------------------------------------ 环境目录
    def _spec(self):
        if self._env_spec is None:
            from envkit import spec as sp
            self._env_spec = sp.load_spec(ROOT)
        return self._env_spec

    def _prepare_envs(self):
        """启动时把环境目录理顺：旧布局迁到 envs/、配置里的旧路径换新、权重目录写进 ComfyUI。

        全是幂等操作（目标在就跳过），只做几次 listdir，不碰权重内容。
        放在窗口起来之前：ComfyUI 起子进程时就要读 extra_model_paths.yaml。
        """
        try:
            from envkit import spec as sp
            spec = self._spec()
            for e in spec.get("envs") or []:
                os.makedirs(sp.env_models_dir(ROOT, spec, e["id"]), exist_ok=True)
            acts = sp.migrate_layout(ROOT, spec=spec)
            if acts:
                self._log("📦 环境目录已整理：%d 项（详情见启动日志）" % len(acts))
            before = json.dumps(self.cfg.get("console") or {}, sort_keys=True)
            sp.migrate_cfg_paths(ROOT, self.cfg)
            if json.dumps(self.cfg.get("console") or {}, sort_keys=True) != before:
                self._save_cfg()
            if os.path.isdir(sp.runtime_dir(ROOT, spec)):
                sp.write_extra_model_paths(ROOT, spec)
        except Exception as e:
            self._log("⚠️ 环境目录没理好：%s" % e)

    @staticmethod
    def _nav_ids(nodes):
        out = set()

        def walk(ns):
            for n in ns or []:
                out.add(n.get("id"))
                walk(n.get("children"))
        walk(nodes)
        return out

    def _restructure_nav(self):
        """按新的默认表重排导航：v5 起恢复分组（出图 / 系统），标签名仍是统一两字。
        只把用户自己改过的标签名带过去；分组名与排布用默认表。"""
        old = {}

        def collect(nodes):
            for n in nodes or []:
                if n.get("type") == "tab":
                    old[n.get("page")] = n.get("name")
                collect(n.get("children"))
        collect(self.cfg.get("nav") or [])

        def build(nodes):
            out = []
            for n in nodes:
                m = copy.deepcopy(n)
                if m.get("type") == "group":
                    m["children"] = build(m.get("children") or [])
                    if not m["children"]:
                        continue          # 空分组不留
                else:
                    # 只有「从来不是任何一版默认名」的才算用户自己改的名。
                    # 光比对新一版的默认名不行：换代后旧默认名看着也像用户改的，
                    # 结果永远还原不回统一的两字名称。
                    prev = old.get(m.get("page"))
                    if prev and prev != n.get("name") and prev not in LEGACY_TAB_NAMES:
                        m["name"] = prev
                out.append(m)
            return out

        self.cfg["nav"] = build(DEFAULT_CFG["nav"])
        if self.cfg["last_tab"] not in self._nav_ids(self.cfg["nav"]):
            self.cfg["last_tab"] = DEFAULT_CFG["last_tab"]
        self.cfg["layout"] = DEFAULT_CFG["layout"]   # 换代默认回到分组树（用户要的就是这个形态）
        return True

    def _repair_nav(self):
        known = {}

        def collect(nodes):
            for n in nodes:
                if n.get("type") == "tab":
                    known.setdefault(n.get("page"), n)
                collect(n.get("children") or [])
        collect(DEFAULT_CFG["nav"])
        have = set()

        def walk(nodes):
            for n in nodes:
                if n.get("type") == "tab":
                    have.add(n.get("page"))
                walk(n.get("children") or [])
        walk(self.cfg.get("nav") or [])
        # 代码里已经没有的功能页：入口留着只会点出一张空白页，一律摘掉
        if have - set(known):
            retired = have - set(known)

            def prune(nodes):
                keep = []
                for n in nodes:
                    if n.get("type") == "tab":
                        if n.get("page") in retired:
                            continue
                    else:
                        n["children"] = prune(n.get("children") or [])
                    keep.append(n)
                return keep
            self.cfg["nav"] = prune(self.cfg.get("nav") or [])
        missing = [copy.deepcopy(n) for p, n in known.items() if p not in have]
        if missing:
            self.cfg.setdefault("nav", [])
            self.cfg["nav"] = missing + self.cfg["nav"]

    def _save_cfg(self):
        """原子写：先落临时文件再 os.replace，而且整个「写临时 + 改名」要排队。

        配置里存着令牌、激活模型、导航结构——直接 truncate 原文件再写，
        断电/被强杀正好卡在那中间就留下一份空 JSON，下次打开等于全新装。

        排队是被真窗口点出来的：界面上每改一个控件就存一次，连着敲四个框就是
        四次并发写，A 还在往 config.json.tmp 里灌、B 已经把这个名字 replace 走，
        Windows 回 WinError 32「配置没存上」——用户看到的是每次敲参数都弹警告，
        重启后参数全丢。重试那几跳是给杀软在缝隙里扫一下 config.json 留的。
        """
        with self._cfg_lock:
            tmp = CFG_PATH + ".tmp"
            err = None
            for i in range(4):
                try:
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(self.cfg, f, ensure_ascii=False, indent=1)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, CFG_PATH)
                    return
                except OSError as e:
                    err = e
                    time.sleep(0.15 * (i + 1))
            self._log("⚠️ 配置没存上：%s" % err)

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
        s = dict(self.st)      # st 里全是标量，浅拷贝就够；每 0.8 秒一轮，别拿 json 来回序列化
        s["dl"] = dict(self.st.get("dl") or {})   # 下载进度是 dict，浅拷贝后再给出去
        eng = str(self.cfg.get("engine", "qwen"))
        s["engine"] = eng
        s["moss_tier"] = str((self.cfg.get("moss") or {}).get("tier", "daily"))
        on = bool(self.moss and self.moss.alive())
        s["comfyui_on"] = on if eng == "moss" else False
        # 权重是否真的在显存里：ComfyUI 懒加载，进程活着 ≠ 模型上卡。
        # 界面拿它区分「已就绪，正在搬权重」和「随时能出图」，也是两个档位
        # 显存差异的唯一可见入口（拉起后约 10 秒由预热补齐）。
        s["comfyui_loaded"] = bool(on and eng == "moss" and self.moss.state.loaded_model)
        s["comfyui_url"] = (self.moss.state.url if (eng == "moss" and self.moss) else "")
        if not self._busy():
            # 空闲时按「当前引擎的常驻态」校准模型灯，避免两引擎切换后灯滞留在旧引擎上
            s["model_loaded"] = on if eng == "moss" else bool(
                self.mgr and getattr(self.mgr, "pipe", None) is not None)
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
        # DownloadURL 引号裹在 scheme 后面：file:///"D:\有 空格\x.png"，
        # 上面的 strip('"') 只剥得掉整串首尾，这层得单独剥——留着就把文件名也带上了引号
        s = re.sub(r'^(file:/+/?)\s*"+', r"\1", s, flags=re.I).rstrip('"\'')
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
        t = os.path.normpath(t.strip().strip('"').strip("'").strip())
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
        """关闭收尾：叫停后台线程 → 停 API 监听 → 停 Moss 子进程 → 存配置。绝不能 return False（=取消关闭）。"""
        self._stop.set()
        if self._api is not None:
            try:
                self._api.stop()
            except Exception:
                pass
        if self.moss is not None:
            try:
                self.moss.stop(wait=4.0)   # 关掉内嵌 ComfyUI 子进程，别留孤儿进程占显存
            except Exception:
                pass
        if self._cloudx is not None:
            try:
                self._cloudx["keep"].stop()
                self._cloudx["host"].close()   # 共用调试浏览器是我们拉起的，退出时一起收
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
            self.st["dup_last"] = False     # 上一轮的同图标记不能顺延到新任务
            self.st["last_fail"] = ""
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

    def _get_moss(self):
        if self.moss is None:
            from moss_mgr import MossManager
            self.moss = MossManager(
                comfyui_dir=_abs_path((self.cfg.get("moss") or {}).get("comfyui_dir", "comfyui")),
                port=_to_int((self.cfg.get("moss") or {}).get("port"), 8876, 1, 65535),
                extra_args=list((self.cfg.get("moss") or {}).get("extra_args") or []),
                log=self._log)
        return self.moss

    def _engine_gate(self, eng):
        """这一路的环境关着就不许跑：返回给人的话要说清去哪儿开。

        前端本来就不会把关掉的功能页画出来，这里管的是漏网的那两条路——
        API 服务还认得 engine 参数，老标签页绑定了被收起的功能页也点得到。
        """
        on = self._env_on()
        if eng == "qwen" and on.get("qwen") is False:
            return "千问环境已关闭 · 到「环境 → 千问」那页开启"
        if eng == "moss" and (on.get("moss") is False and on.get("h3") is False):
            return "Moss 环境已关闭 · 到「环境 → Moss」那页开启"
        return ""

    def _ensure_engine(self, name):
        """把常驻显存的引擎切到 name：切走的那个先释放显存，保证同一时间只激活一个。"""
        cur = str(self.cfg.get("engine", "qwen"))
        if cur == name:
            return
        if name == "moss":
            if self.mgr is not None and getattr(self.mgr, "pipe", None) is not None:
                self.mgr.unload()
                self._log("切换引擎：已卸载千问模型，显存让给 Moss")
        else:
            if self.moss is not None and self.moss.occupying():
                self.moss.stop()
                self._log("切换引擎：已停止 Moss（ComfyUI 子进程），显存让给千问")
        self.cfg["engine"] = name
        self.st["engine"] = name
        self._save_cfg()

    def load_model(self):
        if str(self.cfg.get("engine", "qwen")) == "moss":
            if not self._launch("load", lambda: self._do_moss_load()):
                return {"ok": False, "msg": self._busy_msg()}
            return {"ok": True}
        if not self._launch("load", self._do_load):
            return {"ok": False, "msg": self._busy_msg()}
        return {"ok": True}

    def _report_load(self, pct, stage):
        self.st["load_pct"] = pct
        self.st["load_stage"] = stage

    def _report_step(self, done_i, total_i):
        """两个引擎共用的去噪进度回调：停下之后迟到的步数不再写进状态。"""
        if not self._stop.is_set():
            self.st["done"] = done_i
            self.st["total"] = total_i
            self.st["status"] = "去噪 %d/%d" % (done_i, total_i)

    def _chain_gen(self, chain_gen, fn, what):
        """载入/启动完成后接着出图。返回 True=已经接手（外层不用再 release）。"""
        if not chain_gen:
            return False
        if self._stop.is_set():
            self.st["status"] = "已停止"
            self._log("⏹ %s期间已请求停止：跳过本次生成" % what)
            return True
        fn(chain_gen)
        return True

    def _do_load(self, chain_gen=None):
        try:
            self._ensure_engine("qwen")   # 用千问前确保 Moss 不占显存
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
            if self._chain_gen(chain_gen, self._do_gen, "载入"):
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
            if str(self.cfg.get("engine", "qwen")) == "moss":
                if self.moss is None or not self.moss.occupying():
                    return {"ok": False, "msg": "Moss 引擎本来就没在跑"}
                self._get_moss().stop()
                self.st["model_loaded"] = False
                self.st["status"] = "Moss 已停止"
                self._log("已停止 Moss 引擎 · 显存归还")
                return {"ok": True}
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
        payload = payload or {}
        eng = "moss" if str(payload.get("engine") or "") == "moss" else "qwen"
        gate = self._engine_gate(eng)
        if gate:
            return {"ok": False, "msg": gate}
        if eng == "moss":
            return self._start_moss_gen(payload)
        g = dict(self.cfg.get("gen") or {})
        g.update(payload or {})
        if not str(g.get("prompt", "")).strip():
            return {"ok": False, "msg": "提示词是空的，先写点想要什么"}
        mode = str(g.get("mode") or "gen")
        if mode in ("edit", "inpaint") and not (g.get("images") or []):
            return {"ok": False, "msg": "编辑/重绘需要先选参考图"}
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
        透明档（gen.mode=rgba）原生靠提示词出透明底，永远不喂输入图，返回 None。"""
        from PIL import Image
        mode = str(g.get("mode") or "gen")
        paths = [self._ref_path(p) for p in (g.get("images") or [])]
        paths = [p for p in paths if p]
        # 只有 edit/inpaint 需要图：rgba 并入文生图后，这里不能再靠「没传图」兜，否则带上参考图会掉进 edit 分支
        if mode not in ("edit", "inpaint") or not paths:
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

    def _publish(self, path, *, mode, params, size, steps, seed, sec, name=None):
        """一张图落盘后的统一记账：入画廊、刷新状态、写日志、数一遍张数。

        两个引擎以前各抄一份，于是「固定种子重跑 = 同一张图」这种提醒得改两处；
        收成一个入口后，判断也在这里做——上一张和新图字节相同就直接说穿，
        用户看到同一张画面时知道是种子固定，而不是以为程序没出图。
        """
        prev = str(self.st.get("last_image") or "")
        params.setdefault("_saved", []).append(path)
        self.store.add(path, mode=mode, prompt=str(params.get("prompt", "")),
                       negative=str(params.get("negative", "")),
                       size=size, steps=steps, seed=seed, sec=sec)
        self.st["last_sec"] = sec
        self.st["last_image"] = path
        self.st["dup_last"] = bool(prev and _same_file(prev, path))
        self._log("✅ 已保存：%s · %.1f 秒%s"
                  % (name or os.path.basename(path), sec,
                     "（与上一张相同：种子固定，把「种子」的随机开关打开就每张不一样）"
                     if self.st["dup_last"] else ""))
        self._refresh_gallery_count()

    def _do_gen(self, g):
        self.st["running"] = "gen"
        self.st["done"] = 0
        try:
            self._ensure_engine("qwen")   # 千问出图前保证 Moss 不占显存
            # 全部参数解析放进 try：这里抛出去就永远到不了 finally，running 卡在 gen 再也点不动
            steps = _to_int(g.get("steps"), 8, 1, 100)
            mode = str(g.get("mode") or "gen")
            wh = str(g.get("size", "1024x1024")).lower().split("x")
            w, h = _to_int(wh[0], 1024, 64, 4096), _to_int(wh[1] if len(wh) > 1 else "", 1024, 64, 4096)
            count = _to_int(g.get("count"), 1, 1, 8)
            base = _to_int(g.get("seed"), -1, -1, 10 ** 12)   # <0 = 每张重掷随机种子
            mgr = self._get_mgr()
            if mgr.pipe is None:
                mgr.load(_abs_path(self.cfg["console"]["model_dir"]),
                         offload=bool(self.cfg["console"].get("offload", True)),
                         quant=self.cfg["console"].get("quant", "fp8"))
                self.st["model_loaded"] = True
            out_dir = _abs_path(self.cfg["console"]["output_dir"])
            os.makedirs(out_dir, exist_ok=True)
            input_image = self._build_input_image(g)
            label = {"edit": "编辑", "inpaint": "重绘", "rgba": "生图（透明）"}.get(mode, "生图")
            fit = mode in ("edit", "inpaint")
            res = _to_int(g.get("res"), 1024, 256, 2048)
            sdesc = "随机种子" if base < 0 else "种子 %d 起，每张 +1" % base
            if fit:
                self._log("🚀 开始%s：跟随原图比例 · %d 画幅 · %d 步 × %d 张 · %s"
                          % (label, res, steps, count, sdesc))
            else:
                self._log("🚀 开始%s：%dx%d · %d 步 × %d 张 · %s"
                          % (label, w, h, steps, count, sdesc))

            for i in range(count):
                if self._stop.is_set():
                    self._log("⏹ 已停止（第 %d 张之前）" % (i + 1))
                    self.st["status"] = "已停止"
                    break
                # 固定种子连发要每张 +1：同一个种子 + 同一组参数＝同一张图，
                # 用户点了 4 张拿到 4 张一样的，等于这个功能没做
                seed = _rand_seed() if base < 0 else base + i
                self.st["done"] = 0
                t0 = time.time()
                common = dict(prompt=str(g.get("prompt", "")), image=input_image,
                              steps=None if steps == 8 else steps,
                              seed=seed, kv_cache=bool(g.get("kv_cache", True)),
                              on_step=self._report_step, should_stop=self._stop.is_set)
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
                self._publish(path, mode=mode, params=g,
                              size=("跟随输入图 · %d²" % res) if fit else ("%dx%d" % (w, h)),
                              steps=steps, seed=seed, sec=round(dt, 1),
                              name="(%d/%d) %s" % (i + 1, count, name))
            else:
                self.st["status"] = "✅ 完成"
                self._log("── 结束 ──")
        except Exception as e:
            self.st["last_fail"] = str(e)
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
        elif self._cloud_gen.is_set():
            self._log("⏹ 已请求停止：这边不再等了，平台上那半截可能还在跑")
        else:
            self._log("⏹ 已请求停止：等当前这一步去噪完成后中断")
        return {"ok": True}

    # ------------------------------------------------------------ js_api：Moss 引擎（内嵌 ComfyUI）
    def set_engine(self, name):
        """显式切换激活的生图引擎：切过去会先释放另一边的显存（同一时间只激活一个）。

        卸千问（gc + empty_cache）和停 ComfyUI（taskkill）都要好几秒，必须放后台线程：
        直接在桥线程里做，界面会整窗冻住，看起来就像「点了没反应」。

        「配置里已经是这个引擎」不等于「引擎在跑」：配置文件记的是上次关机时的选择，
        这一轮的 ComfyUI 子进程还没拉起。以前这里直接 return ok，于是「启用 Moss」
        按钮点下去什么都没发生、灯也一直灭着——现在同值也要把引擎补起来（幂等）。
        """
        name = "moss" if str(name) == "moss" else "qwen"
        gate = self._engine_gate(name)
        if gate:
            return {"ok": False, "msg": gate}
        same = name == str(self.cfg.get("engine", "qwen"))
        if name == "moss":
            running = bool(self.moss and self.moss.alive())
            if not same or not running:
                if not self._launch("load", lambda: self._do_set_engine(name, same=same)):
                    return {"ok": False, "msg": self._busy_msg()}
                return {"ok": True, "engine": name,
                        "msg": "正在拉起 Moss…" if same else "切换引擎中，另一边显存先释放"}
            return {"ok": True, "engine": name, "msg": "Moss 已经在跑"}
        if not same:
            if not self._launch("load", lambda: self._do_set_engine(name, same=False)):
                return {"ok": False, "msg": self._busy_msg()}
            return {"ok": True, "engine": name, "msg": "切换引擎中，另一边显存先释放"}
        return {"ok": True, "engine": name, "msg": "千问引擎已激活（权重点「开始」时再载）"}

    def _do_set_engine(self, name, same=False):
        try:
            self.st["status"] = "切换引擎…"
            if not same:
                self._ensure_engine(name)
            if name == "moss" and str((self.cfg.get("moss") or {}).get("tier", "daily")) == "daily":
                self._do_moss_load()
            else:
                self.st["model_loaded"] = False
        except Exception as e:
            self._log("❌ 切换引擎失败：%s" % e)
            self.st["status"] = "切换失败"
        finally:
            # 日常档那条路已经把 load 位放掉了，别再放一次——中间要是有人抢到位，
            # 无条件的 _release() 会替别人把锁开了。
            if self.st["running"] == "load":
                self._release()

    def moss_set_tier(self, tier):
        """档位只在 Moss 激活时才有实时动作：yield=停子进程让显存，daily=拉起 ComfyUI。"""
        tier = "yield" if str(tier) == "yield" else "daily"
        if self._busy():
            return {"ok": False, "msg": self._busy_msg()}
        self.cfg.setdefault("moss", {})["tier"] = tier
        self.st["moss_tier"] = tier
        self._save_cfg()
        if str(self.cfg.get("engine", "qwen")) != "moss":
            return {"ok": True, "tier": tier, "engine": self.cfg.get("engine", "qwen"),
                    "msg": "档位已记录（切到 Moss 引擎时生效）"}
        if tier == "yield":
            if not self._claim("unload"):
                return {"ok": False, "msg": self._busy_msg()}
            try:
                if self.moss is not None and self.moss.occupying():
                    self._get_moss().stop()
                self.st["model_loaded"] = False
                self.st["status"] = "已让出显存"
                self._log("🪫 切到「让出显存档」：ComfyUI 子进程已停，显存交还外部文字模型软件")
                return {"ok": True, "tier": tier}
            except Exception as e:
                return {"ok": False, "msg": str(e)}
            finally:
                self._release()
        self._log("🔋 切回「日常质量档」：拉起 ComfyUI…")
        if not self._launch("load", lambda: self._do_moss_load()):
            return {"ok": False, "msg": self._busy_msg()}
        return {"ok": True, "tier": tier}

    def moss_status(self):
        mgr = self._get_moss()
        self.st["moss_installed"] = mgr.installed()
        eng = str(self.cfg.get("engine", "qwen"))
        tier = str((self.cfg.get("moss") or {}).get("tier", "daily"))
        return {"ok": True, "engine": eng, "tier": tier,
                "installed": self.st["moss_installed"], "running": mgr.alive(),
                "url": mgr.state.url, "port": mgr.state.port, "pid": mgr.state.pid,
                "loaded_model": bool(mgr.state.loaded_model), "last_error": mgr.state.last_error,
                "comfyui_dir": mgr.comfyui_dir, "env_todo": self.st.get("env_todo")}

    def _moss_tier(self, m):
        """认档：认不出来回落极速，别让一个坏字符串把出图卡住。"""
        return MOSS_TIERS.get(str((m or {}).get("quality") or "fast"), MOSS_TIERS["fast"])

    def _moss_params(self, m):
        """把界面配置归一成 Moss 生成参数：档位决定模板/步数/CFG（采样常量在模板里）。
        SLG 只在 full 模板的两档（25/50 步）生效——极速档 CFG=1，模板里也不接 SLG 节点。"""
        t = self._moss_tier(m)
        wh = str(m.get("size", "1024x1024")).lower().split("x")
        # latent 网格要 16 对齐：界面自己折过，API/远端客户端可能给零头，
        # 统一「下取整到 16 的倍数」——和 api_server._check_size 同一条折算，别让调用方
        # 请求 1000 却拿到比回答更大的尺寸
        a16 = lambda v, d: max(64, min(2048, _to_int(v, d, 64, 2048) // 16 * 16))
        return {
            "template": t["template"],
            "prompt": str(m.get("prompt", "")),
            "negative": str(m.get("negative", "")),
            "steps": t["steps"],
            "cfg": t["cfg"],
            "width": a16(wh[0], 1024),
            "height": a16(wh[1] if len(wh) > 1 else "", 1024),
            # batch 这里装的是「张数」：给进度条和循环次数用，
            # 真正提交给 ComfyUI 的 batch_size 在 _do_moss_gen 里逐张压回 1
            "batch": _to_int(m.get("count"), 1, 1, 4),
            "slg_skip_layer": 22,
            "slg_start": 0.0,
            "slg_end": 0.5,
        }

    def _start_moss_gen(self, payload):
        m = dict(self.cfg.get("moss") or {})
        m.update(payload or {})
        if not str(m.get("prompt", "")).strip():
            return {"ok": False, "msg": "提示词是空的，先写点想要什么"}
        params = self._moss_params(m)
        self.st["total"] = params["steps"] * params["batch"]
        need_start = not (self.moss is not None and self.moss.alive())
        launch = (lambda: self._do_moss_load(chain_gen=m)) if need_start \
            else (lambda: self._do_moss_gen(m))
        if not self._launch("load" if need_start else "gen", launch):
            return {"ok": False, "msg": self._busy_msg()}
        if need_start:
            self._log("Moss 引擎未运行：先拉起 ComfyUI，随后自动开始生成")
        return {"ok": True, "total": params["steps"]}

    def _do_moss_load(self, chain_gen=None, chain_fn=None, label="Moss"):
        try:
            self._ensure_engine("moss")
            tier = str((self.cfg.get("moss") or {}).get("tier", "daily"))
            self.st["status"] = "启动 ComfyUI…"
            self._report_load(0, "拉起引擎")
            self._get_moss().start(tier=tier, should_stop=self._stop.is_set)
            self._report_load(100, "已就绪")
            self.st["model_loaded"] = True
            # 状态行是全局一份：从视频页拉起时也写「Moss 就绪」会让人以为在跑生图
            self.st["status"] = "%s 就绪" % label
            self._log("✅ %s 引擎已就绪" % label)
            if not chain_gen:
                # 没接着出图才预热：要出图的话第一张本身就会把权重搬上卡，再插一个小图纯属抢队列
                self._warm_moss_async()
            if self._chain_gen(chain_gen, chain_fn or self._do_moss_gen, "启动"):
                return
        except Exception as e:
            self._log("❌ Moss 引擎启动失败：%s" % e)
            self.st["status"] = "Moss 启动失败"
            self.st["model_loaded"] = False
        finally:
            if self.st["running"] == "load":
                self._release()

    def _warm_moss_async(self):
        """引擎就绪 ≠ 权重上卡：后台补一张 256²/1 步的小图，把加载权重的钱付掉。

        不抢 `_claim` 那个单任务位——用户点「启用」后立刻点「开始」是正常操作，
        预热只是个可以排在人家前面的小任务，ComfyUI 自己有序列化队列。
        """
        def run():
            try:
                self._get_moss().warm()
            except Exception as e:      # warm() 自己吞了 ComfyError，这里只兜 _get_moss 起不来的意外
                self._log("ℹ️ 预热跳过：%s" % e)
        threading.Thread(target=run, daemon=True, name="moss-warm").start()

    def _do_moss_gen(self, m):
        self.st["running"] = "gen"
        self.st["done"] = 0
        m = m or {}
        m.setdefault("_saved", [])
        try:
            self._ensure_engine("moss")
            mgr = self._get_moss()
            if not mgr.alive():
                mgr.start(tier=str((self.cfg.get("moss") or {}).get("tier", "daily")),
                          should_stop=self._stop.is_set)
            params = self._moss_params(m)
            steps, count = params["steps"], params["batch"]
            out_dir = _abs_path((self.cfg.get("moss") or {}).get("output_dir")
                                or self.cfg["console"]["output_dir"])
            os.makedirs(out_dir, exist_ok=True)
            base = _to_int(m.get("seed"), -1, -1, 10 ** 12)
            # 连发 N 张走「逐张提交」，不走 ComfyUI 的 batch_size：
            # 一个 batch 里 N 张共用同一份 latent 噪声，出来几乎一模一样；
            # 而且同一个种子 + 同一张工作流会被 ComfyUI 的节点缓存直接秒回同一张。
            params["batch"] = 1
            self.st["total"] = steps * count
            self._log("🚀 开始 Moss(%s)：%dx%d · %d 步 × %d 张 · %s"
                      % (self._moss_tier(m)["label"],
                         params["width"], params["height"], steps, count,
                         "随机种子" if base < 0 else "种子 %d 起，每张 +1" % base))
            got = 0
            for i in range(count):
                if self._stop.is_set():
                    self._log("⏹ 已停止（第 %d 张之前）" % (i + 1))
                    self.st["status"] = "已停止"
                    return
                seed = _rand_seed() if base < 0 else base + i
                params["seed"] = seed
                self.st["done"] = i * steps
                # 进度条报的是整轮的数（第几张 × 每张多少步），别让它在每张开头倒回去
                def prog(done_i, total_i, _b=i * steps, _t=steps * count):
                    self._report_step(_b + done_i, _t)
                t0 = time.time()
                paths = mgr.generate(params, on_progress=prog,
                                     should_stop=self._stop.is_set,
                                     out_dir=out_dir, out_prefix="moss")
                dt = time.time() - t0
                if self._stop.is_set():
                    self._log("⏹ 已停止：第 %d 张是被中断的半成品，不落盘" % (i + 1))
                    self.st["status"] = "已停止"
                    return
                for path in paths:
                    got += 1
                    self._publish(path, mode="moss", params=m,
                                  size="%dx%d" % (params["width"], params["height"]),
                                  steps=steps, seed=seed, sec=round(dt, 1),
                                  name="(%d/%d) %s" % (i + 1, count, os.path.basename(path)))
            if got:
                self.st["status"] = "✅ 完成"
                self._log("── 结束 ──")
            else:
                self.st["last_fail"] = "工作流跑完但没取回图片"
                self.st["status"] = "Moss 没出图"
                self._log("⚠️ 工作流跑完但没取回图片")
        except Exception as e:
            self.st["last_fail"] = str(e)
            self._log("❌ Moss 生成失败：%s" % e)
            self.st["status"] = "Moss 生成失败"
        finally:
            self._release()

    # ------------------------------------------------------------ js_api：本地 H3 视频
    H3_STEPS = 4          # 出厂权重里那条 4 步 Turbo LoRA：步数不是越多越好，多走会糊
    H3_FPS = 24           # 模型按 24fps 训练，帧数网格 17k+5（124 帧 ≈ 5 秒）
    H3_RATIOS = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1),
                 "4:3": (4, 3), "3:4": (3, 4), "21:9": (21, 9)}
    # 原生画布是 1344×768（768P / 16:9），竖屏镜像 768×1344；
    # 按 16 取整会算成 1360×768，所以这一档钉死成模板里的数
    H3_NATIVE = {("768", "16:9"): (1344, 768), ("768", "9:16"): (768, 1344)}
    # 短边上限分两路：本地停在 2048（12G 卡 + 768P 权重就是天花板），
    # 云端放到 2560——官方 2K 就是短边 1440（2560×1440），往上没有档了。
    H3_HI_LOCAL = 2048
    H3_HI_CLOUD = 2560
    H3_HI_MAX = 8192    # 换算阶段的防呆上限：通道上限留给 _h3_size 按比例缩，别在这儿单钳一边
    TRASH_KEEP = 20       # 撤销栈最多留 20 条：再多就成回收站了，不是「防误删」
    TRASH_DAYS = 3        # 重启后清掉超过 3 天的旧条目（撤销只活在这一次运行里）

    def _h3_frames(self, seconds):
        """秒数 → 模型认的帧数：向上贴到 17k+5 网格（照搬官方模板那颗数学节点）。

        随手填 120 会落在网格外，采样出来时长不对；网格是训进去的，不是格式要求。
        """
        n = max(5, int(round(float(seconds or 5) * self.H3_FPS)))
        return n + (5 - (n % 17)) % 17

    def _h3_native(self, w, h):
        """768P 的 16:9 原生画幅是 1344×768：按 16 取整会算成 1360，这一档贴回原生。

        只认「短边正好是原生档的 P 数、长宽比也贴着原生」的尺寸；
        用户自己填的 1400×768 不在这条线上，原样给他，别替人改画幅。
        """
        short, long_ = (h, w) if h < w else (w, h)
        for (tier, _ratio), (nw, nh) in self.H3_NATIVE.items():
            if int(tier) != short:
                continue
            want = float(max(nw, nh)) / float(min(nw, nh))
            if abs(float(long_) / float(short) - want) < 0.03:
                return (nw, nh) if nw >= nh else (nh, nw)
        return w, h

    def _h3_size(self, v, hi=None):
        """清晰度（短边）× 画幅 → 宽高，两边各贴 16 的倍数、上限按通道给（hi）。

        节点 latent 按 16 切，所以 720 这种不是 32 倍数的短边也能跑（云端 432×768 同理）；
        反过来按 32 取整会把 720P 打成 704P，档位名就对不上了。
        本地停在 2048（12G 卡 + 768P 权重就是天花板），云端放到 2560——
        那是官方 2K 的长边（2K＝短边 1440），再往上平台没有档。
        """
        hi = hi or self.H3_HI_LOCAL
        w, h = self._h3_size_raw(v)
        long_ = max(w, h)
        if long_ > hi:
            # 只钳长边会把 16:9 钳成 2048×1440：画幅歪了，界面上写的数也和出片对不上
            k = float(hi) / long_
            w, h = self._h3_native(_snap16(w * k, hi=hi), _snap16(h * k, hi=hi))
        return (w, h)

    def _h3_size_raw(self, v):
        """三处入口按优先级排：自定义宽高 → size 串（界面这一路只落 size，它才是最新的）
        → 档位+画幅（历史配置与自测用例）。
        顺序反过来的话，界面把 size 改成 1280×720 而 tier 还留着 768，出片就成了上一档的尺寸。
        这里只贴 16 的倍数、不夹通道上限：夹在单边上会把画幅钳歪，缩放交给 _h3_size。
        """
        cap = self.H3_HI_MAX
        a16 = lambda x: _snap16(x, hi=cap)
        tier = _to_int(v.get("tier"), 0, 0, cap)
        ratio = str(v.get("ratio") or "")
        size = str(v.get("size") or "").strip().lower()
        if size == "custom" or str(v.get("tier") or "").strip().lower() == "custom":
            return self._h3_native(a16(_to_int(v.get("cw"), 1344, 16, cap)),
                                   a16(_to_int(v.get("ch"), 768, 16, cap)))
        wh = size.split("x")
        if len(wh) == 2 and wh[0].isdigit() and wh[1].isdigit():
            return self._h3_native(a16(int(wh[0])), a16(int(wh[1])))
        native = self.H3_NATIVE.get((str(tier), ratio))
        if native:
            return native
        if tier and ratio in self.H3_RATIOS:
            aw, ah = self.H3_RATIOS[ratio]
            # 「P」数指短边：横屏短边是高，竖屏短边是宽（720P = 1280×720 / 720×1280）
            if aw >= ah:
                h, w = float(tier), tier * aw / float(ah)
            else:
                w, h = float(tier), tier * ah / float(aw)
            return self._h3_native(a16(w), a16(h))
        # 三处都没给数：用自定义宽高兜底，缺啥按原生 1344×768
        return self._h3_native(a16(_to_int(v.get("cw"), 1344, 16, cap)),
                               a16(_to_int(v.get("ch"), 768, 16, cap)))

    def _video_params(self, v):
        """界面那几样（描述语 / 清晰度×画幅 / 秒数）折成一份 H3 工作流的参数。

        首帧是可选的：给了就是首帧生视频，没给同一份模板走文生视频。
        """
        w, h = self._h3_size(v)
        return {
            "template": "workflow_h3.json",
            "prompt": str(v.get("prompt", "")),
            "negative": "",             # BasicGuider 没有 cfg 输入＝恒定 1，负向条件白跑一遍文本编码器
            "width": w,
            "height": h,
            "length": self._h3_frames(v.get("seconds")),
            "fps": float(self.H3_FPS),
            "steps": self.H3_STEPS,
            "cfg": 1.0,
            "batch": 1,
            "seed": 0,
            "first_image": "",
        }

    def video_gen(self, payload=None):
        """点「开始」：按通道选本地或云端，两条路出一样的片子、进同一个画廊。"""
        v = dict(self.cfg.get("video") or {})
        v.update(payload or {})
        if not str(v.get("prompt", "")).strip():
            return {"ok": False, "msg": "先写一句想要什么画面"}
        # 云端不碰本机权重与 ComfyUI，所以 h3 那个开关管不到它：只管本地那一路
        if str(v.get("exec") or "local") == "cloud":
            return self._video_cloud(v)
        if not self._env_on().get("h3"):
            return {"ok": False, "msg": "H3 环境已关闭 · 到「环境 → H3」那页开启"}
        p = self._video_params(v)
        self.st["total"] = p["steps"]
        need_start = not (self.moss is not None and self.moss.alive())
        launch = ((lambda: self._do_moss_load(chain_gen=v, chain_fn=self._do_video_gen,
                                              label="H3"))
                  if need_start else (lambda: self._do_video_gen(v)))
        if not self._launch("load" if need_start else "video", launch):
            return {"ok": False, "msg": self._busy_msg()}
        if need_start:
            self._log("H3 引擎未运行：先拉起 ComfyUI，随后自动开始出片")
        return {"ok": True, "total": p["steps"], "frames": p["length"]}

    def _video_cloud(self, v):
        """云端通道：不碰显存、不拉 ComfyUI，代价是要开浏览器、按平台计费。

        这里先把「跑不动」的话说完再占任务位：账号没登录、缺 DrissionPage、
        没工作流这三种情况各是一句话，让人知道差哪一步，而不是点了没反应。
        """
        g = self._cloud_h3()
        if not self._dp_ready():
            return {"ok": False, "msg": "云端要浏览器：到「环境 → 基础」补齐 DrissionPage 后重开软件"}
        if self._cloud_gen.is_set():
            return {"ok": False, "msg": "云端正有一段在跑：等它出片或先点停止"}
        try:
            row = g.account(str(v.get("cloud_acct") or ""))
        except Exception as e:
            return {"ok": False, "msg": "云端还没备好：%s" % e}
        try:
            kind, src = g.wf_src(str(v.get("cloud_wf") or ""))
            wf = g.host_url() if kind == "file" else g.wf_url(src)
        except Exception as e:
            return {"ok": False, "msg": "%s" % e}
        if not self._launch("video", lambda: self._do_video_cloud(v)):
            return {"ok": False, "msg": self._busy_msg()}
        w, h = self._h3_size(v, hi=self.H3_HI_CLOUD)
        self._log("☁️ 云端出片：%ds · %dx%d · 号「%s」· %s（要开浏览器，按平台计费）"
                  % (_to_int(v.get("seconds"), 5, 5, 15), w, h, row["name"],
                     ("本地 · " + os.path.basename(src)) if kind == "file" else wf))
        return {"ok": True, "total": 1, "exec": "cloud", "acct": row["name"]}

    def _do_video_cloud(self, v):
        self.st["running"] = "video"
        self.st["video_exec"] = "cloud"
        self.st["done"] = 0
        self.st["total"] = 1
        self.st["status"] = "云端准备中…"
        self._cloud_gen.set()
        t0 = time.time()
        try:
            w, h = self._h3_size(v, hi=self.H3_HI_CLOUD)
            out_dir = _abs_path(self.cfg["console"]["output_dir"])
            p = {"prompt": str(v.get("prompt") or ""),
                 "seconds": _to_int(v.get("seconds"), 5, 5, 15),
                 "width": w, "height": h,
                 "first": self._ref_path(v.get("first") or ""),
                 "acct": str(v.get("cloud_acct") or ""),
                 "wf": str(v.get("cloud_wf") or ""),
                 "out_dir": out_dir}
            if (v.get("first") and not p["first"]):
                # 和那条「静默变成文生视频」的旧坑同一个道理：说破，别让人以为参考图进去了
                self._log("⚠️ 参考图不在了：%s · 这一段只按文字出片"
                          % os.path.basename(str(v.get("first"))))
            path = self._cloud_h3().run(p, on_progress=self._cloud_step,
                                        should_stop=self._stop.is_set)
            if self._stop.is_set():
                self.st["status"] = "已停止"
                return
            self._publish(path, mode="h3", params=v, size="%dx%d" % (w, h),
                          steps=self.H3_STEPS, seed=-1,
                          sec=round(time.time() - t0, 1),
                          name=os.path.basename(path))
            self.st["done"] = 1
            self.st["status"] = "✅ 完成"
            self._log("── 结束 ──")
        except Exception as e:
            self.st["last_fail"] = str(e)
            if self._stop.is_set():
                self._log("⏹ 已停止：云端那半段可能还在平台上跑，去 H3云端 看一眼")
                self.st["status"] = "已停止"
            else:
                self._log("❌ 云端出片失败：%s" % e)
                self.st["status"] = "出片失败"
        finally:
            self._cloud_gen.clear()
            self._release()

    def _cloud_step(self, msg):
        """云端只有一条「等多久」的路可报：没有步数刻度，就把实话写在状态行上。"""
        if not self._stop.is_set():
            self.st["status"] = str(msg or "云端出片中…")[:120]


    def _do_video_gen(self, v):
        self.st["running"] = "video"
        self.st["video_exec"] = "local"
        self.st["done"] = 0
        self.st["status"] = "出片准备…"
        v = v or {}
        v.setdefault("_saved", [])
        try:
            self._ensure_engine("moss")
            mgr = self._get_moss()
            if not mgr.alive():
                mgr.start(tier=str((self.cfg.get("moss") or {}).get("tier", "daily")),
                          should_stop=self._stop.is_set)
            params = self._video_params(v)
            first = self._ref_path(v.get("first") or "")
            if first:
                params["first_image"] = mgr.upload_image(first)
            out_dir = _abs_path(self.cfg["console"]["output_dir"])
            os.makedirs(out_dir, exist_ok=True)
            base = _to_int(v.get("seed"), -1, -1, 10 ** 12)
            seed = _rand_seed() if base < 0 else base
            params["seed"] = seed
            self._log("🎬 开始出片：%ds（%d 帧）· %dx%d · %d 步 · %s%s"
                      % (round(params["length"] / float(self.H3_FPS), 1), params["length"],
                         params["width"], params["height"], params["steps"],
                         "随机种子" if base < 0 else "种子 %d" % seed,
                         " · 首帧 " + os.path.basename(first) if first else ""))
            self.st["status"] = "采样中…"
            t0 = time.time()
            paths = mgr.generate(params,
                                 on_progress=lambda d, t: self._report_step(d, t),
                                 should_stop=self._stop.is_set,
                                 out_dir=out_dir, out_prefix="h3")
            if self._stop.is_set():
                self._log("⏹ 已停止：这一段的半成品不落盘")
                self.st["status"] = "已停止"
                return
            if not paths:
                self.st["last_fail"] = "工作流跑完但没取回片子"
                self.st["status"] = "没出片"
                return
            for path in paths:
                self._publish(path, mode="h3", params=v,
                              size="%dx%d" % (params["width"], params["height"]),
                              steps=params["steps"], seed=seed,
                              sec=round(time.time() - t0, 1),
                              name=os.path.basename(path))
            self.st["status"] = "✅ 完成"
            self._log("── 结束 ──")
        except Exception as e:
            self.st["last_fail"] = str(e)
            self._log("❌ 出片失败：%s" % e)
            self.st["status"] = "出片失败"
        finally:
            self._release()

    # ------------------------------------------------------------ js_api：云端账号
    # 一只调试浏览器 + 多份登录态快照：换号只换 cookies/localStorage，不重启进程。
    # 浏览器只在登录/保活时起；启动路径不 import DrissionPage（与不 import torch 同理）。
    def _cloudkit(self):
        # pywebview 每个 js_api 调用各起一个线程：冷启动时两个云端入口撞在一起，
        # 没锁就会各建一套 store/host/keep，最后赋值盖掉，留下一条没人管的保活线程和一个浏览器
        with self._cloud_lock:
            if self._cloudx is None:
                from cloudkit import browser as cb
                from cloudkit import store as cs
                cfg = self.cfg.setdefault("cloud", {})
                store = cs.AccountStore(ROOT)
                host = cb.BrowserHost(ROOT, cfg, log=self._log)
                keep = cb.KeepAlive(host, store, cfg, log=self._log,
                                    busy=lambda: bool(self.st.get("cloud_busy"))
                                    or self._cloud_gen.is_set())
                self._cloudx = {"store": store, "host": host, "keep": keep}
                keep.start()   # 只等定时器；浏览器没开不会自己拉起
            return self._cloudx

    def _dp_ready(self):
        try:
            import importlib.util
            return importlib.util.find_spec("DrissionPage") is not None
        except (ImportError, ValueError):
            return False

    def _cloud_h3(self):
        """云端出片那条线：账号库、共用浏览器、执行器都从 _cloudkit 那份取。"""
        with self._cloud_lock:      # 与 _cloudkit 同一条：两个线程同时点开始不能各建一台
            if self._h3cloud is None:
                from cloudkit import gen as cg
                h = self._cloudkit()
                self._h3cloud = cg.CloudH3(ROOT, self.cfg.setdefault("cloud", {}),
                                           h["store"], h["host"], log=self._log)
            return self._h3cloud

    def cloud_brief(self):
        """视频页那格「云端」要用的一句话实话：有没有号、有没有 DrissionPage、用的哪份工作流。

        只读档案，不起浏览器、不碰保活——在视频页看一眼通道不该顺手开出一个窗口。
        """
        c = self.cfg.setdefault("cloud", {})
        out = {"dp": self._dp_ready(), "accts": [], "wf": str(c.get("workflow") or ""),
               "busy": bool(self._cloud_gen.is_set())}
        try:
            from cloudkit import store as cs
            st = cs.AccountStore(ROOT)
            for a in st.list():
                snap = st.load(a["id"]) or {}
                if snap.get("cookies"):
                    out["accts"].append({"id": a["id"], "name": a["name"]})
        except Exception:
            pass
        out["ready"] = bool(out["dp"] and out["accts"])
        return out

    def cloud_state(self):
        """给界面的账号表 + 浏览器/保活状态。不含任何凭据。"""
        c = self.cfg.get("cloud") or {}
        if self._cloudx is None and not self._dp_ready():
            # 缺浏览器依赖也把档案列出来：名字和备份是本地数据，不该跟着一起消失
            try:
                from cloudkit import store as cs
                accounts = cs.AccountStore(ROOT).list()
            except Exception:
                accounts = []
            return {"ok": True, "dp": False, "accounts": accounts,
                    "browser": {"on": False, "port": int(c.get("port") or 9333),
                                "base": str(c.get("base") or ""), "account": ""},
                    "busy": self.st.get("cloud_busy", ""),
                    "msg": "缺 DrissionPage：到「环境 → 基础」补齐后重开这页",
                    "keep": {"on": bool(c.get("keep", True)),
                             "min": int(c.get("keep_min") or 30),
                             "last": 0, "msg": "还没跑过"},
                    "concurrency": 1, "page": str(c.get("base") or "")}
        h = self._cloudkit()
        keep = h["keep"]
        return {
            "ok": True, "dp": True,
            "accounts": h["store"].list(),
            "browser": {"on": h["host"].alive(), "port": h["host"].port,
                        "base": h["host"].base, "account": h["host"].current},
            "busy": self.st.get("cloud_busy", ""),
            "msg": self.st.get("cloud_msg", ""),
            "keep": {"on": bool((self.cfg.get("cloud") or {}).get("keep", True)),
                     "min": int((self.cfg.get("cloud") or {}).get("keep_min") or 30),
                     "last": int(keep.last), "msg": keep.last_msg,
                     # 这只窗口现在被谁占着：''=空闲（保活能跑）/ login / gen / hold
                     "purpose": str(h["host"].purpose or "")},
            "concurrency": 1, "page": h["host"].base,
        }

    def _cloud_run(self, label, fn):
        """浏览器操作一律进后台：pywebview 在 UI 线程派发 js_api，
        起浏览器/加载页面动辄几秒，同步等会把消息泵饿死（界面先卡住）。"""
        if self._cloud_gen.is_set():
            # 云端出片那段占着同一只浏览器：这时候换号等于把正在跑的号顶掉
            return False, "云端出片正占用浏览器：先等这一段跑完"
        with self._cloud_lock:
            if self.st.get("cloud_busy"):
                return False, "H3云端正忙：%s" % self.st["cloud_busy"]
            self.st["cloud_busy"] = label
            self.st["cloud_msg"] = ""

        def run():
            try:
                fn()
            except Exception as e:
                from cloudkit.store import brief_error
                # 第三方库的报错常把它正在处理的值原样打回来（设 cookie 失败就是）：
                # 这一句要进界面、日志、账号索引，先抹一遍再落地
                msg = brief_error(e)
                self.st["cloud_msg"] = msg
                self._log("❌ H3云端：%s" % msg)
            finally:
                with self._cloud_lock:
                    self.st["cloud_busy"] = ""
        threading.Thread(target=run, daemon=True, name="cloud-" + label).start()
        return True, ""

    def _cloud_acct(self, aid):
        h = self._cloudkit()
        row = h["store"].get(aid)
        return h, row

    def cloud_new(self, name=""):
        """新建一个登录档案：起共用浏览器，停在登录页；用户登好回来点「保存」。"""
        if not self._dp_ready():
            return {"ok": False, "msg": "缺 DrissionPage：到「环境 → 基础」补齐后重开这页",
                    "state": self.cloud_state()}
        h = self._cloudkit()
        row = h["store"].create(name)
        aid = row["id"]
        h["store"].mark(aid, "pending", "等待登录")
        # 新建档案要一块干净的登录页：共用浏览器里可能还留着上一个号的 cookie，
        # 不清掉的话「新建登录」会直接看到旧号——保存下来就是重复的一份
        ok, msg = self._cloud_run("打开登录页", lambda: h["host"].open_login({}, aid=aid))
        if ok:
            self._log("☁️ 新建登录：%s（在浏览器里登录后点「保存」）" % row["name"])
        return {"ok": ok, "msg": msg, "account": row, "state": self.cloud_state()}

    def cloud_login(self, aid=""):
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}
        state = h["store"].load(aid)
        h["store"].mark(aid, "pending", "等待登录")

        def job():
            h["host"].open_login(state, aid=aid)
            self.st["cloud_msg"] = "登录完点「保存」；以后换号不用再登"
        ok, msg = self._cloud_run("打开登录页", job)
        return {"ok": ok, "msg": msg}

    def cloud_save(self, aid="", name=""):
        """把浏览器里当前的登录态存成这个账号的一份新快照（旧快照保留为备份）。"""
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}

        def job():
            from cloudkit.browser import login_state
            # 整段一次取锁：读快照和判登录态必须是同一个号的同一次状态，
            # 分两次取锁的话中间正好能插进一次保活换号
            with h["host"].lock:
                snap = h["host"].snapshot()
                if not snap.get("cookies"):
                    raise RuntimeError("没读到登录态：先在浏览器里登录，再点保存")
                ts = h["store"].save(aid, snap["cookies"], snap["storage"], snap["url"])
                st, detail = login_state(h["host"].tab())
                h["store"].mark(aid, st, detail)
                h["host"].purpose = ""   # 登录流程收尾，保活可以接着轮换
            if name:
                h["store"].rename(aid, name)
            n = len(h["store"].backups(aid))
            self.st["cloud_msg"] = "已保存 %s · 共 %d 份备份" % (row["name"], n)
            self._log("☁️ 登录态已保存：%s（%d 份）" % (row["name"], n))
            return ts
        ok, msg = self._cloud_run("保存登录态", job)
        return {"ok": ok, "msg": msg}

    def cloud_apply(self, aid=""):
        """用这个账号打开平台：换 cookie 后刷一次页面，人眼看得到是谁的号。"""
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}
        state = h["store"].load(aid)
        if not state or not state.get("cookies"):
            return {"ok": False, "msg": "这个号还没保存登录态"}
        ok, msg = self._cloud_run("切换账号", lambda: h["host"].open_base(state, aid=aid, hold=True))
        if ok:
            self._log("☁️ 切换到账号：%s" % row["name"])
        return {"ok": ok, "msg": msg}

    def cloud_check(self, aid=""):
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}

        def job():
            from cloudkit.browser import cookie_fp, login_state, snapshot_state
            state = h["store"].load(aid)
            with h["host"].lock:
                # hold=True：这一段里保活不许插进来换号，否则检查的是别人的会话、
                # 结论却记在这个号头上
                h["host"].open_base(state, aid=aid, hold=True)
                tab = h["host"].tab()
                st, detail = login_state(tab)
                snap = snapshot_state(tab, h["host"].domains)
                h["host"].purpose = ""
            # 没变就不写：反复点「检查」不该把 12 份备份挤成同一分钟的 12 份
            if snap.get("cookies") and cookie_fp(snap["cookies"]) != cookie_fp((state or {}).get("cookies")):
                h["store"].save(aid, snap["cookies"], snap["storage"], snap["url"])
            h["store"].mark(aid, st, detail)
            self.st["cloud_msg"] = "%s：%s" % (row["name"], detail)
        ok, msg = self._cloud_run("检查登录", job)
        return {"ok": ok, "msg": msg}

    def cloud_delete(self, aid=""):
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}
        if h["host"].current == aid:
            h["host"].current = ""
        h["store"].delete(aid)
        self._log("☁️ 已删除账号：%s" % row["name"])
        return {"ok": True, "state": self.cloud_state()}

    def cloud_rename(self, aid="", name=""):
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}
        if not h["store"].rename(aid, name):
            return {"ok": False, "msg": "名字不能为空"}
        return {"ok": True, "state": self.cloud_state()}

    def cloud_backups(self, aid=""):
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在", "spots": []}
        rows = []
        for ts in h["store"].backups(aid):
            try:
                t = time.strptime(ts[:15], "%Y%m%d-%H%M%S")
                label = time.strftime("%m-%d %H:%M", t)
            except ValueError:
                label = ts
            rows.append({"ts": ts, "label": label})
        return {"ok": True, "spots": rows, "name": row["name"]}

    def cloud_restore(self, aid="", ts=""):
        """回到某份备份：复制成最新一份再灌进浏览器，历史备份一份不删。"""
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}
        state = h["store"].load(aid, ts)
        if not state:
            return {"ok": False, "msg": "这份备份不存在或已被轮换掉"}
        new_ts = h["store"].restore(aid, ts)
        if not new_ts:
            return {"ok": False, "msg": "恢复失败"}

        def job():
            h["store"].mark(aid, "saved", "从备份恢复")
            h["host"].open_base(state, aid=aid)
            self.st["cloud_msg"] = "%s 已恢复到 %s" % (row["name"], ts)
        ok, msg = self._cloud_run("恢复备份", job)
        return {"ok": ok, "msg": msg}

    def cloud_key_set(self, aid="", key=""):
        """API Key 每号一条：协议侧的正牌凭证。只落盘，不回显、不进日志。"""
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}
        if not h["store"].set_key(aid, key):
            return {"ok": False, "msg": "Key 不能为空"}
        self._log("☁️ 已保存 API Key：%s" % row["name"])
        return {"ok": True, "state": self.cloud_state()}

    def cloud_key_clear(self, aid=""):
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}
        h["store"].clear_key(aid)
        return {"ok": True, "state": self.cloud_state()}

    def cloud_keep_now(self):
        if not self._dp_ready():
            return {"ok": False, "msg": "缺 DrissionPage：到「环境 → 基础」补齐后重开这页"}
        h = self._cloudkit()
        if not h["host"].alive():
            return {"ok": False, "msg": "浏览器还没开：先点「打开平台」"}
        ok, msg = self._cloud_run("保活", lambda: h["keep"].sweep(force=True))
        return {"ok": ok, "msg": msg}

    def cloud_browser_start(self):
        if not self._dp_ready():
            return {"ok": False, "msg": "缺 DrissionPage：到「环境 → 基础」补齐后重开这页"}
        h = self._cloudkit()

        def job():
            h["host"].browser()
            self.st["cloud_msg"] = "浏览器已启动（共用调试端口 %d）" % h["host"].port
        ok, msg = self._cloud_run("启动浏览器", job)
        return {"ok": ok, "msg": msg}

    def cloud_browser_stop(self):
        h = self._cloudkit()

        def job():
            h["host"].close()
            self.st["cloud_msg"] = "浏览器已关闭"
        ok, msg = self._cloud_run("关闭浏览器", job)
        return {"ok": ok, "msg": msg}

    def cloud_auth_names(self, aid=""):
        """登录态里取得到的 Rh-* 鉴权头名字（只报名字，不报值）。"""
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在", "names": []}
        return {"ok": True, "names": sorted(h["host"].headers(h["store"].load(aid)))}

    # ------------------------------------------------------------ js_api：API 服务
    def api_state(self):
        return {"ok": True, "cfg": self.cfg["api"],
                "on": bool(self.st["api_on"]), "url": self.st["api_url"]}

    def api_set(self, patch=None):
        """改 API 配置并即时生效（开关/局域网/端口/鉴权/默认引擎与分辨率）。返回 api_state。"""
        p = patch or {}
        a = self.cfg["api"]
        if "enabled" in p:
            a["enabled"] = bool(p["enabled"])
        if "lan" in p:
            a["lan"] = bool(p["lan"])
        if "no_token" in p:
            a["no_token"] = bool(p["no_token"])
        if "def_engine" in p:
            d = str(p["def_engine"] or "follow")
            if d not in ("follow", "qwen", "moss"):
                return {"ok": False, "msg": "默认引擎只能是 follow / qwen / moss",
                        "state": self.api_state()}
            a["def_engine"] = d
        if "def_size" in p:
            s = str(p["def_size"] or "1024x1024").strip().lower()
            # 只做格式关：引擎各自的数值范围在每次请求时按所选引擎再校
            # （这里不 import api_server——它拖着 fastapi/uvicorn，是可选项）
            if not re.fullmatch(r"\d{3,4}x\d{3,4}", s):
                return {"ok": False, "msg": "默认分辨率要给 WxH（如 1024x1024）",
                        "state": self.api_state()}
            a["def_size"] = s
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
        # 只有监听相关的改动才值得重启 uvicorn：免令牌/默认引擎/默认分辨率是逐请求读的，
        # 重启会掐断正在排队的 HTTP 连接，没必要
        if not any(k in p for k in ("enabled", "lan", "port")):
            return {"ok": True, "msg": "", "state": self.api_state()}
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
                self._log("🌐 API 服务已启动：%s（%s）"
                          % (self.st["api_url"],
                             "免令牌模式" if a.get("no_token") else "Bearer 令牌鉴权"))
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
        """画廊清单：只给元信息，缩略图由界面按「滚到哪张取哪张」单独要。

        一次内联 120 张 384px 是 3.3MB 的 base64，桥线程还得连着烧 8 秒 CPU 现做缩略；
        拆成按需取之后，首屏只解码眼睛看得见的那十几张。
        """
        out_dir = _abs_path(self.cfg["console"]["output_dir"])
        if not os.path.isdir(out_dir):
            return []
        files = []
        for name in os.listdir(out_dir):
            if name.lower().endswith(MEDIA_EXT):
                p = os.path.join(out_dir, name)
                try:
                    files.append((os.path.getmtime(p), p))
                except OSError:
                    pass
        files.sort(reverse=True)
        items = []
        for mt, p in files[:limit]:
            items.append({"file": p, "name": os.path.basename(p),
                          "video": p.lower().endswith(VIDEO_EXT),
                          "t": time.strftime("%Y-%m-%d %H:%M", time.localtime(mt))})
        return items

    def _thumb(self, path, mt, wide):
        key = (path, mt, wide)
        if key in self._thumbs:            # 不是「有值就返回」：坏图缓存的是空串，
            hit = self._thumbs[key]         # 用真值判断等于每次轮询都重新解码一遍坏文件
            self._thumbs.move_to_end(key)
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
        while len(self._thumbs) >= 240:     # 逐出最久没看的，别一把清空（清完下轮全量重解码）
            self._thumbs.popitem(last=False)
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
        meta = self.store.get(p)
        try:
            dst = self._trash_move(p)
        except OSError as e:
            return {"ok": False, "msg": "删不动：%s" % e}
        self.store.remove(p)
        with self._trash_lock:
            self._trash.append({"trash": dst, "file": p, "meta": meta,
                                "name": os.path.basename(p)})
            while len(self._trash) > self.TRASH_KEEP:
                old = self._trash.pop(0)
                try:
                    os.remove(old["trash"])
                except OSError:
                    pass
        self._log("已删除：%s（可撤销）" % os.path.basename(p))
        self._refresh_gallery_count()
        return {"ok": True, "undo": True}

    def gallery_undo(self):
        """撤销最近一次删除：文件搬回原处，历史参数（含收藏位与时间）原样插回去。"""
        with self._trash_lock:
            if not self._trash:
                return {"ok": False, "msg": "没有可撤销的删除"}
            it = self._trash.pop()
        src, dst = it["trash"], it["file"]
        if not os.path.isfile(src):
            return {"ok": False, "msg": "撤不回来了：回收站里那份已经不在了"}
        if os.path.exists(dst):
            with self._trash_lock:
                self._trash.append(it)
            return {"ok": False, "msg": "原位置已经有同名文件，先处理掉它再撤销"}
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
        except OSError as e:
            with self._trash_lock:
                self._trash.append(it)
            return {"ok": False, "msg": "恢复失败：%s" % e}
        if it.get("meta"):
            self.store.restore(it["meta"])
        self._log("已撤销删除：%s" % it["name"])
        self._refresh_gallery_count()
        return {"ok": True, "file": dst, "name": it["name"]}

    def _trash_move(self, path):
        """原文件搬进回收站：不留在输出目录，但字节还在，撤销时搬回来即可。"""
        os.makedirs(self._trash_dir, exist_ok=True)
        stamp = int(time.time() * 1000)
        dst = os.path.join(self._trash_dir, "%d_%s" % (stamp, os.path.basename(path)))
        n = 1
        while os.path.exists(dst):
            dst = os.path.join(self._trash_dir,
                               "%d_%d_%s" % (stamp, n, os.path.basename(path)))
            n += 1
        shutil.move(path, dst)
        return dst

    def _trash_purge(self):
        """启动时清回收站：撤销只活在这一次运行里，超过保留期的旧文件直接删掉。"""
        try:
            names = os.listdir(self._trash_dir)
        except OSError:
            return
        ttl = time.time() - self.TRASH_DAYS * 86400
        for name in names:
            head = name.split("_", 1)[0]
            if head.isdigit() and int(head) / 1000.0 >= ttl:
                continue
            try:
                os.remove(os.path.join(self._trash_dir, name))
            except OSError:
                pass

    def _trash_empty(self):
        with self._trash_lock:
            self._trash.clear()
        try:
            names = os.listdir(self._trash_dir)
        except OSError:
            return
        for name in names:
            try:
                os.remove(os.path.join(self._trash_dir, name))
            except OSError:
                pass

    def gallery_clear(self):
        out_dir = _abs_path(self.cfg["console"]["output_dir"])
        try:
            entries = os.listdir(out_dir)
        except OSError as e:
            return {"ok": False, "msg": "打不开输出目录：%s" % e}
        gone, left = 0, set()
        for name in entries:
            p = os.path.join(out_dir, name)
            if not name.lower().endswith(MEDIA_EXT) or not os.path.isfile(p):
                continue
            try:
                os.remove(p)     # 直接扫目录：走 _gallery_items 会给每张图现做缩略图，清空时白烧几十秒 CPU
                gone += 1
            except OSError:
                left.add(os.path.normpath(p))   # 删不掉的（正被占用）留在盘上，它的参数记录也得留着
        # 「清空」按确认框说的不进回收站：之前攒下的撤销条目也一并清掉，
        # 否则清完还能撤回来一张，跟用户刚确认的那句话对不上
        self._trash_empty()
        msg = "已清空输出目录：%d 张" % gone
        if left:
            msg += "，%d 张正被占用没删掉" % len(left)
        self._log(msg)
        self.store.prune(left)
        self._refresh_gallery_count()
        return {"ok": True, "removed": gone}

    def _in_output(self, path):
        """删除类操作只认输出目录里的成片（图或片）· 防止被当成任意文件删除器。"""
        out_dir = os.path.normpath(_abs_path(self.cfg["console"]["output_dir"]))
        p = os.path.normpath(str(path or ""))
        if p.lower().endswith(MEDIA_EXT) and os.path.dirname(p) == out_dir and os.path.isfile(p):
            return p
        return None

    def thumb(self, path, wide=768):
        p = os.path.normpath(str(path or ""))
        if not os.path.isfile(p):
            return {"ok": False, "msg": "图还没落盘"}
        if p.lower().endswith(VIDEO_EXT):
            # 视频不做缩略：解码一帧要引一个视频库，而画廊那张本来就该是「点了就播」。
            # 界面拿这个标记画一张带片名的影片砖，点开交给系统播放器。
            return {"ok": True, "video": True, "url": ""}
        if not p.lower().endswith(IMG_EXT):
            return {"ok": False, "msg": "不是图片也不是视频"}
        # 宽度来自界面（画廊网格要 384、单张预览要 768）：夹住，别让一个怪字符串
        # 把 PIL 拖去解码 8000px 的原图
        wide = _to_int(wide, 768, 64, 1536)
        return {"ok": True, "url": self._thumb(p, os.path.getmtime(p), wide)}

    # ------------------------------------------------------------ js_api：模型管理
    @staticmethod
    def _safe_name(name):
        return bool(re.fullmatch(r"[A-Za-z0-9._-]+", str(name or "")))

    def models_list(self):
        from envkit import spec as sp
        root = sp.env_models_dir(ROOT, self._spec(), "qwen")
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
        from envkit import spec as sp
        if not self._safe_name(name):
            return {"ok": False, "msg": "模型目录名只能是字母数字点横线下划线"}
        root = sp.env_models_dir(ROOT, self._spec(), "qwen")
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            return {"ok": False, "msg": "这个目录不存在"}
        self.cfg["console"]["model_dir"] = os.path.relpath(d, ROOT).replace("\\", "/")
        self._save_cfg()
        self._log("已切换激活模型：%s%s" % (name,
                  "（显存里还是旧模型：重新载入才生效）" if self.st["model_loaded"] else ""))
        return {"ok": True, "cfg": self.cfg}

    def _dl_config(self):
        try:
            from envkit import spec as sp
            return dict((sp.load_spec(ROOT).get("download") or {}))
        except Exception:
            return {}

    def _dl_event(self, ev):
        """envkit/download 的进度回调：worker 线程直接写 st，轮询下一跳就能看见。"""
        self.st["dl"] = dict(ev or {})

    def _model_dl(self, repo, name):
        """同步下载：多镜像自动选路 + 断点续传（装了 Motrix 先交给它）；起不起线程由调用方定。"""
        from envkit import download as hd
        from envkit import spec as sp
        target = os.path.join(sp.env_models_dir(ROOT, self._spec(), "qwen"), name)
        os.makedirs(target, exist_ok=True)
        cfg = self._dl_config()
        rel = os.path.relpath(target, ROOT).replace("\\", "/")
        self._log("📥 下载 %s → %s（自动选镜像 · %d 线程 · 断点续传）"
                  % (repo, rel, int(cfg.get("jobs") or 8)))
        try:
            res = hd.download(
                repo, target,
                jobs=int(cfg.get("jobs") or 8),
                chunk_mb=int(cfg.get("chunk_mb") or 64),
                retries=int(cfg.get("retries") or 20),
                timeout=int(cfg.get("timeout") or 60),
                probe_timeout=int(cfg.get("probe_timeout") or 8),
                endpoints=cfg.get("endpoints"), config=cfg,
                on_progress=self._dl_event, on_log=self._log)
        except Exception as e:
            res = {"ok": False, "error": str(e)}
        finally:
            self.st["dl"] = {}
        if res.get("ok"):
            self._log("✅ 下载完成 %s · %s · 用时 %.1f 分钟 · 镜像 %s"
                      % (rel, hd.fmt_bytes(res.get("bytes") or 0),
                         (res.get("seconds") or 0) / 60.0, res.get("endpoint") or "?"))
            return True
        self._log("❌ 下载失败：%s" % (res.get("error") or "未知错误"))
        return False

    def models_download(self, repo, name=""):
        """模型管理页的下载器：后台线程跑 _model_dl，调用即返回。"""
        from envkit import spec as sp
        repo = str(repo or "").strip()
        name = str(name or "").strip() or repo.split("/")[-1]
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or not self._safe_name(name):
            return {"ok": False, "msg": "repo 格式要 org/name；目录名只允许字母数字点横线下划线"}
        with self._task_lock:
            if self.st.get("env_busy"):
                return {"ok": False, "msg": "环境补全正在跑，等它结束再下"}
            if (self.st.get("dl") or {}).get("busy"):
                return {"ok": False, "msg": "已经有一个下载在跑，等它结束"}
            if self._dl is not None and self._dl.is_alive():
                return {"ok": False, "msg": "已经有一个下载在跑，等它结束"}
            target = os.path.join(sp.env_models_dir(ROOT, self._spec(), "qwen"), name)
            os.makedirs(target, exist_ok=True)
            self.st["dl"] = {"busy": True, "phase": "download", "repo": repo,
                             "file": "", "done": 0, "total": 0, "speed": 0,
                             "eta": 0, "files_done": 0, "files_total": 0}
            self._dl = threading.Thread(target=lambda: self._model_dl(repo, name), daemon=True)
            self._dl.start()
        return {"ok": True, "target": target}

    # ------------------------------------------------------------ js_api：环境体检与补全
    def env_probe_bg(self):
        """开机后台体检一次：「环境」页的待补数不用人先进那页才出现。

        体检本身一百多毫秒（冷一轮，热了 9ms），放后台只是不想让它排在窗口首帧前面：
        先让人看见界面，待补数晚半秒到无所谓。
        """
        def run():
            r = self.env_check()
            if not r.get("ok"):
                self._log("⚠️ 环境体检没跑成：%s" % r.get("msg"))
                return
            n = len(r["todo"])
            self._log("🩺 环境体检：%s" % ("就绪" if not n else "还差 %d 项（环境页可一键补齐）" % n))
        threading.Thread(target=run, daemon=True).start()

    def env_check(self):
        """按 envs/ 清单逐项体检，只留开着的环境：关掉的那路当它不存在。

        「关掉就不检测」必须断在这一处：待补数、横幅、欢迎页那几行「还差几项」、
        一键补齐的清单全都从这一份 items 派生。界面上各过滤一遍迟早漏一处，
        漏的结果就是用户反馈的那句「明明关掉了还一直提醒千问缺模型」。
        """
        from envkit import check as ec
        try:
            r = ec.check(ROOT, spec=self._spec())
        except Exception as e:
            return {"ok": False, "msg": "体检没跑成：%s" % e}
        on = self._env_on()
        is_on = lambda eid: on.get(eid, True)
        r["items"] = [it for it in r["items"] if is_on(str(it.get("env") or "base"))]
        # 开着的环境不再享受「可选＝默认别提醒」的待遇：开关就是本人的选择
        for it in r["items"]:
            it["optional"] = False
        todo = ec.fix_plan(r["items"])
        r["todo"] = [x["key"] for x in todo]
        r["gb"] = round(sum(float(x.get("gb") or 0) for x in todo), 1)
        r["env_on"] = on
        self._sync_env_on()
        cnt = {}
        for x in todo:
            eid = str(x.get("env") or "base")
            cnt[eid] = cnt.get(eid, 0) + 1
        # 每一格都用体检这一份 is_on 判定，总数则由这些格相加：让「合计几项」和
        # 各环境页那句「还差几项」不可能各说各话
        self.st["env_todo_by"] = {eid: (cnt.get(eid, 0) if is_on(eid) else 0)
                                  for eid in sorted(set(on) | set(cnt))}
        self.st["env_todo"] = sum(self.st["env_todo_by"].values())
        return r

    def env_set(self, env_id, on):
        """开/关一个环境：开关落盘，顺手把不该再占显存的引擎放掉，然后后台重新体检。

        关掉千问 = 千问的功能页与环境提醒一起消失；正在跑的那个引擎若已不属于任何
        开着的环境，就把显存交还系统（Moss 停子进程，千问卸管线），不然界面收走了、
        显存还占着。开启时什么都不装——只是把这一路重新放进体检。
        """
        from envkit import spec as sp
        eid = str(env_id or "").strip()
        spec = self._spec()
        if eid == "base" or not sp.env_meta(spec, eid):
            return {"ok": False, "msg": "没有这个环境：%s" % eid}
        want = bool(on)
        self.cfg.setdefault("env_on", {})[eid] = want
        self._save_cfg()
        self._sync_env_on()
        self._log("🎚️ 环境%s：%s" % ("开启" if want else "关闭",
                                    sp.env_meta(spec, eid).get("label") or eid))
        if not want:
            eng = str(self.cfg.get("engine", "qwen"))
            on = self._env_on()
            # Moss 引擎同时服务 moss 与 h3 两个环境（共用同一个 ComfyUI 子进程）
            still = on.get("qwen") if eng == "qwen" else (on.get("moss") or on.get("h3"))
            if not still:
                self._release_engine(eng)
        self.env_probe_bg()
        return {"ok": True, "env_on": self._env_on(), "cfg": self.cfg}

    def _release_engine(self, eng):
        """这一路的环境全关了：把它占的显存还回去（后台做，桥线程里做会冻界面）。"""
        def run():
            try:
                if eng == "moss":
                    if self.moss is not None and self.moss.occupying():
                        self.moss.stop()
                        self._log("🪫 环境已关闭：Moss（ComfyUI 子进程）停止，显存交还系统")
                elif self.mgr is not None and getattr(self.mgr, "pipe", None) is not None:
                    self.mgr.unload()
                    self._log("🪫 环境已关闭：千问模型卸载，显存交还系统")
                self.st["model_loaded"] = False
            except Exception as e:
                self._log("⚠️ 释放显存没成功：%s" % e)
        threading.Thread(target=run, daemon=True, name="env-release").start()

    def env_fix(self, keys=None):
        """一键补齐：pip 装包 / hf-mirror 续传权重 / 建目录，全在后台线程，逐行推进日志。

        keys=None 补全部可修项；否则只补点名的那几项。
        """
        if getattr(sys, "frozen", False):
            return {"ok": False, "msg": "打包版改不了自己的环境（pip 会装到 exe 外面）· "
                                        "请 clone 源码，用根目录的 启动.bat 补环境"}
        # 「查有没有在跑」和「标记在跑」得在一把锁里：pywebview 每次 js_api 单起线程，
        # 连点两下「一键补齐」能同时通过检查，然后两条 pip 一起动同一个 venv。
        with self._task_lock:
            if self.st["env_busy"]:
                return {"ok": False, "msg": "补全还在跑，看下面的日志"}
            if (self.st.get("dl") or {}).get("busy"):
                return {"ok": False, "msg": "手动下载还在跑，等它结束再补环境"}
            if self._dl is not None and self._dl.is_alive():
                return {"ok": False, "msg": "手动下载还在跑，等它结束再补环境"}
            self.st["env_busy"] = True
        try:
            from envkit import check as ec
            on = self._env_on()
            items = [it for it in ec.check(ROOT, spec=self._spec())["items"]
                     if on.get(str(it.get("env") or "base"), True)]
            for it in items:
                it["optional"] = False      # 同 env_check：开着就不算「可选」
        except Exception as e:
            self.st["env_busy"] = False
            return {"ok": False, "msg": "体检没跑成：%s" % e}
        todo = ec.fix_plan(items, keys)
        if not todo:
            self.st["env_busy"] = False
            return {"ok": True, "msg": "没有需要补的", "count": 0}

        self.st["env_steps"] = len(todo)
        self.st["env_step"] = 0
        self.st["env_label"] = ""

        def run():
            try:
                self._run_env_fix(todo, ec)
            except Exception as e:
                self._log("❌ 补全中途出错：%s" % e)
                self.st["env_todo"] = None
            finally:
                # 任何一条路走崩都不能把「补全中」永久挂在界面上
                self.st["env_busy"] = False
                self.st["env_steps"] = 0
                self.st["env_step"] = 0
                self.st["env_label"] = ""
                self.st["dl"] = {}

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True, "count": len(todo),
                "labels": [x["label"] for x in todo]}

    def _run_env_fix(self, todo, ec):
        ok_n, bad_n = 0, 0
        self._log("🔧 开始补全 %d 项：%s"
                  % (len(todo), "、".join(x["label"] for x in todo)))
        for i, it in enumerate(todo, 1):
            kind = it["fix"]["kind"]
            self.st["env_step"] = i
            self.st["env_label"] = it["label"]
            self.st["dl"] = {}
            self._log("[%d/%d] %s" % (i, len(todo), it["label"]))
            try:
                if kind == "pip":
                    ok = self._pip_fix(it)
                elif kind == "model":
                    ok = self._env_model_dl(it["fix"])
                elif kind == "comfyui":
                    ok = self._comfyui_clone(it["fix"])
                elif kind == "comfyvenv":
                    ok = self._comfyui_venv(it["fix"])
                elif kind == "dir":
                    os.makedirs(_abs_path(it["fix"]["path"]), exist_ok=True)
                    self._log("✅ 建好目录 %s" % it["fix"]["path"])
                    ok = True
                else:
                    ok = False
                if ok:
                    ok_n += 1
                else:
                    bad_n += 1
            except Exception as e:
                self._log("❌ %s 补全出错：%s" % (it["label"], e))
                bad_n += 1
        try:
            left = len(ec.fix_plan(ec.check(ROOT, spec=self._spec())["items"]))
        except Exception:
            left = -1
        self._log("%s 补全结束：成功 %d · 失败 %d · 还差 %d 项"
                  % ("✅" if not bad_n and not left else "⚠️", ok_n, bad_n, left))
        self.st["env_todo"] = left if left >= 0 else None

    def _pip_fix(self, item):
        """pip 子进程装一个包，输出只留关键行进日志（全量刷进来人反而看不见）。"""
        from envkit import check as ec
        import subprocess

        argv = ec.pip_argv(item, python=sys.executable)
        self._log("$ %s" % " ".join(argv[3:]))
        keep = re.compile(r"Collecting|Downloading|Download|Installing|Successfully|"
                          r"Requirement already|Building|Uninstalling|ERROR|"
                          r"note:|error:|Getting requirements", re.I)
        try:
            p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace",
                                 cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                 creationflags=NO_CONS)
        except OSError as e:
            self._log("❌ 起不了 pip：%s" % e)
            return False
        for line in p.stdout:
            line = line.strip()
            if line and keep.search(line):
                self._log(line)
        rc = p.wait()
        if rc:
            self._log("❌ %s 装失败（退出码 %s）：git 源要能连 github，"
                      "直连不稳就先开代理再点一次" % (item["label"], rc))
        return rc == 0

    # ------------------------------------------------------------ 内嵌 ComfyUI 与各环境权重
    def _run_stream(self, argv, cwd=None, keep=None, env=None):
        """跑一条命令，命中 keep 正则的行才进日志；返回退出码（起不了返回 -1）。"""
        from envkit import install as ei
        return ei.run_stream(argv, cwd=cwd, keep=keep, env=env, log=self._log)

    def _comfyui_clone(self, fix):
        from envkit import install as ei
        return ei.clone_comfyui(ROOT, fix, self._log)

    _PIP_KEEP = re.compile(r"Collecting|Downloading|Download|Installing|Successfully|"
                           r"Requirement already|Building|Uninstalling|ERROR|error:", re.I)

    def _comfyui_venv(self, fix):
        from envkit import install as ei
        return ei.ensure_comfyui_venv(ROOT, fix, self._log, python=sys.executable)

    def _env_model_dl(self, fix):
        """把一个环境的权重下到它清单里写的目录（同一个下载器，Motrix 可用时先交给它）。"""
        from envkit import download as hd
        from envkit import spec as sp
        repo = str(fix.get("repo") or "")
        reldir = str(fix.get("dir") or "")
        target = _abs_path(reldir)
        os.makedirs(target, exist_ok=True)
        allow = [str(a) for a in (fix.get("allow") or []) if a] or None
        cfg = self._dl_config()
        self._log("📥 下载 %s → %s（%d 个文件 · %d 线程 · 断点续传）"
                  % (repo, reldir, len(allow or []), int(cfg.get("jobs") or 8)))
        try:
            res = hd.download(
                repo, target, allow=allow,
                jobs=int(cfg.get("jobs") or 8),
                chunk_mb=int(cfg.get("chunk_mb") or 64),
                retries=int(cfg.get("retries") or 20),
                timeout=int(cfg.get("timeout") or 60),
                probe_timeout=int(cfg.get("probe_timeout") or 8),
                endpoints=cfg.get("endpoints"), config=cfg,
                on_progress=self._dl_event, on_log=self._log)
        except Exception as e:
            res = {"ok": False, "error": str(e)}
        finally:
            self.st["dl"] = {}
        if res.get("ok"):
            self._log("✅ 权重就位：%s · %s"
                      % (reldir, hd.fmt_bytes(res.get("bytes") or 0)))
            try:
                sp.write_extra_model_paths(ROOT, self._spec())
            except Exception:
                pass
            return True
        self._log("❌ 权重下载失败：%s" % (res.get("error") or "未知错误"))
        return False

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
        """显存读数。poll 每 0.8 秒就来一次，真按那个频率查驱动纯属空转——节流到 2.5 秒。

        走 nvidia-smi（60ms，等子进程时 GIL 是放开的）而不是 import torch：后者 warm
        也要 1.5 秒、冷盘十几秒，且全程独占 GIL，启动那几秒界面就是被它卡住的。
        torch 已经在内存里（千问模型载入过）就直接问它，连进程都不用起。
        """
        now = time.time()
        if now - getattr(self, "_vram_t", 0) < 2.5:
            return
        self._vram_t = now
        t = sys.modules.get("torch")
        try:
            if t is not None and t.cuda.is_available():
                free, total = t.cuda.mem_get_info()
            else:
                line = self._nvidia_smi()
                if not line:
                    return
                used, total = (float(x) for x in line)
                free = total - used
            self.st["vram_used"] = round((total - free) / 2 ** 30, 1)
            self.st["vram_total"] = round(total / 2 ** 30, 1)
        except Exception:
            pass

    def _nvidia_smi(self):
        """(已用 MiB, 总 MiB)；驱动不配合就返回 None，读数留在上一轮那个值。"""
        import subprocess

        si = None
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW   # 别闪黑框
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, timeout=5, startupinfo=si)
        if r.returncode:
            return None
        parts = r.stdout.decode("ascii", "replace").strip().splitlines()[0].split(",")
        return (float(parts[0]), float(parts[1]))

    def _refresh_gallery_count(self):
        out_dir = _abs_path(self.cfg["console"]["output_dir"])
        try:
            self.st["img_count"] = sum(1 for n in os.listdir(out_dir)
                                       if n.lower().endswith(MEDIA_EXT))
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

    def _after_shown():
        # 首帧出来之前一个重活都不许碰：体检与 API 恢复都要读磁盘、起子进程，
        # 跟 WebView2 起窗抢 CPU/磁盘，「界面显示慢」主要就是这儿来的。
        # （显存采样早先也在这儿 warm torch，现在换成 nvidia-smi 了，torch 只在
        #   真要载入千问模型时才 import，启动路径上一个重活都没有。）
        t0 = time.time()
        time.sleep(0.6)             # 让首帧真正落屏，别跟渲染收尾抢
        app.env_probe_bg()          # 环境页待补数的数据来源
        if app.cfg["api"].get("enabled"):
            app.api_set({})         # 上次开着 API：这次启动自动恢复监听
        app._log("🪟 界面首帧后 %.1f 秒，后台体检/服务恢复完成" % (time.time() - t0))

    window.events.shown += lambda: threading.Thread(target=_after_shown, daemon=True).start()
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
