# -*- coding: utf-8 -*-
"""stitch.py —— 多段成片合成与尾帧抽取（走 envs/ffmpeg 这个可选工具环境）

合成有两条路，先体检再选：
· 参数完全一致且不做转场 → concat 的 `-c copy`，容器级直拼，画质与时长都是原样；
  一旦有人中途换了尺寸/通道，硬拼出来是花屏或音画不同步，而且 ffmpeg 不报错，
  所以拼之前把编码、宽高、像素格式、帧率、音频采样率逐项比一遍，不一致就停下。
· 参数不齐或要做转场 → 逐段归一化到同一个画幅/帧率/音频规格（画幅不符补黑边、
  没声音补静音轨），重编码拼一遍。本地与云端混着出的、中途换过清晰度的，
  走这条路也能拼成，不再整批拒拼。

转场的 offset 一律用归一化之后的实测时长累加，不用分镜标称的秒数：
`-c copy` 每段会漂几毫秒，标称值算出来的 offset 攒到后面就是画面卡顿或跳帧。
重编码先落 `<成片>.partial`，ffprobe 验过画幅、时长、音轨都对才原子改名——
中途被杀不会留下一条看着能播其实是半截的成片。
"""
import hashlib
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
        raise StitchError("缺 ffprobe：到「环境管理 → 基础」补上 FFmpeg")
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


def concat(root, paths, out_path, *, log=None, check=True):
    """把 N 段按顺序拼成一个 MP4（不重编码，保留原音轨）。返回概要。"""
    paths = [str(p) for p in paths if p and os.path.isfile(p)]
    if not paths:
        raise StitchError("没有可合成的分段")
    if any(os.path.getsize(p) <= 0 for p in paths):
        raise StitchError("有 0 字节的分段：那一段没出完")
    ff, _ = tools(root)
    if not ff:
        raise StitchError("缺 FFmpeg：到「环境管理 → 基础」补上「FFmpeg 静态包」后再合成")
    if check:
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


AR = 44100          # 音频统一采样率：两份输出的采样率不一样时，越到后面漂得越多


def _even(v, lo=16):
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return 0
    return max(lo, n - n % 2)


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _fps_of(st):
    r = str(st.get("avg_frame_rate") or st.get("r_frame_rate") or "")
    num, _, den = r.partition("/")
    f = _float(num) / (_float(den) or 1.0)
    return round(f, 3) if f > 0 else 0.0


def inspect(root, path):
    """一段的体检报告：多长、多大、几帧一秒、有没有声音。

    空文件、没有画面轨、时长读不出来——这些话在这里说清，别等拼完整部才发现。
    """
    p = str(path or "")
    if not p or not os.path.isfile(p):
        raise StitchError("分段文件不在：%s" % (os.path.basename(p) or "空路径"))
    if os.path.getsize(p) <= 0:
        raise StitchError("%s 是 0 字节：那一段没出完，重出它" % os.path.basename(p))
    info = probe(root, p)
    v = a = None
    for st in info.get("streams") or []:
        kind = st.get("codec_type")
        if kind == "video" and v is None:
            v = st
        elif kind == "audio" and a is None:
            a = st
    if v is None:
        raise StitchError("%s 里没有画面轨：这一段不能用，重出它" % os.path.basename(p))
    dur = max(_float((info.get("format") or {}).get("duration")),
              _float(v.get("duration")))
    if dur <= 0.2:
        raise StitchError("%s 读不出时长：这一段不能用，重出它" % os.path.basename(p))
    return {"path": p, "dur": round(dur, 3), "w": int(_float(v.get("width"))),
            "h": int(_float(v.get("height"))), "fps": _fps_of(v),
            "audio": a is not None, "vcodec": str(v.get("codec_name") or "")}


def preflight(root, paths, w=0, h=0, fps=0):
    """合成前排一遍队：逐段实测，定下成片的画幅与帧率，并判要不要归一化。

    回 (体检表, 宽, 高, 帧率, 要不要归一化)。
    """
    rows = [inspect(root, p) for p in paths]
    n_w, n_h, n_fps = _target(rows, w, h, fps)
    need = any(r["w"] != n_w or r["h"] != n_h or abs(r["fps"] - n_fps) > 0.05
               or not r["audio"] for r in rows)
    return rows, n_w, n_h, n_fps, need


def _target(rows, w=0, h=0, fps=0):
    """成片画幅：调用方给的优先；没给就取多数段那一档（别拿一段特例定调整部的尺寸）。"""
    if not w or not h:
        cnt = {}
        for r in rows:
            if r["w"] and r["h"]:
                cnt[(r["w"], r["h"])] = cnt.get((r["w"], r["h"]), 0) + 1
        if cnt:
            w, h = max(cnt.items(), key=lambda kv: kv[1])[0]
    w, h = _even(w), _even(h)
    if not w or not h:
        raise StitchError("分段都没有可用的画面尺寸，不知道按哪一档合成")
    if not fps:
        c = {}
        for r in rows:
            if r["fps"]:
                c[r["fps"]] = c.get(r["fps"], 0) + 1
        fps = max(c.items(), key=lambda kv: kv[1])[0] if c else 24.0
    return int(w), int(h), round(float(fps), 3)


def norm_key(src, w, h, fps):
    st = os.stat(src)
    s = "%s|%d|%d|%dx%d@%g" % (os.path.abspath(src).lower(), int(st.st_mtime),
                               st.st_size, w, h, fps)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


def norm_dst(work_dir, src, w, h, fps):
    stem = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(work_dir, "%s-%dx%d-%g-%s.mp4"
                        % (stem, w, h, fps, norm_key(src, w, h, fps)))


def normalize(root, src, dst, w, h, fps=24.0, audio=True, timeout=0):
    """一段 → 目标画幅/帧率/音频规格：画面等比缩进去补黑边，没声音补一条静音轨。

    缓存写在文件名里（源文件的 mtime+大小 + 这套参数）：源片重出过或参数换过
    就是另一个名字，旧那份不会被当成结果复用。
    """
    if os.path.isfile(dst) and os.path.getsize(dst) > 0:
        return dst
    ff, _ = tools(root)
    if not ff:
        raise StitchError("缺 FFmpeg：到「环境管理 → 基础」补上「FFmpeg 静态包」后再合成")
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    # 后缀还是 .mp4：ffmpeg 按扩展名选封装格式，写成 .partial 它会直接拒绝
    tmp = dst + ".part.mp4"
    fc = ("[0:v]scale=%d:%d:force_original_aspect_ratio=decrease,setsar=1,"
          "fps=%g,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p[v]"
          % (w, h, fps, w, h))
    args = [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", src]
    if audio:
        fc += ";[0:a]aresample=async=1:first_pts=0[a]"
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=r=%d:cl=stereo" % AR]
        fc += ";[1:a]aresample=%d[a]" % AR
    args += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-c:a", "aac", "-b:a", "160k", "-ar", str(AR), "-ac", "2",
             "-shortest", "-movflags", "+faststart", tmp]
    r = _run(args, timeout=timeout or max(120, int(duration(root, src) * 8) + 60))
    if r.returncode != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) <= 0:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise StitchError("%s 归一化失败：%s"
                          % (os.path.basename(src),
                             (r.stderr or r.stdout or "ffmpeg 没给原因")[:240]))
    os.replace(tmp, dst)
    return dst


def _graph(rows, fade):
    """n 段交叉淡化：offset 用实测时长累加。回 (filter 脚本, 视频标签, 音频标签, 总时长)。

    后一段的开头要被转场吃掉 fade 秒，所以调用方先把 fade 夹到最短那段的四成五以内。
    """
    bits = []
    pv, pa = "0:v", "0:a"
    run = rows[0]["dur"]
    for i in range(1, len(rows)):
        off = max(0.0, run - fade)
        bits.append("[%s][%d:v]xfade=transition=fade:duration=%.3f:offset=%.3f[v%d]"
                    % (pv, i, fade, off, i))
        bits.append("[%s][%d:a]acrossfade=d=%.3f:c1=tri:c2=tri[a%d]" % (pa, i, fade, i))
        pv, pa = "v%d" % i, "a%d" % i
        run += rows[i]["dur"] - fade
    return ";".join(bits), pv, pa, round(run, 3)


def _verify(root, path, w, h, dur):
    """改名之前的最后一道问：画幅、时长、音轨对不对得上。"""
    r = inspect(root, path)
    if r["w"] != w or r["h"] != h:
        raise StitchError("画幅是 %dx%d，应为 %dx%d" % (r["w"], r["h"], w, h))
    if dur > 0 and abs(r["dur"] - dur) > max(0.75, dur * 0.04):
        raise StitchError("时长 %.1f 秒，应为 %.1f 秒" % (r["dur"], dur))
    if not r["audio"]:
        raise StitchError("结果里没有音轨")
    return r


def merge(root, paths, out_path, *, w=0, h=0, fps=0, fade=0.0, work_dir="", log=None):
    """按顺序合成一部：逐段体检 → 参数不齐就逐段归一化 → 转场或直拼 → 验过才落地。

    回 `{"ok", "path", "shots", "duration", "copy", ...}`。`copy=True` 是没重编码的
    快路径；其余都走重编码——先落 `<成片>.part.mp4`，ffprobe 验过才原子改名，
    中途被杀或 ffmpeg 报错都不会留下一条看着能播的半截成片。
    """
    paths = [str(p) for p in paths if p]
    if not paths:
        raise StitchError("没有可合成的分段")
    ff, _ = tools(root)
    if not ff:
        raise StitchError("缺 FFmpeg：到「环境管理 → 基础」补上「FFmpeg 静态包」后再合成")
    rows, w, h, fps, need = preflight(root, paths, w, h, fps)
    fade = max(0.0, _float(fade))
    if not need and fade <= 0:
        return concat(root, paths, out_path, log=log)
    t0 = time.time()
    work = work_dir or os.path.join(os.path.dirname(os.path.abspath(out_path)) or ".", "_norm")
    got = [normalize(root, r["path"], norm_dst(work, r["path"], w, h, fps),
                     w, h, fps, r["audio"]) for r in rows]
    rows = [inspect(root, p) for p in got]
    total = round(sum(r["dur"] for r in rows), 3)
    if len(rows) == 1 or fade <= 0:
        r = concat(root, got, out_path, log=log, check=False)
        # copy 说的是「成片这一刀没重编码」：走到这里分段已经重编过，不能再报 True
        r.update(copy=False, norm=round(time.time() - t0, 1), size="%dx%d" % (w, h))
        return r
    fade = min(fade, round(min(r["dur"] for r in rows) * 0.45, 3))
    script, pv, pa, dur = _graph(rows, fade)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    tmp = out_path + ".part.mp4"
    args = [ff, "-hide_banner", "-loglevel", "error", "-y"]
    for p in got:
        args += ["-i", p]
    args += ["-filter_complex", script, "-map", "[%s]" % pv, "-map", "[%s]" % pa,
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-ar", str(AR), "-ac", "2",
             "-movflags", "+faststart", tmp]
    try:
        r = _run(args, timeout=max(180, int(total * 8) + 120))
        if r.returncode != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) <= 0:
            raise StitchError("转场合成失败：%s"
                              % (r.stderr or r.stdout or "ffmpeg 没给原因")[:300])
        _verify(root, tmp, w, h, dur)
        os.replace(tmp, out_path)
    except StitchError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    if log:
        log("· 合成：%d 段（归一化 %dx%d@%g）· 转场 %.2f 秒 → %s · %.1f 秒 · 用时 %.1f 秒"
            % (len(got), w, h, fps, fade, os.path.basename(out_path), dur,
               time.time() - t0))
    return {"ok": True, "path": out_path, "shots": len(got), "duration": dur,
            "copy": False, "fade": fade, "size": "%dx%d" % (w, h),
            "sec": round(time.time() - t0, 1)}


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
