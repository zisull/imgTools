# -*- coding: utf-8 -*-
"""
api_server.py —— FastAPI 对外 REST（M4）
=========================================
端点（除 /v1/health 外全部鉴权；设置页开了「免令牌」则本机访问不校验）：
  GET  /v1/health                状态：引擎/档位/模型/运行/显存/排队数
  GET  /v1/models                清单：引擎/尺寸档/质量档/默认值（给调用方自查）
  POST /v1/images/generations    JSON {prompt,size,steps,seed,n,mode,negative}；
                                 engine 或 model 选引擎（"moss"/"qwen"，不传按设置页
                                 默认引擎，再回落控制台当前引擎）；
                                 带 engine:"moss" 即走 Moss（内嵌 ComfyUI），
                                 质量 quality:"fast|mid|full" = 8/25/50 步；
                                 response_format:"b64_json"（或 sync:true）= 同步等图，
                                 直接回 OpenAI 形状 {created,data:[{b64_json}]}
                                 （TAIlive 等同步客户端就吃这一路）
  GET  /v1/moss                  Moss 引擎状态（档位/是否拉起/是否就绪）
  POST /v1/images/edits          multipart：image≤10 + prompt + res
  GET  /v1/tasks/{id}            异步任务状态（queued/running/done/failed）
  GET  /v1/images/{id}           取结果 PNG

同一时间只有一个生图引擎常驻显存：API 任务与界面任务共用同一把全局互斥锁（App._claim），
engine:"moss" 的任务会复用 App._do_moss_gen——首次自动拉起 ComfyUI，进度/日志/画廊计数
与界面发起的任务同一条流，界面上看得见；让出显存档（tier=yield）时子进程是停的，
来任务会自动重新拉起（唤醒式，平时不占显存）。

任务单线程序执行（Turbo 一张 20~30s，UI 互斥）：worker 先向 App 抢到任务位、再复用
App._do_gen —— 进度、日志、画廊计数与 UI 发起的任务同一条流，界面上看得见。
uvicorn 跑后台线程，Server.should_exit 可停，改端口/局域网开关即重启监听。

长跑上限：参考图单张 ≤25MB、单次合计 ≤100MB（分块落盘，在流上就拦住）；排队最多
MAX_QUEUED 个，再投回 429；任务单只留最近 MAX_JOBS 张或 JOB_TTL 小时，淘汰时连带删掉
它留下的 api_refs 参考图目录——接口是给人整天调的，不封顶就是无限吃内存和磁盘。
"""
import base64
import os
import queue
import re
import shutil
import threading
import time
import uuid
from collections import OrderedDict
from typing import List

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

# 界面上的 P 档也放进清单：P=短边，横/方/竖 = 16:9 / 1:1 / 9:16；
# 宽高贴 16 的倍数，和 App 的折算规则同一条。老尺寸继续保留，调用方不用改。
_P_IMG = (480, 512, 720, 768, 1024)
_P_ASPECT = ((16, 9), (1, 1), (9, 16))


def _p_size(p, aw, ah):
    long = max(64, min(4096, int(p * max(aw, ah) / float(min(aw, ah)) / 16 + 0.5) * 16))
    return "%dx%d" % ((long, p) if aw >= ah else (p, long))


_P_SIZES = {_p_size(p, aw, ah) for p in _P_IMG for aw, ah in _P_ASPECT}
GEN_SIZES = {"512x512", "768x768", "1024x1024", "576x1024",
             "1024x1536", "1536x1024", "1536x1536"} | _P_SIZES
EDIT_RES = {"512", "768"}
IMG_SUFFIX = (".png", ".jpg", ".jpeg", ".webp")
# Moss（内嵌 ComfyUI）：尺寸须是 16 的倍数（非倍数会自动就近对齐）；12G 卡稳的是 1MP 级，2M 级会触发 offload 变慢
MOSS_SIZES = {"512x512", "768x768", "1024x1024", "832x1216",
              "1216x832", "1024x1536", "1536x1024"} | _P_SIZES
# 与 app.MOSS_TIERS 同键（那张表是权威：模板/步数/CFG 都在那边定）；
# 这里只拿来给 API 明确回 400，而不是像界面那样静默回落成极速档。
MOSS_QUALITY = {"fast": "8 步极速", "mid": "25 步均衡", "full": "50 步精修"}

# 对外服务要能整天开着：参考图和任务单都得有上限，否则刷几次大文件就是无限吃内存/磁盘。
MAX_FILE_BYTES = 25 * 1024 * 1024      # 单张参考图 25MB：手机原图也够，再大只会拖慢出图
MAX_TOTAL_BYTES = 100 * 1024 * 1024    # 一次请求合计 100MB（10 张的上限已经先卡住）
CHUNK = 1024 * 1024
MAX_JOBS = 200                         # 任务单只留最近这么多张，老的连结果图引用一起丢
JOB_TTL = 24 * 3600                    # 超过一天没人取的成品也没意义了
MAX_QUEUED = 50                        # 排队上限：出图单线程，超了就当场回 429
SYNC_WAIT = 280                        # 同步 b64 模式的等待上限（TAIlive 那侧 SD 超时是 300s）
SIZE_RE = re.compile(r"^(\d+)x(\d+)$")


class _TooBig(Exception):
    pass


async def _drain_upload(src, dst_path, file_cap, budget_left, label):
    """把一张参考图分块写进磁盘，边写边量，超限抛 _TooBig；返回写入字节数。

    上限必须在「流」上生效：先 await read() 整个文件再判长度，等于先把对方塞来的
    2GB 收进本机内存才说不——这台机器还要留内存给显存里的模型。
    """
    n = 0
    with open(dst_path, "wb") as fh:
        while True:
            buf = await src.read(CHUNK)
            if not buf:
                break
            n += len(buf)
            if n > file_cap:
                raise _TooBig("%s超过单张上限 %d MB" % (label, file_cap // 1024 // 1024))
            if n > budget_left:
                raise _TooBig("%s让本次上传超过了合计上限 %d MB"
                              % (label, MAX_TOTAL_BYTES // 1024 // 1024))
            fh.write(buf)
    return n


class ApiServer:
    def __init__(self, console):
        self.c = console
        self.jobs = OrderedDict()       # task_id -> job dict（按提交顺序，淘汰从最老那头）
        self.files = OrderedDict()      # image_id -> 绝对路径
        self._q = queue.Queue()
        self._stop = threading.Event()
        self._mut = threading.Lock()    # jobs/files 的增删：多个请求线程会同时进来
        self._server = None
        self._thread = None
        self.api = self._build()
        threading.Thread(target=self._worker, daemon=True).start()

    # ------------------------------------------------------------ 鉴权/工具
    def _check(self, request):
        a = self.c.cfg.get("api") or {}
        if a.get("no_token"):
            return                      # 免令牌模式（设置页开关，仅建议本机调试用）
        tok = str(a.get("token") or "")
        if not tok:
            raise HTTPException(503, "令牌还没生成：先在控制台 API 页开启服务")
        hdr = request.headers.get("authorization") or ""
        if hdr != "Bearer " + tok:
            raise HTTPException(401, "令牌不对：Authorization: Bearer <token>")

    def _api_cfg(self):
        return self.c.cfg.get("api") or {}

    def _resolve_engine(self, body):
        """生图引擎谁说了算：请求里的 engine/model 最优先，其次设置页的默认引擎，
        都没有就跟随控制台当前激活的引擎。model 是 OpenAI 风格的别名（TAIlive 会传）。"""
        want = str(body.get("engine") or body.get("model") or "").lower()
        if want:
            return "moss" if "moss" in want else "qwen"
        d = str(self._api_cfg().get("def_engine") or "follow")
        if d in ("qwen", "moss"):
            return d
        return str(self.c.cfg.get("engine") or "qwen")

    @staticmethod
    def _check_size(size, engine):
        """预设档之外放行「WxH」自定义：千问 64~4096，Moss 64~2048。
        （与界面 runner 的折算规则、后端 _do_gen 的解析范围同一条线。）"""
        m = SIZE_RE.match(str(size or "").strip().lower())
        if not m:
            return None
        w, h = int(m.group(1)), int(m.group(2))
        hi = 2048 if engine == "moss" else 4096
        if not (64 <= w <= hi and 64 <= h <= hi):
            return None
        # Moss 的 latent 网格要 16 对齐。同步客户端（TAIlive 那类）会把长边钳成任意值，
        # 这里硬拒等于让它每张图都吃 400——就近取整（下取整，不超显存预算）比报错有用，
        # 与 App._moss_params 用的是同一条折算规则。
        if engine == "moss":
            w = max(64, min(2048, w // 16 * 16))
            h = max(64, min(2048, h // 16 * 16))
        return "%dx%d" % (w, h)

    def _sync_response(self, job):
        """同步 b64 出图：等任务收尾，直接回 OpenAI 形状。
        TAIlive 的 openai 生图是同步 POST + response_format:b64_json，
        异步任务制对不上——极速档 512² 一两秒就出，等得起。"""
        deadline = time.time() + SYNC_WAIT
        while time.time() < deadline:
            if job["status"] not in ("queued", "running"):
                break
            time.sleep(0.3)
        if job["status"] in ("queued", "running"):
            raise HTTPException(504, "出图超时（%d 秒没出结果），任务 %s 还在后台跑，"
                                 "可稍后 GET /v1/tasks/%s 取" % (SYNC_WAIT, job["id"], job["id"]))
        if job["status"] == "failed":
            raise HTTPException(500, job["error"] or "生成失败")
        data = []
        for im in job["images"]:
            p = self.files.get(im["id"])
            if p and os.path.isfile(p):
                with open(p, "rb") as fh:
                    data.append({"b64_json": base64.b64encode(fh.read()).decode("ascii")})
        if not data:
            raise HTTPException(500, "生成失败：没有产出图片")
        return {"created": int(job["created"]), "data": data}

    def _src(self, request):
        return request.client.host if request.client else "?"

    def _submit(self, payload, src):
        # 出图是单线程的（一张 20~60s），排队不设上限就等于让远端把这台机器的内存和
        # 显存排成一条看不见的长队——宁可当场回 429，让调用方知道现在有多忙。
        if self._q.qsize() >= MAX_QUEUED:
            raise HTTPException(429, "排队已满（最多 %d 个任务），先取已完成的任务，稍后再投"
                                 % MAX_QUEUED)
        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "status": "queued", "created": time.time(),
               "src": src, "payload": payload, "images": [], "error": "", "refs": ""}
        with self._mut:
            self.jobs[jid] = job
            dead = self._gc()
        for j in dead:                # 淘汰的要连参考图目录一起删；放锁外，别让磁盘 IO 卡住别的请求线程
            if j.get("refs"):
                shutil.rmtree(j["refs"], ignore_errors=True)
        self._q.put(job)
        return job

    def _gc(self):
        """任务单淘汰：只丢已经收尾的（排队/在跑的不能动），并清掉它们留下的结果图引用。

        对外服务开着就有无限提交的可能：jobs/files 不设上限，内存和 api_refs 目录只涨不落。
        引用只在「淘汰那一张 job」时摘，不反过来扫全表——worker 正在往 images 里追加，
        扫表会 races 掉刚出图、客户端还没取的成品。
        调用方必须持有 self._mut。
        """
        dead, now = [], time.time()
        for jid in list(self.jobs):          # 从最老那头扫
            job = self.jobs[jid]
            if job["status"] in ("queued", "running"):
                break                        # 撞到没收尾的就停：它后面的都是更新的
            if len(self.jobs) > MAX_JOBS or now - job["created"] > JOB_TTL:
                job = self.jobs.pop(jid)
                for im in job["images"]:
                    self.files.pop(im["id"], None)
                dead.append(job)
        return dead

    def _moss_generation(self, request, body, prompt):
        """engine:moss 的出图请求校验 + 入队（复用 worker 的 _do_moss_gen 通道）。"""
        size = self._check_size(body.get("size") or self._api_cfg().get("def_size"),
                                "moss")
        if not size:
            raise HTTPException(400, "Moss 的 size 要给 WxH（64~2048，自动对齐 16 倍数）；"
                                "预设档：%s" % ", ".join(sorted(MOSS_SIZES)))
        quality = str(body.get("quality") or "fast")
        if quality not in MOSS_QUALITY:
            raise HTTPException(400, "quality 只支持 %s" % " / ".join(
                "%s（%s）" % kv for kv in sorted(MOSS_QUALITY.items())))
        try:
            n = max(1, min(4, int(body.get("n") or 1)))
            seed = int(body.get("seed", -1))
        except (TypeError, ValueError):
            raise HTTPException(400, "n/seed 要给整数")
        payload = {"engine": "moss", "mode": "moss", "prompt": prompt, "size": size,
                   "negative": str(body.get("negative") or ""), "quality": quality,
                   "seed": seed, "count": n}
        job = self._submit(payload, self._src(request))
        self.c._log("🌐 API(%s) 提交 Moss 任务 %s：%s · %s · %d 张"
                    % (job["src"], job["id"], size, quality, n))
        if str(body.get("response_format") or "") == "b64_json" or body.get("sync"):
            return self._sync_response(job)
        return {"task_id": job["id"], "status": job["status"], "engine": "moss"}

    @staticmethod
    def _pub(job):
        return {"task_id": job["id"], "status": job["status"],
                "created": time.strftime("%Y-%m-%d %H:%M:%S",
                                         time.localtime(job["created"])),
                "images": job["images"], "error": job["error"]}

    # ------------------------------------------------------------ worker
    def _worker(self):
        while not self._stop.is_set():
            try:
                job = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            # 占位再起跑：查空闲和真正开跑之间若有窗口，UI 任务会插进来同踩一个 pipeline
            claimed = False
            while not self._stop.is_set():
                if self.c._claim("gen"):
                    claimed = True
                    break
                time.sleep(0.8)
            if not claimed:
                job["status"] = "failed"
                job["error"] = "服务已关闭，任务没执行"
                continue
            job["status"] = "running"
            g = dict(job["payload"])
            g["_saved"] = []
            self.c._log("🌐 API 任务 %s 开始（来源 %s）" % (job["id"], job["src"]))
            try:
                eng = str(job["payload"].get("engine") or "")
                if eng == "moss":
                    self.c._do_moss_gen(g)
                else:
                    self.c._do_gen(g)
                for p in g["_saved"]:
                    iid = uuid.uuid4().hex[:12]
                    with self._mut:
                        self.files[iid] = p
                    job["images"].append({"id": iid,
                                          "name": os.path.basename(p),
                                          "url": "/v1/images/" + iid})
                job["status"] = "done" if job["images"] else "failed"
                if not job["images"]:
                    job["error"] = "生成失败（见控制台日志）"
            except Exception as e:
                job["status"] = "failed"
                job["error"] = str(e)
            self.c._log("🌐 API 任务 %s：%s" % (job["id"], job["status"]))

    # ------------------------------------------------------------ 路由
    def _build(self):
        api = FastAPI(title="Qwen-Image Console API", docs_url=None, redoc_url=None)
        me = self

        @api.get("/v1/health")
        def health():
            s = me.c.st
            return {"ok": True, "engine": s.get("engine", "qwen"),
                    "model_loaded": bool(s.get("model_loaded")),
                    "running": s.get("running"), "vram_used": s.get("vram_used"),
                    "vram_total": s.get("vram_total"), "queued": me._q.qsize(),
                    "tier": s.get("moss_tier", "daily"),
                    "comfyui_on": bool(s.get("comfyui_on")),
                    "moss_installed": bool(s.get("moss_installed"))}

        @api.get("/v1/moss")
        def moss_state(request: Request):
            me._check(request)
            return me.c.moss_status()

        @api.post("/v1/images/generations")
        async def generations(request: Request):
            me._check(request)
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "请求体要是一个 JSON 对象")
            prompt = str(body.get("prompt") or "").strip()
            if not prompt:
                raise HTTPException(400, "prompt 不能为空")
            if me._resolve_engine(body) == "moss":
                return me._moss_generation(request, body, prompt)
            size = me._check_size(body.get("size") or me._api_cfg().get("def_size"), "qwen")
            if not size:
                raise HTTPException(400, "size 认预设档或 WxH（64~4096）：%s"
                                    % ", ".join(sorted(GEN_SIZES)))
            mode = str(body.get("mode") or "gen")
            if mode not in ("gen", "rgba"):
                raise HTTPException(400, "mode 只能是 gen 或 rgba")
            try:
                steps = int(body.get("steps") or 8)
                n = max(1, min(4, int(body.get("n") or 1)))
                seed = int(body.get("seed", -1))
            except (TypeError, ValueError):
                raise HTTPException(400, "steps/n/seed 要给数字")
            if steps not in (8, 40):
                raise HTTPException(400, "steps 只支持 8（Turbo）或 40（精细）")
            payload = {"mode": mode, "prompt": prompt, "size": size,
                       "steps": str(steps), "seed": seed, "count": n,
                       "negative": str(body.get("negative") or ""),
                       "kv_cache": True}
            job = me._submit(payload, me._src(request))
            me.c._log("🌐 API(%s) 提交出图任务 %s：%s" % (job["src"], job["id"], size))
            if str(body.get("response_format") or "") == "b64_json" or body.get("sync"):
                return me._sync_response(job)
            return {"task_id": job["id"], "status": job["status"], "engine": "qwen"}

        @api.post("/v1/images/edits")
        async def edits(request: Request, prompt: str = Form(""),
                        res: str = Form("512"),
                        image: List[UploadFile] = File(default=[])):
            me._check(request)
            prompt = str(prompt or "").strip()
            if not prompt:
                raise HTTPException(400, "prompt 不能为空")
            if str(res) not in EDIT_RES:
                raise HTTPException(400, "res 只支持 512 或 768（1024 在 12G 卡会溢出共享内存）")
            files = [f for f in (image or []) if f and f.filename]
            if not files:
                raise HTTPException(400, "至少带一张参考图（multipart 字段名 image）")
            if len(files) > 10:
                raise HTTPException(400, "参考图最多 10 张")
            jid = uuid.uuid4().hex[:12]
            # 相对输出目录要按项目根展开：exe 的 CWD 可能是任意地方，abspath() 会把参考图写到别人目录下
            ref_dir = os.path.join(me.c.abs_path(me.c.cfg["console"]["output_dir"]),
                                   "api_refs", jid)
            paths = []
            total = 0
            try:
                os.makedirs(ref_dir, exist_ok=True)
                for i, f in enumerate(files):
                    ext = os.path.splitext(f.filename)[1].lower()
                    if ext not in IMG_SUFFIX:
                        raise HTTPException(400, "第 %d 张不是图片格式：%s" % (i + 1, ext))
                    p = os.path.join(ref_dir, "%d%s" % (i + 1, ext))
                    n = await _drain_upload(f, p, MAX_FILE_BYTES,
                                            MAX_TOTAL_BYTES - total, "第 %d 张" % (i + 1))
                    total += n
                    if not n:
                        raise HTTPException(400, "第 %d 张是空文件" % (i + 1))
                    paths.append(p)
            except _TooBig as e:
                shutil.rmtree(ref_dir, ignore_errors=True)
                raise HTTPException(413, str(e))
            except Exception:
                shutil.rmtree(ref_dir, ignore_errors=True)   # 校验没过也不能留半堆参考图在盘上
                raise
            payload = {"mode": "edit", "prompt": prompt, "res": str(res),
                       "images": paths, "steps": "8", "seed": -1, "count": 1,
                       "negative": "", "kv_cache": True}
            job = me._submit(payload, me._src(request))
            job["refs"] = ref_dir     # 排队中的任务不会被淘汰，这里补上没竞态；收尾后由 _gc 连带删目录
            me.c._log("🌐 API(%s) 提交编辑任务 %s：%d 张参考图 · %s 画幅"
                      % (job["src"], job["id"], len(paths), res))
            return {"task_id": job["id"], "status": job["status"]}

        @api.get("/v1/models")
        def models(request: Request):
            """调用方能查的清单：引擎怎么选、各引擎认哪些尺寸/档位、默认值是什么。"""
            me._check(request)
            a = me._api_cfg()
            d = str(a.get("def_engine") or "follow")
            return {"ok": True,
                    "engines": ["qwen", "moss"],
                    "default_engine": d if d in ("qwen", "moss")
                                      else str(me.c.cfg.get("engine") or "qwen"),
                    "default_engine_policy": d,
                    "default_size": str(a.get("def_size") or "1024x1024"),
                    "qwen": {"sizes": sorted(GEN_SIZES),
                             "custom_size": "WxH，64~4096", "steps": [8, 40], "modes": ["gen", "rgba"]},
                    "moss": {"sizes": sorted(MOSS_SIZES),
                             "custom_size": "WxH，64~2048（非 16 倍数自动下取整对齐）",
                             "quality": {k: v for k, v in MOSS_QUALITY.items()}},
                    "edit_res": sorted(EDIT_RES)}

        @api.get("/v1/tasks/{tid}")
        def task_status(tid: str, request: Request):
            me._check(request)
            job = me.jobs.get(tid)
            if not job:
                raise HTTPException(404, "没有这个任务 id")
            return me._pub(job)

        @api.get("/v1/images/{iid}")
        def get_image(iid: str, request: Request):
            me._check(request)
            p = me.files.get(iid)
            if not p or not os.path.isfile(p):
                raise HTTPException(404, "图不在了（任务还没出图，或 id 不对）")
            return FileResponse(p, media_type="image/png",
                                filename=os.path.basename(p))

        return api

    # ------------------------------------------------------------ 生命周期
    def start(self, host, port):
        cfg = uvicorn.Config(self.api, host=host, port=int(port), log_level="warning")
        self._server = uvicorn.Server(cfg)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        for _ in range(60):
            if getattr(self._server, "started", False):
                return True
            if not self._thread.is_alive():
                return False
            time.sleep(0.1)
        return bool(getattr(self._server, "started", False))

    def stop(self):
        self._stop.set()
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=4)
        self._server = None
        self._thread = None
