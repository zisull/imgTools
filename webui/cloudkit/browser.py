# -*- coding: utf-8 -*-
"""共用一只调试浏览器：换号只换数据（cookies + localStorage），不重启、不换端口。

Chromium 的 user-data-dir 是启动参数，进程活着就改不了；调试端口也只能对一个进程。
所以多账号不是「多开浏览器」，而是「一只浏览器 + 多份快照」：
  apply(id)   清空当前存储 → 灌入该账号快照 → 刷新
  snapshot(id) 把当前存储抽出来（cookie 带域名/过期时间）
  sweep()     挨个换号访问平台，把服务端刷新后的 cookie 再存回去（保活）

浏览器只在真要登录/保活时才启动（DrissionPage 也只在那一刻 import）；
启动路径上不碰它，跟「App() 里不 import torch」是同一条规矩。
"""
import os
import re
import threading
import time

from .store import (auth_headers, brief_error, clean_cookies, cloud_dir,
                    filter_cookies)

# 页面刷新后判断「登录还在不在」：先看强信号，再看登录入口；
# 两边都没有就老实说「没验证」——不拿猜的结论写进账号状态。
_JS_BODY = "return (document.body && document.body.innerText || '').slice(0, 4000)"
_RE_OK = re.compile(r"退出登录|个人中心|我的账号|账户设置")
_RE_OUT = re.compile(r"登录\s*/\s*注册|立即登录|扫码登录|手机号登录")


def cookie_fp(cookies):
    """只比「换号真正相关」的字段：Chrome 每次回读的顺序/附加字段会变。"""
    rows = []
    for c in clean_cookies(cookies):
        rows.append((c.get("name"), c.get("domain"), c.get("path"),
                     c.get("value"), c.get("expires")))
    return sorted(rows, key=lambda x: tuple(str(v) for v in x))


def apply_state(tab, state):
    """把一份快照灌进当前标签页：先清空，再逐条设 cookie，最后对齐 localStorage。

    清空是必须的：共用一只浏览器，残留的上一个账号 cookie 会让平台认错人。
    """
    state = state or {}
    cookies = clean_cookies(state.get("cookies"))
    storage = {str(k): str(v) for k, v in (state.get("storage") or {}).items()}
    try:
        tab.set.cookies.clear()
    except Exception:
        pass
    if cookies:
        try:
            tab.set.cookies(cookies)
        except Exception as e:      # 个别字段（sameSite 枚举）不被接受时逐条退让
            for c in cookies:
                try:
                    tab.set.cookies(c)
                except Exception:
                    continue
    try:
        cur = tab.local_storage() or {}
    except Exception:
        cur = {}
    for k in list(cur):
        if k not in storage:
            try:
                tab.set.local_storage(k, False)
            except Exception:
                pass
    for k, v in storage.items():
        try:
            tab.set.local_storage(k, v)
        except Exception:
            pass


def snapshot_state(tab, domains=None):
    try:
        raw = tab.cookies(all_domains=True, all_info=True) or []
    except Exception:
        raw = []
    rows = []
    for c in raw:
        try:
            rows.append(dict(c))
        except (TypeError, ValueError):
            continue
    try:
        storage = dict(tab.local_storage() or {})
    except Exception:
        storage = {}
    return {"cookies": filter_cookies(rows, domains), "storage": storage,
            "url": str(getattr(tab, "url", "") or "")}


def login_state(tab):
    """返回 (state, detail)：ok / expired / unknown。"""
    url = str(getattr(tab, "url", "") or "")
    if "/login" in url.lower():
        return "expired", "跳到了登录页"
    try:
        body = str(tab.run_js(_JS_BODY) or "")
    except Exception:
        body = ""
    if _RE_OK.search(body):
        return "ok", "页面有登录后的入口"
    if _RE_OUT.search(body):
        return "expired", "页面只有登录入口"
    return "unknown", "已保存，页面没有明确信号"


class BrowserHost:
    def __init__(self, root, cfg=None, log=None, port=None, profile=None):
        self.root = root
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self.log = log or (lambda *_: None)
        # 端口与 user-data-dir 都是 Chromium 的启动参数，一个进程一套。
        # 成片要多个号同时跑时，每个号各给一只（见 pool.py），主窗口仍用默认那套。
        self.port = int(port or self.cfg.get("port") or 9333)
        self.base = str(self.cfg.get("base") or "https://www.runninghub.cn").rstrip("/")
        self.profile = str(profile or "").strip() or os.path.join(cloud_dir(root), "browser")
        self.domains = [str(s).lstrip(".").lower()
                        for s in (self.cfg.get("domains") or ["runninghub.cn"]) if s]
        self._b = None
        self._lock = threading.RLock()
        self.current = ""
        # 这段浏览器的用途：login=人正在登录/看，gen=云端出片占着，''=空闲。
        # 保活与手动操作都先看它，别再拿一个布尔猜来猜去。
        self.purpose = ""

    @property
    def lock(self):
        return self._lock

    # ---------- 进程 ----------
    def _opts(self):
        from DrissionPage import ChromiumOptions
        co = ChromiumOptions(read_file=False)   # 不读用户级 ini，端口/路径只认这里
        co.set_local_port(self.port)
        co.set_user_data_path(self.profile)
        path = str(self.cfg.get("browser") or "").strip()
        if path:
            co.set_browser_path(path)
        co.set_load_mode("eager")
        co.set_timeouts(base=10, page_load=30, script=20)
        co.set_argument("--no-default-browser-check")
        co.set_argument("--disable-features=Translate,MediaRouter")
        # 登录页弹「保存密码」会挡住按钮；这是浏览器自己的提示，不影响平台判定
        co.set_pref("credentials_enable_service", False)
        co.set_pref("profile.password_manager_enabled", False)
        return co

    @staticmethod
    def _conn_ok(b):
        try:
            return int(b.tabs_count) >= 0
        except Exception:
            return False

    def browser(self):
        """拿浏览器连接；窗口被人关掉时丢掉死连接再重开。

        以前这里只判 `_b is None`：用户把那只调试窗口叉掉后，`_b` 还指望它活着，
        之后每一次云端出片都撞同一份死连接（「与页面的连接已断开」），只能重启软件。
        """
        with self._lock:
            if self._b is not None and not self._conn_ok(self._b):
                self._b = None
            if self._b is None:
                from DrissionPage import Chromium
                os.makedirs(self.profile, exist_ok=True)
                self._b = Chromium(self._opts())
            return self._b

    def alive(self, wait=True):
        """读的是 self._b 这份共享状态：与 browser()/close() 同一把锁，不然就是数据竞争。

        出片那整段都占着这把锁（见 gen.run）：界面轮询只要一句「开没开」，
        wait=False 时锁被占着就按「进程还在」回答，别为探活把 UI 线程卡到出片结束。
        """
        if wait:
            self._lock.acquire()
        elif not self._lock.acquire(blocking=False):
            return self._b is not None
        try:
            if self._b is None:
                return False
            if not self._conn_ok(self._b):
                self._b = None
                return False
            return True
        finally:
            self._lock.release()

    def tab(self):
        """拿一个能用的页：连接断了就重连/重开一次。

        窗口关掉后留下的死连接不该让这一路永久报废；重开一次还拿不到页才报错。
        """
        with self._lock:
            for _ in range(2):
                b = self.browser()          # 自己会丢掉死连接
                try:
                    return b.latest_tab
                except IndexError:
                    try:                    # 窗口在，只是最后一页被关了
                        return b.new_tab()
                    except Exception:
                        self._b = None
                except Exception:
                    self._b = None
            raise RuntimeError("浏览器窗口被关掉了，自动重开也没连上：再点一次开始")

    def reset(self):
        """丢掉当前连接（不主动杀窗口）：下一次 tab() 会重连或重开一只。"""
        with self._lock:
            self._b = None
            self.current = ""
            self.purpose = ""

    def close(self, force=False):
        with self._lock:
            b, self._b = self._b, None
            self.current = ""
            self.purpose = ""
            if b is None:
                return
            try:
                b.quit(timeout=5, force=bool(force))
            except Exception:
                pass

    def restart(self):
        """把这只调试浏览器整个关掉，下一次 browser() 再拉起一只干净的。

        页面卡死、登录态被平台踢掉时，reset() 只丢连接仍会接回同一个坏进程；
        成片「失败重试一次」要的是新进程，所以这里连进程一起收掉。
        """
        with self._lock:
            b, self._b = self._b, None
            self.current = ""
            self.purpose = ""
            if b is not None:
                try:
                    b.quit(timeout=5, force=True)
                except Exception:
                    pass
            time.sleep(0.8)     # 等端口上的旧进程退干净，别让新连接又挂回它
        return self.browser()

    def occupied(self):
        """这只浏览器被人占着（登录 / 云端出片）＝保活必须让路。"""
        return bool(self.purpose)

    # ---------- 换号 ----------
    def apply(self, state, aid="", reload=True):
        """灌入快照并刷新。调用方负责串行（lock/App 侧的任务锁）。"""
        with self._lock:
            tab = self.tab()
            tab.get(self.base)          # 先在目标域上，cookie 才挂得到正确域名
            apply_state(tab, state)
            if reload:
                tab.get(self.base)
            self.current = aid or ""
            return tab.url

    def open_login(self, state=None, aid=""):
        url = str(self.cfg.get("login_url") or self.base)
        with self._lock:
            tab = self.tab()
            if state is not None:
                tab.get(self.base)
                apply_state(tab, state)
            self.purpose = "login"      # 人正在这个窗口里登录，保活别来顶号
            tab.get(url)
            self.current = aid or ""
            return tab.url

    def open_base(self, state=None, aid="", hold=False):
        with self._lock:
            tab = self.tab()
            if state is not None:
                tab.get(self.base)
                apply_state(tab, state)
            # hold：这次访问是「用户在软件里点的」，读完之前不让保活插进来换号
            self.purpose = "hold" if hold else ""
            tab.get(self.base)
            self.current = aid or ""
            return tab.url

    def snapshot(self):
        with self._lock:
            return snapshot_state(self.tab(), self.domains)

    def check(self):
        with self._lock:
            return login_state(self.tab())

    def headers(self, state):
        """从快照派生协议侧鉴权头（Rh-*）；只给内部用，别打日志。"""
        return auth_headers((state or {}).get("cookies"), (state or {}).get("storage"))


class KeepAlive:
    """后台保活：每 keep_min 分钟把每个账号轮着访问一遍。

    每个号用自己那只浏览器（host_for）：1 号走主窗口，2 号起走各自的独立窗口，
    互不顶号。某只没开就跳过它，绝不自己偷偷拉起一个窗口。
    """

    def __init__(self, host, store, cfg, log=None, busy=None, host_for=None):
        self.host = host
        self.store = store
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self.log = log or (lambda *_: None)
        # 有人在手动操作账号 / 云端正在出片：这两个都不许保活插进来换号
        self.busy = busy or (lambda: False)
        self.host_for = host_for or (lambda _aid: self.host)
        self.last = 0
        self.last_msg = "还没跑过"
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cloud-keep")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(60):
            if not self.cfg.get("keep", True):
                continue
            mins = max(5, int(self.cfg.get("keep_min") or 30))
            if time.time() - self.last < mins * 60:
                continue
            try:
                self.sweep()
            except Exception as e:
                self.last_msg = "保活出错：%s" % e

    def sweep(self, force=False):
        """返回这轮成功的账号数；某只浏览器没开或被占着就跳过它。

        force=True 是人在界面上点了「立即保活」：他自己就是那个 busy 的人，
        但云端出片（purpose=gen）那段照样不让插。
        """
        if not force and self.busy():
            self.last_msg = "有人在动这只浏览器，保活先让路"
            return 0
        done = live = gen = held = 0
        for a in self.store.list():
            aid = a["id"]
            host = self.host_for(aid)
            if host is None or not host.alive():
                continue
            live += 1
            if host.purpose == "gen":
                gen += 1
                continue
            if host.occupied():
                held += 1
                continue
            state = self.store.load(aid)
            if not state or not state.get("cookies"):
                continue
            try:
                with host.lock:
                    host.apply(state, aid=aid)
                    tab = host.tab()
                    tab.get(host.base)
                    st, detail = login_state(tab)
                    snap = snapshot_state(tab, host.domains)
                    # cookie 没变就不写盘：每 30 分钟一份把 12 份备份挤没了
                    if cookie_fp(snap["cookies"]) != cookie_fp(state.get("cookies")):
                        self.store.save(aid, snap["cookies"], snap["storage"], snap["url"])
                self.store.mark(aid, st, detail)
                done += 1
            except Exception as e:
                self.store.mark(aid, "error", brief_error(e))
        self.last = time.time()
        if live == 0:
            self.last_msg = "浏览器没开，保活暂停"
            return 0
        if gen and done == 0:
            self.last_msg = "云端出片占着浏览器，保活先让路"
        elif held:
            self.last_msg = "保活让路：已跑 %d 个账号" % done
        else:
            self.last_msg = "保活完成：%d 个账号" % done
        if done:
            self.log("☁️ 浏览器保活：%d 个账号" % done)
        return done
