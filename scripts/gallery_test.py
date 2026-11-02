# -*- coding: utf-8 -*-
"""画廊删除撤销回归：删除进回收站、撤销搬回原处、历史参数与收藏位原样回来。

跑法： .venv\\Scripts\\python.exe scripts\\gallery_test.py
不碰真输出目录、真历史库：输出/回收站/库全部落在临时目录。
"""
import atexit
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))

TMP = tempfile.mkdtemp(prefix="qic_gal_test_")
os.environ["QIC_CONFIG"] = os.path.join(TMP, "config.json")
atexit.register(shutil.rmtree, TMP, True)

from app import App            # noqa: E402
from store import Store        # noqa: E402

RESULTS = []


def ok(name, cond, extra=""):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ((" · " + str(extra)) if extra else ""))


def main():
    a = App()
    out = os.path.join(TMP, "outputs")
    os.makedirs(out, exist_ok=True)
    a.cfg["console"]["output_dir"] = out
    # App() 已经在真库里建好连接：换成沙箱库与沙箱回收站，一个字节都不碰用户的
    a.store = Store(os.path.join(TMP, "history.db"))
    a.store.init()
    a._trash_dir = os.path.join(TMP, "trash")
    a._trash = []

    def put(name, body=b"PNGDATA"):
        p = os.path.join(out, name)
        with open(p, "wb") as f:
            f.write(body)
        return p

    def trash_names():
        try:
            return os.listdir(a._trash_dir)
        except OSError:
            return []

    # ---------- 单张删除 → 撤销 ----------
    png = put("gen_undo.png")
    a.store.add(png, mode="gen", prompt="一只猫推开木门", negative="blurry",
                size="1024x1024", steps=8, seed=42, sec=12.3)
    a.store.set_fav(png, True)
    row = a.store.get(png)

    r = a.gallery_delete(png)
    ok("删除成功并声明可撤销", r.get("ok") and r.get("undo"), r)
    ok("输出目录里已经看不到这张", not os.path.exists(png))
    ok("文件进了回收站（不是真删）", len(trash_names()) == 1, trash_names())
    ok("历史库那一行跟着走", a.store.get(png) is None)

    r = a.gallery_undo()
    ok("撤销成功", r.get("ok"), r)
    ok("文件回到原路径且字节一致",
       os.path.isfile(png) and open(png, "rb").read() == b"PNGDATA")
    ok("回收站清空", trash_names() == [], trash_names())
    back = a.store.get(png)
    ok("参数原样回来（提示词/种子/耗时/收藏位）",
       back and back["prompt"] == "一只猫推开木门" and back["seed"] == 42
       and back["fav"] == 1 and abs(back["ts"] - row["ts"]) < 1e-6, back)
    ok("没有可撤销的删除时给话", not a.gallery_undo().get("ok"))

    # ---------- 连删两张：后进先出 ----------
    p1, p2 = put("gen_a.png"), put("gen_b.png")
    a.gallery_delete(p1)
    a.gallery_delete(p2)
    ok("连删两张都只离开目录、没丢字节",
       not os.path.exists(p1) and not os.path.exists(p2) and len(trash_names()) == 2)
    a.gallery_undo()
    ok("第一次撤销先回最后删的那张", os.path.exists(p2) and not os.path.exists(p1))
    a.gallery_undo()
    ok("再撤一次回前一张", os.path.exists(p1))

    # ---------- 原位置又有同名文件：拒绝覆盖，且条目还在栈里 ----------
    p3 = put("gen_clash.png", b"OLD")
    a.gallery_delete(p3)
    put("gen_clash.png", b"NEW")            # 删完又有同名新文件落进来
    r = a.gallery_undo()
    ok("原位置被占时拒绝撤销", not r.get("ok") and "同名" in r.get("msg", ""), r)
    ok("拒绝后条目留在栈里（处理完还能再撤）", len(a._trash) == 1, len(a._trash))
    os.remove(os.path.join(out, "gen_clash.png"))
    r = a.gallery_undo()
    ok("腾开位置后撤销成功且搬回的是旧文件",
       r.get("ok") and open(p3, "rb").read() == b"OLD")

    # ---------- 越界与清空 ----------
    outside = os.path.join(TMP, "outside.png")
    with open(outside, "wb") as f:
        f.write(b"X")
    ok("输出目录外的文件拒绝删除", not a.gallery_delete(outside).get("ok"))
    ok("越界拒绝后文件还在", os.path.isfile(outside))

    p4 = put("gen_clear.png")
    a.gallery_delete(p4)
    a.gallery_clear()
    ok("清空按确认语不进回收站（撤销栈一起清掉）",
       not os.listdir(a._trash_dir) and len(a._trash) == 0)

    print("\nGALLERY TEST: %s" % ("PASS" if all(RESULTS) else "FAIL"))
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
