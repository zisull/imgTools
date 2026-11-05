# -*- coding: utf-8 -*-
"""剧本成片回归：拆镜归一化 → 整批出片 → 续跑接帧 → 重出 → 真 ffmpeg 合成。

跑法： .venv\\Scripts\\python.exe scripts\\film_test.py
不碰用户配置 / 输出 / 历史库，也不跑模型：出片那一步用 ffmpeg 现造 0.5 秒的小片，
所以这里验收的是「批次调度、尾帧接续、重出作废、拼接与发布」这条链路。
"""
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))

TMP = tempfile.mkdtemp(prefix="qic_film_test_")
os.environ["QIC_CONFIG"] = os.path.join(TMP, "config.json")
# 本脚本只验本地链路：别让环境里碰巧存在的真 Key 影响 ai_state 的断言
os.environ.pop("DEEPSEEK_API_KEY", None)
os.environ.pop("QIC_AI_KEY", None)
atexit.register(shutil.rmtree, TMP, True)

from app import App                                  # noqa: E402
from filmkit import ai as fa, project as prj, stitch  # noqa: E402
from envkit import spec as sp                        # noqa: E402
from store import Store                              # noqa: E402

RESULTS = []


def ok(name, cond, extra=""):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ((" · " + str(extra)) if extra else ""))


class FakeAI:
    """只验调度，不联网：按 total/shot 给正好 N 段。"""

    def plan_shots(self, story, total, shot, cfg, **kw):
        n = max(1, min(40, int(round(float(total) / shot))))
        return {"title": "回归短剧",
                "shots": [{"i": i, "summary": "第 %d 镜" % i,
                           "prompt": "镜头 %d：少女回头看向门口" % i,
                           "seconds": shot} for i in range(1, n + 1)],
                "count": n, "shot_sec": shot, "total_sec": n * shot,
                "requested_sec": total}

    def rewrite_shot(self, story, index, count, shot, cfg, **kw):
        prev = (kw.get("prev") or {}).get("summary") or "无"
        nxt = (kw.get("nxt") or {}).get("summary") or "无"
        return {"summary": "重写第 %d 镜" % (index + 1),
                "prompt": "第 %d 镜重写｜%s｜%s" % (index + 1, prev, nxt)}

    def settings(self, cfg):
        return {"key": ""}

    def has_key(self, cfg):
        return True

    def _scrub(self, text, key=""):
        return str(text)


class FakeMgr:
    def alive(self):
        return True

    def start(self, **kw):
        pass


def wait_idle(a, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not a.st.get("running"):
            return True
        time.sleep(0.05)
    return False


def wait_cloud(a, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not (a.st.get("cloud") or {}).get("run"):
            return True
        time.sleep(0.05)
    return False


def make_clip(ff, path, color):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    r = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=%s:s=160x288:d=0.5:r=24" % color,
         "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-ar", "44100", "-ac", "2", "-shortest",
         "-movflags", "+faststart", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120)
    if r.returncode != 0:
        raise RuntimeError("造测试片段失败：%s" % (r.stderr or "")[:300])
    return path


def make_raw(ff, path, size="160x288", fps=24, audio=True, d=0.5, color="0x223344"):
    """按指定尺寸/帧率/有无音轨造一条小片——专门用来造「参数不齐」的分段。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    a = ["-f", "lavfi", "-i", "sine=frequency=440:duration=%s" % d] if audio else []
    r = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=%s:s=%s:d=%s:r=%d" % (color, size, d, fps)] + a +
        ["-c:v", "libx264", "-pix_fmt", "yuv420p"] +
        (["-c:a", "aac", "-ar", "44100", "-ac", "2"] if audio else []) +
        ["-shortest", "-movflags", "+faststart", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120)
    if r.returncode != 0:
        raise RuntimeError("造测试片段失败：%s" % (r.stderr or "")[:300])
    return path


def main():
    a = App()
    out = os.path.join(TMP, "outputs")
    os.makedirs(out, exist_ok=True)
    a.cfg["console"]["output_dir"] = out
    ff, fp = stitch.tools(ROOT)
    ok("ffmpeg 扩展环境可用", bool(ff and fp), os.path.basename(ff or ""))

    # ---------------- 清单：ffmpeg 是可选工具，不是模型路线 ----------------
    spec = sp.load_spec(ROOT)
    meta = sp.env_meta(spec, "ffmpeg")
    tool = next((t for t in spec.get("tools") or [] if t.get("key") == "ffmpeg"), {})
    ok("ffmpeg 登记为可选工具环境",
       bool(meta.get("tool")) and bool(meta.get("optional")) and bool(tool),
       meta.get("label") or "")
    ok("ffmpeg 工具路径指向 envs/ffmpeg/bin",
       "ffmpeg" in str(tool.get("dest") or "").replace("\\", "/"),
       str(tool.get("dest") or ""))

    # ---------------- 拆镜：JSON 容错 + 归一化 ----------------
    raw = '好的，下面是分镜：\n```json\n{"title":"雨夜","shots":[{"summary":"进门","prompt":"少女推门"}]}\n```'
    got = fa.extract_json(raw)
    ok("extract_json 去围栏取对象",
       isinstance(got, dict) and got.get("title") == "雨夜"
       and (got.get("shots") or [{}])[0].get("prompt") == "少女推门")
    try:
        fa.extract_json('{"shots":[{"prompt":"写到一半')
        cut = False
    except fa.AiError:
        cut = True
    ok("extract_json 半截 JSON 明确报错", cut)

    rows = prj.norm_shots([
        {"prompt": "A", "seconds": 7},
        {"prompt": ""},
        {"description": "B", "seconds": 5},
        "C",
    ], 15)
    ok("norm_shots 丢空描述并重排号",
       [x["i"] for x in rows] == [1, 2, 3]
       and [x["prompt"] for x in rows] == ["A", "B", "C"]
       and [x["seconds"] for x in rows] == [15, 5, 15],
       [x["seconds"] for x in rows])
    rows2 = prj.norm_shots([{"prompt": "A", "refs": [2, "3", 0, 99, 2]}], 15)
    ok("段级参考编号去重并夹在 1..4", rows2[0]["refs"] == [2, 3], rows2[0]["refs"])

    # ---------------- 参考图池 / 编号 / 接帧插尾帧 ----------------
    p = {"refs": ["refs/001.png", "refs/002.png", "refs/003.png"],
         "mode": "shot", "ref_mode": "same"}
    ok("project_refs 保留顺序", prj.project_refs(p) == p["refs"])
    ok("旧工程只有 first 时折成一张",
       prj.project_refs({"first": "a.png"}) == ["a.png"])
    ok("同一张：每段都 @1", prj.refs_for(p, {"i": 2}) == ["refs/001.png"])
    p["ref_mode"] = "seq"
    ok("按序：第 2 段 @2", prj.refs_for(p, {"i": 2}) == ["refs/002.png"])
    ok("按序：第 4 段绕回 @1", prj.refs_for(p, {"i": 4}) == ["refs/001.png"])
    p["ref_mode"] = "all"
    ok("全带：每段都带全池", prj.refs_for(p, {"i": 3}) == p["refs"])
    ok("段级 refs 只在池里挑且去重",
       prj.refs_for(p, {"i": 1, "refs": [3, 9, 3]}) == ["refs/003.png"])
    p["mode"], p["ref_mode"] = "chain", "same"
    ok("接帧第 1 段不塞尾帧",
       prj.refs_for(p, {"i": 1}, "prev.jpg") == ["refs/001.png"])
    ok("接帧第 2 段：尾帧排 @1",
       prj.refs_for(p, {"i": 2}, "prev.jpg") == ["prev.jpg", "refs/001.png"])
    p4 = {"refs": ["a", "b", "c", "d"], "mode": "chain", "ref_mode": "all"}
    ok("接帧不超 4 张：尾帧占掉一个号位",
       prj.refs_for(p4, {"i": 2}, "prev.jpg") == ["prev.jpg", "a", "b", "c"])

    # ---------------- film_plan ----------------
    real_ai = a._ai
    a._ai = lambda: FakeAI()
    r = a.film_plan({"story": "少女走进雨夜的旧书店，店主抬头，她认出了他。",
                     "total": 60, "shot": 15})
    ok("film_plan 按 60/15 拆 4 段",
       r.get("ok") and r.get("count") == 4 and r.get("shot_sec") == 15
       and all(x["seconds"] == 15 for x in r["shots"]), r.get("count"))
    r = a.film_plan({"story": "短", "total": 60, "shot": 15})
    ok("film_plan 剧情太短直接拒绝", not r.get("ok"))
    r = a.film_plan({"story": "少女走进雨夜的旧书店，店主抬头。",
                     "total": 700, "shot": 15})
    ok("film_plan 超 40 段直接拒绝", not r.get("ok"), r.get("msg"))

    # ---------------- 单镜重写：只换一段，前后镜当上下文 ----------------
    r = a.film_shot_ai({"index": 1, "count": 4, "seconds": 15,
                        "story": "少女走进雨夜的旧书店，店主抬头，她认出了他。",
                        "summary": "旧镜", "prompt": "旧描述",
                        "prev": {"summary": "上一镜", "prompt": "上一镜描述"},
                        "next": {"summary": "下一镜", "prompt": "下一镜描述"}})
    ok("film_shot_ai 只重写一段并带前后镜上下文",
       r.get("ok") and r.get("summary") == "重写第 2 镜"
       and "上一镜" in r.get("prompt", "") and "下一镜" in r.get("prompt", "")
       and r.get("seconds") == 15, r.get("msg"))
    r = a.film_shot_ai({"index": 9, "count": 4, "seconds": 15,
                        "story": "少女走进雨夜的旧书店，店主抬头，她认出了他。"})
    ok("film_shot_ai 段号越界夹到末段",
       r.get("ok") and r.get("summary") == "重写第 4 镜", r.get("summary"))
    r = a.film_shot_ai({"index": 0, "count": 1, "story": "短"})
    ok("film_shot_ai 剧情太短直接拒绝", not r.get("ok"))

    # ---------------- 文本 Key：只进本地配置，接口不回明文 ----------------
    a._ai = real_ai
    secret = "sk-regress000000000000000000000000"
    a.ai_set({"key": secret})
    st = a.ai_state()
    ok("ai_set 后状态显示已配置", st.get("has_key") and st.get("saved"))
    ok("ai_state 不回传明文 Key", secret not in json.dumps(st, ensure_ascii=False))
    ok("_cfg_public 剥离 Key",
       secret not in json.dumps(a._cfg_public(), ensure_ascii=False))
    a.ai_key_clear()
    ok("ai_key_clear 后回到未配置", not a.ai_state().get("has_key"))

    # ---------------- 整批出片：假模型 + 真 ffmpeg 小片 ----------------
    a._ai = lambda: FakeAI()
    a._ensure_engine = lambda eng: None
    a._get_moss = lambda: FakeMgr()
    made = []

    def fake_one(d, proj, sh, first):
        p = prj.abs_path(d, prj.shot_file(sh["i"]))
        make_clip(ff, p, ["0x334455", "0x664433", "0x445566"][(sh["i"] - 1) % 3])
        made.append((sh["i"], first))
        return p

    a._film_one = fake_one
    _pre = a._film_precheck
    a._film_precheck = lambda f, count, base_dir="": {
        "err": "", "exec": "local", "width": 160, "height": 288,
        "first": "", "acct": "", "acct_name": "", "wf": "", "count": count,
        "refs": [], "ref_mode": "same", "acct_mode": "single", "note": "",
        "mode": "chain" if str(f.get("mode")) == "chain" else "shot"}

    r = a.film_start({"shots": [{"prompt": "p%d" % i} for i in range(41)],
                      "story": "少女走进雨夜的旧书店，店主抬头，她认出了他。",
                      "total": 600, "shot": 15, "exec": "local"})
    ok("film_start 超 40 段直接拒绝", not r.get("ok"), r.get("msg"))

    r = a.film_start({"story": "少女走进雨夜的旧书店，店主抬头，她认出了他。",
                      "total": 45, "shot": 15, "exec": "local", "mode": "chain",
                      "style": "电影感写实"})
    ok("film_start 起得来", r.get("ok") and r.get("shots") == 3, r.get("msg"))
    ok("整批跑完并释放任务位", wait_idle(a, 90))
    fs = a.st.get("film") or {}
    ok("三段都完成且成片合成",
       fs.get("state") == "done" and fs.get("done") == 3
       and fs.get("film") and os.path.isfile(fs.get("film")),
       "%s / %s" % (fs.get("state"), fs.get("film")))
    ok("成片时长约等于 1.5 秒",
       abs(stitch.duration(ROOT, fs.get("film") or "") - 1.5) < 0.4,
       stitch.duration(ROOT, fs.get("film") or ""))
    d = a._film_dir
    proj = prj.load(d)
    fr1 = prj.abs_path(d, proj["shots"][0].get("frame") or "")
    ok("每段都抽了尾帧", os.path.isfile(fr1), fr1)
    ok("接帧：第 2 段拿第 1 段尾帧当参考",
       len(made) == 3 and made[0][1] == [] and made[1][1] == [fr1]
       and made[2][1] == [prj.abs_path(d, proj["shots"][1].get("frame") or "")],
       made)
    ok("成片进画廊根目录并记账",
       any(x.get("film") for x in (a.film_list().get("items") or []))
       and os.path.dirname(fs.get("film")) == out)
    items = a.film_list().get("items") or []
    ok("film_list 区分「当前」与「正在跑」",
       items and items[0].get("current") and not items[0].get("running"))

    # ---------------- 续跑：已完成的段跳过，接帧从上一段尾帧继续 ----------------
    proj = prj.load(d)
    proj["shots"][1]["state"] = "wait"
    proj["shots"][1]["file"] = ""
    proj["shots"][1]["frame"] = ""
    proj["film"] = ""
    prj.save(d, proj)
    made.clear()
    r = a.film_resume(d)
    ok("film_resume 接得上", r.get("ok"), r.get("msg"))
    ok("续跑跑完并释放任务位", wait_idle(a, 60))
    proj = prj.load(d)
    fr1b = prj.abs_path(d, proj["shots"][0].get("frame") or "")
    ok("续跑只重出第 2 段", [x[0] for x in made] == [2], made)
    ok("续跑接帧不退回工程首帧",
       made and made[0][1] == [fr1b]
       and made[0][1] != [prj.abs_path(d, proj.get("first") or "")],
       made)

    # ---------------- 重出：逐镜只作废目标段，接帧连带下游 ----------------
    proj = prj.load(d)
    proj["mode"] = "shot"
    proj["film"] = "old.mp4"
    prj.save(d, proj)
    files_before = [prj.abs_path(d, x.get("file") or "") for x in proj["shots"]]
    launched = []

    def fake_launch(dd, pp, only=None, why=""):
        launched.append((dd, set(only or ()), str(why)))
        return {"ok": True, "exec": "cloud"}

    a._film_launch = fake_launch
    r = a.film_redo(2, False)
    proj2 = prj.load(d)
    ok("逐镜重出只重置第 2 段",
       r.get("ok") and r.get("count") == 1
       and proj2["shots"][0]["state"] == "done"
       and proj2["shots"][1]["state"] == "wait"
       and proj2["shots"][1]["file"] == ""
       and os.path.isfile(files_before[0])
       and not os.path.isfile(files_before[1])
       and proj2.get("film") == "", r)
    ok("逐镜重出只跑目标段，不把整部重跑",
       launched and launched[-1][0] == d and launched[-1][1] == {2},
       launched)

    proj = prj.load(d)
    proj["mode"] = "chain"
    prj.save(d, proj)
    files_before = [prj.abs_path(d, x.get("file") or "") for x in proj["shots"]]
    r = a.film_redo(2, True)
    proj3 = prj.load(d)
    ok("接帧重出连带作废下游并保留第 1 段",
       r.get("ok") and r.get("count") == 2
       and proj3["shots"][0]["state"] == "done"
       and os.path.isfile(files_before[0])
       and all(x["state"] == "wait" and x["file"] == ""
               for x in proj3["shots"][1:]), r)
    ok("接帧重出只跑作废的那几段（第 2、3 段）",
       launched[-1][1] == {2, 3}, launched)

    # ---------------- 一键重出失败段：只补没出成的，成功段不碰 ----------------
    proj = prj.load(d)
    proj["mode"] = "shot"
    p1 = prj.abs_path(d, proj["shots"][0]["file"])
    p3 = prj.abs_path(d, prj.shot_file(3))
    os.makedirs(os.path.dirname(p3), exist_ok=True)
    shutil.copyfile(p1, p3)
    proj["shots"][0].update(state="done", err="")
    proj["shots"][1].update(state="fail", file="", frame="", err="平台判失败")
    proj["shots"][2].update(state="done", file=prj.shot_file(3), sec=1.0, err="")
    prj.save(d, proj)
    launched.clear()
    r = a.film_redo_failed()
    proj6 = prj.load(d)
    ok("一键重出：逐镜只补失败那段",
       r.get("ok") and r.get("count") == 1 and launched[-1][1] == {2}
       and proj6["shots"][0]["state"] == "done" and os.path.isfile(p1)
       and proj6["shots"][1]["state"] == "wait"
       and proj6["shots"][2]["state"] == "done" and os.path.isfile(p3), (r, launched))

    proj = prj.load(d)
    proj["mode"] = "chain"
    proj["shots"][2].update(state="done", file=prj.shot_file(3))
    prj.save(d, proj)
    if not os.path.isfile(p3):
        shutil.copyfile(p1, p3)
    launched.clear()
    r = a.film_redo_failed()
    proj7 = prj.load(d)
    ok("一键重出：接帧从最早失败段连带下游",
       r.get("ok") and r.get("count") == 2 and launched[-1][1] == {2, 3}
       and proj7["shots"][0]["state"] == "done"
       and not os.path.isfile(p3), (r, launched))

    proj = prj.load(d)
    for sh in proj["shots"]:
        f = prj.abs_path(d, prj.shot_file(sh["i"]))
        os.makedirs(os.path.dirname(f), exist_ok=True)
        if os.path.abspath(f) != os.path.abspath(p1):
            shutil.copyfile(p1, f)
        sh.update(state="done", file=prj.shot_file(sh["i"]), frame="", err="")
    prj.save(d, proj)
    r = a.film_redo_failed()
    ok("全都在时一键重出不起跑", not r.get("ok") and "全部都在" in str(r.get("msg")), r)

    # ---------------- 云端多号：失败重启一次、两次换号、无号才标失败 ----------------
    class FakeHost:
        def __init__(self):
            self.restarts = 0

        def restart(self):
            self.restarts += 1

    class FakeWorker:
        def __init__(self, aid, name):
            self.aid, self.name = aid, name
            self.host = FakeHost()
            self.bad = self.busy = False

    class FakePool:
        def __init__(self, names):
            self.rows = [{"id": k, "name": v} for k, v in names]
            self.map = {k: FakeWorker(k, v) for k, v in names}
            self.marked, self.closed = [], 0

        def accounts(self):
            return list(self.rows)

        def workers(self, rows):
            return [self.map[x["id"]] for x in rows]

        def mark_fail(self, w, reason):
            w.bad = True
            self.marked.append((w.aid, str(reason)))

        def close(self):
            self.closed += 1

    a._film_precheck = lambda f, count, base_dir="": {
        "err": "", "exec": "cloud", "width": 160, "height": 288,
        "first": "", "acct": "", "acct_name": "自动分配", "wf": "", "count": count,
        "refs": [], "ref_mode": "same",
        "acct_mode": "multi" if str(f.get("acct_mode")) == "multi" else "single",
        "note": "", "mode": "chain" if str(f.get("mode")) == "chain" else "shot"}

    lock = threading.Lock()
    calls, firsts = {}, {}
    fail_ids, fatal_ids, slow_ids = set(), set(), set()

    def cloud_one(d, proj, sh, first, worker=None):
        with lock:
            key = (worker.aid, sh["i"])
            calls[key] = calls.get(key, 0) + 1
            firsts[key] = first
        if worker.aid in fatal_ids:
            raise RuntimeError("云端前端没能加载这份工作流（测试）")
        if worker.aid in fail_ids:
            raise RuntimeError("平台判失败：测试")
        if worker.aid in slow_ids:
            time.sleep(0.08)       # 让坏号先领到活，验证「两次失败再换号」
        p = prj.abs_path(d, prj.shot_file(sh["i"]))
        make_clip(ff, p, "0x778899")
        return p

    a._film_one = cloud_one

    def cloud_start(pool, n, mode="shot", acct_mode="single"):
        calls.clear()
        firsts.clear()
        a._filmpool = pool
        return a.film_start({
            "shots": [{"prompt": "云端第 %d 段" % i} for i in range(1, n + 1)],
            "story": "少女走进雨夜的旧书店，店主抬头，她认出了他。",
            "total": n * 15, "shot": 15, "exec": "cloud", "mode": mode,
            "acct_mode": acct_mode})

    fail_ids.clear()
    fail_ids.add("A")
    fatal_ids.clear()
    slow_ids.clear()
    slow_ids.add("B")
    pool = FakePool([("A", "A号"), ("B", "B号")])
    r = cloud_start(pool, 3, acct_mode="multi")
    ok("云端逐镜：起得来", r.get("ok"), r.get("msg"))
    ok("云端逐镜：跑完并合成", wait_cloud(a, 90))
    fs = a.st.get("film") or {}
    proj = prj.load(a._film_dir)
    a_calls = [v for (aid, _), v in calls.items() if aid == "A"]
    ok("坏号两次失败后转给别的号，三段都出完",
       fs.get("state") == "done" and fs.get("done") == 3
       and bool(fs.get("film")) and os.path.isfile(fs["film"])
       and all(x.get("state") == "done" and x.get("acct_name") == "B号"
               for x in proj["shots"]), fs.get("status"))
    ok("A 号每次都是试满两次、重启一次后才换号",
       a_calls and all(x == 2 for x in a_calls)
       and pool.map["A"].host.restarts == len(a_calls)
       and pool.map["A"].bad and pool.marked, (a_calls, pool.map["A"].host.restarts))
    ok("并行数按可用号算，跑完把池收干净",
       (+fs.get("parallel") or 0) == 2 and pool.closed == 1,
       (fs.get("parallel"), pool.closed))

    # 多号逐镜：每段不带尾帧，两个号同时领活
    fail_ids.clear()
    slow_ids.clear()
    pool = FakePool([("A", "A号"), ("B", "B号")])
    r = cloud_start(pool, 4, acct_mode="multi")
    ok("多号逐镜：起得来", r.get("ok") and r.get("exec") == "cloud", r.get("msg"))
    ok("多号逐镜：跑完", wait_cloud(a, 90))
    fs = a.st.get("film") or {}
    proj = prj.load(a._film_dir)
    used = set(aid for (aid, _i) in calls)
    ok("多号逐镜：两个号都领到活、四段全成",
       fs.get("state") == "done" and fs.get("done") == 4
       and fs.get("parallel") == 2 and used == {"A", "B"}
       and all(x.get("state") == "done" for x in proj["shots"]),
       (fs.get("parallel"), sorted(used)))
    ok("多号逐镜：每段都不等尾帧（参考里没有上一段画面）",
       all(v == [] for v in firsts.values()), firsts)

    # 只有一个号且一直失败：不无限转，老实标失败
    fail_ids.clear()
    fail_ids.add("A")
    slow_ids.clear()
    pool = FakePool([("A", "A号")])
    r = cloud_start(pool, 2)
    ok("云端单号：起得来", r.get("ok"), r.get("msg"))
    ok("云端单号：跑完", wait_cloud(a, 60))
    fs = a.st.get("film") or {}
    proj = prj.load(a._film_dir)
    ok("没有别的号可换：两段都标失败、不合成",
       fs.get("state") == "failed" and fs.get("done") == 0
       and fs.get("missing") == 2 and not fs.get("film")
       and all(x.get("state") == "fail" for x in proj["shots"]),
       "%s / %s" % (fs.get("state"), fs.get("missing")))
    ok("单号失败也标了账号", pool.marked and pool.map["A"].bad)

    # 工作流加载不上：换号也没用，整批暂停而不是把号标坏
    fail_ids.clear()
    fatal_ids.clear()
    fatal_ids.add("A")
    pool = FakePool([("A", "A号")])
    r = cloud_start(pool, 2)
    ok("云端致命错：起得来", r.get("ok"), r.get("msg"))
    ok("云端致命错：跑完", wait_cloud(a, 60))
    fs = a.st.get("film") or {}
    ok("工作流致命错整批暂停，不标坏号",
       fs.get("state") == "paused" and "工作流" in str(fs.get("msg") or "")
       and not pool.marked, (fs.get("state"), fs.get("msg")))

    # 接帧：串行换号，第二段仍接第一段尾帧
    fail_ids.clear()
    fatal_ids.clear()
    fail_ids.add("A")
    pool = FakePool([("A", "A号"), ("B", "B号")])
    r = cloud_start(pool, 2, mode="chain")
    ok("云端接帧：起得来", r.get("ok"), r.get("msg"))
    ok("云端接帧：跑完", wait_cloud(a, 90))
    fs = a.st.get("film") or {}
    proj = prj.load(a._film_dir)
    fr1 = prj.abs_path(a._film_dir, proj["shots"][0].get("frame") or "")
    ok("接帧换号后尾帧仍接得上",
       fs.get("state") == "done" and fs.get("done") == 2
       and all(x.get("acct_name") == "B号" for x in proj["shots"])
       and firsts.get(("B", 2)) == [fr1], (firsts.get(("B", 2)), fr1))

    # 单段重出：只提交目标段，并先回到这段原来的账号浏览器
    fail_ids.clear()
    fatal_ids.clear()
    slow_ids.clear()
    pool = FakePool([("A", "A号"), ("B", "B号")])
    r = cloud_start(pool, 3, acct_mode="multi")
    ok("单段重出：底片先备好", r.get("ok") and wait_cloud(a, 90), r.get("msg"))
    d = a._film_dir
    proj = prj.load(d)

    def drop_shot(idx, aid):
        sh = proj["shots"][idx - 1]
        p = prj.abs_path(d, sh.get("file") or "")
        if p and os.path.isfile(p):
            os.remove(p)
        sh["file"] = ""
        sh["frame"] = ""
        sh["state"] = "wait"
        sh["acct_id"] = aid
        proj["redo"] = {"shots": [idx], "acct": aid}
        prj.save(d, proj)
        calls.clear()
        firsts.clear()
        return sh

    drop_shot(2, "B")
    a._filmpool = pool            # 直接调云端调度，不经过 film_start
    a._film_cloud_run(d, proj, {}, time.time(), only={2})
    ok("单段重出只提交目标段、只用它原来的号",
       set(k[0] for k in calls) == {"B"} and all(k[1] == 2 for k in calls),
       sorted(calls))
    ok("单段重出没碰别的段",
       proj["shots"][0]["state"] == "done" and proj["shots"][2]["state"] == "done",
       [x["state"] for x in proj["shots"]])

    # 原号两次不出成：只重启这一只浏览器，之后才换号；新号的浏览器没被动过
    pool = FakePool([("A", "A号"), ("B", "B号")])
    a._filmpool = pool
    fail_ids.clear()
    fail_ids.add("B")
    drop_shot(2, "B")
    a._film_cloud_run(d, proj, {}, time.time(), only={2})
    ok("单段重出失败先重启原号那只，二次失败才换号",
       pool.map["B"].host.restarts == 1 and pool.map["A"].host.restarts == 0
       and ("A", 2) in calls and all(k[1] == 2 for k in calls),
       (sorted(calls), pool.map["B"].host.restarts, pool.map["A"].host.restarts))

    # ---------------- 段快照：任务号当场落盘，尝试历史留在工程里 ----------------
    del a.__dict__["_film_one"]        # 还原真的 _film_one：这一节验的就是它和执行器的接口
    d3 = prj.new_dir(out)
    prj.save(d3, {"title": "快照", "exec": "cloud", "mode": "shot",
                  "width": 160, "height": 288,
                  "shots": [{"i": 1, "seconds": 15, "prompt": "少女推开书店的门",
                             "state": "wait"}]})
    proj3 = prj.load(d3)
    sh1 = proj3["shots"][0]
    seen_tid, mid_disk = [], []

    class FakeGen:
        """假执行器：只验两件事——号什么时候落盘、下一轮带不带得上。"""
        last_task_id = ""

        def run(self, p, on_progress=None, should_stop=None, on_task=None):
            seen_tid.append(p.get("taskid"))
            on_task("900001")            # 提交后在任务列表上认领到号
            mid_disk.append(prj.load(d3)["shots"][0].get("taskid"))
            self.last_task_id = "900002"  # 真正出片的那条任务，以执行器当场报的为准
            return make_clip(ff, os.path.join(TMP, "snap%03d.mp4" % len(seen_tid)),
                             "0x223344")

    wk = FakeWorker("A", "A号")
    wk.gen = FakeGen()
    a._film_one(d3, proj3, sh1, [], worker=wk)
    ok("认到任务号的那一刻就落盘，不等出片",
       mid_disk == ["900001"] and sh1.get("taskid") == "900002"
       and prj.load(d3)["shots"][0].get("taskid") == "900002", (mid_disk, sh1.get("taskid")))
    a._film_one(d3, proj3, sh1, [], worker=wk)
    ok("下一轮提交带上上一轮的号", seen_tid == ["", "900002"], seen_tid)
    ok("这一段实际按什么参数出的记在段上",
       (sh1.get("made") or {}).get("exec") == "cloud" and sh1["made"].get("w") == 160
       and sh1["made"].get("h") == 288 and sh1["made"].get("bytes") > 0, sh1.get("made"))

    for k in range(10):
        a._film_try(d3, proj3, sh1, wk, k % 3 == 0, sec=1.5,
                    err="" if k % 3 == 0 else "平台判失败：测试")
    tr = prj.load(d3)["shots"][0].get("tries") or []
    ok("尝试历史落进工程、只留最近 %d 条" % App.TRIES_KEEP,
       len(tr) == App.TRIES_KEEP and tr[-1]["acct"] == "A号"
       and tr[-1]["taskid"] == "900002" and tr[-1]["ok"] is True
       and any((not x["ok"]) and "平台判失败" in x["err"] for x in tr), (len(tr), tr[-1]))
    rows = a._film_shots(proj3, d3)
    ok("轮询快照只给条数，不把整叠尝试记录端给界面",
       rows and "tries" not in rows[0] and rows[0].get("tries_n") == App.TRIES_KEEP,
       sorted(k for k in (rows[0] or {}) if k.startswith("tries")))

    sh1["state"] = "fail"
    prj.save(d3, proj3)
    resumed = []

    def spy_launch(dd, pp, only=None, why=""):
        resumed.append((prj.abs_path(dd, ""), pp, str(why)))
        return {"ok": True, "exec": "cloud"}

    a._film_launch = spy_launch
    r = a.film_resume(d3)
    ok("续跑保留任务号，并在提示里说明有几段先问平台",
       r.get("ok") and resumed
       and resumed[-1][1]["shots"][0].get("taskid") == "900002"
       and "先问平台" in resumed[-1][2], resumed[-1][2] if resumed else r)
    a._film_launch = type(a)._film_launch.__get__(a)

    # ---------------- 收片：带号的那一段先问平台，不重交 ----------------
    got_tid = []

    class HarvestGen(FakeGen):
        """照着真执行器的收片分支写：认到片子也要把号交回去，只是不提交。"""
        def run(self, p, on_progress=None, should_stop=None, on_task=None):
            seen_tid.append(p.get("taskid"))
            if p.get("taskid"):
                got_tid.append(p.get("taskid"))
                on_task(p["taskid"])
                self.last_task_id = p["taskid"]
                return make_clip(ff, os.path.join(TMP, "take%03d.mp4" % len(seen_tid)),
                                 "0x556677")   # 平台上早跑完了：直接取回，没提交
            return FakeGen.run(self, p, on_progress, should_stop, on_task)

    wk2 = FakeWorker("B", "B号")
    wk2.gen = HarvestGen()
    sh1["taskid"] = "700111"
    path = a._film_one(d3, proj3, sh1, [], worker=wk2)
    ok("续跑带号那一趟直接收片，不再提交一次",
       got_tid == ["700111"] and os.path.isfile(path) and os.path.getsize(path) > 0,
       (got_tid, path))
    ok("收来的片子仍记着自己的任务号", sh1.get("taskid") == "700111", sh1.get("taskid"))

    from cloudkit import gen as cg

    class HarvestProbe(cg.CloudH3):
        """不接浏览器：把「列表上查到什么」换成一张假表，验收片的判断表。"""
        def __init__(self, hit, url, fail_confirm=0.0):
            self.hit, self.url = hit, url
            self.settle, self.timeout, self.poll_min = 0.05, 1, 0.01
            self.fail_confirm = fail_confirm
            self.logs = []

        def log(self, m):
            self.logs.append(str(m))

        def task_hit(self, tab, tid):
            return self.hit or {}

        def task_media(self, tab, tid):
            return self.url or ""

    def harvest(hit, url="", stop=None, fail_confirm=0.0):
        return HarvestProbe(hit, url, fail_confirm)._harvest(None, "123", None, stop)

    r = harvest({"s": "已完成"}, "http://x/a.mp4")
    ok("收片：平台说跑完 + 卡片有地址 → 直接收，不重交",
       r and r[0] == "http://x/a.mp4" and r[1].endswith("123.mp4"), r)
    ok("收片：任务列表里查不到这个号 → 交回正常流程重交",
       harvest({}) is None)
    ok("收片：平台判了失败 → 交回正常流程重交",
       harvest({"s": "失败", "d": "额度不足"}) is None)
    ok("收片：说跑完却没给地址 → 不收，交回重交",
       harvest({"s": "已完成"}, "") is None)
    try:
        harvest({"s": "生成中"}, "")
        busy = "没抛异常"
    except cg.CloudError as e:
        busy = str(e)
    ok("收片：还在跑就接着等，等满也不当失败", "还在跑" in busy, busy)
    try:
        harvest({"s": "已完成"}, "http://x/a.mp4", stop=lambda: True)
        stopped = "没抛异常"
    except cg.CloudError as e:
        stopped = str(e)
    ok("收片：中途点停止立刻收尾", "已停止" in stopped, stopped)
    ok("收片：失败也要连续读到才收手（等满 fail_confirm 才交回重交）",
       harvest({"s": "失败", "d": "安审失败 重试"}, fail_confirm=0.2) is None)

    class SeqProbe(HarvestProbe):
        """列表上第一次读到失败、下一次就正常了——页面刷新会瞬时报错，不该就此重交。"""
        def __init__(self, hits, url=""):
            HarvestProbe.__init__(self, hits[0], url, fail_confirm=0.3)
            self.seq, self.i = hits, 0

        def task_hit(self, tab, tid):
            h = self.seq[0] if self.i == 0 else self.seq[-1]
            self.i += 1
            return h

    r = SeqProbe([{"s": "失败"}, {"s": "已完成"}], "http://x/b.mp4")._harvest(None, "123", None, None)
    ok("收片：只读到一次失败不收手，随后跑完了照样收片",
       r and r[0] == "http://x/b.mp4", r)
    ok("收片：空任务号不去问平台（_JS_TASK_MEDIA 先拒 bad_id）",
       "bad_id" in cg._JS_TASK_MEDIA and "no_card" in cg._JS_TASK_MEDIA
       and cg._task_media_rank(["", "http://x/p.jpg"]) == "",
       cg._task_media_rank(["", "http://x/p.jpg"]))
    ok("收片：挑地址先认扩展名，图片一律排掉",
       cg._task_media_rank(["http://x/p.jpg", "http://x/a.mp4"]) == "http://x/a.mp4"
       and cg._task_media_rank(["http://x/p.jpg"]) == ""
       and cg._task_media_rank(["http://x/video?id=9"]) == "http://x/video?id=9",
       cg._task_media_rank(["http://x/p.jpg", "http://x/a.mp4"]))

    # ---------------- film_state / 快照 ----------------
    a._film_launch = type(a)._film_launch.__get__(a)   # 还原，给后面真跑用
    a._ai = real_ai
    st = a.film_state()
    ok("film_state 带 ffmpeg 与 Key 状态",
       st.get("ok") and st.get("ffmpeg") is True and st.get("ai_key") is False, st)
    snap = a._snap()
    ok("快照含成片三件套",
       "film" in snap and "ffmpeg" in snap and "ai_key" in snap)

    # ---------------- 最近工程那行的 ×：只搬不删，范围外的目录一律不动 ----------------
    outside = os.path.join(TMP, "outside")
    os.makedirs(outside, exist_ok=True)
    r = a.film_delete(outside)
    ok("× 不碰成片目录以外的目录", not r.get("ok") and os.path.isdir(outside), r.get("msg"))
    ok("× 空路径不误删", not a.film_delete("").get("ok"))
    keep_running = a._film_running
    a._film_running = lambda _d: True
    try:
        r = a.film_delete(d)
        ok("× 正在跑的工程拦下来", not r.get("ok") and "先停止" in str(r.get("msg")), r.get("msg"))
    finally:
        a._film_running = keep_running
    ok("拦下来之后工程还在", os.path.isdir(d))
    r = a.film_delete(d)
    ok("× 删工程：整个目录搬进回收", r.get("ok") and not os.path.isdir(d), r.get("msg"))
    ok("删掉的工程不再出现在清单里",
       d not in [x.get("dir") for x in (a.film_list().get("items") or [])])
    ok("删的是当前那个就把指针清掉", a._film_dir != d, a._film_dir)

    # ---------------- 真拼一条：参数不一致要停下 ----------------
    d2 = prj.new_dir(out)
    p1 = make_clip(ff, os.path.join(d2, "shots", "001.mp4"), "0x112233")
    p2 = make_clip(ff, os.path.join(d2, "shots", "002.mp4"), "0x332211")
    ok("ffprobe 能读出 0.5 秒", abs(stitch.duration(ROOT, p1) - 0.5) < 0.2,
       stitch.duration(ROOT, p1))
    frame = stitch.last_frame(ROOT, p1, os.path.join(d2, "frames", "001.jpg"))
    ok("抽尾帧出图", bool(frame) and os.path.getsize(frame) > 0 if frame else False)
    try:
        stitch.concat(ROOT, [p1, p2], os.path.join(out, "_never.mp4"), log=None)
        bad_ok = True
    except stitch.StitchError:
        bad_ok = False
    # 上面两条同参数，本来就能拼；这条只验顺序：能拼说明校验没误杀
    ok("同参数分段可以直接拼", bad_ok)
    try:
        os.remove(os.path.join(out, "_never.mp4"))
    except OSError:
        pass

    # ---------------- 体检 + 逐段归一化：参数不齐不再整批拒拼 ----------------
    d5 = prj.new_dir(out)
    nm = os.path.join(d5, "norm")
    q1 = make_raw(ff, os.path.join(d5, "shots", "001.mp4"), size="160x288", fps=24)
    q2 = make_raw(ff, os.path.join(d5, "shots", "002.mp4"), size="144x176", fps=30,
                  color="0x992233")
    q3 = make_raw(ff, os.path.join(d5, "shots", "003.mp4"), size="160x288", fps=24,
                  audio=False, color="0x229933")
    rows, tw, th, tfps, need = stitch.preflight(ROOT, [q1, q2, q3])
    ok("体检：读得出每条的尺寸/帧率/有无音轨",
       [r["w"] for r in rows] == [160, 144, 160] and [r["fps"] for r in rows][:2] == [24.0, 30.0]
       and [r["audio"] for r in rows] == [True, True, False] and need, 
       [(r["w"], r["h"], r["fps"], r["audio"]) for r in rows])
    ok("定档：谁人多听谁的，不拿一段特例定调整部",
       (tw, th, tfps) == (160, 288, 24.0), (tw, th, tfps))
    fin5 = os.path.join(d5, "mix.mp4")
    r5 = stitch.merge(ROOT, [q1, q2, q3], fin5, work_dir=nm)
    chk5 = stitch.inspect(ROOT, fin5)
    ok("参数不齐也能拼：重编码到同一画幅，没音轨那段补了静音",
       r5.get("copy") is False and chk5["w"] == 160 and chk5["h"] == 288
       and chk5["audio"] and abs(chk5["dur"] - 1.5) < 0.3, (r5.get("size"), chk5))
    ok("归一化的中间片落在给定的工作目录",
       os.path.isdir(nm) and len([x for x in os.listdir(nm) if x.endswith(".mp4")]) == 3,
       sorted(os.listdir(nm)) if os.path.isdir(nm) else nm)
    mtimes = {x: os.path.getmtime(os.path.join(nm, x)) for x in os.listdir(nm)}
    fin6 = os.path.join(d5, "fade.mp4")
    r6 = stitch.merge(ROOT, [q1, q2, q3], fin6, fade=0.2, work_dir=nm)
    ok("转场总长按实测时长交叠算，不照抄标称",
       r6.get("copy") is False and abs(r6["fade"] - 0.2) < 0.01
       and abs(stitch.duration(ROOT, fin6) - 1.1) < 0.25,
       (r6["fade"], r6["duration"]))
    ok("归一化有缓存：源片没变就一次 ffmpeg 也不重跑",
       all(os.path.getmtime(os.path.join(nm, k)) == v for k, v in mtimes.items()))
    fin7 = os.path.join(d5, "same.mp4")
    r7 = stitch.merge(ROOT, [q1, q1], fin7, work_dir=os.path.join(d5, "unused"))
    ok("参数一致又不要转场：仍走不重编码的快路径",
       r7.get("copy") is True and not os.path.isdir(os.path.join(d5, "unused")), r7)
    zero = os.path.join(d5, "shots", "000.mp4")
    open(zero, "wb").close()
    try:
        stitch.merge(ROOT, [q1, zero], os.path.join(d5, "no.mp4"), work_dir=nm)
        msg0 = "没拦住"
    except stitch.StitchError as e:
        msg0 = str(e)
    ok("0 字节的分段在体检这一关就拦下", "0 字节" in msg0, msg0)

    # ---------------- 合成失败/结果不对：不留半截冒充成片 ----------------
    fin8 = os.path.join(d5, "badfade.mp4")
    stitch.merge(ROOT, [q1, q2], fin8, fade=0.2, work_dir=nm)   # 先把归一化缓存落好
    real_run = stitch._run
    p_bad = make_raw(ff, os.path.join(d5, "wrong.mp4"), size="64x64")

    def fake_run(how):
        def go(argv, timeout=600):
            if not any("xfade" in str(x) for x in argv):
                return real_run(argv, timeout=timeout)
            if how == "crash":
                with open(str(argv[-1]), "wb") as f:
                    f.write(b"half-written")      # 半截文件：这种绝不能留下
                return type("R", (), {"returncode": 1, "stdout": "",
                                      "stderr": "测试：滤镜链断了"})()
            shutil.copyfile(p_bad, str(argv[-1]))
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        return go

    for how, word in (("bad", "画幅"), ("crash", "转场合成失败")):
        fin9 = os.path.join(d5, "bad_%s.mp4" % how)
        stitch._run = fake_run(how)
        try:
            stitch.merge(ROOT, [q1, q2], fin9, fade=0.2, work_dir=nm)
            msg9 = "没拦住"
        except stitch.StitchError as e:
            msg9 = str(e)
        finally:
            stitch._run = real_run
        ok("重编码那步：%s不对就当没成" % word, word in msg9, msg9)
        ok("%s那次没留下成片，也没留下半截" % word,
           not os.path.exists(fin9) and not os.path.exists(fin9 + ".part.mp4"), fin9)

    # ---------------- 成片走 app 那一关：中间片只落工程的 norm/ ----------------
    d6 = prj.new_dir(out)
    make_raw(ff, os.path.join(d6, "shots", "001.mp4"), size="160x288", fps=24)
    make_raw(ff, os.path.join(d6, "shots", "002.mp4"), size="96x240", fps=30, audio=False)
    proj6 = {"title": "混参成片", "exec": "cloud", "width": 160, "height": 288,
             "fade": 0.15,
             "shots": [{"i": 1, "seconds": 15, "state": "done", "file": "shots/001.mp4"},
                       {"i": 2, "seconds": 15, "state": "done", "file": "shots/002.mp4"}]}
    prj.save(d6, proj6)
    fin10 = a._film_merge(d6, prj.load(d6))
    chk10 = stitch.inspect(ROOT, fin10)
    ok("混着出的片子按工程的画幅归一后拼成",
       os.path.isfile(fin10) and chk10["w"] == 160 and chk10["h"] == 288
       and chk10["audio"], (fin10, chk10))
    ok("归一化的中间片只落工程里的 norm/，不脏输出根目录",
       os.path.isdir(os.path.join(d6, "norm"))
       and not os.path.isdir(os.path.join(out, "_norm")),
       os.path.join(d6, "norm"))
    ok("转场秒数存在工程里，续跑重拼口径不丢",
       prj.load(d6).get("fade") == 0.15, prj.load(d6).get("fade"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        RESULTS.append(False)
    passed = sum(1 for x in RESULTS if x)
    print("\n%d/%d 通过" % (passed, len(RESULTS)))
    sys.exit(0 if passed == len(RESULTS) else 1)
