# -*- coding: utf-8 -*-
"""download.py —— 权重下载：Motrix/aria2 优先，回落内置多镜像分段下载器
================================================================
为什么不用 snapshot_download 就完事：它一次只给每个文件一条连接，30GB 的
Text Encoder 单线下到天亮；hf_transfer 在 huggingface_hub 2.x 已经废弃。
hf-mirror 的 resolve 支持 Range（实测 206），所以内置下载器自己切段、多连接并行，
断点续传、速度/剩余时间都能算出来。

桌面上开着 Motrix 时先交给它：Motrix 内置 aria2，端口与密钥只从本机的
%APPDATA%/Motrix/settings.json 读（绝不写进仓库或日志），探测不通就静默回落。
对外只有 download() 一个入口；setup_all（控制台）和 app.py（界面）共用它，
进度回调是同一份结构，两边各自画自己的进度条。

约定：
  · 默认先 hf-mirror，探测失败再退 huggingface.co；--endpoint 只决定优先顺序
  · 每个文件先写 sidecar <file>.mossdl，再预分配，避免「预分配满尺寸」被当成下完
  · 分段各开一条连接、各拿一个文件句柄 seek 写；Windows 没有 os.pwrite
  · 内置下载器彻底失败才回落 huggingface_hub；回落前清理未完成文件，否则 hub
    看见满尺寸文件会当成已完成，留下一个坏权重
  · Motrix 只接「没有内置 sidecar 进度」的文件；接不上就整个交给内置下载器
"""
import fnmatch
import json
import os
import re
import threading
import time
from collections import deque
from urllib import error as urlerr
from urllib import parse as urlparse
from urllib import request as urlreq

DEFAULTS = {
    "endpoints": ["https://hf-mirror.com", "https://huggingface.co"],
    "jobs": 8,
    "chunk_mb": 64,
    "retries": 20,
    "timeout": 60,
    "probe_timeout": 8,
}

_CACHE = {}          # repo -> (ts, endpoint, files)
_CACHE_TTL = 6 * 3600
_MIN_CHUNK_BYTES = 1 << 20      # 小于 1MB 的文件不值得探测 Range，直接单流


# ---------------------------------------------------------------- 杂项
def credentials():
    h = {"User-Agent": "Moss-hf-download/2"}
    tok = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if tok:
        h["Authorization"] = "Bearer " + tok
    return h


def fmt_bytes(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return ("%.1f %s" % (n, unit)) if unit != "B" else ("%d B" % n)
        n /= 1024.0


def fmt_eta(sec):
    sec = float(sec or 0)
    if sec <= 0 or sec > 86400 * 7:
        return ""
    if sec < 60:
        return "%d 秒" % round(sec)
    if sec < 3600:
        return "%d 分" % round(sec / 60.0)
    return "%d 小时 %d 分" % (int(sec // 3600), int((sec % 3600) // 60))


def _log(cb, msg):
    if cb:
        try:
            cb(msg)
        except Exception:
            pass


def _url(endpoint, repo, path):
    return "%s/%s/resolve/main/%s" % (
        endpoint.rstrip("/"), repo, urlparse.quote(path, safe="/"))


def _api_url(endpoint, repo):
    return "%s/api/models/%s?blobs=true" % (
        endpoint.rstrip("/"), urlparse.quote(repo, safe="/"))


def _safe_join(root, rel):
    rel = str(rel).replace("\\", "/")
    parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
    if not parts:
        raise ValueError("空文件名")
    return os.path.join(root, *parts)


def _parse_siblings(data):
    out = []
    for s in data.get("siblings") or []:
        name = s.get("rfilename")
        if not name:
            continue
        size = s.get("size")
        if size is None and isinstance(s.get("lfs"), dict):
            size = s["lfs"].get("size")
        sha = (s.get("lfs") or {}).get("sha256") if isinstance(s.get("lfs"), dict) else ""
        out.append({"path": name, "size": int(size or 0), "sha256": sha or ""})
    return out


def _api_get(repo, endpoint, timeout):
    req = urlreq.Request(_api_url(endpoint, repo), headers=credentials())
    with urlreq.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def list_repo(repo, config=None, endpoint=None, on_log=None):
    """探测镜像并列出仓库文件；返回 (endpoint, files)。同一进程内缓存 6 小时。"""
    cfg = dict(DEFAULTS)
    cfg.update(config or {})
    cache = _CACHE.get(repo)
    if cache and time.time() - cache[0] < _CACHE_TTL and (not endpoint or cache[1] == endpoint):
        return cache[1], cache[2]
    order = []
    if endpoint:
        order.append(str(endpoint).rstrip("/"))
    for ep in cfg.get("endpoints") or []:
        ep = str(ep).rstrip("/")
        if ep and ep not in order:
            order.append(ep)
    last = None
    for ep in order:
        t0 = time.perf_counter()
        try:
            data = _api_get(repo, ep, float(cfg["probe_timeout"]))
            files = _parse_siblings(data)
            if not files:
                raise OSError("镜像返回的文件清单是空的")
            ms = (time.perf_counter() - t0) * 1000
            _log(on_log, "🌐 镜像 %s 可用（%.0f ms，%d 个文件）" % (ep, ms, len(files)))
            _CACHE[repo] = (time.time(), ep, files)
            return ep, files
        except Exception as e:      # noqa: BLE001 —— 换镜像就是靠接住一切
            last = e
            _log(on_log, "⚠️ 镜像 %s 不通：%s" % (ep, e))
    raise OSError("所有镜像都不通（最后一个错误：%s）" % last)


def match_path(path, patterns):
    """allow 模式：支持整路径、文件名、目录前缀（video/）与通配（*.safetensors）。"""
    for p in patterns or []:
        p = str(p)
        if not p:
            continue
        if fnmatch.fnmatch(path, p) or fnmatch.fnmatch(os.path.basename(path), p):
            return True
        if p.endswith("/") and path.startswith(p):
            return True
    return False


def select_files(files, allow):
    if not allow:
        return list(files)
    return [f for f in files if match_path(f["path"], allow)]


# ---------------------------------------------------------------- 分段与续传
def _sidecar(path):
    return path + ".mossdl"


def _load_sidecar(path, size):
    try:
        with open(_sidecar(path), "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if int(d.get("size") or -1) != int(size):
        return None
    chunks = d.get("chunks")
    if not isinstance(chunks, list):
        return None
    out = []
    for c in chunks:
        try:
            s, e = int(c["start"]), int(c["end"])
            d0 = max(0, min(int(c.get("done") or 0), e - s + 1))
        except (KeyError, TypeError, ValueError):
            return None
        out.append({"start": s, "end": e, "done": d0})
    return out


def _save_sidecar(path, size, chunks):
    tmp = _sidecar(path) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"size": int(size),
                       "chunks": [{"start": c["start"], "end": c["end"], "done": c["done"]}
                                  for c in chunks]}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _sidecar(path))
    except OSError:
        pass


def _plan_chunks(size, chunk_size):
    n = max(1, int((size + chunk_size - 1) // chunk_size))
    step = max(1, size // n)
    out, pos = [], 0
    for i in range(n):
        end = size - 1 if i == n - 1 else pos + step - 1
        out.append({"start": pos, "end": end, "done": 0})
        pos = end + 1
    return out


def _probe_range(url, timeout):
    """返回 (是否支持 Range, 服务器报的总字节数)。"""
    req = urlreq.Request(url, headers=dict(credentials(), Range="bytes=0-0"))
    with urlreq.urlopen(req, timeout=timeout) as r:
        if r.status == 206:
            m = re.search(r"/(\d+)\s*$", r.headers.get("Content-Range") or "")
            return True, int(m.group(1)) if m else 0
        return False, int(r.headers.get("Content-Length") or 0)


def _fetch_chunk(url, fh, chunk, counter, stop, timeout, retries):
    """把一段 [start, end] 写进 fh；chunk['done'] 记录已落盘字节。"""
    pos = chunk["start"] + chunk["done"]
    end = chunk["end"]
    attempt = 0
    while pos <= end and not stop.is_set():
        try:
            req = urlreq.Request(url, headers=dict(
                credentials(), Range="bytes=%d-%d" % (pos, end)))
            with urlreq.urlopen(req, timeout=timeout) as r:
                if r.status not in (200, 206):
                    raise OSError("HTTP %s" % r.status)
                if r.status == 200:
                    # 服务器不理 Range：只有从头下整文件时，200 才是对的
                    if pos != 0 or chunk["start"] != 0 or chunk["end"] != chunk["_size"] - 1:
                        raise OSError("服务器不支持 Range")
                while pos <= end and not stop.is_set():
                    want = min(1 << 20, end - pos + 1)
                    buf = r.read(want)
                    if not buf:
                        raise OSError("连接提前结束")
                    fh.seek(pos)
                    fh.write(buf)
                    pos += len(buf)
                    chunk["done"] += len(buf)
                    counter.add(len(buf))
            attempt = 0
        except (OSError, urlerr.URLError, ValueError) as e:
            if stop.is_set():
                break
            attempt += 1
            if attempt > retries:
                raise OSError("分段 %d-%d 重试 %d 次仍失败：%s"
                              % (chunk["start"], end, retries, e))
            time.sleep(min(2 * attempt, 20))
    if pos <= end and not stop.is_set():
        raise OSError("分段 %d-%d 没下完" % (chunk["start"], end))


def _fetch_single(url, fh, size, counter, stop, timeout, retries):
    """服务器不支持 Range：只能从头整文件重下，中断后下次也从头来。"""
    attempt = 0
    while not stop.is_set():
        try:
            req = urlreq.Request(url, headers=credentials())
            with urlreq.urlopen(req, timeout=timeout) as r:
                if r.status != 200:
                    raise OSError("HTTP %s" % r.status)
                pos = 0
                while not stop.is_set():
                    buf = r.read(1 << 20)
                    if not buf:
                        break
                    fh.seek(pos)
                    fh.write(buf)
                    pos += len(buf)
                    counter.add(len(buf))
                if pos != size:
                    raise OSError("只收到 %d / %d 字节" % (pos, size))
                return
        except (OSError, urlerr.URLError, ValueError) as e:
            if stop.is_set():
                break
            attempt += 1
            if attempt > retries:
                raise OSError("单流下载重试 %d 次仍失败：%s" % (retries, e))
            time.sleep(min(2 * attempt, 20))


class _Counter:
    def __init__(self, done=0):
        self.done = done
        self._lock = threading.Lock()

    def add(self, n):
        with self._lock:
            self.done += n

    def get(self):
        with self._lock:
            return self.done


class _Meter:
    """速度用最近 5 秒的窗口算；断点续传开头没有样本时先报 0，不瞎估。"""

    def __init__(self):
        self.samples = deque()

    def tick(self, done):
        now = time.time()
        self.samples.append((now, done))
        while len(self.samples) > 2 and now - self.samples[0][0] > 5:
            self.samples.popleft()
        if len(self.samples) < 2:
            return 0.0
        t0, d0 = self.samples[0]
        dt = max(0.2, now - t0)
        return max(0.0, (done - d0) / dt)


def _dir_bytes(path):
    total = 0
    for base, _dirs, fs in os.walk(path):
        for f in fs:
            try:
                total += os.path.getsize(os.path.join(base, f))
            except OSError:
                pass
    return total


def _emit(cb, ev):
    if cb:
        try:
            cb(ev)
        except Exception:
            pass


# ---------------------------------------------------------------- Motrix / aria2
def motrix_settings():
    """从本机 Motrix 配置里找 RPC 端口与密钥；找不到返回 None。

    这是本机凭证：只在这里读、只拼进内存里的请求，绝不写日志、不进仓库。
    """
    appdata = os.environ.get("APPDATA") or ""
    if not appdata:
        return None
    path = os.path.join(appdata, "Motrix", "settings.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        eng = data.get("engine") or {}
        port = int(eng.get("rpcPort") or 0)
        if port:
            return port, str(eng.get("rpcSecret") or "")
    except Exception:
        pass
    return None


def _motrix_cfg(cfg):
    """cfg.download.motrix：true=自动发现；{port,secret}=手动指定；false=关。"""
    m = (cfg or {}).get("motrix", True)
    if m is False or m is None:
        return None
    if isinstance(m, dict):
        port = int(m.get("port") or 0)
        if port:
            return port, str(m.get("secret") or "")
    return motrix_settings()


def _aria2_call(port, secret, method, params, timeout=5):
    payload = {"jsonrpc": "2.0", "id": "imgtools", "method": method,
               "params": (["token:" + secret] if secret else []) + list(params)}
    req = urlreq.Request("http://127.0.0.1:%d/jsonrpc" % port,
                         data=json.dumps(payload).encode("utf-8"),
                         headers={"Content-Type": "application/json"})
    with urlreq.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        raise OSError(str((err or {}).get("message") or err))
    return data.get("result") if isinstance(data, dict) else data


def aria2_ready(cfg=None):
    """Motrix 在跑且 RPC 能通时返回 (port, secret)，否则 None。"""
    m = _motrix_cfg(cfg)
    if not m:
        return None
    try:
        _aria2_call(m[0], m[1], "aria2.getVersion", [], timeout=1.5)
        return m
    except Exception:
        return None


def _aria2_status(port, secret, gids):
    # aria2 的 system.multicall 不认顶层令牌：要放进每个子调用的 params 里
    auth = ["token:" + secret] if secret else []
    calls = [{"methodName": "aria2.tellStatus",
              "params": auth + [g, ["status", "completedLength", "totalLength",
                                    "downloadSpeed", "errorMessage"]]}
             for g in gids]
    try:
        res = _aria2_call(port, "", "system.multicall", [calls], timeout=5)
    except Exception:
        return None
    out = []
    for r in res or []:
        if isinstance(r, list) and r and isinstance(r[0], dict):
            out.append(r[0])
        elif isinstance(r, dict):
            # Motrix 下完会立刻把任务清掉：GID 找不到交给调用方看盘确认
            msg = str(r.get("message") or "")
            out.append({"status": "missing" if "not found" in msg.lower() else "error",
                        "errorMessage": msg})
        else:
            out.append({"status": "error", "errorMessage": "状态读不出来"})
    return out


def _aria2_cleanup(gids, port, secret):
    for g in gids:
        try:
            _aria2_call(port, secret, "aria2.forceRemove", [g], timeout=3)
        except Exception:
            pass


def _aria2_download(repo, local_dir, picked, ep, cfg, t0, on_progress, on_log,
                    stop, jobs):
    """交给 Motrix 下；返回摘要 dict（成功/失败），或 None 表示「没接上，用内置下载器」。"""
    m = _motrix_cfg(cfg)
    if not m:
        return None
    port, secret = m
    try:
        _aria2_call(port, secret, "aria2.getVersion", [], timeout=1.5)
    except Exception:
        _log(on_log, "ℹ️ Motrix 开着但 RPC 没通，改用内置下载器")
        return None

    endpoints = []
    for x in [ep] + list(cfg.get("endpoints") or []):
        x = str(x or "").rstrip("/")
        if x and x not in endpoints:
            endpoints.append(x)

    done0, total = 0, sum(max(0, int(f["size"] or 0)) for f in picked)
    todo, skipped = [], 0
    for f in picked:
        path = _safe_join(local_dir, f["path"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        size = max(0, int(f["size"] or 0))
        if size == 0:
            open(path, "wb").close()
            skipped += 1
            continue
        if os.path.isfile(path) and os.path.getsize(path) == size:
            done0 += size
            skipped += 1
            continue
        if _load_sidecar(path, size):
            # 内置下载器已经切好段了，aria2 接不上这份进度：整单交给内置
            return None
        todo.append({"path": path, "rel": f["path"], "size": size})
    if not todo:
        return {"ok": True, "endpoint": ep, "files": len(picked), "bytes": total,
                "seconds": round(time.time() - t0, 1), "resumed": done0, "error": ""}

    tok = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    header = ["Authorization: Bearer " + tok] if tok else []
    gids = {}
    try:
        for f in todo:
            uris = [_url(x, repo, f["rel"]) for x in endpoints]
            opts = {
                "dir": os.path.dirname(f["path"]),
                "out": os.path.basename(f["path"]),
                "continue": "true", "allow-overwrite": "true",
                "auto-file-renaming": "false",
                "split": str(max(1, min(16, int(jobs)))),
                "max-connection-per-server": str(max(1, min(16, int(jobs)))),
                "min-split-size": "8M",
            }
            if header:
                opts["header"] = header
            gid = _aria2_call(port, secret, "aria2.addUri", [uris, opts], timeout=10)
            gids[gid] = f["rel"]
    except Exception as e:      # noqa: BLE001
        _aria2_cleanup(list(gids), port, secret)
        _log(on_log, "⚠️ 交给 Motrix 失败（%s），改用内置下载器" % e)
        return None

    _log(on_log, "🚀 交给 Motrix 下载 %d 个文件（aria2 多连接 + 断点续传）" % len(todo))
    gid_list = list(gids)
    files_total = len(picked)
    while True:
        if stop.is_set():
            _aria2_cleanup(gid_list, port, secret)
            _emit(on_progress, {"busy": False, "phase": "aria2", "repo": repo,
                                "done": done0, "total": total, "speed": 0, "eta": 0,
                                "files_done": skipped, "files_total": files_total})
            return {"ok": False, "endpoint": ep, "files": 0, "bytes": 0,
                    "seconds": round(time.time() - t0, 1), "resumed": done0,
                    "error": "已手动停止"}
        st = _aria2_status(port, secret, gid_list)
        if st is None:
            _aria2_cleanup(gid_list, port, secret)
            _log(on_log, "⚠️ 连不上 Motrix 的下载状态，改用内置下载器")
            return None
        # 完成的任务会被 Motrix 立刻清掉：GID 没了就看盘上文件齐不齐
        lost = 0
        for x, f in zip(st, todo):
            if x.get("status") != "missing":
                continue
            if os.path.isfile(f["path"]) and os.path.getsize(f["path"]) == f["size"]:
                x["status"] = "complete"
                x["completedLength"] = str(f["size"])
            else:
                lost += 1
        if lost:
            _aria2_cleanup(gid_list, port, secret)
            _log(on_log, "⚠️ Motrix 里的任务被清掉、文件也没落全，改用内置下载器")
            return {"ok": False, "endpoint": ep, "files": 0, "bytes": 0,
                    "seconds": round(time.time() - t0, 1), "resumed": done0,
                    "error": "Motrix 任务被清掉，文件没落全"}
        done = done0 + sum(int(x.get("completedLength") or 0) for x in st)
        speed = sum(float(x.get("downloadSpeed") or 0) for x in st)
        files_done = skipped + sum(1 for x in st if x.get("status") == "complete")
        active = [gids[g] for g, x in zip(gid_list, st)
                  if x.get("status") in ("active", "waiting", "paused")]
        _emit(on_progress, {
            "busy": True, "phase": "aria2", "repo": repo,
            "file": active[0] if active else "", "file_done": 0, "file_total": 0,
            "done": min(done, total), "total": total, "speed": round(speed, 1),
            "eta": round(max(0, total - done) / speed, 1) if speed > 1 else 0,
            "endpoint": ep, "workers": int(jobs),
            "files_done": files_done, "files_total": files_total,
        })
        bad = [x for x in st if x.get("status") in ("error", "removed")]
        if bad:
            why = str(bad[0].get("errorMessage") or "下载出错")
            _aria2_cleanup(gid_list, port, secret)
            _log(on_log, "⚠️ Motrix 报错：%s，改用内置下载器" % why)
            return {"ok": False, "endpoint": ep, "files": 0, "bytes": 0,
                    "seconds": round(time.time() - t0, 1), "resumed": done0,
                    "error": why}
        if all(x.get("status") == "complete" for x in st):
            _emit(on_progress, {"busy": False, "phase": "aria2", "repo": repo,
                                "done": total, "total": total, "speed": 0, "eta": 0,
                                "files_done": files_total, "files_total": files_total})
            return {"ok": True, "endpoint": ep, "files": len(picked), "bytes": total,
                    "seconds": round(time.time() - t0, 1), "resumed": done0,
                    "error": ""}
        stop.wait(0.8)
    return None


# ---------------------------------------------------------------- 主入口
def download(repo, local_dir, allow=None, jobs=8, chunk_mb=64, retries=20,
             timeout=60, endpoints=None, endpoint=None, probe_timeout=8,
             on_progress=None, on_log=None, stop=None, config=None):
    """把 repo 里选中的文件下到 local_dir。返回摘要 dict，不抛网络异常。

    on_progress(ev)：ev 里 done/total/speed/eta/file/... 都是界面直接能画的数。
    on_log(str)：换镜像、重试、文件切换这类「事发经过」。
    """
    cfg = dict(DEFAULTS)
    cfg.update(config or {})
    cfg.update({"jobs": jobs, "chunk_mb": chunk_mb, "retries": retries,
                "timeout": timeout, "probe_timeout": probe_timeout})
    if endpoints:
        cfg["endpoints"] = endpoints
    stop = stop or threading.Event()
    t0 = time.time()
    local_dir = os.path.abspath(local_dir)
    os.makedirs(local_dir, exist_ok=True)
    _log(on_log, "📥 %s → %s（%d 线程 · 断点续传）" % (repo, local_dir, int(jobs)))

    try:
        ep, files = list_repo(repo, cfg, endpoint=endpoint, on_log=on_log)
    except Exception as e:
        _log(on_log, "❌ 拿不到文件清单：%s" % e)
        return _hub_fallback(repo, local_dir, allow, cfg, t0, on_progress,
                             on_log, stop, str(e))

    picked = select_files(files, allow)
    if not picked:
        return {"ok": False, "endpoint": ep, "files": 0, "bytes": 0,
                "seconds": round(time.time() - t0, 1), "resumed": 0,
                "error": "allow 模式没匹配到任何文件"}
    total = sum(max(0, f["size"]) for f in picked)

    # 装了 Motrix 就先交给它的 aria2；不可用、下到一半报错再走内置分段下载器。
    # 停在「交给内置」这条路上时，已经下完的文件会被下面识别成 complete，不会重下。
    if cfg.get("motrix", True) is not False:
        a = _aria2_download(repo, local_dir, picked, ep, cfg, t0,
                            on_progress, on_log, stop, jobs)
        if a is not None:
            if a.get("ok") or a.get("error") == "已手动停止":
                return a
            _log(on_log, "↩️ Motrix 没下完（%s），改用内置下载器" % (a.get("error") or "未知"))
            for f in picked:
                try:
                    os.remove(_safe_join(local_dir, f["path"]) + ".aria2")
                except OSError:
                    pass

    done0 = 0
    prepared = []        # [{path,size,chunks,complete}]
    for f in picked:
        path = _safe_join(local_dir, f["path"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        size = max(0, f["size"])
        if size == 0:
            prepared.append({"path": path, "rel": f["path"], "size": 0,
                             "chunks": [], "complete": False})
            continue
        sc = _load_sidecar(path, size)
        exists = os.path.isfile(path)
        if not exists and not sc:
            prepared.append({"path": path, "rel": f["path"], "size": size,
                             "chunks": None, "complete": False})
            continue
        if exists and os.path.getsize(path) == size and not sc:
            # 没有 sidecar 的满尺寸文件：当作已完成（hub 下的文件就是这样）
            done0 += size
            prepared.append({"path": path, "rel": f["path"], "size": size,
                             "chunks": None, "complete": True})
            continue
        chunks = sc or _plan_chunks(size, max(1, int(chunk_mb)) * 1024 * 1024)
        done0 += sum(c["done"] for c in chunks)
        prepared.append({"path": path, "rel": f["path"], "size": size,
                         "chunks": chunks, "complete": False})

    counter = _Counter(done0)
    meter = _Meter()
    active = {p["path"]: p for p in prepared if not p["complete"]}
    finish = {"files_done": len(prepared) - len(active), "files_total": len(prepared)}

    def emit(file_rel="", file_done=0, file_total=0, force=False):
        d = counter.get()
        sp = meter.tick(d)
        left = max(0, total - d)
        _emit(on_progress, {
            "busy": not force, "phase": "download", "repo": repo,
            "file": file_rel, "file_done": file_done, "file_total": file_total,
            "done": d, "total": total, "speed": round(sp, 1),
            "eta": round(left / sp, 1) if sp > 1 else 0,
            "endpoint": ep, "workers": int(jobs),
            "files_done": finish["files_done"], "files_total": finish["files_total"],
        })

    stop_sidecar = threading.Event()

    def sidecar_loop():
        while not stop_sidecar.wait(1.5):
            for p in list(active.values()):
                if p["chunks"]:
                    _save_sidecar(p["path"], p["size"], p["chunks"])
            emit()

    threading.Thread(target=sidecar_loop, daemon=True).start()
    emit()
    error = ""
    try:
        for idx, p in enumerate(prepared, 1):
            if stop.is_set():
                error = "已手动停止"
                break
            path, size = p["path"], p["size"]
            if p["complete"]:
                _log(on_log, "✅ 已在本地，跳过 %s" % p["rel"])
                continue
            _log(on_log, "⬇️ [%d/%d] %s（%s）" % (idx, len(prepared), p["rel"], fmt_bytes(size)))
            if size == 0:
                open(path, "wb").close()
                p["complete"] = True
            else:
                url = _url(ep, repo, p["rel"])
                chunks = p["chunks"]
                if chunks is None:
                    chunks = _plan_chunks(size, max(1, int(chunk_mb)) * 1024 * 1024)
                    p["chunks"] = chunks
                # sidecar 必须先于预分配：预分配后硬杀，满尺寸文件会被当成下完了
                _save_sidecar(path, size, chunks)
                with open(path, "a+b") as f:
                    f.truncate(size)
                supports = size < _MIN_CHUNK_BYTES
                remote = size
                if size >= _MIN_CHUNK_BYTES and len(chunks) > 1:
                    try:
                        supports, remote = _probe_range(url, float(cfg["timeout"]))
                    except Exception as e:      # noqa: BLE001
                        _log(on_log, "⚠️ 探测 Range 失败，按单流下：%s" % e)
                        supports = False
                    if remote and remote != size:
                        _log(on_log, "⚠️ 远端大小 %s 与清单 %s 不一致，按远端重排"
                             % (fmt_bytes(remote), fmt_bytes(size)))
                        prior = sum(c["done"] for c in chunks)
                        counter.add(-prior)
                        total += remote - size
                        size = p["size"] = remote
                        chunks = p["chunks"] = _plan_chunks(
                            size, max(1, int(chunk_mb)) * 1024 * 1024)
                        _save_sidecar(path, size, chunks)
                        with open(path, "a+b") as f:
                            f.truncate(size)
                if not supports:
                    # 服务器不理 Range：所有分段作废，从头单流写一遍
                    prior = sum(c["done"] for c in chunks)
                    counter.add(-prior)
                    for c in chunks:
                        c["done"] = 0
                    with open(path, "r+b") as f:
                        _fetch_single(url, f, size, counter, stop,
                                      float(cfg["timeout"]), int(cfg["retries"]))
                    chunks = p["chunks"] = [{"start": 0, "end": size - 1, "done": size}]
                    _save_sidecar(path, size, chunks)
                    p["complete"] = True
                elif len(chunks) <= 1:
                    pending = [c for c in chunks if c["done"] <= c["end"] - c["start"]]
                    if not pending:
                        p["complete"] = True
                    else:
                        c = pending[0]
                        c["_size"] = size
                        with open(path, "r+b") as f:
                            _fetch_chunk(url, f, c, counter, stop,
                                         float(cfg["timeout"]), int(cfg["retries"]))
                        _save_sidecar(path, size, chunks)
                        p["complete"] = True
                else:
                    threads = []
                    errs = []

                    def worker(c):
                        try:
                            c["_size"] = size
                            with open(path, "r+b") as f:
                                _fetch_chunk(url, f, c, counter, stop,
                                             float(cfg["timeout"]), int(cfg["retries"]))
                        except Exception as e:      # noqa: BLE001
                            errs.append(e)

                    maxw = max(1, min(int(jobs), len(chunks)))
                    sem = threading.Semaphore(maxw)
                    for c in chunks:
                        if c["done"] > c["end"] - c["start"]:
                            continue
                        sem.acquire()

                        def run(c=c):
                            try:
                                worker(c)
                            finally:
                                sem.release()
                        th = threading.Thread(target=run, daemon=True)
                        th.start()
                        threads.append(th)
                    for th in threads:
                        th.join()
                    _save_sidecar(path, size, chunks)
                    if errs:
                        raise errs[0]
                    if not all(c["done"] > c["end"] - c["start"] for c in chunks):
                        raise OSError("有分段没下完")
                    p["complete"] = True
            if p["complete"]:
                try:
                    os.remove(_sidecar(path))
                except OSError:
                    pass
                finish["files_done"] += 1
                active.pop(path, None)
                _log(on_log, "✅ 完成 %s" % p["rel"])
                emit(p["rel"], size, size)
    except Exception as e:      # noqa: BLE001
        error = str(e)
        _log(on_log, "❌ 下载中断：%s" % e)
    finally:
        stop_sidecar.set()
        for p in active.values():
            if p.get("chunks"):
                _save_sidecar(p["path"], p["size"], p["chunks"])

    if error:
        # 自家下载器没走通才回落 hub；先清掉预分配的空壳，免得 hub 当成已完成
        for p in prepared:
            if not p["complete"] and p.get("chunks"):
                try:
                    os.remove(p["path"])
                except OSError:
                    pass
                try:
                    os.remove(_sidecar(p["path"]))
                except OSError:
                    pass
        return _hub_fallback(repo, local_dir, allow, cfg, t0, on_progress,
                             on_log, stop, error)

    emit(force=True)
    secs = max(0.1, time.time() - t0)
    return {"ok": True, "endpoint": ep, "files": len(prepared),
            "bytes": total, "seconds": round(secs, 1), "resumed": done0,
            "error": ""}


# ---------------------------------------------------------------- 回落
def _hub_fallback(repo, local_dir, allow, cfg, t0, on_progress, on_log,
                  stop, why):
    """huggingface_hub 兜底：分段/镜像都不行时至少还能下，只是慢且进度粗。"""
    if stop.is_set():
        return {"ok": False, "endpoint": "", "files": 0, "bytes": 0,
                "seconds": round(time.time() - t0, 1), "resumed": 0,
                "error": "已手动停止"}
    _log(on_log, "↩️ 改用 huggingface_hub 兜底（原因：%s）" % why)
    try:
        ep = (cfg.get("endpoints") or ["https://hf-mirror.com"])[0]
        os.environ["HF_ENDPOINT"] = ep
        import huggingface_hub
    except Exception as e:      # noqa: BLE001
        return {"ok": False, "endpoint": "", "files": 0, "bytes": 0,
                "seconds": round(time.time() - t0, 1), "resumed": 0,
                "error": "huggingface_hub 不可用：%s" % e}
    base = _dir_bytes(local_dir)
    meter = _Meter()
    watch_stop = threading.Event()

    def watch():
        while not watch_stop.wait(2):
            d = _dir_bytes(local_dir)
            sp = meter.tick(d)
            _emit(on_progress, {
                "busy": True, "phase": "hub", "repo": repo, "file": "",
                "file_done": 0, "file_total": 0,
                "done": d, "total": 0, "speed": round(sp, 1), "eta": 0,
                "endpoint": ep, "workers": int(cfg.get("jobs") or 4),
                "files_done": 0, "files_total": 0,
            })
    threading.Thread(target=watch, daemon=True).start()
    err = ""
    try:
        for attempt in range(1, int(cfg.get("retries") or 20) + 1):
            if stop.is_set():
                err = "已手动停止"
                break
            try:
                huggingface_hub.snapshot_download(
                    repo_id=repo, local_dir=local_dir,
                    allow_patterns=allow or None,
                    max_workers=int(cfg.get("jobs") or 4),
                    etag_timeout=float(cfg.get("timeout") or 60))
                return {"ok": True, "endpoint": ep, "files": 0,
                        "bytes": max(0, _dir_bytes(local_dir) - base),
                        "seconds": round(time.time() - t0, 1),
                        "resumed": base, "error": ""}
            except Exception as e:      # noqa: BLE001
                err = str(e)
                wait = min(5 * attempt, 30)
                _log(on_log, "⚠️ hub 第 %d 次中断：%s · %d 秒后重试" % (attempt, e, wait))
                time.sleep(wait)
    finally:
        # 不叫停的话它会每 2 秒继续发 busy=True，把界面上的下载横幅一直焊死
        watch_stop.set()
        _emit(on_progress, {"busy": False, "phase": "hub", "repo": repo,
                            "done": _dir_bytes(local_dir), "total": 0,
                            "speed": 0, "eta": 0, "endpoint": ep,
                            "files_done": 0, "files_total": 0})
    return {"ok": False, "endpoint": ep, "files": 0, "bytes": 0,
            "seconds": round(time.time() - t0, 1), "resumed": base, "error": err}


if __name__ == "__main__":      # 手工验证：python -m webui.envkit.download org/name 目标目录
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("dir")
    ap.add_argument("--allow", action="append", default=[])
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--endpoint", default="")
    a = ap.parse_args()
    r = download(a.repo, a.dir, allow=a.allow or None, jobs=a.jobs,
                 endpoint=a.endpoint or None,
                 on_log=lambda s: print(s, flush=True),
                 on_progress=lambda e: print("\r%s / %s  %s/s" % (
                     fmt_bytes(e["done"]), fmt_bytes(e["total"]),
                     fmt_bytes(e["speed"])), end="", flush=True))
    print("\n", r)
