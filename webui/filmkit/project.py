# -*- coding: utf-8 -*-
"""project.py —— 一部短剧的落盘：目录、清单、续跑判定

project.json 只写相对路径：整个 outputs/films/<id> 搬走也能接着跑。
一段算不算「已出」只看文件是不是非空——照 H3yun 那条规矩，进程被杀留下的
0 字节文件不算完成，重启后照样重出这一段，不跳号。
"""
import json
import os
import re
import time


def safe(name, default="短剧"):
    t = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", str(name or "")).strip(" .")
    return (t or default)[:40]


def _out_dir(out_dir):
    return os.path.join(out_dir or "outputs", "films")


def new_dir(out_dir):
    """outputs/films/<YYYYmmdd-HHMMSS>/，同名补 -2、-3（一秒内连开两部也不会撞）。"""
    base = _out_dir(out_dir)
    os.makedirs(base, exist_ok=True)
    stem = time.strftime("%Y%m%d-%H%M%S")
    d = os.path.join(base, stem)
    n = 2
    while os.path.exists(d):
        d = os.path.join(base, "%s-%d" % (stem, n))
        n += 1
    os.makedirs(os.path.join(d, "shots"), exist_ok=True)
    os.makedirs(os.path.join(d, "frames"), exist_ok=True)
    return d


def save(d, proj):
    proj["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path = os.path.join(d, "project.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(proj, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load(d):
    with open(os.path.join(d, "project.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def latest(out_dir):
    base = _out_dir(out_dir)
    if not os.path.isdir(base):
        return ""
    rows = []
    for name in os.listdir(base):
        p = os.path.join(base, name, "project.json")
        if os.path.isfile(p):
            try:
                rows.append((os.path.getmtime(p), p))
            except OSError:
                pass
    rows.sort(reverse=True)
    return os.path.dirname(rows[0][1]) if rows else ""


def rel(d, path):
    """工程内文件只存相对路径（交给 project.json 时用正斜杠）。"""
    try:
        p = os.path.relpath(path, d).replace("\\", "/")
    except ValueError:
        return str(path)
    return "" if p.startswith("..") else p


def abs_path(d, path):
    p = str(path or "").replace("\\", "/")
    if not p:
        return ""
    return p if os.path.isabs(p) else os.path.join(d, *p.split("/"))


def shot_file(i):
    return "shots/%03d.mp4" % int(i)


def frame_file(i):
    return "frames/%03d.jpg" % int(i)


def final_path(out_dir, title, tag=""):
    """成片放在输出根目录（画廊只扫根目录），工程目录里只留分段。

    重名就补 -2、-3，绝不覆盖别人上一部戏。
    """
    os.makedirs(out_dir or ".", exist_ok=True)
    base = safe(title) + "-成片"
    p = os.path.join(out_dir, base + ".mp4")
    n = 2
    while os.path.exists(p):
        p = os.path.join(out_dir, "%s-%d.mp4" % (base, n))
        n += 1
    return p


def norm_refs(v):
    """参考图列表：字符串/列表都收，去空、去重、保序。"""
    if isinstance(v, str):
        v = [v]
    out = []
    for x in (v or []):
        p = str(x).strip()
        if p and p not in out:
            out.append(p)
    return out


def project_refs(proj):
    """工程里的参考图池。旧工程只有 first：折成一张，行为与以前一致。"""
    refs = norm_refs((proj or {}).get("refs"))
    if not refs:
        refs = norm_refs((proj or {}).get("first"))
    return refs


MAX_REFS = 4      # 云端 H3 的媒体槽与编号引用按 4 张做的


def refs_for(proj, sh, prev_frame=""):
    """这一段该带哪几张参考图（顺序即编号）。

    - 段级 refs（第几张）优先，只在固定池里挑；
    - 接帧且不是第 1 段：上一段尾帧排第 1，固定参考图按 ref_mode 随后；
    - ref_mode：same=同一张 / seq=第 i 段第 i 张 / all=全带。
    接帧时尾帧会占掉一个号位，固定图从尾部截掉，别把 5 张交给只收 4 张的工作流。
    """
    pool = project_refs(proj)
    pick = (sh or {}).get("refs") or []
    if pool and pick:
        chosen = []
        for x in pick:
            try:
                n = int(x)
            except (TypeError, ValueError):
                continue
            if 1 <= n <= len(pool) and pool[n - 1] not in chosen:
                chosen.append(pool[n - 1])
        if chosen:
            pool = chosen
    try:
        i = int((sh or {}).get("i") or 1)
    except (TypeError, ValueError):
        i = 1
    mode = str(proj.get("ref_mode") or "same")
    if not pool:
        picks = []
    elif mode == "all":
        picks = list(pool)
    elif mode == "seq":
        picks = [pool[(i - 1) % len(pool)]]
    else:
        picks = pool[:1]
    if str(proj.get("mode")) == "chain" and prev_frame and i > 1:
        return ([prev_frame] + picks)[:MAX_REFS]
    return picks[:MAX_REFS]


def norm_shots(rows, shot_sec=15, limit=40):
    """把界面/模型给的分镜折成统一形状：秒数只认 5/10/15，空描述直接丢掉。"""
    try:
        shot_sec = int(shot_sec or 15)
    except (TypeError, ValueError):
        shot_sec = 15
    if shot_sec not in (5, 10, 15):
        shot_sec = 15
    out = []
    for row in (rows or [])[:limit]:
        if isinstance(row, str):
            row = {"prompt": row}
        if not isinstance(row, dict):
            continue
        prompt = str(row.get("prompt") or row.get("description") or "").strip()
        if not prompt:
            continue
        try:
            sec = int(row.get("seconds") or shot_sec)
        except (TypeError, ValueError):
            sec = shot_sec
        if sec not in (5, 10, 15):
            sec = shot_sec
        picked = []
        for x in ((row.get("refs") or []) if isinstance(row.get("refs"), list) else []):
            try:
                n = int(x)
            except (TypeError, ValueError):
                continue
            if 1 <= n <= MAX_REFS and n not in picked:
                picked.append(n)
        out.append({
            "i": len(out) + 1,
            "summary": str(row.get("summary") or "").strip()[:80],
            "prompt": prompt[:600],
            "refs": picked,
            "seconds": sec,
            "state": "wait",
            "file": "", "frame": "", "sec": 0.0, "err": "",
        })
    return out


def ok_file(d, sh):
    p = abs_path(d, sh.get("file") or "")
    return bool(p and os.path.isfile(p) and os.path.getsize(p) > 0)
