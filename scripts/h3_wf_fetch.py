# -*- coding: utf-8 -*-
"""把平台上那张工作流拉成本地快照（只读 JSON 口，不开浏览器、不建任务、不扣积分）。

以前拿一份本地工作流只能人到网页里「导出工作流」再拖进来；实测这两条只读口够用：
  · POST /api/portal/workflow/detail {workflowId, needContent:true} —— 名字/节点类型/用到的模型
  · POST /api/workflow/export        {workflowId}                   —— 画布 JSON（带 nodes/links）
鉴权 = localStorage 那份 Rh-Accesstoken 当 Bearer + client: WEB（cookie 也一并带上）。
账号库里存的登录态就够，不需要调试浏览器 —— 出片正跑着的时候也能问。

用法：
  python scripts/h3_wf_fetch.py                      # 拉默认那张，只报结构
  python scripts/h3_wf_fetch.py --out wf.json        # 落盘并过一遍 check_workflow_json
不打印 token 值。
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

SITE = "https://www.runninghub.cn"


def wf_id(s):
    m = re.search(r"workflow/(\d+)", str(s or ""))
    return m.group(1) if m else str(s or "").strip()


def api(path, body, token, cookie):
    """带 Bearer 打一发 POST，回 (状态码, 有效载荷)。

    两种回包形状都要认：`/api/portal/*` 裹一层 {code, data}，
    `/api/workflow/export` 直接把画布 JSON 摊在最外层（实测：顶层就是 last_link_id/nodes）。
    裹了才拆；data 是字符串再解一次 JSON。
    """
    import requests
    r = requests.post(SITE + path, json=body, timeout=40, headers={
        "Authorization": "Bearer " + token,
        "client": "WEB",
        "Content-Type": "application/json",
        "Cookie": cookie,
        "Origin": SITE,
        "Referer": SITE + "/",
    })
    try:
        d = r.json()
    except ValueError:
        return r.status_code, r.text[:200]
    if isinstance(d, dict) and "code" in d:
        data = d.get("data")
        if data is None:
            return r.status_code, "平台说：%s" % str(d.get("message") or d.get("msg") or
                                                  d.get("code"))[:120]
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                pass
        return r.status_code, data
    return r.status_code, d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf", default="", help="工作流编号或网页地址，默认用软件那张")
    ap.add_argument("--acct", default="", help="账号 id，默认用档案里第一个")
    ap.add_argument("--out", default="", metavar="FILE", help="把画布 JSON 存到这个文件")
    ap.add_argument("--detail", action="store_true", help="顺带打印平台那份详情（名字/模型）")
    a = ap.parse_args()

    # 全程只读（读账号快照、写的是 --out 指定的文件），所以不动 QIC_CONFIG：
    # 跟着仓库那份 config 走才拿得到用户真登录的号。
    from cloudkit import store as cs
    from cloudkit import gen as cg

    wid = wf_id(a.wf or cg.DEFAULT_WF)
    if not wid:
        print("没给工作流编号")
        return 1
    store = cs.AccountStore(ROOT)
    rows = [x for x in store.list() if (store.load(x["id"]) or {}).get("cookies")]
    if not rows:
        print("账号库里没有一个号：先到软件「环境管理 → 云端账号」新建登录并保存")
        return 1
    row = [x for x in rows if x["id"] == (a.acct or rows[0]["id"])][0]
    state = store.load(row["id"]) or {}
    auth = cs.auth_headers(state.get("cookies"), state.get("storage"))
    token = auth.get("Rh-Accesstoken") or ""
    if not token:
        print("这份登录态里没有 Rh-Accesstoken：重新登录保存一次")
        return 1
    cookie = "; ".join("%s=%s" % (c.get("name"), c.get("value"))
                       for c in (state.get("cookies") or []) if c.get("name"))
    print("· 用账号「%s」的登录态拉工作流 %s（token 不打印）" % (row["name"], wid))

    st, data = api("/api/workflow/export", {"workflowId": wid}, token, cookie)
    if not isinstance(data, dict) or not data.get("nodes"):
        print("✗ /api/workflow/export → HTTP %s，拿不到画布：%s"
              % (st, str(data)[:200]))
        return 1
    nodes = data.get("nodes") or []
    links = data.get("links") or []
    by_type = {}
    for n in nodes:
        by_type.setdefault(str(n.get("type")), []).append(n.get("id"))
    print("· 画布 JSON：%d 个节点 · %d 条连线 · 顶层键 %s"
          % (len(nodes), len(links), ", ".join(sorted(k for k in data)[:8])))
    for t in (cg.MAIN_TYPE, cg.OUT_TYPE):
        print("    %-18s → id %s" % (t, by_type.get(t)))
    print("    其余类型：%s" % ", ".join("%s×%d" % (k, len(v)) for k, v in
                                        sorted(by_type.items())
                                        if k not in (cg.MAIN_TYPE, cg.OUT_TYPE)))
    if a.detail:
        st2, d2 = api("/api/portal/workflow/detail",
                      {"workflowId": wid, "needContent": True}, token, cookie)
        if isinstance(d2, dict):
            print("· 详情 HTTP %s：%s · %s 个节点 · 作者 %s · 发布 %s"
                  % (st2, d2.get("name"), d2.get("nodeCount"),
                     ((d2.get("owner") or {}).get("id")), d2.get("publishTime")))
            print("    用到的模型：%s" % ", ".join(str((m.get("name") if isinstance(m, dict)
                                                        else m) or "")[:40]
                                                  for m in (d2.get("usedModels") or [])[:24]))

    if not a.out:
        print("· 没给 --out：只报结构，不落盘")
        return 0
    path = os.path.abspath(a.out)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print("· 已存 %s（%d 字节）" % (path, os.path.getsize(path)))
    try:
        meta = cg.check_workflow_json(path)
        print("· 结构自检通过：%d 个节点 / %d 条连线，主节点 %s、输出 %s 都在"
              % (meta["nodes"], meta["links"], meta["ids"] & {str(x) for x in
                                                              by_type.get(cg.MAIN_TYPE, [])},
                 by_type.get(cg.OUT_TYPE)))
    except cg.CloudError as e:
        print("· 结构自检没过：%s" % e)
        return 1

    # 主节点上那几档控件的可选值：云端提交的值必须和线上 options 一致，这里顺带对一遍
    for n in nodes:
        if str(n.get("type")) != cg.MAIN_TYPE:
            continue
        vals = n.get("widgets_values")
        print("· 主节点 %s 的 widgets_values（前 12 项）：%s"
              % (n.get("id"), json.dumps(vals if isinstance(vals, list) else vals,
                                         ensure_ascii=False)[:600]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
