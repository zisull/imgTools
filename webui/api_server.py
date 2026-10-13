# -*- coding: utf-8 -*-
"""
api_server.py —— FastAPI 对外 REST（M4）
=========================================
端点（除 /v1/health 外全部 Bearer 令牌鉴权）：
  GET  /v1/health                状态：模型/运行/显存/排队数
  POST /v1/images/generations    JSON {prompt,size,steps,seed,n,mode,negative}
  POST /v1/images/edits          multipart：image≤10 + prompt + res
  GET  /v1/tasks/{id}            异步任务状态（queued/running/done/failed）
  GET  /v1/images/{id}           取结果 PNG

任务单线程序执行（Turbo 一张 20~30s，UI 互斥）：worker 等 App 空闲后复用
App._do_gen —— 进度、日志、画廊计数与 UI 发起的任务同一条流，界面上看得见。
uvicorn 跑后台线程，Server.should_exit 可停，改端口/局域网开关即重启监听。
"""
import os
import queue
import threading
import time
import uuid
from typing import List

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

GEN_SIZES = {"512x512", "768x768", "1024x1024", "576x1024",
             "1024x1536", "1536x1024", "1536x1536"}
EDIT_RES = {"512", "768"}
IMG_SUFFIX = (".png", ".jpg", ".jpeg", ".webp")


class ApiServer:
    def __init__(self, console):
        self.c = console
        self.jobs = {}            # task_id -> job dict
        self.files = {}           # image_id -> 绝对路径
        self._q = queue.Queue()
        self._stop = threading.Event()
        self._server = None
        self._thread = None
        self.api = self._build()
        threading.Thread(target=self._worker, daemon=True).start()

    # ------------------------------------------------------------ 鉴权/工具
    def _check(self, request):
        tok = str((self.c.cfg.get("api") or {}).get("token") or "")
        if not tok:
            raise HTTPException(503, "令牌还没生成：先在控制台 API 页开启服务")
        hdr = request.headers.get("authorization") or ""
        if hdr != "Bearer " + tok:
            raise HTTPException(401, "令牌不对：Authorization: Bearer <token>")

    def _src(self, request):
        return request.client.host if request.client else "?"

    def _submit(self, payload, src):
        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "status": "queued", "created": time.time(),
               "src": src, "payload": payload, "images": [], "error": ""}
        self.jobs[jid] = job
        self._q.put(job)
        return job

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
            while self.c._busy() and not self._stop.is_set():
                time.sleep(0.8)
            if self._stop.is_set():
                job["status"] = "failed"
                job["error"] = "服务已关闭，任务没执行"
                continue
            job["status"] = "running"
            g = dict(job["payload"])
            g["_saved"] = []
            self.c._log("🌐 API 任务 %s 开始（来源 %s）" % (job["id"], job["src"]))
            try:
                self.c._do_gen(g)
                for p in g["_saved"]:
                    iid = uuid.uuid4().hex[:12]
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
            return {"ok": True, "model_loaded": bool(s.get("model_loaded")),
                    "running": s.get("running"), "vram_used": s.get("vram_used"),
                    "vram_total": s.get("vram_total"), "queued": me._q.qsize()}

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
            size = str(body.get("size") or "1024x1024")
            if size not in GEN_SIZES:
                raise HTTPException(400, "size 只认这几档：%s" % ", ".join(sorted(GEN_SIZES)))
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
            return {"task_id": job["id"], "status": job["status"]}

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
            ref_dir = os.path.join(os.path.abspath(me.c.cfg["console"]["output_dir"]),
                                   "api_refs", jid)
            os.makedirs(ref_dir, exist_ok=True)
            paths = []
            for i, f in enumerate(files):
                ext = os.path.splitext(f.filename)[1].lower()
                if ext not in IMG_SUFFIX:
                    raise HTTPException(400, "第 %d 张不是图片格式：%s" % (i + 1, ext))
                data = await f.read()
                if not data:
                    raise HTTPException(400, "第 %d 张是空文件" % (i + 1))
                p = os.path.join(ref_dir, "%d%s" % (i + 1, ext))
                with open(p, "wb") as fh:
                    fh.write(data)
                paths.append(p)
            payload = {"mode": "edit", "prompt": prompt, "res": str(res),
                       "images": paths, "steps": "8", "seed": -1, "count": 1,
                       "negative": "", "kv_cache": True}
            job = me._submit(payload, me._src(request))
            me.c._log("🌐 API(%s) 提交编辑任务 %s：%d 张参考图 · %s 画幅"
                      % (job["src"], job["id"], len(paths), res))
            return {"task_id": job["id"], "status": job["status"]}

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
