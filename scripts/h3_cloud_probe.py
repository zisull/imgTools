# -*- coding: utf-8 -*-
"""H3 云端工作流只读探测（真开浏览器，但不提交任务、不扣积分）。

要拿到的答案：
  1) 用登录态快照能不能直达工作流页（iframe + ComfyUI 图加载出来）；
  2) 主节点上有哪些控件、可选值逐字是什么（云端提交的值必须和线上 options 一致）；
  3) 上传端点的认证路径（apiURL('upload/image')）与输出节点长什么样（取哪两个字段）。

用法：
  python scripts/h3_cloud_probe.py                 # 探默认工作流
  python scripts/h3_cloud_probe.py --url <工作流页地址>
  python scripts/h3_cloud_probe.py --keep           # 探完不关浏览器，人接着看
不打印任何 cookie 值或 Key，只报名字与数量。
"""
import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))

# 控制台是 GBK：emoji 与生僻字会当场抛 UnicodeEncodeError（shoot.py 踩过同一坑）
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_URL = "https://www.runninghub.cn/workflow/2103759530927673346?source=workspace"


def mask(s):
    """把鉴权参数值打掉再印：Rh-Comfy-Auth=eyJ... → Rh-Comfy-Auth=***"""
    return re.sub(r"(Rh-[A-Za-z_-]+=)[^&\s]+", r"\1***", str(s or ""))

# 在主文档里找 ComfyUI 那个 iframe：先按类名/属性，再退回「唯一那个」
_JS_IFRAME = """
var sels=['iframe.comfyUI-iframe',"iframe[class*='comfy']","iframe[id^='iframe']","iframe"];
for(var i=0;i<sels.length;i++){
  var f=document.querySelector(sels[i]);
  if(f&&(f.id||f.name)) return f.id||f.name;
}
return '';
"""
_JS_STATE = """
var f=document.getElementById(arguments[0]);
if(!f) return JSON.stringify({err:'no_iframe'});
if(!f.contentWindow) return JSON.stringify({err:'no_contentWindow'});
try{
  var w=f.contentWindow;
  var n=(w.app&&w.app.graph&&w.app.graph._nodes)||[];
  var up='';
  try{ up=w.comfyAPI.api.api.apiURL('upload/image'); }catch(e){ up='no_comfyAPI:'+(e&&e.message); }
  return JSON.stringify({nodes:n.length,upload:up,
    titles:n.map(function(x){return (x.type||'')+'#'+x.id;}).slice(0,400)});
}catch(e){ return JSON.stringify({err:'cross_origin:'+(e&&e.message)}); }
"""
# 单个节点：控件名/当前值/可选值 + 属性里的 feihou_h3_* 
_JS_NODE = """
var f=document.getElementById(arguments[0]);
var node=f.contentWindow.app.graph.getNodeById(arguments[1]);
if(!node) return JSON.stringify({err:'node not found'});
var ws=(node.widgets||[]).map(function(w,i){
  return {i:i,name:w.name,type:w.type,value:String(w.value===undefined?'':w.value).slice(0,60),
          opts:(w.options&&w.options.values)?w.options.values.slice(0,12):null};
});
var props={};try{Object.keys(node.properties||{}).forEach(function(k){
  var v=node.properties[k];props[k]=typeof v==='object'?JSON.stringify(v).slice(0,80):String(v).slice(0,80);});}catch(e){}
return JSON.stringify({type:node.title||node.type,widgets:ws,props:props});
"""
# 输出节点：videopreview 里那两个字段（filename / cos_url）就是成片的句柄
_JS_OUT = """
var f=document.getElementById(arguments[0]);
var node=f.contentWindow.app.graph.getNodeById(arguments[1]);
if(!node) return JSON.stringify({err:'node not found'});
var out=[];
(node.widgets||[]).forEach(function(w,i){
  if(w.name==='videopreview'&&w.value&&w.value.params)
    out.push({i:i,filename:w.value.params.filename,cos_url:String(w.value.params.cos_url||'').slice(0,60)});
});
return JSON.stringify({type:node.title||node.type,preview:out});
"""
# 关键一问：这台托管 ComfyUI 的 API 路径能不能纯 HTTP 走（不点 DOM 按钮）
# apiURL 是相对路径，所以必须同时报出 iframe 自己的 origin 和 app.api_base_url，
# 否则会把「站点根 /history 恰好通」误当成「/prompt 也在根上」。
_JS_API = """
var f=document.getElementById(arguments[0]);
var api=f.contentWindow.comfyAPI.api.api, w=f.contentWindow, out={};
var ep=['prompt','history','object_info','upload/image','view','queue','interrupt'];
ep.forEach(function(e){ try{ out[e]=api.apiURL(e); }catch(err){ out[e]='ERR:'+(err&&err.message); } });
out._iframe_src = f.src || f.getAttribute('src') || '';
try{ out._origin = w.location.origin; }catch(e){ out._origin='ERR'; }
try{ out._base = String(w.app && w.app.api_base_url); }catch(e){ out._base='ERR'; }
try{ out._client = String(w.app && w.app.client_id); }catch(e){ out._client='ERR'; }
try{ out._graph = JSON.stringify(w.app.graph.serialize()); }
catch(e){ out._graph='ERR'; }
return JSON.stringify(out);
"""


# 页面内发一次空图 POST：和外头的 requests 对照，差的就是某个请求头/会话值。
# 空 prompt 在 ComfyUI 必定校验失败，进不了队列，不建任务、不扣积分。
_JS_POST = """
var f=document.getElementById(arguments[0]);
var w=f.contentWindow, u=w.comfyAPI.api.api.apiURL('prompt');
return fetch(u,{method:'POST',credentials:'include',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({prompt:{},client_id:'qic-probe'})})
  .then(function(r){return r.text().then(function(t){return r.status+' '+t.slice(0,160);});})
  .catch(function(e){return 'ERR '+(e&&e.message);});
"""


# 提交前最后一问：graphToPrompt() 序列化出的主节点入参长什么样。
# 只序列化、不 POST：不建任务、不扣积分，却能证实「写进控件的值」和「线上真收的值」是同一套。
# 新版 ComfyUI 里 graphToPrompt() 返回的是 Promise：直接 .output 取值会拿到 undefined，
# 看着像「序列化是空的」。这里两种都接下来：异步就 then，同步就当场读（run_js 会等 Promise）。
_JS_GRAPHTO = """
var f=document.getElementById(arguments[0]),nid=String(arguments[1]);
var w=f.contentWindow, node=w.app.graph.getNodeById(nid), o={};
function read(p){
  var out=(p&&p.output)||p||{};
  o.keys=Object.keys(out).slice(0,8);
  var n=out[nid];
  var src=(n&&n.inputs)||{};
  o.found=!!n; o.type=(n||{}).class_type||'';
  o.inputs={};Object.keys(src).forEach(function(k){
    var v=src[k];o.inputs[k]=(typeof v==='string')?v.slice(0,180):v;});
  return o;
}
try{
  var p=(w.app.graphToPrompt&&w.app.graphToPrompt())||(w.graphToPrompt&&w.graphToPrompt());
  o.kind=Object.prototype.toString.call(p);
  if(p&&typeof p.then==='function')return p.then(function(x){
    return JSON.stringify(read(x));});
  return JSON.stringify(read(p));
}catch(e){ o.err=String(e&&e.message||e).slice(0,160); }
o.editor=!!(node&&node.__h3Editor);
try{ o.editorText=String((node.__h3Editor||{}).textContent||'').slice(0,120); }catch(e){}
return JSON.stringify(o);
"""


# 平台到底跑到哪一步了：只看，不写、不提交、不扣积分。
# 三路并取，因为不知道哪一路在这台托管实例上活着：
#   · app.queue —— 页面自己那份内存队列（最准，且完全不联网）
#   · GET /queue、GET /history —— 只读口（实测 GET 通、POST /prompt 被网关挡）
#   · 顶层那颗执行按钮的文案 —— RunningHub 排队/跑着时按钮会变字，最后一道兜底
# 出片等待时界面上只有「已等 N 秒」，就是缺这一路：分不清排队、在跑还是已经失败。
_JS_QUEUE = """
var fid=arguments[0];
var f=document.getElementById(fid);
var w=f&&f.contentWindow, o={};
function btnText(){
  var bs=[].slice.call(document.querySelectorAll('.execute-btn-wrap button'));
  return bs.map(function(b){return (b.textContent||'').trim().slice(0,20);}).join('|')||'none';
}
function snap(q){
  if(!q)return null;
  return {running:(q.queue_running||[]).length,pending:(q.queue_pending||[]).length,
          done:Number(q.completed||0),total:Number(q.total_execution_time||0),
          max:Number(q.max_execution_time||0)};
}
function keysOf(o){try{return o?Object.keys(o).slice(0,24):null;}catch(e){return 'err';}}
o.btn=btnText();
try{o.appq=snap(w&&w.app&&w.app.queue);}catch(e){o.appq='err:'+String(e.message).slice(0,60);}
try{o.wsq=snap(w&&w.comfy&&w.comfy.app&&w.comfy.app.queue);}catch(e){}
/* app.queue 在这份托管前端里是 null（实测）：光读内存队列永远读不到，
   所以要问「app 到底有什么」——队列对象换个挂法就得跟着换，别猜。 */
try{o.app_keys=keysOf(w&&w.app);}catch(e){o.app_keys='err';}
try{o.win_keys=keysOf(w);}catch(e){o.win_keys='err';}
/* 新版前端把队列挪进了 app.queueItems（实测 app 上有这个键、没有 queue）。
   先看清它到底是数组还是对象，别猜——猜错就把「不知道」说成「空了」。 */
try{var v=w&&w.app&&w.app.queueItems;
  o.qi=v==null?null:{type:Object.prototype.toString.call(v),
                     len:(v.length!==undefined?v.length:null),
                     keys:keysOf(v),
                     first:v&&v.length?String(JSON.stringify(v[0])).slice(0,120):''};}
catch(e){o.qi='err:'+String(e.message).slice(0,60);}
if(!w||!w.comfyAPI||!w.comfyAPI.api||!w.comfyAPI.api.api){
  o.err='no_comfy_api';return JSON.stringify(o);}
var A=w.comfyAPI.api.api;
function url(ep){var u=A.apiURL?A.apiURL(ep):'';
  return u&&u.indexOf('http')===0?u:'https://www.runninghub.cn'+(u[0]==='/'?u:'/'+u);}
function cut(t){return String(t||'').slice(0,300);}
function get(ep){return fetch(url(ep),{credentials:'include'})
  .then(function(r){return r.text().then(function(t){return {st:r.status,body:t};});})
  .catch(function(e){return {st:0,body:'ERR '+(e&&e.message)};});}
return Promise.all([get('queue'),get('history')]).then(function(rs){
  o.queue_http=rs[0].st;o.hist_http=rs[1].st;
  o.queue_head=cut(rs[0].body);o.hist_head=cut(rs[1].body);
  try{var q=JSON.parse(rs[0].body);
    o.queue={running:((q&&q.queue_running)||[]).length,
             pending:((q&&q.queue_pending)||[]).length,
             keys:keysOf(q),
             first:(q&&q.queue_running&&q.queue_running[0])?
               String(JSON.stringify(q.queue_running[0])).slice(0,120):''};}
  catch(e){o.queue='parse:'+cut(rs[0].body);}
  try{var h=JSON.parse(rs[1].body),ids=Object.keys(h||{});
    o.hist={n:ids.length,last:''};
    if(ids.length){var one=h[ids[ids.length-1]]||{};
      var s=one.status||{};
      o.hist.last={id:String(ids[ids.length-1]).slice(0,12),
                   status:s.status_str||'',completed:s.completed,
                   ok:!(s.status_str==='error'),
                   msg:cut(JSON.stringify(s.messages||s.detail||''),0)};}
    }catch(e){o.hist='parse:'+cut(rs[1].body);}
  o.btn_after=btnText();
  return JSON.stringify(o);});
"""


def js(host, script, *args):
    return host.tab().run_js(script, *args)


# 本地工作流文件这条路能不能走，全看托管前端有没有「把一份 JSON 灌进图里」的口。
# 只读：改的是内存里那张图，不保存、不提交、不扣积分。
_JS_DUMP = """
var f=document.getElementById(arguments[0]);
if(!f||!f.contentWindow||!f.contentWindow.app)return JSON.stringify({err:'no_app'});
var a=f.contentWindow.app, ways=['graph.serialize','app.serialize'], g=null, why=[];
try{g=a.graph&&a.graph.serialize&&a.graph.serialize();}catch(e){why.push('graph:'+(e&&e.message));}
if(!g||!g.nodes){try{g=a.serialize&&a.serialize();}catch(e){why.push('app:'+(e&&e.message));}}
if(!g||!g.nodes)return JSON.stringify({err:'no_serialize',why:why.join(' | ')});
return JSON.stringify(g);
"""
_JS_LOAD = """
var fid=arguments[0],txt=arguments[1];
var f=document.getElementById(fid);
if(!f||!f.contentWindow)return JSON.stringify({err:'no_frame'});
var a=f.contentWindow.app;
if(!a)return JSON.stringify({err:'no_app'});
var g;try{g=JSON.parse(txt);}catch(e){return JSON.stringify({err:'bad_json:'+(e&&e.message)});}
var has={};['loadGraphData','loadApiJson','loadBaggage','clearGraph','graph'].forEach(
  function(k){has[k]=typeof a[k];});
try{a.loadGraphData(g,true,false,'probe.json');}
catch(e){return JSON.stringify({err:'load:'+(e&&e.message),has:has});}
var n=(a.graph&&a.graph._nodes)||[];
function id(t){for(var i=0;i<n.length;i++)if(n[i].type===t)return n[i].id;return 0;}
return JSON.stringify({has:has,nodes:n.length,main:id('FeiHouEasyH3RH'),
  out:id('VHS_VideoCombine'),types:n.map(function(x){return x.type;}).slice(0,40)});
"""


# 线上那颗主节点改一个控件：combo 走 setOption（它会触发节点自己的重算回调），
# 只改内存里的图，不点保存、不提交——工作流原样留在平台上。
# 顺手把「控件现在的值」和「序列化里的值」一起回：两个不一致就是序列化被缓存了，
# 光看序列化会误判成「改了没生效」。
_JS_SETW = """
var f=document.getElementById(arguments[0]),nid=String(arguments[1]);
var want=arguments[2],val=arguments[3];
var w=f.contentWindow,g=w.app.graph,node=g.getNodeById(nid);
var hit=null;(node.widgets||[]).forEach(function(x){if(x.name===want)hit=x;});
if(!hit)return JSON.stringify({err:'no_widget'});
if(hit.options&&hit.options.values&&hit.options.values.indexOf(val)<0)
  return JSON.stringify({err:'not_in_options',opts:(hit.options.values||[]).slice(0,6)});
try{ if(hit.setOption)hit.setOption(val);else hit.value=val; }
catch(e){ return JSON.stringify({err:'set_threw:'+String(e&&e.message||e).slice(0,80)}); }
g.setNodeDirty&&g.setNodeDirty(node);
g.setDirtyCanvas&&g.setDirtyCanvas(true,true);
return JSON.stringify({ok:1,now:String(hit.value)});
"""


def sweep_sizes(host, fid, node):
    """档位 × 画幅 → 序列化出来的宽高：把「云端那个节点自己怎么算尺寸」问成一张表。

    界面这边 P=短边（768P 竖版＝768×1344），线上却是按另一套公式回的数；
    不实测就拿公式猜，出片尺寸会比界面上写的少一大圈，还不报错。
    只读：改的是内存里的图，序列化不落库、不建任务、不扣积分。
    """
    def inputs():
        raw = js(host, _JS_GRAPHTO, fid, node)
        try:
            d = json.loads(raw or "{}")
        except ValueError:
            return {}
        return d.get("inputs") or {}

    def setv(name, val):
        raw = js(host, _JS_SETW, fid, node, name, val)
        try:
            d = json.loads(raw or "{}")
        except ValueError:
            return {"err": str(raw)[:80]}
        return d

    print("· mode 控件文案 → 序列化值：")
    for m in ("I2V or First/Last Frame", "Reference-to-video"):
        s = setv("mode", m)
        i = inputs()
        print("    %-26s 控件=%s 序列化=%s%s"
              % (m, s.get("now", ""), i.get("mode"),
                 "  设不进去：" + str(s.get("err")) if s.get("err") else ""))
    print("· resolution × aspect_ratio → 序列化宽高（界面按短边=P，线上按它自己的公式）：")
    RES = ("480P", "768P", "1024P", "1080P")
    ASP = ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "2:3", "3:2")
    for res in RES:
        for asp in ASP:
            a = setv("resolution", res)
            b = setv("aspect_ratio", asp)
            i = inputs()
            print("    %-6s %-5s → %s×%s（短边 %s）%s"
                  % (res, asp, i.get("width"), i.get("height"),
                     min(int(i.get("width") or 0), int(i.get("height") or 0)),
                     "  设不进去：%s/%s" % (a.get("err"), b.get("err"))
                     if a.get("err") or b.get("err") else ""))
    # 1080P 以上有没有档：先把档位设到它自己的最高，再直接写宽高看它认不认
    print("· 越过档位表直接写宽高（Custom 那条路，界面能给的就这么大）：")
    setv("resolution", "1080P")
    for wh in ((1920, 1080), (2560, 1440), (3072, 1728), (3840, 2160)):
        x = setv("width", wh[0])
        y = setv("height", wh[1])
        i = inputs()
        print("    写 %sx%s → 序列化 %sx%s（档位回读 %s）%s"
              % (wh[0], wh[1], i.get("width"), i.get("height"), i.get("resolution"),
                 "  设不进去：%s/%s" % (x.get("err"), y.get("err"))
                 if x.get("err") or y.get("err") else ""))
    # 顺序要紧：写完宽高再去动画幅，看它会不会把我们的数按档位重算掉
    print("· 写完宽高再改画幅（看谁说了算）：")
    setv("resolution", "768P")
    setv("width", 2560)
    setv("height", 1440)
    before = inputs()
    setv("aspect_ratio", "16:9")
    after = inputs()
    print("    改画幅前 %s×%s → 改后 %s×%s（档位 %s/%s）"
          % (before.get("width"), before.get("height"),
             after.get("width"), after.get("height"),
             after.get("resolution"), after.get("aspect_ratio")))


# 「YZ金鱼」那种图用的是另一套形状：主节点的提示词/尺寸/时长都不是裸控件，
# 而是从 Text / PrimitiveFloat / ResolutionSelector 经 SetNode→GetNode 虚拟节点接进来的。
# 软件要写它，先得按名字把这些源节点找回来——所以这一步只读着把「谁喂给谁」摊开看。
_JS_KJ_MAP = """
var f=document.getElementById(arguments[0]);
var w=f.contentWindow,g=w.app.graph;
var mtype=arguments[1]||'MiniMaxH3ReferenceToVideo';
var nodes=g._nodes||[];
function wv(n,i){var x=(n.widgets||[])[i];return x?String(x.value).slice(0,120):null;}
function nameOf(n){var x=(n.widgets||[])[0];return x?String(x.value):'';}
var sets={},gets={};
nodes.forEach(function(n){
  if(n.type==='SetNode')sets[nameOf(n)]=n;
  else if(n.type==='GetNode')(gets[nameOf(n)]=gets[nameOf(n)]||[]).push(n);
});
// 顺着一条入参往回走：GetNode→同名 SetNode→它的来源；Reroute/分组开关只看那一条链接
function back(node,depth){
  for(var k=0;node&&k<(depth||6);k++){
    if(node.type==='GetNode'){node=sets[nameOf(node)]||null;continue;}
    if(node.type==='SetNode'||/Reroute|Primitive/i.test(node.type)){
      var li=(node.inputs||[]).filter(function(i){return i.link;})[0];
      if(!li)return node;
      var L=g.links?g.links[li.link]:null;
      node=L?g.getNodeById(L.origin_id):null;
      var sl=(L||{}).origin_slot;
      if(node&&node.outputs&&node.outputs[sl])node=node;
      continue;
    }
    return node;
  }
  return node;
}
var main=null;
nodes.forEach(function(n){if(n.type===mtype&&!main)main=n;});
if(!main)return JSON.stringify({err:'图上没有 '+mtype});
var out={main:main.id,type:main.type,slots:{},images:[],videos:[],audits:[],loaders:[]};
(main.inputs||[]).forEach(function(i){
  if(!i.widget)return;
  var L=g.links?g.links[i.link]:null;
  var src=L?g.getNodeById(L.origin_id):null;
  out.slots[i.name]={link:!!L,from:src?src.type:'',via:src?src.id:0,
                     root:(function(){var r=back(src);return r?{id:r.id,type:r.type,
                       widgets:(r.widgets||[]).map(function(x){return x.name;})}:null;})()};
});
// 参考图：LoadImage 喂给哪个 SetNode，SetNode 名字里的数字就是 <Picture N> 的 N
nodes.forEach(function(n){
  if(n.type!=='LoadImage')return;
  var o=(n.outputs||[]).filter(function(x){return x.name==='IMAGE';})[0]||{};
  var to=[];
  (o.links||[]).forEach(function(t){var L=g.links[t];
    if(!L)return;var r=g.getNodeById(L.target_id);
    to.push(r?r.type+':'+nameOf(r):'');});
  out.images.push({id:n.id,mode:n.mode,file:wv(n,0),to:to.join(',')});
});
nodes.forEach(function(n){
  if(n.type==='VHS_LoadVideo')out.videos.push({id:n.id,mode:n.mode});
  else if(n.type==='LoadAudio')out.audits.push({id:n.id,mode:n.mode});
  else if(/LoraLoader|UNETLoader|CLIPLoader|VAELoader|CheckpointLoader/.test(n.type))
    out.loaders.push({id:n.id,type:n.type,mode:n.mode,file:wv(n,0)});
});
// 尺寸那顆 combo 的实时可选值：写进去的画幅必须在这一串里
var sel=null;
nodes.forEach(function(n){if(n.type==='ResolutionSelector')sel=n;});
if(sel)out.size={id:sel.id,widgets:(sel.widgets||[]).map(function(x){
  return {name:x.name,value:String(x.value).slice(0,40),
          opts:(x.options&&x.options.values||[]).slice(0,30)};})};
var out2=null;
nodes.forEach(function(n){if(n.type==='VHS_VideoCombine'&&!out2)out2=n;});
out.vhs=out2?out2.id:0;
return JSON.stringify(out);
"""
# 实例上到底有没有这些模型文件：只 GET /object_info/<节点类型>，不看队列、不提交
_JS_OBJINFO = """
var f=document.getElementById(arguments[0]);
var w=f.contentWindow,A=w.comfyAPI&&w.comfyAPI.api&&w.comfyAPI.api.api;
if(!A)return JSON.stringify({err:'no_api'});
function url(ep){var u=A.apiURL?A.apiURL(ep):'';
  return u&&u.indexOf('http')===0?u:w.location.origin+(u[0]==='/'?u:'/'+u);}
var ts=[].slice.call(arguments,1);
return Promise.all(ts.map(function(t){
  return fetch(url('object_info/'+t),{credentials:'include'})
    .then(function(r){return r.status===200?r.text():('http'+r.status);})
    .catch(function(e){return 'err'+String(e).slice(0,30);});})).then(function(rs){
  var o={};
  rs.forEach(function(s,i){var t=ts[i];try{
    var j=JSON.parse(s),k=Object.keys(j)[0];
    var inps=(j[k]||{}).input||{},need=inps.required||{},opt=inps.optional||{},list={};
    Object.keys(need).concat(Object.keys(opt)).forEach(function(nm){
      var v=need[nm]||opt[nm];
      if(Array.isArray(v[0]))list[nm]=v[0];
      else list[nm]=[String(v[0]||'').slice(0,24)];});
    o[t]=list;
  }catch(e){o[t]={_bad:String(s).slice(0,80)};}});
  return JSON.stringify(o);});
"""


def kj_map(host, fid, maintype):
    """把「能写的节点」摊开：每个控件槽位背后真正的源节点是谁。"""
    raw = str(js(host, _JS_KJ_MAP, fid, maintype) or "")
    try:
        d = json.loads(raw)
    except ValueError:
        print("✗ 映射回包不是 JSON：%s" % raw[:200])
        return None
    if d.get("err"):
        print("✗ %s" % d["err"])
        return d
    print("· 主节点 %s（%s）· 输出节点 %s" % (d.get("main"), d.get("type"), d.get("vhs")))
    for k, v in sorted((d.get("slots") or {}).items()):
        r = v.get("root") or {}
        print("    %-10s 连着=%s ← %s(%s) ← 根 %s(%s) 控件=%s"
              % (k, v.get("link"), v.get("from"), v.get("via"),
                 r.get("type"), r.get("id"), ",".join(r.get("widgets") or [])))
    print("· 参考图 LoadImage（mode 0=正常 4=旁路）：")
    for x in d.get("images") or []:
        print("    id %-4s mode %s → %-8s %s" % (x["id"], x["mode"], x["to"],
                                                 str(x["file"])[:36]))
    print("· 参考视频 %s 个 · 参考音频 %s 个"
          % (len(d.get("videos") or []), len(d.get("audits") or [])))
    for x in d.get("loaders") or []:
        print("    模型 %-20s id %-4s mode %s %s"
              % (x["type"], x["id"], x["mode"], x["file"]))
    sz = d.get("size")
    if sz:
        print("· 尺寸选择器 %s：" % sz.get("id"))
        for x in sz.get("widgets") or []:
            print("    %-14s = %s · 可选 %s"
                  % (x["name"], x["value"], json.dumps(x["opts"], ensure_ascii=False)[:400]))
    return d


def models_check(host, fid, need):
    """这台实例上到底有哪些模型文件，和那张图点名的对一对。
    只 GET /object_info/<类型>，不进队列、不提交、不扣积分。"""
    raw = str(js(host, _JS_OBJINFO, fid, "LoraLoaderModelOnly",
                 "UNETLoader", "CLIPLoader", "VAELoader") or "")
    try:
        d = json.loads(raw)
    except ValueError:
        print("✗ object_info 回包读不懂：%s" % raw[:200])
        return
    pools = {}
    for t, w in (d or {}).items():
        if not isinstance(w, dict):
            continue
        if "_bad" in w:
            print("· %s 的 object_info 读不懂：%s" % (t, w["_bad"]))
        for nm, vals in w.items():
            if isinstance(vals, list) and vals and isinstance(vals[0], str):
                pools.setdefault(nm.lower(), set()).update(vals)
    allnames = set().union(*list(pools.values())) if pools else set()
    print("· 实例上的模型清单：%s" % ", ".join("%s(%d)" % (k, len(v))
                                              for k, v in sorted(pools.items())))
    miss = []
    for f in need or []:
        hit = f in allnames
        print("    %-62s %s" % (f[:62], "在" if hit else "✗ 这台实例上没有"))
        if not hit:
            miss.append(f)
            stem = f.split(".")[0][:14]
            near = [x for x in allnames if stem.lower() in x.lower()][:4]
            if near:
                print("        相近的：%s" % ", ".join(near))
    if miss:
        print("· 缺 %d 个：跑这张图前要么平台上加模型，要么把这些节点旁路掉" % len(miss))
    return miss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("QIC_CLOUD_URL") or DEFAULT_URL)
    ap.add_argument("--acct", default="", help="账号 id，默认用档案里第一个")
    ap.add_argument("--node", type=int, default=389, help="主节点 id")
    ap.add_argument("--out", type=int, default=325, help="输出节点 id")
    ap.add_argument("--wait", type=int, default=120, help="等图加载的秒数")
    ap.add_argument("--post", action="store_true",
                    help="页面内补一次空图 POST，和外头 requests 对照")
    ap.add_argument("--graph", action="store_true",
                    help="打印 graphToPrompt() 序列化出的主节点入参（只序列化，不提交）")
    ap.add_argument("--size", action="store_true",
                    help="扫一遍档位×画幅，问出云端自己算的宽高，以及 mode 序列化成的值")
    ap.add_argument("--queue", action="store_true",
                    help="只看平台跑到哪一步（内存队列 + GET /queue + /history + 按钮文案），不提交不扣分")
    ap.add_argument("--state", action="store_true",
                    help="用 cloudkit 那份真代码读一次状态句（不提交不扣分）：验的就是 Promise 回不回得来")
    ap.add_argument("--dump", default="", metavar="FILE",
                    help="把页面里这张图导成本地工作流文件（app.serialize()，只读）")
    ap.add_argument("--load", default="", metavar="FILE",
                    help="把本地工作流文件灌回页面（app.loadGraphData），验本地文件这条路通不通；不保存不提交")
    ap.add_argument("--keep", action="store_true", help="探完不关浏览器")
    ap.add_argument("--kj", action="store_true",
                    help="按「虚拟节点那张图」的形状反查能写的节点（Text/PrimitiveFloat/"
                         "ResolutionSelector/LoadImage），并把主节点与输出节点指过去")
    ap.add_argument("--maintype", default="MiniMaxH3ReferenceToVideo",
                    help="--kj 找的主节点类型")
    ap.add_argument("--models", action="store_true",
                    help="配 --kj：把图上没旁路的模型文件和实例上的清单对一遍（只 GET）")
    ap.add_argument("--port", type=int, default=9335,
                    help="另起一只浏览器的调试端口：软件保活正占着 9333/9334，"
                         "顶上去等于把用户正在用的窗口开走")
    ap.add_argument("--profile", default="",
                    help="配套的 user-data-dir；留空＝TEMP 下临时一份。"
                         "别用软件那份：同目录会被已经开着的 Chrome 锁住")
    a = ap.parse_args()

    import socket
    with socket.socket() as s:
        s.settimeout(0.6)
        if s.connect_ex(("127.0.0.1", a.port)) == 0:
            print("✗ 端口 %d 上已经有一只浏览器：换一个 --port，"
                  "别接管软件那两只（9333/9334）" % a.port)
            return 1
    if not a.profile:
        a.profile = os.path.join(os.environ.get("TEMP", "/tmp"),
                                 "qic_probe_profile_%d" % a.port)

    # 账号库读的是用户那一份（只取快照，不改它）：所以这里不再设 QIC_CONFIG 把
    # 数据根整体挪走——挪走以后 AccountStore 里一个号都没有，探测就无从谈起。
    from cloudkit import store as cs
    from cloudkit.browser import BrowserHost, login_state

    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8")) \
        if os.path.isfile(os.path.join(ROOT, "config.json")) else {}
    cloud = dict(cfg.get("cloud") or {})
    cloud["login_url"] = a.url
    cloud["port"] = a.port         # 另起一只，不顶软件保活那两只
    store = cs.AccountStore(ROOT)
    accts = store.list()
    if not accts:
        print("账号库里没有一个号：先到软件「环境管理 → 云端账号」新建登录并保存")
        return 1
    aid = a.acct or accts[0]["id"]
    row = [x for x in accts if x["id"] == aid][0]
    state = store.load(aid) or {}
    print("· 用账号「%s」的登录态 · cookie %d 条 · 鉴权头 %d 个（值不打印）"
          % (row["name"], len(state.get("cookies") or []),
             len(cs.auth_headers(state.get("cookies"), state.get("storage")))))

    host = BrowserHost(ROOT, cloud, port=a.port, profile=a.profile)
    print("· 另起一只浏览器：端口 %d · profile %s" % (a.port, a.profile))
    code = 1
    try:
        host.apply(state, aid=aid)              # 灌快照：共用浏览器先清残留
        st, detail = login_state(host.tab())
        print("· 首页登录判定：%s · %s" % (st, detail))
        host.open_login(state, aid=aid)         # 直接开工作流页（purpose=login 让保活让路）
        fid, nodes = "", None
        t0 = time.time()
        while time.time() - t0 < a.wait:
            fid = fid or str(js(host, _JS_IFRAME) or "")
            if fid:
                raw = js(host, _JS_STATE, fid)
                try:
                    nodes = json.loads(raw or "{}")
                except ValueError:
                    nodes = None
                if nodes and nodes.get("nodes"):
                    break
            time.sleep(3)
        if not fid:
            print("✗ 页面上找不到 ComfyUI iframe：这个账号可能打不开该工作流（不是自己的/已删）")
            return 1
        print("· iframe id = %s · 节点数 = %s" % (fid, (nodes or {}).get("nodes")))
        # 这条带鉴权值：apiURL('upload/image') 把 Rh-Comfy-Auth / Rh-Identify 直接拼在
        # query 上，原样打印等于把登录态抄进日志文件（logs/ 在仓库里）
        print("· 上传端点认证路径 = %s" % mask((nodes or {}).get("upload")))
        titles = (nodes or {}).get("titles") or []
        print("· 节点清单（前 400）= %s" % ", ".join(titles[:60]))
        raw = js(host, _JS_API, fid)
        try:
            api = json.loads(raw or "{}")
        except ValueError:
            api = {}
        graph = api.pop("_graph", "") or ""
        for ep in sorted(api):
            print("· apiURL(%s) = %s" % (ep, mask(api[ep])))
        print("· 图序列化：%d 字节 · 节点 %d 个"
              % (len(graph), graph.count('"id":')))
        if graph.startswith("{"):
            g = json.loads(graph)
            n389 = g.get(str(a.node)) or {}
            print("· 节点 %s 的 widgets_values 前 6 项 = %s"
                  % (a.node, mask(json.dumps((n389.get("widgets_values") or [])[:6],
                                             ensure_ascii=False)[:300])))
        # 纯 HTTP 能不能问出东西：只 GET，不 POST，不动队列、不扣积分
        cookie = "; ".join("%s=%s" % (c.get("name"), c.get("value"))
                           for c in (state.get("cookies") or []) if c.get("name"))
        try:
            import requests
            for ep in ("history", "prompt"):
                url = api.get(ep) or ""
                if not url:
                    continue
                # apiURL 已经把鉴权参数拼在 path 上了，这里只补 origin
                full = url if url.startswith("http") else "https://www.runninghub.cn" + (
                    url if url.startswith("/") else "/" + url)
                try:
                    r = requests.get(full, headers={"Cookie": cookie}, timeout=25)
                    print("· GET %s → HTTP %s · %s" % (ep, r.status_code,
                          mask(r.text[:120]).replace("\n", " ")))
                except Exception as e:
                    print("· GET %s 出错：%s" % (ep, str(e)[:120]))
        except ImportError:
            print("· 没装 requests，跳过纯 HTTP 试探")
        kj = None
        if a.kj:
            kj = kj_map(host, fid, a.maintype)
            if kj and (kj.get("main") or 0):
                a.node = kj["main"]
            if kj and (kj.get("vhs") or 0):
                a.out = kj["vhs"]
            if a.models and kj:
                models_check(host, fid, [x.get("file") for x in (kj.get("loaders") or [])
                                         if x.get("mode") == 0 and x.get("file")
                                         and x["file"] != "None"])
        for label, nid in (("主节点", a.node), ("输出节点", a.out)):
            raw = js(host, _JS_NODE, fid, nid)
            try:
                d = json.loads(raw or "{}")
            except ValueError:
                d = {"err": "非 JSON：" + str(raw)[:120]}
            if d.get("err"):
                print("✗ %s %s：%s" % (label, nid, d["err"]))
                continue
            print("· %s %s = %s" % (label, nid, d.get("type")))
            for w in d.get("widgets") or []:
                print("    [%s] %s(%s) = %s%s" % (w["i"], w["name"], w["type"], w["value"],
                                                  "  可选：%s" % w["opts"] if w["opts"] else ""))
            if d.get("props"):
                print("    属性：%s" % json.dumps(d["props"], ensure_ascii=False)[:400])
        raw = js(host, _JS_OUT, fid, a.out)
        print("· 输出节点预览 = %s" % str(raw)[:300])
        if a.graph:
            print("· 将要提交的序列化 = %s" % mask(str(js(host, _JS_GRAPHTO, fid, a.node))[:2000]))
        if a.size:
            sweep_sizes(host, fid, a.node)
        if a.post:
            print("· 页面内 POST prompt(空) = %s" % mask(str(js(host, _JS_POST, fid))[:220]))
        if a.queue:
            raw = str(js(host, _JS_QUEUE, fid) or "")
            try:
                q = json.loads(raw)
            except ValueError:
                q = {"err": raw[:200]}
            print("· 执行按钮 = %s%s" % (q.get("btn"),
                  ("  → " + str(q.get("btn_after"))) if q.get("btn_after") else ""))
            print("· 页面内存队列 = %s" % json.dumps(q.get("appq"), ensure_ascii=False))
            if q.get("app_keys"):
                print("· app 上挂的键 = %s" % json.dumps(q["app_keys"], ensure_ascii=False)[:300])
            if q.get("win_keys"):
                print("· 窗口上的键 = %s" % json.dumps(q["win_keys"], ensure_ascii=False)[:300])
            if q.get("qi") is not None:
                print("· app.queueItems = %s" % json.dumps(q["qi"], ensure_ascii=False)[:400])
            if q.get("wsq"):
                print("· 另一路 app.queue = %s" % json.dumps(q["wsq"], ensure_ascii=False))
            print("· GET /queue → HTTP %s · %s" % (q.get("queue_http"),
                  json.dumps(q.get("queue"), ensure_ascii=False)[:300]))
            print("· /queue 原文 = %s" % str(q.get("queue_head"))[:300])
            print("· GET /history → HTTP %s · %s" % (q.get("hist_http"),
                  json.dumps(q.get("hist"), ensure_ascii=False)[:400]))
            if q.get("err"):
                print("· 拿不到：%s" % q["err"])
            if q.get("queue") == 0 and q.get("hist") == 0:
                print("· 两处都是空的：要么这份托管实例看不到别人提交的任务，要么被网关挡了")
        if a.dump:
            raw = str(js(host, _JS_DUMP, fid) or "")
            try:
                g = json.loads(raw)
            except ValueError:
                g = None
                print("✗ 导回来的不是 JSON：%s" % raw[:200])
            if g is not None and (g.get("nodes") or []):
                with open(a.dump, "w", encoding="utf-8") as f:
                    f.write(raw)
                print("· 导出 %s · %d 字节 · 顶层键 %s · 节点 %d 个 · 连线 %d 条"
                      % (os.path.basename(a.dump), len(raw),
                         ",".join(sorted(g)[:9]),
                         len(g.get("nodes") or []), len(g.get("links") or [])))
            elif g is not None:
                print("✗ 没导出成：%s · %s" % (g.get("err"), g.get("why")))
        if a.load:
            txt = open(a.load, encoding="utf-8").read()
            raw = str(js(host, _JS_LOAD, fid, txt) or "")
            try:
                d = json.loads(raw)
            except ValueError:
                d = {"err": "非 JSON：" + raw[:200]}
            if d.get("err"):
                print("✗ 灌图失败：%s · 前端方法 %s" % (d["err"], d.get("has")))
            else:
                print("· 前端方法 = %s" % json.dumps(d.get("has"), ensure_ascii=False))
                print("· 灌进去之后：节点 %s 个 · 主节点 id=%s · 输出节点 id=%s"
                      % (d.get("nodes"), d.get("main"), d.get("out")))
                print("· 节点类型（前 40）= %s" % ", ".join(d.get("types") or []))
                if d.get("main"):
                    gt = str(js(host, _JS_GRAPHTO, fid, d["main"]) or "")
                    try:
                        s = json.loads(gt)
                    except ValueError:
                        s = {"err": gt[:160]}
                    inp = s.get("inputs") or {}
                    print("· 序列化里这个节点 = %s · 有 editor=%s · 控件数=%s"
                          % (s.get("type"), s.get("editor"), len(inp)))
                    print("· 序列化入参 = %s" % json.dumps(
                        {k: inp[k] for k in list(inp)[:14]}, ensure_ascii=False)[:600])
        if a.state:
            # 走 cloudkit/gen.py 那两份真代码，不在这儿抄一份：
            # 进度脚本现在返回 Promise，只有真页面上跑一次才知道 run_js 等不等它——
            # 等不到就是状态句永远是空的，界面上看不出差别，只有真机撞得出来。
            from cloudkit.gen import CloudH3, _JS_PROGRESS
            g = CloudH3(ROOT, cloud, store, host)
            tab = host.tab()
            r = g.js(tab, _JS_PROGRESS, fid)
            raw = r if isinstance(r, str) else str(r or "")
            print("· 进度脚本回包类型 = %s" % ("str" if isinstance(r, str) and r
                                              else type(r).__name__))
            try:
                d = json.loads(raw or "{}")
            except ValueError:
                d = {"err": "非 JSON：" + raw[:200]}
            print("· 回包 = %s" % json.dumps(d, ensure_ascii=False)[:600])
            n0 = g.history_count(tab, fid)
            print("· 历史条数 = %s" % n0)
            for w in (10, 300):
                print("· 状态句（已等 %d 秒）= 「%s」"
                      % (w, g.platform_state(tab, fid, w, n0)))
        code = 0 if (nodes or {}).get("nodes") else 1
    finally:
        if a.keep:
            print("· 浏览器留着了（--keep）：软件里的保活会让路，看完点「关闭浏览器」")
        else:
            host.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
