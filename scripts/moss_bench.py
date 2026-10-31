# -*- coding: utf-8 -*-
"""moss_bench.py —— 把 Moss 的一次出图拆成秒表，顺便量「显存到底什么时候才被吃满」。

    .venv\\Scripts\\python.exe scripts\\moss_bench.py            # 全套
    .venv\\Scripts\\python.exe scripts\\moss_bench.py warm        # 只量冷/热两张的差

界面只报总秒数，提速要动的是具体某一段：子进程 import、权重上卡、去噪、VAE+存盘、
取图落盘。不拆开就只能猜。第二个用途是回答「日常质量档和让出显存档在显存上看不出区别」——
把「拉起进程后」和「第一次出图后」两个时刻的整卡占用打出来，谁在骗人就一目了然。

显存读的是 `nvidia-smi --query-gpu=memory.used` 的整卡值：这台机器上
`--query-compute-apps` 会吐一堆 [N/A] 的桌面进程，不能当证据（实测踩过）。
"""
import json
import os
import re
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "webui"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app import MOSS_TIERS                            # noqa: E402  档位表以这里为准
from engine.moss_mgr import MossManager               # noqa: E402


def vram_used():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout
        vals = [int(x) for x in out.replace(",", " ").split()]
        return max(vals) if vals else -1
    except Exception:
        return -1


class Sampler:
    """后台每 0.4 秒采一次整卡显存：峰值和「什么时候涨上去的」都要留。"""

    def __init__(self, every=0.4):
        self.every = every
        self.samples = []          # [(t, MiB)]
        self._stop = threading.Event()
        self._th = None

    def start(self):
        self._stop.clear()
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()
        return self

    def _run(self):
        while not self._stop.is_set():
            self.samples.append((time.time(), vram_used()))
            self._stop.wait(self.every)

    def stop(self):
        if self._th:
            self._stop.set()
            self._th.join(timeout=3)
        return self

    def peak(self):
        return max([v for _, v in self.samples if v > 0] or [0])

    def since(self, t0):
        """t0 之后第一次明显抬升（比基线高 500 MiB 以上）的时刻。"""
        base = min([v for _, v in self.samples if v > 0] or [0])
        for t, v in self.samples:
            if t >= t0 and v > base + 500:
                return t - t0, v
        return None, base


def mk_mgr(extra_args=()):
    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    m = cfg.get("moss") or {}
    return MossManager(os.path.join(ROOT, m.get("comfyui_dir") or "comfyui"),
                       port=int(m.get("port") or 8876),
                       extra_args=list(extra_args), log=lambda s: print("   │ " + s))


def params(size, quality, prompt="a lighthouse on a cliff at dusk, warm light"):
    t = MOSS_TIERS[quality]
    w, h = size.lower().split("x")
    return {"template": t["template"], "prompt": prompt, "negative": "watermark",
            "steps": t["steps"], "cfg": t["cfg"], "width": int(w), "height": int(h),
            "seed": 20261027, "batch": 1,
            "slg_skip_layer": 22, "slg_start": 0.0, "slg_end": 0.5}


def one(mgr, label, p, out_dir, prefix="bench"):
    """一张图，拆成：提交→首帧（含权重上卡）→末帧（去噪完）→函数返回（VAE/存盘/取图）。

    种子必须每次不同：同 seed + 同参数会被 ComfyUI 的输入缓存直接命中，0.1 秒返回上一张
    （第一版就被它骗过，把「缓存回图」当成「热路径提速」）。顺带说，界面上连着点两次
    完全一样的参数，秒出的那张也是缓存。"""
    p = dict(p)
    p["seed"] = int(time.time() * 1000) % 10 ** 8
    frames = []
    t0 = time.time()
    paths = mgr.generate(p, on_progress=lambda d, m: frames.append((time.time() - t0, d, m)),
                         out_dir=out_dir, out_prefix=prefix)
    dt = time.time() - t0
    first = frames[0][0] if frames else dt
    last = frames[-1][0] if frames else dt
    per = (last - first) / max(1, len(frames) - 1) if len(frames) > 1 else 0.0
    print("· %-22s 总计 %6.1fs ｜ 首帧 %5.1fs · 末帧 %5.1fs · 收尾 %5.1fs ｜ %d 步 × %.2f s/步 ｜ %s"
          % (label, dt, first, last, dt - last, len(frames), per,
             os.path.basename(paths[0]) if paths else "无图"), flush=True)
    return dt


AB_VARIANTS = [
    ("基线（默认缓存）", []),
    ("fp16累加", ["--fast", "fp16_accumulation"]),
    ("fp16+经典缓存", ["--fast", "fp16_accumulation", "--cache-classic"]),
    ("经典缓存", ["--cache-classic"]),
    ("RAM缓存放宽", ["--cache-ram", "16", "24"]),
    ("高内存模式", ["--high-ram"]),
]


def run_ab():
    """同一个尺寸，逐种启动参数各起一次全新 ComfyUI 进程对比。

    每个变体都要「拉起→冷→热→热」三段：拉起段量的是 import 和节点注册，
    冷/热差才是权重上卡，热那两张才是注意力实现真正影响的部分。
    变体之间必须整进程重启：注意力后端的选择在 import 时就定了，
    同一个进程里换参数不会生效。"""
    rows = []
    base = os.path.join(ROOT, "outputs", "bench")
    for label, extra in AB_VARIANTS:
        # 每个变体单独一个目录：省下的秒数要用「图上有没有变糊」来对账，
        # 混在一个目录里就分不清哪张是谁跑的了。
        tag = re.sub(r"\W+", "", label) or "base"
        out_dir = os.path.join(base, tag)
        os.makedirs(out_dir, exist_ok=True)
        print("\n=== %s  %s ===" % (label, " ".join(extra) or "(空)"), flush=True)
        mgr = mk_mgr(extra)
        if mgr._port_busy():
            print("!! 端口还被上一轮占着，先停掉引擎再跑")
            return 1
        s = Sampler().start()
        t0 = time.time()
        try:
            mgr.start(tier="daily")
        except Exception as e:
            print("!! 起不来：%s" % e)
            s.stop()
            continue
        boot = time.time() - t0
        times = [one(mgr, "冷 512²/8", params("512x512", "fast"), out_dir),
                 one(mgr, "热 512²/8", params("512x512", "fast"), out_dir),
                 one(mgr, "热 1024²/8", params("1024x1024", "fast"), out_dir),
                 one(mgr, "热 768²/25", params("768x768", "mid"), out_dir),
                 one(mgr, "慢轮 1024²/8", params("1024x1024", "fast"), out_dir)]
        peak = s.stop().peak()
        mgr.stop()
        rows.append((label, boot, peak, times))
        time.sleep(2.0)
    print("\n=== 汇总（拉起秒 / 整卡峰值 MiB / 冷512 热512 热1024 热768·25 慢轮1024）===")
    for label, boot, peak, times in rows:
        print("  %-18s 拉起 %5.1fs ｜ 峰 %6d MiB ｜ %s"
              % (label, boot, peak, " ".join("%5.1f" % t for t in times)))
    return 0


def main():
    which = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    if which == "ab":
        return run_ab()
    out_dir = os.path.join(ROOT, "outputs", "bench")
    os.makedirs(out_dir, exist_ok=True)
    mgr = mk_mgr()
    print("显存基线（什么都没起）：%d MiB" % vram_used(), flush=True)

    s = Sampler().start()
    t0 = time.time()
    mgr.start(tier="daily")
    print("\n[拉起] 子进程 → /system_stats 应答：%.1f 秒" % (time.time() - t0), flush=True)
    print("[拉起] 此刻整卡显存：%d MiB ← 「日常质量档」刚点亮时显存就这么点，"
          "权重还没上卡" % vram_used(), flush=True)
    if which == "warm":
        mgr.stop()
        s.stop()
        return

    print("\n[预热] 后台跑一张 256²/1 步把权重搬上卡（界面上由 _warm_moss_async 触发）")
    t1 = time.time()
    ok = mgr.warm()
    print("[预热] 结果 %s ｜ %.1f 秒 ｜ 此刻整卡显存：%d MiB"
          % ("成功" if ok else "失败", time.time() - t1, vram_used()), flush=True)
    left = [n for n in os.listdir(os.path.join(mgr.comfyui_dir, "output"))
            if n.startswith("moss_warm")]
    print("[预热] 没清干净的预热产物：%s" % (left or "无（删净了）"), flush=True)
    up, mb = s.since(t1)
    print("[预热] 显存抬升出现在第 %.1f 秒（%d MiB）" % (up, mb) if up is not None
          else "[预热] 显存没怎么动（?）", flush=True)

    print("\n[出图] 每张都记 提交→首帧→末帧→返回 四段")
    cold = one(mgr, "首张 512²/8（预热后）", params("512x512", "fast"), out_dir)
    warm = one(mgr, "热 512²/8 步（同参数再来）", params("512x512", "fast"), out_dir)
    one(mgr, "热 1024²/8 步", params("1024x1024", "fast"), out_dir)
    one(mgr, "热 768²/25 步", params("768x768", "mid"), out_dir)
    one(mgr, "慢轮 1024²/8 步", params("1024x1024", "fast"), out_dir)
    print("\n[冷/热差] 预热后首张 %.1fs vs 再来一张 %.1fs：首张不再为「权重上卡」买单"
          % (cold, warm), flush=True)
    print("[峰值] 整卡显存峰值：%d MiB" % s.stop().peak(), flush=True)

    print("\n[让出显存] stop() 之前 %d MiB" % vram_used(), flush=True)
    t1 = time.time()
    mgr.stop()
    time.sleep(2.0)
    print("[让出显存] stop() 之后 %d MiB（%.1f 秒后）" % (vram_used(), time.time() - t1), flush=True)
    print("\n产物在 %s" % out_dir)


if __name__ == "__main__":
    main()
