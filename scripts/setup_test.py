# -*- coding: utf-8 -*-
"""setup_all / envkit.download 回归：本地假镜像 + 假 aria2，不联网、不装包、不碰真权重。

跑法： .venv\\Scripts\\python.exe scripts\\setup_test.py
"""
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from envkit import download as hd   # noqa: E402
import setup_all as sa              # noqa: E402

RESULTS = []
_TMP = []


def ok(name, cond, extra=""):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ((" · " + str(extra)) if extra else ""))


def tmpdir(prefix="moss_setup_"):
    d = tempfile.mkdtemp(prefix=prefix)
    _TMP.append(d)
    return d


def serve(handler_cls):
    """每台假镜像一个新端口；清单缓存按 repo 存 6 小时，不清会继续打上一台。"""
    hd._CACHE.clear()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_port


PAYLOAD = bytes(range(256)) * (3 * 1024 * 4 + 123)     # 3MB 出头，内容可复现
REQS = []


class RangeH(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if "/api/models/" in self.path:
            body = json.dumps({"siblings": [{"rfilename": "big.bin",
                                             "size": len(PAYLOAD)}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.endswith("/big.bin"):
            rng = self.headers.get("Range")
            REQS.append(rng)
            if rng:
                m = re.match(r"bytes=(\d+)-(\d+)", rng)
                s, e = int(m.group(1)), int(m.group(2))
                data = PAYLOAD[s:e + 1]
                self.send_response(206)
                self.send_header("Content-Range",
                                 "bytes %d-%d/%d" % (s, e, len(PAYLOAD)))
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(200)
                self.send_header("Content-Length", str(len(PAYLOAD)))
                self.end_headers()
                self.wfile.write(PAYLOAD)
            return
        self.send_response(404)
        self.end_headers()


class NoRangeH(RangeH):
    def do_GET(self):
        if self.path.endswith("/big.bin"):
            REQS.append(self.headers.get("Range"))
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            self.wfile.write(PAYLOAD)
            return
        RangeH.do_GET(self)


def test_patterns():
    ok("目录前缀模式", hd.match_path("video/a.mp4", ["video/*"]))
    ok("文件名通配", hd.match_path("a/b.safetensors", ["*.safetensors"]))
    ok("整路径精确", hd.match_path("x/y.bin", ["x/y.bin"]))
    ok("不匹配", not hd.match_path("x/y", ["z"]))


def test_chunks():
    size = 3 * 1024 * 1024 + 77
    chunks = hd._plan_chunks(size, 1024 * 1024)
    ok("分段从头到尾覆盖", chunks[0]["start"] == 0 and chunks[-1]["end"] == size - 1
       and all(chunks[i]["end"] + 1 == chunks[i + 1]["start"]
               for i in range(len(chunks) - 1)), len(chunks))


def _download(ep, target, **kw):
    # 测试机可能真开着 Motrix：这里必须锁死在「内置下载器」这条路上，
    # 否则断言的东西会随桌面软件在不在而变（Motrix 另有 test_motrix 专测）。
    kw.setdefault("config", {"motrix": False})
    return hd.download("local/test", target, jobs=4, chunk_mb=1, retries=1,
                       endpoints=[ep], probe_timeout=5, timeout=10,
                       on_progress=kw.pop("on_progress", lambda e: None),
                       on_log=kw.pop("on_log", lambda s: None), **kw)


def test_segmented():
    srv, ep = serve(RangeH)
    target = tmpdir()
    events = []
    try:
        r = _download(ep, target, on_progress=events.append)
        data = open(os.path.join(target, "big.bin"), "rb").read()
        ok("分段下载内容一致", r["ok"] and data == PAYLOAD)
        ok("完成后清掉 sidecar", not os.path.exists(
            os.path.join(target, "big.bin.mossdl")))
        ok("分段至少开了 4 条 Range", len([x for x in REQS if x]) >= 4)
        last = events[-1]
        ok("进度含 done/total/速度",
           last.get("done") == len(PAYLOAD) and last.get("total") == len(PAYLOAD)
           and "speed" in last and last.get("busy") is False)
        ok("选中镜像写进进度", last.get("endpoint") == ep)
    finally:
        srv.shutdown()

    # 续传：前两段已落盘，只该再请求后面的段（探测用的 bytes=0-0 不算）
    srv, ep = serve(RangeH)
    target = tmpdir()
    path = os.path.join(target, "big.bin")
    chunks = hd._plan_chunks(len(PAYLOAD), 1024 * 1024)
    with open(path, "wb") as f:
        f.write(PAYLOAD[:chunks[1]["end"] + 1])
        f.truncate(len(PAYLOAD))
    for c in chunks[:2]:
        c["done"] = c["end"] - c["start"] + 1
    hd._save_sidecar(path, len(PAYLOAD), chunks)
    REQS.clear()
    try:
        r = _download(ep, target)
        data = open(path, "rb").read()
        asked = [x for x in REQS if x and x != "bytes=0-0"]
        ok("续传内容一致", r["ok"] and data == PAYLOAD)
        ok("续传跳过已完成段", asked and all(
            int(re.match(r"bytes=(\d+)", x).group(1)) >= chunks[2]["start"]
            for x in asked), asked)
        ok("续传报已下字节", r.get("resumed", 0) >= chunks[1]["end"] + 1,
           r.get("resumed"))
    finally:
        srv.shutdown()


def test_no_range():
    srv, ep = serve(NoRangeH)
    target = tmpdir()
    try:
        r = _download(ep, target)
        data = open(os.path.join(target, "big.bin"), "rb").read()
        ok("不支持 Range 也能下完", r["ok"] and data == PAYLOAD)
    finally:
        srv.shutdown()


def test_sidecar():
    d = tmpdir()
    p = os.path.join(d, "a.bin")
    open(p, "wb").close()
    chunks = hd._plan_chunks(100, 10)
    hd._save_sidecar(p, 100, chunks)
    ok("sidecar 读回", hd._load_sidecar(p, 100) == chunks)
    ok("尺寸不符的 sidecar 作废", hd._load_sidecar(p, 101) is None)


# ---------------------------------------------------------------- Motrix / aria2
class Aria2H(BaseHTTPRequestHandler):
    """假 aria2：addUri 时直接落盘，然后谎报 complete——够验「交接 → 轮询 → 收尾」这条链。"""
    tokens = []
    written = []
    notfound = False       # True 时模拟真 Motrix「下完立刻清掉任务」

    def log_message(self, *a):
        pass

    def _status(self):
        n = len(PAYLOAD)
        return {"status": "complete", "completedLength": str(n), "totalLength": str(n),
                "downloadSpeed": "0", "errorMessage": ""}

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(n) or b"{}")
        method = req.get("method")
        params = list(req.get("params") or [])
        if params and str(params[0]).startswith("token:"):
            Aria2H.tokens.append(params.pop(0)[len("token:"):])
        if method == "aria2.getVersion":
            res = {"version": "1.37.0", "enabledFeatures": []}
        elif method == "aria2.addUri":
            _uris, opts = params
            path = os.path.join(opts["dir"], opts["out"])
            os.makedirs(opts["dir"], exist_ok=True)
            with open(path, "wb") as f:
                f.write(PAYLOAD)
            Aria2H.written.append(path)
            res = "g%d" % len(Aria2H.written)
        elif method == "system.multicall":
            # aria2 的 multicall：令牌在子调用 params 里，不在顶层
            res = []
            for c in params[0]:
                cp = list(c.get("params") or [])
                tok = ""
                if cp and str(cp[0]).startswith("token:"):
                    tok = cp.pop(0)[len("token:"):]
                    Aria2H.tokens.append(tok)
                if not tok:
                    res.append({"code": 1, "message": "Unauthorized"})
                elif Aria2H.notfound:
                    res.append({"code": 1, "message": "GID g1 is not found"})
                else:
                    res.append([self._status()])
        else:
            res = "OK"          # forceRemove 之类
        body = json.dumps({"jsonrpc": "2.0", "id": req.get("id"),
                           "result": res}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_motrix_settings():
    d = tmpdir()
    os.makedirs(os.path.join(d, "Motrix"))
    with open(os.path.join(d, "Motrix", "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"engine": {"rpcPort": 16800, "rpcSecret": "s3cret"}}, f)
    old = os.environ.get("APPDATA")
    os.environ["APPDATA"] = d
    try:
        ok("从本机 Motrix 设置读端口与密钥（不落日志）",
           hd.motrix_settings() == (16800, "s3cret"), hd.motrix_settings())
        ok("motrix=false 时不去发现",
           hd._motrix_cfg({"motrix": False}) is None)
        ok("清单里写死端口时优先用它",
           hd._motrix_cfg({"motrix": {"port": 1, "secret": "s"}}) == (1, "s"))
    finally:
        if old is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = old


def test_motrix():
    srv, ep = serve(RangeH)
    rpc = ThreadingHTTPServer(("127.0.0.1", 0), Aria2H)
    threading.Thread(target=rpc.serve_forever, daemon=True).start()
    Aria2H.tokens.clear()
    Aria2H.written.clear()
    target = tmpdir()
    events = []
    try:
        r = hd.download("local/test", target, endpoints=[ep], probe_timeout=5,
                        timeout=10, on_progress=events.append,
                        on_log=lambda s: None,
                        config={"motrix": {"port": rpc.server_port, "secret": "tok"}})
        data = open(os.path.join(target, "big.bin"), "rb").read()
        ok("Motrix 分支：交给 aria2 并拿回完整文件", r["ok"] and data == PAYLOAD, r)
        ok("Motrix 分支：密钥随 RPC 请求发出（不写进日志）", "tok" in Aria2H.tokens,
           Aria2H.tokens[:1])
        ok("Motrix 分支：进度阶段标成 aria2",
           any(e.get("phase") == "aria2" for e in events))
        # 真 Motrix 下完会立刻把任务清掉（GID 找不到）：盘上文件齐就不该误判失败
        Aria2H.notfound = True
        t2 = tmpdir()
        r2 = hd.download("local/test", t2, endpoints=[ep], probe_timeout=5,
                         timeout=10, on_log=lambda s: None,
                         config={"motrix": {"port": rpc.server_port, "secret": "tok"}})
        d2 = open(os.path.join(t2, "big.bin"), "rb").read()
        ok("Motrix 清掉已完成任务时按盘上文件收尾", r2["ok"] and d2 == PAYLOAD, r2)
    finally:
        Aria2H.notfound = False
        srv.shutdown()
        rpc.shutdown()
    # RPC 不通时必须静默回落内置下载器，不能把下载卡死
    srv, ep = serve(RangeH)
    target = tmpdir()
    try:
        r = hd.download("local/test", target, jobs=4, chunk_mb=1, retries=1,
                        endpoints=[ep], probe_timeout=5, timeout=10,
                        on_log=lambda s: None,
                        config={"motrix": {"port": 1, "secret": "x"}})
        data = open(os.path.join(target, "big.bin"), "rb").read()
        ok("Motrix 没接上 → 自动回落内置下载器", r["ok"] and data == PAYLOAD, r)
    finally:
        srv.shutdown()


def _item(key, group, detail="", state="miss", gb=0, fix=None, label=None, env="base",
          optional=False):
    return {"key": key, "group": group, "detail": detail, "state": state,
            "gb": gb, "label": label or key, "env": env, "optional": optional,
            "fix": fix or {"kind": "none"}}

G_RT = "ComfyUI 运行时"


def test_plan():
    items = [
        _item("dir:outputs", "目录", fix={"kind": "dir", "path": "outputs"}),
        _item("pkg:pywebview", "依赖包", fix={"kind": "pip"}),
        _item("pkg:torch", "依赖包", fix={"kind": "pip"}, env="qwen"),
        _item("pkg:websocket-client", "依赖包", fix={"kind": "pip"}, env="moss"),
        _item("comfy:app", G_RT, state="part", fix={"kind": "comfyui"}, env="moss"),
        _item("comfy:venv", G_RT, fix={"kind": "comfyvenv"}, env="moss"),
        _item("model:turbo", "模型权重", fix={"kind": "model"}, gb=30.3, env="qwen"),
        _item("model:moss-comfy", "模型权重", fix={"kind": "model"}, gb=13, env="moss"),
        _item("model:h3-fl2va", "模型权重", fix={"kind": "model"}, gb=41.37,
              env="h3", optional=True),
    ]

    def keys(engine="all", with_models=True, models_only=False, full=True):
        return [x["key"] for x in sa.build_plan(items, engine, with_models,
                                                models_only, full)]

    # BAT 的默认职责只有一件：把界面壳装到能打开。依赖与权重回软件里下。
    ok("默认只备目录 + 界面壳 + 复检",
       keys(full=False) == ["dirs", "shell", "recheck"], keys(full=False))

    k = keys()
    ok("计划：壳排在依赖前、权重在后、复检收尾",
       k == ["dirs", "shell", "deps", "comfyui", "comfyvenv",
             "qwen_models", "moss_models", "recheck"], k)
    deps = [x for x in sa.build_plan(items, "all", True, False, True)
            if x["key"] == "deps"][0]["items"]
    ok("重依赖与 Moss 包同属依赖步骤",
       {_item_key(x) for x in deps} == {"pkg:torch", "pkg:websocket-client"})
    ok("仅千问：不收 Moss 组与 ComfyUI",
       "comfyui" not in keys("qwen") and "moss_models" not in keys("qwen")
       and "deps" in keys("qwen"))
    k = keys("moss")
    moss_deps = [x for x in sa.build_plan(items, "moss", True, False, True)
                 if x["key"] == "deps"][0]["items"]
    ok("仅 Moss：不装千问专用 torch、不碰千问权重",
       "qwen_models" not in k and "comfyui" in k
       and {_item_key(x) for x in moss_deps} == {"pkg:websocket-client"})
    ok("--no-models 不出权重步骤",
       "qwen_models" not in keys(with_models=False)
       and "moss_models" not in keys(with_models=False))
    ok("--models-only 只留目录 + 权重 + 复检",
       keys(models_only=True) == ["dirs", "qwen_models", "moss_models", "recheck"],
       keys(models_only=True))
    # 可选环境（H3）默认不跟着 all 走；点名 --env h3 才带上运行时 + 权重
    ok("--env all 不悄悄带 41 GB 的 H3", "h3_models" not in keys())
    k = keys("h3")
    ok("--env h3 带上 ComfyUI 运行时与 H3 权重",
       "comfyui" in k and "h3_models" in k and "qwen_models" not in k, k)


def _item_key(it):
    return it["key"]


def test_console_progress():
    con = sa.Console(os.path.join(tmpdir(), "setup.log"))
    con.tty = False
    con.download({"busy": True, "phase": "download", "done": 50 * 1024 * 1024,
                  "total": 100 * 1024 * 1024, "speed": 10 * 1024 * 1024,
                  "eta": 5, "files_done": 0, "files_total": 1, "file": "a.bin"})
    ok("进度文案有百分比/速度/剩余",
       "50%" in con._detail and "MB/s" in con._detail and "剩" in con._detail,
       con._detail)
    con.close()


def test_verify():
    root = tmpdir()
    d = os.path.join(root, "envs", "qwen", "models", "turbo")
    os.makedirs(d)
    with open(os.path.join(d, "a.bin"), "wb") as f:
        f.write(b"x" * 10)
    spec = {"models": [{"repo": "o/turbo", "dir": "envs/qwen/models/turbo",
                        "must": {"a.bin": 10}}]}
    r = sa.Runner(root, None, None, spec)
    it = {"key": "model:turbo",
          "fix": {"repo": "o/turbo", "dir": "envs/qwen/models/turbo"}}
    ok("权重校验：尺寸对", r._verify(it) == [])
    with open(os.path.join(d, "a.bin"), "wb") as f:
        f.write(b"x")
    ok("权重校验：尺寸不对要点名", r._verify(it) == ["a.bin（1/10）"], r._verify(it))


def test_snap_copy():
    cfg_dir = tmpdir()
    os.environ["QIC_CONFIG"] = os.path.join(cfg_dir, "config.json")
    import app

    class Dummy:
        def __init__(self):
            self.st = {"dl": {"busy": True, "done": 3}, "running": None}
            self.cfg = {"engine": "qwen"}
            self.moss = None
            self.mgr = None

        def _busy(self):
            return False
    d = Dummy()
    snap = app.App._snap(d)
    ok("状态快照复制下载进度", snap["dl"] == {"busy": True, "done": 3})
    ok("状态快照不共享 dict", snap["dl"] is not d.st["dl"])


def main():
    test_patterns()
    test_chunks()
    test_segmented()
    test_no_range()
    test_sidecar()
    test_motrix_settings()
    test_motrix()
    test_plan()
    test_console_progress()
    test_verify()
    test_snap_copy()
    bad = RESULTS.count(False)
    print("\nSETUP TEST %s（%d 项）" % ("OK" if not bad else "FAIL %d" % bad, len(RESULTS)))
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        for d in _TMP:
            shutil.rmtree(d, ignore_errors=True)
