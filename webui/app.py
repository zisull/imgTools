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
# v10 加「成片」页：剧本 → AI 拆分镜 → 逐段出片 → 合成一部，通道本地/云端共用。
# v11 页名从两字放成 3~5 字（文生图/局部重绘/剧本成片…）：两字在侧栏和页头都太像标签，
#     也不够说清这页干什么；组名仍是两字，作为层级区分。
# v12 环境四页合成一页「环境管理」（基础/千问/Moss/H3/云端账号做成页内子页），
#     13 页收到 9 页；组名改成「创作 / 系统」，两页都放得下视频与成片。
# 比它旧的配置在载入时按新默认表重排一次（只把用户改过的标签名带过去），见 _restructure_nav。
NAV_VER = 12

# 各版默认表用过的标签名。换代重排时，名字落在这张表里说明「用户没自己改过」，
# 直接换成新默认名；不在表里的才是他改的，原样保留。
LEGACY_TAB_NAMES = {
    "概览", "文生图", "透明素材", "图像编辑", "局部编辑", "提示词工坊", "Moss 生图",
    "画廊", "环境与模型", "模型管理", "日志", "设置", "API 服务",
    "生图", "编辑", "重绘", "词库", "环境",
    "视频", "基础", "千问",
    "云端",
    "成片", "Moss", "H3", "H3云端",
    "基础环境", "千问环境", "Moss 环境", "H3 视频", "H3 云端",
    "环境管理", "云端账号", "运行日志",
    "文生图", "图像编辑", "局部重绘", "视频生成", "剧本成片", "作品画廊", "全局设置",
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
    # 文本 API（OpenAI 兼容）：拆分镜与提示词润色都走它。key 只存本机 config.json，
    # 从不回给界面、不写日志；运行时也可用 DEEPSEEK_API_KEY / QIC_AI_KEY 顶掉这里。
    "ai": {"base": "https://api.deepseek.com", "model": "deepseek-chat", "key": "",
           "temp": 0.7, "timeout": 120, "max_tokens": 8192},
    # 成片：一段剧本 → N 个镜头 → 逐段出片 → 合成。
    # total=目标总秒数，shot=单镜秒数（只认 5/10/15），段数=round(total/shot)；
    # exec=cloud 走 RunningHub（不占显存），local 走本机 H3；mode=chain 用上一段尾帧接下一段，
    # shot=每镜独立（靠同一张首帧/参考图保持身份）。first 只有云端必填。
    "film": {"story": "", "total": 60, "shot": 15, "size": "768x1344", "cw": 768, "ch": 1344,
             "exec": "cloud", "mode": "chain", "first": "", "style": "电影感写实",
             "acct": "", "retry": 2, "seed": -1},
    # 导航：分组套一页一个标签；组名两字作层级，页名 3~5 字说清这页干什么
    # 环境四页并成一页（页内子页切换），导航只留九页：创作五页 + 系统四页
    "nav": [
        {"id": "g_out", "type": "group", "name": "创作", "icon": "flower", "children": [
            {"id": "t_gen", "type": "tab", "name": "文生图", "icon": "flower", "page": "t2i"},
            {"id": "t_edit", "type": "tab", "name": "图像编辑", "icon": "wand", "page": "edit"},
            {"id": "t_inp", "type": "tab", "name": "局部重绘", "icon": "brush", "page": "inpaint"},
            {"id": "t_vid", "type": "tab", "name": "视频生成", "icon": "film", "page": "video"},
            {"id": "t_film", "type": "tab", "name": "剧本成片", "icon": "play", "page": "film"},
        ]},
        {"id": "g_sys", "type": "group", "name": "系统", "icon": "cog", "children": [
            {"id": "t_env", "type": "tab", "name": "环境管理", "icon": "db", "page": "env"},
            {"id": "t_gal", "type": "tab", "name": "作品画廊", "icon": "image", "page": "gallery"},
            {"id": "t_log", "type": "tab", "name": "运行日志", "icon": "hist", "page": "logs"},
            {"id": "t_set", "type": "tab", "name": "全局设置", "icon": "cog", "page": "settings"},
        ]},
    ],
    # 环境页当前停在哪一格：base/qwen/moss/h3/cloud，页外跳转（去补齐、去登录）也写这里
    "env_tab": "base",
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


class FilmError(Exception):
    """成片流程里「能说清原因」的失败：消息直接给界面，不当异常抛栈。"""


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
        # 两条独立任务位：gpu=吃显存的本地活（生图/本地视频/成片/合成），
        # cloud=只等平台、不碰显卡的云端活。云端在跑时本地照旧能出图，
        # 反过来本地在跑也不耽误排队云端；真抢同一张卡的活仍然只认 gpu 这一条。
        self._lanes = {"gpu": None, "cloud": None}
        self._logs = []            # [seq, hh:mm:ss, text]
        self._seq = 0
        self._window = None
        self._thread = None
        self._stop = threading.Event()
        self._stop_cloud = threading.Event()
        self.mgr = None            # PipelineMgr：第一次载入时才 import（拉 torch）
        self.moss = None           # MossManager：切到 Moss 引擎时才建（拉 moss_mgr，纯 stdlib）
        self._api = None           # ApiServer：API 页开启时才 import（拉 fastapi）
        self._dl = None            # 模型下载线程（同一时间只允许一个）
        self._cloudx = None        # 云端账号：DrissionPage/浏览器都在第一次用云端的页时才起
        self._cloud_lock = threading.RLock()   # 账号操作互斥：并发固定 1（一只浏览器）
        # 云端出片占着那只共用浏览器（点运行 + 轮询），这期间账号操作一律让路
        self._cloud_gen = threading.Event()
        self._h3cloud = None       # cloudkit.gen.CloudH3：真要用云端才建
        self._filmpool = None      # cloudkit.pool.CloudPool：云端成片多号并行才建
        # 成片：一条长任务串起 N 段；停止位与普通任务分开，点停止只收当前这一段，
        # 已出的段留在盘上，下次「继续」从断点接着跑。
        self._film_stop = threading.Event()
        self._film_lock = threading.RLock()
        self._film = None          # 当前工程 project.json 的内存副本
        self._film_dir = ""        # 当前工程目录
        self._ff_ok = None         # FFmpeg 是否可用（缓存 15 秒，不必每轮扫清单）
        self._ff_ts = 0.0
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
            # 云端任务单独一条状态线：跑云端时 st.running 仍是本地的，
            # 两边互不覆盖，界面才知道「云端在跑、本地还能出图」
            "cloud": {"run": None, "task": "", "status": "", "done": 0, "total": 0,
                      "t_start": 0, "elapsed": 0, "last_fail": ""},
            # 成片：state=idle/planning/running/done/paused/stopped/failed；
            # shots 每段一条（等待/跑/完成/失败/跳过），界面拿它画时间段线
            "film": {"state": "idle", "phase": "", "status": "", "id": "", "title": "",
                     "dir": "", "total": 0, "done": 0, "current": 0, "elapsed": 0,
                     "film": "", "err": "", "shots": [], "missing": 0, "merge_ok": True,
                     "msg": "", "exec": "", "mode": ""},
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
            # 工具环境（ffmpeg）不是一路模型：没有「关掉不体检」这回事，
            # 也不该在开关表里占一格；缺了只是基础页多一行可补的扩展
            if e.get("tool"):
                continue
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
        """按新的默认表重排导航：v5 起恢复分组（创作 / 系统）。
        只把用户自己改过的标签名带过去；分组名与排布用默认表。"""
        old = {}
        old_page = {}      # 标签 id → 页面键：环境合成一页后，要能猜到他原来停在哪

        def collect(nodes):
            for n in nodes or []:
                if n.get("type") == "tab":
                    old[n.get("page")] = n.get("name")
                    old_page[n.get("id")] = n.get("page")
                collect(n.get("children"))
        collect(self.cfg.get("nav") or [])
        prev_tab = self.cfg.get("last_tab")

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
            # 原来停在环境某页 / 云端页的，合并后落到「环境管理」同一格，不把人甩回文生图
            p = old_page.get(prev_tab) or ""
            z = p[4:] if p.startswith("env_") else ("cloud" if p == "cloud" else "")
            if z in ("base", "qwen", "moss", "h3", "cloud"):
                self.cfg["last_tab"] = "t_env"
                self.cfg["env_tab"] = z
            else:
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
    def _cfg_public(self):
        """发给界面的配置：api token 照旧给（设置页要显示/复制），但文本 API 的 Key 永不外发。

        界面换配置时是整份替换（applyCfg），把 Key 抹成空串最稳：既不会在 DevTools/页面
        源码里留一份，也不会被下一次保存把空串写回盘上——Key 只走 ai_set 一条路。
        """
        c = copy.deepcopy(self.cfg)
        a = c.get("ai")
        if isinstance(a, dict):
            a.pop("key", None)
        return c

    def boot(self):
        return {"cfg": self._cfg_public(), "state": self._snap(),
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
        f = self.st.get("film") or {}
        s["film"] = dict(f)
        s["film"]["shots"] = [dict(x) for x in (f.get("shots") or [])]
        c = dict(self.st.get("cloud") or {})
        if c.get("run") and c.get("t_start"):
            c["elapsed"] = round(time.time() - c["t_start"], 1)
        s["cloud"] = c
        s["ffmpeg"] = self._ff()
        s["ai_key"] = self._ai_has()
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
        return {"ok": True, "cfg": self._cfg_public()}

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
            # kind=output：对话框直接从输出目录起，想翻画廊文件夹里的旧图不必再点几次
            kw = {}
            if kind == "output":
                out = _abs_path((self.cfg.get("console") or {}).get("output_dir", ""))
                if os.path.isdir(out):
                    kw["directory"] = out
            try:
                r = w.create_file_dialog(_fd("OPEN"),
                                         file_types=(_IMG_FILTER,), **kw)
            except Exception as e:
                self._log("⚠️ 文件对话框没打开：%s" % e)
                try:
                    r = w.create_file_dialog(_fd("OPEN"), **kw)   # 过滤串坏掉也要让人能选文件
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
        self._film_stop.set()
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
        if self._filmpool is not None:
            try:
                self._filmpool.close()          # 成片并行的那些浏览器也一起收掉
            except Exception:
                pass
        if self._cloudx is not None:
            try:
                self._cloudx["keep"].stop()
                self._cloudx["browsers"].close_all()   # 每个号那只，连主窗口一起收
            except Exception:
                pass
        self._save_cfg()
        return None

    # ------------------------------------------------------------ js_api：引擎
    def _busy(self):
        return self.st["running"] is not None

    @staticmethod
    def _lane(lane):
        return "cloud" if str(lane or "") == "cloud" else "gpu"

    def _claim(self, key, lane="gpu"):
        """占位：pywebview 给每个 js_api 调用单起一个线程，「先查 _busy 再起线程」
        中间能被另一个调用插进来，两个任务会同踩同一个 pipeline。查+占放一把锁里。

        两条任务位互不相干：云端任务只占 cloud 那条，gpu 照旧给本地生图用。
        st.running 只承载 gpu 这一条，界面里原有「running=本地在跑」的语义不变。
        """
        lane = self._lane(lane)
        with self._task_lock:
            if self._lanes.get(lane) is not None:
                return False
            self._lanes[lane] = key
            if lane == "gpu":
                self.st["running"] = key
                self.st["t_start"] = time.time()
                self.st["dup_last"] = False     # 上一轮的同图标记不能顺延到新任务
                self.st["last_fail"] = ""
                self._stop.clear()       # 上一个任务留下的停止位不能顺延到新任务
            else:
                c = self.st.setdefault("cloud", {})
                c.update(run=key, task=("成片" if key == "film" else "视频"),
                         status="准备中…", done=0, total=0, t_start=time.time(),
                         elapsed=0, last_fail="")
                self._stop_cloud.clear()
            return True

    def _release(self, lane="gpu"):
        lane = self._lane(lane)
        with self._task_lock:
            self._lanes[lane] = None
            if lane == "gpu":
                self.st["running"] = None
            else:
                c = self.st.setdefault("cloud", {})
                t0 = c.get("t_start") or 0
                c["elapsed"] = round(time.time() - t0, 1) if t0 else float(c.get("elapsed") or 0)
                c["run"] = None
                c["t_start"] = 0
                self._cloud_gen.clear()

    def _launch(self, key, fn, lane="gpu"):
        if not self._claim(key, lane):
            return False
        self._thread = threading.Thread(target=fn, daemon=True)
        self._thread.start()
        return True

    def _busy_msg(self, lane="gpu"):
        if self._lane(lane) == "cloud":
            c = self.st.get("cloud") or {}
            return "云端已有任务在跑：%s（等它结束或先点停止）" % (c.get("task") or "任务")
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
            return "千问环境已关闭 · 到「环境管理 → 千问」开启"
        if eng == "moss" and (on.get("moss") is False and on.get("h3") is False):
            return "Moss 环境已关闭 · 到「环境管理 → Moss」开启"
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

    def stop(self, key=None, lane=None):
        """停止：按通道各收各的。云端任务不该顺手把本地生图也停掉。"""
        key = str(key or "")
        lane = str(lane or "")
        if lane not in ("gpu", "cloud"):
            if self._lanes.get("cloud") and (not key or self._lanes["cloud"] == key):
                lane = "cloud"
            elif self._lanes.get("gpu") and (not key or self._lanes["gpu"] == key):
                lane = "gpu"
            elif self._lanes.get("gpu"):
                lane = "gpu"
            elif self._lanes.get("cloud"):
                lane = "cloud"
        if lane == "cloud" and self._lanes.get("cloud"):
            self._stop_cloud.set()
            c = self.st.setdefault("cloud", {})
            c["status"] = "停止中…"
            if str(c.get("run") or "") == "film":
                self._film_stop.set()
                f = self.st.get("film") or {}
                f["status"] = "正在停：这一段收尾后结束，已出的段都留着"
            self._log("⏹ 已请求停止云端任务：这边不再等了，平台上那半截可能还在跑")
            return {"ok": True}
        if lane == "gpu" and self._lanes.get("gpu"):
            self._stop.set()
            self.st["status"] = "停止中…"
            if self.st["running"] == "load":
                self._log("⏹ 已请求停止：模型载入是一次性动作，完成后将不再开始生成")
            elif self._cloud_gen.is_set():
                self._log("⏹ 已请求停止：这边不再等了，平台上那半截可能还在跑")
            else:
                self._log("⏹ 已请求停止：等当前这一步去噪完成后中断")
            return {"ok": True}
        return {"ok": False, "msg": "没有运行中的任务"}

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
            return {"ok": False, "msg": "H3 环境已关闭 · 到「环境管理 → H3」开启"}
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
            return {"ok": False, "msg": "云端要浏览器：到「环境管理 → 基础」补齐 DrissionPage 后重开软件"}
        if self._lanes.get("cloud"):
            return {"ok": False, "msg": self._busy_msg("cloud")}
        try:
            row = g.account(str(v.get("cloud_acct") or ""))
        except Exception as e:
            return {"ok": False, "msg": "云端还没备好：%s" % e}
        # 界面没选号时 account() 会回第一个可用号：把号写回去，
        # 出片那段才不会落到别的浏览器里
        v["cloud_acct"] = row["id"]
        # 2 号起的号有自己的浏览器：单条视频也进它自己那只，别去顶 1 号的窗口
        g = self._cloud_h3_for(row["id"])
        try:
            kind, src = g.wf_src(str(v.get("cloud_wf") or ""))
            # 本地文件没有平台编号：宿主页到开页时再自动借，这里先验结构；
            # 「API 格式 / 缺节点 / 连线断了 / 不是 H3 图」都能当场说清，不用等浏览器。
            if kind == "file":
                g.check_wf_file(src)
                if not g.host_url():
                    return {"ok": False,
                            "msg": "本地工作流要借一页平台画布入口：先在「环境管理 → 云端账号」"
                                   "填一份能打开的 H3 工作流地址当兜底"}
                wf = ""
            else:
                wf = g.wf_url(src)
        except Exception as e:
            return {"ok": False, "msg": "%s" % e}
        if not self._launch("video", lambda: self._do_video_cloud(v), lane="cloud"):
            return {"ok": False, "msg": self._busy_msg("cloud")}
        w, h = self._h3_size(v, hi=self.H3_HI_CLOUD)
        self._log("☁️ 云端出片：%ds · %dx%d · 号「%s」· 浏览器 %d · %s（按平台计费）"
                  % (_to_int(v.get("seconds"), 5, 5, 15), w, h, row["name"],
                     self._cloudkit()["browsers"].slot(row["id"]),
                     ("本地 · " + os.path.basename(src)) if kind == "file" else wf))
        return {"ok": True, "total": 1, "exec": "cloud", "acct": row["name"]}

    def _do_video_cloud(self, v):
        c = self.st.setdefault("cloud", {})
        c.update(task="视频", status="云端准备中…", done=0, total=1, last_fail="")
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
                # 云端这份工作流没有纯文字模式：图不在了就当场说清，别让人以为还能出片
                self._log("⚠️ 参考图不在了：%s · 云端这份工作流必须有图，这一段会直接停下"
                          % os.path.basename(str(v.get("first"))))
            path = self._cloud_h3_for(p["acct"]).run(
                p, on_progress=self._cloud_step,
                should_stop=self._stop_cloud.is_set)
            if self._stop_cloud.is_set():
                c["status"] = "已停止"
                return
            self._publish(path, mode="h3", params=v, size="%dx%d" % (w, h),
                          steps=self.H3_STEPS, seed=-1,
                          sec=round(time.time() - t0, 1),
                          name=os.path.basename(path))
            c["done"] = 1
            c["status"] = "✅ 完成"
            self._log("── 结束 ──")
        except Exception as e:
            c["last_fail"] = str(e)
            if self._stop_cloud.is_set():
                self._log("⏹ 已停止：云端那半段可能还在平台上跑，去「云端账号」看一眼")
                c["status"] = "已停止"
            else:
                self._log("❌ 云端出片失败：%s" % e)
                c["status"] = "出片失败"
        finally:
            self._release("cloud")

    def _cloud_step(self, msg):
        """云端只有一条「等多久」的路可报：没有步数刻度，就把实话写在状态行上。"""
        if not self._stop_cloud.is_set():
            self.st.setdefault("cloud", {})["status"] = str(msg or "云端出片中…")[:120]

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

    # ------------------------------------------------------------ js_api：文本 API
    # 只服务拆镜与润色：Key 只在本机，界面只拿到「有没有」；任何错误先过 _scrub 再回。
    def _ai(self):
        from filmkit import ai as fa
        return fa

    def _ai_has(self):
        try:
            return self._ai().has_key(self.cfg)
        except Exception:
            return False

    def _ai_err(self, e):
        fa = self._ai()
        try:
            key = fa.settings(self.cfg)["key"]
        except Exception:
            key = ""
        return fa._scrub(str(e), key)[:400]

    def ai_state(self):
        s = self._ai().settings(self.cfg)
        return {"ok": True, "has_key": bool(s["key"]),
                "base": s["base"], "model": s["model"],
                "env": bool(os.environ.get("DEEPSEEK_API_KEY")
                            or os.environ.get("QIC_AI_KEY")),
                "saved": bool(str((self.cfg.get("ai") or {}).get("key") or "").strip())}

    def ai_set(self, patch=None):
        p = dict(patch or {})
        a = self.cfg.setdefault("ai", {})
        key = str(p.get("key") or "").strip()
        if key:
            a["key"] = key
        for k in ("base", "model"):
            v = str(p.get(k) or "").strip()
            if v:
                a[k] = v
        if "temp" in p:
            try:
                a["temp"] = max(0.0, min(1.5, float(p["temp"])))
            except (TypeError, ValueError):
                pass
        self._save_cfg()
        self._log("🔐 文本 API 设置已更新（Key %s）"
                  % ("已保存" if a.get("key") else "未填"))
        return self.ai_state()

    def ai_key_clear(self):
        (self.cfg.setdefault("ai", {})).pop("key", None)
        self._save_cfg()
        self._log("🔐 文本 API Key 已清除")
        return self.ai_state()

    def ai_test(self):
        try:
            r = self._ai().test(self.cfg)
            self._log("🔎 文本 API 可用：%s · %d 毫秒" % (r.get("model"), r.get("ms") or 0))
            return r
        except Exception as e:
            msg = self._ai_err(e)
            self._log("❌ 文本 API 测试失败：%s" % msg)
            return {"ok": False, "msg": msg}

    def ai_polish(self, text, kind="image"):
        try:
            out = self._ai().polish(text, kind, self.cfg)
            self._log("✨ 润色完成：%d 字 → %d 字" % (len(str(text or "")), len(out)))
            return {"ok": True, "text": out}
        except Exception as e:
            return {"ok": False, "msg": self._ai_err(e)}

    # ------------------------------------------------------------ js_api：剧本成片
    # 一条长任务串起 N 段：拆分镜 → 逐段出片（本地/云端同一份接口）→ 合成。
    # 每段先落盘再记账；中断后按「非空文件即已完成」续跑，失败只在原位标红、不跳号。
    def _ff(self):
        now = time.time()
        if self._ff_ok is None or now - self._ff_ts > 15:
            try:
                from filmkit import stitch
                self._ff_ok = stitch.available(ROOT)
            except Exception:
                self._ff_ok = False
            self._ff_ts = now
        return bool(self._ff_ok)

    def _film_should_stop(self):
        # 云端成片只认成片自己的停止位：本地生图点停止不能顺手把云端那部也停掉
        if getattr(self, "_film_cloud", False):
            return bool(self._film_stop.is_set())
        return bool(self._stop.is_set() or self._film_stop.is_set())

    def _film_cfg(self, payload=None):
        f = dict(self.cfg.get("film") or {})
        f.update(dict(payload or {}))
        return f

    def _film_ratio(self, size):
        m = re.match(r"^(\d+)x(\d+)$", str(size or "").lower())
        if not m:
            return "9:16"
        w, h = int(m.group(1)), int(m.group(2))
        r = float(w) / max(1, h)
        if abs(r - 1.0) < 0.05:
            return "1:1"
        return "16:9" if r > 1 else "9:16"

    def _film_n(self, total, shot):
        shot = shot if shot in (5, 10, 15) else 15
        return max(1, min(40, int(round(float(total) / shot)))), shot

    def _film_shots(self, proj, d=""):
        """给界面的分段表：相对路径留在工程里，绝对路径只给这一次轮询用。

        界面点缩略图要交给系统播放器/预览，join 路径的活别让 JS 再猜一遍
        （Windows 的分隔符与相对路径的斜杠方向是两套）；文件真在才算有。
        """
        from filmkit import project as prj
        out = []
        for x in (proj.get("shots") or []):
            s = dict(x)
            f = prj.abs_path(d, s.get("file") or "") if d else ""
            fr = prj.abs_path(d, s.get("frame") or "") if d else ""
            s["file_abs"] = f if f and os.path.isfile(f) else ""
            s["frame_abs"] = fr if fr and os.path.isfile(fr) else ""
            out.append(s)
        return out

    def _film_view(self, proj, **kw):
        shots = self._film_shots(proj, str(kw.get("dir") or self._film_dir or ""))
        cur = next((x["i"] for x in shots if x.get("state") == "run"), 0)
        v = {
            "state": "idle", "phase": "", "status": "", "id": str(proj.get("id") or ""),
            "title": str(proj.get("title") or ""), "dir": self._film_dir or "",
            "total": len(shots), "done": sum(1 for x in shots if x.get("state") == "done"),
            "current": cur, "elapsed": 0, "film": str(proj.get("film") or ""), "err": "",
            "missing": sum(1 for x in shots if x.get("state") in ("fail", "skip")),
            "merge_ok": bool(proj.get("merge_ok", True)), "msg": "",
            "exec": str(proj.get("exec") or ""), "mode": str(proj.get("mode") or ""),
            "parallel": 0, "shots": shots,
        }
        v.update(kw)
        return v

    def _film_step(self, msg):
        t = str(msg or "").strip()
        if not t:
            return
        f = self.st.get("film") or {}
        if f.get("state") in ("running", "planning"):
            f["status"] = t[:120]
            self.st["status"] = t[:120]

    # 这几类错误重试同一份工作流也不会变：一份一份重试只是把时间再烧一遍
    FILM_WF_FATAL = ("云端前端没能加载这份工作流", "云端 ComfyUI 前端没接住这份工作流",
                     "这份工作流里没有 H3 主节点", "没有 VHS_VideoCombine",
                     "这是 API 格式", "这份 JSON 里没有画布", "工作流连线",
                     "本地工作流文件读不了", "云端编辑器还没挂好")

    def _film_precheck(self, f, count, base_dir=""):
        """开跑前把「一定跑不动」的话说完：通道、账号、工作流、首帧、ffmpeg。"""
        exec_ = "cloud" if str(f.get("exec")) == "cloud" else "local"
        hi = self.H3_HI_CLOUD if exec_ == "cloud" else self.H3_HI_LOCAL
        if f.get("width") and f.get("height"):
            w, h = int(f["width"]), int(f["height"])
        else:
            w, h = self._h3_size({"size": f.get("size"), "cw": f.get("cw"),
                                  "ch": f.get("ch")}, hi=hi)
        raw_first = str(f.get("first") or "")
        if base_dir and raw_first and not os.path.isabs(raw_first):
            first = os.path.join(base_dir, *raw_first.replace("\\", "/").split("/"))
            first = first if os.path.isfile(first) else ""
        else:
            first = self._ref_path(raw_first)
        acct = str(f.get("acct") or "")
        acct_id, acct_name = "", ""
        wf = str((self.cfg.get("cloud") or {}).get("workflow")
                 or f.get("workflow") or "")
        err = ""
        if exec_ == "cloud":
            if not self._dp_ready():
                err = "云端要浏览器：到「环境管理 → 基础」补齐 DrissionPage 后重开软件"
            elif self._cloud_gen.is_set():
                err = "云端已经有一段在跑：等它结束再开新片"
            else:
                try:
                    g = self._cloud_h3()
                    # 账号留空＝按空闲自动分配；指定了就先把它排前面，
                    # 但两次失败会被标 fail 并换别的号，所以这里不锁死单号。
                    rows = [a for a in g.store.list()
                            if (g.store.load(a["id"]) or {}).get("cookies")
                            and str(a.get("state") or "") != "fail"]
                    if not rows:
                        bad = [a for a in g.store.list()
                               if str(a.get("state") or "") == "fail"]
                        if bad:
                            raise RuntimeError("可用的号都被标成「出片失败」了：到"
                                               "「环境管理 → 云端账号」重新登录或换号")
                        raise RuntimeError("还没有可用的登录账号：到「环境管理 → 云端账号」"
                                           "新建登录并保存")
                    if acct:
                        hit = next((a for a in rows if a["id"] == acct), None)
                        if hit:
                            acct_id, acct_name = hit["id"], hit["name"]
                        else:
                            old = g.store.get(acct)
                            if old and str(old.get("state") or "") == "fail":
                                self._log("☁️ 这个号上次出片失败，已跳过：这次由其它空闲号接")
                            else:
                                raise RuntimeError("这个账号还没有保存过登录态")
                    if not acct_id:
                        acct_name = "自动分配"
                    kind, src = g.wf_src(wf)
                    if kind == "file":
                        g.check_wf_file(src)
                        if not g.host_url():
                            raise RuntimeError("本地工作流要借一页平台画布入口："
                                               "先在「环境管理 → 云端账号」填一份能打开的"
                                               " H3 工作流地址当兜底")
                    else:
                        g.wf_url(src)
                    if not first:
                        err = ("云端这份工作流按参考生成：先在「首帧」那格选一张图"
                               "（本地通道可纯文字起步）")
                except Exception as e:
                    err = str(e)
        elif not self._env_on().get("h3"):
            err = "H3 环境已关闭 · 到「环境管理 → H3」开启"
        if not err and str(f.get("mode")) == "chain" and not self._ff():
            err = ("接帧模式要 FFmpeg 抽尾帧：到「环境管理 → 基础」补上"
                   "「FFmpeg 静态包」（约 190 MB）")
        return {"err": err, "exec": exec_, "width": w, "height": h, "first": first,
                "acct": acct_id, "acct_name": acct_name, "wf": wf, "count": count}

    def _film_new(self, f, shots, title, chk):
        from filmkit import project as prj
        out_dir = _abs_path(self.cfg["console"]["output_dir"])
        d = prj.new_dir(out_dir)
        proj = {
            "ver": 1, "id": os.path.basename(d), "title": title or "未命名短剧",
            "story": str(f.get("story") or ""), "exec": chk["exec"],
            "mode": "chain" if str(f.get("mode")) == "chain" else "shot",
            "shot_sec": _to_int(f.get("shot"), 15, 5, 15),
            "width": chk["width"], "height": chk["height"],
            "acct": chk["acct"], "acct_name": chk["acct_name"], "workflow": chk["wf"],
            "style": str(f.get("style") or ""), "first": "",
            "seed": _to_int(f.get("seed"), -1, -1, 10 ** 12),
            "retry": _to_int(f.get("retry"), 2, 0, 5),
            "shots": shots, "film": "", "merge_ok": True, "merge_missing": 0,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        first = chk["first"]
        if first:
            ext = os.path.splitext(first)[1].lower()
            if ext not in IMG_EXT:
                ext = ".png"
            dst = os.path.join(d, "first" + ext)
            shutil.copy2(first, dst)
            proj["first"] = prj.rel(d, dst)
        prj.save(d, proj)
        return d, proj

    def _film_prompt(self, proj, sh):
        p = str(sh.get("prompt") or "").strip()
        if str(proj.get("mode")) == "chain" and int(sh.get("i") or 1) > 1:
            p += ("。承接上一段结尾：人物、服装、场景与光线保持一致，"
                  "动作从上一段最后的状态自然继续。")
        style = str(proj.get("style") or "").strip()
        if style and style not in p:
            p += "。画面风格：" + style
        return p

    def _film_frame(self, d, sh):
        from filmkit import project as prj, stitch
        if not self._ff():
            return ""
        video = prj.abs_path(d, sh.get("file") or "")
        if not video or not os.path.isfile(video):
            return ""
        fr = prj.abs_path(d, sh.get("frame") or prj.frame_file(sh["i"]))
        got = stitch.last_frame(ROOT, video, fr)
        if got:
            sh["frame"] = prj.rel(d, got)
            return got
        return ""

    def _film_one(self, d, proj, sh, first, worker=None):
        from filmkit import project as prj
        out = prj.abs_path(d, prj.shot_file(sh["i"]))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        w = _to_int(proj.get("width"), 768, 16, 8192)
        h = _to_int(proj.get("height"), 1344, 16, 8192)
        prompt = self._film_prompt(proj, sh)
        if str(proj.get("exec")) == "cloud":
            # worker 是池里的一格（一个号一只浏览器）；没有就走主窗口那只（单条视频那条路）
            acct = str(worker.aid if worker is not None else (proj.get("acct") or ""))
            gen = worker.gen if worker is not None else self._cloud_h3()
            who = (" · " + worker.name) if worker is not None else ""
            p = {"prompt": prompt, "seconds": sh["seconds"], "width": w, "height": h,
                 "first": first, "acct": acct,
                 "wf": str(proj.get("workflow") or ""), "out_dir": os.path.dirname(out)}
            got = gen.run(
                p, on_progress=lambda m: self._film_step(
                    "第 %d 段%s · %s" % (sh["i"], who, m)),
                should_stop=self._film_should_stop)
        else:
            mgr = self._get_moss()
            params = self._video_params({"prompt": prompt, "seconds": sh["seconds"],
                                         "size": "%dx%d" % (w, h)})
            if first:
                params["first_image"] = mgr.upload_image(first)
            seed = _to_int(proj.get("seed"), -1, -1, 10 ** 12)
            params["seed"] = _rand_seed() if seed < 0 else seed
            paths = mgr.generate(
                params,
                on_progress=lambda dn, t: self._film_step(
                    "第 %d 段 · 采样 %d/%d" % (sh["i"], dn, t)),
                should_stop=self._film_should_stop,
                out_dir=os.path.dirname(out), out_prefix="film%03d" % sh["i"])
            if not paths:
                raise FilmError("工作流跑完但没取回片子")
            got = paths[0]
            for extra in paths[1:]:
                try:
                    os.remove(extra)
                except OSError:
                    pass
        if os.path.abspath(got) != os.path.abspath(out):
            try:
                os.replace(got, out)
            except OSError:
                shutil.move(got, out)
        if not os.path.isfile(out) or os.path.getsize(out) <= 0:
            raise FilmError("这一段没落盘")
        return out

    def _film_merge(self, d, proj):
        from filmkit import project as prj, stitch
        paths = [prj.abs_path(d, s.get("file") or "") for s in (proj.get("shots") or [])
                 if s.get("state") == "done" and prj.ok_file(d, s)]
        if not paths:
            raise stitch.StitchError("还没有一段成功出片")
        out_dir = _abs_path(self.cfg["console"]["output_dir"])
        out = prj.final_path(out_dir, proj.get("title") or "短剧")
        r = stitch.concat(ROOT, paths, out, log=self._log)
        proj["film"] = r["path"]
        proj["merge_ok"] = len(paths) == len(proj.get("shots") or [])
        proj["merge_missing"] = len(proj.get("shots") or []) - len(paths)
        prj.save(d, proj)
        return r["path"]

    def _film_publish(self, proj, path, sec):
        self._publish(path, mode="film",
                      params={"prompt": str(proj.get("story") or "")[:200],
                              "negative": "", "_saved": []},
                      size="%dx%d" % (_to_int(proj.get("width"), 0, 0, 8192),
                                      _to_int(proj.get("height"), 0, 0, 8192)),
                      steps=0, seed=_to_int(proj.get("seed"), -1, -1, 10 ** 12),
                      sec=sec, name=os.path.basename(path))

    CLOUD_TRIES = 2         # 同一个号最多两次：第二次前重启那只浏览器

    def _film_cloud_try(self, d, proj, sh, first, fs, worker, total):
        """一个号跑一段：失败先重启浏览器再试一次。回 (ok, err, fatal)。"""
        from filmkit import project as prj
        last = ""
        for attempt in range(self.CLOUD_TRIES):
            if self._film_should_stop():
                return False, "已停止", False
            sh["acct_name"] = worker.name
            tail = "" if attempt == 0 else " · 重启浏览器重试"
            self._log("🎬 第 %d 段 · %s%s：%d 秒 · 云端"
                      % (sh["i"], worker.name, tail, sh["seconds"]))
            t1 = time.time()
            try:
                path = self._film_one(d, proj, sh, first, worker=worker)
                sh["file"] = prj.rel(d, path)
                sh["sec"] = round(time.time() - t1, 1)
                return True, "", False
            except Exception as e:
                last = str(e)[:300]
                self._log("⚠️ 第 %d 段 · %s 失败：%s"
                          % (sh["i"], worker.name, last))
                if self._film_should_stop():
                    return False, last, False
                # 工作流本身加载不上：换号也一样，整批停在这里（调用方暂停）
                if any(k in last for k in self.FILM_WF_FATAL):
                    return False, last, True
                if attempt + 1 < self.CLOUD_TRIES:
                    self._film_step("第 %d 段 · %s 没出成：重启这只浏览器再试一次"
                                    % (sh["i"], worker.name))
                    try:
                        worker.host.restart()
                    except Exception as re:
                        from cloudkit.store import brief_error
                        self._log("⚠️ 重启「%s」的浏览器失败：%s"
                                  % (worker.name, brief_error(re)))
                    time.sleep(2.0)
        return False, last, False

    def _film_cloud_state(self, d, proj, fs, t0, note=""):
        """并行时多个线程都会改进度：统一在这把锁下落盘，别各写各的。"""
        from filmkit import project as prj
        with self._film_lock:
            fs["done"] = sum(1 for x in proj["shots"] if x.get("state") == "done")
            fs["missing"] = sum(1 for x in proj["shots"]
                                if x.get("state") in ("fail", "skip"))
            fs["elapsed"] = round(time.time() - t0, 1)
            fs["shots"] = self._film_shots(proj, d)
            if note:
                fs["status"] = note[:160]
            self.st.setdefault("cloud", {})["status"] = fs.get("status") or ""
            self.st["status"] = fs.get("status") or ""
            prj.save(d, proj)

    def _film_cloud_serial(self, d, proj, fs, t0, workers):
        """接帧模式：参考图是上一段尾帧，只能一段一段来；失败时换号续跑。"""
        from filmkit import project as prj
        total = len(proj["shots"])
        last_ref = prj.abs_path(d, proj.get("first") or "")
        fail_run = 0
        for sh in proj["shots"]:
            if self._film_should_stop():
                break
            if prj.ok_file(d, sh):
                sh["state"] = "done"
                sh["err"] = ""
                fr = prj.abs_path(d, sh.get("frame") or "")
                if not fr or not os.path.isfile(fr):
                    fr = self._film_frame(d, sh) or ""
                if fr:
                    last_ref = fr
                continue
            sh["state"] = "run"
            sh["err"] = ""
            fs["current"] = sh["i"]
            self._film_cloud_state(d, proj, fs, t0,
                                   "第 %d/%d 段 · 云端串行（%d 个号待命）"
                                   % (sh["i"], total, len(workers)))
            tried, ok, fatal, last = set(), False, False, ""
            while not self._film_should_stop():
                w = next((x for x in workers
                          if not x.bad and x.aid not in tried), None)
                if w is None:
                    break
                tried.add(w.aid)
                w.busy = True
                ok, last, fatal = self._film_cloud_try(
                    d, proj, sh, last_ref, fs, w, total)
                w.busy = False
                if ok or fatal or self._film_should_stop():
                    break
                self._film_pool().mark_fail(w, last)
                self._film_cloud_state(d, proj, fs, t0,
                                       "第 %d 段 · %s 没出成，换下一个号"
                                       % (sh["i"], w.name))
            if self._film_should_stop():
                sh["state"] = "wait"
                break
            if ok:
                sh["state"] = "done"
                fail_run = 0
                self._log("✅ 第 %d 段出完（%s）：%s · %.1f 秒"
                          % (sh["i"], sh.get("acct_name") or "云端",
                             os.path.basename(sh["file"]), sh["sec"]))
                fr = self._film_frame(d, sh)
                if fr:
                    last_ref = fr
                else:
                    self._log("⚠️ 第 %d 段抽不出尾帧：下一段沿用上一张参考图"
                              % sh["i"])
            else:
                sh["state"] = "fail"
                sh["err"] = last or "没有可用的账号"
                fail_run += 1
                self._log("❌ 第 %d 段跳过（不跳号）：%s"
                          % (sh["i"], sh["err"]))
                if fatal:
                    fs["state"] = "paused"
                    fs["phase"] = "暂停"
                    fs["msg"] = ("工作流没加载上，已停下：%s。修好工作流后点「继续」，"
                                 "已经出完的段都留着" % sh["err"][:120])
                    fs["status"] = "工作流没加载上，已停下"
                    self._log("⛔ 工作流没加载上：整批停下，不重试")
                    break
                if fail_run >= 5:
                    fs["state"] = "paused"
                    fs["phase"] = "暂停"
                    fs["msg"] = ("连续 5 段失败，已暂停：先处理登录/额度/账号，"
                                 "再点「继续」")
                    fs["status"] = fs["msg"]
                    self._log("⛔ 连续 5 段失败，整批暂停")
                    break
            self._film_cloud_state(d, proj, fs, t0)
        return last_ref

    def _film_cloud_parallel(self, d, proj, fs, t0, workers):
        """逐镜模式：空闲的号自己领下一段，一段最多试两个号。"""
        from filmkit import project as prj
        from cloudkit import pool as cp
        total = len(proj["shots"])
        cap = max(1, min(cp.MAX_PARALLEL, len(workers),
                         int((self.cfg.get("cloud") or {}).get("parallel") or 3)))
        fs["parallel"] = cap
        pending = []
        for sh in proj["shots"]:
            if prj.ok_file(d, sh):
                sh["state"] = "done"
                sh["err"] = ""
            else:
                pending.append(sh)
        if not pending:
            return
        cond = threading.Condition()
        sem = threading.Semaphore(cap)
        state = {"inflight": 0, "fail_run": 0, "abort": False, "fatal": ""}
        tried = {sh["i"]: set() for sh in pending}
        alive = set(w.aid for w in workers)

        def pick(w):
            """挑一段这个号还没试过的；返回 (下标, 段)。"""
            for i, sh in enumerate(pending):
                if w.aid not in tried[sh["i"]]:
                    return i, sh
            return None

        def take(w):
            """拿下一段；没有可接的且手上也没人在跑时就退出。"""
            with cond:
                while not state["abort"] and not self._film_should_stop():
                    got = pick(w)
                    if got is not None:
                        i, sh = got
                        pending.pop(i)
                        tried[sh["i"]].add(w.aid)
                        state["inflight"] += 1
                        return sh
                    if state["inflight"] == 0:
                        return None
                    cond.wait(0.5)
                return None

        def give_back(sh, last):
            """两次都没出成：标坏号，再把这段交给别的空闲号。"""
            others = [x for x in workers
                      if x.aid in alive and x.aid not in tried[sh["i"]]]
            if others:
                pending.insert(0, sh)
                sh["state"] = "wait"
                sh["err"] = last
                self._log("↪️ 第 %d 段转给别的号：%s"
                          % (sh["i"], "、".join(x.name for x in others[:3])))
            else:
                sh["state"] = "fail"
                sh["err"] = last or "没有可用的账号"
                state["fail_run"] += 1
                self._log("❌ 第 %d 段跳过（不跳号）：%s" % (sh["i"], sh["err"]))
            cond.notify_all()

        def work(w):
            while not state["abort"] and not self._film_should_stop():
                sem.acquire()
                sh, got = None, False
                try:
                    sh = take(w)
                    if sh is None:
                        return
                    got = True
                    with self._film_lock:
                        sh["state"] = "run"
                        sh["err"] = ""
                        fs["current"] = sh["i"]
                    self._film_cloud_state(d, proj, fs, t0,
                                           "云端 %d 个号并行 · 已完成 %d/%d"
                                           % (cap, fs.get("done") or 0, total))
                    ok, last, fatal = self._film_cloud_try(
                        d, proj, sh, prj.abs_path(d, proj.get("first") or ""),
                        fs, w, total)
                    if self._film_should_stop():
                        sh["state"] = "wait"
                        return
                    if fatal:
                        with self._film_lock:
                            sh["state"] = "fail"
                            sh["err"] = last
                            fs["state"] = "paused"
                            fs["phase"] = "暂停"
                            fs["msg"] = ("工作流没加载上，已停下：%s。修好工作流后"
                                         "点「继续」，已经出完的段都留着" % last[:120])
                            fs["status"] = "工作流没加载上，已停下"
                        state["fatal"] = last
                        state["abort"] = True
                        self._film_stop.set()       # 让其它号手上那段也收手
                        self._log("⛔ 工作流没加载上：整批停下，不重试")
                        return
                    if ok:
                        with cond:
                            state["fail_run"] = 0
                        with self._film_lock:
                            sh["state"] = "done"
                            self._log("✅ 第 %d 段出完（%s）：%s · %.1f 秒"
                                      % (sh["i"], sh.get("acct_name") or "云端",
                                         os.path.basename(sh["file"]), sh["sec"]))
                            fr = self._film_frame(d, sh)
                            if not fr:
                                self._log("⚠️ 第 %d 段抽不出尾帧：时间线少张缩略图"
                                          % sh["i"])
                        self._film_cloud_state(d, proj, fs, t0)
                        continue        # 号还活着，接着领下一段
                    # 这个号两次都没出成：标 fail，并把它从「还能接活」里拿掉
                    self._film_pool().mark_fail(w, last)
                    with cond:
                        alive.discard(w.aid)
                        give_back(sh, last)
                        if state["fail_run"] >= 5 and not state["abort"]:
                            state["abort"] = True
                            state["fatal"] = "连续 5 段失败"
                            self._film_stop.set()
                    self._film_cloud_state(d, proj, fs, t0)
                    if state["abort"]:
                        with self._film_lock:
                            fs["state"] = "paused"
                            fs["phase"] = "暂停"
                            fs["msg"] = ("连续 5 段失败，已暂停：先处理登录/额度/账号，"
                                         "再点「继续」")
                            fs["status"] = fs["msg"]
                        self._log("⛔ 连续 5 段失败，整批暂停")
                    return
                finally:
                    if got:
                        with cond:
                            state["inflight"] -= 1
                            cond.notify_all()
                    sem.release()

        threads = [threading.Thread(target=work, args=(w,), daemon=True,
                                    name="film-%s" % w.aid) for w in workers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 所有号都试过仍剩下的：老实标失败，不跳号
        with cond:
            left = list(pending)
            pending.clear()
        for sh in left:
            if self._film_should_stop() or fs.get("state") == "paused":
                if sh.get("state") != "done":
                    sh["state"] = "wait"
            else:
                sh["state"] = "fail"
                sh["err"] = state["fatal"] or "没有空闲的账号能接这一段"
        self._film_cloud_state(d, proj, fs, t0)

    def _film_cloud_run(self, d, proj, fs, t0):
        """云端成片：接帧串行、逐镜并行；失败重启浏览器再试，二次失败换号。"""
        pool = self._film_pool()
        rows = pool.accounts()
        if not rows:
            raise FilmError("没有可用的云端账号：到「环境管理 → 云端账号」登录并保存"
                            "（标成「出片失败」的号要重新登录或换号）")
        pref = str(proj.get("acct") or "")
        if pref:
            rows.sort(key=lambda a: 0 if a["id"] == pref else 1)
        workers = pool.workers(rows)
        if str(proj.get("mode")) == "chain":
            self._log("☁️ 云端成片：接帧串行 · %d 个号待命（失败自动换号）"
                      % len(workers))
            self._film_cloud_serial(d, proj, fs, t0, workers)
        else:
            cap = min(4, len(workers),
                      int((self.cfg.get("cloud") or {}).get("parallel") or 3))
            self._log("☁️ 云端成片：逐镜并行 · %d 个号（最多同时 %d 个，每号一只浏览器）"
                      % (len(workers), max(1, cap)))
            self._film_cloud_parallel(d, proj, fs, t0, workers)

    def _film_run(self, d, proj):
        from filmkit import project as prj
        t0 = time.time()
        fs = self.st["film"]
        fs["state"] = "running"
        fs["phase"] = "出片"
        fs["status"] = "准备中…"
        fs["shots"] = self._film_shots(proj, d)
        retry = _to_int(proj.get("retry"), 2, 0, 5)
        chain = str(proj.get("mode")) == "chain"
        cloud = str(proj.get("exec")) == "cloud"
        self._film_cloud = cloud
        fail_run = 0
        last_ref = prj.abs_path(d, proj.get("first") or "")
        try:
            if cloud:
                self._cloud_gen.set()
            else:
                self._ensure_engine("moss")
                self._film_step("拉起 H3 引擎…")
                mgr = self._get_moss()
                if not mgr.alive():
                    mgr.start(tier=str((self.cfg.get("moss") or {}).get("tier", "daily")),
                              should_stop=self._film_should_stop)
                self._film_step("引擎就绪，开始出片")
            total = len(proj.get("shots") or [])
            if cloud:
                # 云端自己调度：接帧串行换号、逐镜多号并行；下面那条串行循环只跑本地
                try:
                    self._film_cloud_run(d, proj, fs, t0)
                finally:
                    self._film_pool_close()   # 收调度包装；账号浏览器留着，下次直接用
            for sh in ([] if cloud else proj["shots"]):
                if self._film_should_stop():
                    break
                if prj.ok_file(d, sh):
                    sh["state"] = "done"
                    sh["err"] = ""
                    fr = prj.abs_path(d, sh.get("frame") or "")
                    if not fr or not os.path.isfile(fr):
                        fr = self._film_frame(d, sh) or ""
                    # 续跑时接帧要接在「上一段已经出完的尾帧」上，不能退回工程首帧
                    if chain and fr:
                        last_ref = fr
                    continue
                sh["state"] = "run"
                sh["err"] = ""
                fs["current"] = sh["i"]
                fs["status"] = "第 %d/%d 段 · %s" % (
                    sh["i"], total, "云端出片中" if cloud else "本地出片中")
                if cloud:
                    self.st.setdefault("cloud", {})["status"] = fs["status"]
                else:
                    self.st["status"] = fs["status"]
                fs["elapsed"] = round(time.time() - t0, 1)
                prj.save(d, proj)
                ok = False
                last = ""
                fatal = False
                first = last_ref
                for attempt in range(retry + 1):
                    if self._film_should_stop():
                        break
                    label = "第 %d 段" % sh["i"] + (
                        "" if attempt == 0 else " · 第 %d 次重试" % attempt)
                    self._log("🎬 %s：%d 秒 · %s" % (
                        label, sh["seconds"], "云端" if cloud else "本地"))
                    t1 = time.time()
                    try:
                        path = self._film_one(d, proj, sh, first)
                        if not cloud and self._film_should_stop():
                            # 本地半路停下：这一段的文件可能是残的，丢掉重出，别当已完成
                            try:
                                os.remove(path)
                            except OSError:
                                pass
                            sh["file"] = ""
                            sh["sec"] = 0.0
                            break
                        sh["file"] = prj.rel(d, path)
                        sh["sec"] = round(time.time() - t1, 1)
                        ok = True
                        break
                    except Exception as e:
                        last = str(e)[:300]
                        self._log("⚠️ %s失败：%s" % (label, last))
                        if self._film_should_stop():
                            break
                        # 工作流本身加载不上：同一份图重试多少次都一样，整批停在这里
                        if cloud and any(k in last for k in self.FILM_WF_FATAL):
                            fatal = True
                            break
                        time.sleep(min(8.0, 2.0 * (attempt + 1)))
                if self._film_should_stop():
                    sh["state"] = "wait"
                    break
                if ok:
                    sh["state"] = "done"
                    fail_run = 0
                    self._log("✅ 第 %d 段出完：%s · %.1f 秒"
                              % (sh["i"], os.path.basename(sh["file"]), sh["sec"]))
                    # 每段都抽一张尾帧：时间线上要能看见这一段的画面，
                    # 接帧模式再拿它当下一段的参考；缺 ffmpeg 时抽不出就只少张缩略图
                    fr = self._film_frame(d, sh)
                    if chain:
                        if fr:
                            last_ref = fr
                        else:
                            self._log("⚠️ 第 %d 段抽不出尾帧：下一段沿用上一张参考图"
                                      % sh["i"])
                else:
                    sh["state"] = "fail"
                    sh["err"] = last or "未知错误"
                    fail_run += 1
                    self._log("❌ 第 %d 段跳过（不跳号）：%s" % (sh["i"], sh["err"]))
                    if fatal:
                        fs["state"] = "paused"
                        fs["phase"] = "暂停"
                        fs["msg"] = ("工作流没加载上，已停下：%s。修好工作流后点「继续」，"
                                     "已经出完的段都留着" % sh["err"][:120])
                        fs["status"] = "工作流没加载上，已停下"
                        self._log("⛔ 工作流没加载上：整批停下，不重试")
                        break
                    if fail_run >= 5:
                        fs["state"] = "paused"
                        fs["phase"] = "暂停"
                        fs["msg"] = ("连续 5 段失败，已暂停：先处理登录/额度/环境，"
                                     "再点「继续」")
                        fs["status"] = fs["msg"]
                        self._log("⛔ 连续 5 段失败，整批暂停")
                        break
                fs["done"] = sum(1 for x in proj["shots"] if x.get("state") == "done")
                fs["missing"] = sum(1 for x in proj["shots"]
                                    if x.get("state") in ("fail", "skip"))
                fs["elapsed"] = round(time.time() - t0, 1)
                fs["shots"] = self._film_shots(proj, d)
                if cloud:
                    self.st.setdefault("cloud", {})["status"] = fs["status"]
                else:
                    self.st["status"] = fs["status"]
                prj.save(d, proj)
            if fs["state"] != "paused":
                if self._film_should_stop():
                    fs["state"] = "stopped"
                    fs["phase"] = "已停"
                    fs["done"] = sum(1 for x in proj["shots"]
                                     if x.get("state") == "done")
                    fs["status"] = "已停止 · %d/%d 段" % (fs["done"],
                                                          len(proj["shots"]))
                    self._log("⏹ 成片已停：已出的段都留着，点「继续」从断点接着跑")
                else:
                    done = [x for x in proj["shots"] if x.get("state") == "done"]
                    if not done:
                        fs["state"] = "failed"
                        fs["phase"] = "失败"
                        fs["status"] = "没有一段出成功"
                        fs["msg"] = "每段都失败了：看日志里第一条错误，先处理登录/额度/环境"
                    else:
                        fs["phase"] = "合成"
                        fs["status"] = "合成中…"
                        if cloud:
                            self.st.setdefault("cloud", {})["status"] = fs["status"]
                        else:
                            self.st["status"] = "合成中…"
                        try:
                            film = self._film_merge(d, proj)
                            fs["film"] = film
                            fs["state"] = "done"
                            fs["phase"] = "完成"
                            fs["merge_ok"] = bool(proj.get("merge_ok"))
                            miss = int(proj.get("merge_missing") or 0)
                            fs["status"] = "✅ 成片完成" + (
                                "（缺 %d 段，序号没乱）" % miss if miss else "")
                            self._film_publish(proj, film, round(time.time() - t0, 1))
                            self._log("── 成片结束：%s ──" % film)
                        except Exception as e:
                            fs["state"] = "done"
                            fs["phase"] = "完成"
                            fs["merge_ok"] = False
                            fs["status"] = "分段都出完了 · 没合成"
                            fs["msg"] = "合成失败：%s" % str(e)[:200]
                            self._log("⚠️ 分段都出完，但合成失败：%s" % e)
        except Exception as e:
            fs["state"] = "failed"
            fs["phase"] = "中断"
            fs["err"] = str(e)[:300]
            fs["status"] = "出片中断"
            self._log("❌ 成片中断：%s" % e)
        finally:
            if cloud:
                self._cloud_gen.clear()
            fs["done"] = sum(1 for x in proj["shots"] if x.get("state") == "done")
            fs["missing"] = sum(1 for x in proj["shots"]
                                if x.get("state") in ("fail", "skip"))
            fs["elapsed"] = round(time.time() - t0, 1)
            fs["shots"] = self._film_shots(proj, d)
            if cloud:
                c = self.st.setdefault("cloud", {})
                c["status"] = fs.get("status") or ""
                c["done"] = fs.get("done") or 0
                c["total"] = fs.get("total") or 0
            prj.save(d, proj)
            if cloud:
                self._film_pool_close()     # 成片并行的浏览器收干净，别在桌面留一排窗口
            self._film_cloud = False
            self._release("cloud" if cloud else "gpu")

    def film_plan(self, payload=None):
        f = self._film_cfg(payload)
        story = str(f.get("story") or "").strip()
        if len(story) < 4:
            return {"ok": False, "msg": "先写一段剧情"}
        total = _to_int(f.get("total"), 60, 5, 3600)
        n, shot = self._film_n(total, _to_int(f.get("shot"), 15, 5, 15))
        if total > 40 * shot:
            return {"ok": False, "msg": "最多 40 段（15 秒一段＝10 分钟）："
                                        "把总时长压到 600 秒内，或拆成两集"}
        try:
            r = self._ai().plan_shots(
                story, total, shot, self.cfg,
                style=str(f.get("style") or ""), ratio=self._film_ratio(
                    str(f.get("size") or "")),
                extra=str(f.get("extra") or ""), log=self._log)
        except Exception as e:
            msg = self._ai_err(e)
            self._log("❌ 拆分镜失败：%s" % msg)
            return {"ok": False, "msg": msg}
        return {"ok": True, "title": r["title"], "shots": r["shots"],
                "count": r["count"], "shot_sec": r["shot_sec"],
                "total_sec": r["total_sec"]}

    def film_start(self, payload=None):
        from filmkit import project as prj
        p = dict(payload or {})
        f = self._film_cfg(p)
        rows = p.get("shots") or []
        if len(rows) > 40:
            return {"ok": False, "msg": "最多 40 段：把总时长压到 600 秒内，或拆成两集"}
        total = _to_int(f.get("total"), 60, 5, 3600)
        n, shot = self._film_n(total, _to_int(f.get("shot"), 15, 5, 15))
        if not rows and len(str(f.get("story") or "").strip()) < 4:
            return {"ok": False, "msg": "先写一段剧情，或先点「AI 拆分镜」"}
        if not rows and total > 40 * shot:
            return {"ok": False, "msg": "最多 40 段（15 秒一段＝10 分钟）："
                                        "把总时长压到 600 秒内，或拆成两集"}
        lane = "cloud" if str(f.get("exec") or "local") == "cloud" else "gpu"
        if not self._claim("film", lane):
            return {"ok": False, "msg": self._busy_msg(lane)}
        self._film_stop.clear()
        try:
            title = str(f.get("title") or p.get("title") or "").strip()
            if not rows:
                self.st["film"] = {"state": "planning", "phase": "拆镜", "status": "拆分镜中…",
                                   "id": "", "title": title, "dir": "", "total": n,
                                   "done": 0, "current": 0, "elapsed": 0, "film": "",
                                   "err": "", "shots": [], "missing": 0, "merge_ok": True,
                                   "msg": "", "exec": str(f.get("exec") or ""), "mode": ""}
                plan = self.film_plan(f)
                if not plan.get("ok"):
                    raise FilmError(plan.get("msg") or "拆分镜失败")
                rows = plan["shots"]
                title = title or plan.get("title") or ""
                shot = int(plan.get("shot_sec") or shot)
            shots = prj.norm_shots(rows, shot)
            if not shots:
                raise FilmError("分镜是空的：先点「AI 拆分镜」或写一段剧情")
            chk = self._film_precheck(f, len(shots))
            if chk["err"]:
                raise FilmError(chk["err"])
            d, proj = self._film_new(f, shots, title, chk)
        except Exception as e:
            self._release(lane)
            msg = str(e) if isinstance(e, FilmError) else self._ai_err(e)
            self.st["film"] = dict(self.st.get("film") or {}, state="idle", phase="",
                                   status="", msg=msg)
            self._log("❌ 成片没起来：%s" % msg)
            return {"ok": False, "msg": msg}
        self._film = proj
        self._film_dir = d
        self.st["film"] = self._film_view(proj, state="running", phase="出片",
                                          status="准备中…")
        self._log("🎬 成片开跑：%s · %d 段 × %d 秒 · %s"
                  % (proj["title"], len(shots), shot,
                     "云端" if chk["exec"] == "cloud" else "本地"))
        self._thread = threading.Thread(target=self._film_run, args=(d, proj), daemon=True)
        self._thread.start()
        lo = len(shots) * (6 if chk["exec"] == "cloud" else 4)
        hi = len(shots) * (10 if chk["exec"] == "cloud" else 10)
        return {"ok": True, "id": proj["id"], "title": proj["title"],
                "shots": len(shots), "shot_sec": shot,
                "exec": chk["exec"], "estimate": "%d~%d 分钟" % (lo, hi)}

    def film_stop(self):
        gpu = self._lanes.get("gpu") == "film"
        cloud = self._lanes.get("cloud") == "film"
        if not (gpu or cloud):
            return {"ok": False, "msg": "成片没在跑"}
        self._film_stop.set()
        if gpu:
            self._stop.set()
        if cloud:
            self._stop_cloud.set()
            c = self.st.setdefault("cloud", {})
            c["status"] = "正在停：这一段收尾后结束"
        f = self.st.get("film") or {}
        f["status"] = "正在停：这一段收尾后结束，已出的段都留着"
        self._log("⏹ 收到停止：当前这一段收尾后结束；云端那一段可能还在平台上跑")
        return {"ok": True}

    def film_state(self):
        return {"ok": True, "film": self._snap().get("film"),
                "ffmpeg": self._ff(), "ai_key": self._ai_has()}

    def film_list(self):
        from filmkit import project as prj
        base = os.path.join(_abs_path(self.cfg["console"]["output_dir"]), "films")
        items = []
        if os.path.isdir(base):
            for name in os.listdir(base):
                d = os.path.join(base, name)
                try:
                    proj = prj.load(d)
                except Exception:
                    continue
                shots = proj.get("shots") or []
                items.append({
                    "id": str(proj.get("id") or name),
                    "title": str(proj.get("title") or ""),
                    "dir": d,
                    "time": str(proj.get("updated") or proj.get("created") or ""),
                    "done": sum(1 for x in shots if x.get("state") == "done"),
                    "total": len(shots),
                    "film": str(proj.get("film") or ""),
                    # 「当前」与「正在跑」是两件事：跑完的当前工程仍要能点继续/重出
                    "current": d == (self._film_dir or ""),
                    "running": (d == (self._film_dir or "")
                                and (self._lanes.get("gpu") in ("film", "film_merge")
                                     or self._lanes.get("cloud") == "film")),
                })
        items.sort(key=lambda x: x["time"], reverse=True)
        return {"ok": True, "items": items[:20]}

    def film_resume(self, dir=""):
        from filmkit import project as prj
        d = str(dir or "").strip() or self._film_dir
        if not d:
            d = prj.latest(_abs_path(self.cfg["console"]["output_dir"]))
        if not d or not os.path.isfile(os.path.join(d, "project.json")):
            return {"ok": False, "msg": "还没有可续跑的工程"}
        try:
            proj = prj.load(d)
        except Exception as e:
            return {"ok": False, "msg": "工程读不出来：%s" % e}
        if not (proj.get("shots") or []):
            return {"ok": False, "msg": "这份工程没有分镜"}
        for sh in proj["shots"]:
            if sh.get("state") in ("run", "fail"):
                sh["state"] = "wait"
                sh["err"] = ""
                sh["acct_name"] = ""    # 上一次用的号不带到这一轮
            if sh.get("state") == "done" and not prj.ok_file(d, sh):
                sh["state"] = "wait"
                sh["file"] = ""
                sh["frame"] = ""
                sh["acct_name"] = ""
        all_done = all(prj.ok_file(d, sh) for sh in proj["shots"])
        film = str(proj.get("film") or "")
        if all_done and film and os.path.isfile(film):
            self._film = proj
            self._film_dir = d
            self.st["film"] = self._film_view(proj, state="done", phase="完成",
                                              status="✅ 已完成")
            return {"ok": True, "msg": "这部已经完成了", "film": film}
        chk = self._film_precheck(proj, len(proj["shots"]), base_dir=d)
        if chk["err"]:
            return {"ok": False, "msg": chk["err"]}
        # 先占位、写好 view 再起线程：_film_run 第一句就读 st.film，
        # 反过来写的话线程可能先拿到旧的 idle 视图，之后又被这里覆盖，界面就不动了
        lane = "cloud" if str(proj.get("exec") or "local") == "cloud" else "gpu"
        if not self._claim("film", lane):
            return {"ok": False, "msg": self._busy_msg(lane)}
        self._film_stop.clear()
        self._film = proj
        self._film_dir = d
        self.st["film"] = self._film_view(proj, state="running", phase="出片",
                                          status="准备中…")
        self._thread = threading.Thread(target=self._film_run, args=(d, proj), daemon=True)
        self._thread.start()
        self._log("▶️ 继续成片：%s · 从第一段没出的往后跑" % (proj.get("title") or d))
        return {"ok": True, "exec": proj.get("exec") or "local"}

    def film_redo(self, shot=1, deep=False):
        """重出某一段。接帧模式下自动连带作废后面所有段：第 N+1 段的参考
        是第 N 段的尾帧，只重出第 N 段的话，后半部还是旧画面接出来的。

        作废=删掉那几段的 mp4 与尾帧、状态回到等待，再按续跑那条路跑——
        已完成的段照旧跳过，失败段原位重试，不跳号。
        """
        from filmkit import project as prj
        if (self._lanes.get("gpu") in ("film", "film_merge")
                or self._lanes.get("cloud") == "film"):
            return {"ok": False, "msg": "成片在跑：先点停止再重出"}
        d = self._film_dir or ""
        if not d or not os.path.isfile(os.path.join(d, "project.json")):
            return {"ok": False, "msg": "没有工程：先跑一部，或从「最近工程」打开一份"}
        try:
            proj = prj.load(d)          # 以盘上为准：界面里那份可能是几轮前的快照
        except Exception as e:
            return {"ok": False, "msg": "工程读不出来：%s" % e}
        shots = proj.get("shots") or []
        if not shots:
            return {"ok": False, "msg": "这份工程没有分镜"}
        i = _to_int(shot, 1, 1, len(shots))
        deep = bool(deep or str(proj.get("mode")) == "chain")
        n = 0
        for sh in shots:
            if sh.get("i") != i and not (deep and int(sh.get("i") or 0) > i):
                continue
            for key in ("file", "frame"):
                p = prj.abs_path(d, sh.get(key) or "")
                if p and os.path.isfile(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
                sh[key] = ""
            sh["state"] = "wait"
            sh["sec"] = 0.0
            sh["err"] = ""
            n += 1
        # 旧成片已经拼过被作废的段：指回它只会让人以为「改完了」
        proj["film"] = ""
        proj["merge_ok"] = True
        proj["merge_missing"] = 0
        prj.save(d, proj)
        self._log("↻ 重出第 %d 段%s：作废 %d 段"
                  % (i, "（接帧，含后面所有段）" if deep else "", n))
        r = self.film_resume(d)
        if not r.get("ok"):
            return r
        return {"ok": True, "msg": "从第 %d 段重出，作废 %d 段" % (i, n), "count": n,
                "exec": r.get("exec") or "local"}

    def film_merge(self, dir=""):
        from filmkit import project as prj
        d = str(dir or "").strip() or self._film_dir
        if not d:
            d = prj.latest(_abs_path(self.cfg["console"]["output_dir"]))
        if not d or not os.path.isfile(os.path.join(d, "project.json")):
            return {"ok": False, "msg": "还没有可合成的工程"}
        try:
            proj = prj.load(d)
        except Exception as e:
            return {"ok": False, "msg": "工程读不出来：%s" % e}
        if not any(s.get("state") == "done" and prj.ok_file(d, s)
                   for s in (proj.get("shots") or [])):
            return {"ok": False, "msg": "还没有一段成功出片"}
        if not self._ff():
            return {"ok": False, "msg": "缺 FFmpeg：到「环境管理 → 基础」补上后再合成"}
        self._film = proj
        self._film_dir = d
        if not self._launch("film_merge", lambda: self._film_merge_job(d, proj)):
            return {"ok": False, "msg": self._busy_msg()}
        self.st["film"] = self._film_view(proj, state="running", phase="合成",
                                          status="合成中…")
        return {"ok": True}

    def _film_merge_job(self, d, proj):
        t0 = time.time()
        try:
            self.st["status"] = "合成中…"
            path = self._film_merge(d, proj)
            self._film_publish(proj, path, round(time.time() - t0, 1))
            self.st["film"] = self._film_view(proj, state="done", phase="完成",
                                              status="✅ 成片完成", film=path,
                                              merge_ok=bool(proj.get("merge_ok")))
            self.st["status"] = "✅ 成片完成"
            self._log("── 成片结束：%s ──" % path)
        except Exception as e:
            self.st["film"] = self._film_view(proj, state="done", phase="完成",
                                              status="没合成",
                                              msg="合成失败：%s" % str(e)[:200])
            self.st["status"] = "合成失败"
            self._log("❌ 合成失败：%s" % e)
        finally:
            self._release()

    # ------------------------------------------------------------ js_api：云端账号
    # 一个号一只调试浏览器：1 号用主窗口，2 号起各用独立端口/profile，互不顶号。
    # 浏览器只在登录/检查/保活/出片时起；启动路径不 import DrissionPage（与不 import torch 同理）。
    def _cloudkit(self):
        # pywebview 每个 js_api 调用各起一个线程：冷启动时两个云端入口撞在一起，
        # 没锁就会各建一套 store/host/keep，最后赋值盖掉，留下一条没人管的保活线程和一个浏览器
        with self._cloud_lock:
            if self._cloudx is None:
                from cloudkit import browser as cb
                from cloudkit import pool as cp
                from cloudkit import store as cs
                cfg = self.cfg.setdefault("cloud", {})
                store = cs.AccountStore(ROOT)
                host = cb.BrowserHost(ROOT, cfg, log=self._log)
                # 1 号用主窗口，2 号起各用一只独立浏览器；登录、检查、出片都找自己那只
                browsers = cp.AccountBrowsers(ROOT, cfg, store, host, log=self._log)
                keep = cb.KeepAlive(host, store, cfg, log=self._log,
                                    busy=lambda: bool(self.st.get("cloud_busy"))
                                    or self._cloud_gen.is_set(),
                                    host_for=browsers.host_for)
                self._cloudx = {"store": store, "host": host,
                                "browsers": browsers, "keep": keep}
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

    def _film_pool(self):
        """成片并行时每个号用它自己那只常驻浏览器；只读档案，不提前起窗口。"""
        with self._cloud_lock:
            if self._filmpool is None:
                from cloudkit import pool as cp
                h = self._cloudkit()
                self._filmpool = cp.CloudPool(h["browsers"], log=self._log)
            return self._filmpool

    def _film_pool_close(self):
        with self._cloud_lock:
            p, self._filmpool = self._filmpool, None
        if p is not None:
            try:
                p.close()
            except Exception as e:
                self._log("⚠️ 关闭成片浏览器池失败：%s" % e)

    def _cloud_h3_for(self, aid=""):
        """这条活该进哪只浏览器：1 号用主窗口的执行器，2 号起用它自己那只。"""
        h = self._cloudkit()
        if h["browsers"].slot(aid) <= 1:
            return self._cloud_h3()
        row = h["store"].get(aid)
        if not row:
            return self._cloud_h3()
        return self._film_pool().worker(row).gen

    def cloud_brief(self):
        """视频页那格「云端」要用的一句话实话：有没有号、有没有 DrissionPage、用的哪份工作流。

        只读档案，不起浏览器、不碰保活——在视频页看一眼通道不该顺手开出一个窗口。
        """
        c = self.cfg.setdefault("cloud", {})
        out = {"dp": self._dp_ready(), "accts": [], "wf": str(c.get("workflow") or ""),
               "busy": bool(self._cloud_gen.is_set()), "failed": 0}
        try:
            from cloudkit import store as cs
            st = cs.AccountStore(ROOT)
            for a in st.list():
                snap = st.load(a["id"]) or {}
                if not snap.get("cookies"):
                    continue
                # 出片失败被标 fail 的号不出现在选择器里，等人重新登录/换号
                if str(a.get("state") or "") == "fail":
                    out["failed"] += 1
                    continue
                out["accts"].append({"id": a["id"], "name": a["name"]})
        except Exception:
            pass
        out["ready"] = bool(out["dp"] and out["accts"])
        return out

    def cloud_check_wf(self, path=""):
        """选完工作流先验结构：不拉浏览器、不占任务位，选完几秒内就能知道行不行。

        本地文件当场给结论；平台地址只能等开页再验，这里不假装知道。
        """
        s = str(path or (self.cfg.get("cloud") or {}).get("workflow") or "").strip()
        if not s:
            return {"ok": False, "msg": "还没填工作流"}
        if not re.search(r"\.json$|\.txt$", s, re.I):
            return {"ok": True, "kind": "remote", "msg": "平台工作流：开跑时进页面再验"}
        p = os.path.normpath(s if os.path.isabs(s) else os.path.join(ROOT, s))
        try:
            from cloudkit.gen import check_workflow_json
            meta = check_workflow_json(p)
        except Exception as e:
            return {"ok": False, "kind": "file", "msg": str(e)}
        return {"ok": True, "kind": "file", "nodes": meta["nodes"], "links": meta["links"],
                "msg": "结构没问题：%d 个节点 · 主节点/输出节点都在" % meta["nodes"]}

    def cloud_state(self):
        """给界面的账号表 + 每只浏览器的状态。不含任何凭据。"""
        c = self.cfg.get("cloud") or {}
        base_port = int(c.get("port") or 9333)
        if self._cloudx is None and not self._dp_ready():
            # 缺浏览器依赖也把档案列出来：名字和备份是本地数据，不该跟着一起消失
            try:
                from cloudkit import store as cs
                accounts = cs.AccountStore(ROOT).list()
            except Exception:
                accounts = []
            for i, a in enumerate(accounts, 1):
                a["slot"] = i
                a["browser_port"] = base_port + i - 1
            return {"ok": True, "dp": False, "accounts": accounts,
                    "browsers": [{"slot": a["slot"], "port": a["browser_port"],
                                  "on": False, "account": str(a.get("name") or ""),
                                  "account_id": str(a.get("id") or ""),
                                  "purpose": "", "main": a["slot"] == 1}
                                 for a in accounts],
                    "browser": {"on": False, "port": base_port,
                                "base": str(c.get("base") or ""), "account": ""},
                    "busy": self.st.get("cloud_busy", ""),
                    "msg": "缺 DrissionPage：到「环境管理 → 基础」补齐后重开这页",
                    "keep": {"on": bool(c.get("keep", True)),
                             "min": int(c.get("keep_min") or 30),
                             "last": 0, "msg": "还没跑过"},
                    "concurrency": 1, "parallel": 0, "page": str(c.get("base") or "")}
        h = self._cloudkit()
        keep = h["keep"]
        accounts = h["store"].list()
        browsers = h["browsers"].state()
        # 账号行上直接看得到「这个号用第几只浏览器 / 哪个端口」
        by_id = {b["account_id"]: b for b in browsers}
        for a in accounts:
            b = by_id.get(str(a.get("id") or "")) or {}
            a["slot"] = int(b.get("slot") or 0)
            a["browser_port"] = int(b.get("port") or 0)
        try:
            from cloudkit.pool import MAX_PARALLEL
            healthy = sum(1 for a in accounts
                          if str(a.get("state") or "") != "fail"
                          and (h["store"].load(a["id"]) or {}).get("cookies"))
            parallel = min(MAX_PARALLEL, healthy)
        except Exception:
            parallel = 1
        running = [b for b in browsers if b["on"]]
        return {
            "ok": True, "dp": True,
            "accounts": accounts,
            "browsers": browsers,
            # 老字段：主窗口那只是为了兼容「打开平台/关闭全部」那组按钮的读数
            "browser": {"on": h["host"].alive(wait=False), "port": h["host"].port,
                        "base": h["host"].base, "account": h["host"].current,
                        "open": len(running)},
            "busy": self.st.get("cloud_busy", ""),
            "msg": self.st.get("cloud_msg", ""),
            "keep": {"on": bool((self.cfg.get("cloud") or {}).get("keep", True)),
                     "min": int((self.cfg.get("cloud") or {}).get("keep_min") or 30),
                     "last": int(keep.last), "msg": keep.last_msg,
                     # 这只窗口现在被谁占着：''=空闲（保活能跑）/ login / gen / hold
                     "purpose": str(h["host"].purpose or "")},
            "concurrency": 1,
            # 成片逐镜时最多几个号同时跑（每个号一只独立浏览器，主窗口仍是 1）
            "parallel": parallel, "page": h["host"].base,
        }

    def _cloud_run(self, label, fn, aid=""):
        """浏览器操作一律进后台：pywebview 在 UI 线程派发 js_api，
        起浏览器/加载页面动辄几秒，同步等会把消息泵饿死（界面先卡住）。

        aid 是这次要动的号：只拦「它自己那只浏览器正在出片」，
        别的号在跑不该把登录/检查/保存全堵死。
        """
        if aid:
            try:
                if self._cloudkit()["browsers"].host_for(aid).purpose == "gen":
                    return False, "这个号正在出片：等这一段跑完再动它"
            except Exception:
                pass
        elif self._cloud_gen.is_set():
            return False, "云端出片正占用浏览器：先等这一段跑完"
        with self._cloud_lock:
            if self.st.get("cloud_busy"):
                return False, "云端账号正忙：%s" % self.st["cloud_busy"]
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
                self._log("❌ 云端账号：%s" % msg)
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
            return {"ok": False, "msg": "缺 DrissionPage：到「环境管理 → 基础」补齐后重开这页",
                    "state": self.cloud_state()}
        h = self._cloudkit()
        row = h["store"].create(name)
        aid = row["id"]
        h["store"].mark(aid, "pending", "等待登录")
        # 新建档案要一块干净的登录页：这只浏览器里可能还留着上一个号的 cookie，
        # 不清掉的话「新建登录」会直接看到旧号——保存下来就是重复的一份
        ok, msg = self._cloud_run(
            "打开登录页", lambda: h["browsers"].host_for(aid).open_login({}, aid=aid),
            aid=aid)
        if ok:
            self._log("☁️ 新建登录：%s（浏览器 %d · 登录后点「保存」）"
                      % (row["name"], h["browsers"].slot(aid)))
        return {"ok": ok, "msg": msg, "account": row, "state": self.cloud_state()}

    def cloud_login(self, aid=""):
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}
        state = h["store"].load(aid)
        h["store"].mark(aid, "pending", "等待登录")

        def job():
            h["browsers"].host_for(aid).open_login(state, aid=aid)
            self.st["cloud_msg"] = "登录完点「保存」；以后换号不用再登"
        ok, msg = self._cloud_run("打开登录页", job, aid=aid)
        return {"ok": ok, "msg": msg}

    def cloud_save(self, aid="", name=""):
        """把浏览器里当前的登录态存成这个账号的一份新快照（旧快照保留为备份）。"""
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}

        def job():
            from cloudkit.browser import login_state
            host = h["browsers"].host_for(aid)
            # 整段一次取锁：读快照和判登录态必须是同一个号的同一次状态，
            # 分两次取锁的话中间正好能插进一次保活换号
            with host.lock:
                snap = host.snapshot()
                if not snap.get("cookies"):
                    raise RuntimeError("没读到登录态：先在浏览器里登录，再点保存")
                ts = h["store"].save(aid, snap["cookies"], snap["storage"], snap["url"])
                st, detail = login_state(host.tab())
                h["store"].mark(aid, st, detail)
                host.purpose = ""       # 登录流程收尾，保活可以接着轮换
            if name:
                h["store"].rename(aid, name)
            n = len(h["store"].backups(aid))
            self.st["cloud_msg"] = "已保存 %s · 共 %d 份备份" % (row["name"], n)
            self._log("☁️ 登录态已保存：%s（%d 份）" % (row["name"], n))
            return ts
        ok, msg = self._cloud_run("保存登录态", job, aid=aid)
        return {"ok": ok, "msg": msg}

    def cloud_apply(self, aid=""):
        """用这个账号打开平台：换 cookie 后刷一次页面，人眼看得到是谁的号。"""
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}
        state = h["store"].load(aid)
        if not state or not state.get("cookies"):
            return {"ok": False, "msg": "这个号还没保存登录态"}
        host = h["browsers"].host_for(aid)
        ok, msg = self._cloud_run("切换账号",
                                  lambda: host.open_base(state, aid=aid, hold=True),
                                  aid=aid)
        if ok:
            self._log("☁️ 切换到账号：%s（浏览器 %d）"
                      % (row["name"], h["browsers"].slot(aid)))
        return {"ok": ok, "msg": msg}

    def cloud_check(self, aid=""):
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}

        def job():
            from cloudkit.browser import cookie_fp, login_state, snapshot_state
            host = h["browsers"].host_for(aid)
            state = h["store"].load(aid)
            with host.lock:
                # hold=True：这一段里保活不许插进来换号，否则检查的是别人的会话、
                # 结论却记在这个号头上
                host.open_base(state, aid=aid, hold=True)
                tab = host.tab()
                st, detail = login_state(tab)
                snap = snapshot_state(tab, host.domains)
                host.purpose = ""
            # 没变就不写：反复点「检查」不该把 12 份备份挤成同一分钟的 12 份
            if snap.get("cookies") and cookie_fp(snap["cookies"]) != cookie_fp((state or {}).get("cookies")):
                h["store"].save(aid, snap["cookies"], snap["storage"], snap["url"])
            h["store"].mark(aid, st, detail)
            self.st["cloud_msg"] = "%s：%s" % (row["name"], detail)
        ok, msg = self._cloud_run("检查登录", job, aid=aid)
        return {"ok": ok, "msg": msg}

    def cloud_delete(self, aid=""):
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在"}
        if self._cloud_gen.is_set():
            # 删号会让后面的号位往前挪，正在跑的那只窗口会被当成「号位变了」收掉
            return {"ok": False, "msg": "云端在出片：出完再删，免得号位一挪把正在跑的窗口换掉"}
        if h["browsers"].slot(aid) <= 1:
            if h["host"].current == aid:
                h["host"].current = ""
        else:
            h["browsers"].close(aid)     # 这个号的独立窗口跟着一起收，别留个空壳
        h["store"].delete(aid)
        h["browsers"].reconcile()        # 后面的号顺延：原号位的窗口收掉，改走新号位
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
            h["browsers"].host_for(aid).open_base(state, aid=aid)
            self.st["cloud_msg"] = "%s 已恢复到 %s" % (row["name"], ts)
        ok, msg = self._cloud_run("恢复备份", job, aid=aid)
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
            return {"ok": False, "msg": "缺 DrissionPage：到「环境管理 → 基础」补齐后重开这页"}
        h = self._cloudkit()
        if not any(b["on"] for b in h["browsers"].state()):
            return {"ok": False, "msg": "浏览器还没开：先点「打开全部」"}
        ok, msg = self._cloud_run("保活", lambda: h["keep"].sweep(force=True))
        return {"ok": ok, "msg": msg}

    def cloud_browser_start(self):
        if not self._dp_ready():
            return {"ok": False, "msg": "缺 DrissionPage：到「环境管理 → 基础」补齐后重开这页"}
        h = self._cloudkit()

        def job():
            opened = []
            for a in h["store"].list():
                state = h["store"].load(a["id"])
                if not state or not state.get("cookies"):
                    continue
                # 每个号回自己那只窗口：2 号开的是第二只浏览器，不去顶别人的号
                host = h["browsers"].host_for(a["id"])
                host.open_base(state, aid=a["id"])
                opened.append("浏览器 %d（%d）" % (h["browsers"].slot(a["id"]), host.port))
            if not opened:
                # 一个号都没登录过：先开主窗口停在平台首页，登录入口还留着
                h["host"].open_base({})
                opened.append("浏览器 1（%d）" % h["host"].port)
            self.st["cloud_msg"] = "已打开：" + "、".join(opened)
        ok, msg = self._cloud_run("启动浏览器", job)
        return {"ok": ok, "msg": msg}

    def cloud_browser_stop(self):
        h = self._cloudkit()

        def job():
            h["browsers"].close_all()
            self.st["cloud_msg"] = "浏览器已全部关闭"
        ok, msg = self._cloud_run("关闭浏览器", job)
        return {"ok": ok, "msg": msg}

    def cloud_auth_names(self, aid=""):
        """登录态里取得到的 Rh-* 鉴权头名字（只报名字，不报值）。"""
        h, row = self._cloud_acct(aid)
        if not row:
            return {"ok": False, "msg": "账号不存在", "names": []}
        return {"ok": True,
                "names": sorted(h["browsers"].host_for(aid).headers(h["store"].load(aid)))}

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
        tools = {e["id"] for e in self._spec().get("envs") or [] if e.get("tool")}
        is_on = lambda eid: eid in tools or on.get(eid, True)
        r["items"] = [it for it in r["items"] if is_on(str(it.get("env") or "base"))]
        # 开着的环境不再享受「可选＝默认别提醒」的待遇：开关就是本人的选择。
        # 工具环境例外：它没有开关，miss 也只算「可选扩展没装」，不进待补总数。
        for it in r["items"]:
            it["optional"] = str(it.get("env") or "base") in tools
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
        return {"ok": True, "env_on": self._env_on(), "cfg": self._cfg_public()}

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
            tools = {e["id"] for e in self._spec().get("envs") or [] if e.get("tool")}
            items = [it for it in ec.check(ROOT, spec=self._spec())["items"]
                     if str(it.get("env") or "base") in tools
                     or on.get(str(it.get("env") or "base"), True)]
            for it in items:
                # 同 env_check：开着就不算「可选」；工具环境保留可选（默认不整批补）
                it["optional"] = str(it.get("env") or "base") in tools
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
                elif kind == "tool":
                    ok = self._env_tool_install(it["fix"])
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

    def _env_tool_install(self, fix):
        """可选工具（ffmpeg）：下载静态包→只解出可执行文件→跑一次 -version 自检。"""
        from envkit import install as ei

        def prog(ev):
            self.st["dl"] = dict(ev or {})

        self.st["dl"] = {"busy": True, "phase": "tool", "file": "", "done": 0,
                         "total": 0, "speed": 0, "eta": 0,
                         "files_done": 0, "files_total": 1}
        try:
            ok = ei.install_tool(ROOT, fix, self._log,
                                 on_line=self._log, on_progress=prog)
        except Exception as e:
            self._log("❌ 工具安装出错：%s" % e)
            ok = False
        finally:
            self.st["dl"] = {}
        return ok

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
