# -*- coding: utf-8 -*-
"""云端账号库 / 共用调试浏览器的无浏览器自测。

    .venv\\Scripts\\python.exe scripts\\cloud_test.py

不起 Chromium、不碰 GPU：拿假 tab / 假 host 把「一个号一只浏览器（1 号=主窗口，
2 号起独立端口）+ 快照落盘」这条契约钉住——备份轮换、灌快照前清残留、保活只在
数据真变了才写盘、号位/端口不重叠，以及索引里绝不出现凭据。
真机冒烟（端口 9333、扫码登录）另跑，不在这里。
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
    # 留空＝软件自带那张默认画布（平台上那张 H3 参考生视频），不用人填也不用拖文件
    kind, src = g.wf_src()
    assert (kind, src) == ("remote", cg.WF_URL % cg.DEFAULT_WF), src
    assert g.wf_label(kind, src).startswith("默认 · "), g.wf_label(kind, src)
    # 平台那一格能粘好几种地址，编号都提得出来、都拼成编辑器入口那一页
    for u, want in (("https://www.runninghub.cn/ai-detail/1/workflow/123", "123"),
                    ("https://www.runninghub.cn/ai-detail/%s" % cg.DEFAULT_WF, cg.DEFAULT_WF),
                    ("https://www.runninghub.cn/ai-detail/2/%s" % cg.DEFAULT_WF, cg.DEFAULT_WF),
                    ("https://www.runninghub.cn/workflow/%s" % cg.DEFAULT_WF, cg.DEFAULT_WF),
                    # 分享页那一格也算：人从社区里点进来的就是这种地址
                    ("https://www.runninghub.cn/post/%s/?inviteCode=rh-v1333" % cg.DEFAULT_WF,
                     cg.DEFAULT_WF),
                    (cg.DEFAULT_WF, cg.DEFAULT_WF)):
        assert cg.wf_id_of(u) == want, u
    g.cfg = {"workflow": "https://www.runninghub.cn/ai-detail/1/workflow/123"}
    assert g.wf_src() == ("remote", g.cfg["workflow"])
    assert g.wf_url() == cg.WF_URL % "123", g.wf_url()
    assert g.wf_label("remote", g.cfg["workflow"]).startswith("平台 · ")
    # 默认那张顶上：填了本地文件或什么都没填时 wf_id 不能回空，否则拼不出入口页
    g.cfg = {"workflow": p}
    assert g.wf_id() == cg.DEFAULT_WF, g.wf_id()
    assert g.wf_src() == ("file", os.path.normpath(p)), g.wf_src()
    g.cfg = {"workflow": os.path.join(d, "nope.json")}
    try:
        g.wf_src()
        raise AssertionError("本地文件不在却没报错")
    except cg.CloudError as e:
        assert "找不到" in str(e), str(e)

    # 宿主页：手动覆盖 → 平台默认 → 内置页；内置页保证「只给本地文件也能跑」
    g.cfg = {"wf_host": "https://www.runninghub.cn/ai-detail/1/workflow/777",
             "default_wf": cg.WF_URL % "999"}
    assert g.host_url() == cg.WF_URL % "777", g.host_url()
    g.cfg = {"wf_host": "", "default_wf": "888"}
    assert g.host_url() == cg.WF_URL % "888", g.host_url()
    g.cfg = {"workflow": p}
    assert g.host_url() == cg.WF_URL % cg.DEFAULT_WF, g.host_url()
    # 连默认那张都没了也要有页可开：内置那一页是最后一级跳板
    keep = cg.DEFAULT_WF
    try:
        cg.DEFAULT_WF = ""
        assert g.host_url() == cg.HOST_WF_FALLBACK, g.host_url()
    finally:
        cg.DEFAULT_WF = keep
    print("  ✓ 云端工作流：留空＝内置默认那张 / 平台那几种地址都提得出编号 / 手动覆盖仍优先")


def test_kj_write():
    """新形状（参数挂在虚拟节点上那张）：认完接线之后要写哪几格、尺寸怎么折。

    这几条都是真机量出来的，钉住免得以后改回「拿默认值瞎写」：
      · 帧数那条数学式（5 秒→124、12 秒→294，回来的文件就是 294 帧 / 12.25 秒）；
      · 分辨率选择器往上贴格子（作者说明表 0.2→608x352、0.98→1344x768）；
      · 百万像素那格是浮点，别替它抢着圆——按它报的 step=1 圆会把 1280x720 抬到 1.0 兆，
        出片反而比界面大一档，白烧显存。
    """
    from cloudkit import gen as cg
    assert [cg.kj_frames(s) for s in (5, 6, 8, 10, 12, 15)] == [124, 158, 192, 243, 294, 362]
    assert cg.kj_out_size("0.9", "16:9", 32) == (1280, 736)
    assert cg.kj_out_size(0.98, "16:9", 32) == (1344, 768)
    assert cg.kj_out_size(0.2, "16:9", 32) == (608, 352)
    assert cg.kj_out_size(0.9, "9:16", 32) == (736, 1280)
    assert cg.kj_out_size(0.9, "坏画幅", 32) == (0, 0)
    assert cg.megapixels_of(1280, 720) == 0.92
    assert cg.snap_megapixels(0.92, {"opts": ["0.5", "0.9", "1.5"]}) == "0.9"
    assert cg.snap_megapixels(0.92, {"opts": None, "step": 1}) == 0.92
    opts = ["1:1 (Square)", "9:16 (Portrait Widescreen)", "16:9 (Widescreen)"]
    assert cg.ratio_label(opts, "16:9") == "16:9 (Widescreen)"
    assert cg.ratio_label(opts, "4:5") == ""

    g = cg.CloudH3(ROOT, {}, None, None)
    size = cg.pick_size(1280, 720)
    res = {"roles": {"prompt": {"id": 263, "w": "text", "src": "text"},
                     "length": {"id": 259, "w": "value", "src": "prim"},
                     "width": {"id": 252, "w": "aspect_ratio", "src": "res"},
                     "height": {"id": 252, "w": "aspect_ratio", "src": "res"}},
           "aspect": opts, "res": {"opts": None, "step": 1}, "multiple": 32}
    w = g._kj_writes(res, "雨夜的旧书店 <Picture 1>", 5, size)
    assert [x[4] for x in w] == ["prompt", "seconds", "aspect", "megapixels"], w
    assert w[0][:3] == [263, "text", "雨夜的旧书店 <Picture 1>"], w[0]
    assert w[1][2] == 5, "接了数学式的那格写秒数，帧数由它自己算"
    assert w[2][2] == "16:9 (Widescreen)" and w[2][3] is True, "画幅必须是下拉里的值"
    assert w[3][2] == 0.92
    # 主节点自己带宽高（没接选择器）：直接写那两格，不去找画幅；时长也就写帧数
    direct = {"roles": {"prompt": {"id": 389, "w": "prompt", "src": "direct"},
                        "length": {"id": 389, "w": "length", "src": "direct"},
                        "width": {"id": 389, "w": "width", "src": "direct"},
                        "height": {"id": 389, "w": "height", "src": "direct"}}}
    w2 = g._kj_writes(direct, "x", 5, size)
    assert [x[4] for x in w2] == ["prompt", "seconds", "width", "height"], w2
    assert w2[1][2] == cg.kj_frames(5) and w2[0][3] is False
    # 画幅对不上这张图的档位：停下说一声，别交一个它不认的字符串出去
    bad = dict(res, aspect=["1:1 (Square)"])
    try:
        g._kj_writes(bad, "x", 5, size)
        raise AssertionError("画幅不在选项里却没报错")
    except cg.CloudError as e:
        assert "画幅" in str(e), str(e)

    # 形状：两种画法都得认，缺主节点的照样拦
    d = tempfile.mkdtemp(prefix="kj_", dir=TMP)

    def wf(nodes):
        p = os.path.join(d, "n.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"nodes": nodes, "links": []}, f)
        return p
    kj = wf([{"id": 265, "type": cg.MAIN_TYPE_KJ}, {"id": 364, "type": cg.OUT_TYPE}])
    assert cg.check_workflow_json(kj)["shape"] == cg.SHAPE_KJ
    fh = wf([{"id": 389, "type": cg.MAIN_TYPE}, {"id": 325, "type": cg.OUT_TYPE}])
    assert cg.check_workflow_json(fh)["shape"] == cg.SHAPE_FH
    try:
        cg.check_workflow_json(wf([{"id": 1, "type": "KSampler"}]))
        raise AssertionError("没有 H3 主节点却没报错")
    except cg.CloudError as e:
        assert "主节点" in str(e), str(e)

    # 界面口径的编号 → 节点认的 <Picture N>
    assert cg.mention.picture_text("a @1 b [2] c", 2) == ("a <Picture 1> b <Picture 2> c", 2)
    txt, n = cg.mention.picture_text("什么编号都没写", 3)
    assert n == 3 and txt.startswith("<Picture 1> <Picture 2> <Picture 3>"), txt
    assert cg.mention.picture_text("单图不用点名", 1) == ("单图不用点名", 0)
    try:
        cg.mention.picture_text("@5 超出了", 2)
        raise AssertionError("引用越界却没报错")
    except ValueError as e:
        assert "第 5 张" in str(e), str(e)
    print("  ✓ 新形状写路径：接线清单 / 帧数与尺寸口径 / 两种画法都认 / 编号换成 <Picture N>")


def test_load_local_wf():
    """本地工作流：开跑前验结构、灌图等异步结果、失败当场停。

    真机量过：托管前端有 app.loadGraphData，导出 65605 字节能原样灌回去、
    23 个节点按类型重新认得出主节点与输出节点。新版前端还会把失败藏进 Promise，
    这里用假 tab 把「结构不对 / 灌图报错 / setGraph」几条都锁住。
    """
    from cloudkit import gen as cg
    d = tempfile.mkdtemp(prefix="load_", dir=TMP)

    def mk(name, obj):
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(obj if isinstance(obj, str) else json.dumps(obj))
        return p

    good_obj = {"nodes": [{"id": 1, "type": "FeiHouEasyH3RH"},
                          {"id": 2, "type": "VHS_VideoCombine"}],
                "links": [[1, 1, 0, 2, 0, "IMAGE"]]}
    good = mk("g.json", good_obj)

    class Tab:
        def refresh(self):
            pass

    g = cg.CloudH3(ROOT, {}, None, None)
    g.js = lambda *a: json.dumps({"ok": 1, "state": "ok", "ids": ["1", "2"],
                                  "main": 1, "out": 2, "nodes": 2})
    assert g.load_local_wf(Tab(), "f", good, lambda: False) == {
        "main": 1, "out": 2, "nodes": 2, "shape": cg.SHAPE_FH}
    assert g.shape == cg.SHAPE_FH and g.wf_title.startswith("本地 · "), g.wf_title

    def boom(path, tab=None):
        try:
            g.load_local_wf(tab, "f", path, lambda: False)
        except cg.CloudError as e:
            return str(e)
        raise AssertionError("没拦住：%s" % path)

    assert "不是 JSON" in boom(mk("b.json", "{oops"))
    # 我们自己那份 API 格式（{"1": {...}}）不是画布，要说清是哪一种
    assert "API 格式" in boom(mk("api.json", {"1": {"class_type": "X"}}))
    assert "没有画布节点" in boom(mk("nocanvas.json", {"nodes": [], "links": []}))
    # 节点/连线结构不对：开跑前就拦，不等到页面里报错
    assert "H3 主节点" in boom(mk("wrong.json", {
        "nodes": [{"id": 1, "type": "Other"}], "links": []}))
    assert "VHS_VideoCombine" in boom(mk("noout.json", {
        "nodes": [{"id": 1, "type": "FeiHouEasyH3RH"}], "links": []}))
    assert "连线" in boom(mk("badlink.json", {
        "nodes": good_obj["nodes"], "links": [[1, 1, 0, 9, 0, "IMAGE"]]}))
    assert "8MB" in boom(mk("big.json", '{"nodes":[1]}' + " " * (9 * 1048576)))

    # 页面异步报错：等到的错误要带出来，而不是继续拿旧图提交
    g2 = cg.CloudH3(ROOT, {}, None, None)

    def js(tab, script, *a):
        if script is cg._JS_FRONTEND_READY:
            return True
        if script is cg._JS_LOAD_WF:
            return json.dumps({"ok": 1})
        if script is cg._JS_WF_STATE:
            return json.dumps({"state": "err", "msg": "TypeError: setGraph is undefined"})
        return "f"

    g2.js = js
    msg = ""
    try:
        g2.load_local_wf(Tab(), "f", good, lambda: False)
    except cg.CloudError as e:
        msg = str(e)
    assert "setGraph" in msg, msg

    # 真机踩过的那次：restart 之后灌图，前端回执 ok 但画布一条节点都没认到，
    # 旧写法一次读数就判死 → 整批被按「工作流加载不上」暂停。
    # 平台自己那张图是异步挂上来的，后到时会把本地这份盖掉：给它几秒，稳住了才算灌上。
    g3 = cg.CloudH3(ROOT, {}, None, None)
    g3.wf_settle = 2
    seq = {"load": 0, "state": 0}

    def js3(tab, script, *a):
        if script is cg._JS_FRONTEND_READY:
            return True
        if script is cg._JS_LOAD_WF:
            seq["load"] += 1
            return json.dumps({"ok": 1})
        if script is cg._JS_WF_STATE:
            seq["state"] += 1
            if seq["state"] < 3:      # 头两次：图挂上了但节点还没换过来
                return json.dumps({"state": "ok", "ids": [], "nodes": 0})
            return json.dumps({"state": "ok", "ids": ["1", "2"],
                               "main": 1, "out": 2})
        return "f"

    g3.js = js3
    assert g3.load_local_wf(Tab(), "f", good, lambda: False) == {
        "main": 1, "out": 2, "nodes": 2, "shape": cg.SHAPE_FH}
    assert seq["load"] == 1, seq          # 稳住了就别再灌第二遍
    # 默认值：配置文件没写就是 6 秒，写了按写的
    assert cg.CloudH3(ROOT, {}, None, None).wf_settle == 6
    assert cg.CloudH3(ROOT, {"wf_settle_sec": 2}, None, None).wf_settle == 2

    # 一直认不到：三次（原地再灌一次 + 整页重开一次）都不行才停，错误照说
    g4 = cg.CloudH3(ROOT, {}, None, None)
    g4.wf_settle = 0
    hits = {"load": 0, "refresh": 0}

    class Tab2:
        def refresh(self):
            hits["refresh"] += 1

    def js4(tab, script, *a):
        if script is cg._JS_FRONTEND_READY:
            return True
        if script is cg._JS_LOAD_WF:
            hits["load"] += 1
            return json.dumps({"ok": 1})
        if script is cg._JS_WF_STATE:
            return json.dumps({"state": "ok", "ids": [], "nodes": 0})
        return "f"

    g4.js = js4
    msg4 = ""
    try:
        g4.load_local_wf(Tab2(), "f", good, lambda: False)
    except cg.CloudError as e:
        msg4 = str(e)
    assert "只认到 0 个" in msg4, msg4
    assert hits["load"] == 3 and hits["refresh"] == 1, hits
    print("  ✓ 本地工作流：结构/连线/API 格式先拦，异步 setGraph 也当场停，"
          "画布 0 节点先等它稳")


def test_write_selfcheck():
    """提交前那道自检：读不到序列化就是失败，不许「拿不到值 = 全绿」。

    这条锁来自真踩过的坑：graphToPrompt() 在现代版本回的是 Promise，
    旧写法直接取 .output 拿到 undefined，每一项都「没值」，检查全部通过，
    于是提示词没写进去、参考图槽位还挂着平台原来 6 张图这种问题一路放到提交。
    """
    from cloudkit import gen as cg
    size = cg.pick_size(848, 480)
    # 媒体条目要和 media_item() 同形：filename 是刚传上去的那一张，storage 只能是 input
    spec = {"prompt": "一只猫推开木门，阳光落在地板上",
            "media": [{"media_type": "image", "ordinal": 1, "filename": "new.png",
                       "subfolder": "", "storage": "input", "audio_trim": ""}]}
    good = {"mode": "reference", "fps": 24, "seconds": 5, "resolution": "480P",
            "media": 1, "slots": 1, "gallery": 1,
            "media0": {"filename": "new.png", "ordinal": 1, "storage": "input"},
            "prompt": spec["prompt"]}

    def gen(check, bad=None, editor=True):
        g = cg.CloudH3(TMP, {}, None, None)
        g.js = lambda tab, script, *a: json.dumps(
            {"bad": bad or [], "check": check, "editor": editor})
        return g

    def run(check, spec_=None, **kw):
        g = gen(check, **kw)
        return g._write(None, "f", {"main": 389, "out": 325}, spec_ or spec, 5, size)

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
        # 有参考图必须走 reference：切到 image 就是平台那条「参考生视频未收到图片」
        ("模式不对", dict(good, mode="image")),
        # 从线上旧条目抄来的 storage 会让执行节点取不到文件
        ("storage 抄旧了", dict(good, media0={"filename": "new.png", "storage": "comfyui"})),
        ("媒体没换成新图", dict(good, media0={"filename": "old.png", "storage": "input"})),
        ("画廊没认", dict(good, gallery=0)),
    ):
        try:
            run(dict(bad))
        except cg.CloudError as e:
            assert str(e), label
        else:
            raise AssertionError("自检没拦住：%s" % label)

    # 多图：逐条比对文件名/序号，且 @编号必须真变成 chip
    spec2 = {"prompt": "@1 和 @2", "chips": 2,
             "media": [{"filename": "a.png", "ordinal": 1, "storage": "input"},
                       {"filename": "b.png", "ordinal": 2, "storage": "input"}]}
    good2 = {"mode": "reference", "fps": 24, "seconds": 5, "resolution": "480P",
             "media": 2, "slots": 2, "gallery": 2, "chips": 2, "prompt": "",
             "mediaAll": [{"filename": "a.png", "ordinal": 1, "storage": "input"},
                          {"filename": "b.png", "ordinal": 2, "storage": "input"}]}
    assert run(dict(good2), spec2)
    for label, bad in (
        ("第二张还是旧图", dict(good2, mediaAll=[
            good2["mediaAll"][0],
            {"filename": "old.png", "ordinal": 2, "storage": "input"}])),
        ("序号不连续", dict(good2, mediaAll=[
            good2["mediaAll"][0],
            {"filename": "b.png", "ordinal": 3, "storage": "input"}])),
        ("chip 少了", dict(good2, chips=1)),
    ):
        try:
            run(dict(bad), spec2)
        except cg.CloudError as e:
            assert str(e), label
        else:
            raise AssertionError("多图自检没拦住：%s" % label)
    print("  ✓ 提交前自检：缺证据即失败，槽位/媒体/提示词/档位/fps/时长/模式逐项拦得住")
    print("  ✓ 多图自检：逐张比对文件名/序号，chip 少了当场停")


def test_media_item():
    """媒体条目的形状锁死成 H3yun 实机那一份。

    storage 只能是 input（上传口就是 /upload/image + type=input），audio_trim 必须是空串；
    从线上旧条目抄模板会把 comfyui / 裁切区间带进来，节点执行时取不到文件，
    平台就回那句「参考生视频未收到图片或视频」。
    """
    from cloudkit import gen as cg
    g = cg.CloudH3(TMP, {}, None, None)
    assert g.media_item("a.png", "") == {
        "media_type": "image", "ordinal": 1, "filename": "a.png",
        "subfolder": "", "storage": "input", "audio_trim": ""}
    assert g.media_item("a.png", "sub")["subfolder"] == "sub"
    assert g.media_item("b.png", "", 3)["ordinal"] == 3
    print("  ✓ 媒体条目：storage=input、audio_trim 空、序号连续、字段不随旧模板漂")


def test_mention():
    """编号引用必须是 chip DOM：纯文本 @1 在编辑器序列化时只是普通文字。"""
    from cloudkit import mention as mn
    media = [
        {"ordinal": 1, "filename": "a.png"},
        {"ordinal": 2, "filename": "b c.png"},
    ]
    assert mn.normalize("@图1 和 [2] 还有 @3") == "@1 和 @2 还有 @3"
    assert mn.ref_numbers("@1 @2") == [1, 2]
    try:
        mn.ref_numbers("@3", 2)
        out = False
    except ValueError:
        out = True
    assert out, "越界编号必须报错"
    assert mn.render_prompt("一只猫", media[:1]) == (None, 0), "单图无编号走纯文本老路"
    html, n = mn.render_prompt("一只猫", media)
    assert n == 2 and html.count('class="h3-mention-chip"') == 2, (n, html[:80])
    html, n = mn.render_prompt("@2 走到门口", media)
    assert n == 1 and 'data-ordinal="2"' in html and "@图2" in html, html[:120]
    assert 'data-token="@Image2"' in html and 'data-tag="&lt;Picture 2&gt;"' in html
    assert "src=\"/view?filename=b c.png&amp;type=input\"" in html, html[:200]
    html, n = mn.render_prompt("@2 <b>别当真</b>", media)
    assert "&lt;b&gt;别当真&lt;/b&gt;" in html, html
    try:
        mn.render_prompt("@3", media)
        out = False
    except ValueError:
        out = True
    assert out, "引用没有的那张必须报错"
    print("  ✓ 编号引用：@1/@图2/[1] 三种写法 → chip，多图自动补号，越界当场报错")


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
    # 提交前那条基线没读到（None）＝不知道历史本来几条：一律不许说「多出来一条」，
    # 否则列表一渲染，上一段的旧记录就被读成「我们这段跑完了」，催 90 秒收尾报失败
    one = ('{"http":{"run":0,"pend":0,"keys":["q"]},'
           '"h":{"n":1,"last":{"id":"b","s":"success","c":true}}}')
    s = g(one).platform_state(None, "f", 300, None)
    assert "跑完" not in s and "查不到" in s, "没基线也把一条旧历史当成了这段：%r" % s
    err1 = ('{"http":{"run":0,"pend":0,"keys":["q"]},'
            '"h":{"n":1,"last":{"id":"b","s":"error"}}}')
    assert "判了失败" not in g(err1).platform_state(None, "f", 300, None), "没基线就把旧记录判成这段的失败"
    assert "判了失败" not in g(err1).platform_state(None, "f", 300, 1), "没多出一条就别判失败"
    # history_count 读到 0 条也算没基线（页面那栏还没挂起来时量到的同样是 0）
    x = cg.CloudH3(TMP, {}, None, None)
    x.js = lambda tab, script, *a: '{"h":{"n":0}}'
    assert x.history_count(None, "f") is None, "空历史该当没基线，不许拿来比新旧"
    x.js = lambda tab, script, *a: '{"h":{"n":3}}'
    assert x.history_count(None, "f") == 3

    # 任务列表那一栏：平台自己写着「生成中 04:02」「任务失败」，比队列更直接。
    # 只认提交后新冒出来的 taskid（提交前那份 known 里的旧账一律不算）。
    def gt(tasks, prog="{}"):
        x = cg.CloudH3(TMP, {}, None, None)
        x.js = lambda tab, script, *a: tasks if script == cg._JS_TASKS else prog
        return x
    live = '{"cur":[{"id":"111","s":"生成中 04:02","d":""}],"his":[]}'
    s = gt(live).platform_state(None, "f", 30, 0, known={"222"})
    assert "生成中 04:02" in s and "111" in s, "任务列表里在跑没读出来：%r" % s
    dead = '{"cur":[],"his":[{"id":"333","s":"任务失败","d":""}]}'
    s = gt(dead).platform_state(None, "f", 30, 0, known={"222"})
    assert "平台判失败" in s and "333" in s, "任务列表里的失败没读出来：%r" % s
    # 失败那条是提交前就在的旧账：不许算到这一段头上
    assert gt(dead).platform_state(None, "f", 30, 0, known={"333"}) == "", "把旧失败算成了这段的"
    # 认领到 taskid 后就只认那一条：哪怕它早就在基线里，失败也得当场收手
    dead2 = ('{"cur":[],"his":[{"id":"333","s":"任务失败",'
             '"d":"任务 333 失败：节点报错 参考图没收到"}]}')
    s = gt(dead2).platform_state(None, "f", 30, 0, known={"333"}, task_id="333")
    assert "平台判失败" in s and "参考图没收到" in s and "333" in s, s
    # 列表把计时也写出来时，状态行要带上「已运行 04:02」
    live2 = '{"cur":[{"id":"111","s":"生成中","time":"04:02","d":"生成中 取消"}]}'
    s = gt(live2).platform_state(None, "f", 30, 0, known=set(), task_id="111")
    assert "生成中" in s and "已运行 04:02" in s, s
    # 任务项里挂的「取消」按钮不能当成「已取消」
    live3 = '{"cur":[{"id":"111","s":"生成中 00:12","d":"生成中 00:12 取消"}]}'
    s = gt(live3).platform_state(None, "f", 30, 0, known=set(), task_id="111")
    assert "平台判失败" not in s and "生成中" in s, s
    # 状态元素里同时扫得到在跑和失败词：按最先出现的那个定性，在跑压过失败
    mix = '{"cur":[{"id":"111","s":"生成中 00:12 排队中 前面有任务失败","d":""}]}'
    s = gt(mix).platform_state(None, "f", 30, 0, known=set(), task_id="111")
    assert "平台判失败" not in s and "生成中 00:12" in s, s
    # 状态字读空、只有整条文本可读：从「运行模式/取消」这些噪声里认出「生成中」
    onlyd = '{"cur":[{"id":"111","s":"","d":"taskid 111 生成中 00:30 运行模式 Lite 取消"}]}'
    s = gt(onlyd).platform_state(None, "f", 30, 0, known=set(), task_id="111")
    assert "平台判失败" not in s and "生成中" in s, s
    # 「未完成」不算跑完：别拿它去催那 90 秒的收尾
    nod = '{"cur":[{"id":"111","s":"生成中 未完成","d":""}]}'
    s = gt(nod).platform_state(None, "f", 30, 0, known=set(), task_id="111")
    assert "跑完" not in s and "生成中" in s, s
    # 真机抓到的那一次：状态字写着在跑，卡片尾巴上挂着一颗「安审失败 重试」的标签
    tag = ('{"cur":[{"id":"111","s":"生成中 07:50",'
           '"d":"PlusH3工作流删除2026-11-03 12:32:07taskid: 111运行模式: Plus运行时长: 07:50安审失败 重试"}]}')
    s = gt(tag).platform_state(None, "f", 30, 0, known=set(), task_id="111")
    assert "平台判失败" not in s and "生成中 07:50" in s, "在跑的状态被卡片标签判死了：%r" % s
    # 只有整条文本可读、里面最先出现的是「安审失败」：那才是平台自己给这段的定性
    tag2 = tag.replace('"s":"生成中 07:50"', '"s":""')
    s = gt(tag2).platform_state(None, "f", 30, 0, known=set(), task_id="111")
    assert "平台判失败" in s and "taskid 111" in s, s
    assert cg._task_word("已完成 05:12") == "已完成", cg._task_word("已完成 05:12")
    assert cg._task_kind(cg._task_word("任务失败 错误")) == "fail", "两个失败词取最先那个"
    assert cg._task_kind(cg._task_word("未完成")) == "", "「未完成」既不算完成也不算失败"
    assert cg._task_kind(cg._task_word("取消")) == "", "光一颗「取消」按钮不算已取消"
    # 认领到的 taskid 这一轮没在列表里（页面正在重渲染）：说「读不到」，不许拿别的行顶账
    s = gt(live).platform_state(None, "f", 30, 0, known=set(), task_id="999")
    assert s == "", "taskid 没读到还去差集里抓了一条：%r" % s
    # 基线没读到（None）＝新旧差集不可信：列表里那条旧失败不能算到我们这段头上
    s = gt(dead).platform_state(None, "f", 30, 0, known=None, task_id="")
    assert "平台判失败" not in s, "基线不可信还拿差集判失败：%r" % s
    # 任务列表去重、按 taskid 从新到旧
    x = cg.CloudH3(TMP, {}, None, None)
    x.js = lambda tab, script, *a: (
        '{"cur":[{"id":"111","s":"生成中"}],'
        '"his":[{"id":"222","s":"任务失败"},{"id":"111","s":"生成中"}]}')
    ids = [i["id"] for i in (x.task_entries(None).get("items") or [])]
    assert ids == ["222", "111"], ids
    # 基线读不到＝None；读到但一条都没有也算 None（右侧那栏还没挂起来时量到的同样是空，
    # 分不清「真没任务」和「还没渲染」——这时候拿差集判失败，认到的多半是上一段的旧账）
    x = cg.CloudH3(TMP, {}, None, None)
    x.js = lambda tab, script, *a: ""
    assert x.known_task_ids(None) is None
    x.js = lambda tab, script, *a: '{"cur":[],"his":[]}'
    assert x.known_task_ids(None) is None

    def cap(rows, known):
        """按给定的一串列表快照跑一遍认领（sleep 免掉，只看认领规则）。"""
        x = cg.CloudH3(TMP, {}, None, None)
        seq = [{"items": r} for r in rows]
        n = {"i": 0}

        def te(tab):
            out = seq[min(n["i"], len(seq) - 1)]
            n["i"] += 1
            return out

        x.task_entries = te
        x.log = lambda *a, **k: None
        old_sleep = cg.time.sleep
        cg.time.sleep = lambda s: None
        try:
            return x.capture_task_id(None, known, limit=0.2)
        finally:
            cg.time.sleep = old_sleep
    # 提交后认领：在跑/排队的新条目认下来
    assert cap([[], [{"id": "900000000000000001", "s": "排队中"}]], None) \
        == "900000000000000001", "排队中的新任务没认领"
    # 基线不可信时只认「在跑」的那条：列表里那条旧失败不是我们这段，别认领它
    assert cap([[{"id": "800000000000000002", "s": "任务失败"}]], None) == "", \
        "把旧失败记录认领成了本段"
    # 基线可信（列表上已有别的号）：新冒出来那条哪怕一上来就读成失败，也要先见过它跑起来才认领
    assert cap([[{"id": "900000000000000003", "s": "任务失败"}]],
               {"1000000000000000001"}) == "", "只读到失败的一条不该认领"
    assert cap([[{"id": "900000000000000004", "s": "生成中"}]],
               {"1000000000000000001"}) == "900000000000000004", "在跑的那条该认下来"
    # 读到失败时 _wait_result 当场收手，不干等到超时
    x = gt(dead)
    x.poll_min = 0.01
    x.timeout = 5
    x.fail_confirm = 0
    t0 = time.time()
    try:
        x._wait_result(None, "f", "out", "base", None, None, 0, {"222"})
        raise AssertionError("失败没抛错")
    except cg.CloudError as e:
        assert "平台判失败" in str(e), str(e)
    assert time.time() - t0 < 3, "失败时还在干等"
    # 确认窗口没走完就不收手：一次读数（页面重渲染那半秒）不该重交一段还在跑的片
    x = gt(dead)
    x.poll_min = 0.01
    x.timeout = 1
    x.fail_confirm = 30
    msgs = []
    try:
        x._wait_result(None, "f", "out", "base", lambda m: msgs.append(m), None, 0, {"222"})
        raise AssertionError("超时该抛错")
    except cg.CloudError as e:
        assert "没出新片" in str(e) and "平台判失败" in str(e), str(e)
    assert any("先等" in m and "确认" in m for m in msgs), msgs
    # 窗口从配置读：cloud.fail_confirm_sec（界面不摊开，留一个能调的口子）
    assert cg.CloudH3(TMP, {"fail_confirm_sec": 40}, None, None).fail_confirm == 40
    assert cg.CloudH3(TMP, {}, None, None).fail_confirm == 15
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


def test_browser_selfheal():
    """调试窗口被叉掉后要能自己重开，而不是拿死连接一路撞「与页面的连接已断开」。

    真机那次的形状：用户关掉 Chrome → BrowserHost._b 还是旧连接 → 之后每次云端出片
    都在 tab.get / run_js 上抛 PageDisconnectedError，只能重启软件。这里用假连接钉住。
    """
    from cloudkit import gen as cg

    class Dead:
        @property
        def tabs_count(self):
            raise RuntimeError("与页面的连接已断开。")

    class Live:
        tabs_count = 1

        def __init__(self, tabs=None):
            self._tabs = [object()] if tabs is None else tabs
            self.new = 0

        @property
        def latest_tab(self):
            if not self._tabs:
                raise IndexError("no tabs")
            return self._tabs[-1]

        def new_tab(self):
            self.new += 1
            t = object()
            self._tabs.append(t)
            return t

    # 断连判定：DrissionPage 的类名与它原生文案两边都认，普通业务错不许误吞
    class PageDisconnectedError(Exception):
        pass
    assert cg.browser_gone(PageDisconnectedError("x"))
    assert cg.browser_gone(RuntimeError("与页面的连接已断开。 版本: 4.1.1.4"))
    assert cg.browser_gone(RuntimeError("浏览器已关闭或链接已断开"))
    assert not cg.browser_gone(cg.CloudError("没给工作流"))
    assert not cg.browser_gone(RuntimeError("参考图找不到：a.png"))

    host = cb.BrowserHost(ROOT, {"base": "https://example.test"})
    host._b = Dead()
    assert host.alive() is False and host._b is None      # 探活顺手丢掉死连接
    host._b = Live()
    assert host.alive() is True and host._b is not None

    # browser()：死连接不许原样返回，要重建一只（这里用假 DrissionPage 拦住真启动）
    made = []

    class FakeChromium:
        def __init__(self, opts):
            made.append(opts)
            self.tabs_count = 1

    class FakeOpts:
        def __init__(self, **kw):
            pass

        def __getattr__(self, name):
            return lambda *a, **k: None

    fake = type(sys)("DrissionPage")
    fake.Chromium, fake.ChromiumOptions = FakeChromium, FakeOpts
    old = sys.modules.get("DrissionPage")
    sys.modules["DrissionPage"] = fake
    try:
        host._b = Dead()
        b = host.browser()
        assert isinstance(b, FakeChromium) and len(made) == 1
        assert host.browser() is b and len(made) == 1     # 活着就复用，不反复起
    finally:
        if old is None:
            sys.modules.pop("DrissionPage", None)
        else:
            sys.modules["DrissionPage"] = old

    # tab()：正常拿最后一页；最后一页被关掉就补一页；两次都拿不到才报错
    host2 = cb.BrowserHost(ROOT, {"base": "https://example.test"})
    live = Live()
    host2._b = live
    assert host2.tab() is live._tabs[-1]
    empty = Live(tabs=[])
    host2._b = empty
    assert host2.tab() is empty._tabs[-1] and empty.new == 1

    class BadTabBrowser(Live):
        @property
        def latest_tab(self):
            raise RuntimeError("与页面的连接已断开")

    host2._b = BadTabBrowser()
    host2.browser = lambda: host2._b       # 拦住真实重建，只验 tab() 的两次尝试
    try:
        host2.tab()
        raise AssertionError("两次都拿不到页却没有报错")
    except RuntimeError as e:
        assert "没连上" in str(e), e

    # _enter()：进页时撞上断连 → reset 一次、重开一次；普通错原样抛
    class FakeTab:
        def __init__(self, name, fail=None):
            self.name, self.fail = name, fail

        def get(self, url):
            if self.fail:
                raise self.fail
            return "ok"

    class FakeHost:
        def __init__(self, tabs):
            self.lock = threading.RLock()
            self.purpose, self.current = "", ""
            self.tabs, self.resets, self.applies, self.i = tabs, 0, [], 0

        def apply(self, state, aid="", reload=True):
            self.applies.append(aid)
            self.current = aid

        def tab(self):
            t = self.tabs[min(self.i, len(self.tabs) - 1)]
            self.i += 1
            return t

        def reset(self):
            self.resets += 1
            self.current = ""

    h = FakeHost([FakeTab("t1", PageDisconnectedError("与页面的连接已断开")), FakeTab("t2")])
    h.purpose = "gen"
    c = cg.CloudH3(ROOT, {}, object(), h)
    assert c._enter({}, "A", "https://x", None, None).name == "t2" and h.resets == 1
    h2 = FakeHost([FakeTab("t1", ValueError("bad"))])
    try:
        cg.CloudH3(ROOT, {}, object(), h2)._enter({}, "A", "https://x", None, None)
        raise AssertionError("普通错不该被当成断连重试")
    except ValueError as e:
        assert str(e) == "bad" and h2.resets == 0
    print("  ✓ 浏览器自愈：窗口关掉后探活丢死连接、重开一次；进页撞断连也只重试一次")


def test_account_browsers():
    """一个号一只浏览器：1 号用主窗口，2 号起独立端口/profile，坏号标 fail 后跳过。"""
    from cloudkit import pool as cp
    s = _fresh()
    a = s.create("A 号")
    b = s.create("B 号")
    s.create("没登录的号")
    s.save(a["id"], _snap()["cookies"], {}, "https://www.runninghub.cn/")
    s.save(b["id"], _snap()["cookies"], {}, "https://www.runninghub.cn/")

    main = cb.BrowserHost(ROOT, {"port": 19100},
                          profile=os.path.join(TMP, "prof_main"))
    br = cp.AccountBrowsers(ROOT, {"port": 19100}, s, main)
    pool = cp.CloudPool(br)
    rows = pool.accounts()
    assert [x["id"] for x in rows] == [a["id"], b["id"]], rows   # 没快照的不进池
    assert (br.slot(a["id"]), br.slot(b["id"])) == (1, 2)
    wa, wb = pool.workers(rows)
    # 1 号就是主窗口（9333/19100），2 号分到下一只；两个号不再抢一个窗口
    assert wa.host is main and wa.host.port == 19100, wa.host.port
    assert wb.host is not main and wb.host.port == 19101, wb.host.port
    assert main.profile != wb.host.profile, (main.profile, wb.host.profile)
    assert wb.host.profile.startswith(os.path.abspath(os.environ["QIC_CLOUD_DIR"])), \
        wb.host.profile
    assert pool.worker(rows[0]) is wa, "同一个号必须复用同一只，不能重复起浏览器"
    st = br.state()
    assert [x["slot"] for x in st] == [1, 2, 3], st
    assert [x["port"] for x in st] == [19100, 19101, 19102], st
    assert st[0]["main"] and not st[1]["main"]

    pool.mark_fail(wa, "两次都没出成")
    assert wa.bad and s.get(a["id"])["state"] == "fail"
    assert [x["id"] for x in pool.accounts()] == [b["id"]], "fail 的号下次必须跳过"

    # 成片收尾只丢调度包装；账号浏览器（含 2 号那只）继续留着
    pool.close()
    assert b["id"] in br._hosts, "close() 不该把账号自己的浏览器一起收掉"

    # 删掉 1 号：2 号顺延成「浏览器 1」，原独立窗口收掉，下一次直接用主窗口
    s.delete(a["id"])
    br.reconcile()
    assert br.slot(b["id"]) == 1 and b["id"] not in br._hosts
    assert br.host_for(b["id"]) is main
    br.close_all()

    # restart：连进程一起收（force），下一次拉起新的
    h = cb.BrowserHost(ROOT, {}, port=19103, profile=os.path.join(TMP, "prof_x"))
    assert h.port == 19103 and h.profile.endswith("prof_x")

    calls = []

    class B:
        def quit(self, timeout=5, force=False):
            calls.append((timeout, force))

    h._b = B()
    h.browser = lambda: "fresh"
    assert h.restart() == "fresh" and h._b is None
    assert calls == [(5, True)], calls
    print("  ✓ 账号浏览器：1 号主窗口 / 2 号起独立端口，坏号标 fail，重启连进程一起收")


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
        test_kj_write,
        test_load_local_wf,
        test_write_selfcheck,
        test_media_item,
        test_mention,
        test_platform_state,
        test_browser_selfheal,
        test_account_browsers,
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
