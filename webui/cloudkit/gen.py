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
主节点按 class_type 找 FeiHouEasyH3RH（老形状）或 MiniMaxH3ReferenceToVideo
（新形状，参数挂在虚拟节点上），输出节点按 VHS_VideoCombine 找。
"""
import json
import math
import os
import re
import time

from . import mention

WF_URL = "https://www.runninghub.cn/workflow/%s"
# 两张内置画布，界面上是下拉里的两项；「默认」仍是之前那张 FeiHou 画布，
# 金鱼那张单独列出来，不替默认。两张的节点类型和写路径都不同，见下面 SHAPE_FH/SHAPE_KJ。
LEGACY_WF = "2117505440799084545"
LEGACY_WF_NAME = "H3 参考生视频"
GOLDFISH_WF = "2109907990638850050"
GOLDFISH_WF_NAME = "MiniMax H3 参考生视频"
# 界面上「默认」的空值口径没有变：DEFAULT_WF 就是默认那张。
DEFAULT_WF = LEGACY_WF
DEFAULT_WF_NAME = LEGACY_WF_NAME
WF_CUSTOM_NAME = "指定地址 / 本地文件"
WF_PRESETS = (
    {"code": "default", "name": "默认 · " + LEGACY_WF_NAME, "id": LEGACY_WF},
    {"code": "goldfish", "name": "金鱼 · " + GOLDFISH_WF_NAME, "id": GOLDFISH_WF},
)


def wf_choice(cfg):
    """这份云端配置选的是哪张：("default"|"goldfish"|"custom", 自定义值)。

    老配置里没有 wf_preset：填过地址/文件就当自定义，空着就是默认那张——
    这样升级不会把人家手填的工作流悄悄换掉。
    """
    c = cfg if isinstance(cfg, dict) else {}
    key = str(c.get("wf_preset") or "").strip()
    custom = str(c.get("workflow") or c.get("wf") or "").strip()
    if key == "goldfish":
        return "goldfish", custom
    if key == "custom":
        return "custom", custom
    if key == "default":
        return "default", custom
    return ("custom", custom) if custom else ("default", custom)


def wf_choices():
    """给界面下拉的三项：默认 / 金鱼 / 自定义。编号一并给出去，方便界面上写清楚。"""
    out = [{"code": p["code"], "name": p["name"], "id": p["id"]} for p in WF_PRESETS]
    out.append({"code": "custom", "name": WF_CUSTOM_NAME, "id": ""})
    return out


# 本地导出的画布没有平台编号；借平台上的某一页进实例（换图不换实例）。
# 这一页只是入口，跑的还是灌进去的那张图——和 H3yun 内置的宿主页同一个。
HOST_WF_FALLBACK = WF_URL % "2103759530927673346"
# 平台上见过的两种 H3 画布形状：
#   feihou —— 主节点 FeiHouEasyH3RH 自带提示词编辑器和媒体清单，写它就够；
#   kj     —— 主节点 MiniMaxH3ReferenceToVideo，提示词在 Text 节点、时长在
#             PrimitiveFloat（后面挂一条换算公式）、尺寸在 ResolutionSelector，
#             参考图是 9 个 LoadImage；这些都通过 SetNode→GetNode 虚拟节点接进主节点。
MAIN_TYPE = "FeiHouEasyH3RH"
MAIN_TYPE_KJ = "MiniMaxH3ReferenceToVideo"
OUT_TYPE = "VHS_VideoCombine"
SHAPE_FH = "feihou"
SHAPE_KJ = "kj"
MODE_REF = "Reference-to-video"
# kj 那张的参考图槽位编号：SetNode 名字里的数字就是提示词里的 <Picture N>
KJ_IMAGE_NAME = "图像%d"
KJ_PROMPT_NAME = "提示词"
KJ_MAX_IMAGES = 9
# 云端只放开这三档画幅：界面上横/方/竖已经是全集，其它画幅留给「自定义宽高」
RATIO_BY_ORIENT = {"h": "16:9", "s": "1:1", "v": "9:16"}
TIERS = [360, 416, 480, 540, 640, 720, 768, 832, 928, 1024, 1080]
# ResolutionSelector 的百万像素就照作者那张说明表的口径给（0.2→608x352 … 2.0→1920x1088）
KJ_MP_MIN, KJ_MP_MAX = 0.2, 2.0


def wf_id_of(s):
    """从平台那一格里粘来的地址提出工作流编号，认这几种写法：
    /workflow/<id>（编辑器与运行入口）、/ai-detail/<类型>/workflow/<id>、
    /ai-detail/<id>（「查看工作流」那页，地址栏里最常见）、/post/<id>（作品详情页，
    社区分享出来的就是这一种，进去点「查看工作流」才挂画布）。
    只给编号、或一个 URL 都提不出，就按原样收。
    """
    s = str(s or "").strip()
    for pat in (r"/workflow/(\d+)", r"/ai-detail/(?:\d+/)?(\d+)", r"/post/(\d+)"):
        m = re.search(pat, s)
        if m:
            return m.group(1)
    return s if s.isdigit() else ""


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
var main=0,out=0,kj=0;
n.forEach(function(x){
  if(x.type==='FeiHouEasyH3RH')main=x.id;
  else if(x.type==='MiniMaxH3ReferenceToVideo')kj=x.id;
  else if(x.type==='VHS_VideoCombine')out=x.id;
});
if(!main&&kj)main=kj;
return JSON.stringify({nodes:n.length,main:main,out:out,shape:(main===kj?'kj':'feihou')});
"""
# 本地工作流文件这条路：真机量过托管前端确实有 app.loadGraphData（探针 --dump/--load 往返
# 过一次：导出 65605 字节、灌回去 23 个节点、主节点 389 与输出节点 325 都按类型认得）。
# 只改内存里那张图——不点保存、不提交、不扣积分。
# 新版前端的 loadGraphData 回的是 Promise：同步 try/catch 接不到异步拒绝，
# 失败会变成页面上那个「Loading aborted…setGraph」弹窗，而这边的代码还当成功了。
# 所以把结果挂到 window.__qicWfLoad，由 Python 侧轮询，失败当场停，不拿旧图继续提交。
_JS_LOAD_WF = """
var fid=arguments[0],txt=arguments[1];
var f=document.getElementById(fid);
if(!f||!f.contentWindow)return JSON.stringify({err:'no_frame'});
var w=f.contentWindow,a=w.app;
if(!a||typeof a.loadGraphData!=='function')return JSON.stringify({err:'这份前端没有 loadGraphData 的口'});
var g;try{g=JSON.parse(txt);}catch(e){return JSON.stringify({err:'不是 JSON：'+(e&&e.message)});}
if(!g||!g.nodes)return JSON.stringify({err:'JSON 里没有 nodes'});
var r=null;
try{
  w.__qicWfLoad={state:'pending',msg:''};
  r=a.loadGraphData(g,true,false,'local.json');
  if(r&&typeof r.then==='function'){
    r.then(function(){w.__qicWfLoad={state:'ok',msg:''};},
           function(e){w.__qicWfLoad={state:'err',msg:String(e&&e.message||e)};});
  }else w.__qicWfLoad={state:'ok',msg:''};
}catch(e){w.__qicWfLoad={state:'err',msg:String(e&&e.message||e)};}
return JSON.stringify({ok:1,async:!!(r&&typeof r.then==='function')});
"""
# 灌图结果 + 画布现状：节点 id 拿来和文件逐一对，防止「加载失败了但旧图还挂着」被当成成功
_JS_WF_STATE = """
var f=document.getElementById(arguments[0]);
if(!f||!f.contentWindow)return JSON.stringify({state:'err',msg:'画布不在了'});
var w=f.contentWindow,s=w.__qicWfLoad||{state:'none'};
var n=((w.app||{}).graph||{})._nodes||[],main=0,out=0,kj=0;
n.forEach(function(x){if(x.type==='FeiHouEasyH3RH')main=x.id;
  else if(x.type==='MiniMaxH3ReferenceToVideo')kj=x.id;
  else if(x.type==='VHS_VideoCombine')out=x.id;});
if(!main&&kj)main=kj;
return JSON.stringify({state:s.state||'none',msg:s.msg||'',nodes:n.length,
  main:main,out:out,shape:(main===kj?'kj':'feihou'),
  ids:n.map(function(x){return String(x.id);})});
"""
# 前端真正能接图：loadGraphData 是函数只是第一道，graph 也得挂上
_JS_FRONTEND_READY = """
var f=document.getElementById(arguments[0]);
var a=f&&f.contentWindow&&f.contentWindow.app;
return !!(a&&typeof a.loadGraphData==='function'&&a.graph);
"""


def _wf_json(path):
    """读 + 解析工作流 JSON；API 格式在这里就拦下，并说清该导哪一份。"""
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
    if not isinstance(g, dict):
        raise CloudError("本地那份不是画布工作流：顶层不是对象")
    # API 格式（{"1": {"class_type": …}}）是给 /prompt 的，画布不认：
    # 我们自己的 webui/moss/workflow_h3.json 就是这种，别让人把它拖进来。
    api_keys = [k for k in g if str(k).isdigit()]
    if api_keys and any(isinstance(g.get(k), dict) and g[k].get("class_type") for k in api_keys):
        raise CloudError("这是 API 格式的工作流（节点编号 → class_type），云端画布不认；"
                         "请在网页里点「导出工作流」存一份带 nodes 的再选")
    return g


def check_workflow_json(path):
    """开跑前先拆开看一眼：能当场判死的，别开浏览器、别等几分钟才失败。

    只查结构（nodes/links/节点类型），不查节点装没装——那得进页面才知道。
    返回 {nodes, links, ids, types}；不合格直接 CloudError，消息里说清是哪一种不对。
    """
    g = _wf_json(path)
    nodes, links = g.get("nodes"), g.get("links")
    if not isinstance(nodes, list) or not nodes:
        raise CloudError("这份 JSON 里没有画布节点：要网页里「导出工作流」存下来的那份（带 nodes）")
    if not isinstance(links, list):
        raise CloudError("这份 JSON 里没有 links：要网页里「导出工作流」存下来的那份（带 links）")
    ids, types = set(), set()
    for n in nodes:
        if not isinstance(n, dict) or n.get("id") is None or not str(n.get("type") or "").strip():
            raise CloudError("工作流节点缺 id/type：这份 JSON 不完整，重新导出一次")
        ids.add(str(n["id"]))
        types.add(str(n["type"]))
    for l in links:
        if not isinstance(l, (list, tuple)) or len(l) < 5:
            raise CloudError("工作流连线格式不对：重新导出一次再试")
        if str(l[1]) not in ids or str(l[3]) not in ids:
            raise CloudError("工作流连线指向了不存在的节点（%s → %s）：重新导出一次再试"
                             % (l[1], l[3]))
    if MAIN_TYPE in types:
        shape = SHAPE_FH
    elif MAIN_TYPE_KJ in types:
        shape = SHAPE_KJ
    else:
        raise CloudError("这份工作流里没有 H3 主节点（%s 或 %s）：不是这条路要的那张图"
                         % (MAIN_TYPE, MAIN_TYPE_KJ))
    if "VHS_VideoCombine" not in types:
        raise CloudError("这份工作流里没有 VHS_VideoCombine 输出节点：取不到成片")
    return {"nodes": len(nodes), "links": len(links), "ids": ids, "types": types,
            "shape": shape}
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
var phtml=String(spec.prompt_html||'');
var wantChips=parseInt(spec.chips||0,10)||0;
function fire(el){try{el.dispatchEvent(new w.Event('input',{bubbles:true}));}catch(e){}
  try{el.dispatchEvent(new w.Event('change',{bubbles:true}));}catch(e){}}
var ed=d.querySelector('.comfy-multiline-input.h3-prompt-editor')||d.querySelector('.h3-prompt-editor');
if(ed&&ed.isContentEditable===true){try{ed.focus();}catch(e){}
  ed.innerHTML=phtml||esc(text);
  // 参考图超过一张时，编号必须以 chip 形式进去：直写 innerHTML 偶尔被编辑器
  // 拆成纯文字，这时用 template 把节点整体搬一次，再核对 chip 数。
  if(phtml&&wantChips>0&&ed.querySelectorAll('.h3-mention-chip').length===0){
    try{var tpl=d.createElement('template');tpl.innerHTML=phtml;
      ed.innerHTML='';ed.appendChild(tpl.content);}catch(e){}
  }
  fire(ed);
}else if(node.__h3Editor){
  if(phtml&&typeof node.__h3Editor.innerHTML==='string')node.__h3Editor.innerHTML=phtml;
  else node.__h3Editor.textContent=text;
  fire(node.__h3Editor);
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
  // 多图时逐条核对：文件名/序号/storage 必须与刚上传的那一组一一对应，
  // 只看 media0 会把「第一张对、后面几张还是旧图」放过去。
  var mall=[];try{mall=(mj||[]).map(function(x){
    return {filename:x.filename,ordinal:x.ordinal,storage:x.storage};});}catch(e){}
  var chips=0;try{chips=d.querySelectorAll('.h3-mention-chip').length;}catch(e){}
  return {prompt:String(inp.prompt||'').slice(0,80),seconds:inp.seconds,fps:inp.fps,
          mode:inp.mode,resolution:inp.resolution,aspect:inp.aspect_ratio,
          width:inp.width,height:inp.height,
          media:(mj&&mj.length)||0,
          media0:(mj&&mj[0])||null,
          mediaAll:mall,chips:chips,
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
# ---------- 新形状（MiniMaxH3ReferenceToVideo）：先把「能写的节点」反查出来 ----------
# 主节点上那几颗控件（prompt/width/height/length）多半挂着链接，直接改值等于写在
# 一个被连线盖住的空壳上——序列化时链接值会把它们整个盖掉。所以要顺着链接往回走：
# GetNode→同名 SetNode→它的来源，Reroute/Primitive/数学式这类中转再往前一跳，
# 落到真正写数的 Text / PrimitiveFloat / ResolutionSelector 上；没连线的才写主节点自己。
# 参考图同理：LoadImage 喂给哪个 SetNode，SetNode 名字里的数字就是提示词的 <Picture N>。
# 这一步只读（不点保存、不提交）；写什么值由 Python 侧按接线算，页面脚本只照清单落值。
_JS_KJ_MAP = """
var f=document.getElementById(arguments[0]);
if(!f||!f.contentWindow)return JSON.stringify({err:'no_frame'});
var w=f.contentWindow,g=w.app.graph,nodes=(g||{})._nodes||[];
function name0(n){var x=(n.widgets||[])[0];return x?String(x.value):'';}
function linkOf(id){return (g.links||{})[id]||(id&&g.links&&g.links[String(id)])||null;}
var sets={};
nodes.forEach(function(n){if(n.type==='SetNode')sets[name0(n)]=n;});
function back(node,depth){
  for(var k=0;node&&k<(depth||8);k++){
    if(node.type==='GetNode'){node=sets[name0(node)]||null;continue;}
    if(node.type==='ComfyMathExpression'||node.type==='SetNode'
       ||/Reroute|Primitive/i.test(node.type)){
      var li=(node.inputs||[]).filter(function(x){return x.link;})[0];
      if(!li)return node;
      var L=linkOf(li.link);
      node=L?g.getNodeById(L.origin_id):null;
      continue;
    }
    return node;
  }
  return node;
}
var main=null;
nodes.forEach(function(n){if(n.type==='MiniMaxH3ReferenceToVideo'&&!main)main=n;});
if(!main)return JSON.stringify({err:'图上没有 MiniMaxH3ReferenceToVideo'});
var out={main:main.id,roles:{},aspect:[],images:[],res:null,multiple:0};
(main.inputs||[]).forEach(function(i){
  var nm=(i.widget||{}).name;
  if(!nm)return;
  if(!i.link){out.roles[nm]={id:main.id,w:nm,src:'direct'};return;}
  var L=linkOf(i.link),r=L?back(g.getNodeById(L.origin_id)):null;
  if(!r)return;
  if(r.type==='Text')out.roles[nm]={id:r.id,w:'text',src:'text'};
  else if(/Primitive/.test(r.type))out.roles[nm]={id:r.id,w:'value',src:'prim'};
  else if(r.type==='ResolutionSelector'){
    out.roles[nm]={id:r.id,w:'aspect_ratio',src:'res'};
    (r.widgets||[]).forEach(function(x){
      if(x.name==='aspect_ratio'&&x.options&&x.options.values)
        out.aspect=x.options.values.slice(0,40);
      // 百万像素那一格只认它自己那几档（下拉或按 step 取整）：写一个它不认的小数，
      // 节点回头自己改成别的一档，出片尺寸就不是界面要的那一格了。
      if(x.name==='megapixels')out.res={
        opts:x.options&&x.options.values?x.options.values.slice(0,60):null,
        min:x.options?x.options.min:null,max:x.options?x.options.max:null,
        step:x.options?x.options.step:null,val:x.value};
      if(x.name==='multiple')out.multiple=x.value;});
  } else out.roles[nm]={id:r.id,w:'',src:r.type};
});
nodes.forEach(function(n){
  if(n.type!=='LoadImage')return;
  var o=(n.outputs||[]).filter(function(x){return x.name==='IMAGE';})[0]||{};
  var nm='';
  (o.links||[]).some(function(t){var L=linkOf(t);if(!L)return false;
    var r=g.getNodeById(L.target_id);
    if(r&&r.type==='SetNode'){nm=name0(r);return true;}return false;});
  out.images.push({id:n.id,name:nm,mode:n.mode});
});
var vhs=null;
nodes.forEach(function(n){if(n.type==='VHS_VideoCombine'&&!vhs)vhs=n;});
out.out=vhs?vhs.id:0;
return JSON.stringify(out);
"""
# 照清单落值：每项是 [节点 id, 控件名, 值, 是否必须是下拉里的合法值, 标签]。
# 下拉（画幅）不认就拦下来不写——写进去一个平台不认的字符串，出的是废片还照扣积分；
# 参考图那一格反倒不能拦：刚 upload 上来的文件名还没进这一版前端缓存的列表里，
# 但控件收得下，节点执行时按文件名取图（老形状那条路也是这么走的）。
# 写完拿 graphToPrompt 的序列化结果对账：提示词和文件名有没有真的进去——
# 虚拟节点会把值折成连线引用，主节点自己那格未必是字符串，所以整串里搜最稳。
_JS_KJ_WRITE = """
var fid=arguments[0],mid=arguments[1],spec=JSON.parse(arguments[2]);
var f=document.getElementById(fid);
if(!f||!f.contentWindow)return JSON.stringify({err:'no_frame'});
var w=f.contentWindow,g=w.app.graph;
var bad=[],warn=[],ck={},seen={};
function widget(node,name){var hit=null;
  (node.widgets||[]).forEach(function(x){if(x.name===name)hit=x;});return hit;}
(spec.writes||[]).forEach(function(it){
  var id=it[0],name=it[1],val=it[2],strict=it[3],tag=it[4];
  if(!id||!name){bad.push('接线不全:'+tag);return;}
  var node=g.getNodeById(id);
  if(!node){bad.push('节点没了:'+tag);return;}
  var x=widget(node,name);
  if(!x){bad.push('没控件:'+tag);return;}
  var vals=x.options&&x.options.values;
  var ok=Array.isArray(vals)&&vals.length&&
         vals.map(function(v){return String(v);}).indexOf(String(val))>=0;
  if(strict&&!ok){warn.push(tag+'：这个值不在下拉里（'+String(val).slice(0,40)+'），没写');return;}
  try{ if(x.setOption&&ok)x.setOption(val); else x.value=val; }
  catch(e){ try{x.value=val;}catch(e2){bad.push('写不进:'+tag);return;} }
  x.value=val;
  try{ if(typeof x.callback==='function')x.callback(val); }catch(e){}
  g.setNodeDirty&&g.setNodeDirty(node);
  seen[tag]=String(x.value).slice(0,60);
});
g.setDirtyCanvas&&g.setDirtyCanvas(true,true);
ck.seen=seen;
function pack(){return JSON.stringify({bad:bad,warn:warn,check:ck});}
function chk(o){
  var ser='';try{ser=JSON.stringify((o&&o.output)||{});}catch(e){}
  ck.serBytes=ser.length;
  var frag=String(spec.frag||'');
  ck.prompt=frag?ser.indexOf(frag)>=0:true;
  ck.files=(spec.files||[]).map(function(fn){return ser.indexOf(String(fn))>=0;});
  var m=g.getNodeById(mid)||{},wm={};
  (m.widgets||[]).forEach(function(x){wm[x.name]=x.value;});
  ck.width=wm.width;ck.height=wm.height;ck.length=wm.length;
  return pack();
}
var p=null;
try{
  p=(w.app.graphToPrompt&&w.app.graphToPrompt())||(w.graphToPrompt&&w.graphToPrompt());
}catch(e){ck.err=String(e&&e.message||e).slice(0,100);return pack();}
if(p&&p.then)return p.then(chk,function(e){ck.err=String(e&&e.message||e).slice(0,100);
                                          return pack();});
return chk(p);
"""


def ratio_label(opts, ratio):
    """在 ResolutionSelector 的实时可选值里挑出这一画幅那一条（"16:9 (Widescreen)" 之类）。
    对不上就回空串：宁可停下说一声，也不拿一个近似档位糊过去。"""
    want = str(ratio or "").strip()
    for x in opts or []:
        if str(x or "").strip() == want:
            return str(x)
    for x in opts or []:
        if str(x or "").strip().startswith(want):
            return str(x)
    return ""


def megapixels_of(w, h):
    """界面那对宽高折成 ResolutionSelector 的百万像素（作者那张说明表就是这个口径）。
    节点自己再按 multiple 取整，所以实际出片尺寸会比界面写的大半格小半格。"""
    mp = max(0, int(w or 0)) * max(0, int(h or 0)) / 1000000.0
    return round(min(KJ_MP_MAX, max(KJ_MP_MIN, mp)), 2)


def _num_of(x):
    """从 "0.9" / "0.9MP" / 0.9 里抠出那个数；抠不到回 None。"""
    if isinstance(x, bool) or x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"\d+(?:\.\d+)?", str(x))
    return float(m.group()) if m else None


def snap_megapixels(target, res):
    """这一格是下拉就挑它给的那几条；是浮点就原样写，让它自己取整。

    下拉不能糊：写一个列表里没有的字符串节点不认，出的是废片还照扣积分。
    浮点反倒别抢着替它取整——实测它的 options.step 报 1，真按 1 的格子圆会把
    1280x720 抬到 1.0 兆像素（出片 1344x768，比界面要的还大一档，白烧显存）；
    原样写 0.92，节点自己圆成 0.9，回读那个数才是真出片的数。
    """
    info = res if isinstance(res, dict) else {}
    pairs = [(v, x) for x in (info.get("opts") or [])
             for v in [_num_of(x)] if v is not None]
    if not pairs:
        return target
    return min(pairs, key=lambda p: abs(p[0] - target))[1]


def kj_out_size(mp, ratio, multiple=32):
    """按「百万像素 × 画幅 × multiple」推节点最后算出来的那对宽高。
    它是往上贴格子的：拿作者说明表对过 0.2→608x352、0.98→1344x768、2.0→1920x1088，
    四舍五入算不出这三组，只有进一位能对上。"""
    parts = str(ratio or "").replace(" ", "").split(":")[:2]
    if len(parts) < 2:
        return 0, 0
    a, b = _num_of(parts[0]), _num_of(parts[1])
    mp = _num_of(mp)
    if not a or not b or not mp or mp <= 0:
        return 0, 0
    w = (mp * 1000000.0 * a / b) ** 0.5
    h = w * b / a
    m = _num_of(multiple)
    if m and m > 0:
        w = m * math.ceil(w / m)
        h = m * math.ceil(h / m)
    return int(w), int(h)


def kj_frames(secs):
    """秒数换成这份节点要的帧数：24fps，再补齐到「除 17 余 5」。
    作者图上那条数学式就是这个（max(5,round(a*24)) + (5-…) % 17），
    实测 12 秒 → 294 帧 → 回来的文件正好 294 帧 / 12.25 秒。"""
    n = max(5, int(round(max(1, int(secs)) * 24)))
    return n + (5 - n % 17) % 17


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


# 平台自己的任务列表：右侧那一栏同时写着 taskid、状态（生成中 04:02 / 任务失败）
# 和运行模式，是判断「我们这段排上没有、跑到哪、是不是已经失败」最准的一处。
# GET /history 在这套实例上常常是 0，页面队列也常常是空壳，所以优先读这张 DOM。
# 两套取法：先按老类名（.rh-task-item / .history-item + .rh-task-id）取；
# 类名改了就对叶子节点里的「taskid: 一串数字」兜底——H3yun 在同一个平台上
# 就是用后一种跑完整部短剧的，不受前端改版影响。只读 DOM，不点任何按钮。
_JS_TASKS = """
function q(x){return String(x==null?'':x).replace(/\\s+/g,' ').trim();}
function clean(e){
  if(!e)return '';
  var c=e.cloneNode(true);
  var drop=c.querySelectorAll('svg,script,style,img,video,canvas');
  for(var i=0;i<drop.length;i++){if(drop[i].parentNode)drop[i].parentNode.removeChild(drop[i]);}
  return q(c.textContent);
}
function stOf(t){
  t=String(t||'');
  var m=t.match(/(生成中|运行中|采样中|排队中|队列中|等待中|已完成|完成|成功|失败|错误|异常|已取消|取消中|已停止|已中止|中断)/);
  return m?m[1]:'';
}
function tmOf(t){
  var m=String(t||'').match(/([0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?)/);
  return m?m[1]:'';
}
function modeOf(t){
  var m=String(t||'').match(/运行模式[:\\s：]*([^\\s,，。;；|]+)/);
  if(!m)return '';
  var v=m[1];
  if(/ultra/i.test(v))return 'Ultra';
  if(/plus/i.test(v))return 'Lite/Plus';
  if(/standard/i.test(v))return 'Lite/Standard';
  return v.slice(0,24);
}
function nameOf(t){
  var m=String(t||'').match(/([\\u4e00-\\u9fa5A-Za-z0-9]{1,20}(?:运行|模板))/);
  return m?m[1]:'';
}
var out={cur:[],his:[]},seen={};
function add(id,box,leaf,isHis){
  id=String(id||'');
  if(!id||seen[id])return;
  seen[id]=1;
  var bt=clean(box)||q(leaf);
  var stEl=box.querySelector('.rh-task-status,.task-status-running,[class*="task-status"],[class*="history-status"]');
  var s=stEl?clean(stEl):'';
  if(!s)s=stOf(bt);
  var stm=s.match(/([0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?)/);
  var o={id:id,s:s,d:bt.slice(0,240),time:(stm?stm[1]:tmOf(bt)),
         mode:modeOf(bt),name:nameOf(bt),his:!!isHis,raw:q(leaf).slice(0,120)};
  (isHis?out.his:out.cur).push(o);
}
/* 先按已知类名取：老版任务项有 .rh-task-id，状态字在 .rh-task-status 里 */
var pairs=[[".workflow-result-wrap .rh-task-item",".rh-task-id",false],
           [".rh-task-item",".rh-task-id",false],
           [".rh-task-history .history-item",".history-id",true],
           [".history-item",".history-id",true]];
pairs.forEach(function(p){
  var els=[];
  try{els=[].slice.call(document.querySelectorAll(p[0]));}catch(e){}
  els.slice(0,15).forEach(function(e){
    var t=clean(e.querySelector(p[1]));
    var m=t.match(/[0-9]{10,}/);
    if(m)add(m[0],e,e,p[2]);
  });
});
/* 类名对不上时按「taskid: 一串数字」兜底：不受前端改版影响 */
if(!(out.cur.length+out.his.length)){
  var roots=['.rh-task-list','.task-list','[class*="task-list"]','[class*="taskList"]',
             '.workflow-result-wrap','.rh-task-history'];
  var rootsHit=[];
  roots.forEach(function(s){
    try{[].slice.call(document.querySelectorAll(s)).slice(0,15).forEach(function(e){rootsHit.push(e);});}catch(e){}
  });
  if(!rootsHit.length)rootsHit=[document];
  rootsHit.forEach(function(root){
    var all=[];
    try{all=[].slice.call(root.querySelectorAll('*'));}catch(e){return;}
    for(var i=0;i<all.length&&(out.cur.length+out.his.length)<40;i++){
      var el=all[i];
      if(el.children&&el.children.length>4)continue;
      var t=q(el.textContent);
      var m=t.match(/taskid[:\\s]*([0-9]{10,})/i);
      if(!m)continue;
      var id=m[1],box=el;
      for(var j=0;j<12;j++){
        if(!box.parentElement)break;
        var up=box.parentElement,ut=clean(up);
        if(ut.length>800)break;
        box=up;
        if(/运行模式/.test(ut)||stOf(ut))break;
      }
      var cls=(String(box.className||'')+' '+String((box.parentElement||{}).className||'')).toLowerCase();
      add(id,box,t,/history/.test(cls));
    }
  });
}
return JSON.stringify(out);
"""


def browser_gone(e):
    """这只调试浏览器被关了、或页面连接断了：属于重开一次就能自愈的那类错。"""
    if type(e).__name__ in ("PageDisconnectedError", "BrowserConnectError", "ContextLostError"):
        return True
    s = str(e)
    return any(k in s for k in ("连接已断开", "已关闭", "连接失败", "页面被关闭", "没连上"))


# 任务列表里的状态词。只认「已取消/已停止」这类完成态，不认光秃秃的「取消/停止」——
# 任务项里常常挂着一颗「取消」按钮，把按钮字当成状态会在任务还在跑时误判失败。
# 一条任务里同时出现好几种词时（「生成中 …取消」「排队中 …上次失败记录」），
# 按「最先出现的那个词」定性，运行中的词压过失败词：人在任务列表里看到「运行中」
# 就判失败，会把还在跑的那段白白重启重交一遍。
_TASK_RUN_KW = ("生成中", "运行中", "采样中", "排队", "队列", "等待",
                "running", "queued", "pending", "wait")
_TASK_FAIL_KW = ("失败", "错误", "异常", "已取消", "取消中", "已停止", "已中止",
                 "中断", "failed", "error")
_TASK_DONE_KW = ("已完成", "完成", "成功", "completed", "success")
# 「未完成」「尚未成功」这类否定说法不算完成也不算失败：前面带这些字就当没看见
_TASK_NEG = "未不没无非"


_TASK_WORDS = (
    tuple((w, "run") for w in _TASK_RUN_KW)
    + tuple((w, "fail") for w in _TASK_FAIL_KW)
    + tuple((w, "done") for w in _TASK_DONE_KW)
)


def _tid_num(v):
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return 0


def _task_word(text):
    """从一串状态文本里挑出「这段任务自己的状态」：最先出现的那个状态词。

    整串里到处扫失败词会误伤（按钮字、旧记录、节点名都带「错误/取消」），
    所以只取第一个命中的词；同一位置命中多个就取最长的那个（「已完成」优先于「完成」）。
    读不出状态词回空串——空串意味着「不知道」，不能拿去判失败。
    """
    s = str(text or "").lower()
    hit = None
    for kw, _kind in _TASK_WORDS:
        k = kw.lower()
        i = s.find(k)
        while i >= 0 and (i > 0 and s[i - 1] in _TASK_NEG):   # 「未完成」「没有错误」不算
            i = s.find(k, i + 1)
        if i < 0:
            continue
        if hit is None or (i, -len(k)) < hit[:2]:
            hit = (i, -len(k), kw)
    return "" if hit is None else hit[2]


def _task_kind(word):
    """状态词属于哪一类："" / "run"（还在跑或排着）/ "fail" / "done"。"""
    w = str(word or "")
    if w in _TASK_RUN_KW:
        return "run"
    if w in _TASK_FAIL_KW:
        return "fail"
    if w in _TASK_DONE_KW:
        return "done"
    return ""


def _task_failed(text):
    return _task_kind(_task_word(text)) == "fail"


def _task_running(text):
    return _task_kind(_task_word(text)) == "run"


def _task_done(text):
    return _task_kind(_task_word(text)) == "done"


def pick_size(w, h):
    """把界面的 WxH 翻成云端那四件套：档位标签 + 画幅 + 宽 + 高。

    线上实测（scripts/h3_cloud_probe.py --size）：改 resolution / aspect_ratio 之后，
    序列化里的 width/height 一动不动——那两颗档位控件只是标签，真出片按 width/height 走
    （实测提交 848×480，回来的文件就是 848×480）。所以宽高我们自己算、自己写，
    档位只按界面口径（P=短边）标一个名，凑不出的就写 Custom，不猜平台的公式。
    """
    # 与 App._snap32、界面 C.a32 同一套舍入（Python 的 round 是 .5 向偶数，会差一格）。
    # H3 的 latent 再按 2×2 切 patch，宽高必须落在 32 网格上，和本地那条共用一套格子。
    # 档位名照界面给的短边算：720→736 之后仍叫 720P，不能因为贴格变成 Custom。
    # 上限 2560：云端出片尺寸由我们写进 width/height，官方最高 2K＝短边 1440（长边 2560）。
    snap = lambda x: max(32, min(2560, int(float(x) / 32.0 + 0.5) * 32))
    short_in = min(w, h)
    w, h = snap(w), snap(h)
    tier = min(TIERS, key=lambda t: abs(t - short_in))
    orient = "s" if w == h else ("h" if w > h else "v")
    return {"resolution": "%dP" % tier if tier == short_in else "Custom",
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
        # 平台标了失败要连着看这么久才收手：页面重渲染、DOM 只挂上半截都能瞬时报错，
        # 一次读到就判死会把还在跑的那段重启重交一遍。
        self.fail_confirm = max(0, int(self.cfg.get("fail_confirm_sec") or 15))
        # 灌完图后画布的读数还要稳这么久：平台自己那张图后到会把本地这份盖掉
        self.wf_settle = max(0, min(60, int(self.cfg.get("wf_settle_sec") or 6)))
        self.tag = str(self.cfg.get("exec_tag") or "Plus")
        self.has_editor = False
        self.shape = SHAPE_FH          # 这一张到底是哪种画法：feihou 还是虚拟节点那张
        self.wf_title = ""
        self._task_id = ""          # 本段提交后从任务列表认领到的 taskid

    # ---------- 账号与工作流 ----------
    def account(self, aid=""):
        # state=fail 是成片里两次都没出成的号：跳过它，直到人重新保存登录态。
        rows = [a for a in self.store.list()
                if (self.store.load(a["id"]) or {}).get("cookies")
                and str(a.get("state") or "") != "fail"]
        if not rows:
            raise CloudError("没有可用的登录账号：到「环境管理 → 云端账号」新建登录并保存"
                             "（标成「出片失败」的号要重新登录或换号）")
        if aid:
            for a in rows:
                if a["id"] == aid:
                    return a
            other = self.store.get(aid)
            if other and str(other.get("state") or "") == "fail":
                raise CloudError("这个号上次出片失败已被跳过：到「环境管理 → 云端账号」"
                                 "重新登录保存，或换一个号")
            raise CloudError("这个账号还没有保存过登录态")
        return rows[0]

    def wf_id(self, wf=""):
        s = str(wf or "").strip()
        if s:
            return wf_id_of(s) or wf_id_of(self.cfg.get("default_wf")) or DEFAULT_WF
        choice, custom = wf_choice(self.cfg)
        if choice == "goldfish":
            return GOLDFISH_WF
        if choice == "custom":
            return wf_id_of(custom) or wf_id_of(self.cfg.get("default_wf")) or DEFAULT_WF
        return DEFAULT_WF

    def wf_url(self, wf=""):
        return WF_URL % self.wf_id(wf)

    def wf_src(self, wf=""):
        """这份工作流从哪儿来：("file", 本地路径) 或 ("remote", 平台编号/地址)。

        判据只认结尾是不是 .json/.txt——平台上「导出工作流」存下来就是这份；
        导出的 JSON 里不带工作流编号（实测只有一个随机 uuid），所以本地那份
        还得借一个平台页进去跑，见 host_url。

        界面上选「默认」/「金鱼」就走两张内置画布；选「指定地址」才读 workflow 那格。
        没选过（老配置）就有地址按自定义、没有按默认，见 wf_choice。
        """
        s = str(wf or "").strip()
        if not s:
            choice, custom = wf_choice(self.cfg)
            if choice == "goldfish":
                return ("remote", WF_URL % GOLDFISH_WF)
            if choice == "custom":
                s = custom
                if not s:
                    raise CloudError("工作流选了「%s」，但那一格还没填地址或文件"
                                     % WF_CUSTOM_NAME)
            else:
                return ("remote", WF_URL % DEFAULT_WF)
        if re.search(r"\.json$|\.txt$", s, re.I):
            path = self._ref(s)
            if not path:
                raise CloudError("本地工作流文件找不到：%s" % s[:80])
            return ("file", path)
        return ("remote", s)

    def wf_label(self, kind="", src=""):
        """这一张在界面上怎么称呼：两张内置画布点名，本地那份只报文件名。"""
        if not src:
            kind, src = self.wf_src()
        if kind == "file":
            return "本地 · %s" % os.path.basename(src)
        wid = wf_id_of(src)
        if wid == DEFAULT_WF:
            return "默认 · %s" % LEGACY_WF_NAME
        if wid == GOLDFISH_WF:
            return "金鱼 · %s" % GOLDFISH_WF_NAME
        return "平台 · %s" % (wid or src[:40])

    def host_url(self):
        """本地那份借哪一页进去：手动覆盖 → 平台默认 → 默认那张 → 内置那一页。

        换的是画布上那张图，跑它的还是那台实例——「换图不换实例」。
        入口页只是跳板，真跑的一定是灌进去的那张画布。
        """
        for cand in (self.cfg.get("wf_host"), self.cfg.get("default_wf"),
                     DEFAULT_WF, HOST_WF_FALLBACK):
            s = str(cand or "").strip()
            if re.search(r"\.json$|\.txt$", s, re.I):
                continue          # default_wf 被人填成本地文件时别把路径当编号拼进 URL
            # 三种平台地址写法（/workflow/、/ai-detail/、/ai-detail/<类型>/）都提得出一样的编号
            wid = wf_id_of(s)
            if wid:
                return WF_URL % wid
        return ""

    # ---------- 灌本地工作流 ----------
    def check_wf_file(self, path):
        return check_workflow_json(path)

    def _wait_frontend(self, tab, fid, stop, limit=40):
        """等前端真正能接图：loadGraphData 是函数只是第一道，graph 也得挂上。"""
        for _ in range(limit * 2):
            if stop and stop():
                raise CloudError("已停止")
            try:
                if self.js(tab, _JS_FRONTEND_READY, fid):
                    return
            except Exception:
                pass
            time.sleep(0.5)
        raise CloudError("云端编辑器还没挂好：等不到画布，重开这段再试")

    def _load_once(self, tab, fid, txt, stop, meta, limit=25, settle=6):
        """灌一次并等结果（同步/异步都接）：回 (ids, 错误串)。

        settle：loadGraphData 已经回执成功、画布上的节点却还差一批时再等这么久的
        读数。平台自己那张图是异步挂上来的，它后到就会把我们灌的那份盖掉——
        一次读数就判死，整批会被按「工作流加载不上」暂停（真机踩过）。
        """
        from .store import brief_error
        try:
            d = json.loads(self.js(tab, _JS_LOAD_WF, fid, txt) or "{}")
        except ValueError:
            return None, "页面没回话"
        except Exception as e:
            return None, brief_error(e, 80)
        if d.get("err"):
            return None, str(d["err"])
        t0 = time.time()
        short_at, short_msg = None, ""
        while time.time() - t0 < limit:
            if stop and stop():
                raise CloudError("已停止")
            try:
                st = json.loads(self.js(tab, _JS_WF_STATE, fid) or "{}")
            except ValueError:
                st = {}
            except Exception:
                st = {}
            state = st.get("state")
            if state == "err":
                return None, str(st.get("msg") or "前端加载工作流失败")
            if state == "ok":
                got = set(str(x) for x in (st.get("ids") or []))
                missing = meta["ids"] - got
                if missing:
                    short_msg = ("文件里 %d 个节点，画布只认到 %d 个（缺 %d）"
                                 % (len(meta["ids"]), len(got), len(missing)))
                    if short_at is None:
                        short_at = time.time()
                    elif time.time() - short_at >= settle:
                        return None, short_msg
                elif not st.get("main") or not st.get("out"):
                    return None, "图上没有 H3 主节点/输出节点"
                else:
                    return {"main": st.get("main"), "out": st.get("out"),
                            "shape": st.get("shape") or SHAPE_FH,
                            "nodes": len(got)}, ""
            time.sleep(0.5)
        return None, short_msg or "等 %d 秒也没把工作流挂到画布上" % limit

    def load_local_wf(self, tab, fid, path, stop, limit=30):
        """把本地 JSON 灌进页面，再按类型重新认主节点/输出节点（那张图的 id 未必是 389）。"""
        from .store import brief_error
        meta = self.check_wf_file(path)
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                txt = f.read()
        except Exception as e:
            raise CloudError("本地工作流文件读不了：%s" % brief_error(e, 80))
        last = ""
        for attempt in (0, 1, 2):
            self._wait_frontend(tab, fid, stop)
            ids, err = self._load_once(tab, fid, txt, stop, meta, settle=self.wf_settle)
            if ids:
                # 内置默认那张在界面上说人话，别摆出安装目录里的一长串
                self.wf_title = self.wf_label("file", path)
                self.shape = str(ids.get("shape") or SHAPE_FH)
                self.log("· 灌入工作流「%s」：节点 %s 个 · 主节点 %s · 输出节点 %s"
                         % (os.path.basename(path), ids["nodes"], ids["main"], ids["out"]))
                return ids
            last = err
            # 前端偶发处在半初始化/上一张图还没清完：先在这张页面原地再灌一次
            # （多数是平台自己那张图后到、把我们的盖掉，重灌一次就压住它），
            # 还不行才整页重开；最后一次仍失败就停——不拿画布上残留的旧图继续提交。
            if attempt == 0:
                self.log("· 工作流没灌上（%s）：这张页面再灌一次" % str(err)[:60])
                time.sleep(1.5)
                continue
            if attempt == 1:
                self.log("· 还是灌不上（%s）：重开页面再试一次" % str(err)[:60])
                try:
                    tab.refresh()
                except Exception as e:
                    raise CloudError("工作流没灌上，重开页面也失败：%s" % brief_error(e, 60))
                fid = self._wait_frame(tab, stop)
        msg = str(last or "未知原因")
        if "setGraph" in msg:
            raise CloudError("云端 ComfyUI 前端没接住这份工作流（setGraph）：多半是这份导出"
                             "和当前前端版本不合。先在网页里手动打开它，能正常显示再点开始；"
                             "还报错就重新「导出工作流」一次")
        raise CloudError("云端前端没能加载这份工作流：%s" % msg[:120])

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
        """p：{prompt, seconds, width, height, refs, wf, acct}；回本地 mp4 路径。

        refs 是参考图列表，顺序即编号（第 1 张 = @1）。p["first"] 是老调用方的
        单图写法，仍然认。不只一张时必须走 chip 引用，否则模型分不清谁是谁。
        """
        row = self.account(p.get("acct"))
        aid = row["id"]
        state = self.store.load(aid)
        self._task_id = ""          # 这一段的 taskid 从提交后重新认领
        kind, src = self.wf_src(p.get("wf"))
        secs = max(5, min(15, int(p.get("seconds") or 5)))
        size = pick_size(int(p.get("width") or 768), int(p.get("height") or 768))
        raw = p.get("refs")
        if isinstance(raw, str):
            raw = [raw]
        raw = [x for x in (raw or []) if str(x or "").strip()]
        if not raw and p.get("first"):
            raw = [p.get("first")]
        refs = [self._ref(str(x)) for x in raw]
        lost = sum(1 for x in refs if not x)
        if lost:
            raise CloudError("有 %d 张参考图找不到了：先在界面上重新选一遍" % lost)
        if not refs:
            # 这份节点只有「图生/首尾帧」和「参考生视频」两种，没有纯文字模式。
            # 不给图就交上去，平台会当场判「参考生视频未收到图片或视频」——先在这里说清。
            raise CloudError("云端这份 H3 工作流按参考生成：先在「参考图」那格选图，"
                             "纯文字它不接")
        if len(refs) > mention.MAX_REFS:
            raise CloudError("参考图最多 %d 张：现在给了 %d 张"
                             % (mention.MAX_REFS, len(refs)))
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
                shape = str(ids.get("shape") or SHAPE_FH)
                self.shape = shape
                kmap = None
                if shape == SHAPE_KJ:
                    # 新形状没有提示词编辑器可等，也没有 feihou 那串属性可看：
                    # 要等的是接线——谁喂主节点的提示词、谁喂时长和尺寸。
                    kmap = self._kj_map(tab, fid)
                else:
                    self._wait_editor(tab, fid, should_stop)
                    self._log_shape(tab, fid, ids["main"])
                self._p(on_progress, should_stop,
                        "云端：上传参考图（%d 张）…" % len(refs))
                media = []
                for i, path in enumerate(refs, 1):
                    fn, sub = self.upload(path, state)
                    media.append(self.media_item(fn, sub, i))
                if shape == SHAPE_KJ:
                    slots = kmap.get("slots") or {}
                    gap = [i for i in range(1, len(refs) + 1) if i not in slots]
                    if gap:
                        raise CloudError("这张图只留着 %d 个参考图槽位，第 %s 号被旁路了："
                                         "少给几张图或换一张图"
                                         % (len(slots), "、".join(str(x) for x in gap)))
                    try:
                        prompt_text, _pics = mention.picture_text(
                            str(p.get("prompt") or ""), len(refs))
                    except ValueError as e:
                        raise CloudError(str(e))
                    files = [(i, slots[i],
                              ("%s/%s" % (sub, fn)) if sub else fn)
                             for i, m in enumerate(media, 1)
                             for fn, sub in [(m["filename"], m["subfolder"])]]
                    self._p(on_progress, should_stop, "云端：写入参数…")
                    self._write_kj(tab, fid, ids, kmap, prompt_text, secs, size, files)
                else:
                    try:
                        prompt_html, chips = mention.render_prompt(
                            str(p.get("prompt") or ""), media)
                    except ValueError as e:
                        raise CloudError(str(e))
                    spec = {
                        "prompt": str(p.get("prompt") or ""),
                        # 有 chip 时编辑器写 HTML；单图且没写编号时留空，走原来的纯文本通路
                        "prompt_html": prompt_html or "",
                        "chips": chips,
                        "media": media,
                        # 画廊预览：H3yun 每段都写这一份；少了它画廊不按新图刷新
                        "preview": {"shown": {"aspect_ratio": size["aspect_ratio"],
                                              "fps": 24, "resolution": size["resolution"]},
                                    "fallback": {"aspect_ratio": size["aspect_ratio"],
                                                  "fps": 24}},
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
                    self._write(tab, fid, ids, spec, secs, size)
                base_name = self._filename(tab, fid, ids["out"])
                self._p(on_progress, should_stop, "云端：提交任务…")
                hist0 = self.history_count(tab, fid)   # 提交前有几条，之后才知道多没多
                known = self.known_task_ids(tab)      # 提交前任务列表上已有的，几秒后才多出我们这条
                hit = self._submit(tab, should_stop)
                self._p(on_progress, should_stop,
                        "云端：已提交（%s）…" % hit.replace("clicked ", "").strip())
                tid = self.capture_task_id(tab, known, should_stop)
                if tid:
                    self._p(on_progress, should_stop,
                            "云端：任务列表已认领 taskid %s" % tid)
                cos, fname = self._wait_result(tab, fid, ids["out"], base_name,
                                               on_progress, should_stop, hist0,
                                               known, tid)
            except CloudError:
                raise
            except Exception as e:
                # 生成中途窗口被关掉：平台上可能还在跑，别把原生异常甩给界面
                if browser_gone(e):
                    raise CloudError("浏览器窗口被关掉了：这一段没跑完。"
                                     "平台上可能还在跑，去「环境管理 → 云端账号」看一眼；"
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
                return {"main": d["main"], "out": d["out"],
                        "nodes": d.get("nodes"),
                        "shape": d.get("shape") or SHAPE_FH}
            time.sleep(3)
        raise CloudError("图加载完但没找到 H3 主节点/输出节点：这份工作流不是 H3 成片图"
                         "（要 %s 或 %s 那两种画法之一）" % (MAIN_TYPE, MAIN_TYPE_KJ))

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

    def media_item(self, name, sub, ordinal=1):
        """一条媒体引用，字段固定成 H3yun 实机验证过的那一份。

        ordinal 从 1 递增，和提示词里的 @1/@2 一一对应；多图时必须连续，
        否则 By index 会把编号对到别的图上。
        """
        return {"media_type": "image", "ordinal": int(ordinal), "filename": name,
                "subfolder": sub or "", "storage": "input", "audio_trim": ""}

    def _write(self, tab, fid, ids, spec, secs, size):
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
        mine_media = list(spec.get("media") or [])
        want_slots = len(mine_media)
        want_chips = int(spec.get("chips") or 0)
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
        # 序列化里的媒体必须逐条对上刚上传的那一组：只比第一张会把
        # 「后面几张还是旧模板的图」放过去，节点执行时照样串味。
        if want_slots:
            got = c.get("mediaAll") if isinstance(c.get("mediaAll"), list) else []
            if not got:
                m0 = c.get("media0") if isinstance(c.get("media0"), dict) else {}
                got = [m0] if m0 else []
            if len(got) != want_slots:
                bad.append("序列化里 %d 条媒体（该 %d 条）" % (len(got), want_slots))
            for i, mine in enumerate(mine_media[:len(got)]):
                seen = got[i] if isinstance(got[i], dict) else {}
                if str(seen.get("filename") or "") != str(mine.get("filename") or ""):
                    bad.append("第 %d 张参考图没换成新图（%s）"
                               % (i + 1, str(seen.get("filename") or "")[:24]))
                try:
                    seen_ord = int(seen.get("ordinal") or 0)
                except (TypeError, ValueError):
                    seen_ord = -1
                if seen_ord != int(mine.get("ordinal") or 0):
                    bad.append("第 %d 张 ordinal=%s（该 %s）"
                               % (i + 1, seen.get("ordinal"), mine.get("ordinal")))
                if str(seen.get("storage") or "input") != "input":
                    bad.append("第 %d 张 storage=%s" % (i + 1, seen.get("storage")))
        # 画廊是节点自己的账本：序列化对了但画廊空着，说明节点没认这份媒体
        if want_slots and int(c.get("gallery") or 0) < want_slots:
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
                bad.append("画廊里只有 %s 张参考图（该 %d 张）"
                           % (c.get("gallery"), want_slots))
        # 多图必须把编号以 chip 形式写进编辑器；chip 数只许多不许少。
        # 少了说明编号被当普通文字，模型不知道第几张图是谁——这一段白跑。
        if want_chips and int(c.get("chips") or 0) < want_chips:
            bad.append("提示词里的 @编号没变成引用（chip %s 个，该 %d 个）"
                       % (c.get("chips"), want_chips))
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
        # 钱照扣、出的却是别人的片子。有 chip 时序列化里是占位符，按 chip 数判；
        # 纯文本（单图）仍按开头那段字比对。
        if not want_chips:
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

    # ---------- 新形状（虚拟节点那张）：认接线 → 照清单写 → 对序列化 ----------
    def _kj_map(self, tab, fid):
        """顺着 SetNode/GetNode 把「能写的节点」认出来。认不到就停，不拿默认值瞎写。"""
        from .store import brief_error
        try:
            raw = self.js(tab, _JS_KJ_MAP, fid)
        except Exception as e:
            raise CloudError("读这张图的接线失败：%s" % brief_error(e, 80))
        try:
            d = json.loads(raw or "{}")
        except ValueError:
            raise CloudError("读这张图的接线：页面回的不是 JSON")
        if d.get("err"):
            raise CloudError("这份工作流不是能写的 H3 图：%s" % str(d["err"])[:80])
        roles = d.get("roles") or {}
        miss = [k for k in ("prompt", "length", "width", "height") if k not in roles]
        if miss:
            raise CloudError("主节点上没有 %s 这几个入参：这张图的写法软件还不认"
                             % "、".join(miss))
        for k in ("prompt", "length", "width", "height"):
            src = str((roles[k] or {}).get("src") or "")
            if src not in ("direct", "text", "prim", "res"):
                raise CloudError("主节点的 %s 是从「%s」接过来的，这一种还没学会写"
                                 % (k, src or "未知节点"))
        slots = {}
        for x in d.get("images") or []:
            m = re.search(r"(\d+)", str(x.get("name") or ""))
            if not m or int(x.get("mode") or 0) != 0:
                continue        # 旁路掉的槽位不能挂图，作者就是这么留空档的
            slots.setdefault(int(m.group(1)), int(x["id"]))
        d["slots"] = slots
        self.log("· 接线：提示词→%s(%s) · 时长→%s(%s) · 尺寸→%s(%s) · 参考图槽 %d 个"
                 % ((roles["prompt"] or {}).get("id"), (roles["prompt"] or {}).get("src"),
                    (roles["length"] or {}).get("id"), (roles["length"] or {}).get("src"),
                    (roles["width"] or {}).get("id"), (roles["width"] or {}).get("src"),
                    len(slots)))
        return d

    def _kj_writes(self, map, prompt, secs, size):
        """按接线算出要写的每一格：[节点 id, 控件名, 值, 必须是合法选项, 标签]。"""
        r = map.get("roles") or {}
        w = []
        p = r.get("prompt") or {}
        w.append([p.get("id"), p.get("w"), prompt, False, "prompt"])
        # 时长挂在 PrimitiveFloat 上时写的是秒数——它后面那条数学式自己换成帧数；
        # 主节点那一格没连线才由我们直接写帧数（照作者那条式子的口径）。
        l = r.get("length") or {}
        w.append([l.get("id"), l.get("w"),
                  secs if l.get("src") != "direct" else kj_frames(secs),
                  False, "seconds"])
        wd, hg = r.get("width") or {}, r.get("height") or {}
        if (wd.get("src") == "res" and hg.get("src") == "res"
                and wd.get("id") == hg.get("id")):
            label = ratio_label(map.get("aspect"), size["aspect_ratio"])
            if not label:
                raise CloudError("这张图的尺寸选择器里没有 %s 画幅（它给的是 %s）："
                                 "换个画幅或换一张图"
                                 % (size["aspect_ratio"],
                                    "、".join(str(x) for x in (map.get("aspect") or [])[:6])))
            w.append([wd.get("id"), "aspect_ratio", label, True, "aspect"])
            w.append([wd.get("id"), "megapixels",
                      snap_megapixels(megapixels_of(size["width"], size["height"]),
                                      map.get("res")), False, "megapixels"])
        else:
            w.append([wd.get("id"), wd.get("w"), size["width"], False, "width"])
            w.append([hg.get("id"), hg.get("w"), size["height"], False, "height"])
        return w

    def _write_kj(self, tab, fid, ids, map, prompt, secs, size, files):
        """files 是 [(序号, 节点 id, 文件名)]：先照清单落值，再拿序列化结果对账。"""
        writes = self._kj_writes(map, prompt, secs, size)
        names = []
        for n, nid, fn in files:
            tag = "图%d" % n
            writes.append([nid, "image", fn, False, tag])
            names.append((tag, fn))
        spec = {"writes": writes,
                # 对账用的两串：提示词开头那段 + 每张图的文件名（按序号排）
                "frag": str(prompt or "")[:24],
                "files": [fn for _tag, fn in names]}
        try:
            raw = self.js(tab, _JS_KJ_WRITE, fid, ids["main"],
                          json.dumps(spec, ensure_ascii=False))
        except Exception as e:
            from .store import brief_error
            raise CloudError("写入节点出错：%s" % brief_error(e, 80))
        try:
            d = json.loads(raw or "{}")
        except ValueError:
            raise CloudError("写入节点的返回读不懂：%s" % str(raw)[:160])
        if d.get("err"):
            raise CloudError("写入失败：%s" % d["err"])
        c = d.get("check") or {}
        if c.get("err"):
            raise CloudError("提交前自检读不到序列化结果（%s）：不敢盲提交"
                             % str(c.get("err"))[:80])
        for x in (d.get("warn") or []):
            self.log("· 接线提醒：%s" % str(x)[:80])
        bad = list(d.get("bad") or [])
        seen = c.get("seen") or {}
        if str(seen.get("prompt") or "")[:24] != str(prompt or "")[:24]:
            bad.append("提示词写不进那格（回读「%s」）" % str(seen.get("prompt"))[:24])
        if prompt and not c.get("prompt"):
            bad.append("提示词没进序列化：交上去的还是这张图原来那段话")
        if str(seen.get("seconds")) != str(secs):
            bad.append("时长没进去（回读 %s，该 %s）" % (seen.get("seconds"), secs))
        for i, ok in enumerate(c.get("files") or []):
            if not ok:
                bad.append("第 %d 张参考图没进序列化" % (i + 1))
        if bad:
            raise CloudError("提交前自检没过：%s" % "、".join(str(x)[:60] for x in bad[:6]))
        # 尺寸只提醒不拦：这一档差半格就差了，不至于废片
        if "aspect" in seen:
            # 走分辨率选择器时，主节点那两格是被连线盖住的旧值，不能拿它当回报；
            # 照选择器自己的口径（百万像素 × 画幅 × multiple）推出真正会出的那对宽高。
            ow, oh = kj_out_size(seen.get("megapixels"), size["aspect_ratio"],
                                 map.get("multiple"))
            if (ow, oh) != (size["width"], size["height"]):
                self.log("· 画幅 %s · %d 秒 · 出片 %dx%d（界面写的 %dx%d，"
                         "这张图的尺寸档只到这一格）"
                         % (seen.get("aspect"), secs, ow or size["width"],
                            oh or size["height"], size["width"], size["height"]))
            else:
                self.log("· 画幅 %s · %d 秒 · 出片 %dx%d"
                         % (seen.get("aspect"), secs, ow, oh))
        else:
            for k in ("width", "height"):
                if c.get(k) not in (None, size[k]):
                    self.log("· 主节点读回的 %s=%s，界面写的是 %s：这一段出片尺寸会和界面不一样"
                             % (k, c.get(k), size[k]))
        return d

    def _filename(self, tab, fid, out):
        try:
            return str(json.loads(self.js(tab, _JS_RESULT, fid, out) or "{}")
                       .get("filename") or "")
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

        读不到回 None＝基线不可信：之后不许拿「比基线多了一条」判跑完或判失败。
        「读到 0 条」同样算不可信——页面那栏还没挂起来时量到的也是 0，
        跟这个号真的一条历史都没有分不开；拿这种 0 当基线，等列表一渲染出来就
        会把上一段的旧记录读成「我们这段跑完了」，然后催 90 秒收尾、报生成失败。
        """
        try:
            raw = self.js(tab, _JS_PROGRESS, fid)
            d = json.loads(raw) if raw else {}
            n = int((d.get("h") or {}).get("n") or 0)
            return n or None
        except Exception:
            return None

    def task_entries(self, tab):
        """平台右侧任务列表：去重后按 taskid 从新到旧。读不到回空（不猜）。

        同一条可能同时出现在「当前」和「历史」里，按 taskid 去重，只留最先读到的那份。
        """
        try:
            raw = self.js(tab, _JS_TASKS)
            if not raw:
                return {}
            d = json.loads(raw)
        except Exception:
            return {}
        if not isinstance(d, dict):
            return {}
        seen, items = set(), []
        for k in ("cur", "his"):
            for x in d.get(k) or []:
                if not isinstance(x, dict):
                    continue
                tid = str(x.get("id") or "")
                if not tid or tid in seen:
                    continue
                seen.add(tid)
                items.append(x)
        items.sort(key=lambda x: _tid_num(x.get("id")), reverse=True)
        return {"items": items}

    def known_task_ids(self, tab):
        """提交前已经在那张列表上的 taskid：之后多出来的那条才是我们这段。

        回 None ＝ 基线不可信，之后不许拿新旧差集判失败、也不许拿「新出现」认领。
        除了读不到，「读到但一条都没有」也算不可信：右侧那栏还没挂起来时
        量到的同样是空，跟「平台上真的一条任务都没有」分不开——
        这时候拿差集去判失败，认到的多半是上一段那条旧记录。
        """
        d = self.task_entries(tab)
        if not d:
            return None
        ids = {str(x.get("id")) for x in (d.get("items") or []) if x.get("id")}
        return ids or None

    def capture_task_id(self, tab, known, stop=None, limit=40):
        """提交后从任务列表认领我们这一段的 taskid。

        每只浏览器同一时刻只有我们在提交，所以「提交后新出现的那条」就是，
        取 taskid 最大的那条。提交前基线没读到（known 为空）时只认「在跑/排队」
        的新条目，免得把列表里旧的失败记录当成这一段。
        只读着「失败」的条目一律不认领：认领错了，之后每次轮询都盯着那条旧账，
        还在跑的这一段会被一路判成失败。真失败了还有差集那条路能认出来。
        """
        trusted = known is not None        # None＝基线没读到或一条都没有，不可信
        known = {str(x) for x in (known or ())}
        t0 = time.time()
        hit = ""
        while time.time() - t0 < limit:
            if stop and stop():
                return ""
            items = self.task_entries(tab).get("items") or []
            new = [x for x in items if x.get("id") and str(x["id"]) not in known]
            if new:
                txt = lambda x: x.get("s") or x.get("d")
                running = [x for x in new if _task_running(txt(x))]
                fresh = [x for x in new if not _task_failed(txt(x))]
                cand = running or (fresh if trusted else [])
                if cand:
                    best = max(cand, key=lambda x: _tid_num(x.get("id")))
                    hit = str(best.get("id") or "")
                    if running or len(cand) == 1:
                        break
            time.sleep(1.5)
        if hit:
            self._task_id = hit
            self.log("· 任务列表认领 taskid %s" % hit)
        return hit

    def platform_state(self, tab, fid, waited, hist0=None, known=None, task_id=""):
        """平台上这一段到底到哪一步了——一句话，读不到就回空串（绝不编一个）。

        时间波动很大（实测同参数一段 353 秒出片、一段排到二十分钟没动），
        只报「已等 N 秒」人分不清排队/在跑/已失败，所以去问平台自己：
        右侧任务列表（taskid + 状态 + 计时，最准）、页面内存里的队列、GET /history 的条数。
        hist0 = 提交那一刻的历史条数（None＝没读到，不可信）；
        known = 提交前列表上已有的 taskid（同上，None＝不可信）；
        task_id = 提交后认领到的本段 taskid——三个都只用来认出「我们这一段」。
        """
        # 先看任务列表：它直接写着「生成中 04:02」「任务失败」，比队列更有信息量。
        # 认领到 task_id 就只按那一条判；没认领到才用 known 差集，绝不拿旧失败顶账。
        # known 是 None ＝ 提交前那张列表根本没读到，差集不可信，一律不拿来判失败
        # （否则旧那条失败记录会被当成我们这段，还在跑的号白白重交一遍）。
        tasks = self.task_entries(tab) if (known is not None or task_id) else {}
        items = list(tasks.get("items") or [])
        base = {str(x) for x in (known or ())}
        my = None
        if task_id:
            my = next((x for x in items
                       if str(x.get("id")) == str(task_id)), None)
        if my is None and known is not None and not task_id:
            new = [x for x in items
                   if x.get("id") and str(x["id"]) not in base]
            running = [x for x in new if _task_running(x.get("s") or x.get("d"))]
            if running:
                my = running[0]
            elif len(new) == 1:
                my = new[0]
        if my is not None:
            s = str(my.get("s") or "").strip()
            det = str(my.get("d") or "").strip()
            tm = str(my.get("time") or "").strip()
            tid = str(my.get("id") or "")
            extra = (" · 已运行 " + tm) if (tm and tm not in s) else ""
            # 状态元素里没字就去整条里找：列表把状态和计时写在两处时也能认出来。
            w = _task_word(s) or _task_word(det)
            kind = _task_kind(w)
            if kind == "run":
                # 列表自己写着在跑/排队 —— 这一句压过所有失败判断，宁可多等不重交
                return "平台上这一段：" + (s or w) + extra + " · taskid " + tid
            if kind == "done":
                return "平台说这段跑完了，可输出节点还没刷新 · taskid " + tid
            if kind == "fail":
                # 把状态字顶在前面：日志里只留整条文本时，分不清是「状态＝失败」
                # 还是卡片上挂着一颗「安审失败/重试」的标签——上一轮就为这个吵过。
                bits = []
                if s:
                    bits.append("状态「%s」" % s)
                if det and det != s:
                    bits.append(det[:120])
                return "平台判失败：" + (" · ".join(bits) or w) + " · taskid " + tid
            # 一个状态词都没读到：只认容器里明确的「任务失败/生成失败」，
            # 不拿一个孤零零的「错误」去猜（旁边可能有「错误」按钮/标签）。
            if re.search(r"(任务失败|生成失败|执行失败|运行失败|出错了)", det):
                return "平台判失败：" + det + " · taskid " + tid
            if s:
                return "平台上这一段：" + s + extra + " · taskid " + tid
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
        new = hist0 is not None and (h.get("n") or 0) > int(hist0 or 0)   # 多出一条＝这条是我们那段
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
            return "平台把这段判了失败：去平台上那一页看原因" + btn
        # 「队列空了」是一句有分量的话：只有真读到过那个队列对象才可以说。
        # keys 是对象自己的字段名——读回来个空壳（{}），形状和「空队列」一模一样，
        # 但那是不知情，不是空。
        if q and q.get("keys") and waited > 60:
            if new and last.get("c"):
                return "平台说这段跑完了，可输出节点还没刷新：去平台上看一眼" + btn
            if new:
                return "平台已经收下这段，还在它那边跑" + btn
            # 队列里没它、历史里也没多出来：平台上看不见这段任务。
            # 说「队列已空」太像「已经失败了」，实测提交后头几分钟就是这个状态，
            # 说「查不到、可能在它自己的池子里排队」才是当时能给出的最大信息量。
            return "平台上查不到这段任务" + btn + "：可能在它自己的池子里排队"
        return ""

    def _wait_result(self, tab, fid, out, base_name, cb, stop, hist0=None, known=None,
                     task_id=""):
        t0 = time.time()
        seen = ""
        note = ""
        where = ""
        done_at = fail_at = 0.0
        while time.time() - t0 < self.timeout:
            if stop and stop():
                raise CloudError("已停止：云端那半段还在跑，下次进来能在平台上看到")
            try:
                d = json.loads(self.js(tab, _JS_RESULT, fid, out) or "{}")
            except ValueError:
                d = {}
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
            where = self.platform_state(tab, fid, int(time.time() - t0),
                                        hist0, known, task_id)
            # 平台自己把它标成失败了：再等下去多半也只是等超时。
            # 但不许一次读到就收手——连着读到 fail_confirm 秒才算数，
            # 中间只要有一次又看到「生成中/排队」，立刻清零接着等。
            if "平台判失败" in where:
                if not fail_at:
                    fail_at = time.time()
                left = int(round(self.fail_confirm - (time.time() - fail_at)))
                if left <= 0:
                    raise CloudError(where)
                note = "平台刚标了失败，先等 %d 秒再确认（页面刷新会瞬时报错）" % max(0, left)
            else:
                fail_at = 0.0
                note = ""
            # 平台说跑完了、输出节点却一直不刷新：给 90 秒收尾，再等就是空耗
            if "跑完了" in where or "输出节点还没刷新" in where:
                if not done_at:
                    done_at = time.time()
                elif time.time() - done_at > 90:
                    raise CloudError(where + "：平台说跑完了但成片一直没取回来，"
                                     "去平台上那一页确认；没出就点重出这一段")
            else:
                done_at = 0.0
            if cb:
                waited = int(time.time() - t0)
                left = int(self.timeout - waited)
                # 确认那句放最前：界面那行只留前 120 字，堆在尾巴上等于没说
                cb(" · ".join(x for x in (note or "云端出片中…已等 %d 秒（剩 %d 秒超时）"
                                          % (waited, max(0, left)), where, seen) if x))
            time.sleep(self.poll_min)
        # 收尾那句得带上「我们到底看见了什么」：只说「等超时」等于没交代，
        # 而平台上查不到这段＝多半根本没提交成功，是另一件事。
        return self._timeout_err(where, seen)

    def _timeout_err(self, where, seen):
        hint = ""
        w = where or ""
        if "平台判失败" in w:
            # 失败读到但没连续够：不是替它脱罪，是别拿一次瞬时读数重交一遍还在跑的段
            hint = "（列表一路把它标成失败，但没连续读到确认那么久：点开那一条看节点报错）"
        elif "查不到" in w:
            # 实测这段并不等于「没提交上」：同参数的第一段 353 秒出了片，
            # 而这一路读到的队列同样是空的——平台真正的排队不在这个页面里。
            hint = "（这段排在平台自己的池子里，这个页面看不到它到哪一步）"
        elif "排队" in w:
            hint = "（一直在平台队列里排着：前面还有别人）"
        elif "跑完" in w:
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
