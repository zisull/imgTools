# -*- coding: utf-8 -*-
"""新形状（MiniMaxH3ReferenceToVideo 那张）写路径干跑：认接线、上传图、落值、对序列化——
到「点运行」之前一步为止。不提交任务、不扣积分，改的只是页面内存里那张图。

为什么要这一趟：这张图的提示词/时长/尺寸都不在主节点自己身上，而是从
Text / PrimitiveFloat / ResolutionSelector 经 SetNode→GetNode 接进来的。
接线认错了不会报错，只会安静地交出模板里那段原来的故事板——钱照扣，片是别人的。
所以提交前必须真机量一次：序列化里到底有没有我们这段提示词、这几张图的文件名。

用法（另起一只浏览器，别顶软件保活那两只窗口）：
  python scripts/h3_kj_dryrun.py --port 9345 --secs 5 --wh 1280x720
参考图默认从 data 里挑一张现成的，没有就自己画一张纯色图当靶子。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def a_ref(root, pick=""):
    """一张参考图：用户给的就用给的，否则在 data 里找现成的，再不行画一张。"""
    if pick:
        return pick if os.path.isfile(pick) else ""
    for base, _dirs, files in os.walk(os.path.join(root, "data")):
        for fn in files:
            if fn.lower().endswith((".png", ".jpg", ".jpeg")) and "trash" not in base:
                return os.path.join(base, fn)
    try:
        from PIL import Image
    except ImportError:
        return ""
    out = os.path.join(os.environ.get("TEMP", "/tmp"), "qic_kj_dryref.png")
    Image.new("RGB", (512, 512), (96, 128, 176)).save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf", default="", help="工作流编号或地址，默认用软件内置那张")
    ap.add_argument("--acct", default="", help="账号 id，默认用账号库第一个")
    ap.add_argument("--ref", action="append", default=[],
                    help="参考图路径，可重复给多张（试多图引用）；留空自动挑一张")
    ap.add_argument("--noref", action="store_true", help="一张图都不给（只验接线）")
    ap.add_argument("--secs", type=int, default=5)
    ap.add_argument("--wh", default="1280x720", help="界面口径的宽高")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--port", type=int, default=9345,
                    help="另起一只浏览器的调试端口：软件保活占着 9333/9334")
    ap.add_argument("--profile", default="", help="配套的 user-data-dir，留空＝TEMP 临时一份")
    ap.add_argument("--keep", action="store_true", help="跑完不关浏览器（人可以进页面看一眼）")
    a = ap.parse_args()

    import socket
    with socket.socket() as s:
        s.settimeout(0.6)
        if s.connect_ex(("127.0.0.1", a.port)) == 0:
            print("✗ 端口 %d 上已经有一只浏览器：换一个 --port" % a.port)
            return 1
    if not a.profile:
        a.profile = os.path.join(os.environ.get("TEMP", "/tmp"),
                                 "qic_kj_dry_%d" % a.port)

    # 只读账号库那份登录态（不写它），也不设 QIC_CONFIG：数据根一挪就没有号了
    from cloudkit import store as cs
    from cloudkit import gen as cg
    from cloudkit.browser import BrowserHost

    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8")) \
        if os.path.isfile(os.path.join(ROOT, "config.json")) else {}
    cloud = dict(cfg.get("cloud") or {})
    cloud["port"] = a.port
    cloud["show_browser"] = bool(cloud.get("show_browser", True))
    store = cs.AccountStore(ROOT)
    rows = [x for x in store.list() if (store.load(x["id"]) or {}).get("cookies")]
    if not rows:
        print("账号库里没有一个带登录态的号：先到软件「环境管理 → 云端账号」新建登录并保存")
        return 1
    row = [x for x in rows if x["id"] == (a.acct or rows[0]["id"])][0]
    state = store.load(row["id"]) or {}
    host = BrowserHost(ROOT, cloud, port=a.port, profile=a.profile)
    g = cg.CloudH3(ROOT, cloud, store, host, log=lambda *x: print("   ", " ".join(str(y) for y in x)))
    wid = cg.wf_id_of(a.wf) or cg.GOLDFISH_WF
    url = cg.WF_URL % wid
    print("· 账号「%s」· 工作流 %s · 端口 %d" % (row["name"], wid, a.port))
    print("· 地址 %s" % url)

    if a.noref:
        refs = []
    elif a.ref:
        miss = [x for x in a.ref if not os.path.isfile(x)]
        if miss:
            print("✗ 参考图找不到：%s" % "、".join(miss))
            return 1
        refs = list(a.ref)
    else:
        one = a_ref(ROOT, "")
        if not one:
            print("✗ 一张参考图都找不到（--ref 给一张）")
            return 1
        refs = [one]
    code = 1
    try:
        with host.lock:
            host.purpose = "gen"
            # 走软件同一进页通路：灌快照→开页→点「我自己打开」→等画布
            tab = g._enter(state, row["id"], url, None, None)
            fid = g._wait_frame(tab, None)
            ids = g._wait_graph(tab, fid, None)
            print("· 画布：%s 个节点 · 主节点 %s · 输出节点 %s · 形状 %s"
                  % (ids.get("nodes"), ids.get("main"), ids.get("out"), ids.get("shape")))
            if ids.get("shape") != cg.SHAPE_KJ:
                print("✗ 这张不是新形状（%s）：干跑脚本只管虚拟节点那一种" % ids.get("shape"))
                return 1
            kmap = g._kj_map(tab, fid)
            print("· 槽位（<Picture N> → LoadImage）：%s"
                  % json.dumps(kmap.get("slots"), ensure_ascii=False))
            print("· 画幅可选：%s" % json.dumps(kmap.get("aspect"), ensure_ascii=False)[:220])
            print("· 尺寸那一格：%s · 每格 %s 像素"
                  % (json.dumps(kmap.get("res"), ensure_ascii=False)[:260],
                     kmap.get("multiple")))
            w, h = (int(x) for x in a.wh.lower().split("x"))
            size = cg.pick_size(w, h)
            files = []
            for i, path in enumerate(refs, 1):
                fn, sub = g.upload(path, state)
                files.append((i, (kmap.get("slots") or {}).get(i),
                              ("%s/%s" % (sub, fn)) if sub else fn))
                print("· 第 %d 张上传 → %s（槽位节点 %s）" % (i, fn, files[-1][1]))
            # 界面口径写编号（@1 @2）：picture_text 负责换成节点认的 <Picture N>
            prompt = a.prompt or ("一个女孩推门走进雨夜的旧书店，店主抬头，她认出了他 "
                                  + " ".join("@%d" % i for i in range(1, len(refs) + 1)))
            text, _n = cg.mention.picture_text(prompt, len(refs))
            print("· 提示词里 %d 个 <Picture> 引用：%s"
                  % (text.count("<Picture"), text[:80]))
            print("· 计划要写的每一格：")
            for it in (g._kj_writes(kmap, text, a.secs, size)
                       + [[(kmap.get("slots") or {}).get(i), "image", fn, False, "图%d" % i]
                          for i, _nid, fn in files]):
                print("    节点 %-6s 控件 %-14s 值 %s%s"
                      % (it[0], it[1], str(it[2])[:52].replace("\n", "⏎"),
                         "（必须是下拉里的值）" if it[3] else ""))
            if not files:
                print("· 没给参考图：只验接线与尺寸，不写图")
                g._write_kj(tab, fid, ids, kmap, text, a.secs, size, [])
            else:
                g._write_kj(tab, fid, ids, kmap, text, a.secs, size,
                            [(i, nid, fn) for i, nid, fn in files if nid])
            print("✓ 写入与序列化对账都过了（没点运行，不扣积分）")
            if a.keep:
                print("· --keep：浏览器留着，页面上能看到写进去的值；关掉它再结束")
                try:
                    input("按回车关掉这只浏览器…")
                except Exception:
                    pass
            code = 0
    except cg.CloudError as e:
        print("✗ %s" % e)
    except Exception as e:
        print("✗ 干跑炸了：%s" % str(e)[:200])
        import traceback
        traceback.print_exc()
    finally:
        if not a.keep:
            try:
                host.close()
            except Exception:
                pass
    return code


if __name__ == "__main__":
    sys.exit(main())
