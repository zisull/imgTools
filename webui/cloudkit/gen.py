# -*- coding: utf-8 -*-
"""H3 云端出片：浏览器只管「登录 + 点执行」，上传与取片走协议。

为什么是这个分工（都在 RunningHub 上实测过，见 H3yun合并方案.md §十）：
  · 站点根只把只读与上传口代理给托管 ComfyUI（GET history/object_info、POST upload/image 都通），
    POST /prompt 一律被网关挡掉（外头发回 nginx 403，页面内发回 SPA 首页）——
    提交这件事没有公开可复现的协议口，只能点页面上那颗执行按钮；
  · 成片的 cos_url 是公开 TOS 地址，下载不需要 cookie，所以取片这段完全不碰浏览器。

写节点也有讲究：提示词不是普通控件。graphToPrompt() 在序列化前会用
node.__h3Editor 的内容覆盖 widgets[prompt].value，所以直接改控件是白改，
必须写编辑器；文本里的 `<Picture N>` 会被换成 __MINIMAX_H3_REF_N__，
这一条也是实测过的（改成 TEST_A <Picture 2> TEST_B，提交体就成了 …_REF_2__…）。

所有值都从「用户已登录的那份工作流」里读，不预设节点 id：
主节点按 class_type 找 FeiHouEasyH3RH，输出节点按 VHS_VideoCombine 找。
"""
import json
import os
import re
import time

WF_URL = "https://www.runninghub.cn/workflow/%s"
MAIN_TYPE = "FeiHouEasyH3RH"
OUT_TYPE = "VHS_VideoCombine"
MODE_I2V = "I2V or First/Last Frame"
MODE_REF = "Reference-to-video"
# 云端只放开这三档画幅：界面上横/方/竖已经是全集，其它画幅留给「自定义宽高」
RATIO_BY_ORIENT = {"h": "16:9", "s": "1:1", "v": "9:16"}
TIERS = [360, 416, 480, 540, 640, 720, 768, 832, 928, 1024, 1080]


class CloudError(RuntimeError):
    """云端这条路上能用人话说清的失败：账号没登录、工作流打不开、提交被拒。"""


# ---------- 页面脚本 ----------
_JS_FRAME = """
var sels=['iframe.comfyUI-iframe',"iframe[src*='comfyUI.html']","iframe[id^='iframe']","iframe"];
for(var i=0;i<sels.length;i++){
  var f=document.querySelector(sels[i]);
  if(f&&(f.id||f.name))return f.id||f.name;
}
return '';
"""
# 图好了没有：节点数 + 主/输出节点的 id（按 class_type 认，不认死编号）
_JS_READY = """
var f=document.getElementById(arguments[0]);
if(!f||!f.contentWindow)return JSON.stringify({err:'no_frame'});
var n=((f.contentWindow.app||{}).graph||{})._nodes||[];
var main=0,out=0;
n.forEach(function(x){
  if(x.type==='FeiHouEasyH3RH')main=x.id;
  else if(x.type==='VHS_VideoCombine')out=x.id;
});
return JSON.stringify({nodes:n.length,main:main,out:out});
"""
# 本地工作流文件这条路：真机量过托管前端确实有 app.loadGraphData（探针 --dump/--load 往返
# 过一次：导出 65605 字节、灌回去 23 个节点、主节点 389 与输出节点 325 都按类型认得）。
# 只改内存里那张图——不点保存、不提交、不扣积分。
_JS_LOAD_WF = """
var fid=arguments[0],txt=arguments[1];
var f=document.getElementById(fid);
if(!f||!f.contentWindow)return JSON.stringify({err:'no_frame'});
var a=f.contentWindow.app;
if(!a||typeof a.loadGraphData!=='function')return JSON.stringify({err:'这份前端没有 loadGraphData 的口'});
var g;try{g=JSON.parse(txt);}catch(e){return JSON.stringify({err:'不是 JSON：'+(e&&e.message)});}
if(!g||!g.nodes)return JSON.stringify({err:'JSON 里没有 nodes'});
try{a.loadGraphData(g,true,false,'local.json');}
catch(e){return JSON.stringify({err:'loadGraphData 报错：'+(e&&e.message)});}
return JSON.stringify({ok:1,nodes:((a.graph||{})._nodes||[]).length});
"""
# 写之前先看一眼：主节点现在的控件名与值、媒体那一份的真实形状（拿它当模板）
_JS_INSPECT = """
var f=document.getElementById(arguments[0]);
var node=f.contentWindow.app.graph.getNodeById(arguments[1]);
if(!node)return JSON.stringify({err:'no_node'});
var w={};(node.widgets||[]).forEach(function(x){w[x.name]=String(x.value===undefined?'':x.value).slice(0,120);});
var m=null;try{m=node.properties.feihou_h3_embedded_media;}catch(e){}
if(typeof m==='string'){try{m=JSON.parse(m);}catch(e){m=null;}}
return JSON.stringify({type:node.type,editor:!!node.__h3Editor,widgets:w,
  media:(m&&m.length)?Object.keys(m[0]):[],media0:(m&&m[0])?m[0]:null});
"""
# 一次写完：普通控件 + 提示词编辑器 + 媒体属性；顺手做自检，不合格就别点运行
_JS_WRITE = """
var fid=arguments[0],nid=arguments[1],spec=JSON.parse(arguments[2]);
var w=document.getElementById(fid).contentWindow, g=w.app.graph;
var node=g.getNodeById(nid);
if(!node)return JSON.stringify({err:'no_node'});
var by={};(node.widgets||[]).forEach(function(x){by[x.name]=x;});
function setv(k,v){var x=by[k];if(!x)return 'no:'+k;
  if(x.type==='combo'||x.options&&x.options.values){
    if(x.options.values.indexOf(v)<0)return 'opt:'+k+':'+v;
    if(x.setOption)x.setOption(v);else x.value=v;
  }else x.value=v;
  x.value=v;g.setNodeDirty?g.setNodeDirty(node):0;return '';}
var bad=[];
Object.keys(spec.widgets||{}).forEach(function(k){var r=setv(k,spec.widgets[k]);if(r)bad.push(r);});
// 媒体：形状照线上那一条抄，值换成我们刚上传的文件
var media=spec.media||[];
try{node.properties.feihou_h3_embedded_media=JSON.stringify(media);}catch(e){bad.push('prop_media');}
if(by.embedded_media_json)by.embedded_media_json.value=JSON.stringify(media);
// 提示词：编辑器是真源，控件是它的副本——只改控件等于没改
var text=spec.prompt||'';
var ed=node.__h3Editor;
if(ed){ed.textContent=text;
  try{ed.dispatchEvent(new InputEvent('input',{bubbles:true}));}catch(e){}
}else if(by.prompt){by.prompt.value=text;}else bad.push('no_prompt_slot');
g.setDirtyCanvas&&g.setDirtyCanvas(true,true);
// 自检：拿即将提交的序列化结果比对，不合规就报出来，宁可停下也不出废片
// 新版 ComfyUI 的 graphToPrompt() 回的是 Promise：不 then 就取到 undefined，
// 于是每一项都「没值」→ 检查全过 → 这条防线形同不存在（实测过：直接 .output 读回来是空的）。
function chkOf(inp){
  inp=inp||{};
  var nm=0;Object.keys(inp).forEach(function(k){if(/^media_\\d+$/.test(k)&&inp[k])nm++;});
  return {prompt:String(inp.prompt||'').slice(0,80),seconds:inp.seconds,fps:inp.fps,
          mode:inp.mode,resolution:inp.resolution,aspect:inp.aspect_ratio,
          width:inp.width,height:inp.height,
          media:inp.embedded_media_json?JSON.parse(inp.embedded_media_json).length:0,
          slots:nm};
}
function pack(chk){return JSON.stringify({bad:bad,check:chk,editor:!!ed});}
var p=null;
try{
  p=(w.app.graphToPrompt&&w.app.graphToPrompt())||(w.graphToPrompt&&w.graphToPrompt());
}catch(e){return pack({err:String(e&&e.message||e).slice(0,100)});}
if(p&&p.then){
  return p.then(function(o){
    return pack(chkOf((o&&o.output&&o.output[String(nid)]||{}).inputs));
  },function(e){return pack({err:String(e&&e.message||e).slice(0,100)});});
}
return pack(chkOf((p&&p.output&&p.output[String(nid)]||{}).inputs));
"""
# 输出节点：文件名 + 公开下载地址
_JS_RESULT = """
var f=document.getElementById(arguments[0]);
var node=f.contentWindow.app.graph.getNodeById(arguments[1]);
if(!node)return JSON.stringify({err:'no_node'});
var o={};
(node.widgets||[]).forEach(function(x){
  if(x.name==='videopreview'&&x.value&&x.value.params){
    o.filename=x.value.params.filename||'';
    o.cos_url=x.value.params.cos_url||x.value.params.subfolder||'';
    o.full=x.value.params.fullpath||'';
  }});
return JSON.stringify(o);
"""
# 顶层页的运行按钮：三档（Lite/Standard、Lite/Plus、Ultra），H3yun 用的是 Plus 那颗
_JS_EXEC = """
var tag=arguments[0];
var bs=[].slice.call(document.querySelectorAll('.execute-btn-wrap button'));
if(!bs.length)return 'no_btn';
var hit=null;
bs.forEach(function(b){
  var t=(b.querySelector('.plus-tags')||{}).textContent||'';
  if(!hit&&tag&&t.indexOf(tag)>=0)hit=b;
});
hit=hit||bs[0];
var lab=(hit.textContent||'').trim().slice(0,40);
hit.click();
return 'clicked '+lab;
"""
_JS_EXEC_STATE = """
var bs=[].slice.call(document.querySelectorAll('.execute-btn-wrap button'));
return bs.length?((bs[0].textContent||'').trim().slice(0,24)):'gone';
"""
# 平台到底跑到哪一步了：以页面内存里的 app.queue / app.queueItems 为主（它由 WebSocket
# 推送维护，和人在平台上看到的口径一致），只读的 GET /queue、GET /history 当备份——
# 真机两种形状都量到过：新开的工作流页里 app.queue 是 null，跑起来的会话里它一直在。
# fetch 返回 Promise 没关系：这版 DrissionPage 的 run_js 固定 awaitPromise=True。
# 只读，不提交、不动队列、不扣积分。
# 为什么值得读：出片时间波动很大（实测同参数一段 353 秒出、一段排到 30 分钟没动），
# 只报「已等 N 秒」分不清排队/在跑/已失败，人只能干等或盲点停止。
_JS_PROGRESS = """
var fid=arguments[0];
var f=document.getElementById(fid),o={};
if(!f||!f.contentWindow)return JSON.stringify({err:'no_frame'});
var w=f.contentWindow;
/* 两版前端叫法不同：老版 queue_running/queue_pending，新版 running/queued。
   只认一种就会永远读成 0/0，然后把「读不到」说成「队列空了」。 */
function lens(q){return q?{run:((q.queue_running||q.running)||[]).length,
                           pend:((q.queue_pending||q.queued)||[]).length,
                           keys:Object.keys(q).slice(0,10)}:null;}
o.mem=lens(w.app&&w.app.queue);
/* 这份新版前端没有 app.queue，队列在 app.queueItems（实测是个数组）。
   它不区分跑着/排着，所以只敢说「有 N 个在平台上」，不敢说「正在跑」。 */
o.items=(w.app&&Array.isArray(w.app.queueItems))?{n:w.app.queueItems.length}:null;
var bs=[].slice.call(document.querySelectorAll('.execute-btn-wrap button'));
if(bs.length)o.btn=(bs[0].textContent||'').trim().slice(0,20);
var A=w.comfyAPI&&w.comfyAPI.api&&w.comfyAPI.api.api;
if(!A)return JSON.stringify(o);
function url(ep){var u=A.apiURL?A.apiURL(ep):'';
  return u&&u.indexOf('http')===0?u:w.location.origin+(u[0]==='/'?u:'/'+u);}
function get(ep){return fetch(url(ep),{credentials:'include'})
  .then(function(r){return r.status===200?r.text():'';})
  .catch(function(){return '';});}
return Promise.all([get('queue'),get('history')]).then(function(rs){
  try{o.http=lens(JSON.parse(rs[0]));}catch(e){}
  /* 历史读整份、不读 /history/{fid}：那个参数是界面里 iframe 的 DOM id，
     不是任务的 prompt id（实测 _JS_RESULT 用的 fid 就是 getElementById 的那个），
     拼进去永远查不到东西，还会把「查不到」说成「没跑成」。 */
  try{var h=JSON.parse(rs[1])||{},ids=Object.keys(h),one=ids.length?(h[ids[ids.length-1]]||{}):{};
    var st=one.status||{};
    o.h={n:ids.length,last:ids.length?{id:String(ids[ids.length-1]).slice(0,12),
        s:String(st.status_str||''),c:!!st.completed}:null};}
  catch(e){}
  return JSON.stringify(o);});
"""


def pick_size(w, h):
    """把界面的 WxH 翻成云端那四件套：档位标签 + 画幅 + 宽 + 高。

    线上实测（scripts/h3_cloud_probe.py --size）：改 resolution / aspect_ratio 之后，
    序列化里的 width/height 一动不动——那两颗档位控件只是标签，真出片按 width/height 走
    （实测提交 848×480，回来的文件就是 848×480）。所以宽高我们自己算、自己写，
    档位只按界面口径（P=短边）标一个名，凑不出的就写 Custom，不猜平台的公式。
    """
    # 与 App._snap16、界面 C.a16 同一套四舍五入（Python 的 round 是 .5 向偶数，会差 16）。
    # 上限 2560：云端出片尺寸由我们写进 width/height，官方最高 2K＝短边 1440（长边 2560）。
    a16 = lambda x: max(16, min(2560, int(float(x) / 16.0 + 0.5) * 16))
    w, h = a16(w), a16(h)
    short = min(w, h)
    tier = min(TIERS, key=lambda t: abs(t - short))
    orient = "s" if w == h else ("h" if w > h else "v")
    return {"resolution": "%dP" % tier if tier == short else "Custom",
            "aspect_ratio": RATIO_BY_ORIENT[orient], "width": w, "height": h}


class CloudH3:
    """一次一段：upload → 写节点 → 点运行 → 轮询 → 下载。

    host/store 由 App 那份 _cloudkit 传进来，别在这里自己开浏览器：
    共用一只调试浏览器是多账号能跑起来的前提。
    """

    def __init__(self, root, cfg, store, host, log=None):
        self.root = root
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self.store = store
        self.host = host
        self.log = log or (lambda *_: None)
        self.poll_min = max(2, int(self.cfg.get("poll_sec") or 5))
        self.timeout = max(60, int(self.cfg.get("gen_timeout") or 1800))
        self.tag = str(self.cfg.get("exec_tag") or "Plus")
        self.media_tpl = None
        self.has_editor = False
        self.wf_title = ""

    # ---------- 账号与工作流 ----------
    def account(self, aid=""):
        rows = [a for a in self.store.list() if (self.store.load(a["id"]) or {}).get("cookies")]
        if not rows:
            raise CloudError("还没有可用的登录账号：到「H3云端」页新建登录并保存")
        if aid:
            for a in rows:
                if a["id"] == aid:
                    return a
            raise CloudError("这个账号还没有保存过登录态")
        return rows[0]

    def wf_id(self, wf=""):
        s = str(wf or self.cfg.get("workflow") or self.cfg.get("wf") or "").strip()
        m = re.search(r"workflow/(\d+)", s)
        if m:
            return m.group(1)
        if s.isdigit():
            return s
        return str(self.cfg.get("default_wf") or "")

    def wf_url(self, wf=""):
        wid = self.wf_id(wf)
        if not wid:
            raise CloudError("没给工作流：在「H3云端」页填一个已跑通过的 H3 工作流地址")
        return WF_URL % wid

    def wf_src(self, wf=""):
        """这份工作流从哪儿来：("file", 本地路径) 或 ("remote", 平台编号)，都没给就 ("", "")。

        判据只认结尾是不是 .json/.txt——平台上「导出工作流」存下来就是这份；
        导出的 JSON 里不带工作流编号（实测只有一个随机 uuid），所以本地那份
        还得借一个平台页进去跑，见 host_url。
        """
        s = str(wf or self.cfg.get("workflow") or self.cfg.get("wf") or "").strip()
        if not s:
            return ("", "")
        if re.search(r"\.json$|\.txt$", s, re.I):
            path = self._ref(s)
            if not path:
                raise CloudError("本地工作流文件找不到：%s" % s[:80])
            return ("file", path)
        return ("remote", s)

    def host_url(self):
        """本地那份借哪一页进去：托管 ComfyUI 只能从某个平台工作流页打开。

        换的是画布上那张图，跑它的还是那台实例——「换图不换实例」。
        """
        for cand in (self.cfg.get("wf_host"), self.cfg.get("default_wf")):
            s = str(cand or "").strip()
            m = re.search(r"workflow/(\d+)", s)
            wid = m.group(1) if m else (s if s.isdigit() else "")
            if wid:
                return WF_URL % wid
        raise CloudError("本地那份工作流要知道用哪一页跑：再填一个平台上打得开的工作流地址（宿主页）")

    # ---------- 灌本地工作流 ----------
    def load_local_wf(self, tab, fid, path, stop, limit=30):
        """把本地 JSON 灌进页面，再按类型重新认主节点/输出节点（那张图的 id 未必是 389）。"""
        from .store import brief_error
        try:
            if os.path.getsize(path) > 8 * 1048576:
                raise CloudError("这份文件超过 8MB，不像工作流 JSON")
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                txt = f.read()
        except CloudError:
            raise
        except Exception as e:
            raise CloudError("本地工作流文件读不了：%s" % brief_error(e, 80))
        try:
            g = json.loads(txt)
        except ValueError:
            raise CloudError("本地那份不是 JSON：用平台「导出工作流」存下来的那一份")
        if not (isinstance(g, dict) and (g.get("nodes") or [])):
            raise CloudError("这份 JSON 里没有画布：要平台「导出工作流」存下来的那种（带 nodes）——"
                             "不是 API 格式、也不是节点清单")
        try:
            d = json.loads(self.js(tab, _JS_LOAD_WF, fid, txt) or "{}")
        except ValueError:
            d = {"err": "页面没回话"}
        except Exception as e:
            d = {"err": brief_error(e, 80)}
        if d.get("err"):
            raise CloudError("灌不进那张图：%s" % d["err"])
        try:
            ids = self._wait_graph(tab, fid, stop, limit=limit)
        except CloudError as e:
            raise CloudError("本地那份工作流没那张图要的东西：%s" % str(e)[-60:])
        self.wf_title = "本地 · %s" % os.path.basename(path)
        self.log("· 灌入本地工作流「%s」：节点 %s 个 · 主节点 %s · 输出节点 %s"
                 % (os.path.basename(path), d.get("nodes"), ids["main"], ids["out"]))
        return ids

    def js(self, tab, script, *args):
        return tab.run_js(script, *args)

    # ---------- 上传（协议侧，不碰页面） ----------
    def upload(self, path, state):
        """把本地参考图传到那台托管 ComfyUI 的 input 里，回 (name, subfolder)。

        认证值由快照派生拼在 query 上；上传是这台实例唯一真的开放 API，
        提交不是——所以只有这一段值得绕开浏览器。
        """
        import requests
        from .store import auth_headers, brief_error
        if not os.path.isfile(path):
            raise CloudError("参考图找不到：%s" % os.path.basename(path))
        hdrs = auth_headers(state.get("cookies"), state.get("storage"))
        if not hdrs.get("Rh-Comfy-Auth") or not hdrs.get("Rh-Identify"):
            raise CloudError("这份登录快照里没有 ComfyUI 的鉴权值：重新保存一次登录态")
        q = "&".join("%s=%s" % (k, hdrs[k]) for k in ("Rh-Comfy-Auth", "Rh-Identify"))
        url = "%s/upload/image?%s" % (self.host.base.rstrip("/"), q)
        cookie = "; ".join("%s=%s" % (c.get("name"), c.get("value"))
                           for c in (state.get("cookies") or []) if c.get("name"))
        name = os.path.basename(path)
        last = ""
        for _ in range(3):                     # 平台偶发 5xx，重试三次再放弃
            try:
                with open(path, "rb") as f:
                    r = requests.post(url, headers={"Cookie": cookie},
                                      files={"image": (name, f, "application/octet-stream")},
                                      data={"type": "input"}, timeout=60)
                if r.status_code == 200:
                    d = r.json() if isinstance(r.text, str) else {}
                    fn = str((d or {}).get("name") or "")
                    if fn:
                        return fn, str((d or {}).get("subfolder") or "")
                    last = "没回文件名"
                else:
                    last = "HTTP %s" % r.status_code
            except Exception as e:
                # requests 的异常串会原样带上它正在打的 URL——那条 query 里就是鉴权值，
                # 所以走 store 那句现成的：压成一行、长令牌截半，别把凭据抄进日志和状态行
                last = brief_error(e, 160)
            time.sleep(3)
        raise CloudError("参考图上传失败：%s" % last)

    # ---------- 主流程 ----------
    def run(self, p, on_progress=None, should_stop=None):
        """p：{prompt, seconds, width, height, first, wf, acct}；回本地 mp4 路径。

        顺序是「开页 → 抄形状 → 传图 → 写节点 → 提交 → 轮询 → 下载」：
        先开页是因为媒体条目的字段形状要从线上那一条抄，抄完才谈得上写。
        """
        row = self.account(p.get("acct"))
        aid = row["id"]
        state = self.store.load(aid)
        kind, src = self.wf_src(p.get("wf"))
        url = self.host_url() if kind == "file" else self.wf_url(src)
        secs = max(5, min(15, int(p.get("seconds") or 5)))
        size = pick_size(int(p.get("width") or 768), int(p.get("height") or 768))
        first = self._ref(str(p.get("first") or ""))
        with self.host.lock:
            self.host.purpose = "gen"            # 这段期间保活别换号，否则中途掉登录
            try:
                tab = self.host.tab()
                tab.get(url)
                fid = self._wait_frame(tab, should_stop)
                if kind == "file":
                    # 平台上那张图只是张跳板：进去之后立刻换成用户本地这一份
                    self._p(on_progress, should_stop, "云端：灌入本地工作流…")
                    ids = self.load_local_wf(tab, fid, src, should_stop)
                else:
                    ids = self._wait_graph(tab, fid, should_stop)
                self._log_shape(tab, fid, ids["main"])
                media = []
                if first:
                    self._p(on_progress, should_stop, "云端：上传参考图…")
                    fn, sub = self.upload(first, state)
                    media = [self.media_item(fn, sub)]
                spec = {
                    "prompt": str(p.get("prompt") or ""),
                    "media": media,
                    "widgets": {
                        "mode": MODE_I2V if media else MODE_REF,
                        "seconds": secs,
                        "fps": 24,
                        "audio_duration_auto": "Off",
                        "reference_text_only": not bool(media),
                        "resolution": size["resolution"],
                        "aspect_ratio": size["aspect_ratio"],
                        "width": size["width"],
                        "height": size["height"],
                    },
                }
                self._p(on_progress, should_stop, "云端：写入参数…")
                self._write(tab, fid, ids, spec, secs, size, bool(media))
                base_name = self._filename(tab, fid, ids["out"])
                self._p(on_progress, should_stop, "云端：提交任务…")
                hist0 = self.history_count(tab, fid)   # 提交前有几条，之后才知道多没多
                self._submit(tab)
                cos, fname = self._wait_result(tab, fid, ids["out"], base_name,
                                               on_progress, should_stop, hist0)
            finally:
                self.host.purpose = ""
        self._p(on_progress, should_stop, "云端：下载成片…")
        return self._download(cos, fname, p.get("out_dir") or "")

    def _ref(self, p):
        """参考图路径：配置里存的是相对整合包的写法，先折成绝对路径再判存在。"""
        p = str(p or "").replace("file:///", "").replace("file://", "")
        p = os.path.normpath(p if os.path.isabs(p) else os.path.join(self.root, p))
        return p if os.path.isfile(p) else ""

    def _p(self, cb, stop, msg):
        if stop and stop():
            raise CloudError("已停止：这一段没提交/没取回")
        if cb:
            try:
                cb(msg)
            except Exception:
                pass

    def _wait_frame(self, tab, stop, limit=60):
        t0 = time.time()
        while time.time() - t0 < limit:
            if stop and stop():
                raise CloudError("已停止")
            fid = str(self.js(tab, _JS_FRAME) or "")
            if fid:
                return fid
            time.sleep(2)
        raise CloudError("工作流页没出 ComfyUI 画布：链接对不对、这个号有没有这份图")

    def _wait_graph(self, tab, fid, stop, limit=120):
        t0 = time.time()
        while time.time() - t0 < limit:
            if stop and stop():
                raise CloudError("已停止")
            try:
                d = json.loads(self.js(tab, _JS_READY, fid) or "{}")
            except ValueError:
                d = {}
            if d.get("main") and d.get("out"):
                self.wf_title = str(getattr(tab, "title", "") or "")
                return {"main": d["main"], "out": d["out"]}
            time.sleep(3)
        raise CloudError("图加载完但没找到 H3 主节点/输出节点：这份工作流不是 H3 成片图")

    def _log_shape(self, tab, fid, main):
        """把线上媒体条目的字段抄下来当模板：缺 key 的写法会被 ensureEmbeddedMedia 丢掉。

        storage/audio_trim 这些键的取值是平台自己的约定，不猜——
        那份工作流里既然已经有一条媒体，就照它那一条的形状填新值。
        """
        try:
            d = json.loads(self.js(tab, _JS_INSPECT, fid, main) or "{}")
        except ValueError:
            d = {}
        if d.get("err"):
            raise CloudError("读不到主节点：%s" % d["err"])
        self.media_tpl = d.get("media0") if isinstance(d.get("media0"), dict) else None
        self.has_editor = bool(d.get("editor"))
        return d

    def media_item(self, name, sub):
        """一条媒体引用：有模板就抄模板换文件名，没有就按线上常见形状给最小的一份。"""
        item = dict(self.media_tpl or {"media_type": "image", "ordinal": 1,
                                       "filename": "", "subfolder": "",
                                       "storage": "comfyui", "audio_trim": "00:00-00:00"})
        item.update({"media_type": "image", "ordinal": 1, "filename": name,
                     "subfolder": sub})
        return item

    def _write(self, tab, fid, ids, spec, secs, size, has_media):
        raw = self.js(tab, _JS_WRITE, fid, ids["main"], json.dumps(spec, ensure_ascii=False))
        try:
            d = json.loads(raw or "{}")
        except ValueError:
            raise CloudError("写入节点的返回读不懂：%s" % str(raw)[:160])
        if d.get("err"):
            raise CloudError("写入主节点失败：%s" % d["err"])
        bad = list(d.get("bad") or [])
        c = d.get("check") or {}
        want_slots = 1 if has_media else 0
        # 「读不到」不能算过关：以前这里每一项都写成 `not in (None, 期望值)`，
        # 于是自检只要整体失灵就全绿——而它确实失灵过一次（graphToPrompt 回的是 Promise）。
        if c.get("err") or c.get("mode") is None:
            raise CloudError("提交前自检读不到序列化结果（%s）：不敢盲提交"
                             % str(c.get("err") or "序列化里没值")[:80])
        # 线上实测：mode 控件「I2V or First/Last Frame」序列化后是 image，
        # 「Reference-to-video」是 reference，所以有参考图走前者
        want_mode = "image" if has_media else "reference"
        if c.get("mode") != want_mode:
            bad.append("mode=%s" % c.get("mode"))
        if c.get("fps") not in (24, 24.0):
            bad.append("fps=%s（必须是 24，否则出的是 1 帧秒的片）" % c.get("fps"))
        if c.get("seconds") not in (secs, float(secs)):
            bad.append("seconds=%s" % c.get("seconds"))
        if c.get("resolution") != size["resolution"]:
            bad.append("resolution=%s" % c.get("resolution"))
        if int(c.get("media") or 0) != want_slots:
            bad.append("media=%s" % c.get("media"))
        # 序列化里还留着 media_1…media_6 那几颗隐藏控件（节点自己按媒体列表灌的）。
        # 只换 embedded_media_json 而它们没跟着清，就会拿上一份工作流的图当参考出片
        if int(c.get("slots") if c.get("slots") is not None else 0) != want_slots:
            bad.append("参考图槽位 %s 个（只该 %s 个）：平台上的旧图没换干净"
                       % (c.get("slots"), want_slots))
        # 提示词这一条最要紧：编辑器没写进去的话，交上去的还是这份工作流原来那段话，
        # 钱照扣、出的却是别人的片子——所以只认序列化里真出现了我们那句
        want_text = str(spec.get("prompt") or "").strip()
        got_text = str(c.get("prompt") or "").strip()
        if want_text and want_text[:24] not in got_text:
            bad.append("提示词没进去（序列化里开头是「%s」）" % got_text[:24])
        if bad:
            raise CloudError("提交前自检没过：%s" % "、".join(str(x)[:60] for x in bad[:6]))
        # 宽高只提醒不拦：真机量到的是「写进去就原样留着」，万一哪天节点自己又算了一遍，
        # 也只能照实说一声——拦下来等于这一段白等，还可能已经扣了积分
        for k in ("width", "height"):
            if c.get(k) not in (None, size[k]):
                self.log("· 平台读回的 %s=%s，我们写的是 %s：这一段出片尺寸会和界面不一样"
                         % (k, c.get(k), size[k]))
        if not d.get("editor"):
            self.log("· 提示词写进了控件而不是编辑器：这份云上没渲染出编辑器，可能被 graphToPrompt 覆盖")
        return d

    def _filename(self, tab, fid, out):
        try:
            return str(json.loads(self.js(tab, _JS_RESULT, fid, out) or "{}").get("filename") or "")
        except ValueError:
            return ""

    def _submit(self, tab):
        r = str(self.js(tab, _JS_EXEC, self.tag) or "")
        if r.startswith("no_btn"):
            raise CloudError("页面上找不到运行按钮：这份工作流可能没权限跑，或页面还没加载完")
        return r

    def history_count(self, tab, fid):
        """平台上现在有几条历史——提交前后各读一次，多出来的那条才是我们这段。
        读不到回 0（宁可说「查不到」，也不把旧的一条当成新的）。"""
        try:
            raw = self.js(tab, _JS_PROGRESS, fid)
            d = json.loads(raw) if raw else {}
            return int((d.get("h") or {}).get("n") or 0)
        except Exception:
            return 0

    def platform_state(self, tab, fid, waited, hist0=0):
        """平台上这一段到底到哪一步了——一句话，读不到就回空串（绝不编一个）。

        时间波动很大（实测同参数一段 353 秒出片、一段排到二十分钟没动），
        只报「已等 N 秒」人分不清排队/在跑/已失败，所以去问平台自己：
        页面内存里那份队列看排没排、GET /history 的条数看这条落没落。
        hist0 = 提交那一刻的历史条数，用来认出「刚多出来的那一条」是不是我们这段。
        """
        try:
            raw = self.js(tab, _JS_PROGRESS, fid)
            if not raw:
                return ""            # 脚本没回东西＝没读到，别把「不知道」说成「队列空了」
            d = json.loads(raw)
        except ValueError:
            return ""
        except Exception:
            return ""
        if d.get("err"):
            return ""
        btn = " · 按钮「%s」" % d["btn"] if d.get("btn") else ""
        h = d.get("h") or {}
        last = h.get("last") or {}
        new = (h.get("n") or 0) > int(hist0 or 0)     # 提交后又落了一条＝这条是我们那段
        # 谁真读到用谁，且**内存那份优先**：它是页面自己按 WebSocket 推送维护的，
        # 界面那颗按钮变不变字都看它——和人在平台上看到的口径一致。
        # GET /queue 只当备份（真机两种都见过：新开的页面 app.queue 是 null，
        # 跑起来的会话里它反倒一直在）。两边都说空，才轮到「查不到」那句。
        q = next((x for x in (d.get("mem"), d.get("http")) if x), None)
        if q:
            if int(q.get("run") or 0):
                return "平台正在跑这一段"
            if int(q.get("pend") or 0):
                return "云端排队中 · 前面 %d 个" % int(q.get("pend") or 0)
        else:
            # 队列对象一个都没读到，只有那个不区分跑着/排着的数组：
            # 就说「平台上有 N 个任务」，不编成「正在跑」。
            n = int((d.get("items") or {}).get("n") or 0)
            if n:
                return "平台上有 %d 个任务（排队或在跑）" % n
        if new and str(last.get("s") or "") == "error":
            return "平台把这段判了失败：去云端页看原因" + btn
        # 「队列空了」是一句有分量的话：只有真读到过那个队列对象才可以说。
        # keys 是对象自己的字段名——读回来个空壳（{}），形状和「空队列」一模一样，
        # 但那是不知情，不是空。
        if q and q.get("keys") and waited > 60:
            if new and last.get("c"):
                return "平台说这段跑完了，可输出节点还没刷新：去云端页看一眼" + btn
            if new:
                return "平台已经收下这段，还在它那边跑" + btn
            # 队列里没它、历史里也没多出来：平台上看不见这段任务。
            # 说「队列已空」太像「已经失败了」，实测提交后头几分钟就是这个状态，
            # 说「查不到、可能在它自己的池子里排队」才是当时能给出的最大信息量。
            return "平台上查不到这段任务" + btn + "：可能在它自己的池子里排队"
        return ""

    def _wait_result(self, tab, fid, out, base_name, cb, stop, hist0=0):
        t0 = time.time()
        seen = ""
        where = ""
        while time.time() - t0 < self.timeout:
            if stop and stop():
                raise CloudError("已停止：云端那半段还在跑，下次进来能在平台上看到")
            time.sleep(self.poll_min)
            try:
                d = json.loads(self.js(tab, _JS_RESULT, fid, out) or "{}")
            except ValueError:
                continue
            fname = str(d.get("filename") or "")
            if fname and fname != base_name:
                cos = str(d.get("cos_url") or "")
                if cos.startswith("http"):
                    return cos, fname or "h3_cloud.mp4"
                seen = "没回公开地址"
            else:
                # 这句只针对「刚看到的那个新文件名」：输出节点一清掉，
                # 继续挂着就成了一句没根据的抱怨
                seen = ""
            where = self.platform_state(tab, fid, int(time.time() - t0), hist0)
            if cb:
                waited = int(time.time() - t0)
                left = int(self.timeout - waited)
                cb(" · ".join(x for x in ("云端出片中…已等 %d 秒（剩 %d 秒超时）"
                                          % (waited, max(0, left)), where, seen) if x))
        # 收尾那句得带上「我们到底看见了什么」：只说「等超时」等于没交代，
        # 而平台上查不到这段＝多半根本没提交成功，是另一件事。
        return self._timeout_err(where, seen)

    def _timeout_err(self, where, seen):
        hint = ""
        if "查不到" in (where or ""):
            # 实测这段并不等于「没提交上」：同参数的第一段 353 秒出了片，
            # 而这一路读到的队列同样是空的——平台真正的排队不在这个页面里。
            hint = "（这段排在平台自己的池子里，这个页面看不到它到哪一步）"
        elif "排队" in (where or ""):
            hint = "（一直在平台队列里排着：前面还有别人）"
        elif "跑完" in (where or ""):
            hint = "（平台说跑完了，是取回来的这一步没接上）"
        raise CloudError("等到 %d 秒也没出新片：%s%s"
                         % (self.timeout, where or "没读到平台状态", hint))

    def _download(self, cos, fname, out_dir):
        """cos_url 是公开地址，不需要 cookie；临时文件要尽快落地，别等平台清。"""
        import requests
        out_dir = out_dir or os.path.join(self.root, "outputs")
        os.makedirs(out_dir, exist_ok=True)
        ext = os.path.splitext(str(fname).split("?")[0])[1] or ".mp4"
        path = os.path.join(out_dir, time.strftime("h3c_%Y%m%d-%H%M%S") + ext)
        with requests.get(cos, stream=True, timeout=180) as r:
            if r.status_code != 200:
                raise CloudError("成片下载失败：HTTP %s" % r.status_code)
            with open(path, "wb") as f:
                for chunk in r.iter_content(1024 * 256):
                    if chunk:
                        f.write(chunk)
        if os.path.getsize(path) < 4096:
            raise CloudError("下载回来的文件太小（%d 字节），不像一段片子" % os.path.getsize(path))
        return path
