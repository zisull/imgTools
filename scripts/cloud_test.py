# -*- coding: utf-8 -*-
"""云端账号库 / 共用调试浏览器的无浏览器自测。

    .venv\\Scripts\\python.exe scripts\\cloud_test.py

不起 Chromium、不碰 GPU：拿假 tab / 假 host 把「多账号 = 一只浏览器 + 多份数据」
这条契约钉住——落盘结构、备份轮换、换号时清残留、保活只在数据真变了才写盘、
以及索引里绝不出现凭据。真机冒烟（端口 9333、扫码登录）另跑，不在这里。
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="moss_cloud_")
os.environ["QIC_CONFIG"] = os.path.join(TMP, "config.json")
os.environ["QIC_CLOUD_DIR"] = os.path.join(TMP, "cloud")

from cloudkit import store as cs          # noqa: E402
from cloudkit import browser as cb        # noqa: E402


def _snap(domain=".runninghub.cn", **extra):
    c = {"name": "Rh-Identify", "value": "SECRET-TOKEN",
         "domain": domain, "path": "/", "expires": 4102444800}
    c.update(extra)
    return {"cookies": [c], "storage": {"Rh_Sid": "sid-1"}, "url": "https://www.runninghub.cn/"}


def _fresh():
    """每个用例一份独立账号库，别让上一个用例的账号混进 list()[0]。"""
    os.environ["QIC_CLOUD_DIR"] = tempfile.mkdtemp(prefix="t_", dir=TMP)
    return cs.AccountStore(ROOT)


def test_store_dir_isolated():
    s = cs.AccountStore(ROOT)
    assert s.dir == os.environ["QIC_CLOUD_DIR"], s.dir
    assert os.path.abspath(s.dir).startswith(os.path.abspath(TMP)), s.dir


def test_store_crud():
    s = _fresh()
    a = s.create("主号")
    aid = a["id"]
    assert a["state"] == "new" and s.exists(aid)
    assert s.get(aid)["name"] == "主号"
    assert s.rename(aid, "新名字") and s.get(aid)["name"] == "新名字"
    assert not s.rename(aid, "   ") and s.get(aid)["name"] == "新名字"
    auto = s.create("")
    assert auto["name"].strip(), auto
    assert s.delete(auto["id"]) and not s.exists(auto["id"])
    assert not os.path.isdir(s.acct_dir(auto["id"]))
    assert not s.delete("acc_missing")
    print("  ✓ 账号增删改：默认名、空名字拒绝、删号连带清目录")


def test_snapshots_and_prune():
    s = _fresh()
    aid = s.create("备份号")["id"]
    stamps = []
    for i in range(15):
        stamps.append(s.save(aid, _snap()["cookies"],
                             {"Rh_Sid": "sid-%d" % i}, "https://www.runninghub.cn/"))
        time.sleep(0.004)          # 时间戳带毫秒：同一毫秒两次保存会互相覆盖
    assert len(set(stamps)) == 15, stamps
    backs = s.backups(aid)
    assert len(backs) == cs.MAX_BACKUPS, backs
    assert s.load(aid)["storage"]["Rh_Sid"] == "sid-14"
    # 索引只放摘要：cookie 值 / API Key 不该出现在 accounts.json
    raw = open(s.index_path, encoding="utf-8").read()
    assert "SECRET-TOKEN" not in raw and "sid-14" not in raw, raw
    assert s.list()[0]["backups"] == cs.MAX_BACKUPS
    print("  ✓ 快照与轮换：15 次保存留 12 份、最新一份可读、索引不含凭据")


def test_restore_and_bad_ts():
    s = _fresh()
    aid = s.create("恢复号")["id"]
    s.save(aid, _snap()["cookies"], {"Rh_Sid": "old"}, "https://www.runninghub.cn/")
    time.sleep(0.004)
    s.save(aid, _snap()["cookies"], {"Rh_Sid": "new"}, "https://www.runninghub.cn/")
    old_ts = s.backups(aid)[-1]
    old = s.load(aid, old_ts)
    assert old["storage"]["Rh_Sid"] == "old", old
    now_ts = s.restore(aid, old_ts)
    assert now_ts and now_ts != old_ts
    assert s.load(aid)["storage"]["Rh_Sid"] == "old"
    assert len(s.backups(aid)) == 3          # 恢复也留历史，不删旧备份
    # ts 来自界面：必须过格式关，不能拿 ../ 去读别的文件
    assert s.load(aid, "../../accounts") is None
    assert s.restore(aid, "../x") == ""
    assert s.load(aid, "20260101-000000-000") is None
    print("  ✓ 备份恢复：复制成最新一份、历史不删、非法时间戳一律拒绝")


def test_key_roundtrip():
    s = _fresh()
    aid = s.create("Key 号")["id"]
    assert not s.set_key(aid, "  ")
    assert s.set_key(aid, "sk-local-test")
    assert s.get_key(aid) == "sk-local-test"
    assert s.list()[0]["has_key"] is True
    assert "sk-local-test" not in open(s.index_path, encoding="utf-8").read()
    assert s.clear_key(aid) and s.get_key(aid) == ""
    assert s.list()[0]["has_key"] is False
    print("  ✓ API Key：只在 u/<id>/key.json、索引只报「有没有」")


def test_cookie_helpers():
    rows = [
        {"name": "Rh-Identify", "value": "a", "domain": ".runninghub.cn",
         "path": "/", "expires": 1, "somethingElse": "x"},
        {"name": "Rh-Identify", "value": "dup", "domain": ".runninghub.cn", "path": "/"},
        {"name": "Rh-Identify", "value": "b", "domain": "evil-runninghub.cn", "path": "/"},
        {"name": "", "value": "nameless", "domain": ".runninghub.cn", "path": "/"},
    ]
    clean = cs.clean_cookies(rows)
    assert len(clean) == 2 and clean[0]["value"] == "a", clean
    assert "somethingElse" not in clean[0]
    kept = cs.filter_cookies(rows, ["runninghub.cn"])
    assert [c["value"] for c in kept] == ["a"], kept
    assert len(cs.filter_cookies(rows, [])) == 2
    assert cs.domain_ok(".runninghub.cn", ["runninghub.cn"])
    assert cs.domain_ok("www.runninghub.cn", ["runninghub.cn"])
    assert not cs.domain_ok("evil-runninghub.cn", ["runninghub.cn"])
    hdr = cs.auth_headers(
        [{"name": "Rh-Identify", "value": "v1"},
         {"name": "Rh-canvas_zoom_sensitivity", "value": "just-a-pref"},
         {"name": "session", "value": "keep-out"}],
        {"Rh-Comfy-Auth": "v2", "Rh-first-login": "keep-out", "other": "keep-out"})
    assert hdr == {"Rh-Identify": "v1", "Rh-Comfy-Auth": "v2"}, hdr
    assert cs.mask_secret("abcdefghij") == "abcd***ghij"
    assert cs.mask_secret("abc") == "***"
    print("  ✓ cookie 清洗/域名过滤/鉴权头按名单取：偏好与埋点不再冒充秘密")


class FakeCookieSetter:
    def __init__(self, tab):
        self.tab = tab

    def __call__(self, cookies):
        if isinstance(cookies, dict):
            cookies = [cookies]
        self.tab._cookies = [dict(c) for c in cookies]

    def clear(self):
        self.tab._cookies = []


class FakeSet:
    def __init__(self, tab):
        self.tab = tab
        self.cookies = FakeCookieSetter(tab)

    def local_storage(self, key, value):
        if value is False:
            self.tab._storage.pop(key, None)
        else:
            self.tab._storage[key] = value


class FakeTab:
    def __init__(self):
        self._cookies = []
        self._storage = {}
        self.url = "https://www.runninghub.cn/"
        self.body = ""
        self.set = FakeSet(self)

    def cookies(self, all_domains=False, all_info=False):
        return [dict(c) for c in self._cookies]

    def local_storage(self):
        return dict(self._storage)

    def run_js(self, _js):
        return self.body

    def get(self, url):
        self.url = url


def test_apply_and_snapshot():
    tab = FakeTab()
    tab._storage = {"stale": "x", "Rh_Sid": "old"}
    state = _snap()
    state["storage"] = {"Rh_Sid": "sid-2"}
    cb.apply_state(tab, state)
    assert [c["name"] for c in tab._cookies] == ["Rh-Identify"]
    assert tab._storage == {"Rh_Sid": "sid-2"}, tab._storage   # 上一号的残留被清掉
    snap = cb.snapshot_state(tab, ["runninghub.cn"])
    assert snap["cookies"][0]["value"] == "SECRET-TOKEN"
    assert snap["storage"] == {"Rh_Sid": "sid-2"}
    # 别的站点的 cookie 不跟快照走
    tab._cookies.append({"name": "other", "value": "x", "domain": ".example.com", "path": "/"})
    assert [c["name"] for c in cb.snapshot_state(tab, ["runninghub.cn"])["cookies"]] == ["Rh-Identify"]
    print("  ✓ 换号：先清 cookie/localStorage 残留，再灌快照；快照按域名收口")


def test_login_state():
    tab = FakeTab()
    tab.url = "https://www.runninghub.cn/login?redirect=x"
    assert cb.login_state(tab)[0] == "expired"
    tab.url = "https://www.runninghub.cn/"
    tab.body = "作品  个人中心  退出登录"
    assert cb.login_state(tab)[0] == "ok"
    tab.body = "登录 / 注册  扫码登录"
    assert cb.login_state(tab)[0] == "expired"
    tab.body = "这是一个活动页"
    assert cb.login_state(tab)[0] == "unknown"
    print("  ✓ 登录判定：URL / 登录后入口 / 登录入口 / 无信号，四档分明")


class FakeKeepTab:
    def __init__(self, host):
        self.host = host
        self.url = host.base

    def get(self, url):
        self.url = url

    def cookies(self, all_domains=False, all_info=False):
        return [{"name": "Rh-Identify", "value": self.host.values.get(self.host.current, ""),
                 "domain": ".runninghub.cn", "path": "/"}]

    def local_storage(self):
        return {"Rh_Sid": "sid-" + self.host.current}

    def run_js(self, _js):
        return "个人中心"


class FakeKeepHost:
    def __init__(self):
        self.base = "https://www.runninghub.cn"
        self.domains = ["runninghub.cn"]
        self.lock = threading.RLock()
        self.values = {"a1": "v1", "a2": "v0"}
        self.current = ""
        self.seq = []
        self.alive_flag = True
        self.purpose = ""
        self._tab = FakeKeepTab(self)

    def alive(self):
        return self.alive_flag

    def occupied(self):
        return bool(self.purpose)

    def apply(self, state, aid="", reload=True):
        self.current = aid
        self.seq.append(aid)

    def tab(self):
        return self._tab


class FakeKeepStore:
    def __init__(self):
        c = [{"name": "Rh-Identify", "value": "v0", "domain": ".runninghub.cn", "path": "/"}]
        self.snaps = {
            "a1": {"cookies": [dict(c[0])], "storage": {}, "url": ""},
            "a2": {"cookies": [dict(c[0])], "storage": {}, "url": ""},
        }
        self.saved = []
        self.marked = []

    def list(self):
        return [{"id": "a1"}, {"id": "a2"}]

    def load(self, aid):
        return self.snaps.get(aid)

    def save(self, aid, cookies, storage=None, url=""):
        self.saved.append(aid)
        self.snaps[aid] = {"cookies": cookies, "storage": storage or {}, "url": url}
        return "ts"

    def mark(self, aid, state, detail=""):
        self.marked.append((aid, state, detail))


def test_keepalive_sweep():
    host, store = FakeKeepHost(), FakeKeepStore()
    ka = cb.KeepAlive(host, store, {"keep": True, "keep_min": 30})
    assert ka.sweep() == 2
    assert host.seq == ["a1", "a2"], host.seq            # 串行轮换，绝不并行
    assert store.saved == ["a1"], store.saved            # a2 的数据没变就不写盘
    assert [a for a, _, _ in store.marked] == ["a1", "a2"]
    assert [s for _, s, _ in store.marked] == ["ok", "ok"]
    assert ka.last > 0 and "2 个账号" in ka.last_msg
    # 第二轮：服务端没再刷新 cookie，一份新备份都不该产生（否则 12 份很快被挤没）
    store.saved.clear()
    assert ka.sweep() == 2 and store.saved == [], store.saved
    # 登录页开着（人可能正在扫码）：保活让路，不能在眼皮底下换号
    host.purpose = "login"
    assert ka.sweep() == 0 and "让路" in ka.last_msg
    host.purpose = ""
    # 手动操作正占着浏览器（cloud_busy）：定时那一轮让路；人自己点的「立即保活」照跑
    ka.busy = lambda: True
    assert ka.sweep() == 0 and "让路" in ka.last_msg
    assert ka.sweep(force=True) == 2
    ka.busy = lambda: False
    # 云端出片占着（purpose=gen）：连「立即保活」也不许换号
    host.purpose = "gen"
    assert ka.sweep(force=True) == 0 and "出片" in ka.last_msg
    host.purpose = ""
    # 浏览器关着：跳过并说清楚，不许自己偷偷拉起一个窗口
    host.alive_flag = False
    assert ka.sweep() == 0 and "浏览器没开" in ka.last_msg
    print("  ✓ 保活：按序换号、只在 cookie 变化时落盘、登录/出片/手动操作占着就让路")


def test_pick_size():
    """界面那套「P=短边」怎么翻成云端那四件套（档位 + 画幅 + 宽 + 高）。

    线上实测过：档位/画幅那两颗控件改了以后序列化里的宽高纹丝不动，
    出片尺寸完全由 width/height 决定（提交 848×480 → 文件就是 848×480）。
    所以档位只是名字：凑得出短边档位就写 480P，凑不出就写 Custom，宽高一律原样带过去。
    """
    from cloudkit import gen as cg
    cases = [
        ((848, 480), {"resolution": "480P", "aspect_ratio": "16:9", "width": 848, "height": 480}),
        ((480, 848), {"resolution": "480P", "aspect_ratio": "9:16", "width": 480, "height": 848}),
        # 原生档：按 16 取整会算成 1360，界面登记的 1344 原样送过去
        ((1344, 768), {"resolution": "768P", "aspect_ratio": "16:9",
                       "width": 1344, "height": 768}),
        ((768, 1344), {"resolution": "768P", "aspect_ratio": "9:16",
                       "width": 768, "height": 1344}),
        ((768, 768), {"resolution": "768P", "aspect_ratio": "1:1", "width": 768, "height": 768}),
        # 自定义（短边不在档位上）：档位写 Custom，但画幅一个像素都不替人改
        ((900, 600), {"resolution": "Custom", "aspect_ratio": "16:9",
                      "width": 896, "height": 608}),
        ((1350, 749), {"resolution": "Custom", "aspect_ratio": "16:9",
                       "width": 1344, "height": 752}),
    ]
    for (w, h), want in cases:
        got = cg.pick_size(w, h)
        assert got == want, ((w, h), got, want)
    # 840 正好卡在「.5」上：两边都必须四舍五入到 848（Python 自带的 round 是「.5 向偶数」，
    # 会给出 832，前后端就差一格——这条锁就是为它写的）
    assert cg.pick_size(840, 480)["width"] == 848, cg.pick_size(840, 480)
    # 2K 是短边 1440（2560×1440），平台档位表里没有这一档，写 Custom、宽高原样带过去；
    # 再往上平台不收，钳在 2560
    assert cg.pick_size(2560, 1440) == {"resolution": "Custom", "aspect_ratio": "16:9",
                                        "width": 2560, "height": 1440}
    assert cg.pick_size(1440, 1440) == {"resolution": "Custom", "aspect_ratio": "1:1",
                                        "width": 1440, "height": 1440}
    assert cg.pick_size(3840, 2160)["width"] == 2560, cg.pick_size(3840, 2160)
    print("  ✓ 云端尺寸：宽高自己定、档位只当名字、自定义不改人画幅、上限到 2K")


def test_wf_src():
    """工作流那一格：平台地址 / 本地导出的 .json / 什么都没有，三种各回一句话。

    本地那份没有工作流编号（导出文件里只有一个随机 uuid），所以还得借一个宿主页——
    「换图不换实例」：换的是画布上那张图，跑它的还是那台托管实例。
    """
    from cloudkit import gen as cg
    d = tempfile.mkdtemp(prefix="wf_", dir=TMP)
    p = os.path.join(d, "h3.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"nodes": [{"id": 1, "type": "FeiHouEasyH3RH"}], "links": []}, f)

    g = cg.CloudH3(ROOT, {}, None, None)
    assert g.wf_src() == ("", ""), g.wf_src()
    g.cfg = {"workflow": "https://www.runninghub.cn/ai-detail/1/workflow/123"}
    assert g.wf_src() == ("remote", g.cfg["workflow"])
    g.cfg = {"workflow": p}
    assert g.wf_src() == ("file", os.path.normpath(p)), g.wf_src()
    g.cfg = {"workflow": os.path.join(d, "nope.json")}
    try:
        g.wf_src()
        raise AssertionError("本地文件不在却没报错")
    except cg.CloudError as e:
        assert "找不到" in str(e), str(e)

    # 宿主页：能认整段地址里的编号、也认纯数字；没填就说清楚要补什么
    g.cfg = {"wf_host": "https://www.runninghub.cn/ai-detail/1/workflow/777"}
    assert g.host_url() == cg.WF_URL % "777", g.host_url()
    g.cfg = {"wf_host": "888"}
    assert g.host_url() == cg.WF_URL % "888", g.host_url()
    g.cfg = {"workflow": p}
    try:
        g.host_url()
        raise AssertionError("没填宿主页却没报错")
    except cg.CloudError as e:
        assert "宿主页" in str(e), str(e)
    print("  ✓ 云端工作流：平台地址 / 本地 .json / 宿主页三态，缺了各说一句话")


def test_load_local_wf():
    """把本地 JSON 灌进页面：不是画布、不是 JSON、灌不进、超过 8MB 各拦一次。

    真机量过：托管前端有 app.loadGraphData，导出 65605 字节能原样灌回去、
    23 个节点按类型重新认得出主节点与输出节点。这里拿假 tab 锁住失败那几条。
    """
    from cloudkit import gen as cg
    d = tempfile.mkdtemp(prefix="load_", dir=TMP)

    def mk(name, text):
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    good = mk("g.json", json.dumps({"nodes": [{"id": 1}], "links": []}))
    g = cg.CloudH3(ROOT, {}, None, None)
    g.js = lambda *a: json.dumps({"ok": 1, "nodes": 1})
    g._wait_graph = lambda tab, fid, stop, limit=30: {"main": "1", "out": "2"}
    assert g.load_local_wf(None, "f", good, lambda: False) == {"main": "1", "out": "2"}
    assert g.wf_title.startswith("本地 · "), g.wf_title

    def boom(path, script_ret=None):
        if script_ret is not None:
            g.js = lambda *a: script_ret
        try:
            g.load_local_wf(None, "f", path, lambda: False)
        except cg.CloudError as e:
            return str(e)
        raise AssertionError("没拦住：%s" % path)

    assert "不是 JSON" in boom(mk("b.json", "{oops"))
    # 我们自己那份 API 格式（{"1": {...}}）不是画布，要说清是哪一种
    assert "没有画布" in boom(mk("api.json", json.dumps({"1": {"class_type": "X"}})))
    assert "灌不进" in boom(good, json.dumps({"err": "no_frame"}))
    assert "8MB" in boom(mk("big.json", '{"nodes":[1]}' + " " * (9 * 1048576)))
    print("  ✓ 本地工作流灌入：不是画布 / 不是 JSON / 灌不进 / 超 8MB，四种都拦得住")


def test_write_selfcheck():
    """提交前那道自检：读不到序列化就是失败，不许「拿不到值 = 全绿」。

    这条锁来自真踩过的坑：graphToPrompt() 在现代版本回的是 Promise，
    旧写法直接取 .output 拿到 undefined，每一项都「没值」，检查全部通过，
    于是提示词没写进去、参考图槽位还挂着平台原来 6 张图这种问题一路放到提交。
    """
    from cloudkit import gen as cg
    size = cg.pick_size(848, 480)
    spec = {"prompt": "一只猫推开木门，阳光落在地板上", "media": [1]}
    good = {"mode": "image", "fps": 24, "seconds": 5, "resolution": "480P",
            "media": 1, "slots": 1, "prompt": spec["prompt"]}

    def gen(check, bad=None, editor=True):
        g = cg.CloudH3(TMP, {}, None, None)
        g.js = lambda tab, script, *a: json.dumps(
            {"bad": bad or [], "check": check, "editor": editor})
        return g

    def run(check, **kw):
        g = gen(check, **kw)
        return g._write(None, "f", {"main": 389, "out": 325}, spec, 5, size, True)

    assert run(dict(good))                       # 全对：不该抛
    for label, bad in (
        ("读不到序列化", {}),                     # 就是那次 Promise 故障的形状
        ("序列化报错", {"err": "boom"}),
        ("槽位没清", dict(good, slots=6)),
        ("媒体没写", dict(good, media=0)),
        ("提示词没进去", dict(good, prompt="## subject_definitions <Subject 1> 老片段")),
        ("档位不对", dict(good, resolution="768P")),
        ("fps 不对", dict(good, fps=1)),
        ("时长不对", dict(good, seconds=15)),
        ("模式不对", dict(good, mode="reference")),
    ):
        try:
            run(dict(bad))
        except cg.CloudError as e:
            assert str(e), label
        else:
            raise AssertionError("自检没拦住：%s" % label)
    print("  ✓ 提交前自检：缺证据即失败，槽位/媒体/提示词/档位/fps/时长/模式逐项拦得住")


def test_platform_state():
    """等片那段的实话：把平台队列读成人话，读不到就闭嘴——不编状态。

    云端出片时间波动大（一段 353 秒、一段排到二十分钟没动），只报「已等 N 秒」
    等于没报：人分不清排队、在跑还是已经失败。
    """
    from cloudkit import gen as cg

    def g(raw):
        x = cg.CloudH3(TMP, {}, None, None)
        x.js = lambda tab, script, *a: raw
        return x

    cases = [
        ('{"http":{"run":1,"pend":0,"keys":["queue_running"]},"mem":null}', 300, "平台正在跑这一段"),
        ('{"http":{"run":0,"pend":2,"keys":["queue_pending"]}}', 300, "排队中 · 前面 2 个"),
        # 实测这份托管前端 w.app.queue 是 null，内存那份读不到；GET /queue 才是通的。
        # 反过来哪天网关挡了 GET，内存里那份也得能顶上来——两条路都留着测。
        ('{"http":null,"mem":{"run":1,"pend":0,"keys":["running"]}}', 300, "平台正在跑这一段"),
        # 两份口径不一致时以内存那份为准：那是界面自己按推送维护的，和人看到的一致
        ('{"http":{"run":0,"pend":0,"keys":["queue_running"]},"mem":{"run":1,"pend":0,"keys":["queue_running"]}}',
         300, "平台正在跑这一段"),
        # 队列读到且真空、历史也没多出一条：只能说「平台上查不到这段」，
        # 说「队列已空」听着像判了死刑（实测提交后头几分钟就是这个状态，片段还在平台池子里）
        ('{"http":{"run":0,"pend":0,"keys":["queue_running"]},"btn":"运行Lite","h":{"n":1,"last":{"id":"a"}}}',
         300, "平台上查不到这段任务"),
        # 新版前端字段改叫 running/queued：计数照样读得到，别因为叫法不同就当没读到
        ('{"http":{"run":0,"pend":2,"keys":["running","queued"]}}', 300, "排队中 · 前面 2 个"),
        ('{"http":{"run":0,"pend":0,"keys":["queue_running"]}}', 10, ""),   # 刚提交，别急着下结论
        ('{"btn":"运行"}', 300, ""),                              # 没读到队列对象＝不知情，不说「空了」
        # 新版前端只有 app.queueItems 那个数组：不区分跑着/排着，就不许说成「正在跑」
        ('{"http":null,"mem":null,"items":{"n":2}}', 300, "平台上有 2 个任务"),
        ('{"http":null,"mem":null,"items":{"n":0}}', 300, ""),
        ('{"http":{"run":0,"pend":0},"mem":null}', 900, ""),      # 同上：字段读成 undefined 不是空队列
        ('{"err":"no_frame"}', 300, ""),
        ('不是 JSON', 300, ""),
        ('', 300, ""),
    ]
    for raw, waited, want in cases:
        got = g(raw).platform_state(None, "f", waited, 1)
        assert (want in got) if want else (got == want), "%s → %r（想要含 %r）" % (raw, got, want)
    assert "运行Lite" in g('{"http":{"run":0,"pend":0,"keys":["r"]},"btn":"运行Lite"}'
                           ).platform_state(None, "f", 900, 0)

    # 历史多出一条 + error ＝ 真失败；没多出来 ＝ 那条是旧账，不能算在我们这段头上
    err = '{"http":{"run":0,"pend":0,"keys":["q"]},"h":{"n":2,"last":{"id":"b","s":"error"}}}'
    assert "平台把这段判了失败" in g(err).platform_state(None, "f", 300, 1), "报错没认出来"
    assert "平台上查不到" in g(err).platform_state(None, "f", 300, 2), "把上一条旧记录当成了这段的失败"
    # 多出一条、跑完了（c=true）而片子还没刷新 vs 还没跑完：两句话不一样
    okd = '{"http":{"run":0,"pend":0,"keys":["q"]},"h":{"n":2,"last":{"id":"b","s":"success","c":true}}}'
    assert "输出节点还没刷新" in g(okd).platform_state(None, "f", 300, 1), "跑完没刷新没认出来"
    run = '{"http":{"run":0,"pend":0,"keys":["q"]},"h":{"n":2,"last":{"id":"b","s":"running"}}}'
    assert "平台已经收下这段" in g(run).platform_state(None, "f", 300, 1), "收下没跑完没认出来"
    print("  ✓ 云端状态：在跑/排队/查不到/报错/跑完没刷新五种说实话，读不到就留空不编")

    # 超时那句也要带「看见了什么」：光说等超时，人不知道该怪排队还是怪取回
    def terr(where):
        x = cg.CloudH3(TMP, {}, None, None)
        x.timeout = 300
        try:
            x._timeout_err(where, "")
        except cg.CloudError as e:
            return str(e)
        raise AssertionError("没抛错：%r" % where)
    # 「查不到」不能写成「多半没提交成功」：实测出片成功的那段同样查不到
    assert "平台自己的池子" in terr("平台上查不到这段任务 · 按钮「运行」"), terr("查不到")
    assert "没提交" not in terr("平台上查不到这段任务"), "把查不到说成了没提交"
    assert "前面还有别人" in terr("云端排队中 · 前面 3 个"), terr("排队")
    assert "取回来的这一步" in terr("平台说这段跑完了，可输出节点还没刷新"), terr("跑完没刷新")
    assert "没读到平台状态" in terr(""), terr("")
    print("  ✓ 云端超时收尾：把看见的原因带进错误里，不是一句「等超时」")


def test_bridge_without_dp():
    import app as webapp
    old = webapp.App._dp_ready
    webapp.App._dp_ready = lambda self: False
    try:
        os.environ["QIC_CLOUD_DIR"] = tempfile.mkdtemp(prefix="t_", dir=TMP)
        cs.AccountStore(ROOT).create("既有档案")
        a = webapp.App()
        s = a.cloud_state()
        assert s["ok"] is True and s["dp"] is False, s
        assert s["concurrency"] == 1
        assert [x["name"] for x in s["accounts"]] == ["既有档案"], s["accounts"]
        assert "DrissionPage" in s["msg"], s["msg"]
        r = a.cloud_new("临时号")
        assert r["ok"] is False and "DrissionPage" in r["msg"], r
        assert a._cloudx is None, "缺依赖时不许把浏览器/保活线程建起来"
    finally:
        webapp.App._dp_ready = old
    print("  ✓ 后端桥：缺 DrissionPage 只影响开浏览器，档案仍列得出来、不拖启动")


def main():
    tests = [
        test_store_dir_isolated,
        test_store_crud,
        test_snapshots_and_prune,
        test_restore_and_bad_ts,
        test_key_roundtrip,
        test_cookie_helpers,
        test_apply_and_snapshot,
        test_login_state,
        test_keepalive_sweep,
        test_pick_size,
        test_wf_src,
        test_load_local_wf,
        test_write_selfcheck,
        test_platform_state,
        test_bridge_without_dp,
    ]
    print("云端账号库自测（无浏览器 / 无 GPU）")
    try:
        for t in tests:
            t()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("全部通过")


if __name__ == "__main__":
    main()
