# -*- coding: utf-8 -*-
"""把官方 MiniMax H3 工作流模板（UI 格式）打成可读的节点图，供手写 API 模板对照。

只读，不改任何文件；用完可以留着，下次换 ComfyUI 版本再跑一遍看官方模板有没有变。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, "comfyui", ".venv", "lib", "site-packages",
                   "comfyui_workflow_templates_json", "templates")


def link_endpoints(links, lid):
    """links 既可能是 [id, from, from_slot, to, to_slot, type] 也可能是 dict。"""
    for lk in links or []:
        if isinstance(lk, dict):
            if lk.get("id") == lid:
                return lk.get("origin_id"), lk.get("origin_slot")
        elif isinstance(lk, list) and lk and lk[0] == lid:
            return lk[1], lk[2]
    return None, None


def main(name):
    d = json.load(open(os.path.join(TPL, name), encoding="utf-8"))
    byid = {n["id"]: n for n in d["nodes"]}
    for n in sorted(d["nodes"], key=lambda x: x["id"]):
        print("── %s  %s" % (n["id"], n["type"]))
        wv = n.get("widgets_values_named")
        if wv:
            print("   widgets:", json.dumps(wv, ensure_ascii=False)[:400])
        if n.get("widgets_values") is not None and not wv:
            print("   widgets_values:", json.dumps(n["widgets_values"], ensure_ascii=False)[:400])
        for i in n.get("inputs") or []:
            if i.get("link") is None:
                continue
            src, slot = link_endpoints(d.get("links"), i["link"])
            print("   in %-18s <- %s(%s)[%s]" % (i["name"], src, byid[src]["type"] if src in byid else "?", slot))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "video_minimax_h3_i2v.json"))
