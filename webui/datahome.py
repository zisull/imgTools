# -*- coding: utf-8 -*-
"""可写数据目录的唯一解析点：日志、画廊库、回收站、云端账号库都从这里派生。

默认全在仓库内（<root>/logs、<root>/data）。回归脚本的固定做法是把 QIC_CONFIG
指到自己的临时文件 —— 那时光靠「每个脚本再自觉多设一个环境变量」不够：漏一项
就把满屏 PASS 写进用户正在用的 logs/run.log（真实堆栈被噪音埋掉）、把假账号写进
data/cloud、把测试图记进 data/history.db。所以配置一旦落在仓库外，这几份数据
整体跟着配置目录走，脚本只设 QIC_CONFIG 一项就都隔离了。
"""
import os


def home(root):
    """写数据的根：QIC_CONFIG 落在仓库之外时返回它所在目录，否则返回仓库根。"""
    root_abs = os.path.abspath(root)
    cfg = os.environ.get("QIC_CONFIG") or ""
    if cfg:
        d = os.path.dirname(os.path.abspath(cfg))
        if os.path.normcase(d) != os.path.normcase(root_abs):
            return d
    return root_abs


def logs_dir(root):
    return os.path.join(home(root), "logs")


def data_dir(root):
    return os.path.join(home(root), "data")
