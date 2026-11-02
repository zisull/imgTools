# -*- coding: utf-8 -*-
"""账号浏览器：1 号用主窗口，2 号起各用一只独立浏览器。

主窗口（9333 · data/cloud/browser）留给账号 1：登录、检查、单条视频都走它；
账号 2 起按账号顺序分到 9334、9335…，profile 在 data/cloud/browser_acct/<id>。
登录/保存/检查/出片都找账号自己那只，换号不再把所有号轮灌进同一个窗口。

成片的 CloudPool 只是调度包装：worker 借用这里的常驻浏览器，跑完 close()
只丢包装、窗口留着；关窗口由账号页的「关闭全部」或软件退出统一收。
"""
import os
import threading

from . import browser as cb
from .store import cloud_dir

# 一只 Chrome 约几百 MB；再多也没有收益，平台那边也会限并发
MAX_PARALLEL = 4


class AccountBrowsers:
    """账号 → 浏览器：第 1 个账号用主窗口，第 2 个起各起一只独立窗口。"""

    def __init__(self, root, cfg, store, main, log=None):
        self.root = root
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self.store = store
        self.main = main                     # 账号 1 用的那只（9333）
        self.log = log or (lambda *_: None)
        self._lock = threading.RLock()
        self._hosts = {}                     # aid -> BrowserHost（仅 2 号及以后）
        self._slots = {}                     # aid -> 建这只窗口时的号位

    def slot(self, aid):
        """账号排第几（1 起）；按账号库顺序，删号后后面的人顺延。"""
        aid = str(aid or "")
        for i, a in enumerate(self.store.list(), 1):
            if str(a.get("id") or "") == aid:
                return i
        return 0

    def _port(self, slot):
        return int(self.cfg.get("port") or 9333) + max(0, int(slot) - 1)

    def _profile(self, aid):
        return os.path.join(cloud_dir(self.root), "browser_acct", str(aid or ""))

    def host_for(self, aid):
        """拿这个账号自己的那只浏览器；只建对象，不提前起进程。"""
        aid = str(aid or "")
        slot = self.slot(aid)
        if slot <= 0:
            return self.main
        if slot == 1:
            with self._lock:
                stale = self._hosts.pop(aid, None)
                self._slots.pop(aid, None)
            if stale is not None:
                stale.close(force=True)      # 顺延到 1 号了，独立窗口不再需要
            return self.main
        with self._lock:
            h = self._hosts.get(aid)
            if h is not None and self._slots.get(aid) == slot:
                return h
            if h is not None:
                h.close(force=True)          # 号位变了，端口跟着换
            h = cb.BrowserHost(self.root, self.cfg, log=self.log,
                               port=self._port(slot), profile=self._profile(aid))
            self._hosts[aid] = h
            self._slots[aid] = slot
            return h

    def close(self, aid=""):
        """只关这个账号的浏览器；1 号就是主窗口。"""
        aid = str(aid or "")
        if self.slot(aid) == 1:
            self.main.close(force=True)
            return
        with self._lock:
            h = self._hosts.pop(aid, None)
            self._slots.pop(aid, None)
        if h is not None:
            h.close(force=True)

    def close_all(self):
        with self._lock:
            hosts = list(self._hosts.values())
            self._hosts.clear()
            self._slots.clear()
        for h in hosts:
            try:
                h.close(force=True)
            except Exception:
                pass
        try:
            self.main.close(force=True)
        except Exception:
            pass

    def reconcile(self):
        """删号后号位会前移：把已不在原号位的窗口收掉，别让 state 报错窗口。

        删号期间云端出片已被上层拦住，这里不会收掉正在出片的浏览器。
        """
        cur = {str(a.get("id") or ""): i for i, a in enumerate(self.store.list(), 1)}
        with self._lock:
            stale = [(aid, h) for aid, h in self._hosts.items()
                     if cur.get(aid, 0) != self._slots.get(aid)]
            for aid, _h in stale:
                self._hosts.pop(aid, None)
                self._slots.pop(aid, None)
        for _aid, h in stale:
            try:
                h.close(force=True)
            except Exception:
                pass

    def state(self):
        """给账号页：每个号分到哪只浏览器、开没开、正被谁用着。不含凭据。"""
        with self._lock:
            hosts = dict(self._hosts)
            rows = self.store.list()
            out = []
            for i, a in enumerate(rows, 1):
                h = self.main if i == 1 else hosts.get(a["id"])
                out.append({
                    "slot": i,
                    "port": h.port if h is not None else self._port(i),
                    # wait=False：出片时那只 host 的锁是长占的，探活不能跟着等
                    "on": bool(h is not None and h.alive(wait=False)),
                    "account": str(a.get("name") or ""),
                    "account_id": str(a.get("id") or ""),
                    "purpose": str(getattr(h, "purpose", "") or "") if h is not None else "",
                    "main": i == 1,
                })
            return out


class Worker:
    """池里的一格：账号 + 它自己的浏览器 + 执行器。字段由调度线程读写。"""

    def __init__(self, aid, name, host, gen):
        self.aid = aid
        self.name = name
        self.host = host
        self.gen = gen
        self.bad = False        # 两次都没出成：这一轮不再接活
        self.busy = False
        self.err = ""


class CloudPool:
    """成片调度用的一层包装；浏览器本身归 AccountBrowsers，跑完不关。"""

    def __init__(self, browsers, log=None):
        self.browsers = browsers
        self.root = browsers.root
        self.cfg = browsers.cfg
        self.store = browsers.store
        self.log = log or browsers.log
        self._workers = {}
        self._lock = threading.RLock()

    def accounts(self):
        """可出片的号：有登录快照、且没被标成 fail。

        state=error 是「上次检查出错」（浏览器被关、页面断开那一类），
        重开一次就能自愈，所以不在这里拦；只有成片里两次都没出成才标 fail。
        """
        out = []
        for a in self.store.list():
            if str(a.get("state") or "") == "fail":
                continue
            snap = self.store.load(a["id"]) or {}
            if not snap.get("cookies"):
                continue
            out.append(a)
        return out

    def worker(self, row):
        """按账号拿执行器；同一个号永远复用同一只浏览器。"""
        aid = str(row.get("id") or "")
        with self._lock:
            w = self._workers.get(aid)
            if w is not None:
                return w
            from . import gen as cg
            host = self.browsers.host_for(aid)
            gen = cg.CloudH3(self.root, self.cfg, self.store, host, log=self.log)
            w = Worker(aid, str(row.get("name") or aid), host, gen)
            self._workers[aid] = w
            return w

    def workers(self, rows):
        """按给定顺序建好；账号可以比并发多，多出来的用来接坏号的活。"""
        return [self.worker(a) for a in rows]

    def mark_fail(self, w, reason):
        """两次都没出成：账号标 fail，下一次成片/单条视频都先跳过它。"""
        text = str(reason or "")[:160]
        w.bad = True
        w.err = text
        self.store.mark(w.aid, "fail", text)
        self.log("⛔ 账号「%s」标为失败：%s" % (w.name, text[:80]))

    def close(self):
        """成片收尾：只丢这轮的执行器包装，账号浏览器继续留着。"""
        with self._lock:
            self._workers.clear()
