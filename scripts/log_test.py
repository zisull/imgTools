# -*- coding: utf-8 -*-
"""日志与数据目录回归：界面日志要落盘，落盘要落在自测自己的目录里。

跑法： .venv\\Scripts\\python.exe scripts\\log_test.py

验两件真出过的事：
  · App._log 只写内存 → 窗口一关，run.log 里一行现场都不剩；
  · 自测只设了 QIC_CONFIG，却把满屏 PASS 写进用户正在用的 logs/run.log，
    把测试图记进用户的 data/history.db，把用户的真账号当成测试数据读走。
"""
import atexit
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))

TMP = tempfile.mkdtemp(prefix="qic_log_test_")
os.environ["QIC_CONFIG"] = os.path.join(TMP, "config.json")
os.environ.pop("QIC_CLOUD_DIR", None)      # 这份要验的是「没单独指定时也跟着配置走」
atexit.register(shutil.rmtree, TMP, True)

RESULTS = []


def ok(name, cond, extra=""):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ((" · " + str(extra)) if extra else ""))


def read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def under_tmp(path):
    return os.path.normpath(path).startswith(os.path.normpath(TMP) + os.sep)


def main():
    import app as A
    from app import App
    from cloudkit import store as cs

    # ---------------- 目录：配置落在仓库外，logs/data/cloud 整体跟着走 ----------------
    ok("日志目录跟着配置走", under_tmp(A.LOG_DIR), A.LOG_DIR)
    ok("落盘就在配置旁边的 run.log",
       os.path.normpath(A.RUN_LOG) == os.path.normpath(
           os.path.join(A.LOG_DIR, "run.log")), A.RUN_LOG)

    a = App()
    ok("历史库开在临时目录里",
       under_tmp(A.datahome.data_dir(A.ROOT))
       and os.path.isfile(os.path.join(TMP, "data", "history.db")),
       A.datahome.data_dir(A.ROOT))
    ok("回收站跟着配置走", under_tmp(a._trash_dir), a._trash_dir)
    ok("账号库不单独指定也跟着配置走",
       os.path.normpath(cs.cloud_dir(ROOT)) == os.path.normpath(
           os.path.join(TMP, "data", "cloud")), cs.cloud_dir(ROOT))
    os.environ["QIC_CLOUD_DIR"] = os.path.join(TMP, "cloud_explicit")
    ok("显式指定 QIC_CLOUD_DIR 仍然优先",
       os.path.normpath(cs.cloud_dir(ROOT)) == os.path.normpath(
           os.environ["QIC_CLOUD_DIR"]), cs.cloud_dir(ROOT))
    os.environ.pop("QIC_CLOUD_DIR", None)

    # ---------------- 落盘：界面里那条日志同步进 run.log ----------------
    marker = "界面上的这条要落到盘上 %d" % int(time.time())
    a._log(marker)
    body = read(A.RUN_LOG)
    ok("界面日志落盘", marker in body, A.RUN_LOG)
    ok("落盘的行带时间前缀", "\n   [" in body, body[-120:])

    secret = "sk-" + "abcdefghijklmnopqrst"
    a._log("文本 API 报错：Key 是 %s" % secret)
    body = read(A.RUN_LOG)
    ok("落盘把 Key 形状打码", secret not in body and "sk-***" in body, "")

    a._log("两行的日志\n第二行")
    body = read(A.RUN_LOG)
    ok("多行日志在盘上折成一行", "两行的日志 ↵ 第二行" in body, "")
    ok("启动标记写明是自测", "· 自测" in body, body[-200:])

    # 关掉窗口之后现场还在：重开一只 App 只追加，不清空
    a2 = App()
    a2._log("第二次会话的一条")
    body = read(A.RUN_LOG)
    ok("重开会话不抹掉前一轮", "界面上的这条要落到盘上" in body
       and "第二次会话的一条" in body, "")


if __name__ == "__main__":
    main()
    passed = sum(1 for x in RESULTS if x)
    print("\n%d/%d 通过" % (passed, len(RESULTS)))
    sys.exit(0 if passed == len(RESULTS) else 1)
