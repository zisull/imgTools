# -*- coding: utf-8 -*-
"""性能探针：定位「编辑为什么这么慢 / 加 512 档有没有用」。
载入一次，分别跑 文生图@512、编辑@512、编辑@768，打印每张耗时 + 全程最低可用内存 + 显存峰值。
用法: .venv/Scripts/python.exe scripts/perf_probe.py
"""
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import psutil  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402
from engine.pipeline_mgr import PipelineMgr  # noqa: E402

BOAT = os.path.join(ROOT, "models", "Qwen-Image-2.1-Turbo", "assets", "turbo-boat-input.png")
OUT = os.path.join(ROOT, "outputs")


class Sampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.min_ram = float("inf")
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            self.min_ram = min(self.min_ram, psutil.virtual_memory().available / 2**30)
            self._stop.wait(0.3)

    def stop(self):
        self._stop.set()


def timed(tag, mgr, **kw):
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    img = mgr.generate(**kw)
    dt = time.time() - t0
    peak = torch.cuda.max_memory_allocated() / 2**30
    p = os.path.join(OUT, "probe_%s.png" % tag)
    img.save(p)
    print("[%-10s] %7.1fs  显存峰值 %.1fGB  -> %s" % (tag, dt, peak, os.path.basename(p)), flush=True)
    return dt


def main():
    mgr = PipelineMgr()
    mgr.load(os.path.join(ROOT, "models", "Qwen-Image-2.1-Turbo"), offload=True, quant="fp8")
    boat = Image.open(BOAT).convert("RGBA")
    s = Sampler(); s.start()
    timed("t2i512", mgr, prompt="A red apple on a white table, studio light", width=512, height=512, seed=42)
    timed("edit512", mgr, prompt="Photorealistic yacht on the sea, side view.", image=boat, resolution=512, seed=42)
    timed("edit768", mgr, prompt="Photorealistic yacht on the sea, side view.", image=boat, resolution=768, seed=42)
    s.stop()
    print("全程最低可用内存: %.1f GB / 总 %.0f GB" % (s.min_ram, psutil.virtual_memory().total / 2**30), flush=True)


if __name__ == "__main__":
    main()
