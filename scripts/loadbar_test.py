# -*- coding: utf-8 -*-
"""loadbar 回归：文本进度条 → 界面百分比的换算，用真 transformers/diffusers 模块验。

不碰 GPU、不载入 31GB 权重：只把两个库的进度条工厂真的换下来，
喂它们真实的调用形式（外层 5 个组件 + 内层逐张量组），看百分比序列对不对。
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))

import loadbar  # noqa: E402

FAIL = []


def ck(name, cond, got=""):
    print("%-34s %s %s" % (name, "PASS" if cond else "FAIL", got if got != "" else ""))
    if not cond:
        FAIL.append(name)


def make_repo(steps=(("tokenizer", 0), ("text_encoder", 8 << 30), ("transformer", 40 << 30),
                     ("vae", 1 << 30), ("scheduler", 0))):
    d = tempfile.mkdtemp(prefix="qic_loadbar_")
    import json
    idx = {k: ["lib", "Cls"] for k, _ in steps}
    idx["_class_name"] = "QwenImage21Pipeline"
    with open(os.path.join(d, "model_index.json"), "w", encoding="utf-8") as fh:
        json.dump(idx, fh)
    for name, size in steps:
        sub = os.path.join(d, name)
        os.makedirs(sub, exist_ok=True)
        if size:
            with open(os.path.join(sub, "x.safetensors"), "wb") as fh:
                fh.truncate(size)          # 稀疏文件：只占目录项，不写真字节
    return d


def main():
    repo = make_repo()
    try:
        # ---------------------------------------------------------- plan()
        pl = dict(loadbar.plan(repo))
        ck("plan 读到 5 个组件", len(pl) == 5, sorted(pl))
        ck("plan 按字节计权", pl.get("transformer") == 40 << 30, pl.get("transformer"))
        ck("缺权重文件的组件记 0", pl.get("tokenizer") == 0, pl.get("tokenizer"))
        ck("model_index 缺失时退回空计划",
           loadbar.plan(os.path.join(repo, "nope")) == [])

        # ------------------------------------------------- 权重与百分比换算
        seen = []
        bar = loadbar.LoadBar(lambda p, s: seen.append((p, s)), loadbar.plan(repo))
        floor = bar.floor
        tot = sum([max(8 << 30, floor), max(40 << 30, floor), max(1 << 30, floor)]) \
            + 2 * floor
        ck("总权重=各组件份额之和", abs(bar.total - tot) < 1, "%.0f" % bar.total)

        items = [(k, ["lib", "Cls"]) for k in
                 ("tokenizer", "text_encoder", "transformer", "vae", "scheduler")]
        outer = bar._df(items, desc="Loading pipeline components...", total=5)
        for name, _v in outer:
            if name == "transformer":
                inner = bar._tf(lambda *a, **k: object(), items,
                                {"desc": "Loading weights", "total": 750})
                for i in range(750):
                    inner.update(1)
        last = seen[-1][0]
        pcts = [p for p, _s in seen]
        ck("收尾到 99%（100 由调用方补）", last == 99, last)
        ck("百分比单调不回退", all(b >= a for a, b in zip(pcts, pcts[1:])),
           "%d 帧" % len(pcts))
        # transformer 段：份额 40G / 总 54.3G，起点=(0.8+8.6)/54.3≈17%
        t0 = [p for p, s in seen if s == "载入 transformer"][0]
        t1 = [p for p, s in seen if s == "载入 vae"][0]
        ck("transformer 段起点≈17%", abs(t0 - 17) <= 1, t0)
        ck("transformer 段走完≈96%", abs(t1 - 96) <= 1, t1)
        ck("内层 750 组真的推进了百分比", t1 - t0 > 70, t1 - t0)
        ck("外层收尾话术", seen[-1][1] == "整理显存…", seen[-1][1])

        # ------------------------------------------- 关掉文本条后仍要能计数
        # EmptyTqdm 没有 .n/.total（__getattr__ 会返回空函数）：代理必须自己数
        class Empty:
            def __init__(self, it=None):
                self._it = it or []

            def __iter__(self):
                return iter(self._it)

            def __getattr__(self, k):
                def f(*a, **kw):
                    return None
                return f

        seen2 = []
        bar2 = loadbar.LoadBar(lambda p, s: seen2.append(p), loadbar.plan(repo))
        bar2.stage("transformer")            # 没有段就没有「段内的几成」
        sub = bar2._tf(lambda *a, **k: Empty(items), (items,), {"desc": "Loading weights"})
        list(iter(sub))
        for _ in range(5):
            sub.update(1)
        ck("空壳条也能按 len(iterable) 折算", seen2 and seen2[-1] > 0, seen2[-3:])
        ck("未知 total 时不乱报",
           bar2._tf(lambda *a, **k: Empty(), (), {"desc": "x"}).update(3) is None)

        # ------------------------------------------- 真装真卸（两个库的入口）
        import importlib
        tfl = importlib.import_module("transformers.utils.logging")
        dfl = importlib.import_module("diffusers.utils.logging")
        before_tf, before_df = tfl.tqdm, dfl.tqdm
        got = []
        with loadbar.watch(repo, lambda p, s: got.append((p, s))) as w:
            ck("transformers 的条被接管", tfl.tqdm is before_tf
               and getattr(tfl, "_tqdm_hook", None) is not None)
            ck("diffusers 的条被接管", dfl.tqdm is not before_df)
            for name, _v in dfl.tqdm(items, desc="Loading pipeline components..."):
                pass
            w.stage(None)
        ck("退出后 diffusers 原样还回", dfl.tqdm is before_df)
        tfl.set_tqdm_hook(None)
        ck("退出后 transformers 钩子清掉", getattr(tfl, "_tqdm_hook", None) is None)
        ck("真模块走一遍有百分比", any(p > 0 for p, _s in got), got[-2:])

        # ------------------------------------------- 文本条全局静音不影响接管
        loadbar.silence_text_bars()
        ck("transformers 文本条已关", tfl.is_progress_bar_enabled() is False)
        ck("diffusers 文本条已关", dfl.is_progress_bar_enabled() is False)
        seen4 = []
        with loadbar.watch(repo, lambda p, s: seen4.append(p)) as w4:
            w4.stage("transformer")
            # 真入口：transformers/core_model_loading.py 就是这么调的（不传 total，靠 len）
            for _x in tfl.tqdm(items, desc="Loading weights"):
                pass
        ck("静音后走真工厂仍然计数", seen4 and seen4[-1] > 0, seen4[-2:])
        seen5 = []
        with loadbar.watch(repo, lambda p, s: seen5.append(p)) as w5:
            for name, _v in dfl.tqdm(items, desc="Loading pipeline components..."):
                pass
        ck("外层走真模块能到 99%", seen5 and seen5[-1] == 99, seen5[-2:])
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    print("\nLOADBAR TEST " + ("FAIL: " + ", ".join(FAIL) if FAIL else "PASS"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
