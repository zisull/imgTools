# -*- coding: utf-8 -*-
"""参考图编号 → 节点认的 @提及 chip。

为什么不能直接往提示词里写 `@1` 或 `<Picture 1>`：`FeiHouEasyH3RH` 的内嵌编辑器
只把 `span.h3-mention-chip` 这种 DOM 认作引用，纯文本在 serialize() 时是普通文字，
媒体照样上传，但「第几张图是谁」这层信息就丢了。结构照抄 H3yun 实机验证过的那一份
（`D:\\AI\\H3yun\\assets.py:_mention_chip_html`）。

纯函数、不碰浏览器，直接用单测钉住。
"""
import html
import re

# 只认「@1 / @图1 / [1]」三种写法；前面紧挨字母数字的不算（a@1 这种不是引用）
_REF_RE = re.compile(r"(?<![\w@])(?:@图?(\d+)|\[(\d+)\])")
MAX_REFS = 4


def normalize(text):
    """把三种写法统一成 @N，给界面提示与日志用。"""
    return _REF_RE.sub(lambda m: "@" + (m.group(1) or m.group(2)), str(text or ""))


def ref_numbers(text, count=0):
    """按出现顺序返回编号；count>0 时校验越界（越界直接报错，别白跑一段）。"""
    out = []
    for m in _REF_RE.finditer(str(text or "")):
        n = int(m.group(1) or m.group(2))
        if count and (n < 1 or n > count):
            raise ValueError("引用了第 %d 张参考图，但这次只上传了 %d 张" % (n, count))
        out.append(n)
    return out


def chip_html(n, filename, label=None):
    """一张图的 @提及 chip。字段与 H3yun 实机一致，只把可见文字换成「@图N」。"""
    n = int(n)
    fn = str(filename or "")
    e = lambda s: html.escape(str(s), quote=True)
    tag = "<Picture %d>" % n
    preview = "/view?filename=%s&type=input" % fn
    name = label or ("图%d" % n)
    return (
        '<span class="h3-mention-chip" contenteditable="false"'
        ' data-token="@Image%d" data-tag="%s" data-label="Image%d"'
        ' data-full-label="%s" data-media-type="image" data-reference-mode="index"'
        ' data-ordinal="%d" data-source-id="-%d" data-source-slot="0"'
        ' data-preview-url="%s" data-pending-reference=""'
        ' title="%s %s">'
        '<img class="h3-mention-chip-thumb" alt="" draggable="false"'
        ' src="%s" data-preview-url="%s" data-media-type="image">'
        '<span class="h3-mention-chip-label">@%s</span></span>'
        % (n, e(tag), n, e(fn), n, n, e(preview),
           e(name), e(tag), e(preview), e(preview), e(name))
    )


def picture_text(text, count):
    """把编号写成 `<Picture N>` 纯文本，返回 (文本, 引用数)。

    新形状（MiniMaxH3ReferenceToVideo）的提示词走 Text 节点，没有 contenteditable
    编辑器，也就没有 chip 这一说——节点自己就把 `<Picture N>` 当引用认
    （作者那张图的提示词通篇就是这么写的，实测线上序列化出来一模一样）。
    没写编号但给了多张图时，开头补一串 `<Picture 1> <Picture 2>…`：
    不写它模型分不清第几张图是谁。
    """
    s = str(text or "")
    count = max(0, int(count or 0))
    n = [0]

    def rep(m):
        k = int(m.group(1) or m.group(2))
        if count and (k < 1 or k > count):
            raise ValueError("引用了第 %d 张参考图，但这次只上传了 %d 张" % (k, count))
        n[0] += 1
        return "<Picture %d>" % k

    out = _REF_RE.sub(rep, s)
    if n[0] == 0 and count > 1:
        out = " ".join("<Picture %d>" % i for i in range(1, count + 1)) + " " + out
        n[0] = count
    return out, n[0]


def _by_ordinal(media):
    out = {}
    for i, m in enumerate(media or []):
        if not isinstance(m, dict) or not m.get("filename"):
            continue
        try:
            n = int(m.get("ordinal") or (i + 1))
        except (TypeError, ValueError):
            n = i + 1
        out[n] = m
    return out


def render_prompt(text, media):
    """把文案里的编号换成 chip，返回 (html 或 None, chip 数)。

    - 单图且没写编号：返回 (None, 0)，让调用方走原来的纯文本通路（已验证能出片）。
    - 多图但一个编号都没写：在开头补 `@1 @2 …`，否则模型分不清每张图对应谁。
    - 编号越界：抛 ValueError。
    """
    text = str(text or "")
    idx = _by_ordinal(media)
    if not idx:
        return None, 0
    matches = list(_REF_RE.finditer(text))
    if not matches:
        if len(idx) < 2:
            return None, 0
        chips = [chip_html(n, idx[n]["filename"]) for n in sorted(idx)]
        return "".join(chips) + " " + html.escape(text).replace("\n", "<br>"), len(chips)

    parts, pos, count = [], 0, 0
    for m in matches:
        n = int(m.group(1) or m.group(2))
        if n not in idx:
            raise ValueError("引用了第 %d 张参考图，但这次只上传了 %d 张"
                             % (n, len(idx)))
        parts.append(html.escape(text[pos:m.start()]).replace("\n", "<br>"))
        parts.append(chip_html(n, idx[n]["filename"]))
        pos, count = m.end(), count + 1
    parts.append(html.escape(text[pos:]).replace("\n", "<br>"))
    return "".join(parts), count
