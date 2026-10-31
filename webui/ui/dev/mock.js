/* dev/mock.js —— 浏览器预览用的假后端（正常启动不内联，仅截图/看界面用）
   提供 window.MIC_MOCK.*，接口签名与 webui/app.py 的 js_api 一一对应。 */
(function(){
const cfg={
  app_title:'Qwen 生图控制台',theme:'tide',mode:'dark',layout:'tree',sidebar_min:false,
  notify:true,last_tab:'t_gen',nav_ver:6,open:{},console_mode:'both',welcomed:true,
  console:{model_dir:'D:/AI/Qwen-Image-2.1/models/Qwen-Image-2.1-Turbo',
           output_dir:'D:/AI/Qwen-Image-2.1/outputs',quant:'fp8',offload:true},
  gen:{mode:'gen',prompt:'雨夜的霓虹小巷，湿路面拖出长反光，电影感光线',
      negative:'低画质，模糊，噪点，压缩失真，水印，签名，文字，多余手指，肢体畸形，面部扭曲，比例失衡，过曝，死黑，裁切',size:'1024x1024',cw:1024,ch:1024,steps:'8',seed:-1,count:1,kv_cache:true},
  edit:{prompt:'把这张铅笔素描变成白底上的同款实物照片。',
        negative:'低画质，模糊，噪点，压缩失真，水印，签名，文字，多余手指，肢体畸形，面部扭曲，比例失衡，过曝，死黑，裁切',res:'512',steps:'8',seed:-1,count:1,kv_cache:true},
  inpaint:{prompt:'在仪表台上放一副墨镜。',
        negative:'低画质，模糊，噪点，压缩失真，水印，签名，文字，多余手指，肢体畸形，面部扭曲，比例失衡，过曝，死黑，裁切',res:'512',steps:'8',seed:-1,count:1,kv_cache:true,brush:48},
  lib:{cat:'person'},
  engine:'qwen',
  moss:{comfyui_dir:'comfyui',port:8876,tier:'daily',extra_args:[],
        output_dir:'D:/AI/Qwen-Image-2.1/outputs',
        prompt:'银发少女，柔和棚拍光，眼睛细节清晰',
        negative:'低画质，模糊，噪点，压缩失真，水印，签名，文字，多余手指，肢体畸形，面部扭曲，比例失衡，过曝，死黑，裁切',size:'1024x1024',cw:1024,ch:1024,
        seed:-1,count:1,quality:'fast'},
  api:{enabled:false,lan:false,host:'127.0.0.1',port:8765,token:'',no_token:false,
       def_engine:'follow',def_size:'1024x1024'},
  nav:[
    {id:'g_out',type:'group',name:'出图',icon:'flower',children:[
      {id:'t_gen',type:'tab',name:'生图',icon:'flower',page:'t2i'},
      {id:'t_edit',type:'tab',name:'编辑',icon:'wand',page:'edit'},
      {id:'t_inp',type:'tab',name:'重绘',icon:'brush',page:'inpaint'}]},
    {id:'g_sys',type:'group',name:'系统',icon:'cog',children:[
      {id:'t_gal',type:'tab',name:'画廊',icon:'image',page:'gallery'},
      {id:'t_mod',type:'tab',name:'环境',icon:'db',page:'models'},
      {id:'t_log',type:'tab',name:'日志',icon:'hist',page:'logs'},
      {id:'t_set',type:'tab',name:'设置',icon:'cog',page:'settings'}]},
  ],
};
cfg.default_nav=JSON.parse(JSON.stringify(cfg.nav));

const st={running:null,status:'就绪',done:0,total:0,
  model_loaded:false,model_name:'Qwen-Image-2.1-Turbo',quant:'fp8',
  vram_used:0.6,vram_total:12,img_count:6,last_sec:28.4,
  last_image:'D:/AI/Qwen-Image-2.1/outputs/gen_20261013_094107.png',
  api_on:false,api_url:'',load_pct:0,load_stage:'',env_busy:false,env_todo:null,
  env_todo_qwen:null,env_todo_moss:null,
  engine:'qwen',moss_tier:'daily',moss_installed:false,comfyui_on:false,comfyui_loaded:false,comfyui_url:''};

let seq=0;
const logs=[];
const now=()=>new Date().toTimeString().slice(0,8);
function L(t){logs.push([++seq,now(),t]);}
function stamp(){const d=new Date(),p=n=>String(n).padStart(2,'0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;}

/* 缩略图：按路径哈希出一个稳定渐变 SVG（data: 内联，浏览器里直接能显示） */
function hueOf(s){let h=0;for(let i=0;i<String(s).length;i++)h=(h*31+String(s).charCodeAt(i))%360;return h;}
function thumbFor(p){
  const h=hueOf(p),h2=(h+48)%360;
  return 'data:image/svg+xml;utf8,'+encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512">`+
    `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">`+
    `<stop offset="0" stop-color="hsl(${h},70%,55%)"/><stop offset="1" stop-color="hsl(${h2},75%,35%)"/>`+
    `</linearGradient></defs><rect width="512" height="512" fill="url(#g)"/>`+
    `<circle cx="140" cy="140" r="60" fill="hsla(${h2},80%,80%,.5)"/>`+
    `<path d="M40 420 L200 260 L300 360 L380 280 L480 400 Z" fill="hsla(${h},60%,20%,.6)"/></svg>`);
}

/* 画廊种子：形状与 App.gallery_list 一致（file/name/t/size/seed/prompt/url + 历史库字段） */
const GAL=[
  {file:'D:/AI/Qwen-Image-2.1/outputs/gen_20261013_094107.png',name:'gen_20261013_094107.png',
   t:'2026-10-13 09:41',size:'1024×1024',seed:42,prompt:'A neon-lit alley in the rain…',
   mode:'gen',negative:'',steps:8,sec:28.4,fav:1},
  {file:'D:/AI/Qwen-Image-2.1/outputs/gen_20261013_091852.png',name:'gen_20261013_091852.png',
   t:'2026-10-13 09:18',size:'1536×1024',seed:7,prompt:'Chinese ink painting of misty mountains',
   mode:'gen',negative:'blurry',steps:8,sec:77.2,fav:0},
  {file:'D:/AI/Qwen-Image-2.1/outputs/gen_20261012_223341.png',name:'gen_20261012_223341.png',
   t:'2026-10-12 22:33',size:'跟随输入图 · 512²',seed:-1,prompt:'Portrait of an elderly lighthouse keeper',
   mode:'edit',negative:'',steps:8,sec:19.5,fav:0},
  {file:'D:/AI/Qwen-Image-2.1/outputs/gen_20261012_215503.png',name:'gen_20261012_215503.png',
   t:'2026-10-12 21:55',size:'1024×1024',seed:2026,prompt:'Isometric smart warehouse, cutaway view',
   mode:'rgba',negative:'',steps:8,sec:26.1,fav:1},
  {file:'D:/AI/Qwen-Image-2.1/outputs/gen_20261012_201144.png',name:'gen_20261012_201144.png',
   t:'2026-10-12 20:11',size:'512x512',seed:100,prompt:'产品白底图：磨砂黑保温杯，柔光',
   mode:'gen',negative:'',steps:40,sec:96.3,fav:0},
  {file:'D:/AI/Qwen-Image-2.1/outputs/gen_20261011_180209.png',name:'gen_20261011_180209.png',
   t:'2026-10-11 18:02',size:'1024×1024',seed:9,prompt:'Steampunk owl clockwork, macro detail'},
];
GAL.forEach(g=>g.url=thumbFor(g.file));

/* 模型清单种子：形状与 App.models_list 一致 */
const MDL=[
  {name:'Qwen-Image-2.1-Turbo',gb:31.2,shards:32,index:true,active:true},
  {name:'Qwen-Image-2.1',gb:0,shards:0,index:false,active:false},
];

/* 体检种子：形状与 webui/env_check.check() 一致。
   故意留三项「没装/待补」，方便在浏览器里核对补全那条 UI 路径长什么样。 */
const ENV=[
  {key:'python',group:'运行环境',label:'Python 解释器',state:'ok',detail:'当前 3.12.10（要求 3.11~3.13）',fix:{kind:'none'}},
  {key:'venv',group:'运行环境',label:'虚拟环境',state:'ok',detail:'用的就是本目录 .venv',fix:{kind:'none'}},
  {key:'disk',group:'运行环境',label:'磁盘空间',state:'ok',detail:'本盘剩余 273.5 GB（权重共约 30.3 GB）',fix:{kind:'none'}},
  {key:'pkg:torch',group:'依赖包',label:'torch 2.11.0',state:'ok',detail:'已装 2.11.0+cu128',fix:{kind:'pip'}},
  {key:'pkg:torchao',group:'依赖包',label:'torchao 0.18.0',state:'miss',detail:'没装',fix:{kind:'pip'}},
  {key:'pkg:diffusers',group:'依赖包',label:'diffusers 916a5791',state:'part',
   detail:'已装 0.41.0.dev0，但 commit 是 b1a2c3d4，清单钉的是 916a5791',fix:{kind:'pip'}},
  {key:'pkg:pywebview',group:'依赖包',label:'pywebview 6.2.1',state:'ok',detail:'已装 6.2.1',fix:{kind:'pip'}},
  {key:'pkg:websocket-client',group:'Moss 环境',label:'websocket-client 1.8.0',state:'ok',
   detail:'已装 1.8.0（Moss 的 /ws 步数进度靠它）',fix:{kind:'pip'}},
  {key:'model:turbo',group:'模型权重',label:'主力模型 Turbo（Qwen/Qwen-Image-2.1-Turbo）',state:'part',
   detail:'权重不完整：1 个文件字节数不对（transformer/diffusion_pytorch_model-00002-of-00002.safetensors） · 续传补齐即可',
   gb:30.3,fix:{kind:'model'}},
  {key:'comfy:app',group:'Moss 环境',label:'内嵌 ComfyUI（comfyui）',state:'miss',
   detail:'还没 clone（约 100MB · Comfy-Org/ComfyUI v0.42.1）',gb:0.1,fix:{kind:'comfyui'}},
  {key:'comfy:venv',group:'Moss 环境',label:'ComfyUI 独立环境',state:'miss',
   detail:'要先有 ComfyUI 本体才能建它的环境',gb:0,fix:{kind:'comfyvenv'}},
  {key:'moss:moss-comfy',group:'Moss 环境',label:'MOSS-Image 权重（Comfy-Org）',state:'miss',
   detail:'目录不存在：comfyui/models · 约 13 GB',gb:13.01,fix:{kind:'mossmodel'}},
  {key:'moss:moss-lora',group:'Moss 环境',label:'8 步 DMD LoRA（Kromoss）',state:'miss',
   detail:'目录不存在：comfyui/models/loras · 约 2.2 GB',gb:2.21,fix:{kind:'mossmodel'}},
  {key:'dir:outputs',group:'目录',label:'outputs/',state:'ok',detail:'可写',fix:{kind:'dir'}},
];
function envTodo(){return ENV.filter(x=>x.state==='miss'||x.state==='part').map(x=>x.key);}
/* 待补数按引擎拆一份（与 app.env_check 里那条判法一致）：欢迎页要说得出「这一路还差几项」 */
function envTodoBy(){
  const grp=k=>((ENV.find(x=>x.key===k)||{}).group)==='Moss 环境';
  const moss=envTodo().filter(k=>/^(comfy:|moss:)/.test(k)||grp(k)).length;
  const all=envTodo().length;
  return {qwen:all-moss,moss:moss};
}

/* 假任务推进：载入 3 轮 → 生成按步走 → 收尾出图 */
let loadTick=0,genTok=0,wantGen=false;
function finishGen(){
  const name='gen_'+stamp().replace(/[-: ]/g,'').slice(0,14)+'.png';
  const file=(cfg.console.output_dir+'/'+name).replace(/\\/g,'/');
  const it={file:file,name:name,t:stamp(),size:cfg.gen.size,seed:cfg.gen.seed,
            prompt:cfg.gen.prompt,url:thumbFor(file),
            mode:'gen',negative:cfg.gen.negative||'',steps:parseInt(cfg.gen.steps,10)||8,
            sec:+(8+Math.random()*6).toFixed(1),fav:0};
  GAL.unshift(it);
  if(GAL.length>60)GAL.length=60;
  st.img_count=GAL.length;
  st.last_image=file;
  st.last_sec=8.2+Math.random()*6;
  st.model_loaded=true;
  st.vram_used=9.6;
  st.running=null;st.status='✅ 完成 · '+name;
  L('✅ 已保存：'+file);
  L('── 结束 ──');
}
function advance(){
  if(st.running==='load'){
    if(st.engine==='moss'){
      mossLoadTick++;
      const LOAD=[[20,'拉起 ComfyUI 子进程'],[60,'等健康检查 /system_stats']][mossLoadTick-1]
        ||[99,'灌 MOSS 权重…'];
      st.load_pct=LOAD[0];st.load_stage=LOAD[1];
      L(mossLoadTick===1?'🌱 正在启动内嵌 ComfyUI（端口 '+MOSS.port+'）…':'ComfyUI 起来了，等它就位');
      if(mossLoadTick>=3)mossStep();
      return;
    }
    loadTick++;
    /* 与真后端同构：载入进度也是「百分比 + 阶段话术」，界面那条进度条不再只能空转 */
    const LOAD=[[8,'载入 processor'],[42,'载入 text_encoder'],[88,'载入 transformer']][loadTick-1]
      ||[99,'整理显存…'];
    st.load_pct=LOAD[0];st.load_stage=LOAD[1];
    L(loadTick===1?'载入模型（fp8 量化 + CPU offload）…':
      loadTick===2?'文本编码器就位':'DiT 权重就位，预热一遍');
    if(loadTick>=3){
      st.model_loaded=true;st.vram_used=9.6;st.status='模型已载入';st.load_pct=100;st.load_stage='已就绪';
      L('✅ 模型已载入 · 显存 9.6/12 GB');
      if(wantGen){wantGen=false;beginGen();}
      else st.running=null;
    }
    return;
  }
  if(st.running==='gen'){
    if(st.paused)return;
    st.done++;
    if(st.engine==='moss'){
      L(`第 ${st.done} / ${st.total} 步 去噪`);
      st.status=`去噪 ${st.done}/${st.total}`;
      st.vram_used=10.4+Math.random()*0.5;
      if(st.done>=st.total)finishMoss();
      return;
    }
    L(`第 ${st.done} / ${st.total} 步 去噪`);
    st.status=`去噪 ${st.done}/${st.total}`;
    st.vram_used=(String(cfg.gen.size).indexOf('1536')>=0?11.3:10.2)+Math.random()*0.4;
    if(st.done>=st.total)finishGen();
  }
}
function beginGen(){
  const steps=parseInt(cfg.gen.steps,10)||8;
  st.running='gen';st.done=0;st.total=steps;st.status='去噪 0/'+steps;
  L('🚀 开始'+(cfg.gen.mode==='rgba'?'透明素材':'生成')+'：'+cfg.gen.size+' · '+steps+' 步 · 种子 '+cfg.gen.seed);
}

/* ---------- Moss（内嵌 ComfyUI）假状态 ---------- */
const MOSS={installed:false,running:false,url:'',port:8876,pid:0,tier:'daily',loaded:false};
/* 档位步数与 App.MOSS_TIERS 对齐（mock 只管把界面演像，真档位定义在后端那张表里） */
const MOSS_STEPS={fast:8,mid:25,full:50};
let mossLoadTick=0, wantMossGen=false, mossQ=null;
function mossStep(){
  MOSS.loaded=true;st.model_loaded=true;st.comfyui_on=true;st.comfyui_loaded=true;st.moss_installed=true;
  st.load_pct=100;st.load_stage='已就绪';st.status='Moss 就绪';
  L('✅ ComfyUI 已就绪：'+MOSS.url+'（首次灌权重较慢）');
  MOSS.running=true;st.running=null;
  if(wantMossGen){wantMossGen=false;beginMossGen();}
}
function beginMossGen(){
  const steps=MOSS_STEPS[cfg.moss.quality]||8;
  const n=Math.max(1,Math.min(4,parseInt(cfg.moss.count,10)||1));
  st.engine='moss';st.running='gen';st.done=0;st.total=steps*n;
  st.model_loaded=true;st.comfyui_on=true;st.comfyui_loaded=true;MOSS.running=true;MOSS.loaded=true;
  st.status='去噪 0/'+(steps*n);mossQ=steps;
  L('🚀 开始 Moss('+cfg.moss.quality+')：'+cfg.moss.size+' · '+steps+' 步 × '+n+' 张 · '+
    (cfg.moss.seed<0?'随机种子':'种子 '+cfg.moss.seed+' 起，每张 +1'));
}
function mossYield(){
  if(MOSS.running||st.comfyui_on){L('🛑 已停止 ComfyUI 子进程，显存归还给外部文字模型软件');}
  MOSS.running=false;MOSS.loaded=false;st.comfyui_on=false;st.comfyui_loaded=false;st.comfyui_url='';
  if(st.engine==='moss'){st.model_loaded=false;st.vram_used=0.6;}
}
function finishMoss(){
  const name='moss_'+stamp().replace(/[-: ]/g,'').slice(0,14)+'.png';
  const file=(cfg.moss.output_dir+'/'+name).replace(/\\/g,'/');
  const n=Math.max(1,Math.min(4,parseInt(cfg.moss.count,10)||1));
  const base=parseInt(cfg.moss.seed,10);
  for(let i=0;i<n;i++){
    const f=n>1?file.replace(/\.png$/,'_'+(i+1)+'.png'):file;
    GAL.unshift({file:f,name:f.split('/').pop(),t:stamp(),size:cfg.moss.size,
      seed:(isNaN(base)||base<0)?(Date.now()%100000)+i:base+i,
      prompt:cfg.moss.prompt,url:thumbFor(f),mode:'moss',negative:cfg.moss.negative||'',
      steps:MOSS_STEPS[cfg.moss.quality]||8,sec:+(6+Math.random()*10).toFixed(1),fav:0});
  }
  if(GAL.length>60)GAL.length=60;
  st.img_count=GAL.length;st.last_image=file;st.last_sec=7.5+Math.random()*8;
  st.running=null;st.status='✅ 完成 · '+name;
  L('✅ 已保存：'+file);L('── 结束 ──');
}

L('就绪 · Qwen 生图控制台');
L('显存基线：桌面占用 0.6 / 12 GB');

window.MIC_MOCK={
  boot(){return {cfg:cfg,state:st,version:'0.2.0-m2',default_nav:cfg.default_nav};},
  poll(c){advance();
    return {seq:seq,logs:logs.slice(c),state:st};},
  save_cfg(patch){
    (function merge(t,s){Object.keys(s||{}).forEach(k=>{
      if(s[k]&&typeof s[k]==='object'&&!Array.isArray(s[k])){
        if(typeof t[k]!=='object'||t[k]===null)t[k]={};merge(t[k],s[k]);}
      else t[k]=s[k];});})(cfg,patch);
    if(cfg.console.quant!==st.quant){st.quant=cfg.console.quant;
      L('量化方式已改为 '+(st.quant==='fp8'?'fp8（12G 推荐）':'不量化（12G 会溢出到共享内存）'));}
    return {ok:true,cfg:cfg};},
  pick(kind){return kind==='dir'?'D:/AI/Qwen-Image-2.1/outputs':'D:/AI/Qwen-Image-2.1/outputs/sample.png';},
  drop_path(items,kind){
    const n=String((items&&items[0])||'').split(/[\\/]/).pop()||'model';
    return Promise.resolve({ok:true,path:kind==='dir'?('D:/AI/Qwen-Image-2.1/models/'+n):('D:/AI/Qwen-Image-2.1/outputs/'+n)});
  },
  save_drop(n){
    const p='D:/AI/Qwen-Image-2.1/outputs/drop_refs/'+(String(n||'drop.png').split(/[\\/]/).pop());
    L('📥 拖放的文件已代收（mock）：'+p);
    return Promise.resolve({ok:true,path:p});
  },
  set_title(t){cfg.app_title=t;return {ok:true,title:t};},
  refresh_stats(){st.img_count=GAL.length;return {ok:true,state:st};},
  load_model(){
    if(st.running)return {ok:false,msg:'有任务在跑：'+st.running};
    if(st.engine==='moss'){
      st.running='load';mossLoadTick=0;wantMossGen=false;st.status='启动 ComfyUI…';MOSS.tier=cfg.moss.tier||'daily';
      return {ok:true};
    }
    st.running='load';loadTick=0;st.status='载入模型…';
    return {ok:true};},
  unload_model(){
    if(st.running)return {ok:false,msg:'有任务在跑：'+st.running};
    if(st.engine==='moss'){
      if(!(MOSS.running&&st.comfyui_on))return {ok:false,msg:'Moss 引擎本来就没在跑'};
      mossYield();st.model_loaded=false;st.status='Moss 已停止';
      return {ok:true};
    }
    st.model_loaded=false;st.vram_used=0.6;st.status='模型已卸载';
    L('已卸载模型 · 显存归还（0.6/12 GB）');
    return {ok:true};},
  start_gen(p){
    if(st.running)return {ok:false,msg:'有任务在跑：'+st.running};
    if(String((p||{}).engine||'')==='moss'){
      cfg.moss=Object.assign({},cfg.moss,p||{});delete cfg.moss.engine;
      if(String(cfg.moss.prompt||'').trim()==='')return {ok:false,msg:'提示词是空的，先写点想要什么'};
      if(!MOSS.installed)return {ok:false,msg:'Moss 环境还没补全：点「一键补全 Moss 环境」'};
      const steps=MOSS_STEPS[cfg.moss.quality]||8;
      const n=Math.max(1,Math.min(4,parseInt(cfg.moss.count,10)||1));
      if(MOSS.running&&st.comfyui_on){beginMossGen();return {ok:true,total:steps*n};}
      st.engine='moss';st.running='load';mossLoadTick=0;wantMossGen=true;
      st.status='启动 ComfyUI…';MOSS.tier=cfg.moss.tier||'daily';
      L('Moss 引擎未运行：先拉起 ComfyUI，随后自动开始生成');
      return {ok:true,total:steps*n};
    }
    cfg.gen=Object.assign(cfg.gen,p||{});
    if(String(cfg.gen.prompt||'').trim()==='')return {ok:false,msg:'提示词是空的，先写点想要什么'};
    if(!st.model_loaded){
      st.running='load';loadTick=0;wantGen=true;st.status='先载入模型…';
      L('模型未载入：先载入，随后自动开始生成');
      return {ok:true,total:parseInt(cfg.gen.steps,10)||8};
    }
    beginGen();
    return {ok:true,total:st.total};},
  stop(key){
    if(!st.running)return {ok:false,msg:'没有运行中的任务'};
    st.running=null;wantGen=false;wantMossGen=false;st.status='已停止';
    L('⏹ 已请求停止'+(key==='gen'?'：本步完成后中断':''));
    return {ok:true};},
  /* ---------- 引擎切换与 Moss 档位（同一时间只激活一个引擎；档位=显存分时） ---------- */
  set_engine(name){
    if(st.running)return {ok:false,msg:'有任务在跑：'+st.running};
    name=name==='moss'?'moss':'qwen';
    if(name==='qwen'){
      if(st.comfyui_on){mossYield();L('切换引擎：已停止 Moss（ComfyUI 子进程），显存让给千问');}
      st.engine='qwen';st.model_loaded=false;
      return {ok:true,engine:'qwen'};
    }
    st.engine='moss';
    if(st.model_loaded){mossYield();st.model_loaded=false;L('切换引擎：已卸载千问模型，显存让给 Moss');}
    cfg.engine='moss';
    if((cfg.moss.tier||'daily')==='daily'){
      st.running='load';mossLoadTick=0;wantMossGen=false;st.status='启动 ComfyUI…';
      MOSS.tier='daily';
    }else st.model_loaded=false;
    return {ok:true,engine:'moss'};},
  moss_set_tier(tier){
    if(st.running)return {ok:false,msg:'有任务在跑：'+st.running};
    tier=tier==='yield'?'yield':'daily';cfg.moss.tier=tier;st.moss_tier=tier;
    if(st.engine!=='moss')return {ok:true,tier:tier,engine:st.engine,msg:'档位已记录（切到 Moss 引擎时生效）'};
    if(tier==='yield'){mossYield();st.model_loaded=false;st.status='已让出显存';return {ok:true,tier:tier};}
    st.running='load';mossLoadTick=0;wantMossGen=false;st.status='启动 ComfyUI…';MOSS.tier='daily';
    L('🔋 切回「日常质量档」：拉起 ComfyUI…');
    return {ok:true,tier:tier};},
  moss_status(){
    MOSS.installed=MOSS.installed||st.moss_installed;
    return {ok:true,engine:st.engine,tier:cfg.moss.tier||'daily',
      installed:!!MOSS.installed,running:!!(MOSS.running&&st.comfyui_on),
      url:MOSS.running?MOSS.url:'',port:MOSS.port,pid:MOSS.running?MOSS.pid:0,
      loaded_model:!!MOSS.loaded,last_error:'',comfyui_dir:'comfyui',env_todo:st.env_todo};},
  thumb(p){return Promise.resolve({ok:true,url:thumbFor(p)});},
  /* 与 App.gallery_list 同形状：清单只带元信息，缩略图由界面滚到哪张才取哪张 */
  gallery_list(){st.img_count=GAL.length;
    const items=GAL.map(g=>{const o=Object.assign({},g);delete o.url;return o;});
    return Promise.resolve({ok:true,items:items,stats:{total:GAL.length,fav:GAL.filter(g=>g.fav).length}});},
  gallery_fav(f,on){
    const it=GAL.find(x=>x.file===f);
    if(!it)return {ok:false,msg:'这张已经不在了'};
    if(!it.mode)return {ok:false,msg:'老图没有参数记录，收藏不了'};
    it.fav=on?1:0;L((on?'已收藏：':'已取消收藏：')+it.name);
    return {ok:true};},
  gallery_delete(f){
    const i=GAL.map(x=>x.file).indexOf(f);
    if(i<0)return {ok:false,msg:'这张已经不在了'};
    L('已删除：'+GAL[i].name);GAL.splice(i,1);
    return {ok:true};},
  gallery_clear(){GAL.length=0;st.img_count=0;L('已清空输出目录（mock）');return {ok:true};},
  open_path(p){L('已打开：'+p);return {ok:true};},
  open_url(u){L('已在浏览器打开：'+u);return {ok:true};},
  api_state(){return {ok:true,cfg:cfg.api,on:st.api_on,url:st.api_url};},
  api_set(p){
    if('enabled' in p)cfg.api.enabled=!!p.enabled;
    if('lan' in p)cfg.api.lan=!!p.lan;
    if('no_token' in p)cfg.api.no_token=!!p.no_token;
    if('def_engine' in p)cfg.api.def_engine=p.def_engine;
    if('def_size' in p)cfg.api.def_size=p.def_size;
    if('port' in p)cfg.api.port=parseInt(p.port,10)||cfg.api.port;
    if(cfg.api.enabled&&!cfg.api.token){
      cfg.api.token='qic_'+Math.random().toString(16).slice(2,18);
      L('🔑 已生成 API 令牌');}
    st.api_on=cfg.api.enabled;
    st.api_url=cfg.api.enabled
      ?('http://'+(cfg.api.lan?'192.168.1.66':'127.0.0.1')+':'+cfg.api.port):'';
    L(cfg.api.enabled?('🌐 API 服务已启动：'+st.api_url+'（Bearer 令牌鉴权）')
      :'API 服务已停止');
    if(cfg.api.lan&&cfg.api.enabled)L('⚠️ 局域网模式：注意防火墙放行端口 '+cfg.api.port);
    return {ok:true,state:{cfg:cfg.api,on:st.api_on,url:st.api_url}};},
  api_token_reset(){
    cfg.api.token='qic_'+Math.random().toString(16).slice(2,18);
    L('🔑 API 令牌已重新生成');
    return {ok:true,state:{cfg:cfg.api,on:st.api_on,url:st.api_url}};},
  models_list(){
    return Promise.resolve({ok:true,dir:'D:/AI/Qwen-Image-2.1/models',
      items:MDL.map(m=>Object.assign({},m))});},
  models_set_active(n){
    if(!MDL.some(m=>m.name===n))return {ok:false,msg:'目录不存在：'+n};
    MDL.forEach(m=>m.active=(m.name===n));
    cfg.console.model_dir='D:/AI/Qwen-Image-2.1/models/'+n;
    L('已设为激活：'+n+(st.model_loaded?'（显存里还是旧模型，卸载重载入才生效）':''));
    return {ok:true,cfg:cfg};},
  models_download(repo,name){
    if(!/^[\w.-]+\/[\w.-]+$/.test(String(repo||'')))return {ok:false,msg:'仓库 ID 形状不对：应为 org/name'};
    const nm=String(name||'').trim()||String(repo).split('/').pop();
    if(!MDL.some(m=>m.name===nm))MDL.push({name:nm,gb:0,shards:0,index:false,active:false});
    L('⬇ 开始下载 '+repo+' → models/'+nm+'（hf-mirror 断点续传 · mock）');
    setTimeout(function(){
      const m=MDL.find(x=>x.name===nm);
      if(m){m.gb=31.2;m.shards=32;m.index=true;}
      L('✅ 下载完成：'+nm+'（32/32 个分片校验通过）');
    },4000);
    return {ok:true};},
  env_check(){
    /* 后端 env_check 顺手把待补数写进状态：环境与模型页的横幅靠它 */
    st.env_todo=envTodo().length;
    Object.assign(st,{env_todo_qwen:envTodoBy().qwen,env_todo_moss:envTodoBy().moss});
    return Promise.resolve({ok:true,spec:'env.json',gb:30.3,
      items:ENV.map(x=>Object.assign({},x,{fix:Object.assign({},x.fix)})),todo:envTodo()});},
  env_fix(keys){
    const want=Array.isArray(keys)?keys:envTodo();
    const hit=ENV.filter(x=>want.indexOf(x.key)>=0&&(x.state==='miss'||x.state==='part'));
    if(!hit.length)return {ok:true,count:0,msg:'没有需要补的'};
    st.env_busy=true;st.env_todo=hit.length;
    L('🔧 开始补全 '+hit.length+' 项：'+hit.map(x=>x.label).join('、'));
    setTimeout(function(){
      hit.forEach(function(x){
        const k=x.fix.kind;
        if(k==='pip')L('Successfully installed '+x.label);
        else if(k==='model')L('…下载中：models/ 当前 30.3 GB');
        else if(k==='comfyui')L('Cloning into comfyui/ … Receiving objects: 100%（v0.42.1）');
        else if(k==='comfyvenv')L('Successfully installed comfyui deps（独立 .venv）');
        else if(k==='mossmodel')L('✅ 权重就位：'+x.label);
        else L('✅ 建好目录 '+x.label);
        x.state='ok';
        x.detail=k==='pip'?'已装（刚补）'
          :(k==='model'||k==='mossmodel')?'文件齐全（校验过）'
          :k==='comfyui'?'main.py 就位'
          :k==='comfyvenv'?'.venv 已建'
          :'可写';
      });
      if(hit.some(x=>x.fix.kind==='mossmodel'||x.fix.kind==='comfyui'||x.fix.kind==='comfyvenv')){
        MOSS.installed=true;st.moss_installed=true;
      }
      L('✅ 补全结束：成功 '+hit.length+' · 失败 0 · 还差 0 项');
      st.env_busy=false;st.env_todo=envTodo().length;
      Object.assign(st,{env_todo_qwen:envTodoBy().qwen,env_todo_moss:envTodoBy().moss});
    },5000);
    return {ok:true,count:hit.length,labels:hit.map(x=>x.label)};},
};
})();
