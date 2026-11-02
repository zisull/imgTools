# -*- coding: utf-8 -*-
"""h3_cloud_smoke.py —— H3 云端通道的真机冒烟：走界面同一个入口，量出成片真实尺寸。

为什么需要它（本地那条有 h3_video_smoke.py，云端这条以前没有）：
  云端不是「把参数发过去就完事」——节点里那些档位/画幅是它自己算宽高的，
  界面写 768×1344、平台给 432×768 这种事只有真跑一段才知道。所以这里量的不是
  「软件报了多大」，而是**落盘那个 mp4 的 tkhd 里到底写了多大**。

全程不碰显卡、不拉 ComfyUI：只开那只共用调试浏览器，按平台计费。

    .venv\\Scripts\\python.exe scripts\\h3_cloud_smoke.py
    .venv\\Scripts\\python.exe scripts\\h3_cloud_smoke.py 5 848x480
    .venv\\Scripts\\python.exe scripts\\h3_cloud_smoke.py 5 848x480 --wf 工作流ID
"""
import os
import struct
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))
# 冒烟会写 config（导航换代、参数回填），先指到临时那份，别咬用户那一份
os.environ["QIC_CONFIG"] = os.path.join(tempfile.gettempdir(), "qic_cloudsmoke_cfg.json")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_WF = "2103759530927673346"


def mp4_size(path):
    """从 mp4 的 tkhd 里读真实宽高（不装任何视频库）。

    tkhd 末尾 8 字节是 width/height 的 16.16 定点数；一条片子可能有好几条轨，
    取最大的那个非零值——画面轨总比字幕/元数据轨大。读不出来就回 None，
    冒烟宁可报「量不到」，也不要拿界面的数当证据。
    """
    with open(path, "rb") as f:
        data = f.read()

    def boxes(buf, start, stop):
        i = start
        while i + 8 <= stop:
            size = struct.unpack(">I", buf[i:i + 4])[0]
            kind = buf[i + 4:i + 8]
            head = 8
            if size == 1:
                size = struct.unpack(">Q", buf[i + 8:i + 16])[0]
                head = 16
            elif size == 0:
                size = stop - i
            if size < head or i + size > stop:
                return
            yield kind, i + head, min(i + size, stop)
            i += size

    best = (0, 0)
    for kind, s, e in boxes(data, 0, len(data)):
        if kind != b"moov":
            continue
        for k2, s2, e2 in boxes(data, s, e):
            if k2 != b"trak":
                continue
            for k3, s3, e3 in boxes(data, s2, e2):
                if k3 != b"tkhd" or e3 - s3 < 8:
                    continue
                # version(1)+flags(3)+时间戳若干，宽高永远是最后 8 字节
                w, h = struct.unpack(">II", data[e3 - 8:e3])
                w, h = w >> 16, h >> 16
                if w * h > best[0] * best[1]:
                    best = (w, h)
    return best if best[0] and best[1] else None


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("seconds", nargs="?", default="5")
    ap.add_argument("size", nargs="?", default="848x480")
    ap.add_argument("--wf", default=DEFAULT_WF,
                    help="平台工作流地址/ID，或本地「导出工作流」存下来的 .json")
    ap.add_argument("--prompt", default="一只猫推开木门，阳光落在地板上，镜头缓慢推进")
    ap.add_argument("--first", default="",
                    help="首帧/参考图：云端这份 H3 工作流按参考生成，得给一张图")
    args = ap.parse_args()
    seconds, size, wf, prompt = args.seconds, args.size, args.wf, args.prompt

    from app import App
    a = App()
    # 平台池子排起来没准头（实测 5 秒段也能排到十几分钟）；冒烟宁可多等，
    # 不要把「还在平台那边跑」误报成失败。界面上的默认仍是 30 分钟。
    a.cfg.setdefault("cloud", {})["gen_timeout"] = 3600
    before = set()
    out_dir = os.path.join(ROOT, str((a.cfg.get("console") or {}).get("output_dir") or "outputs"))
    if os.path.isdir(out_dir):
        before = {x for x in os.listdir(out_dir) if x.lower().endswith(".mp4")}

    t0 = time.time()
    r = a.video_gen({"prompt": prompt, "first": args.first,
                     "seconds": seconds, "size": size, "exec": "cloud",
                     "cloud_wf": wf, "cloud_acct": ""})
    print("· 发起：%s" % ("ok · 号「%s」· 界面写 %s" % (r.get("acct"), size)
                          if r.get("ok") else r.get("msg")))
    if not r.get("ok"):
        return 1
    last = ""
    while a.st.get("running") and time.time() - t0 < 3700:
        s = str(a.st.get("status") or "")
        if s != last:
            print("  [%4ds] %s" % (int(time.time() - t0), s))
            last = s
        time.sleep(2)
    el = time.time() - t0
    fail = a.st.get("last_fail")
    print("· 收尾：状态=%s 用时 %.1f 秒" % (a.st.get("status"), el))
    new = sorted({x for x in os.listdir(out_dir)
                  if x.lower().endswith(".mp4")} - before,
                 key=lambda x: os.path.getmtime(os.path.join(out_dir, x)))
    if fail:
        print("✗ 失败：%s" % str(fail)[:300])
        return 1
    if not new:
        print("✗ 没有新片子落到 %s" % out_dir)
        return 1
    f = os.path.join(out_dir, new[-1])
    dim = mp4_size(f)
    print("· 成片：%s · %.1f MB" % (f, os.path.getsize(f) / 1048576.0))
    print("· 界面写 %s → 文件里真是 %s" % (size, ("%dx%d" % dim) if dim else "量不到"))
    rec = [x for x in (a.gallery_list().get("items") or []) if x.get("file") == f]
    if rec:
        print("· 画廊记录：size=%s · 用时=%ss" % (rec[0].get("size"), rec[0].get("sec")))
    a._cloudkit()["host"].close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
