# -*- coding: utf-8 -*-
"""cloudkit —— 云端账号与浏览器宿主。

store.py   账号库：每号一份浏览器状态快照（cookies + localStorage）+ 多份备份
browser.py 共用一只调试浏览器：换号只换数据，不重启进程；保活与鉴权头派生
gen.py     H3 云端执行器：工作流加载、上传参考图、等片、下载
pool.py    成片账号池：每个号一只独立浏览器，逐镜并行、两次失败换号

浏览器进程只在真正要用时起（DrissionPage 在 browser.py 里才 import），
启动路径上不碰它——同 App() 里不 import torch 是同一条规矩。
"""
