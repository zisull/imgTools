# -*- coding: utf-8 -*-
"""新形状那张默认工作流：真机跑一条短片，走软件同一个 run() 通路。

干跑（h3_kj_dryrun.py）能证明接线认对、值写进、序列化对账过，但证不了平台那头
真能出片——模型档、显存、这条虚拟节点链在执行时会不会炸，只有真交一次才知道。
所以这个脚本只干一件事：照界面的参数口径调 CloudH3.run()，回来把文件、时长、
帧数、尺寸报出来。

另起一只浏览器（软件保活占着 9333/9334），账号库那份登录态只读。
用法：
  python scripts/h3_kj_gen.py --port 9345 --secs 5 --wh 1280x720 --ref 图.png
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf", default="", help="工作流编号或地址，默认用软件内置那张")
    ap.add_argument("--acct", default="", help="账号 id，默认账号库第一个")
    ap.add_argument("--ref", action="append", default=[], help="参考图，可重复")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--secs", type=int, default=5)
    ap.add_argument("--wh", default="1280x720")
    ap.add_argument("--port", type=int, default=9346)
    ap.add_argument("--profile", default="")
    a = ap.parse_args()

    import socket
    with socket.socket() as s:
        s.settimeout(0.6)
        if s.connect_ex(("127.0.0.1", a.port)) == 0:
            print("✗ 端口 %d 上已经有一只浏览器：换一个 --port" % a.port)
            return 1
    profile = a.profile or os.path.join(os.environ.get("TEMP", "/tmp"),
                                        "qic_kj_gen_%d" % a.port)

    # 只读账号库那份登录态：这条要真出片，就得用人家真登录的那个号
    from cloudkit import store as cs
    from cloudkit import gen as cg
    from cloudkit.browser import BrowserHost

    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8")) \
        if os.path.isfile(os.path.join(ROOT, "config.json")) else {}
    cloud = dict(cfg.get("cloud") or {})
    cloud["port"] = a.port
    # 把配置里那两格抹掉：这一趟要验的是软件内置那张默认画布，
    # 不是用户自己存过的那份本地工作流（wf_src 会退回去读它）
    cloud.pop("workflow", None)
    cloud.pop("wf_host", None)
    store = cs.AccountStore(ROOT)
    rows = [x for x in store.list() if (store.load(x["id"]) or {}).get("cookies")]
    if not rows:
        print("账号库里没有一个带登录态的号")
        return 1
    acct = a.acct or rows[0]["id"]
    refs = [x for x in a.ref if x]
    if not refs:
        print("✗ 这张图按参考生成：至少给一张 --ref")
        return 1
    w, h = (int(x) for x in a.wh.lower().split("x"))
    prompt = a.prompt or ("一个女孩推门走进雨夜的旧书店，店主抬头，她认出了她 "
                          + " ".join("<Picture %d>" % i for i in range(1, len(refs) + 1)))
    host = BrowserHost(ROOT, cloud, port=a.port, profile=profile)
    g = cg.CloudH3(ROOT, cloud, store, host,
                   log=lambda *x: print("   ", " ".join(str(y) for y in x)))
    p = {"prompt": prompt, "seconds": a.secs, "width": w, "height": h,
         "refs": refs, "wf": a.wf or cg.GOLDFISH_WF, "acct": acct}
    print("· 账号 %s · 工作流 %s · %ds · %dx%d · %d 张参考图"
          % (acct, cg.wf_id_of(a.wf) or cg.GOLDFISH_WF, a.secs, w, h, len(refs)))
    t0 = time.time()
    code = 1
    try:
        with host.lock:
            out = g.run(p, on_progress=lambda m: print("  ← %s" % m),
                        should_stop=lambda: False)
        cost = time.time() - t0
        print("✓ 出片 %s（%.0f 字节 · 全程 %.0f 秒 · 形状 %s · taskid %s）"
              % (out, os.path.getsize(out) if out and os.path.isfile(out) else 0,
                 cost, g.shape, getattr(g, "_task_id", "")))
        try:
            import subprocess
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                "-show_entries", "stream=width,height,nb_frames,r_frame_rate",
                                "-of", "default=nw=1", out],
                               capture_output=True, text=True, timeout=60)
            print("· 片子本身：%s" % " ".join(r.stdout.split()) or r.stderr[:120])
        except Exception as e:
            print("· 没量到片子参数（%s）：有 ffmpeg 就能报宽高和帧数" % str(e)[:60])
        code = 0
    except cg.CloudError as e:
        print("✗ %s（跑了 %.0f 秒）" % (e, time.time() - t0))
    except Exception as e:
        print("✗ 真机跑炸了：%s" % str(e)[:200])
        import traceback
        traceback.print_exc()
    finally:
        try:
            host.close()
        except Exception:
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
