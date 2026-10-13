# -*- coding: utf-8 -*-
"""M5 自测：历史库读写 + 模型清单 + 画廊合并元信息。不启窗口、不生成。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "webui"), os.path.join(ROOT, "engine")):
    sys.path.insert(0, _p)

from store import Store  # noqa: E402


def test_store():
    db = os.path.join(ROOT, "data", "_selftest.db")
    st = Store(db)
    st.init()
    f = "outputs/gen_selftest.png"
    st.add(f, mode="gen", prompt="p", negative="n", size="1024x1024",
           steps=8, seed=42, sec=28.4)
    m = st.meta_map([f])
    assert m[f]["mode"] == "gen" and m[f]["seed"] == 42, m
    st.set_fav(f, True)
    assert st.meta_map([f])[f]["fav"] == 1
    st.set_fav(f, False)
    assert st.meta_map([f])[f]["fav"] == 0
    # 库里没记录的普通文件不炸
    assert "other.png" not in st.meta_map(["other.png"])
    # prune：只留清单里还活着的
    assert st.prune(set()) == 1
    assert not st.meta_map([f]), "prune 后应清空"
    stats = st.stats()
    assert stats["count"] == 0 and stats["fav"] == 0, stats
    st.remove(f)
    st._db.close()
    os.remove(db)
    print("store OK")


def test_app():
    from app import App
    a = App()
    r = a.models_list()
    assert r["ok"] and isinstance(r["items"], list), r
    names = [x["name"] for x in r["items"]]
    print("models_list:", [(x["name"], x["gb"], x["shards"], x["index"], x["active"]) for x in r["items"]])
    assert "Qwen-Image-2.1-Turbo" in names, names
    assert r["items"][names.index("Qwen-Image-2.1-Turbo")]["index"] is True
    bad = a.models_download("bad repo!!", "")
    assert not bad["ok"], bad
    g = a.gallery_list()
    assert g["ok"] and "items" in g and "stats" in g, g
    print("gallery_list: %d 张 · stats=%s" % (len(g["items"]), g["stats"]))
    d = a.gallery_delete(os.path.join(ROOT, "outputs", "不存在的图.png"))
    print("gallery_delete(缺失):", d)
    print("app OK")


if __name__ == "__main__":
    test_store()
    test_app()
    print("M5 SELFTEST PASS")
