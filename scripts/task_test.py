# -*- coding: utf-8 -*-
"""任务层回归（不碰真模型）：占位互斥、坏参数不卡 running、停止不落半成品。

用假的 PipelineMgr 顶掉 self.mgr，输出目录与历史库都指向临时文件，
绝不写进用户正在用的 config.json / data/history.db。
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "webui"), os.path.join(ROOT, "engine")):
    sys.path.insert(0, _p)

from app import App, _to_int          # noqa: E402
from store import Store                # noqa: E402


class FakeImg:
    def __init__(self, size):
        from PIL import Image
        self.im = Image.new("RGBA", size, (255, 0, 0, 255))

    def save(self, path):
        self.im.save(path)


class FakeMgr:
    """generate 时按 halt_at 决定要不要「跑一半被停止」：置停止位后照常返回一张图。"""

    def __init__(self, app, halt=False):
        self.pipe = object()
        self.app = app
        self.halt = halt
        self.calls = 0
        self.loaded = False

    def load(self, *a, **k):
        self.loaded = True

    def generate(self, **kw):
        self.calls += 1
        if self.halt:
            self.app._stop.set()          # 模拟去噪中途用户按了停止
        return FakeImg((64, 64))


def main():
    tmp = tempfile.mkdtemp(prefix="qic_task_test_")
    out = os.path.join(tmp, "outputs")
    os.makedirs(out, exist_ok=True)
    fails = []

    def ck(name, cond, extra=""):
        print("%-34s %s %s" % (name, "PASS" if cond else "FAIL", extra))
        if not cond:
            fails.append(name)

    try:
        a = App()
        a.cfg["console"]["output_dir"] = out          # 只在内存里改，不落 config.json
        st = Store(os.path.join(tmp, "t.db"))
        st.init()
        a.store = st

        # 1) 坏参数一律回落默认档
        ck("_to_int 容错", _to_int("abc", 8, 1, 100) == 8 and _to_int(None, 8) == 8
           and _to_int("40", 8, 1, 100) == 40 and _to_int(99999, 8, 1, 100) == 100)

        # 2) 占位互斥：占着的时候第二个任务进不来
        a.st["running"] = None
        ck("claim 空闲可占", a._claim("gen") is True)
        ck("claim 忙时拒绝", a._claim("gen") is False)
        ck("busy 报占用者", a._busy() and a._busy_msg().endswith("gen"))
        a._release()
        ck("release 后自由", a._claim("load") is True)
        a._release()

        # 3) 停止不能顺延：上一次留下的停止位不能把下一个任务掐死
        a._stop.set()
        ck("claim 清停止位", a._claim("gen") is True and a._stop.is_set() is False)
        a._release()

        # 4) 正常一张：落盘 + 进历史库 + running 归位
        a.mgr = FakeMgr(a)
        a._do_gen({"mode": "gen", "prompt": "p", "size": "64x64",
                   "steps": "8", "seed": 7, "count": 1})
        files = os.listdir(out)
        ck("正常出图落盘", len(files) == 1, files)
        ck("正常出图进库", st.stats()["count"] == 1)
        ck("跑完 running 归位", a.st["running"] is None)

        # 5) 一批多张：每张都要各自落盘（秒级时间戳会撞名，历史坑）
        a._stop.clear()
        a._do_gen({"mode": "gen", "prompt": "p", "size": "64x64",
                   "steps": "8", "seed": -1, "count": 3})
        ck("一批 3 张落 3 个文件", len(os.listdir(out)) == 4, sorted(os.listdir(out)))
        ck("3 张各自进库", st.stats()["count"] == 4, st.stats())

        # 6) 坏 steps/size：不再抛在 try 外，running 必须归位
        a._do_gen({"mode": "gen", "prompt": "p", "size": "坏值",
                   "steps": "abc", "seed": None, "count": "xyz"})
        ck("坏参数不卡 running", a.st["running"] is None)
        ck("坏参数仍出一张", len(os.listdir(out)) == 5, sorted(os.listdir(out)))

        # 7) 中途停止：pipeline 照样返回图，但不许落盘、不许进库
        before_files = set(os.listdir(out))
        before_rows = st.stats()["count"]
        a._stop.clear()
        a.mgr = FakeMgr(a, halt=True)
        a._do_gen({"mode": "gen", "prompt": "p", "size": "64x64",
                   "steps": "8", "seed": 7, "count": 1})
        ck("停止时不落半成品", set(os.listdir(out)) == before_files,
           sorted(set(os.listdir(out)) - before_files))
        ck("停止时不进历史库", st.stats()["count"] == before_rows)
        ck("停止后 running 归位", a.st["running"] is None)
        ck("停止后状态文案", "已停止" in str(a.st["status"]), a.st["status"])

        # 7) 画廊清空：只删图、只清被删掉的记录，被占用的留着
        a._stop.clear()
        a.mgr = FakeMgr(a)
        a._do_gen({"mode": "gen", "prompt": "keepme", "size": "64x64",
                   "steps": "8", "seed": 7, "count": 1})
        rows = st.stats()["count"]
        ck("清空前有图有记录", rows >= 3 and len(os.listdir(out)) >= 3,
           "rows=%d files=%d" % (rows, len(os.listdir(out))))
        r = a.gallery_clear()
        ck("清空返回 ok", r.get("ok") is True, r)
        ck("图片已删净", os.listdir(out) == [])
        ck("记录同步清掉", st.stats()["count"] == 0)

        st._db.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%s" % ("TASK TEST PASS" if not fails else "TASK TEST FAIL: %s" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
