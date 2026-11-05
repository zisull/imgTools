# -*- coding: utf-8 -*-
"""风格预设：一段风格模板（{prompt} 占位）+ 通用反向 + 适用引擎 + 缩略图 + 参考图。

词库管「这一句怎么写」，风格预设管「这一类图整体怎么拍」——点一下把当前提示词套进
模板，顺手补上这条风格对应的反向词，参考图有余位再补进去。

数据是一份可以直接手改的 JSON。用户那份落在 <data>/styles/presets.json，出厂那份随包
走 webui/styles_default.json，第一次用才复制过去：复制而不是每次合并，合并会让用户
删掉的那几条在下次启动又长回来。图片一律搬进 <data>/styles/img/，整个目录搬到别的
机器上也还在。
"""
import json
import os
import re
import shutil
import time
import zlib

import datahome

ENGINE = ("qwen", "moss", "h3", "cloud")
# 适用引擎为空＝哪一路都能用：多数人不在乎这条，让他少填一格
ID_RE = re.compile(r"^[a-z0-9_-]{1,24}$")
NAME_MAX, TPL_MAX, NEG_MAX, REF_MAX = 24, 4000, 1200, 4
SEP = "，"
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")


def _here():
    return os.path.dirname(os.path.abspath(__file__))


def factory_path():
    return os.path.join(_here(), "styles_default.json")


def styles_dir(root):
    return os.path.join(datahome.data_dir(root), "styles")


def img_dir(root):
    return os.path.join(styles_dir(root), "img")


def data_path(root):
    return os.path.join(styles_dir(root), "presets.json")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, list) else None


def mkid(name):
    """编号只由名字派生：手改 JSON 的人不必自己想一个，重复了再补后缀。"""
    base = "s%08x" % (zlib.crc32(str(name or "").encode("utf-8")) & 0xFFFFFFFF)
    return base


def _uniq_id(items, cid, name):
    got, n = cid, 0
    have = {str(x.get("id") or "") for x in items}
    while got in have:
        n += 1
        got = "%s_%d" % (cid, n)
        if len(got) > 24:
            got = "s%08x" % (zlib.crc32(("%s%d" % (name, n)).encode("utf-8")) & 0xFFFFFFFF)
    return got


def _clean_list(v, cap):
    out = []
    for x in (v if isinstance(v, (list, tuple)) else ([v] if v else [])):
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= cap:
            break
    return out


def _clean_eng(v):
    got = [e for e in ENGINE if e in _clean_list(v, len(ENGINE))]
    return got


def norm(p, keep_id=True):
    """收脏数据：界面和手改的 JSON 都走这一个口子，长度与字符集在这里夹住。"""
    p = p if isinstance(p, dict) else {}
    name = str(p.get("name") or "").strip()[:NAME_MAX]
    tpl = str(p.get("tpl") or p.get("template") or "").strip()[:TPL_MAX]
    cid = str(p.get("id") or "").strip()
    if not ID_RE.match(cid or "") or not keep_id:
        cid = mkid(name or tpl or "style")
    return {"id": cid, "name": name, "tpl": tpl,
            "neg": str(p.get("neg") or p.get("negative") or "").strip()[:NEG_MAX],
            "eng": _clean_eng(p.get("eng")),
            "thumb": str(p.get("thumb") or "").strip(),
            "refs": _clean_list(p.get("refs"), REF_MAX),
            "note": str(p.get("note") or "").strip()[:80],
            "ts": p.get("ts") or time.time()}


def load(root):
    """读用户那份；没有就从出厂那份复制一份出来（复制后用户改什么就都是他的）。"""
    path = data_path(root)
    items = _read_json(path)
    if items is None:
        items = _read_json(factory_path()) or []
        _write(path, items)
    out, have = [], set()
    for p in items:
        n = norm(p)
        if not n["tpl"]:
            continue                      # 没模板的条目点下去什么也不发生，不如不收
        if n["id"] in have:
            n["id"] = _uniq_id(out, n["id"], n["name"])
        have.add(n["id"])
        out.append(n)
    return out


def _write(path, items):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def save(root, items):
    _write(data_path(root), [norm(p) for p in items])
    return items


def find(items, pid):
    pid = str(pid or "")
    for p in items:
        if p.get("id") == pid:
            return p
    return None


def _tidy(text):
    """占位符换成空原文后会留下「，，」和「：，」这类接缝，收一遍。

    收尾也剥冒号：「电影感写实：{prompt}」在人还没写主体时就只剩一个光秃秃的冒号。
    """
    t = re.sub(r"[，、。]\s*(?=，)", "", str(text or ""))
    t = re.sub(r"([:：])\s*，", r"\1", t)
    return t.strip(SEP + "。、 ：:").strip()


def render(p, text):
    """{prompt} 在模板里就原位插进去；没写就把原话接在模板后面。

    只认这一种占位符、不认 {neg} 之类的：预设是给界面点的，能填的格子只有提示词。
    """
    tpl = str((p or {}).get("tpl") or "")
    t = str(text or "").strip()
    if "{prompt}" in tpl:
        return _tidy(tpl.replace("{prompt}", t)) if t else _tidy(tpl.replace("{prompt}", SEP))
    if not tpl:
        return t
    return _tidy(t + SEP + tpl) if t else _tidy(tpl)


def choose(items, engine):
    """适用引擎为空＝全适用；否则只有点名了这一路的才出现在那一页上。"""
    engine = str(engine or "")
    if engine and engine not in ENGINE:
        engine = ""
    return [p for p in (items or []) if not p.get("eng") or not engine
            or engine in p["eng"]]


def _abs(root, p):
    if not p:
        return ""
    return p if os.path.isabs(p) else os.path.join(styles_dir(root), p)


def _rel(root, p):
    """能表示成 styles 目录内的相对路径就存相对：整个目录搬走也不丢。"""
    try:
        r = os.path.relpath(os.path.abspath(p), os.path.abspath(styles_dir(root)))
    except ValueError:
        return p
    return p if r.startswith("..") else r.replace("\\", "/")


def adopt(root, pid, path):
    """把外部图片收进 <data>/styles/img/，返回相对路径；已经在里面或文件没了就原样回。"""
    src = str(path or "").strip()
    if not src or not os.path.isfile(src):
        return src
    if os.path.normcase(os.path.dirname(os.path.abspath(src))) == \
            os.path.normcase(os.path.abspath(img_dir(root))):
        return _rel(root, src)
    ext = os.path.splitext(src)[1].lower()
    if ext not in IMG_EXT:
        return src
    stem = re.sub(r"[^\w.\-]", "_", os.path.splitext(os.path.basename(src))[0])[:40] or "style"
    os.makedirs(img_dir(root), exist_ok=True)
    dst = os.path.join(img_dir(root), "%s_%s%s" % (stem, mkid(pid or src), ext))
    try:
        shutil.copy2(src, dst)
    except OSError:
        return src
    return _rel(root, dst)


def paths(root, p, kind="thumb"):
    """预设里的图片路径解析成绝对路径；kind=refs 回 (绝对路径列表, 找不到的张数)。"""
    if kind == "refs":
        out, lost = [], 0
        for r in (p or {}).get("refs") or []:
            a = _abs(root, r)
            if a and os.path.isfile(a):
                out.append(a)
            else:
                lost += 1
        return out, lost
    a = _abs(root, (p or {}).get("thumb") or "")
    return a if a and os.path.isfile(a) else ""


def upsert(root, p):
    """新增或覆盖一条；图片在这一步统一收进 styles/img，界面只管把选中的路径交过来。"""
    items = load(root)
    n = norm(p)
    if not n["name"]:
        return items, "名字是空的：给这条风格起个两三个字的短名"
    if not n["tpl"]:
        return items, "模板是空的：没有提示词的预设点下去什么都不发生"
    if n["thumb"]:
        n["thumb"] = adopt(root, n["id"], n["thumb"])
    n["refs"] = [adopt(root, n["id"], r) for r in n["refs"]]
    old = find(items, n["id"])
    if old:
        items[items.index(old)] = n
    else:
        n["id"] = _uniq_id(items, n["id"], n["name"])
        items.append(n)
    save(root, items)
    return items, ""


def delete(root, pid):
    items = load(root)
    p = find(items, pid)
    if not p:
        return items, "没有这条风格"
    items.remove(p)
    save(root, items)
    # 只清我们收进 styles/img 的那几张：外部原图是用户自己的东西，不碰
    for r in [p.get("thumb") or ""] + list(p.get("refs") or []):
        a = _abs(root, r)
        if a and os.path.isfile(a) and os.path.normcase(os.path.dirname(a)) == \
                os.path.normcase(os.path.abspath(img_dir(root))):
            try:
                os.remove(a)
            except OSError:
                pass
    return items, ""


def reset(root):
    """恢复出厂：整份替换成包里的那份，用户自己加的随之消失（界面要先问一句）。"""
    items = _read_json(factory_path()) or []
    save(root, items)
    return items


def draft(meta, name="", engine=""):
    """从画廊那一张的记账里草一条预设：提示词当模板、它的反向当通用反向。

    原话整段当模板会写死主体，所以顺手把最长的那一段留下、其余照抄——真正要不要
    改成 {prompt} 交给用户在编辑框里动笔，这里不替他猜。
    """
    m = meta or {}
    prompt = str(m.get("prompt") or "").strip()[:TPL_MAX]
    return {"id": mkid(name or prompt or "style"),
            "name": str(name or "").strip()[:NAME_MAX],
            "tpl": prompt,
            "neg": str(m.get("negative") or "").strip()[:NEG_MAX],
            "eng": _clean_eng([engine] if engine else []),
            "thumb": str(m.get("file") or "").strip(),
            "refs": [], "note": "", "ts": time.time()}
