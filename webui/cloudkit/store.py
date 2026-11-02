# -*- coding: utf-8 -*-
"""账号库：一个账号 = 一份浏览器状态（cookies + localStorage）+ 可选的 API Key。

为什么不给每个账号一只浏览器：Chromium 的 user-data-dir 是启动参数，进程活着就换不了；
调试端口也一次只认一个进程。共用一只浏览器、换号时整份替换存储，才是
「一个端口跑多个账号」——也就是用户要的「浏览器做平台，只变数据路径」。

落盘（data/cloud/u/<id>/）：
  latest.json               最近一次保存（换号时读它）
  <yyyymmdd-hhmmss-mmm>.json 历次备份，保留 MAX_BACKUPS 份，多的从旧往新删
  key.json                  API Key（有才写；和快照分开——恢复旧快照不能把 key 带回空值）
accounts.json 只存名字与状态摘要，**不含任何凭据**；日志也只许出现名字。
"""
import json
import os
import re
import shutil
import time
import uuid

MAX_BACKUPS = 12
TS_RE = re.compile(r"^\d{8}-\d{6}-\d{3}$")
# Chrome 还回来的 cookie 字段很多，只留回填时真正用得上的这些；
# 凭据值只在 data/cloud 里躺着，不进索引、不进日志、不回给界面。
_COOKIE_KEYS = ("name", "value", "domain", "path", "expires",
                "httpOnly", "secure", "sameSite", "priority")


def clean_cookies(cookies):
    """去重 + 只留已知字段：Chrome 的 Cookie 对象直接 json.dump 会带出枚举/时间对象。"""
    out, seen = [], set()
    for c in cookies or []:
        try:
            d = dict(c)
        except (TypeError, ValueError):
            continue
        item = {}
        for k in _COOKIE_KEYS:
            v = d.get(k)
            if v is None:
                continue
            if isinstance(v, (int, float, bool, str)):
                item[k] = v
        name = str(item.get("name") or "")
        if not name:
            continue
        key = (name, str(item.get("domain") or ""), str(item.get("path") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def domain_ok(domain, suffixes):
    """domain 是否属于给定站点（去掉前导点后按后缀比）。suffixes 为空＝全收。"""
    if not suffixes:
        return True
    d = str(domain or "").lstrip(".").lower()
    return any(d == s or d.endswith("." + s) for s in suffixes if s)


def filter_cookies(cookies, suffixes=None):
    return [c for c in clean_cookies(cookies)
            if domain_ok(c.get("domain"), suffixes)]


# 平台真正的凭据只有这几个名字。其余 Rh-* 是埋点开关和画布偏好——
# 以前按「Rh- 开头都算」收，18 个「鉴权头」里一半是缩放灵敏度，
# 既骗人又可能把无关值发出去。清单化之后，多出来的名字一律不收。
AUTH_NAMES = ("Rh-Accesstoken", "Rh-Refreshtoken", "Rh-Comfy-Auth",
              "Rh-Identify", "Rh-Expire-In", "Rh-Comfy-Expire-In")


def auth_headers(cookies, storage=None):
    """按名字挑出协议侧要的鉴权值：cookie 先，localStorage 补。

    平台把 Rh-Identify / Rh-Comfy-Auth 这类值放在 cookie 或 localStorage 里，
    浏览器自动化能拿到它们，后续走协议（上传、提交）就不用再开页面。
    这里只负责取，不负责用；谁调用谁保存，别写进日志。
    """
    have = {}
    for c in cookies or []:
        n = str(c.get("name") or "")
        v = str(c.get("value") or "")
        if n and v and n not in have:
            have[n] = v
    st = storage or {}
    out = {}
    for n in AUTH_NAMES:
        v = have.get(n) or str(st.get(n) or "")
        if v:
            out[n] = v
    return out


def mask_secret(s, keep=4):
    s = str(s or "")
    if not s:
        return ""
    if len(s) <= keep * 2:
        return "*" * len(s)
    return s[:keep] + "***" + s[-keep:]


# 第三方库报错时常把它正在处理的值原样打回（DrissionPage 设 cookie 失败就是这么一句），
# 而这句话会流进界面状态行、日志和账号索引。凡看起来像长令牌的（≥16 位无空格）一律截半。
_RE_LONG = re.compile(r"[A-Za-z0-9_\-]{16,}")


def brief_error(e, limit=120):
    """给界面与日志用的一句错：压成一行、抹掉长令牌，别把凭据带出去。"""
    try:
        text = str(e) or type(e).__name__
    except Exception:
        text = type(e).__name__
    text = " ".join(str(text).split())[:limit]
    return _RE_LONG.sub(lambda m: mask_secret(m.group(0)), text)


def cloud_dir(root):
    """账号库根目录。自测用 QIC_CLOUD_DIR 指到临时目录，别把假 cookie 写进用户目录。"""
    return os.environ.get("QIC_CLOUD_DIR") or os.path.join(root, "data", "cloud")


def _now():
    return int(time.time())


def _stamp():
    return time.strftime("%Y%m%d-%H%M%S") + "-%03d" % (int(time.time() * 1000) % 1000)


def _atomic_json(path, obj, private=False):
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    if private:
        try:                     # Windows 上 chmod 只是尽力而为；目录本身在本地
            os.chmod(path, 0o600)
        except OSError:
            pass


def _read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


class AccountStore:
    def __init__(self, root):
        self.root = root
        self.dir = cloud_dir(root)
        self.index_path = os.path.join(self.dir, "accounts.json")
        self._lock = None

    # ---------- 基础 ----------
    def _lock_obj(self):
        if self._lock is None:
            import threading
            self._lock = threading.RLock()
        return self._lock

    def _index(self):
        data = _read_json(self.index_path, {})
        if not isinstance(data, dict):
            return {"ver": 1, "accounts": []}
        if not isinstance(data.get("accounts"), list):
            data["accounts"] = []      # 索引被写坏时别让新建号直接 KeyError
        return data

    def _write_index(self, data):
        data["ver"] = 1
        _atomic_json(self.index_path, data)

    def _find(self, data, aid):
        for a in data.get("accounts") or []:
            if a.get("id") == aid:
                return a
        return None

    def acct_dir(self, aid):
        return os.path.join(self.dir, "u", aid)

    # ---------- 读 ----------
    def list(self):
        """给界面的账号表：名字、状态、备份数，没有任何凭据。"""
        with self._lock_obj():
            data = self._index()
            out = []
            for a in data.get("accounts") or []:
                aid = a.get("id")
                if not aid:
                    continue
                row = {k: a.get(k) for k in
                       ("id", "name", "created", "last_saved", "last_check",
                        "state", "detail")}
                row["backups"] = len(self.backups(aid))
                row["has_key"] = os.path.isfile(os.path.join(self.acct_dir(aid), "key.json"))
                out.append(row)
            return out

    def get(self, aid):
        with self._lock_obj():
            return dict(self._find(self._index(), aid) or {})

    def exists(self, aid):
        return bool(self.get(aid))

    # ---------- 写 ----------
    def create(self, name=""):
        with self._lock_obj():
            data = self._index()
            aid = "acc_" + uuid.uuid4().hex[:10]
            name = str(name or "").strip()[:24] or "账号 %d" % (len(data["accounts"]) + 1)
            row = {"id": aid, "name": name, "created": _now(),
                   "last_saved": 0, "last_check": 0,
                   "state": "new", "detail": ""}
            data["accounts"].append(row)
            self._write_index(data)
            os.makedirs(self.acct_dir(aid), exist_ok=True)
            return dict(row)

    def rename(self, aid, name):
        name = str(name or "").strip()[:24]
        if not name:
            return False
        with self._lock_obj():
            data = self._index()
            row = self._find(data, aid)
            if not row:
                return False
            row["name"] = name
            self._write_index(data)
            return True

    def delete(self, aid):
        with self._lock_obj():
            data = self._index()
            before = len(data["accounts"])
            data["accounts"] = [a for a in data["accounts"] if a.get("id") != aid]
            if len(data["accounts"]) == before:
                return False
            self._write_index(data)
            shutil.rmtree(self.acct_dir(aid), ignore_errors=True)
            return True

    def save(self, aid, cookies, storage=None, url=""):
        """落一份新快照（latest + 带时间戳的备份），返回时间戳。"""
        with self._lock_obj():
            data = self._index()
            row = self._find(data, aid)
            if not row:
                return ""
            ts = _stamp()
            payload = {"ts": ts, "saved": _now(), "url": str(url or "")[:300],
                       "cookies": clean_cookies(cookies),
                       "storage": {str(k): str(v) for k, v in (storage or {}).items()}}
            d = self.acct_dir(aid)
            _atomic_json(os.path.join(d, ts + ".json"), payload, private=True)
            _atomic_json(os.path.join(d, "latest.json"), payload, private=True)
            row["last_saved"] = payload["saved"]
            row["state"] = "saved"
            row["detail"] = ""
            self._write_index(data)
            self._prune(aid)
            return ts

    def _prune(self, aid):
        try:
            names = [n for n in os.listdir(self.acct_dir(aid))
                     if TS_RE.match(n[:-5]) and n.endswith(".json")]
        except OSError:
            return
        names.sort()
        for n in names[:-MAX_BACKUPS]:
            try:
                os.remove(os.path.join(self.acct_dir(aid), n))
            except OSError:
                pass

    def backups(self, aid):
        try:
            names = [n[:-5] for n in os.listdir(self.acct_dir(aid))
                     if n.endswith(".json") and TS_RE.match(n[:-5])]
        except OSError:
            return []
        names.sort(reverse=True)
        return names

    def load(self, aid, ts=""):
        """读一份快照；ts 非法或不存在回 None（ts 来自界面，必须先过格式关）。"""
        if ts and not TS_RE.match(str(ts)):
            return None
        path = os.path.join(self.acct_dir(aid),
                            (str(ts) + ".json") if ts else "latest.json")
        d = _read_json(path)
        if not isinstance(d, dict):
            return None
        return {"cookies": clean_cookies(d.get("cookies")),
                "storage": {str(k): str(v) for k, v in (d.get("storage") or {}).items()},
                "url": d.get("url") or "", "ts": d.get("ts") or ""}

    def restore(self, aid, ts):
        """把某份备份复制成「最近一份」——不删除历史，恢复本身也可再撤回。"""
        d = self.load(aid, ts)
        if not d:
            return ""
        return self.save(aid, d["cookies"], d["storage"], d["url"])

    def mark(self, aid, state, detail=""):
        with self._lock_obj():
            data = self._index()
            row = self._find(data, aid)
            if not row:
                return
            row["state"] = str(state or "")[:16]
            row["detail"] = str(detail or "")[:160]
            row["last_check"] = _now()
            self._write_index(data)

    # ---------- API Key ----------
    def set_key(self, aid, key):
        key = str(key or "").strip()
        if not key or not self.exists(aid):
            return False
        _atomic_json(os.path.join(self.acct_dir(aid), "key.json"),
                     {"api_key": key}, private=True)
        return True

    def get_key(self, aid):
        d = _read_json(os.path.join(self.acct_dir(aid), "key.json"), {})
        return str(d.get("api_key") or "") if isinstance(d, dict) else ""

    def clear_key(self, aid):
        try:
            os.remove(os.path.join(self.acct_dir(aid), "key.json"))
            return True
        except OSError:
            return False
