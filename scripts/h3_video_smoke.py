# -*- coding: utf-8 -*-
"""h3_video_smoke.py —— 本地 H3 视频的真机冒烟：出一段带声音的成片，报秒数/显存峰值/落盘。

走的和用户点的是同一条路：界面那三样（描述语 / 画幅 / 时长）直接发给 `App.video_gen`，
由它拉起内嵌 ComfyUI、灌同一份 workflow_h3.json。
显存读整卡 `nvidia-smi --query-gpu=memory.used`——这台机器 `--query-compute-apps` 会吐一堆
[N/A] 的桌面进程，不能当证据（moss_bench 里记过）。

    .venv\\Scripts\\python.exe scripts\\h3_video_smoke.py
    .venv\\Scripts\\python.exe scripts\\h3_video_smoke.py 10 1024x1024
"""
import os
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))
# 冒烟也会写 config.json（换代后的导航、参数回填），先把它指到临时那份，别咬用户配置
os.environ["QIC_CONFIG"] = os.path.join(tempfile.gettempdir(), "qic_h3smoke_cfg.json")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app import App  # noqa: E402


def gpu_used():
    """整卡占用（MiB）；拿不到就报 0，不让冒烟因为一次查询失败而断。"""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=6).stdout
        return sum(int(x.split(",")[0]) for x in out.splitlines() if x.strip())
    except Exception:
        return 0


def main():
    seconds = sys.argv[1] if len(sys.argv) > 1 else "5"
    size = sys.argv[2] if len(sys.argv) > 2 else "1344x768"
    a = App()
    idle = gpu_used()
    peak = [idle]
    stop = threading.Event()

    def sample():
        while not stop.wait(1.0):
            peak[0] = max(peak[0], gpu_used())

    threading.Thread(target=sample, daemon=True).start()

    t0 = time.time()
    r = a.video_gen({"prompt": "一只猫推开木门，阳光落在地板上，镜头缓慢推进",
                     "seconds": seconds, "size": size, "seed": -1})
    if not r.get("ok"):
        print("没起来：%s" % r.get("msg"))
        return 1
    print("已发任务：%s 秒 · %s · %d 帧 · %d 步" % (seconds, size, r["frames"], r["total"]))
    last = ""
    while a.st.get("running") and time.time() - t0 < 1800:
        s = "%s %s/%s" % (a.st.get("running"), a.st.get("done"), a.st.get("total"))
        if s != last:
            print("  [%4ds] %s · 显存 %d MiB" % (int(time.time() - t0), s, gpu_used()))
            last = s
        time.sleep(1)
    stop.set()
    el = time.time() - t0
    fail = a.st.get("last_fail")
    print("收尾：状态=%s 用时 %.1f 秒 · 显存 空载 %d → 峰值 %d MiB"
          % (a.st.get("status"), el, idle, peak[0]))
    if fail:
        print("失败：%s" % fail)
        return 1
    vids = [x for x in a.gallery_list()["items"] if str(x.get("file", "")).lower().endswith(".mp4")]
    if not vids:
        print("画廊里没有成片")
        return 1
    f = vids[0]["file"]
    print("成片：%s · %.1f MB · 记录参数 %s · %s 步 · %s s"
          % (f, os.path.getsize(f) / 1048576.0, vids[0].get("size"),
             vids[0].get("steps"), vids[0].get("sec")))
    # 让出显存档：子进程没了显存才真正归零，别把 41G 权重留在卡上
    a.moss_set_tier("yield")
    time.sleep(3)
    print("让出显存后整卡占用：%d MiB" % gpu_used())
    return 0


if __name__ == "__main__":
    sys.exit(main())
