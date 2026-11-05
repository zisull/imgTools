# -*- coding: utf-8 -*-
"""风格预设库回归：{prompt} 渲染、按引擎过滤、图片入库与清理、坏数据回落、js_api 形状。

跑法： .venv\\Scripts\\python.exe scripts\\style_test.py
全部落在临时目录（QIC_CONFIG 先指过去），不碰用户那份 config.json 与真数据目录。
"""
import atexit
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))

TMP = tempfile.mkdtemp(prefix="qic_style_test_")
os.environ["QIC_CONFIG"] = os.path.join(TMP, "config.json")
atexit.register(shutil.rmtree, TMP, True)

import preset            # noqa: E402
from app import App      # noqa: E402
from store import Store  # noqa: E402

RESULTS = []


def ok(name, cond, extra=""):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ((" · " + str(extra)) if extra else ""))


def put(path, body=b"PNGDATA"):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    return path


def main():
    data = preset.styles_dir(ROOT)
    ok("风格目录跟着配置目录走", data.startswith(TMP), data)

    # ---------- 第一次用：复制出厂那份 ----------
    items = preset.load(ROOT)
    ok("出厂清单能读出来", len(items) >= 8, len(items))
    ok("复制落盘了（不是每次重新合并）", os.path.isfile(preset.data_path(ROOT)))
    ok("每条都带 {prompt} 或至少能追加",
       all(p["tpl"] for p in items))
    ok("出厂每条 id 唯一", len({p["id"] for p in items}) == len(items))
    ok("出厂引擎标记都在认的集合里",
       all(set(p["eng"]) <= set(preset.ENGINE) for p in items))

    # ---------- 渲染：占位 / 追加 / 空原文的接缝 ----------
    p = {"tpl": "电影感写实，35mm：{prompt}", "neg": ""}
    ok("带占位就原位插", preset.render(p, "雨夜小巷") == "电影感写实，35mm：雨夜小巷",
       preset.render(p, "雨夜小巷"))
    ok("不含占位就接在原话后面", preset.render({"tpl": "胶片颗粒"}, "一只猫") == "一只猫，胶片颗粒",
       preset.render({"tpl": "胶片颗粒"}, "一只猫"))
    ok("空模板原样回", preset.render({"tpl": ""}, "一只猫") == "一只猫")
    ok("占位换空原文不留「：，」", preset.render(p, "") == "电影感写实，35mm",
       preset.render(p, ""))
    ok("占位换空原文不留「，，」",
       "，，" not in preset.render({"tpl": "{prompt}，柔光，浅景深"}, ""))
    ok("空原文且模板只有占位→空串", preset.render({"tpl": "{prompt}"}, "") == "",
       repr(preset.render({"tpl": "{prompt}"}, "")))

    # ---------- 按引擎过滤 ----------
    mix = [{"id": "a", "tpl": "x", "eng": ["qwen"]},
           {"id": "b", "tpl": "y", "eng": ["h3"]},
           {"id": "c", "tpl": "z", "eng": []}]
    ok("千问页只列千问和通用",
       [x["id"] for x in preset.choose(mix, "qwen")] == ["a", "c"])
    ok("不点名引擎＝全给", [x["id"] for x in preset.choose(mix, "")] == ["a", "b", "c"])
    ok("没认识的引擎标记也别把人筛空",
       [x["id"] for x in preset.choose(mix, "bogus")] == ["a", "b", "c"])

    # ---------- 新增 / 图片入库 / 删除 ----------
    ext = put(os.path.join(TMP, "outside.png"))
    items, err = preset.upsert(ROOT, {"name": "测试档", "tpl": "冷色调，{prompt}",
                                      "eng": ["moss"], "thumb": ext, "refs": [ext]})
    ok("新增没报错", err == "", err)
    one = preset.find(items, "测试档") or [x for x in items if x["name"] == "测试档"][0]
    ok("缩略图收进了库内", one["thumb"].startswith("img/") or
       os.path.normcase(os.path.dirname(os.path.abspath(preset._abs(ROOT, one["thumb"])))) ==
       os.path.normcase(os.path.abspath(preset.img_dir(ROOT))), one["thumb"])
    ok("外部原图一个字没动", os.path.isfile(ext))
    abs_thumb = preset.paths(ROOT, one, "thumb")
    ok("能解析回绝对路径", bool(abs_thumb) and os.path.isfile(abs_thumb), abs_thumb)
    refs, lost = preset.paths(ROOT, one, "refs")
    ok("参考图解析得到、一张没丢", len(refs) == 1 and lost == 0, (refs, lost))

    _, err = preset.upsert(ROOT, {"name": "", "tpl": "x"})
    ok("空名被拦（点下去什么也不发生的预设不收）", bool(err), err)
    _, err = preset.upsert(ROOT, {"name": "空模板", "tpl": "  "})
    ok("空模板被拦", bool(err), err)

    items, err = preset.delete(ROOT, one["id"])
    ok("删除成功", err == "" and preset.find(items, one["id"]) is None, err)
    ok("库内副本跟着清掉", not os.path.isfile(abs_thumb))
    ok("外部原图还在（那是用户自己的东西）", os.path.isfile(ext))

    # ---------- 覆盖同 id 不重复长条 ----------
    items, _ = preset.upsert(ROOT, {"id": "sdead000", "name": "重复", "tpl": "{prompt} 冷色"})
    n1 = len(items)
    items, _ = preset.upsert(ROOT, {"id": "sdead000", "name": "重复", "tpl": "{prompt} 暖色"})
    ok("同 id 再存是覆盖不是新增", len(items) == n1, (n1, len(items)))
    ok("模板改到位了", preset.find(items, "sdead000")["tpl"].endswith("暖色"))

    # ---------- 坏数据 / 坏 JSON ----------
    bad = json.dumps([{"name": "脏数据", "tpl": "x", "eng": ["nonsense", "qwen", "qwen"],
                       "refs": ["r%d" % i for i in range(9)], "note": "长" * 200,
                       "evil": {"a": 1}}] +
                     [{"tpl": "没名字的条目也要有个 id"}, {"name": "没模板", "tpl": ""}],
                     ensure_ascii=False)
    with open(preset.data_path(ROOT), "w", encoding="utf-8") as f:
        f.write(bad)
    items = preset.load(ROOT)
    ok("脏字段夹住（引擎去重、参考图封顶、备注截断）",
       items[0]["eng"] == ["qwen"] and len(items[0]["refs"]) == preset.REF_MAX
       and len(items[0]["note"]) <= 80, items[0])
    ok("空模板那条不入库", all(x["tpl"] for x in items) and len(items) == 2, len(items))
    ok("没 id 的条目补出合法 id", all(preset.ID_RE.match(x["id"]) for x in items),
       [x["id"] for x in items])
    with open(preset.data_path(ROOT), "w", encoding="utf-8") as f:
        f.write("{不是 JSON")
    items = preset.load(ROOT)
    ok("坏 JSON 也能回落到出厂那份", len(items) >= 8, len(items))

    # ---------- 恢复出厂 ----------
    preset.upsert(ROOT, {"name": "临时加的", "tpl": "x"})
    items = preset.reset(ROOT)
    ok("恢复出厂后自己加的没了", preset.find(items, "临时加的") is None or
       all(x["name"] != "临时加的" for x in items), len(items))

    # ---------- 草稿：从画廊那一张的记账起草 ----------
    d = preset.draft({"prompt": "一只猫推开木门，阳光落在地板上", "negative": "模糊",
                      "file": "gen_x.png"}, "猫开门", "h3")
    ok("草稿带上提示词与反向", d["tpl"].startswith("一只猫") and d["neg"] == "模糊", d)
    ok("草稿点名引擎", d["eng"] == ["h3"], d["eng"])
    ok("草稿的缩略图就是那张本身", d["thumb"] == "gen_x.png")

    # ---------- js_api 形状 ----------
    a = App()
    a.store = Store(os.path.join(TMP, "history.db"))
    a.store.init()

    r = a.style_list("qwen")
    ok("style_list 回 items 且不带 base64",
       r.get("ok") and isinstance(r["items"], list) and
       all("thumb" not in x or isinstance(x["thumb"], str) for x in r["items"]) and
       all("url" not in x for x in r["items"]), len(r.get("items", [])))
    ids = [x["id"] for x in r["items"]]
    ok("千问这一路不含只给视频的风格",
       all("h3" not in x["eng"] or "qwen" in x["eng"] for x in r["items"]))
    r = a.style_list("no-such-engine")
    ok("不认识的引擎标记友好回全部", r.get("ok") and len(r["items"]) >= len(ids))

    r = a.style_apply(ids[0], "雨夜小巷")
    ok("style_apply 回渲染好的提示词", r.get("ok") and r["prompt"], r.get("name"))
    ok("style_apply 带着反向与参考图键", "negative" in r and "refs" in r and "lost" in r)
    r = a.style_apply("没有这个号")
    ok("套用到已被删的条目给一句话", not r.get("ok") and r.get("msg"), r)

    r = a.style_save({"name": "接口档", "tpl": "暖色，{prompt}", "eng": ["qwen"]})
    ok("style_save 成功", r.get("ok"), len(r.get("items", [])))
    new_id = [x["id"] for x in r["items"] if x["name"] == "接口档"]
    ok("新那条在清单里", bool(new_id), new_id)
    r = a.style_save({"name": "", "tpl": "x"})
    ok("style_save 空名把原因带回来", not r.get("ok") and "名字" in r.get("msg", ""), r)

    src = put(os.path.join(TMP, "outputs", "gen_api.png"))
    a.store.add(src, mode="gen", prompt="一只猫", negative="模糊",
                size="1024x1024", steps=8, seed=7, sec=1.0)
    r = a.style_draft(src)
    ok("style_draft 从历史库拿到提示词",
       r.get("ok") and r["preset"]["tpl"] == "一只猫" and r["preset"]["neg"] == "模糊", r)
    ok("草稿按那一张的出处点名引擎：gen＝千问",
       r["preset"]["eng"] == ["qwen"], r["preset"].get("eng"))
    moss_png = put(os.path.join(TMP, "outputs", "moss_api.png"))
    a.store.add(moss_png, mode="moss", prompt="雪原上的狐", negative="低饱和",
                size="1024x1024", steps=8, seed=1, sec=1.0)
    ok("草稿认得 Moss 档：不挂到千问那一路",
       a.style_draft(moss_png)["preset"]["eng"] == ["moss"])
    r = a.style_draft(os.path.join(TMP, "没这个文件.png"))
    ok("草稿：文件没了给一句话", not r.get("ok"), r)
    ghost = put(os.path.join(TMP, "outputs", "gen_ghost.png"))
    ok("草稿：没记账的图给一句话", not a.style_draft(ghost).get("ok"))

    r = a.style_delete(new_id[0])
    ok("style_delete 成功且清单少了那条",
       r.get("ok") and all(x["name"] != "接口档" for x in r["items"]), len(r.get("items", [])))
    r = a.style_reset()
    ok("style_reset 回全量清单", r.get("ok") and len(r["items"]) >= 8, len(r.get("items", [])))
    ok("对外发的预设里绝不含 base64",
       all("base64" not in json.dumps(x) for x in r["items"]))

    print("\n%d/%d 通过" % (sum(RESULTS), len(RESULTS)))
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
