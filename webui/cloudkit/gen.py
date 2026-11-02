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
# 本地导出的画布没有平台编号；借平台上的某一页进实例（换图不换实例）。
# 这一页只是入口，跑的还是灌进去的那张图——和 H3yun 内置的宿主页同一个。
HOST_WF_FALLBACK = WF_URL % "2103759530927673346"
MAIN_TYPE = "FeiHouEasyH3RH"
OUT_TYPE = "VHS_VideoCombine"
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
# 自动找宿主页那套（列表页点卡片 → 作品页 → 运行）依赖平台 SPA 的路由，
# 实测客户端跳转偶尔只落空壳、按钮不挂出来——不如内置一页稳，整段去掉。
# 写之前先看一眼：主节点现在的控件名与值、媒体那一份的真实形状（拿它当模板）
_JS_INSPECT = """
var f=document.getElementById(arguments[0]);
var node=f.contentWindow.app.graph.getNodeById(arguments[1]);
if(!node)return JSON.stringify({err:'no_node'});
var w={};(node.widgets||[]).forEach(function(x){w[x.name]=String(x.value===undefined?'':x.value).slice(0,120);});
var mo=[];try{(node.widgets||[]).forEach(function(x){
  if(x.name==='mode'&&x.options&&x.options.values)mo=x.options.values.slice(0,8);});}catch(e){}
var m=null;try{m=node.properties.feihou_h3_embedded_media;}catch(e){}
if(typeof m==='string'){try{m=JSON.parse(m);}catch(e){m=null;}}
return JSON.stringify({type:node.type,editor:!!node.__h3Editor,widgets:w,modeOpts:mo,
  media:(m&&m.length)?Object.keys(m[0]):[],media0:(m&&m[0])?m[0]:null});
"""
# 一次写完：普通控件 + 提示词编辑器 + 媒体属性；顺手做自检，不合格就别点运行
_JS_WRITE = """
var fid=arguments[0],nid=arguments[1],spec=JSON.parse(arguments[2]);
var f=document.getElementById(fid);
if(!f||!f.contentWindow)return JSON.stringify({err:'no_frame'});
var w=f.contentWindow, d=f.contentDocument||w.document, g=w.app.graph;
var node=g.getNodeById(nid);
if(!node)return JSON.stringify({err:'no_node'});
var by={};(node.widgets||[]).forEach(function(x){by[x.name]=x;});
// 这些是新版节点才有的控件：老工作流里没有就跳过，不能因为缺一颗就整段不跑
var opt={ref_image_size:1,reference_mention_mode:1,prompt_optimizer_enabled:1,
         low_vram_streamed_attention:1,reference_text_only:1,audio_duration_auto:1};
var warn=[];
// 照 H3yun 的做法直接写值：它的下拉显示的是中文标签，值仍收英文口径；
// 拿 options.values 先卡一道会把能跑的值误判成非法。选项表不认只记一条，
// 真正的对错交给后面的序列化自检（那才是节点实际提交的东西）。
function setv(k,v){var x=by[k];if(!x)return 'no:'+k;
  var vals=x.options&&x.options.values;
  if(Array.isArray(vals)&&vals.indexOf(v)<0)warn.push('opt:'+k+':'+v);
  try{if(x.setOption)x.setOption(v);else x.value=v;}catch(e){x.value=v;}
  x.value=v;
  g.setNodeDirty?g.setNodeDirty(node):0;return '';}
var bad=[];
Object.keys(spec.widgets||{}).forEach(function(k){
  var r=setv(k,spec.widgets[k]);
  if(r){if(opt[k])warn.push(r);else bad.push(r);}});
// 媒体三条一起写（H3yun 实机那套，跑了整部短剧）：
//   · 属性必须是**数组**，节点自己的 ensureEmbeddedMedia 只认数组；
//   · 条目只留 media_type/ordinal/filename/subfolder/storage/audio_trim，
//     storage 固定 "input"、audio_trim 固定空串——从线上旧条目抄会把 comfyui/裁切区间带进来；
//   · minimax_h3_virtual_media_links 必须清空，否则上一份工作流的旧图会被当成参考。
// 少写 production_preview 时画廊不刷新，节点也可能按旧预览判定「没有参考」。
var media=spec.media||[];
node.properties=node.properties||{};
try{node.properties.feihou_h3_embedded_media=media;}catch(e){bad.push('prop_media');}
try{node.properties.minimax_h3_virtual_media_links=[];}catch(e){warn.push('prop_links');}
try{node.properties.feihou_h3_production_preview=spec.preview||{};}catch(e){warn.push('prop_preview');}
if(by.embedded_media_json)by.embedded_media_json.value=JSON.stringify(media);
else bad.push('no:embedded_media_json');
// 提示词：编辑器是真源，控件是它的副本——只改控件等于没改。
// 编辑器在 iframe 里，事件也必须用 iframe 自己的 Event：顶层 window 的 InputEvent
// 跨进 iframe 后节点那边未必认，编辑器不会把文本同步回控件与序列化数据。
var text=spec.prompt||'';
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/\\n/g,'<br>');}
var ed=d.querySelector('.comfy-multiline-input.h3-prompt-editor')||d.querySelector('.h3-prompt-editor');
if(ed&&ed.isContentEditable===true){try{ed.focus();}catch(e){}
  ed.innerHTML=esc(text);
  try{ed.dispatchEvent(new w.Event('input',{bubbles:true}));}catch(e){}
  try{ed.dispatchEvent(new w.Event('change',{bubbles:true}));}catch(e){}
}else if(node.__h3Editor){node.__h3Editor.textContent=text;
  try{node.__h3Editor.dispatchEvent(new w.Event('input',{bubbles:true}));}catch(e){}
}else if(by.prompt){by.prompt.value=text;}else bad.push('no_prompt_slot');
// 节点 JS 把「重画媒体画廊」挂在 mode 控件的 callback 上（syncModeWidgets + renderEmbeddedMediaGallery）。
// 直接给 widget.value 赋值不会触发它——画廊就会停在灌图时那 8 张旧图上，自检也看不见新图。
// 手动调一次回调，等于模拟用户重新选了一次模式；不改任何值。
try{if(by.mode&&typeof by.mode.callback==='function')by.mode.callback(by.mode.value);}catch(e){}
g.setDirtyCanvas&&g.setDirtyCanvas(true,true);
// 自检：拿即将提交的序列化结果比对，不合规就报出来，宁可停下也不出废片
// 新版 ComfyUI 的 graphToPrompt() 回的是 Promise：不 then 就取到 undefined，
// 于是每一项都「没值」→ 检查全过 → 这条防线形同不存在（实测过：直接 .output 读回来是空的）。
function chkOf(inp){
  inp=inp||{};
  var nm=0;Object.keys(inp).forEach(function(k){if(/^media_\\d+$/.test(k)&&inp[k])nm++;});
  // 画廊里真填上的槽位：和序列化里的媒体一起看，两个都空才算「参考图没进去」
  var gal=0;try{gal=d.querySelectorAll('.fh-h3-media-slot.has-media').length;}catch(e){}
  var mj=[];try{mj=inp.embedded_media_json?JSON.parse(inp.embedded_media_json):[];}catch(e){}
  return {prompt:String(inp.prompt||'').slice(0,80),seconds:inp.seconds,fps:inp.fps,
          mode:inp.mode,resolution:inp.resolution,aspect:inp.aspect_ratio,
          width:inp.width,height:inp.height,
          media:(mj&&mj.length)||0,
          media0:(mj&&mj[0])||null,
          slots:nm,gallery:gal};
}
function pack(chk){return JSON.stringify({bad:bad,warn:warn,check:chk,editor:!!ed});}
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
# 提示词编辑器就绪没：节点比画布晚一步挂编辑器（H3yun 也是重试等它）。
# 编辑器没挂好就只写控件的话，graphToPrompt 会用编辑器里的旧文案再覆盖回去——
# 自检当时看是过的，提交出去的却是工作流原来那段长故事板。
_JS_EDITOR = """
var f=document.getElementById(arguments[0]);
if(!f||!f.contentWindow)return 0;
var d=f.contentDocument||f.contentWindow.document;
var ed=d.querySelector('.comfy-multiline-input.h3-prompt-editor')||d.querySelector('.h3-prompt-editor');
return (ed&&ed.isContentEditable===true)?1:0;
"""
# 节点媒体画廊实际填了几格：.has-media 是节点自己挂的类，空槽不会挂。
# 序列化里的媒体对了但这里还是 0，说明节点没认这份媒体——别急着提交。
_JS_GALLERY = """
var f=document.getElementById(arguments[0]);
if(!f||!f.contentWindow)return 0;
var d=f.contentDocument||f.contentWindow.document;
return d.querySelectorAll('.fh-h3-media-slot.has-media').length;
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
# 顶层页的运行按钮：三档（Lite/Standard、Lite/Plus、Ultra），H3yun 用的是 Plus 那颗。
# 平台在任务跑着时会把后两档的 .plus-tags 收起来、按钮置灰，所以标签只当第一线索：
# 标签找不到就按固定顺序认（从左到右 Standard / Plus / Ultra），并且**不点禁用按钮**——
# 以前匹配不到就落到第一颗，等于把 Plus 悄悄降成 Standard。
_JS_EXEC = """
var tag=(arguments[0]||'').toLowerCase();
var bs=[].slice.call(document.querySelectorAll('.execute-btn-wrap button'));
if(!bs.length)return 'no_btn';
/* 平台只给第一颗挂 .plus-tags；后两档只有「运行」两个字。
   按固定顺序补名：左 Standard / 中 Plus / 右 Ultra。 */
function lab(b,i){
  var t=(b.querySelector('.plus-tags')||{}).textContent||'';
  if(t)return t.replace(/\\s+/g,' ').trim().slice(0,40);
  if(i===bs.length-1&&bs.length>1&&/ultra/.test(String(b.className)))return 'Ultra';
  if(bs.length>=2)return ['Lite/Standard','Lite/Plus','Ultra'][Math.min(i,2)];
  return (b.textContent||'').replace(/\\s+/g,' ').trim().slice(0,40);
}
var pick=-1;
bs.forEach(function(b,i){
  if(pick<0&&tag&&lab(b,i).toLowerCase().indexOf(tag)>=0)pick=i;});
if(pick<0&&tag){
  pick=tag.indexOf('ultra')>=0?bs.length-1:(bs.length>=2?1:0);
}
if(pick<0)pick=0;
var hit=bs[pick];
if(hit.disabled||hit.getAttribute('disabled')!==null)return 'btn_disabled '+lab(hit,pick);
var out='clicked '+lab(hit,pick);
hit.click();
return out;
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


# 平台自己的任务列表：当前任务（.rh-task-item）和历史（.history-item）都在会话页上，
# 每条带 taskid 和状态文字（生成中 04:02 / 任务失败）。GET /history 在这套实例上一直是 0，
# 只有这张列表能看见「我们这段到底排上没有、跑到哪、是不是已经判失败了」。
# 只读 DOM，不点任何按钮。
_JS_TASKS = """
function clean(e){if(!e)return '';
  var c=e.cloneNode(true);
  [].slice.call(c.querySelectorAll('svg,script,style')).forEach(function(x){x.remove();});
  return (c.textContent||'').replace(/\\s+/g,' ').trim().slice(0,120);}
function one(e){
  var id=clean(e.querySelector('.rh-task-id,.history-id')).match(/\\d+/)||[''];
  var st=e.querySelector('.rh-task-status,[class*=history-status]');
  var d=e.querySelector('.history-bottom-info');
  return {id:id[0],s:clean(st||e.querySelector('.task-status-running')),d:clean(d)};
}
return JSON.stringify({
  cur:[].slice.call(document.querySelectorAll('.workflow-result-wrap .rh-task-item')).slice(0,6).map(one),
  his:[].slice.call(document.querySelectorAll('.rh-task-history .history-item')).slice(0,8).map(one)});
"""


def browser_gone(e):
    """这只调试浏览器被关了、或页面连接断了：属于重开一次就能自愈的那类错。"""
    if type(e).__name__ in ("PageDisconnectedError", "BrowserConnectError", "ContextLostError"):
        return True
    s = str(e)
    return any(k in s for k in ("连接已断开", "已关闭", "连接失败", "页面被关闭", "没连上"))


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
        """本地那份借哪一页进去：手动覆盖 → 平台默认 → 内置那一页。

        换的是画布上那张图，跑它的还是那台实例——「换图不换实例」。
        内置页只是入口，谁都借得到；真跑的一定是灌进去的本地画布。
        """
        for cand in (self.cfg.get("wf_host"), self.cfg.get("default_wf"),
                     HOST_WF_FALLBACK):
            s = str(cand or "").strip()
            m = re.search(r"workflow/(\d+)", s)
            wid = m.group(1) if m else (s if s.isdigit() else "")
            if wid:
                return WF_URL % wid
        return ""

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
        # comfyUI.html 是「先到壳、后挂 app」：实测 iframe 已在，loadGraphData 先是对象、
        # 两三秒后才变成函数、再几秒才把图挂上。等它挂好再灌，别拿「壳到了」当「编辑器好了」。
        for _ in range(40):
            if stop and stop():
                raise CloudError("已停止")
            ready = self.js(tab,
                            "var f=document.getElementById(arguments[0]);"
                            "var a=f&&f.contentWindow&&f.contentWindow.app;"
                            "return !!(a&&typeof a.loadGraphData==='function');", fid)
            if ready:
                break
            time.sleep(0.5)
        else:
            raise CloudError("云端编辑器还没挂好：等不到 loadGraphData，重开这段再试")
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
    def _enter(self, state, aid, url, cb, stop):
        """进工作流页。浏览器窗口被关掉/页面断开时清死连接、重开一次再进。

        用户关掉调试 Chrome 是常事；旧写法拿着那份死连接一路撞「与页面的连接已断开」，
        重开一次就能好，不值得让人重启软件。
        """
        for attempt in (0, 1):
            try:
                if getattr(self.host, "current", aid) != aid:
                    self.host.apply(state, aid=aid)
                tab = self.host.tab()
                tab.get(url)
                return tab
            except Exception as e:
                if attempt or not browser_gone(e):
                    raise
                self._p(cb, stop, "云端：浏览器窗口被关掉了，重开一次…")
                self.host.reset()
                time.sleep(1.5)
        raise CloudError("浏览器窗口被关掉了：重开也没连上，再点一次开始")

    def run(self, p, on_progress=None, should_stop=None):
        """p：{prompt, seconds, width, height, first, wf, acct}；回本地 mp4 路径。

        顺序是「开页 → 抄形状 → 传图 → 写节点 → 提交 → 轮询 → 下载」：
        先开页是因为媒体条目的字段形状要从线上那一条抄，抄完才谈得上写。
        """
        row = self.account(p.get("acct"))
        aid = row["id"]
        state = self.store.load(aid)
        kind, src = self.wf_src(p.get("wf"))
        secs = max(5, min(15, int(p.get("seconds") or 5)))
        size = pick_size(int(p.get("width") or 768), int(p.get("height") or 768))
        first = self._ref(str(p.get("first") or ""))
        if kind == "file":
            url = self.host_url()
            if not url:
                raise CloudError("本地工作流缺一个平台入口页：填一份网页工作流地址当兜底")
        else:
            url = self.wf_url(src)
        with self.host.lock:
            self.host.purpose = "gen"            # 这段期间保活别换号，否则中途掉登录
            try:
                tab = self._enter(state, aid, url, on_progress, should_stop)
                fid = self._wait_frame(tab, should_stop)
                if kind == "file":
                    # 平台上那张图只是张跳板：进去之后立刻换成用户本地这一份
                    self._p(on_progress, should_stop, "云端：灌入本地工作流…")
                    ids = self.load_local_wf(tab, fid, src, should_stop)
                else:
                    ids = self._wait_graph(tab, fid, should_stop)
                self._wait_editor(tab, fid, should_stop)
                self._log_shape(tab, fid, ids["main"])
                media = []
                if not first:
                    # 这份节点只有「图生/首尾帧」和「参考生视频」两种，没有纯文字模式。
                    # 不给图就交上去，平台会当场判「参考生视频未收到图片或视频」——先在这里说清。
                    # 读不到 modeOpts 时也按「必须给图」处理：宁可拦下，也不花积分去换一句平台报错。
                    raise CloudError("云端这份 H3 工作流按参考生成：先在「参考图」那格选一张图，"
                                     "纯文字它不接")
                if first:
                    self._p(on_progress, should_stop, "云端：上传参考图…")
                    fn, sub = self.upload(first, state)
                    media = [self.media_item(fn, sub)]
                spec = {
                    "prompt": str(p.get("prompt") or ""),
                    "media": media,
                    # 画廊预览：H3yun 每段都写这一份；少了它画廊不按新图刷新
                    "preview": {"shown": {"aspect_ratio": size["aspect_ratio"],
                                          "fps": 24, "resolution": size["resolution"]},
                                "fallback": {"aspect_ratio": size["aspect_ratio"], "fps": 24}},
                    "widgets": {
                        # 有图就走「参考生视频」：节点的参考模式才认 embedded_media 清单。
                        # 之前切到 I2V/首尾帧，序列化里 mode=image，但节点执行时按参考槽取图，
                        # 拿不到就把整段判成「参考生视频未收到图片或视频」——这是那条报错的来源。
                        "mode": MODE_REF,
                        "seconds": secs,
                        "fps": 24,
                        "audio_duration_auto": "Off",
                        "ref_image_size": "640",
                        "reference_mention_mode": "By index",
                        # 节点自带的提示词扩写会再去请求一次 LLM，SSL 一抖整段就废；H3yun 默认关
                        "prompt_optimizer_enabled": False,
                        "reference_text_only": not bool(media),
                        "low_vram_streamed_attention": False,
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
                known = self.known_task_ids(tab)      # 提交前任务列表上已有的，几秒后才多出我们这条
                hit = self._submit(tab, should_stop)
                self._p(on_progress, should_stop, "云端：已提交（%s）" % hit.replace("clicked ", "").strip())
                cos, fname = self._wait_result(tab, fid, ids["out"], base_name,
                                               on_progress, should_stop, hist0, known)
            except CloudError:
                raise
            except Exception as e:
                # 生成中途窗口被关掉：平台上可能还在跑，别把原生异常甩给界面
                if browser_gone(e):
                    raise CloudError("浏览器窗口被关掉了：这一段没跑完。"
                                     "平台上可能还在跑，去「H3云端」看一眼；"
                                     "重开自动处理，再点开始即可")
                raise
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

    def _wait_editor(self, tab, fid, stop, limit=20):
        """等提示词编辑器挂好再写。等不到也只是记一条——有的工作流版本可能真没有编辑器。"""
        t0 = time.time()
        while time.time() - t0 < limit:
            if stop and stop():
                raise CloudError("已停止")
            try:
                if self.js(tab, _JS_EDITOR, fid):
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        self.log("· 等 %d 秒也没挂出提示词编辑器：改走控件/节点编辑器兜底" % limit)
        return False

    def _log_shape(self, tab, fid, main):
        """看一眼前置条件：节点类型、模式选项、编辑器在不在。

        媒体条目的字段不再从旧条目抄（见 media_item）——旧图那一条的 storage/裁切区间
        可能属于另一个实例，抄过来正是「节点说没收到参考」的来源。
        """
        try:
            d = json.loads(self.js(tab, _JS_INSPECT, fid, main) or "{}")
        except ValueError:
            d = {}
        if d.get("err"):
            raise CloudError("读不到主节点：%s" % d["err"])
        self.has_editor = bool(d.get("editor"))
        return d

    def media_item(self, name, sub):
        """一条媒体引用，字段固定成 H3yun 实机验证过的那一份。

        为什么不再从线上旧条目抄：`storage` 一旦抄成 "comfyui"、`audio_trim` 抄成非空串，
        ensureEmbeddedMedia 虽然放行，落到执行节点那边却取不到文件，
        最后整段被平台判「参考生视频未收到图片或视频」。上传口是 /upload/image + type=input，
        所以 storage 只能是 "input"。
        """
        return {"media_type": "image", "ordinal": 1, "filename": name,
                "subfolder": sub or "", "storage": "input", "audio_trim": ""}

    def _write(self, tab, fid, ids, spec, secs, size, has_media):
        raw = self.js(tab, _JS_WRITE, fid, ids["main"], json.dumps(spec, ensure_ascii=False))
        try:
            d = json.loads(raw or "{}")
        except ValueError:
            raise CloudError("写入节点的返回读不懂：%s" % str(raw)[:160])
        if d.get("err"):
            raise CloudError("写入主节点失败：%s" % d["err"])
        for x in (d.get("warn") or []):
            self.log("· 控件提醒：%s" % str(x)[:80])
        bad = list(d.get("bad") or [])
        c = d.get("check") or {}
        want_slots = 1 if has_media else 0
        # 「读不到」不能算过关：以前这里每一项都写成 `not in (None, 期望值)`，
        # 于是自检只要整体失灵就全绿——而它确实失灵过一次（graphToPrompt 回的是 Promise）。
        if c.get("err") or c.get("mode") is None:
            raise CloudError("提交前自检读不到序列化结果（%s）：不敢盲提交"
                             % str(c.get("err") or "序列化里没值")[:80])
        # 线上实测：mode 控件「Reference-to-video」序列化后是 reference。
        # 有图时固定走参考模式——这和 H3yun 线上跑通整部短剧的口径一致。
        want_mode = "reference"
        if c.get("mode") != want_mode:
            bad.append("mode=%s" % c.get("mode"))
        # 序列化里的那条媒体必须就是我们刚传的：旧模板的 storage/文件名没换干净，
        # 节点执行时照样会说「没收到参考」。
        if has_media:
            m0 = c.get("media0") if isinstance(c.get("media0"), dict) else {}
            mine = (spec.get("media") or [{}])[0]
            if m0 and str(m0.get("filename") or "") != str(mine.get("filename") or ""):
                bad.append("媒体文件名没换成新图（%s）" % str(m0.get("filename") or "")[:24])
            if m0 and str(m0.get("storage") or "input") != "input":
                bad.append("媒体 storage=%s" % m0.get("storage"))
        # 画廊是节点自己的账本：序列化对了但画廊空着，说明节点没认这份媒体
        if has_media and int(c.get("gallery") or 0) < want_slots:
            for _ in range(8):
                time.sleep(0.5)
                try:
                    gal = int(self.js(tab, _JS_GALLERY, fid) or 0)
                except Exception:
                    gal = 0
                if gal >= want_slots:
                    c["gallery"] = gal
                    break
            if int(c.get("gallery") or 0) < want_slots:
                bad.append("画廊里没有参考图（节点没认这份媒体）")
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

    def _submit(self, tab, stop=None, limit=40):
        """找到运行按钮再点：平台页是 SPA，按钮比画布晚挂出来。

        实测本地图灌进去、参考图上完，页面上那颗按钮还在慢慢渲染——
        一次读不到就报「没权限」是假话，等一会儿它自己就出来了。
        """
        t0 = time.time()
        last = ""
        while time.time() - t0 < limit:
            if stop and stop():
                raise CloudError("已停止：还没点提交")
            last = str(self.js(tab, _JS_EXEC, self.tag) or "")
            if last.startswith("clicked"):
                return last
            time.sleep(2)
        if last.startswith("btn_disabled"):
            raise CloudError("运行按钮一直是禁用的：这个号上还有任务在跑，等它完再点"
                             "（没替你点「继续运行」，那条跑的不是这次写的参数）")
        raise CloudError("页面上找不到运行按钮：等 %d 秒也没挂出来（这份工作流可能没权限跑）" % limit)

    def history_count(self, tab, fid):
        """平台上现在有几条历史——提交前后各读一次，多出来的那条才是我们这段。
        读不到回 0（宁可说「查不到」，也不把旧的一条当成新的）。"""
        try:
            raw = self.js(tab, _JS_PROGRESS, fid)
            d = json.loads(raw) if raw else {}
            return int((d.get("h") or {}).get("n") or 0)
        except Exception:
            return 0

    def task_entries(self, tab):
        """平台任务列表：当前在跑的与最近的几条历史。读不到回空表（不猜）。"""
        try:
            raw = self.js(tab, _JS_TASKS)
            d = json.loads(raw) if raw else {}
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def known_task_ids(self, tab):
        """提交前已经在那张列表上的 taskid：之后多出来的那条才是我们这段。"""
        d = self.task_entries(tab)
        ids = set()
        for k in ("cur", "his"):
            for x in d.get(k) or []:
                if x.get("id"):
                    ids.add(str(x["id"]))
        return ids

    def platform_state(self, tab, fid, waited, hist0=0, known=None):
        """平台上这一段到底到哪一步了——一句话，读不到就回空串（绝不编一个）。

        时间波动很大（实测同参数一段 353 秒出片、一段排到二十分钟没动），
        只报「已等 N 秒」人分不清排队/在跑/已失败，所以去问平台自己：
        任务列表那一栏（最准，平台自己写的状态）、页面内存里的队列、GET /history 的条数。
        hist0 = 提交那一刻的历史条数；known = 提交前列表上已有的 taskid——
        两者都只用来认出「刚多出来的那一条」是不是我们这段。
        """
        # 先看任务列表：它直接写着「生成中 04:02」「任务失败」，比队列更有信息量。
        # 提交后新出现的那个 taskid 就是我们这一段；匹配不到就退回旧口径，不去猜别的任务。
        tasks = self.task_entries(tab) if known is not None else {}
        cand = list(tasks.get("cur") or []) + list(tasks.get("his") or [])[:1]
        for x in cand:
            if not x.get("id") or str(x["id"]) in (known or ()):
                continue
            st = str(x.get("s") or "")
            det = str(x.get("d") or "")
            if "失败" in st:
                return ("平台判失败：" + (det or "任务列表把它标成失败，点开那一条看节点报错")
                        + " · taskid " + str(x["id"]))
            if st:
                return "平台上这一段：" + st + " · taskid " + str(x["id"])
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

    def _wait_result(self, tab, fid, out, base_name, cb, stop, hist0=0, known=None):
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
            where = self.platform_state(tab, fid, int(time.time() - t0), hist0, known)
            # 平台自己把它标成失败了：再等下去也只是等超时，当场收手把原因带出去
            if "平台判失败" in where:
                raise CloudError(where)
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
