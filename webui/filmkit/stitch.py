# -*- coding: utf-8 -*-
"""stitch.py —— 多段成片合成与尾帧抽取（走 envs/ffmpeg 这个可选工具环境）

为什么先校验再拼：concat 的 `-c copy` 是容器级拼接，只认参数完全一致的分段。
同一条工作流出来的片子一般一致；一旦有人中途换了尺寸/通道，硬拼出来就是花屏或
音画不同步，而且 ffmpeg 不报错。所以先把每段的编码、宽高、像素格式、帧率、
音频采样率逐项比一遍，不一致就停下来让人重出，不交废片。
"""
import json
import os
import shutil
import subprocess
import time

NO_CONS = 0x08000000 if os.name == "nt" else 0


class StitchError(Exception):
    pass


def tools(root):
    """(ffmpeg, ffprobe) 的绝对路径；清单里的没有就回落系统 PATH。"""
    ff = fp = ""
    try:
        import sys
        webui = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if webui not in sys.path:
            sys.path.insert(0, webui)
        from envkit import spec as sp
        spec = sp.load_spec(root)
        for name in ("ffmpeg.exe", "ffmpeg"):
            p = sp.tool_path(root, spec, "ffmpeg", name)
            if p and os.path.isfile(p):
                ff = p
                break
        for name in ("ffprobe.exe", "ffprobe"):
            p = sp.tool_path(root, spec, "ffmpeg", name)
            if p and os.path.isfile(p):
                fp = p
                break
    except Exception:
        pass
    return ff or shutil.which("ffmpeg") or "", fp or shutil.which("ffprobe") or ""


def available(root):
    ff, fp = tools(root)
    return bool(ff and fp)


def version(root):
    ff, _ = tools(root)
    if not ff:
        return ""
    try:
        r = subprocess.run([ff, "-version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=20,
                           creationflags=NO_CONS)
        return (r.stdout or "").splitlines()[0][:120]
    except Exception:
        return ""


def _run(argv, timeout=600):
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout, creationflags=NO_CONS)
    except subprocess.TimeoutExpired:
        raise StitchError("ffmpeg 超时（%d 秒）：片长太长或磁盘太慢" % timeout)
    except OSError as e:
        raise StitchError("起不了 ffmpeg：%s" % e)


def probe(root, path):
    _, fp = tools(root)
    if not fp:
        raise StitchError("缺 ffprobe：到「环境 → 基础」补上 FFmpeg")
    r = _run([fp, "-v", "error", "-print_format", "json",
              "-show_streams", "-show_format", str(path)], timeout=60)
    if r.returncode != 0:
        raise StitchError("读不了这一段：%s" % (r.stderr or "")[:200])
    try:
        return json.loads(r.stdout or "{}")
    except ValueError:
        raise StitchError("ffprobe 回的格式不对")


def duration(root, path):
    try:
        return float((probe(root, path).get("format") or {}).get("duration") or 0)
    except Exception:
        return 0.0


def _sig(info):
    """拼一段的可比指纹：视频看编码/宽高/像素格式/帧率，音频看编码/采样率/声道。"""
    v, a = [], []
    for st in info.get("streams") or []:
        kind = st.get("codec_type")
        if kind == "video":
            v.append((st.get("codec_name"), st.get("width"), st.get("height"),
                      st.get("pix_fmt"), st.get("r_frame_rate")))
        elif kind == "audio":
            a.append((st.get("codec_name"), st.get("sample_rate"),
                      st.get("channels"), st.get("channel_layout")))
    return {"video": sorted(v, key=str), "audio": sorted(a, key=str)}


def check_compatible(root, paths):
    if not paths:
        raise StitchError("没有可合成的分段")
    base = _sig(probe(root, paths[0]))
    bad = []
    for p in paths[1:]:
        cur = _sig(probe(root, p))
        for kind, name in (("video", "画面"), ("audio", "音频")):
            if cur[kind] != base[kind]:
                bad.append("%s 的%s参数与第一段不同" % (os.path.basename(p), name))
    if bad:
        raise StitchError("分段参数不一致，不能直接拼：" + "；".join(bad[:3])
                          + "。同一部短剧请用同一通道、同一清晰度重出。")
    return base


def concat(root, paths, out_path, *, log=None):
    """把 N 段按顺序拼成一个 MP4（不重编码，保留原音轨）。返回概要。"""
    paths = [str(p) for p in paths if p and os.path.isfile(p)]
    if not paths:
        raise StitchError("没有可合成的分段")
    if any(os.path.getsize(p) <= 0 for p in paths):
        raise StitchError("有 0 字节的分段：那一段没出完")
    ff, _ = tools(root)
    if not ff:
        raise StitchError("缺 FFmpeg：到「环境 → 基础」补上「FFmpeg 静态包」后再合成")
    check_compatible(root, paths)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    if len(paths) == 1:
        shutil.copy2(paths[0], out_path)
        return {"ok": True, "path": out_path, "shots": 1,
                "duration": round(duration(root, out_path), 2), "copy": True}
    lst = os.path.join(os.path.dirname(out_path) or ".", "_concat.txt")
    with open(lst, "w", encoding="utf-8", newline="\n") as f:
        for p in paths:
            q = os.path.abspath(p).replace("\\", "/").replace("'", "'\\''")
            f.write("file '%s'\n" % q)
    t0 = time.time()
    r = _run([ff, "-hide_banner", "-loglevel", "error", "-y",
              "-f", "concat", "-safe", "0", "-i", lst,
              "-c", "copy", "-movflags", "+faststart", out_path],
             timeout=max(120, int(sum(duration(root, p) for p in paths) * 4) + 60))
    try:
        os.remove(lst)
    except OSError:
        pass
    if r.returncode != 0 or not os.path.isfile(out_path) or os.path.getsize(out_path) <= 0:
        try:
            os.remove(out_path)
        except OSError:
            pass
        raise StitchError("合成失败：%s" % (r.stderr or r.stdout or "ffmpeg 没给原因")[:300])
    dur = duration(root, out_path)
    if log:
        log("· 合成：%d 段 → %s · %.1f 秒 · %.1f MB · 用时 %.1f 秒"
            % (len(paths), os.path.basename(out_path), dur,
               os.path.getsize(out_path) / 1048576.0, time.time() - t0))
    return {"ok": True, "path": out_path, "shots": len(paths),
            "duration": round(dur, 2), "copy": True}


def last_frame(root, video, out_path):
    """抽最后 0.25 秒里的一帧当下一镜的参考图。抽不出来返回空串（不阻断整条链）。"""
    ff, _ = tools(root)
    if not ff or not os.path.isfile(video):
        return ""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    args = ["-hide_banner", "-loglevel", "error", "-y",
            "-sseof", "-0.25", "-i", video, "-frames:v", "1", "-q:v", "2", out_path]
    r = _run([ff] + args, timeout=120)
    if r.returncode != 0 or not os.path.isfile(out_path) or os.path.getsize(out_path) <= 0:
        d = duration(root, video)
        if d > 0.2:
            _run([ff, "-hide_banner", "-loglevel", "error", "-y",
                  "-ss", "%.2f" % max(0.0, d - 0.15), "-i", video,
                  "-frames:v", "1", "-q:v", "2", out_path], timeout=120)
    return out_path if (os.path.isfile(out_path) and os.path.getsize(out_path) > 0) else ""
