# -*- coding: utf-8 -*-
"""Moss 自测（无 GPU / 无 ComfyUI）：工作流装配 + 假 ComfyUI 端到端出图 + env 体检。

    .venv\\Scripts\\python.exe scripts\\moss_selftest.py

只验「不碰显卡也能验」的那几层（需要 uvicorn 才能起服务的那些用例不在这里，
本脚本连 uvicorn 都是假模块，验的是提交/淘汰这段纯逻辑）：
  · 模板占位符替换对不对、类型保不保、极速档不接 SLG、精修档接 SLG 且不挂 LoRA
  · MossManager 对着一台假 ComfyUI 走完 start→/prompt→/history→/view→落盘
  · 引擎「没起来」时的三种退场：进程崩、用户按停止、失败路径的锁可重入
  · 报错只引用本轮那一段日志（旧崩溃不会被当成这一轮的根因），等待期间有心跳
  · /ws 与 /prompt 的先后顺序、事件整批丢失时的 history 兜底
  · env_check 的 Moss 段（comfyui/comfyvenv/mossmodel 三类可修项）
  · 内嵌 ComfyUI 的 torch 索引单独指 cu130+（int8/w4a8 内核的开关，千问那套不动）
  · 旧版 ComfyUI（main.py 在但没有 moss_image 节点）要报「可修」，不能报绿灯
  · 对外 API 的长跑上限：参考图分块拦截、任务单淘汰、排队满了回 429
  · 导航换代（v2 的 11 页 → v6 的 7 页）：老配置自动重排、改过的名字留着、二次启动幂等
  · 四个出图 mode 的输入图契约：透明档（rgba）并进文生图后不许串到 edit 那条流水线
App 的 __init__ 不建窗口（窗口在 main() 里），所以配置载入那段直接真跑一遍；
档位切换、生成这类要 webview 与显卡的状态机仍留给真机冒烟（scripts\\ui_cdp.py）。
"""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "webui"), os.path.join(ROOT, "engine")):
    sys.path.insert(0, _p)

try:
    sys.stdout.reconfigure(encoding="utf-8")   # Windows 控制台默认 GBK，✓ 和中文会炸
except Exception:
    pass

from moss_mgr import ComfyError, MossManager, _is_win  # noqa: E402

STATE = {"graph": None, "order": [], "ready_at": 0.0, "ws_url": "",
         "client_id": "", "number": None, "queue_body": None,
         "running_q": [], "pending_q": [],
         "imgs": [{"filename": "moss_00001.png", "subfolder": "", "type": "output"}]}


class FakeComfy(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body=b"", ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/system_stats"):
            self._send(200, b'{"devices":[{"name":"cuda:0"}]}')
        elif self.path.startswith("/history/"):
            # ready_at 之前回空：模拟「任务还在跑，历史里当然还没有」
            if time.time() < STATE["ready_at"]:
                self._send(200, b"{}")
                return
            # 真·ComfyUI history 按节点 id 组织：outputs.<node>.images（18 是 SaveImage）
            self._send(200, json.dumps({
                self.path.rsplit("/", 1)[-1]: {"outputs": {"18": {"images": STATE["imgs"]}}}
                }).encode())
        elif self.path.startswith("/view"):
            self._send(200, b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")
        elif self.path.startswith("/queue"):
            # 真·ComfyUI 的队列项是 [number, prompt_id, workflow, outputs, extra_data]
            self._send(200, json.dumps({"queue_running": STATE["running_q"],
                                        "queue_pending": STATE["pending_q"]}).encode())
        else:
            self._send(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if self.path == "/prompt":
            STATE["order"].append("prompt")
            body = json.loads(raw.decode("utf-8"))
            STATE["graph"] = body.get("prompt")
            STATE["client_id"] = body.get("client_id") or ""
            STATE["number"] = body.get("number")
            self._send(200, b'{"prompt_id":"fake-1"}')
        elif self.path == "/queue":
            STATE["order"].append("queue")
            STATE["queue_body"] = json.loads(raw.decode("utf-8"))
            self._send(200, b'{"ok":true}')
        elif self.path == "/interrupt":
            STATE["order"].append("interrupt")
            self._send(200, b'{"ok":true}')
        else:
            self._send(404)


def test_templates():
    mgr = MossManager(os.path.join(ROOT, "comfyui"), port=1)
    fast = mgr.build_graph(template="workflow_fast.json", prompt="a fox", negative="",
                           width=1024, height=768, seed=7, steps=8, cfg=1.0,
                           batch=3, prefix="moss")
    ct = {n["class_type"] for n in fast.values()}
    assert "SkipLayerGuidanceDiTSimple" not in ct, "极速档不该有 SLG（CFG=1 无负向分支）"
    assert "LoraLoaderModelOnly" in ct, "极速档要挂 8 步 DMD LoRA"
    assert "ModelSamplingSD3" not in ct, "原生路径 shift 已烘进核心，不该有采样补丁节点"
    ksam = next(n for n in fast.values() if n["class_type"] == "KSampler")["inputs"]
    assert ksam["scheduler"] == "simple" and ksam["steps"] == 8 and ksam["cfg"] == 1.0
    unet = next(n for n in fast.values() if n["class_type"] == "UNETLoader")["inputs"]
    assert unet["unet_name"] == "moss_image_sft_int8_convrot.safetensors", "拼写必须是 convrot"
    clip = next(n for n in fast.values() if n["class_type"] == "CLIPLoader")["inputs"]
    assert clip["type"] == "moss_image" and clip["clip_name"] == "qwen3.5_9b_w4a8_gptq.safetensors"
    empty = next(n for n in fast.values() if n["class_type"] == "EmptyFlux2LatentImage")["inputs"]
    assert empty["width"] == 1024 and isinstance(empty["width"], int), "占位符要保留 int 类型"
    assert empty["batch_size"] == 3, "count 走 batch 一次过"
    assert ksam["seed"] == 7 and isinstance(ksam["seed"], int)
    # 提速锁：CFG=1 时采样器不读负向条件，所以负向接线必须复用正向节点。
    # 单挂一个负向 CLIPTextEncode 的话，每张新提示词都白跑一次 9B 文本编码器前向。
    assert ksam["negative"] == ksam["positive"], "极速档负向该接正向输出，别再编一遍"
    assert sum(1 for n in fast.values() if n["class_type"] == "CLIPTextEncode") == 1, \
        "极速档只许一个文本编码节点"
    assert not any("{{" in json.dumps(n) for n in fast.values()), "有占位符没替换干净"

    full = mgr.build_graph(template="workflow_full.json", prompt="a fox",
                           negative="watermark", width=832, height=1216, seed=42,
                           steps=50, cfg=3.0, slg_skip_layer=22, slg_start=0.0, slg_end=0.5)
    ct2 = {n["class_type"] for n in full.values()}
    assert "SkipLayerGuidanceDiTSimple" in ct2 and "LoraLoaderModelOnly" not in ct2
    slg = next(n for n in full.values() if n["class_type"] == "SkipLayerGuidanceDiTSimple")["inputs"]
    assert slg["single_layers"] == "22" and slg["end_percent"] == 0.5
    k2 = next(n for n in full.values() if n["class_type"] == "KSampler")["inputs"]
    assert k2["scheduler"] == "sgm_uniform" and k2["cfg"] == 3.0 and k2["steps"] == 50
    # 中间档 25 步：走的是 full 模板（不挂 LoRA），与精修只差步数
    mid = mgr.build_graph(template="workflow_full.json", prompt="a fox",
                          negative="watermark", width=1024, height=1024, seed=1,
                          steps=25, cfg=3.0)
    k3 = next(n for n in mid.values() if n["class_type"] == "KSampler")["inputs"]
    assert k3["steps"] == 25 and k3["cfg"] == 3.0 and k3["scheduler"] == "sgm_uniform"
    assert "LoraLoaderModelOnly" not in {n["class_type"] for n in mid.values()}, \
        "25 步绝不能挂 8 步 DMD LoRA（那是极速档的结构性节点）"
    assert not any("{{" in json.dumps(n) for n in mid.values()), "25 步档有占位符没替换干净"
    print("  ✓ 模板装配：fast 无 SLG/挂 LoRA，full 接 SLG/无 LoRA，类型与拼写都对")


def test_generate_against_fake():
    httpd = HTTPServer(("127.0.0.1", 0), FakeComfy)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        mgr = MossManager(os.path.join(ROOT, "comfyui"), port=port, log=lambda s: None)
        mgr.state.url = "http://127.0.0.1:%d" % port
        mgr.state.running = True
        seen = []
        out = tempfile.mkdtemp(prefix="moss_selftest_")
        paths = mgr.generate(
            dict(template="workflow_fast.json", prompt="a red fox", negative="",
                 width=1024, height=1024, seed=1, steps=8, cfg=1.0, batch=1, prefix="moss"),
            on_progress=lambda d, t: seen.append((d, t)),
            should_stop=lambda: False, out_dir=out, out_prefix="moss")
        assert len(paths) == 1 and os.path.isfile(paths[0]), paths
        assert os.path.getsize(paths[0]) > 8, "落盘的 PNG 是空的"
        assert STATE["graph"] and "1" in STATE["graph"], "POST /prompt 该收到整张图"
        assert STATE["graph"]["1"]["class_type"] == "UNETLoader"
        print("  ✓ 假 ComfyUI 端到端：/prompt→/history→/view→落盘 1 张 PNG")
    finally:
        httpd.shutdown()


def test_ws_order_and_loss():
    """/ws 必须先挂上再提交，且一条事件收不到也要秒收尾。

    真机现场：ComfyUI 自己写着「Prompt executed in 14.17 seconds」，generate() 却耗了
    1201 秒——WS 是 POST /prompt 之后才连的，那一轮的 execution_progress /
    execution_success 全发给了还不存在的 client_id，而循环只等 execution_success
    才退，于是空转到 1200 秒上限，界面进度条全程空白。
    """
    import types

    httpd = HTTPServer(("127.0.0.1", 0), FakeComfy)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    class WsTimeout(Exception):
        pass

    class WsClosed(Exception):
        pass

    class FakeSocket:
        def __init__(self, msgs):
            self.msgs, self.closed = list(msgs), False

        def settimeout(self, _t):
            pass

        def recv(self):
            time.sleep(0.05)                  # 真 recv() 是阻塞的，别让自测空转 CPU
            if self.msgs:
                return json.dumps(self.msgs.pop(0))
            raise WsTimeout("no event")

        def close(self):
            self.closed = True

    out = tempfile.mkdtemp(prefix="moss_selftest_ws_")
    old_ws = sys.modules.get("websocket")
    try:
        mgr = MossManager(os.path.join(ROOT, "comfyui"), port=port, log=lambda s: None)
        mgr.state.url = "http://127.0.0.1:%d" % port
        mgr.state.running = True
        socks = []

        def install(msgs):
            sock = FakeSocket(msgs)
            socks.append(sock)
            sys.modules["websocket"] = types.SimpleNamespace(
                create_connection=lambda url, **k: (STATE["order"].append("ws"),
                                                    STATE.__setitem__("ws_url", url), sock)[2],
                WebSocketTimeoutException=WsTimeout,
                WebSocketConnectionClosedException=WsClosed)
            return sock

        def run(msgs, ready_in):
            STATE["order"], STATE["ready_at"] = [], time.time() + ready_in
            seen = []
            t0 = time.time()
            paths = mgr.generate(
                dict(template="workflow_fast.json", prompt="a fox", negative="",
                     width=512, height=512, seed=3, steps=8, cfg=1.0, batch=1, prefix="moss"),
                on_progress=lambda d, t: seen.append((d, t)),
                should_stop=lambda: False, out_dir=out, out_prefix="moss")
            return seen, paths, time.time() - t0

        # ① 事件整批丢失（一条都收不到）：靠 2 秒一次的 history 兜底收尾
        sock = install([])
        seen, paths, el = run([], 0.3)
        assert STATE["order"][:2] == ["ws", "prompt"], STATE["order"]
        # sid 注册名写错（client_id）时服务端 sockets 里没有这条连接，事件全丢但
        # 一声不响——正是真机上「14 秒的活干等 20 分钟」的根因，必须在自测里钉死。
        assert "clientId=" in STATE["ws_url"] and "client_id=" not in STATE["ws_url"], STATE["ws_url"]
        assert paths and os.path.isfile(paths[0]), paths
        assert el < 30, "事件丢了就干等到超时：%.0fs" % el
        assert sock.closed, "socket 没收尾，反复出图会攒一堆悬挂连接"
        assert not seen, seen

        # ② 事件正常到达：进度回调要有数，且不能等满兜底窗口
        #    两代事件名都要认（这支 ComfyUI 发 "progress"，旧版发 "execution_progress"）
        prog = [{"type": "progress" if i % 2 else "execution_progress",
                 "data": {"prompt_id": "fake-1", "value": v, "max": 8}}
                for i, v in enumerate((1, 2, 8))]
        prog.append({"type": "execution_success", "data": {"prompt_id": "fake-1"}})
        install(prog)
        seen, paths, el = run(prog, 3.0)      # 历史故意晚 3 秒：逼它靠事件而不是兜底
        assert seen == [(1, 8), (2, 8), (8, 8)], seen
        assert STATE["order"][:2] == ["ws", "prompt"], STATE["order"]
        assert paths, paths
    finally:
        if old_ws is None:
            sys.modules.pop("websocket", None)
        else:
            sys.modules["websocket"] = old_ws
        STATE["ready_at"] = 0.0
        STATE["order"] = []
        httpd.shutdown()
        shutil.rmtree(out, ignore_errors=True)
    print("  ✓ 进度通道：先连 /ws 再提交；事件全丢也能 3 秒内收尾，事件在时步级进度有数")


def test_env_moss():
    import env_check as ec

    spec = ec.load_spec(ROOT)
    assert isinstance(spec.get("moss"), dict), "env.json 要有 moss 段"
    # 拿一个空的临时根目录当「干净机器」：本机可能已经补全过了，
    # 拿真实 ROOT 断言「该有 comfyui/comfyvenv 可修」就成了看运气。
    clean = tempfile.mkdtemp(prefix="moss_selftest_env_")
    try:
        items = ec._moss_checks(clean, spec)
    finally:
        shutil.rmtree(clean, ignore_errors=True)
    kinds = {it["fix"]["kind"] for it in items}
    assert {"comfyui", "comfyvenv", "mossmodel"} <= kinds, kinds
    assert all(it["group"] == "Moss 环境" for it in items)
    plan = {it["key"] for it in ec.fix_plan(items)}
    assert {"comfy:app", "comfy:venv", "moss:moss-comfy", "moss:moss-lora"} <= plan, plan
    # 权重清单必须带精确字节数（断点续传靠它判完整）
    for m in spec["moss"]["models"]:
        assert m.get("must") and all(int(v) > 1000 for v in m["must"].values()), m["key"]
    print("  ✓ env 体检：Moss 段 4 项可修，权重清单带精确字节数")


def test_comfyui_torch_index():
    """内嵌 ComfyUI 的 torch 索引必须单独指到 cu130+，且不许把千问那套带跑。

    这不是洁癖：MOSS-Image 的权重是 int8_convrot / w4a8_gptq，ComfyUI 的
    comfy/quant_ops.py 在 torch.version.cuda < 13 时把整套 kitchen CUDA 后端
    disable 掉，只走 eager 反量化。同一张 4070 热 512²/8 步实测 4.3 秒 → 0.9 秒。
    """
    import env_check as ec

    def cu(s):
        m = re.search(r"cu(\d+)", str(s or ""))
        return int(m.group(1)) if m else 0

    spec = ec.load_spec(ROOT)
    qwen = str((spec.get("indexes") or {}).get("torch") or "")
    mine = str(((spec.get("moss") or {}).get("comfyui") or {}).get("torch_index") or "")
    assert cu(mine) >= 130, "内嵌 ComfyUI 的 torch 没指到 cu130+：int8/w4a8 内核会被整组关掉，出图慢 5 倍"
    assert cu(qwen) < cu(mine), "千问那套不跑 int8/w4a8 内核，索引不该跟着一起换"

    # 只改 env.json 不改 app.py 等于没改：这两行断言盯的是「代码真读了这个键」
    src = open(os.path.join(ROOT, "webui", "app.py"), encoding="utf-8").read()
    assert "torch_index" in src, "app.py 里没人读 moss.comfyui.torch_index"
    assert "--force-reinstall" in src, "只换 local 标记（+cu128→+cu130）时 pip 当成已满足，必须强制重装"
    print("  ✓ 内嵌 ComfyUI 的 torch 单独指 cu130+ 索引，千问那套照旧 cu%d" % cu(qwen))


def test_comfyui_moss_nodes():
    """旧版 ComfyUI（没有 moss_image 节点）要报「可修」，不能报 ok。

    跨机迁移最容易踩的静默失败：clone 时代码是旧的，main.py 明明在、体检却绿灯，
    直到点出图才炸「未知 class_type」。极速档加载要 1~2 分钟，用户根本猜不到是版本问题。
    """
    import env_check as ec

    spec = ec.load_spec(ROOT)
    moss = spec["moss"]
    root = tempfile.mkdtemp(prefix="moss_selftest_cx_")
    try:
        cx_dir = os.path.join(root, moss["comfyui"].get("dir") or "comfyui")
        d = lambda *p: os.makedirs(os.path.join(cx_dir, *p), exist_ok=True)
        item = lambda: ec._check_comfyui(root, moss, None)

        assert item()["state"] == "miss", item()
        d("comfy_extras")
        open(os.path.join(cx_dir, "main.py"), "w").close()
        assert item()["state"] == "part", "main.py 在但不认 moss_image，不能算 ok"
        assert item()["fix"]["kind"] == "comfyui", item()["fix"]
        open(os.path.join(cx_dir, "comfy_extras", "nodes_moss_image.py"), "w").close()
        assert item()["state"] == "ok", item()
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("  ✓ 旧 ComfyUI 缺 moss_image 节点：报「可修」并挂一键补全")


def test_wait_ready():
    """引擎拉起的等待逻辑：进程崩了要一秒退、用户按停止要立刻退、失败路径不能自锁。

    这三条对应的都是真机现象——「2 分多钟界面卡在启动中」：CPU 版 torch 让 ComfyUI 在
    import 阶段就崩，而 start() 的失败分支要在持锁状态下调 stop()，锁不可重入就死锁。
    """
    mgr = MossManager(os.path.join(ROOT, "comfyui"), port=1)

    class Dead:
        returncode = 1
        def poll(self): return 1
    mgr._proc = Dead()
    t0 = time.time()
    why = mgr._wait_ready(60)
    assert why.startswith("进程退出"), why
    assert time.time() - t0 < 1.0, "进程都没了还等满 60 秒 = 界面卡在「启动中」"

    mgr._proc = None                       # 进程在、但永远不健康：靠停止位退出
    why = mgr._wait_ready(60, should_stop=lambda: True)
    assert "取消" in why, why

    seen = []                              # 等待期间要有心跳，别让人对着黑盒干等

    class Alive:
        returncode = None
        def poll(self): return None
    mgr._proc = Alive()                    # 进程在、服务永远不来：只走超时那条路
    mgr.log = lambda s: seen.append(s)
    why = mgr._wait_ready(2)               # 端口 1 上没人 listening，探测只会立刻失败
    assert "没等到" in why, why
    assert not seen, seen                  # 心跳是 30 秒一次，2 秒内不该刷屏
    mgr.log = print
    mgr._proc = None                       # 假进程收掉：下面那段要真去调 stop()

    done = []
    def hold_lock_and_stop():
        with mgr._lock:                    # start() 的失败路径就是这个形状
            mgr.stop(wait=0.2)
            done.append(True)
    th = threading.Thread(target=hold_lock_and_stop, daemon=True)
    th.start()
    th.join(5)
    assert done, "持锁调 stop() 死锁：锁必须是可重入的 RLock"
    print("  ✓ 引擎等待：崩了立刻退、按停止立刻退、失败路径不自锁")


def test_job_object():
    """Job Object 兜底：壳被强杀时，ComfyUI 子进程必须跟着没——「让出显存」不能只靠收尾代码。

    这里验的是同一条内核机制：作业句柄一关，作业里的进程就被杀。真机上句柄由
    pythonw.exe 持有，进程死了句柄自动关闭，效果等价于下面这行 close()。
    """
    from moss_mgr import _KillOnCloseJob
    if not _is_win():
        print("  · Job Object 是 Windows 机制，非 Windows 上跳过")
        return
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    job = _KillOnCloseJob()
    assert job.bind(child), "作业绑不上：64 位句柄被截断，或 _handle 取错了吗"
    time.sleep(0.6)
    assert child.poll() is None, "绑作业不该立刻杀掉子进程"
    job.close()
    t0 = time.time()
    while child.poll() is None and time.time() - t0 < 6:
        time.sleep(0.2)
    assert child.poll() is not None, "句柄关了子进程还活着：强杀壳照样会留孤儿占显存"
    assert not job.h, "close() 没把句柄清掉，重复启停会漏句柄"
    print("  ✓ Job Object：子进程随作业句柄关闭而死（强杀壳不再留孤儿）")


def test_occupying():
    """「让出显存」「切回千问」「手动卸载」三处都问 occupying()。

    只信 state.running 的话，「启动到一半超时、子进程还活着」这一档标记是 False，
    用户点「让出显存」代码直接跳过 stop()——显存根本没还，这条硬边界就破了。
    """
    mgr = MossManager(os.path.join(ROOT, "comfyui"), port=8876)
    mgr.state.running = False
    assert not mgr.occupying(), "什么都没起过时必须为假，否则点让出显存会空喊「已停止」"
    mgr.state.running = True
    assert mgr.occupying(), "标记说拉起过就算还占着"
    mgr.state.running = False
    mgr._proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert mgr.occupying(), "标记翻了但进程还在：这就是启动超时后点让出显存的现场"
        mgr.stop()
        assert not mgr.occupying(), "stop() 之后既不占显存也不留进程"
        assert mgr._proc is None, "stop() 没把引用清掉"
    finally:
        if mgr._proc is not None and mgr._proc.poll() is None:
            mgr._proc.kill()
    print("  ✓ occupying()：粘性标记说没跑、进程还活着时也认「还占着显存」，stop() 收得干净")


def test_warm():
    """预热：拉起进程 ≠ 权重上卡，所以要在后台补一张小图，且不能留垃圾、不能串台。

    钉住四件事：
      · 提交的是 256²/1 步/CFG1 的极小图，前缀 moss_warm（界面据此才认得出该删谁）；
      · clientId 用的是预热自己那一个——ComfyUI 按 clientId 只保留一条 /ws 连接，
        复用用户那个会把用户正在跑的进度通道挤掉（表现是进度条整批事件静默丢失）；
      · 只删 moss_warm 开头的产物，用户真正那张必须原封不动；
      · 引擎不在跑时直接返回 False，不去 POST 一个不存在的端口。
    """
    root = tempfile.mkdtemp(prefix="moss_warm_")
    out = os.path.join(root, "output")
    os.makedirs(out)
    junk = os.path.join(out, "moss_warm_00001.png")
    mine = os.path.join(out, "moss_00001.png")
    open(junk, "wb").write(b"x" * 8)
    open(mine, "wb").write(b"x" * 8)
    STATE["imgs"] = [{"filename": "moss_warm_00001.png", "subfolder": "", "type": "output"},
                     {"filename": "moss_00001.png", "subfolder": "", "type": "output"}]
    STATE["client_id"] = ""
    httpd = HTTPServer(("127.0.0.1", 0), FakeComfy)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        mgr = MossManager(root, port=port, log=lambda s: None)
        assert not mgr.warm(), "引擎没跑也必须不跑，不能把预热打到空端口上"
        mgr.state.url = "http://127.0.0.1:%d" % port
        mgr.state.running = True
        logs = []
        mgr.log = logs.append
        assert mgr.warm(), "假 ComfyUI 一路都在，预热该成功"
        g = STATE["graph"]
        ks = next(n for n in g.values() if n["class_type"] == "KSampler")["inputs"]
        lat = next(n for n in g.values() if n["class_type"] == "EmptyFlux2LatentImage")["inputs"]
        save = next(n for n in g.values() if n["class_type"] == "SaveImage")["inputs"]
        assert ks["steps"] == 1 and ks["cfg"] == 1.0, "预热只负责把权重搬上卡，不该真去采样"
        assert lat["width"] == 256 and lat["height"] == 256, "预热图要小到不影响队列"
        assert save["filename_prefix"] == "moss_warm", "删垃圾全靠这个前缀"
        assert STATE["client_id"] and STATE["client_id"] != mgr._client_id, \
            "预热的 clientId 必须独立，否则会把用户那轮 /ws 挤下线"
        assert STATE["number"] == 10 ** 9, \
            "预热要排队尾：任务队列是小的先跑，用户点完启用立刻点开始时不能排在人家前面"
        assert mgr.state.loaded_model, "预热成功就要把「权重已在显存」这件事告诉界面"
        assert not os.path.exists(junk), "预热那张小图留在 comfyui/output 里就是垃圾"
        assert os.path.exists(mine), "删过了用户自己的图：前缀没起作用"
        assert any("预热完成" in x for x in logs), logs
        STATE["imgs"] = [{"filename": "moss_00001.png", "subfolder": "", "type": "output"}]
    finally:
        httpd.shutdown()
        shutil.rmtree(root, ignore_errors=True)
    print("  ✓ 预热：1 步 256²、独立 clientId、只删 moss_warm 产物、成功即报「权重已上卡」")


def test_cancel_warm():
    """真任务进来时预热要让路：还排在队里的删掉，正在跑的那条才允许打断。

    /interrupt 打的是 ComfyUI 当前正在跑的任务，认错对象就等于把用户那一轮掐了——
    所以「跑的不是预热」这一支必须钉住：既不许删也不许中断。
    """
    httpd = HTTPServer(("127.0.0.1", 0), FakeComfy)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        mgr = MossManager(os.path.join(ROOT, "comfyui"), port=port, log=lambda s: None)
        mgr.state.url = "http://127.0.0.1:%d" % port
        item = lambda pid: [1, pid, {}, [], {}]

        STATE.update(order=[], queue_body=None, pending_q=[item("fake-1")], running_q=[])
        mgr._warm_pid = "fake-1"
        mgr._warm_gone.clear()
        mgr.cancel_warm()
        assert STATE["queue_body"] == {"delete": ["fake-1"]}, STATE["queue_body"]
        assert "interrupt" not in STATE["order"], "还在排队就中断，会顺手掐掉别人的任务"
        assert mgr._warm_pid is None and mgr._warm_gone.is_set(), "预热线程得知道自己该收工"

        STATE.update(order=[], queue_body=None, pending_q=[], running_q=[item("fake-1")])
        mgr._warm_pid = "fake-1"
        mgr.cancel_warm()
        assert STATE["queue_body"] is None, "正在跑的任务删不掉，别再发没用的删除请求"
        assert "interrupt" in STATE["order"], "预热正占着 GPU，不打断它用户就得干等"

        STATE.update(order=[], queue_body=None, pending_q=[], running_q=[item("user-9")])
        mgr._warm_pid = "fake-1"
        mgr.cancel_warm()
        assert STATE["order"] == [], "跑的是用户那一轮：一个请求都不许发"
        assert mgr._warm_pid is None and mgr._warm_gone.is_set()

        STATE.update(order=[], pending_q=[], running_q=[])
        mgr._warm_pid = None
        mgr.cancel_warm()
        assert STATE["order"] == [], "没有预热在跑就该什么都不做"
    finally:
        STATE.update(running_q=[], pending_q=[], queue_body=None, order=[])
        httpd.shutdown()
    print("  ✓ 撤预热：排队中删任务、跑着才中断、跑的是用户那轮就一个请求都不发")


def test_extra_args_guard():
    """config.json 里一句 --listen 0.0.0.0 就能把无鉴权的内嵌 ComfyUI 推到局域网——必须拒启。"""
    ok_mgr = MossManager(os.path.join(ROOT, "comfyui"), port=8876,
                         extra_args=["--cache-lru", "256", "  "])
    assert ok_mgr._safe_extra() == ["--cache-lru", "256"], ok_mgr._safe_extra()
    for bad in (["--listen", "0.0.0.0"], ["--port", "9000"], ["--host=0.0.0.0"],
                ["--listen:0.0.0.0"]):
        mgr = MossManager(os.path.join(ROOT, "comfyui"), port=8876, extra_args=bad)
        try:
            mgr._safe_extra()
            raise AssertionError("该拒绝却没拒绝：%s" % bad)
        except ComfyError as e:
            assert "监听地址" in str(e), e
    print("  ✓ 附加参数守卫：改监听地址/端口的直接拒启，其余照常放行")


def test_log_segment():
    """报错只许引用「本轮启动」那一段日志：跨轮的旧崩溃会被当成这一轮的根因端给人。

    真踩过的现场：换完 CUDA 轮子那一轮只是首次初始化慢，界面却报
    「AssertionError：Torch not compiled with CUDA enabled」——那是上一轮留下的尾巴。
    """
    root = tempfile.mkdtemp(prefix="moss_selftest_seg_")
    try:
        mgr = MossManager(os.path.join(root, "cx", "comfyui"), port=1)
        os.makedirs(os.path.dirname(mgr.log_path))
        with open(mgr.log_path, "w", encoding="utf-8") as f:
            f.write("AssertionError: Torch not compiled with CUDA enabled\n")
        mark = os.path.getsize(mgr.log_path)
        with open(mgr.log_path, "a", encoding="utf-8") as f:
            f.write("\n===== ComfyUI 启动 =====\n[INFO] Using pytorch attention\n")
        assert "Torch not compiled" in "".join(mgr._tail_log(20)), "没切段时本该看到上一轮"
        mgr._log_mark = mark
        assert mgr._tail_log(20) == ["===== ComfyUI 启动 =====",
                                     "[INFO] Using pytorch attention"], mgr._tail_log(20)
        assert mgr._fail_reason() == "", mgr._fail_reason()   # 本轮才两行 = 还在起步，别乱指根因
        with open(mgr.log_path, "a", encoding="utf-8") as f:
            f.write("Traceback (most recent call last):\nValueError: unknown node MossImage\n")
        assert "ValueError" in mgr._fail_reason(), mgr._fail_reason()   # 本轮真报错还是要报
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("  ✓ 报错只引用本轮日志：旧崩溃不会被当成这一轮的根因，起步阶段也不乱指")


def _api_server():
    """开一台不接显卡、不接 uvicorn 的 ApiServer：只验提交/淘汰这段纯逻辑。

    这台开发机的 .venv 没装 uvicorn 和 python-multipart（都是「只影响 API 服务」的可选项），
    而 FastAPI 在定义 Form/File 路由时就要 import 它。这里根本不解析表单，
    所以把这两个模块挂成假的一路走通，验的是上限与淘汰本身。
    """
    import types

    sys.modules.setdefault("uvicorn", types.SimpleNamespace(Config=object, Server=object))
    if "multipart" not in sys.modules:
        mp = types.ModuleType("multipart")
        mp.__version__ = "0.0-mock"
        inner = types.ModuleType("multipart.multipart")
        inner.parse_options_header = lambda *a, **k: ("", {})
        mp.multipart = inner
        sys.modules["multipart"] = mp
        sys.modules["multipart.multipart"] = inner
    import api_server as ap

    class Stub:
        cfg = {"api": {"token": "t"}, "console": {"output_dir": "outputs"}}
        st = {}

        def _log(self, *a):
            pass

        def abs_path(self, p):
            return os.path.join(ROOT, p)

        def _claim(self, kind):
            return False

    srv = ap.ApiServer(Stub())
    srv._stop.set()          # worker 一进门就退：这些任务不该真去抢显存
    return srv, ap


def test_upload_caps():
    """参考图上限要拦在「流」上：收到一半就断，绝不先把整张收进内存。"""
    import asyncio

    srv, ap = _api_server()

    class Body:
        def __init__(self, data):
            self.left = data

        async def read(self, n):
            buf, self.left = self.left[:n], self.left[n:]
            return buf

    d = tempfile.mkdtemp(prefix="moss_selftest_up_")
    try:
        p = os.path.join(d, "1.png")
        n = asyncio.run(ap._drain_upload(Body(b"x" * 900), p, 1000, 5000, "第 1 张"))
        assert n == 900 and os.path.getsize(p) == 900, n

        # 单张超限：抛错，且盘上落下的只有被接受的前缀（没写超）
        try:
            asyncio.run(ap._drain_upload(Body(b"y" * 2500), p, 1000, 5000, "第 2 张"))
            raise AssertionError("该拦却没拦：单张 2500 > 上限 1000")
        except ap._TooBig as e:
            assert "第 2 张" in str(e) and "上限" in str(e), e
        assert os.path.getsize(p) <= 1000, "超上限的字节已经落盘了，说明是事后才判"

        # 合计预算：第一张花了 900，第二张只剩 100，就得断
        p2 = os.path.join(d, "2.png")
        try:
            asyncio.run(ap._drain_upload(Body(b"z" * 400), p2, 1000, 100, "第 3 张"))
            raise AssertionError("该拦却没拦：合计预算只剩 100")
        except ap._TooBig as e:
            assert "合计" in str(e), e
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("  ✓ 上传上限：分块落盘、超限即断、盘上不会留下超额的字节")


def test_job_gc():
    """任务单淘汰：只丢收尾的、连带删参考图目录、结果图引用一起没；排队的不能动。"""
    srv, ap = _api_server()
    old_jobs, old_queue = ap.MAX_JOBS, ap.MAX_QUEUED
    ap.MAX_JOBS, ap.MAX_QUEUED = 4, 100
    d = tempfile.mkdtemp(prefix="moss_selftest_gc_")
    try:
        refs = [os.path.join(d, "api_refs", "t%d" % i) for i in range(6)]
        for r in refs:
            os.makedirs(r)
            open(os.path.join(r, "1.png"), "wb").close()
        jobs = [srv._submit({"prompt": "p%d" % i}, "test") for i in range(6)]
        for i, j in enumerate(jobs):
            j["refs"] = refs[i]
        assert len(srv.jobs) == 6, len(srv.jobs)          # 全在排队：一个都不许淘汰
        assert os.path.isdir(refs[0])

        for j in jobs[:4]:                               # 前四张收尾，触发上限
            iid = "img" + j["id"]
            srv.files[iid] = os.path.join(d, "out.png")
            j["images"].append({"id": iid, "name": "out.png", "url": "/v1/images/" + iid})
            j["status"] = "done"
        srv._submit({"prompt": "more"}, "test")           # 第 7 投：该挤掉最老的
        assert jobs[0]["id"] not in srv.jobs, "超限没淘汰"
        assert not os.path.isdir(refs[0]), "任务没了，参考图目录还留在盘上"
        assert not any(j["id"] in srv.jobs for j in jobs[:3]), srv.jobs.keys()
        assert all("img" + j["id"] not in srv.files for j in jobs[:3]), srv.files.keys()
        for j in jobs[3:]:                                # 还没轮到淘汰的必须原封不动
            assert j["id"] in srv.jobs, j["id"]
        assert os.path.isdir(refs[4]), refs[4]

        # 排队满了：宁可当场 429，也不让远端把这台机器排成看不见的长队
        import fastapi

        ap.MAX_QUEUED = 5
        try:
            for _ in range(200):
                srv._submit({"prompt": "flood"}, "test")
            raise AssertionError("队列已满却还在收")
        except fastapi.HTTPException as e:
            assert e.status_code == 429, e.status_code
    finally:
        ap.MAX_JOBS, ap.MAX_QUEUED = old_jobs, old_queue
        shutil.rmtree(d, ignore_errors=True)
    print("  ✓ 任务单淘汰：满了挤掉最老的、连带清参考图目录、排队的绝不丢、投爆回 429")


def test_nav_migration():
    """导航换代：v2 那份带分组、还单列着概览/透明/工坊/API 的老配置，
    要自动重排成 v6 的 7 页两组（出图 / 系统）、Moss 并进生图页、词库也并进生图页、
    标签名统一两字，且第二次启动不许再动它。

    换机/升级后用户只点一次「启动」，界面结构就得跟代码走；他改过的标签名是唯一
    该留下的东西——所以这一段既验重排，也验「幂等」和「退役页不复活」。
    """
    import app as webapp
    d = tempfile.mkdtemp(prefix="moss_nav_")
    path = os.path.join(d, "config.json")
    old_path = webapp.CFG_PATH
    try:
        v2 = copy.deepcopy(webapp.DEFAULT_CFG)
        v2.update({"nav_ver": 2, "last_tab": "t_ov", "layout": "flat",
                   "rgba": {"prompt": "旧页留下的参数"}})
        v2["nav"] = [
            {"id": "t_ov", "type": "tab", "name": "概览", "icon": "home", "page": "overview"},
            {"id": "g_qwen", "type": "group", "name": "千问生图", "icon": "flower", "children": [
                {"id": "t_gen", "type": "tab", "name": "我的出图页", "icon": "flower", "page": "t2i"},
                {"id": "t_edit", "type": "tab", "name": "图像编辑", "icon": "wand", "page": "edit"},
                {"id": "t_rgba", "type": "tab", "name": "透明素材", "icon": "layers", "page": "rgba"},
                {"id": "t_pe", "type": "tab", "name": "提示词工坊", "icon": "book", "page": "pe"}]},
            {"id": "t_api", "type": "tab", "name": "API 服务", "icon": "globe", "page": "api"}]

        def launch(cfg_on_disk):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg_on_disk, f, ensure_ascii=False)
            # 真跑一遍 __init__（不建窗口）：换代是在构造头几行里回写盘的，
            # 拿 __new__ 造个假对象就把「锁还没建就先存盘」这类顺序错误盖住了
            return webapp.App().cfg

        def flat(cfg):
            """摊平成 page -> name，顺便看看分组结构"""
            out = []

            def walk(nodes, depth):
                for n in nodes:
                    if n.get("type") == "tab":
                        out.append((depth, n["page"], n["name"]))
                    walk(n.get("children") or [], depth + 1)
            walk(cfg["nav"], 0)
            return out

        webapp.CFG_PATH = path
        c1 = launch(v2)
        rows = flat(c1)
        pages = [p for _, p, _ in rows]
        assert c1["nav_ver"] == webapp.NAV_VER, c1["nav_ver"]
        assert sorted(pages) == sorted(["t2i", "edit", "inpaint",
                                         "gallery", "models", "logs", "settings"]), pages
        assert dict((p, n) for _, p, n in rows)["t2i"] == "我的出图页", rows
        # 「图像编辑」是历代默认名之一＝用户没改过，换成 v4 的统一两字名
        assert dict((p, n) for _, p, n in rows)["edit"] == "编辑", rows
        assert c1["last_tab"] == webapp.DEFAULT_CFG["last_tab"], c1["last_tab"]  # t_ov 没了要回落
        assert c1["layout"] == "tree", c1["layout"]
        assert "rgba" not in c1, "老的 rgba 配置块该清掉"
        # v5 把分组收回来、v6 把词库收进生图页：七页全在「出图 / 系统」两组底下，顶层只剩分组本身
        groups = [n["name"] for n in c1["nav"] if n.get("type") == "group"]
        assert groups == ["出图", "系统"], groups
        assert all(d0 == 1 for d0, _, _ in rows), rows
        assert pages[:3] == ["t2i", "edit", "inpaint"], pages
        assert pages[3:] == ["gallery", "models", "logs", "settings"], pages
        # 重排完立刻落盘：下次开机不该再走一遍换代
        on_disk = json.load(open(path, encoding="utf-8"))
        assert on_disk["nav_ver"] == webapp.NAV_VER, on_disk.get("nav_ver")

        c2 = launch(on_disk)                        # 第二次启动：一模一样
        assert flat(c2) == rows, "换代不能每次开机都来一遍"
        # v4 那份「平铺无分组」的配置升上来：页还在、用户改过的名还在，分组按新默认表补回来
        v4 = copy.deepcopy(on_disk)
        v4["nav_ver"], v4["layout"] = 4, "flat"
        v4["nav"] = [n for row in v4["nav"] for n in
                     (row.get("children") or []) if n.get("type") == "tab"]
        c5 = launch(v4)
        rows5 = flat(c5)
        assert [n.get("type") for n in c5["nav"]] == ["group", "group"], c5["nav"]
        assert c5["layout"] == "tree", c5["layout"]
        assert dict((p, n) for _, p, n in rows5)["t2i"] == "我的出图页", rows5
        assert len(rows5) == 7, rows5
        # 用户手抖把退役页塞回来（或从旧机器拷了份配置）：入口留着只会点出空白页
        dirty = copy.deepcopy(on_disk)
        dirty["nav"].insert(0, {"id": "t_ov", "type": "tab", "name": "概览",
                                "icon": "home", "page": "overview"})
        c3 = launch(dirty)
        assert "overview" not in [p for _, p, _ in flat(c3)], flat(c3)
        assert len([p for _, p, _ in flat(c3)]) == 7, flat(c3)
        print("  ✓ 导航换代：v2/v4 老配置都重排成两组 7 页、改过的名字留着、二次启动幂等、退役页不复活")
    finally:
        webapp.CFG_PATH = old_path
        shutil.rmtree(d, ignore_errors=True)


def test_input_image_modes():
    """四个 mode 的「要不要喂输入图」钉死：透明档并进文生图后，rgba 就算被带上参考图
    也不能掉进 edit 那条流水线——它靠提示词出原生 alpha，输入图是另一回事。"""
    import app as webapp
    from PIL import Image
    d = tempfile.mkdtemp(prefix="moss_modes_")
    old_path = webapp.CFG_PATH
    try:
        webapp.CFG_PATH = os.path.join(d, "config.json")
        a = webapp.App()
        src = os.path.join(d, "in.png")
        Image.new("RGB", (64, 48), (10, 20, 30)).save(src)
        for mode in ("gen", "rgba"):
            assert a._build_input_image({"mode": mode, "images": [src]}) is None, mode
        got = a._build_input_image({"mode": "edit", "images": [src]})
        assert isinstance(got, list) and got[0].size == (64, 48), got
        inp = a._build_input_image({"mode": "inpaint", "images": [src], "mask": None})
        assert not isinstance(inp, list) and inp.mode == "RGBA", inp
        print("  ✓ 输入图契约：gen/rgba 一律不喂图（rgba 带上参考图也不串档）、edit 给列表、inpaint 给带 alpha 的原图")
    finally:
        webapp.CFG_PATH = old_path
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    print("Moss 自测（无 GPU）：")
    test_templates()
    test_generate_against_fake()
    test_ws_order_and_loss()
    test_wait_ready()
    test_log_segment()
    test_job_object()
    test_occupying()
    test_warm()
    test_cancel_warm()
    test_extra_args_guard()
    test_env_moss()
    test_comfyui_torch_index()
    test_comfyui_moss_nodes()
    test_upload_caps()
    test_job_gc()
    test_nav_migration()
    test_input_image_modes()
    print("全部通过 ✅")
