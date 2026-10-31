# -*- coding: utf-8 -*-
"""ui_cdp.py —— 真开一次桌面窗口，再用 WebView2 的调试端口当「手」去点界面。

    .venv\\Scripts\\python.exe scripts\\ui_cdp.py moss

和 ui_drive.py 的分工：那个直接在 Python 侧调 js_api 同名方法（快、无需窗口），
这个把 `启动.bat` 那条真链路跑起来（pythonw + pywebview + WebView2），然后用 CDP
往页面里注 JS：走的是 `MIC.nav.goto()` → 按钮 onclick → `MIC.api.*()` 桥 → 轮询渲染
这一整条前端路，界面上显示什么就验什么。用户能点到的东西，这里都能点。

前提：WebView2 认 WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS 这个环境变量，
喂一句 --remote-debugging-port=9222 就会在本地开一个 CDP 端点（只监听 127.0.0.1）。
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

CDP = "http://127.0.0.1:9222"


def http_json(path, timeout=2.0):
    with urllib.request.urlopen(CDP + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_page(timeout=60.0):
    """等界面出来：CDP 的 page 目标 + 页面里 MIC 已就绪。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            targets = [t for t in http_json("/json/list")
                       if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
        except Exception:
            targets = []
        if targets:
            return targets[0]
        time.sleep(0.5)
    raise RuntimeError("没等到 WebView2 的调试目标（界面可能没起来）")


class Page:
    """最小 CDP 客户端：只用到 Runtime.evaluate。"""

    def __init__(self, target):
        import websocket
        self.ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=30.0)
        self._id = 0

    def js(self, expr, await_promise=False, timeout=120.0):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate", "params": {
            "expression": expr, "returnByValue": True, "awaitPromise": await_promise}}))
        self.ws.settimeout(timeout)
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") != mid:
                continue                      # 事件的单帧：忽略，只等自己这次回包
            res = msg.get("result", {})
            if "exceptionDetails" in res:
                raise RuntimeError("页面里抛错：%s"
                                   % json.dumps(res["exceptionDetails"], ensure_ascii=False)[:400])
            return res.get("result", {}).get("value")

    def click(self, needle, text=None):
        """点真按钮（等价于用户用鼠标点）。点之前先清零笔记：点完之后读到的
        报错/提示就只属于这一下，不背上一颗按钮的旧账。

        参数一律用 JSON.stringify 注进 JS：档位那颗按钮的 onclick 本身就带单引号
        （MIC.moss.setTier('yield')），拼字符串会把 JS 的引号怼断。"""
        self.js("window.__errs=[];window.__toasts=[];")
        js = ("(function(n,t){var el=document.querySelector('[onclick*='+JSON.stringify(n)+']');"
              "if(!el&&t){el=Array.prototype.slice.call("
              "document.querySelectorAll('button,.btn,[onclick]')).find("
              "function(x){return (x.textContent||'').trim().indexOf(t)>=0;});}"
              "if(!el)return 'NO-BUTTON:'+n;el.click();return 'clicked';})")
        return self.js("%s(%s,%s)" % (js, json.dumps(needle), json.dumps(text or "")))

    def inventory(self):
        """页面上所有可点的东西：onclick 片段 ≤ 可见文字。"""
        return self.js("Array.prototype.slice.call(document.querySelectorAll('[onclick]'))"
                       ".map(function(e){return (e.getAttribute('onclick')||'').slice(0,46)"
                       "+' ≤ '+(e.textContent||'').trim().replace(/\\s+/g,' ').slice(0,22);}).join('\\n')")

    def type(self, key, value):
        """往真控件里打字 + 派发 change：走的是 form.js 的事件委托，和键盘一模一样。
        以前这里想调 MIC.form.set()——那个方法不存在，`&&` 短路后静默跳过，
        于是整轮跑的是配置里的老提示词，测试和用户的输入根本不是同一件事。"""
        js = ("(function(){var el=document.querySelector('#view [data-k=\"%s\"]');"
              "if(!el)return 'NO-INPUT:%s';el.value=%s;"
              "el.dispatchEvent(new Event('change',{bubbles:true}));return el.value;})()"
              % (key, key, json.dumps(str(value))))
        return self.js(js)

    def st(self):
        return self.js("JSON.parse(JSON.stringify(MIC.s.st))")

    def arm(self):
        """埋两个钩子：按钮 onclick 里抛的错（不会传到我们的 evaluate 返回值上）和
        MIC.toast 弹的文案。用户「点了没反应」九成落在这两处，不抓就只能靠猜。"""
        return self.js("(function(){window.__errs=[];window.__toasts=[];"
                       "window.onerror=function(m,s,l,c){window.__errs.push(m+' @'+l+':'+c);};"
                       "var t=MIC.toast;MIC.toast=function(x){window.__toasts.push(String(x));"
                       "return t.apply(MIC,arguments);};return 'armed';})()")

    def notes(self):
        """取出并清空这一轮攒下的报错/提示。"""
        v = self.js("(function(){var r={err:window.__errs||[],toast:window.__toasts||[]};"
                    "window.__errs=[];window.__toasts=[];return JSON.stringify(r);})()")
        try:
            return json.loads(v or "{}")
        except Exception:
            return {"err": [str(v)], "toast": []}

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def main():
    scenario = (sys.argv[1] if len(sys.argv) > 1 else "moss").lower()
    pyw = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")
    env = dict(os.environ, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--remote-debugging-port=9222")
    backup = None
    if scenario == "guard":
        backup = arm_bad_extra()
        print("· 已往 config.json 塞进越界的 extra_args（跑完还原）", flush=True)
    print("· 用启动.bat 那条真链路开窗口：%s webui\\app.py" % pyw, flush=True)
    proc = subprocess.Popen([pyw, os.path.join(ROOT, "webui", "app.py")], cwd=ROOT, env=env)
    fail = []
    page = None
    try:
        target = wait_page()
        print("· 界面已连上：%s" % (target.get("title") or target.get("url")), flush=True)
        page = Page(target)
        print("· 页面标题：%s · MIC 已就绪=%s"
              % (page.js("document.title"), page.js("typeof MIC!=='undefined'")), flush=True)
        page.arm()
        if scenario in ("moss", "repeat", "race", "dom", "peek", "tier", "orphan", "direct", "guard"):
            page.js("MIC.nav.goto('moss')")
            time.sleep(1.2)
        if scenario == "moss":
            fail = run_moss(page)
        elif scenario == "repeat":
            fail = run_repeat(page)
        elif scenario == "race":
            fail = run_race(page)
        elif scenario == "tier":
            fail = run_tier(page)
        elif scenario == "orphan":
            fail = run_orphan(page, proc)
        elif scenario == "direct":
            fail = run_direct(page)
        elif scenario == "guard":
            fail = run_guard(page)
        elif scenario == "dom":
            print("· 引擎灯：%s" % page.js(
                "JSON.stringify({cfg:MIC.s.cfg.engine,st:MIC.s.st.engine,"
                "on:MIC.s.st.comfyui_on,page:MIC.nav.pageOf()})"), flush=True)
            print("· 页面容器：<div id=view> 长度 %s"
                  % page.js("String((MIC.$('view')||{}).innerHTML.length)"), flush=True)
            print("· 这一页可点的按钮：\n%s" % page.inventory(), flush=True)
        elif scenario == "peek":
            print(page.js(sys.argv[2] if len(sys.argv) > 2 else "MIC.$('view').innerHTML.slice(0,800)"),
                  flush=True)
        else:
            raise SystemExit("未知场景：%s" % scenario)
    finally:
        if page:
            page.close()
        if proc.poll() is None:
            print("· 关窗口（等价于点右上角 ×，走 on_closing 收尾）", flush=True)
            proc.terminate()
            for _ in range(20):
                if proc.poll() is not None:
                    break
                time.sleep(0.5)
        time.sleep(2.0)
        left = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe"],
                              capture_output=True, text=True).stdout
        print("· 收尾后 comfyui 残留：", "有！" if "comfyui" in left.lower() else "无（按端口再确认一遍）")
        busy = ""
        try:
            urllib.request.urlopen("http://127.0.0.1:8876/system_stats", timeout=2).read()
            busy = "8876 还在应答 = 有孤儿"
        except Exception:
            busy = "8876 无应答 = 干净"
        print("· " + busy, flush=True)
        if backup:
            with open(backup[0], "wb") as f:
                f.write(backup[1])
            print("· config.json 已还原（越界那句 extra_args 不留在机器上）", flush=True)
    print("\n" + ("UI CDP FAIL %d" % len(fail) if fail else "UI CDP OK ✅"))
    for m in fail:
        print("  ✗ " + m)
    return 1 if fail else 0


def check(fail, ok, msg):
    print(("  ✓ " if ok else "  ✗ ") + msg, flush=True)
    if not ok:
        fail.append(msg)


def clicked(fail, page, needle, label, settle=1.5, text=None):
    """真点一下并把这一跳的现场（报错/提示）摊在屏幕上：静默失败要有声音。
    等 settle 秒再收笔记，因为按钮里那些 api.*() 调用是异步的，提示在回调里才弹。"""
    r = page.click(needle, text=text)
    time.sleep(settle)
    n = page.notes()
    print("· 点「%s」（%s）：%s 报错=%s 提示=%s"
          % (label, needle, r, n.get("err"), n.get("toast")), flush=True)
    check(fail, r == "clicked", "界面上找到了「%s」这颗按钮" % label)
    check(fail, not (n.get("err") or []), "点「%s」没有把 JS 跑崩" % label)
    return r, n


def wait_render(page, needle, timeout=20.0):
    """等这一页真渲染出来：mount() 里那句 mossStatus() 是异步的，抢在它回来之前查 DOM 会看到空页。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if needle in (page.js("MIC.$('view').innerHTML") or ""):
            return True
        time.sleep(0.4)
    return False


def run_moss(page):
    fail = []
    print("[场景] 界面上真点：切去千问 → 回 Moss 页 → 点「切到 Moss 生图」→ 填参数 → 点「开始」→ 看成图")
    check(fail, wait_render(page, "MIC.moss."), "Moss 页渲染出来了（异步体检回来之后才有内容）")

    # 先把引擎切走，好把「切到 Moss 生图」那颗按钮逼出来：用户报的就是点它没反应。
    # 这里刻意不手动调 MIC.render()：真用户的路径就是「后端状态变了 → 界面自己该重画」，
    # 上一版靠脚本补一刀才找到按钮，正好把「页面留着一屏旧按钮」这个真 bug 盖住了。
    page.js("MIC.api.setEngine('qwen')")
    st = wait_for(page, lambda s: not s.get("running") and s.get("engine") != "moss",
                  60, "等切到千问")
    check(fail, not (page.st() or {}).get("comfyui_on"), "切走后 ComfyUI 已停")
    check(fail, wait_render(page, "MIC.moss.enable"),
          "引擎未启用时页面给的是「切到 Moss 生图」按钮（不是空壳）")

    # 「切到 Moss 生图」这一下就是用户报的那一刀：以前点完什么都没发生
    clicked(fail, page, "MIC.moss.enable", "切到 Moss 生图")
    st = wait_for(page, lambda s: s.get("comfyui_on") or "失败" in (s.get("status") or ""),
                  300, "等 ComfyUI 灯亮")
    check(fail, bool(st.get("comfyui_on")), "界面上引擎灯亮了：comfyui_on=%s url=%s"
          % (st.get("comfyui_on"), st.get("comfyui_url")))
    check(fail, "MIC.moss.enable" not in (page.js("MIC.$('view').innerHTML") or ""),
          "灯亮后「切到 Moss 生图」这颗按钮自己消失（页面状态跟引擎对得上）")

    # 提示词得真打进输入框：config 里那条是上次的，界面上是从表单提交的
    for k, v in (("moss.prompt", "a lighthouse on a cliff at dusk"),
                 ("moss.size", "512x512"), ("moss.count", "1"), ("moss.seed", "-1")):
        got = page.type(k, v)
        check(fail, got == str(v), "在输入框里填 %s=%s（回读 %s）" % (k, v, got))
    clicked(fail, page, "MIC.moss.start", "开始出图")
    # 连敲四个框 = 四次并发存配置。以前这里必刷一屏「配置没存上」（.tmp 改名撞车），
    # 用户看到的是每次改参数都弹警告、重启后参数全丢。
    nsave = page.js("(MIC.s.logs||[]).filter(function(l){return "
                    "/配置没存上/.test(l.text||'');}).length")
    check(fail, not int(nsave or 0), "改完参数没有把配置写丢（日志里 0 条「配置没存上」）")
    st = wait_for(page, lambda s: not s.get("running"), 400, "等任务收尾")
    print("· 收尾状态：%s" % json.dumps({k: st.get(k) for k in
                                    ("status", "done", "total", "last_image", "last_sec")},
                                    ensure_ascii=False), flush=True)
    check(fail, str(st.get("status") or "").startswith("✅"), "界面状态：「%s」" % st.get("status"))
    img = st.get("last_image") or ""
    check(fail, bool(img) and os.path.isfile(img), "成图：%s" % img)
    check(fail, (st.get("done") or 0) > 0, "进度条动过：%s/%s" % (st.get("done"), st.get("total")))
    logs = page.js("(MIC.s.logs||[]).slice(-8).map(function(l){return l.t+'  '+l.text;}).join('\\n')")
    print("· 界面日志尾：%s" % logs, flush=True)
    # 出的必须是刚填的那一组参数：不然「界面里改了、跑的还是配置里的老值」永远发现不了
    check(fail, "512x512" in str(logs), "按输入框里改的尺寸出图（日志里是 512x512）")
    # 预热的两条硬账：权重灯要亮（这才叫「日常档 ≠ 让出显存档」看得见），
    # 而且那张 256² 小图不许留在 comfyui/output 里当垃圾。
    check(fail, bool((page.st() or {}).get("comfyui_loaded")),
          "界面报「权重已常驻」：comfyui_loaded=%s" % (page.st() or {}).get("comfyui_loaded"))
    left = [n for n in os.listdir(os.path.join(ROOT, "comfyui", "output"))
            if n.startswith("moss_warm")]
    check(fail, not left, "预热产物删净（comfyui/output 里剩 %s）" % (left or "无"))
    return fail


def run_repeat(page):
    """用户报的那条：同一页连点「开始」重复生图，概率失败、预览停在上一张。
    每轮都走真按钮 + 真轮询，逐轮对账：状态 ✅、新图真的换了文件、种子随机时两张不一样。"""
    fail = []
    print("[场景] 重复生图：同一页真点 5 轮「开始」，每轮都要出新图")
    check(fail, wait_render(page, "MIC.moss."), "Moss 页渲染出来了")
    for k, v in (("moss.prompt", "a red apple on a wooden table"),
                 ("moss.size", "512x512"), ("moss.count", "1"), ("moss.seed", "-1")):
        page.type(k, v)
    seen = []
    for i in range(5):
        clicked(fail, page, "MIC.moss.start", "第 %d 轮开始" % (i + 1))
        st = wait_for(page, lambda s: not s.get("running"), 300, "等第 %d 轮收尾" % (i + 1))
        img = str(st.get("last_image") or "")
        ok = str(st.get("status") or "").startswith("✅") and os.path.isfile(img)
        print("   · 第 %d 轮：%s · %s" % (i + 1, st.get("status"), os.path.basename(img)), flush=True)
        check(fail, ok, "第 %d 轮出图（%s）" % (i + 1, st.get("status")))
        if img:
            if seen:
                check(fail, img != seen[-1], "第 %d 轮是**新文件**（上一轮 %s）"
                      % (i + 1, os.path.basename(seen[-1])))
            seen.append(img)
    if len(seen) >= 2:
        import hashlib
        def _sha(p):
            with open(p, "rb") as f:
                return hashlib.sha1(f.read()).hexdigest()
        check(fail, _sha(seen[0]) != _sha(seen[-1]),
              "随机种子下第一轮与最后一轮不是同一张图（%s vs %s）"
              % (os.path.basename(seen[0]), os.path.basename(seen[-1])))
    logs = page.js("(MIC.s.logs||[]).slice(-10).map(function(l){return l.t+'  '+l.text;}).join('\\n')")
    print("· 界面日志尾：%s" % logs, flush=True)
    return fail


def run_race(page):
    """手快连点两下「开始」：第二下必须被拦在界面这层（不能弹失败提示，也不能起第二个任务）。"""
    fail = []
    print("[场景] 连点两下「开始」：界面自己要先占位，不许把第二下变成失败提示")
    check(fail, wait_render(page, "MIC.moss."), "Moss 页渲染出来了")
    for k, v in (("moss.prompt", "a red apple on a wooden table"),
                 ("moss.size", "512x512"), ("moss.count", "1"), ("moss.seed", "-1")):
        page.type(k, v)
    r1 = page.click("MIC.moss.start")
    time.sleep(0.05)
    r2 = page.click("MIC.moss.start")
    time.sleep(1.2)
    n = page.notes()
    print("· 两下点击：%s / %s · 报错=%s 提示=%s" % (r1, r2, n.get("err"), n.get("toast")), flush=True)
    check(fail, r1 == "clicked", "第一下点到「开始」")
    check(fail, r2 == "clicked" or str(r2).startswith("NO-BUTTON"),
          "第二下要么被界面占位吃掉（已画成停止按钮），要么按下去也起不了第二个任务")
    check(fail, not [t for t in (n.get("toast") or [])
                     if "在跑" in t or "未启动" in t], "第二下没有变成失败提示")
    st = wait_for(page, lambda s: not s.get("running"), 300, "等这一轮收尾")
    check(fail, str(st.get("status") or "").startswith("✅"), "最终状态：%s" % st.get("status"))
    runs = page.js("(MIC.s.logs||[]).filter(function(l){"
                   "return /开始 Moss/.test(l.text||'');}).length")
    check(fail, int(runs or 0) == 1, "只起了一轮（日志里 %s 条「开始 Moss」）" % runs)
    return fail


def wait_for(page, pred, timeout, label):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        st = page.st() or {}
        key = (st.get("running"), st.get("status"), st.get("done"), st.get("comfyui_on"))
        if key != last:
            # 顺带把界面日志的最后一行摊出来：卡住的时候这一行就是现场
            try:
                tail = page.js("(MIC.s.logs||[]).slice(-1)"
                               ".map(function(l){return l.text}).join('')||''")
            except Exception:
                tail = ""
            print("   · %s｜running=%s 去噪 %s/%s comfyui_on=%s（%.0fs）%s"
                  % (st.get("status"), st.get("running"), st.get("done"),
                     st.get("total"), st.get("comfyui_on"), time.time() - t0,
                     ("← " + str(tail)[:90]) if tail else ""), flush=True)
            last = key
        if pred(st):
            return st
        time.sleep(0.8)
    raise RuntimeError("%s：等到 %d 秒还没成" % (label, timeout))


def vram_used():
    """整卡占用（MiB）。只读总量、不读进程列表：这台机器上 --query-compute-apps
    会吐一堆 [N/A] 的桌面进程，拿它当证据会误判（实测踩过这个坑）。"""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                             "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout
        vals = [int(x) for x in out.replace(",", " ").split()]
        return max(vals) if vals else -1
    except Exception:
        return -1


def port_pid(port=8876):
    """谁在监听 8876；无应答返回 0。"""
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return 0
    for line in out.splitlines():
        if (":%d " % port) in line and "LISTENING" in line:
            try:
                return int(line.split()[-1])
            except Exception:
                return 0
    return 0


def moss_ready(page, fail):
    """用户进 Moss 页最容易走的一条路：先把引擎切走，再点「切到 Moss 生图」回来。"""
    page.js("MIC.api.setEngine('qwen')")
    wait_for(page, lambda s: not s.get("running") and s.get("engine") != "moss",
             90, "等切到千问")
    clicked(fail, page, "MIC.moss.enable", "切到 Moss 生图")
    st = wait_for(page, lambda s: s.get("comfyui_on") or "失败" in (s.get("status") or ""),
                  300, "等 ComfyUI 灯亮")
    check(fail, bool(st.get("comfyui_on")), "界面上引擎灯亮了：comfyui_on=%s url=%s"
          % (st.get("comfyui_on"), st.get("comfyui_url")))
    return st


def run_tier(page):
    fail = []
    print("[场景] 档位按钮：出过图（显存吃满）→ 让出显存 → 显存真还回去 → 切回日常自动重载")
    moss_ready(page, fail)
    # 先把显存真用起来再测「让出去」：引擎刚拉起来时权重还没搬进显存，
    # 整卡只有桌面基线那 1.3 GB，这时候量降幅等于没测（第一版就是这么红的）。
    for k, v in (("moss.size", "512x512"), ("moss.count", "1")):
        page.type(k, v)
    clicked(fail, page, "MIC.moss.start", "开始出图")
    st = wait_for(page, lambda s: not s.get("running"), 400, "等这张图收尾")
    check(fail, str(st.get("status") or "").startswith("✅"), "让出显存前先在 Moss 上出了一张图")
    before = vram_used()
    print("· 出过图、让出显存前的整卡占用：%s MiB" % before, flush=True)
    clicked(fail, page, "MIC.moss.setTier('yield')", "让出显存档")
    st = wait_for(page, lambda s: not s.get("comfyui_on"), 120, "等 ComfyUI 停")
    check(fail, not st.get("comfyui_on"), "灯灭了：comfyui_on=%s" % st.get("comfyui_on"))
    time.sleep(2.0)                       # 进程退了到显存回收有一小段滞后
    after = vram_used()
    print("· 让出显存后整卡占用：%s MiB" % after, flush=True)
    check(fail, before < 0 or after < 0 or after <= before - 1000,
          "显存真的还回给外部软件：%s → %s MiB（降 %s）" % (before, after, before - after))
    clicked(fail, page, "MIC.moss.setTier('daily')", "日常质量档")
    st = wait_for(page, lambda s: s.get("comfyui_on"), 300, "等切回日常自动重载")
    check(fail, bool(st.get("comfyui_on")), "切回日常档引擎自己回来了：comfyui_on=%s"
          % st.get("comfyui_on"))
    return fail


def run_direct(page):
    """用户最省的走法：不点「切到 Moss 生图」，直接在 Moss 页点「开始出图」。
    引擎此刻还挂在千问、页面上那颗「切过去」的按钮明摆着没点亮——这时候点开始，
    后端要么把引擎补起来把图出了，要么把话说明白，绝不能不吭声。"""
    fail = []
    print("[场景] 引擎没点亮时直接点「开始出图」：要么自动把引擎拉起来，要么给出原因")
    page.js("MIC.api.setEngine('qwen')")
    wait_for(page, lambda s: not s.get("running") and s.get("engine") != "moss",
             90, "等切到千问")
    st0 = page.st() or {}
    print("· 点之前的灯：engine=%s comfyui_on=%s"
          % (st0.get("engine"), st0.get("comfyui_on")), flush=True)
    for k, v in (("moss.prompt", "a red paper boat floating on a pond"),
                 ("moss.size", "512x512"), ("moss.count", "1")):
        page.type(k, v)
    clicked(fail, page, "MIC.moss.start", "开始出图")
    st = wait_for(page, lambda s: not s.get("running"), 480, "等这一轮收尾")
    ok = str(st.get("status") or "").startswith("✅")
    bad = "失败" in (st.get("status") or "") or "❌" in (st.get("status") or "")
    print("· 收尾：%s" % json.dumps({k: st.get(k) for k in
                                ("status", "done", "total", "last_image")},
                                ensure_ascii=False), flush=True)
    check(fail, ok or bad,
          "没点亮也能要么自动起引擎出图、要么把原因说清（界面状态：「%s」）" % st.get("status"))
    if ok:
        img = st.get("last_image") or ""
        check(fail, bool(img) and os.path.isfile(img), "自动起引擎也照样成图：%s" % img)
    else:
        print("· 界面日志尾：%s" % page.js(
            "(MIC.s.logs||[]).slice(-6).map(function(l){return l.text;}).join(' / ')"), flush=True)
    return fail


def run_orphan(page, proc):
    fail = []
    print("[场景] 硬边界：任务管理器式强杀壳（taskkill /F /T，不给 on_closing 机会），"
          "ComfyUI 不能活下来占显存")
    moss_ready(page, fail)
    pid = port_pid()
    check(fail, pid > 0, "内嵌 ComfyUI 是独立进程：监听 8876 的 PID=%s" % pid)
    print("· 强杀壳：pythonw PID=%s" % proc.pid, flush=True)
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                   capture_output=True, text=True)
    try:
        proc.wait(timeout=20)
    except Exception:
        pass
    time.sleep(3.0)                       # Job Object 收口有一小段滞后
    now = port_pid()
    print("· 强杀后再看 8876：%s" % ("PID=%s" % now if now else "无应答"), flush=True)
    check(fail, not (pid and now == pid), "原 ComfyUI 进程没活下来（不留孤儿）")
    return fail


def run_guard(page):
    """越界配置必须在界面上看得见：拒启 + 说清是哪一句，而不是默默转圈或谎报就绪。"""
    fail = []
    print("[场景] 越界守卫：config.json 写了 --listen 0.0.0.0 → 点「切到 Moss 生图」应拒启并说清原因")
    clicked(fail, page, "MIC.moss.enable", "切到 Moss 生图")
    st = wait_for(page, lambda s: ("失败" in (s.get("status") or "")) or ("❌" in (s.get("status") or ""))
                  or s.get("comfyui_on"), 300, "等界面给出结论")
    check(fail, not st.get("comfyui_on"), "越界的引擎没被点亮：comfyui_on=%s" % st.get("comfyui_on"))
    check(fail, ("失败" in (st.get("status") or "")) or ("❌" in (st.get("status") or "")),
          "界面状态直接说失败：「%s」" % st.get("status"))
    logs = page.js("(MIC.s.logs||[]).slice(-6).map(function(l){return l.text}).join(' / ')")
    print("· 界面日志尾：%s" % logs, flush=True)
    check(fail, "--listen" in str(logs), "日志里点名是哪句参数越界（用户知道该改哪里）")
    check(fail, port_pid() == 0, "8876 根本没起来：确实拒了，不是起了个监听局域网的")
    return fail


def arm_bad_extra():
    """往 config.json 塞一句 --listen 0.0.0.0 —— 无鉴权的内嵌 ComfyUI 监听局域网，
    整台机器就暴露了。返回备份字节，跑完还原（这机器上不留越界配置）。"""
    path = os.path.join(ROOT, "config.json")
    with open(path, "rb") as f:
        raw = f.read()
    cfg = json.loads(raw.decode("utf-8"))
    cfg.setdefault("moss", {})["extra_args"] = ["--listen", "0.0.0.0"]
    cfg["engine"] = "qwen"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    return (path, raw)


if __name__ == "__main__":
    sys.exit(main())
