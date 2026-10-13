# -*- coding: utf-8 -*-
"""M4 全链路自测：真 App + 真 FastAPI + HTTP 出图（验收=本机 curl 全链路）
跑：  .venv\\Scripts\\python.exe scripts\\m4_selftest.py
链路：health → 鉴权/参数负例 → generations 512 出图 → 轮询 → 下载 PNG
      → edits 上传参考图再出一张。收尾把服务关掉、配置还原。
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "webui"), os.path.join(ROOT, "engine")):
    if p not in sys.path:
        sys.path.insert(0, p)

import requests  # noqa: E402
from app import App  # noqa: E402

BASE = ""
H = {}


def wait_task(tid, limit=420):
    t0 = time.time()
    while True:
        j = requests.get(BASE + "/v1/tasks/" + tid, headers=H, timeout=10).json()
        print("  [%6.1fs] %s -> %s" % (time.time() - t0, tid, j["status"]))
        if j["status"] in ("done", "failed"):
            return j
        if time.time() - t0 > limit:
            raise SystemExit("❌ 任务超时没结束")
        time.sleep(3)


def download(iid):
    r = requests.get(BASE + "/v1/images/" + iid, headers=H, timeout=30)
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG", \
        "下载失败 %s" % r.status_code
    out = os.path.join(ROOT, "outputs", "m4_curl_%s.png" % iid)
    with open(out, "wb") as f:
        f.write(r.content)
    from PIL import Image
    im = Image.open(out)
    print("  图 %s %s %s" % (im.size, im.mode, out))
    return out


def main():
    global BASE, H
    a = App()
    r = a.api_set({"enabled": True, "lan": False})
    assert r["ok"], "服务起不来：" + r.get("msg", "?")
    port = a.cfg["api"]["port"]
    BASE = "http://127.0.0.1:%d" % port
    H = {"Authorization": "Bearer " + r["state"]["cfg"]["token"]}
    print("API 已启动 %s" % BASE)
    try:
        # 1) 体检（免令牌）
        j = requests.get(BASE + "/v1/health", timeout=10).json()
        assert j["ok"] and "model_loaded" in j, j
        print("health ok:", j)
        # 2) 负例：错令牌 401 / 坏 size 400 / 空 prompt 400
        s = requests.get(BASE + "/v1/tasks/x",
                         headers={"Authorization": "Bearer wrong"}, timeout=10)
        assert s.status_code == 401, s.status_code
        s = requests.post(BASE + "/v1/images/generations", headers=H,
                          json={"prompt": "x", "size": "123x45"}, timeout=10)
        assert s.status_code == 400, s.text
        s = requests.post(BASE + "/v1/images/generations", headers=H,
                          json={"prompt": "  "}, timeout=10)
        assert s.status_code == 400, s.text
        print("鉴权与参数负例 ok")
        # 3) 全链路出图（首跑含模型载入）
        s = requests.post(BASE + "/v1/images/generations", headers=H,
                          json={"prompt": "A red fox sitting in fresh snow, "
                                          "crisp fur detail, telephoto wildlife shot",
                                "size": "512x512", "n": 1, "seed": 42}, timeout=15)
        tid = s.json()["task_id"]
        print("generations 已受理", tid)
        j = wait_task(tid)
        assert j["status"] == "done", j
        gen_path = download(j["images"][0]["id"])
        # 4) 编辑链路：multipart 上传参考图
        with open(gen_path, "rb") as f:
            s = requests.post(BASE + "/v1/images/edits", headers=H,
                              data={"prompt": "Turn it into a soft watercolor "
                                              "painting on a white background",
                                    "res": "512"},
                              files={"image": ("ref.png", f, "image/png")},
                              timeout=30)
        assert s.status_code == 200, s.text
        tid = s.json()["task_id"]
        print("edits 已受理", tid)
        j = wait_task(tid)
        assert j["status"] == "done", j
        download(j["images"][0]["id"])
        print("✅ M4 全链路通过：health/鉴权/负例/出图/编辑/下载")
    finally:
        a.api_set({"enabled": False})
        print("API 服务已关闭，配置还原")


if __name__ == "__main__":
    main()
