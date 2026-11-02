# -*- coding: utf-8 -*-
"""H3 云端纯 HTTP 探针：不开浏览器，只用账号快照里的 Rh-* 鉴权值问 API。

这一关决定架构：
  · 若 object_info / history 用 cookie 就能读，且 POST /prompt 空图回的是
    400（校验失败）而不是 401/403 —— 说明生成可以纯协议走，浏览器只负责登录一次；
  · 若回 401/403 —— 说明会话值和浏览器绑定，得退回「浏览器里点执行 + 读控件」。

只发两种请求：GET（只读）和 POST /prompt 且 prompt 为空对象。
空图在 ComfyUI 侧必定校验失败，进不了队列，不建任务、不扣积分。
任何鉴权值都不打印，只报 HTTP 码与响应前若干字节的打码结果。

用法：
  python scripts/h3_http_probe.py                 # 用档案里第一个账号
  python scripts/h3_http_probe.py --acct acc_xxx
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ORIGIN = "https://www.runninghub.cn"
# 托管 ComfyUI 的 apiURL 是相对路径，origin 就是站内根（浏览器里 GET /history 已通过）
AUTH_KEYS = ("Rh-Comfy-Auth", "Rh-Identify")


def mask(s):
    return re.sub(r"(Rh-[A-Za-z_-]+=)[^&\s]+", r"\1***", str(s or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--acct", default="")
    a = ap.parse_args()

    os.environ.setdefault("QIC_CONFIG", os.path.join(
        os.environ.get("TEMP", "/tmp"), "qic_cloud_probe_config.json"))
    from cloudkit import store as cs

    store = cs.AccountStore(ROOT)
    accts = store.list()
    if not accts:
        print("账号库是空的：先到软件「环境管理 → 云端账号」新建登录并保存")
        return 1
    aid = a.acct or accts[0]["id"]
    row = [x for x in accts if x["id"] == aid][0]
    state = store.load(aid) or {}
    hdrs = cs.auth_headers(state.get("cookies"), state.get("storage"))
    cookie = "; ".join("%s=%s" % (c.get("name"), c.get("value"))
                       for c in (state.get("cookies") or []) if c.get("name"))
    print("· 账号「%s」· cookie %d 条 · Rh-* 鉴权名 %d 个（值不打印）"
          % (row["name"], len(state.get("cookies") or []), len(hdrs)))
    print("· 探针要用的两个头名在不在：%s"
          % ", ".join("%s=%s" % (k, "有" if hdrs.get(k) else "缺") for k in AUTH_KEYS))
    missing = [k for k in AUTH_KEYS if not hdrs.get(k)]
    if missing:
        print("✗ 快照里没有 %s：这个登录态可能过期或域名没兜住，回软件重新保存一次" % "/".join(missing))
        return 1

    try:
        import requests
    except ImportError:
        print("✗ 主 .venv 没装 requests")
        return 1

    def url(ep):
        q = "&".join("%s=%s" % (k, hdrs[k]) for k in AUTH_KEYS)
        return "%s/%s?%s" % (ORIGIN, ep.lstrip("/"), q)

    heads = {"Cookie": cookie, "Referer": ORIGIN + "/", "User-Agent":
             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
    out = 1
    try:
        for ep in ("history", "object_info"):
            r = requests.get(url(ep), headers=heads, timeout=40)
            txt = r.text or ""
            hint = ""
            if ep == "object_info":
                hint = " · 含主节点=%s · 共 %d 字节" % (
                    "FeiHouEasyH3RH" in txt, len(txt))
            print("· GET  %-12s → HTTP %s · %s%s"
                  % (ep, r.status_code, mask(txt[:100]).replace("\n", " "), hint))
        # 空图必定校验失败：证明「提交口能用」，又绝不会真起任务
        body = {"prompt": {}, "client_id": "qic-probe"}
        # nginx 常按「POST 必须有同源 Origin」放行，所以逐个变体试：
        # 带 Origin / 走 /api 前缀 / 两者都换。全用空图，任何一路都不可能起任务。
        variants = [
            ("prompt + Origin", "prompt",
             dict(heads, **{"Content-Type": "application/json",
                            "Origin": ORIGIN})),
            ("api/prompt", "api/prompt",
             dict(heads, **{"Content-Type": "application/json",
                            "Origin": ORIGIN})),
            ("prompt 无 Origin", "prompt",
             dict(heads, **{"Content-Type": "application/json"})),
        ]
        code = 0
        for label, ep, h in variants:
            r = requests.post(url(ep), headers=h, data=json.dumps(body), timeout=40)
            code = r.status_code
            print("· POST %-16s → HTTP %s · %s" % (label, r.status_code,
                  mask(r.text[:160]).replace("\n", " ")))
            if r.status_code == 400:
                break
        if code == 400:
            print("✓ 结论：纯 HTTP 可提交——浏览器只负责登录，生成走协议。")
            out = 0
        elif code in (401, 403):
            print("✗ 结论：鉴权值和浏览器会话绑着，得在页面里点执行。")
            out = 2
        else:
            print("? 结论：码 %s 不在预期里（既没通过也没被拒），实现时按 DOM 路径兜底。"
                  % code)
            out = 3
    except Exception as e:
        print("✗ 请求出错：%s" % str(e)[:200])
        out = 1
    return out


if __name__ == "__main__":
    sys.exit(main())
