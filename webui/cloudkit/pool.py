# -*- coding: utf-8 -*-
"""账号浏览器池：一个号一只调试浏览器，只给云端成片并行用。

主窗口那只（data/cloud/browser, 9333）仍是登录、保活、单条视频的共用窗口；
成片要多个号同时跑时，每个号各起一只（独立端口 + 独立 profile），
互不顶号，也互不抢 cookies。池只在成片开跑时懒建，跑完 close() 收干净。

坏号用 state="fail" 记在账号索引里：下一次成片的账号池自动跳过它，
直到人重新保存登录态（store.save 会把 state 改回 saved）。
"""
import os
import threading

from . import browser as cb
from . import gen as cg
from .store import cloud_dir

# 一只 Chrome 约几百 MB；再多也没有收益，平台那边也会限并发
MAX_PARALLEL = 4


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
    def __init__(self, root, cfg, store, log=None):
        self.root = root
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self.store = store
        self.log = log or (lambda *_: None)
        self._workers = {}
        self._lock = threading.RLock()
        self._seq = 0
        self._base_port = int(self.cfg.get("port") or 9333)

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
        """按账号懒建一只浏览器；同一个号永远复用同一只。"""
        aid = str(row.get("id") or "")
        with self._lock:
            w = self._workers.get(aid)
            if w is not None:
                return w
            self._seq += 1
            port = self._base_port + self._seq
            prof = os.path.join(cloud_dir(self.root), "browser_pool", aid)
            host = cb.BrowserHost(self.root, self.cfg, log=self.log,
                                  port=port, profile=prof)
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
        """成片收尾：把池里所有浏览器都关掉，别在桌面上留一排 Chrome。"""
        with self._lock:
            ws = list(self._workers.values())
            self._workers.clear()
            self._seq = 0
        for w in ws:
            try:
                w.host.close(force=True)
            except Exception:
                pass
