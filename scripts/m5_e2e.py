# -*- coding: utf-8 -*-
"""M5 端到端：真引擎生成 512 一张 → 历史库有记录 → 收藏 → 删图删行。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "webui"), os.path.join(ROOT, "engine")):
    sys.path.insert(0, _p)

from app import App  # noqa: E402


def main():
    a = App()
    g = {"mode": "gen", "prompt": "a small red apple on a white table, product photo",
         "negative": "", "size": "512x512", "steps": "8", "seed": 7, "count": 1,
         "kv_cache": True}
    a._do_gen(g)
    saved = g.get("_saved") or []
    assert saved, "没落盘"
    f = saved[0]
    print("落盘:", f)

    items = a.gallery_list()["items"]
    it = next((x for x in items if x["file"] == f), None)
    assert it, "画廊里没有这张"
    assert it["mode"] == "gen" and it["seed"] == 7 and int(it["steps"]) == 8, it
    print("历史库参数:", it["size"], it["steps"], "步", it["sec"], "s")

    assert a.gallery_fav(f, True)["ok"]
    it = next(x for x in a.gallery_list()["items"] if x["file"] == f)
    assert it["fav"] == 1, it
    print("收藏 OK")

    assert a.gallery_delete(f)["ok"]
    assert f not in [x["file"] for x in a.gallery_list()["items"]]
    assert not a.store.meta_map([f]), "删图后库行应被带走"
    print("删除对账 OK")
    print("M5 E2E PASS")


if __name__ == "__main__":
    main()
