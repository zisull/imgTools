# -*- coding: utf-8 -*-
"""loadbar.py —— 把第三方库的文本进度条接成界面里的百分比。

黑框（控制台）去掉之后，「Loading weights: 88%」这类文本条就没有落脚的地方了，
而模型载入恰恰是全程最慢的一段。这里接管 transformers / diffusers 的进度条工厂：
文本一律不再输出，只取「走到哪了」这一件事，按各组件权重文件的字节数折算成
0~100 的总进度，喂给前端的载入进度条。

两条来源：
  · diffusers `Loading pipeline components...`（外层，5 个组件）→ 推进到哪个组件
  · transformers `Loading weights`（内层，逐张量组）→ 当前组件内部走了几成
接管都是临时装、退出即还原：这两个模块的开关是进程级的，别把它带进别的调用方。
"""
import contextlib
import importlib
import json
import os

_WEIGHT_EXT = (".safetensors", ".bin", ".ckpt", ".pt", ".gguf")
# 没有权重文件的组件（tokenizer / scheduler）也给一点份额，否则进度条会在它们身上「跳过去」
_MIN_SHARE = 50 * 1024 * 1024


def _dir_bytes(d):
    total = 0
    try:
        for root, _dirs, files in os.walk(d):
            for f in files:
                if f.lower().endswith(_WEIGHT_EXT):
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
    except OSError:
        pass
    return total


def plan(repo_path):
    """model_index.json → [(组件名, 权重字节)]。读不到就返回 []，进度退回「只报阶段」。"""
    try:
        with open(os.path.join(repo_path, "model_index.json"), "r", encoding="utf-8") as fh:
            idx = json.load(fh)
    except Exception:
        return []
    out = []
    for k, v in idx.items():
        if k.startswith("_") or not v:
            continue
        out.append((k, _dir_bytes(os.path.join(repo_path, k))))
    return out


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _total_of(args, kwargs):
    t = _num(kwargs.get("total"))
    if t and t > 0:
        return t
    it = args[0] if args else kwargs.get("iterable")
    try:
        n = float(len(it))
        return n if n > 0 else None
    except Exception:
        return None


class _Sub:
    """内层条。计数必须由我们自己数：文本条关掉后被包对象是个空壳，
    它不会替我们推进；而接管迭代也不会重复计数（被包对象的 .n 我们从不读）。"""

    def __init__(self, inner, total, on_frac):
        self._i = inner
        self._t = total
        self._n = 0.0
        self._on = on_frac

    def _tick(self, d):
        self._n += d
        if self._t:
            self._on(min(1.0, self._n / self._t))

    def update(self, n=1):
        d = _num(n)
        self._tick(1.0 if d is None else d)
        try:
            self._i.update(n)
        except Exception:
            pass
        return None

    def close(self):
        if self._t:
            self._on(1.0)
        try:
            return self._i.close()
        except Exception:
            return None

    def __iter__(self):
        for x in self._i:
            self._tick(1.0)
            yield x

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False

    def __getattr__(self, k):
        try:
            return getattr(self._i, k)
        except AttributeError:
            def _noop(*a, **kw):
                return None
            return _noop


class LoadBar:
    def __init__(self, report, steps=None):
        self.report = report or (lambda p, s: None)
        self._df_orig = None      # install() 之前也得有：单测会直接喂调用形式
        steps = steps or []
        floor = max([_MIN_SHARE] + [int(t * 0.02) for _n, t in steps]) if steps else _MIN_SHARE
        self.weights = {n: max(float(b), float(floor)) for n, b in steps}
        self.total = sum(self.weights.values()) or 1.0
        self.floor = float(floor)
        self.base = 0.0
        self.cur_w = 0.0
        self.cur_name = None
        self.frac = 0.0
        self.stage_txt = "准备载入"

    # ---------------------------------------------------------------- 进度换算
    def _emit(self):
        done = (self.base + self.cur_w * self.frac) / self.total
        pct = int(max(0, min(99, round(done * 100))))
        try:
            self.report(pct, self.stage_txt)
        except Exception:
            pass

    def _frac(self, f):
        self.frac = max(0.0, min(1.0, float(f)))
        self._emit()

    def stage(self, name):
        """外层走到某个组件：把上一个组件结清，再开新段。"""
        if self.cur_name:
            self.base += self.cur_w
        self.frac = 0.0
        if name is None:
            self.cur_name = None
            self.cur_w = 0.0
            self.stage_txt = "整理显存…"
        else:
            self.cur_name = str(name)
            self.cur_w = self.weights.get(self.cur_name, self.floor)
            self.stage_txt = "载入 " + self.cur_name
        self._emit()

    def note(self, text):
        """引擎侧主动报一句阶段话术（不推进百分比）。"""
        self.stage_txt = str(text)
        self._emit()

    # ---------------------------------------------------------------- 装与卸
    def _df(self, *args, **kwargs):
        desc = str(kwargs.get("desc") or "")
        if "pipeline components" in desc:
            # 外层条直接换掉：连被包对象都不建，否则静音没生效时会漏出一条文本条
            return _Stage(self, args[0] if args else kwargs.get("iterable"))
        obj = None
        if self._df_orig:
            try:
                obj = self._df_orig(*args, **dict(kwargs, disable=True))
            except Exception:
                obj = None
        return _Sub(obj, _total_of(args, kwargs), self._frac)

    def _tf(self, factory, args, kwargs):
        try:
            obj = factory(*args, **dict(kwargs, disable=True))
        except Exception:
            obj = None
        return _Sub(obj, _total_of(args, kwargs), self._frac)

    def install(self):
        saved = {}
        self._df_orig = None
        try:
            lg = importlib.import_module("transformers.utils.logging")
            saved["tf"] = (lg, lg.set_tqdm_hook(self._tf))
        except Exception:
            pass
        try:
            lg = importlib.import_module("diffusers.utils.logging")
            saved["df"] = (lg, getattr(lg, "tqdm", None))
            self._df_orig = saved["df"][1]
            lg.tqdm = self._df
        except Exception:
            pass
        return saved

    def uninstall(self, saved):
        lg, prev = saved.get("tf") or (None, None)
        if lg is not None:
            try:
                lg.set_tqdm_hook(prev)
            except Exception:
                pass
        lg, prev = saved.get("df") or (None, None)
        if lg is not None:
            try:
                lg.tqdm = prev
            except Exception:
                pass
        self._df_orig = None


class _Stage:
    """外层条：diffusers 是 `for name,(lib,cls) in tqdm(init_dict.items())`，
    在交给循环体之前先记账，所以这里推进的是「这个组件刚开始」。"""

    def __init__(self, bar, iterable):
        self._b = bar
        self._it = iterable or []

    def __iter__(self):
        for item in self._it:
            try:
                name = item[0]
            except Exception:
                name = None
            self._b.stage(name)
            yield item
        self._b.stage(None)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@contextlib.contextmanager
def watch(repo_path, report):
    """包住一次 pipeline 载入：`with watch(dir, cb): pipe = ...from_pretrained(...)`。"""
    bar = LoadBar(report, plan(repo_path))
    saved = bar.install()
    try:
        yield bar
    finally:
        bar.uninstall(saved)


def silence_text_bars():
    """全局关掉两个库的文本进度条：黑框没了，文本条留着只会往日志里灌几千行 \\r。
    关掉后工厂仍会被调用（拿到的是空壳），所以 loadbar 的接管照旧生效。"""
    for m in ("transformers.utils.logging", "diffusers.utils.logging"):
        try:
            importlib.import_module(m).disable_progress_bar()
        except Exception:
            pass
