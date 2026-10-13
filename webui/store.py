# -*- coding: utf-8 -*-
"""
store.py —— 历史库（SQLite：ROOT/data/history.db，整合包：删目录即净）
=====================================================================
每张成图一行：参数 + 收藏位。画廊的一键回填/收藏/筛选都查这里，
文件本身仍是 outputs/ 里的 PNG（库只是索引，删库不丢图）。

线程：写在生成 worker 线程、读在 js_api 主线程 —— 单连接 + 锁。
"""
import os
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS images(
  file TEXT PRIMARY KEY, name TEXT, mode TEXT,
  prompt TEXT, negative TEXT, size TEXT,
  steps INTEGER, seed INTEGER, sec REAL, ts REAL, fav INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_images_ts ON images(ts DESC);
"""


class Store:
    def __init__(self, db_path):
        d = os.path.dirname(db_path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row

    def init(self):
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    def add(self, file, *, mode, prompt, negative, size, steps, seed, sec):
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO images"
                "(file,name,mode,prompt,negative,size,steps,seed,sec,ts)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (file, os.path.basename(file), mode, prompt, negative,
                 size, steps, seed, sec, time.time()))
            self._db.commit()

    def meta_map(self, files):
        """{file: 行dict}：只回库里有的；画廊没记录的旧图照常显示、没有参数。"""
        if not files:
            return {}
        q = ",".join("?" * len(files))
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM images WHERE file IN (%s)" % q, files).fetchall()
        return {r["file"]: dict(r) for r in rows}

    def set_fav(self, file, fav):
        with self._lock:
            self._db.execute("UPDATE images SET fav=? WHERE file=?",
                             (1 if fav else 0, file))
            self._db.commit()

    def remove(self, file):
        with self._lock:
            self._db.execute("DELETE FROM images WHERE file=?", (file,))
            self._db.commit()

    def prune(self, existing_files):
        """清掉图已不存在的孤儿行（画廊清空/手删后对账）。"""
        keep = set(existing_files)
        with self._lock:
            rows = self._db.execute("SELECT file FROM images").fetchall()
            gone = [r["file"] for r in rows if r["file"] not in keep]
            for f in gone:
                self._db.execute("DELETE FROM images WHERE file=?", (f,))
            if gone:
                self._db.commit()
        return len(gone)

    def stats(self):
        with self._lock:
            n, fav = self._db.execute(
                "SELECT COUNT(*), COALESCE(SUM(fav),0) FROM images").fetchone()
        return {"count": n, "fav": fav}
