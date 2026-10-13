# -*- coding: utf-8 -*-
"""API 任务链路回归（不碰显存）：HTTP 提交 → 队列 → 抢任务位 → _do_gen → 取图。

PipelineMgr 用假对象顶掉，输出目录/历史库都落临时文件，端口取 18765 避开
正在运行的控制台。验证的是这一段调度与鉴权逻辑，不是模型本身。
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "webui"), os.path.join(ROOT, "engine")):
    sys.path.insert(0, _p)

from app import App                      # noqa: E402
from store import Store                   # noqa: E402
from api_server import ApiServer          # noqa: E402
from task_test import FakeMgr             # noqa: E402

PORT = 18765
TOK = "testtoken123"


def req(path, token=TOK, body=None, method=None):
    url = "http://127.0.0.1:%d%s" % (PORT, path)
    data = None
    hdr = {"Authorization": "Bearer " + token} if token else {}
    if body is not None:
        data = json.dumps(body).encode()
        hdr["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            raw = resp.read()
            ct = resp.headers.get("content-type", "")
            return resp.status, (raw if "json" not in ct else json.loads(raw))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:120]


def wait_status(api, jid, want, timeout=25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st, j = req("/v1/tasks/" + jid)
        if st == 200 and j.get("status") in (want, "failed"):
            return j
        time.sleep(0.4)
    return {"status": "超时没等到 " + want}


def main():
    tmp = tempfile.mkdtemp(prefix="qic_api_test_")
    out = os.path.join(tmp, "outputs")
    os.makedirs(out, exist_ok=True)
    fails = []

    def ck(name, cond, extra=""):
        print("%-32s %s %s" % (name, "PASS" if cond else "FAIL", extra))
        if not cond:
            fails.append(name)

    a = App()
    a.cfg["console"]["output_dir"] = out
    a.cfg["api"]["token"] = TOK
    st = Store(os.path.join(tmp, "t.db"))
    st.init()
    a.store = st
    a.mgr = FakeMgr(a)                    # 关键：绝不让 _do_gen 去碰真模型
    srv = ApiServer(a)
    ok = srv.start("127.0.0.1", PORT)
    try:
        ck("监听起来了", ok is True, ok)

        s, h = req("/v1/health", token=None)
        ck("health 免鉴权", s == 200 and h.get("ok"), h)
        s, _ = req("/v1/health", token="WRONG")
        s2, _ = req("/v1/tasks/nope", token="WRONG")
        ck("health 不鉴权 / 任务鉴权", s == 200 and s2 == 401, (s, s2))

        # UI 正在跑时，API 任务只能排队，不能挤进同一个 pipeline
        a.st["running"] = None
        claimed = a._claim("gen")
        s, j = req("/v1/images/generations", body={"prompt": "a red fox",
                                                  "size": "512x512", "n": 2})
        ck("提交拿到 task_id", s == 200 and j.get("task_id"), j)
        jid = j.get("task_id", "")
        time.sleep(1.5)
        s, q = req("/v1/tasks/" + jid)
        ck("UI 占用时只排队", q.get("status") == "queued", q.get("status"))
        ck("排队期间没偷偷出图", os.listdir(out) == [], os.listdir(out))
        a._release()                      # 放行：worker 下一轮就该抢到任务位
        done = wait_status(srv, jid, "done")
        ck("放行后跑完", done.get("status") == "done", done)
        ck("两张各落一个文件", len(os.listdir(out)) == 2, sorted(os.listdir(out)))
        names = sorted(os.listdir(out))
        ck("两个文件名不重复", len(set(names)) == 2, names)
        ck("跑完释放任务位", a.st["running"] is None, a.st["running"])
        ck("两条都进了历史库", st.stats()["count"] == 2, st.stats())

        imgs = done.get("images") or []
        ck("任务回两个图 id", len(imgs) == 2, imgs)
        if imgs:
            s, raw = req(imgs[0]["url"])
            ck("取回的是 PNG 字节", s == 200 and raw[:8] ==
               b"\x89PNG\r\n\x1a\n", s)
        s, _ = req("/v1/images/generations", body={"prompt": "", "size": "512x512"})
        ck("空 prompt 被拒", s == 400, s)
        s, _ = req("/v1/images/generations", body={"prompt": "x", "size": "999x999"})
        ck("非法 size 被拒", s == 400, s)
    finally:
        srv.stop()
        st._db.close()
        a._stop.set()
        shutil.rmtree(tmp, ignore_errors=True)
        time.sleep(0.5)

    print("\n%s" % ("API TASK TEST PASS" if not fails
                    else "API TASK TEST FAIL: %s" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
