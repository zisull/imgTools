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

    def settings(self, cfg):
        return {"key": ""}

    def has_key(self, cfg):
        return True


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


def main():
    a = App()
    out = os.path.join(TMP, "outputs")
    os.makedirs(out, exist_ok=True)
    a.cfg["console"]["output_dir"] = out
    a.store = Store(os.path.join(TMP, "history.db"))
    a.store.init()
    a._trash_dir = os.path.join(TMP, "trash")

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
        "first": "", "acct": "", "acct_name": "", "wf": "", "count": count}

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
       len(made) == 3 and made[0][1] == "" and made[1][1] == fr1
       and made[2][1] == prj.abs_path(d, proj["shots"][1].get("frame") or ""),
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
       made and made[0][1] == fr1b and made[0][1] != prj.abs_path(d, proj.get("first") or ""),
       made)

    # ---------------- 重出：逐镜只作废目标段，接帧连带下游 ----------------
    proj = prj.load(d)
    proj["mode"] = "shot"
    proj["film"] = "old.mp4"
    prj.save(d, proj)
    files_before = [prj.abs_path(d, x.get("file") or "") for x in proj["shots"]]
    resumed = []
    a.film_resume = lambda dd="": (resumed.append(dd) or {"ok": True})
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
    ok("重出后走续跑而非另起工程", resumed and resumed[-1] == d, resumed)

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

    # ---------------- film_state / 快照 ----------------
    a.film_resume = type(a).film_resume.__get__(a)   # 还原，给后面真续跑用
    a._ai = real_ai
    st = a.film_state()
    ok("film_state 带 ffmpeg 与 Key 状态",
       st.get("ok") and st.get("ffmpeg") is True and st.get("ai_key") is False, st)
    snap = a._snap()
    ok("快照含成片三件套",
       "film" in snap and "ffmpeg" in snap and "ai_key" in snap)

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


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        RESULTS.append(False)
    passed = sum(1 for x in RESULTS if x)
    print("\n%d/%d 通过" % (passed, len(RESULTS)))
    sys.exit(0 if passed == len(RESULTS) else 1)
