# -*- coding: utf-8 -*-
"""ui/assemble.py —— 把 shell.html + css/ + js/ 拼成单文件 HTML

单独成模块的原因：pywebview 用 create_window(html=...) 才秒开（实测 file:// +
外链子资源首帧 8 秒以上），拼合顺序必须唯一；开发期的截图脚本也要用同一份顺序，
所以这里不 import webview / rfq_core，保持零依赖。

mock=True 时额外内联 ui/dev/mock.js：只在浏览器里预览界面用，正常启动不带。
"""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

CSS_ORDER = [
    "css/base.css",
    "css/tide.css",
    "css/plum.css",
    "css/nav.css",
    "css/pages.css",
    "css/kw.css",
    "css/win.css",
    "css/gen.css",
]

# 依赖顺序：dom → api/state → theme/nav/form/view → router → runner → pages → boot
JS_ORDER = [
    "js/core/dom.js",
    "js/core/api.js",
    "js/core/state.js",
    "js/core/theme.js",
    "js/core/nav.js",
    "js/core/form.js",
    "js/core/view.js",
    "js/core/win.js",
    "js/core/router.js",
    "js/core/runner.js",
    "js/pages/overview.js",
    "js/pages/t2i.js",
    "js/pages/gallery.js",
    "js/pages/settings.js",
    "js/pages/blank.js",
    "js/boot.js",
]

DEV_MOCK = "dev/mock.js"


def _rd(rel):
    path = os.path.normpath(os.path.join(ROOT, rel))
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def assemble(mock=False):
    html = _rd("shell.html")
    css = "\n".join(_rd(p) for p in CSS_ORDER)
    scripts = [_rd(p) for p in JS_ORDER]
    if mock:
        scripts.insert(0, _rd(DEV_MOCK))
    return (html.replace("/*__CSS__*/", css)
                .replace("/*__JS__*/", "\n".join(scripts)))

