# -*- coding: utf-8 -*-
"""ui_drive.py —— 用脚本走一遍用户的点击路径（不开窗口，直接调 js_api 的那几个方法）。

    .venv\\Scripts\\python.exe scripts\\ui_drive.py moss
    .venv\\Scripts\\python.exe scripts\\ui_drive.py tier
    .venv\\Scripts\\python.exe scripts\\ui_drive.py env

前端每个按钮背后就是一句 `MIC.api.xxx()`，落到 App 上就是同名方法；界面 800ms 一次的
轮询就是 App.poll()。这里把这两件事照做一遍：点下去 → 轮询到收尾 → 看界面会显示什么。
和 shoot.py（无头浏览器 + mock 桥）互补：那个验前端渲染，这个验真引擎、真子进程、真显存。
退出码非 0 = 场景没走通，可直接当回归用。
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "webui"), os.path.join(ROOT, "engine")):
    sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app import App                                          # noqa: E402

TIMEOUT = float(os.environ.get("UI_DRIVE_TIMEOUT", "500"))


class Driver:
    def __init__(self):
        self.app = App()
        self.seq = 0
        self.fail = []

    # ---- 前端那套轮询：取新日志、看状态灯 ----
    def tick(self, quiet=False):
        r = self.app.poll(self.seq)
        self.seq = r["seq"]
        for _, ts, text in r["logs"]:
            if not quiet:
                print("   [%s] %s" % (ts, text), flush=True)
        return r["state"]

    def wait_idle(self, label, expect_done=None, timeout=None):
        """等 st.running 清空（= 界面上那条进度条停住），顺带把状态变化打出来。"""
        t0 = time.time()
        last = None
        st = self.tick()
        while st.get("running") or last is None:
            if time.time() - t0 > (timeout or TIMEOUT):
                self.fail.append("%s：等到超时（running=%s status=%s）"
                                 % (label, st.get("running"), st.get("status")))
                return st, False
            key = (st.get("status"), st.get("done"), st.get("total"), st.get("running"))
            if key != last and None not in key[:2]:
                print("   · %s｜%s %s/%s（%.0fs）"
                      % (st.get("running"), st.get("status"), st.get("done"),
                         st.get("total"), time.time() - t0), flush=True)
                last = key
            time.sleep(0.4)
            st = self.tick()
        print("   ↳ 收尾：status=%s · %.1f 秒" % (st.get("status"), time.time() - t0), flush=True)
        return st, True

    def check(self, ok, msg):
        print(("  ✓ " if ok else "  ✗ ") + msg, flush=True)
        if not ok:
            self.fail.append(msg)
        return ok

    # ---- 场景 ----
    def s_moss(self):
        print("[场景] Moss：开引擎 → 出图（用户路径：切引擎、点开始）")
        eng = str(self.app.cfg.get("engine", "qwen"))
        pid0 = self.app.moss.state.pid if self.app.moss else None
        r = self.app.set_engine("moss")
        self.check(r.get("ok"), "点「启用 Moss」→ set_engine 回 %s" % json.dumps(r, ensure_ascii=False))
        if eng == "moss":
            # 配置文件里已经是 moss（上次没关掉），这一刀验的就是「同值也要把引擎补起来」：
            # 曾经这里直接 return ok，按钮点下去什么都没发生，灯一直灭着。
            st, _ = self.wait_idle("切引擎")
            self.check(self.app.moss is not None and self.app.moss.state.pid not in (None, pid0),
                       "配置本就是 moss：再点启用也真的重新拉起了进程（pid=%s）"
                       % (self.app.moss.state.pid if self.app.moss else None))
        st, ok = self.wait_idle("等引擎就绪")
        self.check(st.get("comfyui_on"), "引擎灯：comfyui_on=%s url=%s"
                   % (st.get("comfyui_on"), st.get("comfyui_url")))
        self.check(bool(self.app.moss and self.app.moss.alive()), "MossManager.alive()")

        r = self.app.start_gen({"engine": "moss", "prompt": "a lighthouse on a cliff at dusk",
                                "negative": "watermark", "size": "512x512",
                                "quality": "fast", "count": 1, "seed": -1})
        self.check(r.get("ok"), "点「开始」→ start_gen 回 %s" % json.dumps(r, ensure_ascii=False))
        st, ok = self.wait_idle("出图")
        self.check(st.get("done") and st.get("total"), "进度条走到 %s/%s"
                   % (st.get("done"), st.get("total")))
        img = st.get("last_image")
        self.check(bool(img) and os.path.isfile(img), "成图落盘：%s" % img)
        self.check(str(st.get("status")).startswith("✅"), "界面状态文案：%s" % st.get("status"))
        return st

    def s_revive(self):
        print("[场景] 子进程被人中途杀掉：界面灯要跟着灭，下次点开始要自己复活")
        self.app.set_engine("moss")
        st, _ = self.wait_idle("拉起引擎")
        self.check(st.get("comfyui_on"), "先正常拉起：comfyui_on=%s" % st.get("comfyui_on"))
        pid = self.app.moss.state.pid
        subprocess.call(["taskkill", "/PID", str(pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
        st = self.tick()
        self.check(not st.get("comfyui_on"), "外部杀掉后灯自己灭：comfyui_on=%s" % st.get("comfyui_on"))
        r = self.app.start_gen({"engine": "moss", "prompt": "a white cup on a wooden table",
                                "negative": "", "size": "512x512", "quality": "fast",
                                "count": 1, "seed": -1})
        self.check(r.get("ok"), "再点开始 → start_gen 回 %s" % json.dumps(r, ensure_ascii=False))
        st, _ = self.wait_idle("复活并出图")
        img = st.get("last_image")
        self.check(bool(img) and os.path.isfile(img), "自动重启后仍出图：%s" % img)

    def s_tier(self):
        print("[场景] 档位：让出显存 → 切回日常")
        self.app.set_engine("moss")
        self.wait_idle("切引擎")
        r = self.app.moss_set_tier("yield")
        self.check(r.get("ok"), "切「让出显存」→ %s" % json.dumps(r, ensure_ascii=False))
        st, _ = self.wait_idle("让出显存")
        self.check(not st.get("comfyui_on"), "让出后 comfyui_on=%s" % st.get("comfyui_on"))
        r = self.app.moss_set_tier("daily")
        self.check(r.get("ok"), "切回「日常质量档」→ %s" % json.dumps(r, ensure_ascii=False))
        st, _ = self.wait_idle("重载")
        self.check(st.get("comfyui_on"), "切回后自动重载：comfyui_on=%s" % st.get("comfyui_on"))

    def s_env(self):
        print("[场景] 环境体检：Moss 那几项")
        r = self.app.env_check()
        items = [it for it in (r or {}).get("items", []) if "comfy" in str(it.get("key"))
                 or str(it.get("key")).startswith("moss:")]
        for it in items:
            print("   · %-18s %-5s %s" % (it.get("key"), it.get("state"), it.get("label")))
        self.check(items and all(it["state"] == "ok" for it in items),
                   "Moss 段全绿（%d 项）" % len(items))

    def s_qwen_switch(self):
        print("[场景] 引擎来回切：Moss → 千问 → Moss（验显存不叠、界面不冻）")
        self.app.set_engine("moss")
        self.wait_idle("moss")
        r = self.app.set_engine("qwen")
        self.check(r.get("ok"), "切回千问 → %s" % json.dumps(r, ensure_ascii=False))
        st, _ = self.wait_idle("千问")
        self.check(not st.get("comfyui_on"), "切走后 ComfyUI 已停：%s" % st.get("comfyui_on"))
        r = self.app.set_engine("moss")
        self.check(r.get("ok"), "再切回 Moss → %s" % json.dumps(r, ensure_ascii=False))
        st, _ = self.wait_idle("moss 回来")
        self.check(st.get("comfyui_on"), "回来又拉起了：%s" % st.get("comfyui_on"))


def main():
    scenario = (sys.argv[1] if len(sys.argv) > 1 else "moss").lower()
    d = Driver()
    if scenario == "tier":
        d.s_tier()
    elif scenario == "env":
        d.s_env()
    elif scenario == "switch":
        d.s_qwen_switch()
    elif scenario == "revive":
        d.s_revive()
    elif scenario == "all":
        d.s_env(), d.s_moss(), d.s_tier()
    else:
        d.s_moss()
    try:
        d.app.on_closing()        # 收尾：和关窗口一样把子进程带走，别留孤儿占显存
    except Exception as e:
        print("（收尾异常，不影响结论：%s）" % e)
    print("\n" + ("UI DRIVE FAIL %d" % len(d.fail) if d.fail else "UI DRIVE OK ✅"))
    for m in d.fail:
        print("  ✗ " + m)
    return 1 if d.fail else 0


if __name__ == "__main__":
    sys.exit(main())
