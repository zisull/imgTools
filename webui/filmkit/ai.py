# -*- coding: utf-8 -*-
"""ai.py —— 文本 API：拆分镜与提示词润色

密钥只从运行时取：环境变量 DEEPSEEK_API_KEY / QIC_AI_KEY 优先，其次 config.ai.key。
本模块不写日志、不回传密钥；任何要显示的错误串都先过 _scrub（真 Key 与 sk- 形状都打码）。
接口按 OpenAI 兼容的 /chat/completions 走，默认 DeepSeek，也能填别的兼容端点。
"""
import json
import os
import re
import time

import requests

DEFAULTS = {
    "base": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "key": "",
    "temp": 0.7,
    "timeout": 120,
    "max_tokens": 8192,
}


class AiError(Exception):
    pass


def settings(cfg=None):
    s = dict(DEFAULTS)
    s.update((cfg or {}).get("ai") or {})
    key = (os.environ.get("DEEPSEEK_API_KEY")
           or os.environ.get("QIC_AI_KEY")
           or str(s.get("key") or ""))
    s["key"] = str(key).strip()
    s["base"] = str(s.get("base") or DEFAULTS["base"]).strip().rstrip("/")
    s["model"] = str(s.get("model") or DEFAULTS["model"]).strip()
    try:
        s["timeout"] = max(15, min(300, int(s.get("timeout") or 120)))
    except (TypeError, ValueError):
        s["timeout"] = 120
    try:
        s["max_tokens"] = max(64, min(8192, int(s.get("max_tokens") or 8192)))
    except (TypeError, ValueError):
        s["max_tokens"] = 8192
    try:
        s["temp"] = max(0.0, min(1.5, float(s.get("temp") if s.get("temp") is not None else 0.7)))
    except (TypeError, ValueError):
        s["temp"] = 0.7
    return s


def has_key(cfg=None):
    return bool(settings(cfg)["key"])


def _scrub(text, key=""):
    t = str(text or "")
    if key:
        t = t.replace(key, "***")
    return re.sub(r"sk-[A-Za-z0-9_-]{10,}", "sk-***", t)


def _url(base):
    b = str(base or "").rstrip("/")
    return b + "/chat/completions"


def _post(url, headers, body, timeout):
    """一次请求；429/5xx/网络错重试，401/403 直接说清楚，别拿重试拖时间。"""
    last = ""
    for i in range(3):
        try:
            r = requests.post(url, headers=headers, json=body, timeout=timeout)
        except requests.RequestException as e:
            last = "连不上文本 API：%s" % e
            time.sleep(1.5 * (i + 1))
            continue
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                raise AiError("文本 API 回的不是 JSON（HTTP 200）")
        if r.status_code in (401, 403):
            raise AiError("文本 API 不认这个 Key 或没有权限（HTTP %d）" % r.status_code)
        if r.status_code == 400 and "response_format" in (r.text or ""):
            # 有些兼容端点不认 JSON 模式：去掉再试一次，交给解析层兜底
            body = dict(body)
            body.pop("response_format", None)
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            last = "文本 API 忙（HTTP %d）" % r.status_code
            time.sleep(2.0 * (i + 1))
            continue
        raise AiError("文本 API 报错 HTTP %d：%s" % (r.status_code, str(r.text or "")[:300]))
    raise AiError(last or "文本 API 没响应")


def chat(messages, cfg=None, *, json_mode=False, temperature=None,
         max_tokens=None, timeout=None):
    s = settings(cfg)
    if not s["key"]:
        raise AiError("还没填文本 API Key：到「设置 → 文本 API」填一个（只存本机）")
    body = {
        "model": s["model"],
        "messages": messages,
        "temperature": s["temp"] if temperature is None else temperature,
        "max_tokens": s["max_tokens"] if max_tokens is None else max_tokens,
        "stream": False,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": "Bearer " + s["key"],
               "Content-Type": "application/json"}
    try:
        data = _post(_url(s["base"]), headers, body,
                     s["timeout"] if timeout is None else timeout)
    except requests.RequestException as e:
        raise AiError(_scrub("请求文本 API 失败：%s" % e, s["key"]))
    try:
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        content = msg.get("content")
    except (AttributeError, IndexError, TypeError):
        content = None
    if not isinstance(content, str) or not content.strip():
        raise AiError("文本 API 回了空内容")
    return content.strip()


# ---------------------------------------------------------------- JSON 容错
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)


def extract_json(text):
    """从模型回复里捞一个 JSON：去围栏 → 从第一个 {/[ 起做括号配对（认字符串转义）。

    只返回已闭合的那一段；模型爱在 JSON 前后写「好的，下面是…」，也爱在半路断掉，
    这两种都不能让 json.loads 直接炸到用户脸上。
    """
    raw = _FENCE.sub("", str(text or "")).strip()
    starts = [i for i in (raw.find("{"), raw.find("[")) if i >= 0]
    if not starts:
        raise AiError("模型没按 JSON 回：%s" % raw[:200])
    start = min(starts)
    stack = []
    in_str = False
    esc = False
    pairs = {"{": "}", "[": "]"}
    for i, ch in enumerate(raw[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in pairs:
            stack.append(pairs[ch])
        elif ch in "}]":
            if not stack or stack[-1] != ch:
                break
            stack.pop()
            if not stack:
                try:
                    return json.loads(raw[start:i + 1])
                except ValueError as e:
                    raise AiError("模型回的分镜不是合法 JSON：%s" % e)
    raise AiError("模型回的 JSON 没闭合：%s" % raw[:200])


# ---------------------------------------------------------------- 拆分镜
PLAN_SYSTEM = """你是短剧分镜师。把用户给的剧情拆成连贯、可拍的镜头，只输出 JSON，不要解释。
规则：
1. 必须正好 {n} 个镜头，每镜 {sec} 秒（H3 单段上限 15 秒）。
2. 每镜写一条可直接喂给视频模型的中文提示词：主体 + 动作 + 场景 + 镜头运动 + 光线 + 画面风格 + 环境声/对白语气；90~220 字。
3. 同一角色在每一镜都用固定的身份锚重复描述（年龄段、发型、服装、体态），保证跨镜不漂。
4. 对白用「」括起来，只写短句；没有对白就不写。
5. 镜头要承接：第 i 镜结尾的人物状态、位置与光线，就是第 i+1 镜的开头。
6. 所有角色一律成年人；不写未成年人，不写露骨性行为、血腥细节。
7. 输出形状：{{"title":"片名","shots":[{{"summary":"一句话剧情","prompt":"提示词"}}]}}
"""

PLAN_USER = """剧情：
{story}

补充：{extra}
画面风格：{style}
画幅：{ratio}
总时长：约 {total} 秒，正好 {n} 镜，每镜 {sec} 秒。
"""


def _clean_prompt(s):
    t = str(s or "").strip()
    t = re.sub(r"^\s*```[a-z]*\s*|\s*```\s*$", "", t, flags=re.I)
    t = re.sub(r"^\s*(?:prompt|提示词|画面描述)\s*[:：]\s*", "", t, flags=re.I)
    t = t.strip().strip('"').strip("“”").strip()
    return re.sub(r"[ \t]+", " ", t)


def plan_shots(story, total_sec, shot_sec=15, cfg=None, *, style="", ratio="9:16",
               extra="", log=None):
    story = str(story or "").strip()
    if len(story) < 4:
        raise AiError("先写一段剧情")
    try:
        total_sec = max(5, min(3600, int(total_sec or 60)))
    except (TypeError, ValueError):
        total_sec = 60
    try:
        shot_sec = int(shot_sec or 15)
    except (TypeError, ValueError):
        shot_sec = 15
    if shot_sec not in (5, 10, 15):
        shot_sec = 15
    n = max(1, min(40, int(round(total_sec / float(shot_sec)))))
    actual = n * shot_sec

    messages = [
        {"role": "system", "content": PLAN_SYSTEM.format(n=n, sec=shot_sec)},
        {"role": "user", "content": PLAN_USER.format(
            story=story[:6000], extra=extra or "无", style=style or "电影感写实",
            ratio=ratio, total=actual, n=n, sec=shot_sec)},
    ]
    title, shots = "", []
    for attempt in range(2):
        raw = chat(messages, cfg, json_mode=True,
                   temperature=0.55 if attempt == 0 else 0.35,
                   max_tokens=min(settings(cfg)["max_tokens"], max(1600, n * 320)))
        data = extract_json(raw)
        if isinstance(data, dict):
            title = str(data.get("title") or title or "").strip()
            rows = data.get("shots") or data.get("scenes") or data.get("list") or []
        else:
            rows = data
        if not isinstance(rows, list):
            rows = []
        shots = []
        for row in rows:
            if isinstance(row, str):
                prompt, summary = row, ""
            elif isinstance(row, dict):
                prompt = (row.get("prompt") or row.get("description")
                          or row.get("text") or row.get("画面") or "")
                summary = (row.get("summary") or row.get("title")
                           or row.get("scene") or row.get("剧情") or "")
            else:
                continue
            prompt = _clean_prompt(prompt)
            if not prompt:
                continue
            shots.append({"summary": str(summary or "").strip()[:80],
                          "prompt": prompt[:600], "seconds": shot_sec})
        if len(shots) >= n:
            shots = shots[:n]
            break
        if log:
            log("· 模型只拆出 %d/%d 段，再要一次" % (len(shots), n))
        messages += [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "镜头数不对：必须正好 %d 段，你给了 %d 段。"
                                        "请按同样规则重写，仍然只输出 JSON。" % (n, len(shots))},
        ]
    else:
        raise AiError("模型只拆出 %d 段，要求 %d 段：把剧情写得更具体一点，或换一档时长再试"
                      % (len(shots), n))
    for i, sh in enumerate(shots, 1):
        sh["i"] = i
    if log:
        log("· 拆镜完成：%s · %d 镜 × %d 秒（约 %d 秒）"
            % (title or "未命名", len(shots), shot_sec, actual))
    return {"title": title or "未命名短剧", "shots": shots,
            "count": len(shots), "shot_sec": shot_sec,
            "total_sec": actual, "requested_sec": total_sec}


# ---------------------------------------------------------------- 润色
POLISH_SYSTEM = {
    "image": """你是专业 AI 生图提示词工程师。把用户的描述润色成一条可直接生图的提示词。
只输出润色后的提示词本身，不要解释、不要分点、不要引号。
要求：保留用户原意、人物身份与场景，不新增人物、不改变剧情；
从专业构图角度补齐画面语言——主体位置与视线、景别与机位（特写/中景/全景）、
镜头焦段与景深、光源方向与色温、画面色彩与材质、姿态表情、背景层次。
年龄一律成年人；不写未成年人，不写露骨性行为。120~260 字，用与原文相同的语言。""",
    "video": """你是专业 AI 视频提示词工程师。把用户的描述润色成一条可直接生成 15 秒短镜头的提示词。
只输出润色后的提示词本身，不要解释、不要分点、不要引号。
要求：保留用户原意、人物身份与场景，不新增人物、不改变剧情；
补齐可拍细节——景别与机位、镜头运动（推/拉/摇/移/跟）、动作节奏、
光线与色温、环境氛围、可用环境声与对白语气。动作在 15 秒内能完成。
年龄一律成年人；不写未成年人，不写露骨性行为、血腥细节。120~260 字，用与原文相同的语言。""",
}


def polish(text, kind="image", cfg=None):
    src = str(text or "").strip()
    if len(src) < 2:
        raise AiError("先写一句要润色的描述")
    kind = "video" if str(kind) == "video" else "image"
    raw = chat([{"role": "system", "content": POLISH_SYSTEM[kind]},
                {"role": "user", "content": src[:4000]}],
               cfg, temperature=0.75, max_tokens=900)
    out = _clean_prompt(raw)
    out = re.sub(r"^(?:润色后|优化后|提示词)\s*[:：]\s*", "", out).strip()
    if len(out) < 4:
        raise AiError("模型没给出有效的润色结果")
    return out[:1200]


def test(cfg=None):
    t0 = time.time()
    s = settings(cfg)
    reply = chat([{"role": "user", "content": "只回复两个字：可用"}],
                 cfg, temperature=0, max_tokens=16, timeout=40)
    return {"ok": True, "ms": round((time.time() - t0) * 1000),
            "model": s["model"], "reply": reply[:40]}
