"""命令行出图 + 测速（M1 验收工具）。

用法:
  python scripts/gen.py --prompt "..." [--size 1024x1024] [--steps N] [--seed 42]
                        [--repo models/Qwen-Image-2.1-Turbo] [--out outputs/x.png]
                        [--bench "1024x1024,1536x1536,2048x2048"]

--bench 模式依次各出 1 张，打印耗时/显存峰值/内存可用量，用于分档决策。
"""
import argparse
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 权重已在本地，禁止偷偷联网
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import psutil  # noqa: E402
import torch  # noqa: E402

from engine.pipeline_mgr import PipelineMgr  # noqa: E402


class MemSampler(threading.Thread):
    """后台采样系统可用内存最低值。"""

    def __init__(self):
        super().__init__(daemon=True)
        self.min_avail_gb = float("inf")
        self._stop = threading.Event()
        self.total_gb = psutil.virtual_memory().total / 2**30

    def run(self):
        while not self._stop.is_set():
            avail = psutil.virtual_memory().available / 2**30
            self.min_avail_gb = min(self.min_avail_gb, avail)
            self._stop.wait(0.5)

    def stop(self):
        self._stop.set()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="A neon shop sign that reads \"QWEN IMAGE 2.1\", rainy night, reflections on wet pavement")
    ap.add_argument("--size", default="1024x1024")
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--repo", default=os.path.join(ROOT, "models", "Qwen-Image-2.1-Turbo"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--bench", default=None, help="逗号分隔的尺寸列表，逐个出图测速")
    ap.add_argument("--quant", default="fp8", choices=["fp8", "none"], help="fp8=torchao Float8WeightOnly(12G卡推荐)")
    args = ap.parse_args()

    mgr = PipelineMgr()
    mgr.load(args.repo, quant=args.quant)

    sampler = MemSampler()
    sampler.start()
    sizes = [s.strip() for s in args.bench.split(",")] if args.bench else [args.size]
    results = []
    for i, s in enumerate(sizes):
        w, h = (int(x) for x in s.lower().split("x"))
        out = args.out or os.path.join(
            ROOT, "outputs", f"bench_{w}x{h}_{int(time.time())}.png"
        )
        os.makedirs(os.path.dirname(out), exist_ok=True)
        torch.cuda.reset_peak_memory_stats()
        t0 = time.time()
        img = mgr.generate(args.prompt, width=w, height=h, steps=args.steps, seed=args.seed)
        dt = time.time() - t0
        img.save(out)
        peak_gb = torch.cuda.max_memory_allocated() / 2**30
        results.append((s, dt, peak_gb))
        print(f"[{s}] {dt:.1f}s  显存峰值 {peak_gb:.1f}GB  -> {out}", flush=True)

    sampler.stop()
    print("\n=== 测速汇总 ===")
    for s, dt, peak in results:
        print(f"{s:>12}  {dt:6.1f}s  显存峰值 {peak:.1f}GB")
    print(f"系统内存: 总 {sampler.total_gb:.0f}GB, 全程最低可用 {sampler.min_avail_gb:.1f}GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
