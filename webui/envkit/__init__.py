# -*- coding: utf-8 -*-
"""envkit —— 环境清单、体检、安装与下载

  spec.py      清单解析、环境注册表、目录布局、把权重目录写进 ComfyUI
  check.py     体检（纯检测，可注入探针）
  install.py   装 ComfyUI / 依赖这些真正动手的动作
  download.py  权重下载（Motrix/aria2 优先，回落内置分段多线程）
"""
