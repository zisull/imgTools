/* dev/mock.js —— 浏览器预览用的假后端（正常启动不内联，仅截图/看界面用）
   提供 window.MIC_MOCK.*，接口签名与 webui/app.py 的 js_api 一一对应。 */
(function(){
const cfg={
  app_title:'Qwen 生图控制台',theme:'tide',mode:'dark',layout:'tree',sidebar_min:false,
  notify:true,last_tab:'t_gen',nav_ver:12,open:{},welcomed:true,env_tab:'base',
  /* 环境开关：关掉的那路后端不体检、界面不显示（env_check 先按这份过滤） */
  env_on:{base:true,qwen:true,moss:true,h3:true},
  console:{model_dir:'D:/AI/Qwen-Image-2.1/envs/qwen/models/Qwen-Image-2.1-Turbo',
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
  video:{prompt:'一只猫推开木门，阳光落在地板上，镜头缓慢推进',
        seconds:5,size:'1344x768',cw:1344,ch:768,first:'',seed:-1,
        exec:'local',cloud_acct:''},
  film:{story:'雨夜的旧书店，一个女孩推门进来，抖落伞上的水，店主抬头，两人认出彼此。',
        total:60,shot:15,size:'768x1344',cw:768,ch:1344,exec:'cloud',mode:'chain',
        first:'',style:'电影感写实',acct:'',retry:2,seed:-1},
  ai:{base:'https://api.deepseek.com',model:'deepseek-chat',temp:0.7},
  api:{enabled:false,lan:false,host:'127.0.0.1',port:8765,token:'',no_token:false,
       def_engine:'follow',def_size:'1024x1024'},
  cloud:{port:9333,base:'https://www.runninghub.cn',login_url:'',browser:'',
         domains:['runninghub.cn'],show_browser:true,keep:true,keep_min:30,concurrency:1,
         wf_preset:'default',workflow:'',exec_tag:'Plus',poll_sec:5,gen_timeout:1800},
  nav:[
    {id:'g_out',type:'group',name:'创作',icon:'flower',children:[
      {id:'t_gen',type:'tab',name:'文生图',icon:'flower',page:'t2i'},
      {id:'t_edit',type:'tab',name:'图像编辑',icon:'wand',page:'edit'},
      {id:'t_inp',type:'tab',name:'局部重绘',icon:'brush',page:'inpaint'},
      {id:'t_vid',type:'tab',name:'视频生成',icon:'film',page:'video'},
      {id:'t_film',type:'tab',name:'剧本成片',icon:'play',page:'film'}]},
    {id:'g_sys',type:'group',name:'系统',icon:'cog',children:[
      {id:'t_env',type:'tab',name:'环境管理',icon:'db',page:'env'},
      {id:'t_gal',type:'tab',name:'作品画廊',icon:'image',page:'gallery'},
      {id:'t_log',type:'tab',name:'运行日志',icon:'hist',page:'logs'},
      {id:'t_set',type:'tab',name:'全局设置',icon:'cog',page:'settings'}]},
  ],
};
cfg.default_nav=JSON.parse(JSON.stringify(cfg.nav));

const st={running:null,status:'就绪',done:0,total:0,
  model_loaded:false,model_name:'Qwen-Image-2.1-Turbo',quant:'fp8',
  vram_used:0.6,vram_total:12,img_count:6,last_sec:28.4,
  last_image:'D:/AI/Qwen-Image-2.1/outputs/gen_20261013_094107.png',
  api_on:false,api_url:'',load_pct:0,load_stage:'',env_busy:false,env_todo:null,
  env_on:{base:true,qwen:true,moss:true,h3:true},env_todo_by:{},
  engine:'qwen',moss_tier:'daily',moss_installed:false,comfyui_on:false,comfyui_loaded:false,comfyui_url:'',
  cloud_busy:'',cloud_msg:'',ffmpeg:true,ai_key:false,
  /* 云端任务单独一条线：和 st.running 互不覆盖，界面靠它演示「云端在跑本地照常出图」 */
  cloud:{run:null,task:'',status:'',done:0,total:0,t_start:0,elapsed:0,last_fail:''},
  film:{state:'idle',phase:'',status:'',id:'',title:'',dir:'',total:0,done:0,current:0,
        elapsed:0,film:'',err:'',shots:[],missing:0,merge_ok:true,msg:'',exec:'',mode:''}};

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
  /* 成片：后端给 video:true，画廊不取缩略，整块砖是放片按钮 */
  {file:'D:/AI/Qwen-Image-2.1/outputs/h3_20261013_115230.mp4',name:'h3_20261013_115230.mp4',
   t:'2026-10-13 11:52',size:'1344×768',seed:88,prompt:'一只猫推开木门，阳光落在地板上，镜头缓慢推进',
   mode:'h3',negative:'',steps:4,sec:96.5,fav:0,video:true},
];
GAL.forEach(g=>g.url=thumbFor(g.file));
/* 删除撤销的假回收站：只留最近删的那张，跟真后端的「栈顶可撤销」同义 */
const GAL_TRASH=[];

/* 模型清单种子：形状与 App.models_list 一致 */
const MDL=[
  {name:'Qwen-Image-2.1-Turbo',gb:31.2,shards:32,index:true,active:true},
  {name:'Qwen-Image-2.1',gb:0,shards:0,index:false,active:false},
];

/* 体检种子：形状与 webui/env_check.check() 一致。
   故意留三项「没装/待补」，方便在浏览器里核对补全那条 UI 路径长什么样。 */
const ENV=[
  {key:'python',group:'运行环境',env:'base',label:'Python 解释器',state:'ok',detail:'当前 3.12.10（要求 3.11~3.13）',fix:{kind:'none'}},
  {key:'venv',group:'运行环境',env:'base',label:'虚拟环境',state:'ok',detail:'用的就是本目录 .venv',fix:{kind:'none'}},
  {key:'disk',group:'运行环境',env:'base',label:'磁盘空间',state:'ok',detail:'本盘剩余 273.5 GB（待补权重约 30.3 GB）',fix:{kind:'none'}},
  {key:'pkg:torch',group:'依赖包',env:'qwen',label:'torch 2.11.0',state:'ok',detail:'已装 2.11.0+cu128',fix:{kind:'pip'}},
  {key:'pkg:torchao',group:'依赖包',env:'qwen',label:'torchao 0.18.0',state:'miss',detail:'没装',fix:{kind:'pip'}},
  {key:'pkg:diffusers',group:'依赖包',env:'qwen',label:'diffusers 916a5791',state:'part',
   detail:'已装 0.41.0.dev0，但 commit 是 b1a2c3d4，清单钉的是 916a5791',fix:{kind:'pip'}},
  {key:'pkg:pywebview',group:'依赖包',env:'base',label:'pywebview 6.2.1',state:'ok',detail:'已装 6.2.1',fix:{kind:'pip'}},
  {key:'pkg:websocket-client',group:'依赖包',env:'moss',label:'websocket-client 1.8.0',state:'ok',
   detail:'已装 1.8.0（Moss 的 /ws 步数进度靠它）',fix:{kind:'pip'}},
  {key:'model:turbo',group:'模型权重',env:'qwen',label:'主力模型 Turbo（Qwen/Qwen-Image-2.1-Turbo）',state:'part',
   detail:'权重不完整：1 个文件字节数不对（transformer/diffusion_pytorch_model-00002-of-00002.safetensors） · 续传补齐即可',
   gb:30.3,fix:{kind:'model'}},
  {key:'comfy:app',group:'ComfyUI 运行时',env:'moss',label:'内嵌 ComfyUI（comfyui）',state:'miss',
   detail:'还没 clone（约 100MB · Comfy-Org/ComfyUI v0.42.1）',gb:0.1,fix:{kind:'comfyui'}},
  {key:'comfy:venv',group:'ComfyUI 运行时',env:'moss',label:'ComfyUI 独立环境',state:'miss',
   detail:'要先有 ComfyUI 本体才能建它的环境',gb:0,fix:{kind:'comfyvenv'}},
  {key:'model:moss-comfy',group:'模型权重',env:'moss',label:'MOSS-Image 权重（Comfy-Org）',state:'miss',
   detail:'目录不存在：envs/moss/models · 约 13 GB',gb:13.01,fix:{kind:'model'}},
  {key:'model:moss-lora',group:'模型权重',env:'moss',label:'8 步 DMD LoRA（Kromoss）',state:'miss',
   detail:'目录不存在：envs/moss/models/loras · 约 1.1 GB',gb:1.1,fix:{kind:'model'}},
  {key:'model:h3-fl2va',group:'模型权重',env:'h3',optional:true,label:'H3 图生视频权重（41.4 GB）',
   state:'miss',detail:'目录不存在：envs/h3/models · 约 41.37 GB',gb:41.37,fix:{kind:'model'}},
  {key:'tool:ffmpeg',group:'扩展工具',env:'ffmpeg',optional:true,label:'FFmpeg 静态包（约 190 MB）',
   state:'ok',detail:'已装 · envs/ffmpeg/bin',
   fix:{kind:'tool',key:'ffmpeg',dest:'envs/ffmpeg/bin',files:['ffmpeg.exe','ffprobe.exe'],urls:[]}},
  {key:'dir:outputs',group:'目录',env:'base',label:'outputs/',state:'ok',detail:'可写',fix:{kind:'dir'}},
];
const ENVS=[
  {id:'base',label:'基础',icon:'db',engine:'',title:'基础（两路共用）',optional:false,
   desc:'主 .venv、界面壳与输出目录；两个引擎都靠它。'},
  {id:'qwen',label:'千问',icon:'flower',engine:'qwen',title:'千问环境',optional:false,
   desc:'diffusers 进程内直跑。主 .venv + envs/qwen/models。'},
  {id:'moss',label:'Moss',icon:'wave',engine:'moss',title:'Moss 环境',optional:false,
   desc:'内嵌 ComfyUI 子进程（共用 comfyui/ 与它的 .venv）。权重在 envs/moss/models。'},
  {id:'h3',label:'H3 视频',icon:'film',engine:'moss',title:'H3 视频（可选）',optional:true,
   desc:'MiniMax H3 图生视频，共用 Moss 的 ComfyUI 运行时；默认不下载。'},
  {id:'ffmpeg',label:'FFmpeg',icon:'scissors',engine:'',title:'FFmpeg（可选）',optional:true,tool:true,
   desc:'把多段成片拼成一部短剧，并抽尾帧接下一镜；不装也能逐段出片。'},
];
/* 关掉的环境当它不存在：与 app.env_check 同一条规矩（先过滤，再算待补） */
function envLive(){
  const o=cfg.env_on||{};
  return ENV.filter(x=>o[String(x.env||'base')]!==false)
            .map(x=>Object.assign({},x,{optional:false}));   // 开着就不算「可选」
}
function envTodo(){
  return envLive().filter(x=>x.state==='miss'||x.state==='part').map(x=>x.key);
}
/* 待补数按环境拆一份：基础项只归基础页，不重复算进每个引擎（与后端一致） */
function envTodoBy(){
  const n={base:0,qwen:0,moss:0,h3:0};
  envLive().forEach(function(x){
    if(x.state!=='miss'&&x.state!=='part')return;
    const e=String(x.env||'base');n[e]=(n[e]||0)+1;
  });
  return n;
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
  advanceCloud();
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
    return;
  }
  /* 出片只有 4 步（Turbo LoRA 烘死的），mock 照同样节奏走 */
  if(st.running==='video'){
    st.done++;
    L(`第 ${st.done} / ${st.total} 步 采样`);
    st.status=`出片 ${st.done}/${st.total}`;
    st.vram_used=11.0+Math.random()*0.4;
    if(st.done>=st.total)finishVideo();
    return;
  }
  /* 成片：每两轮走完一段，界面上的时间线能看见「跑完 → 下一段」 */
  if(st.running==='film'){
    const fs=st.film;
    filmStep(fs);
    if(fs.done>=fs.total)finishFilm();
    return;
  }
  if(st.running==='film_merge')finishFilm();
}
function beginGen(){
  const steps=parseInt(cfg.gen.steps,10)||8;
  st.running='gen';st.done=0;st.total=steps;st.status='去噪 0/'+steps;
  L('🚀 开始'+(cfg.gen.mode==='rgba'?'透明素材':'生成')+'：'+cfg.gen.size+' · '+steps+' 步 · 种子 '+cfg.gen.seed);
}
/* 成片：mock 也落一条带 video 标记的画廊项，界面那块的砖才知道自己是影片 */
function finishVideo(){
  const name='h3_'+stamp().replace(/[-: ]/g,'').slice(0,14)+'.mp4';
  const file=(cfg.console.output_dir+'/'+name).replace(/\\/g,'/');
  GAL.unshift({file:file,name:name,t:stamp(),size:cfg.video.size,seed:cfg.video.seed,
               prompt:cfg.video.prompt,mode:'h3',negative:'',steps:4,
               sec:+(70+Math.random()*40).toFixed(1),fav:0,video:true});
  if(GAL.length>60)GAL.length=60;
  st.img_count=GAL.length;st.last_image=file;st.last_sec=96.5;
  if(st.running==='video'){st.running=null;st.status='✅ 完成 · '+name;}
  L('✅ 已保存：'+file+' · 96.5 秒');
  L('── 结束 ──');
}

/* ---------- 成片与文本 API 假状态 ---------- */
const AI={has:false};
const FILM={tick:0};
function finishFilm(){
  const fs=st.film;
  const name='film_'+stamp().replace(/[-: ]/g,'').slice(0,14)+'.mp4';
  const file=(cfg.console.output_dir+'/'+name).replace(/\\/g,'/');
  fs.state='done';fs.phase='完成';fs.status='✅ 成片完成';fs.film=file;fs.current=0;
  fs.shots.forEach(function(s){if(s.state==='run')s.state='done';});
  fs.done=fs.total;
  if(st.running==='film'){st.running=null;st.status='✅ 成片完成';}
  GAL.unshift({file:file,name:name,t:stamp(),size:(fs.width||768)+'×'+(fs.height||1344),
               seed:-1,prompt:cfg.film.story,mode:'film',negative:'',steps:0,
               sec:fs.elapsed,fav:0,video:true});
  st.img_count=GAL.length;
  L('✅ 成片已保存：'+file);L('── 成片结束 ──');
}
/* 云端那条线单独走：本地在出图时它照样能推进，两边的收尾互不覆盖 */
function filmStep(fs){
  fs.elapsed=+(fs.elapsed+0.8).toFixed(1);
  if(FILM.tick++%2)return;
  const cur=fs.shots.filter(s=>s.state==='run')[0];
  if(cur){
    cur.state='done';cur.sec=8.4;
    cur.frame_abs='D:/AI/Qwen-Image-2.1/outputs/films/demo/frames/'+
      String(cur.i).padStart(3,'0')+'.jpg';
    fs.done++;
  }
  const nxt=fs.shots.filter(s=>s.state==='wait')[0];
  if(nxt){
    nxt.state='run';fs.current=nxt.i;
    fs.status='第 '+nxt.i+'/'+fs.total+' 段 · '+(fs.exec==='cloud'?'云端':'本地')+'出片中';
  }
}
function advanceCloud(){
  const c=st.cloud;if(!c.run)return;
  c.elapsed=+(Number(c.elapsed)+0.8).toFixed(1);
  if(c.run==='video'){
    c.done=(Number(c.done)||0)+1;c.total=1;c.status='云端出片中';
    if(c.done>=c.total){
      finishVideo();
      c.status='✅ 云端出片完成';c.run=null;c.elapsed=0;
    }
    return;
  }
  if(c.run==='film'){
    const fs=st.film;
    filmStep(fs);
    c.done=fs.done;c.total=fs.total;c.status=fs.status;
    if(fs.done>=fs.total){
      finishFilm();
      c.status='✅ 云端成片完成';c.run=null;c.elapsed=0;
    }
  }
}

/* ---------- Moss（内嵌 ComfyUI）假状态 ---------- */
const MOSS={installed:false,running:false,url:'',port:8876,pid:0,tier:'daily',loaded:false};
/* 档位步数与 App.MOSS_TIERS 对齐（mock 只管把界面演像，真档位定义在后端那张表里） */
const MOSS_STEPS={fast:8,mid:25,full:50};
let mossLoadTick=0, wantMossGen=false, mossQ=null, wantVideo=false;
function mossStep(){
  MOSS.loaded=true;st.model_loaded=true;st.comfyui_on=true;st.comfyui_loaded=true;st.moss_installed=true;
  st.load_pct=100;st.load_stage='已就绪';st.status='Moss 就绪';
  L('✅ ComfyUI 已就绪：'+MOSS.url+'（首次灌权重较慢）');
  MOSS.running=true;st.running=null;
  if(wantVideo){
    /* 载入接出片：和真后端那条 chain_fn 同构 */
    wantVideo=false;st.running='video';st.done=0;st.total=4;st.status='出片 0/4';
    L('🎬 开始出片：'+(cfg.video.seconds||5)+' 秒 · '+cfg.video.size+' · 4 步');
    return;
  }
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

/* 云端账号假数据：只用于浏览器里看页面，真实快照在 data/cloud/（脚本不内联） */
/* 和 cloudkit.gen 同步：默认是之前那张 FeiHou 画布，金鱼单独一项 */
const WF_DEFAULT='2117505440799084545';
const WF_GOLDFISH='2109907990638850050';
const WF_CHOICES=[
  {code:'default',name:'默认 · H3 参考生视频',id:WF_DEFAULT},
  {code:'goldfish',name:'金鱼 · MiniMax H3 参考生视频',id:WF_GOLDFISH},
  {code:'custom',name:'指定地址 / 本地文件',id:''}];
const CLOUD={
  br:{on:true,port:9333,base:'https://www.runninghub.cn',account:'acc_demo1'},
  keep:{on:true,min:30,last:Date.now()/1000-600,msg:'保活完成：2 个账号',purpose:''},
  accts:[
    {id:'acc_demo1',name:'主号',created:Date.now()/1000-86400*3,last_saved:Date.now()/1000-3600,
     last_check:Date.now()/1000-600,state:'ok',detail:'页面有登录后的入口',backups:4,has_key:true},
    {id:'acc_demo2',name:'小号',created:Date.now()/1000-86400,last_saved:Date.now()/1000-86400,
     last_check:Date.now()/1000-7200,state:'expired',detail:'页面只有登录入口',backups:2,has_key:false},
  ],
};

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
    return Promise.resolve({ok:true,path:kind==='dir'?('D:/AI/Qwen-Image-2.1/envs/qwen/models/'+n):('D:/AI/Qwen-Image-2.1/outputs/'+n)});
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
  stop(key,lane){
    if(lane==='cloud'){
      const c=st.cloud;
      if(!c.run)return {ok:false,msg:'云端没有运行中的任务'};
      if(st.film&&c.run==='film'){st.film.state='stopped';st.film.phase='已停';
        st.film.status='已停止 · '+st.film.done+'/'+st.film.total+' 段';}
      c.status='已停止';c.run=null;
      L('⏹ 已请求停止云端任务：平台上那半截可能还在跑');
      return {ok:true};
    }
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
    L('已删除：'+GAL[i].name+'（可撤销）');
    GAL_TRASH.push(GAL[i]);GAL.splice(i,1);
    return {ok:true,undo:true};},
  gallery_undo(){
    const it=GAL_TRASH.pop();
    if(!it)return {ok:false,msg:'没有可撤销的删除'};
    GAL.push(it);L('已撤销删除：'+it.name);
    return {ok:true,file:it.file,name:it.name};},
  gallery_clear(){GAL.length=0;GAL_TRASH.length=0;st.img_count=0;L('已清空输出目录（mock）');return {ok:true};},
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
    return Promise.resolve({ok:true,dir:'D:/AI/Qwen-Image-2.1/envs/qwen/models',
      items:MDL.map(m=>Object.assign({},m))});},
  models_set_active(n){
    if(!MDL.some(m=>m.name===n))return {ok:false,msg:'目录不存在：'+n};
    MDL.forEach(m=>m.active=(m.name===n));
    cfg.console.model_dir='D:/AI/Qwen-Image-2.1/envs/qwen/models/'+n;
    L('已设为激活：'+n+(st.model_loaded?'（显存里还是旧模型，卸载重载入才生效）':''));
    return {ok:true,cfg:cfg};},
  models_download(repo,name){
    if(!/^[\w.-]+\/[\w.-]+$/.test(String(repo||'')))return {ok:false,msg:'仓库 ID 形状不对：应为 org/name'};
    const nm=String(name||'').trim()||String(repo).split('/').pop();
    if(!MDL.some(m=>m.name===nm))MDL.push({name:nm,gb:0,shards:0,index:false,active:false});
    L('⬇ 开始下载 '+repo+' → envs/qwen/models/'+nm+'（hf-mirror 断点续传 · mock）');
    setTimeout(function(){
      const m=MDL.find(x=>x.name===nm);
      if(m){m.gb=31.2;m.shards=32;m.index=true;}
      L('✅ 下载完成：'+nm+'（32/32 个分片校验通过）');
    },4000);
    return {ok:true};},
  env_check(){
    /* 后端 env_check 顺手把待补数按环境写进状态：环境页的横幅与开关那行字靠它 */
    st.env_on=Object.assign({},cfg.env_on);
    st.env_todo_by=envTodoBy();
    st.env_todo=envTodo().length;
    const items=envLive();
    return Promise.resolve({ok:true,spec:'envs/index.json',gb:30.3,envs:ENVS,
      items:items,todo:items.filter(x=>x.state==='miss'||x.state==='part').map(x=>x.key),
      env_on:st.env_on});},
  /* 环境开关：关掉就顺手把显存里那一路交还（与 app.env_set 同构） */
  env_set(id,want){
    if(id==='base'||!ENVS.some(e=>e.id===id))return {ok:false,msg:'没有这个环境：'+id};
    cfg.env_on[id]=!!want;
    /* 后端 env_set 顺手把开关表刷进状态（_sync_env_on），轮询带出去的就是那一份：
       假后端也必须同步，否则界面本地改的 st.env_on 会被下一轮轮询用旧值盖回去，
       关掉的环境八百毫秒后又「活了」——探针抓到过这个。 */
    st.env_on=Object.assign({},cfg.env_on);
    st.env_todo_by=envTodoBy();
    st.env_todo=envTodo().length;
    const lb=(ENVS.filter(e=>e.id===id)[0]||{}).label||id;
    L('🎚️ 环境'+(want?'开启':'关闭')+'：'+lb);
    if(!want){
      const o=cfg.env_on;
      const still=st.engine==='qwen'?o.qwen:(o.moss||o.h3);
      if(!still){
        if(st.engine==='moss'){MOSS.running=false;MOSS.loaded=false;
          st.comfyui_on=false;st.comfyui_loaded=false;st.comfyui_url='';}
        st.model_loaded=false;st.vram_used=0.6;
        L('🪫 环境已关闭：显存交还系统');
      }
    }
    return {ok:true,env_on:Object.assign({},cfg.env_on),cfg:cfg};},
  /* H3 出片：本地那条没拉起 ComfyUI 时先走载入再自动接上；云端只等、不出步数 */
  video_gen(p){
    const body=Object.assign({},cfg.video,p||{});
    Object.keys(p||{}).forEach(k=>{cfg.video[k]=p[k];});
    const n=parseInt(body.seconds,10)||5;
    if(String(body.exec)==='cloud'){
      if(!cfg.cloud.workflow)return {ok:false,msg:'没给工作流：在视频页填一个已跑通过的 H3 工作流地址'};
      if(st.cloud.run)return {ok:false,msg:'云端已经有一段在跑：等它结束再开新片'};
      st.cloud={run:'video',task:'视频',status:'云端准备中…',done:0,total:1,
                t_start:Date.now()/1000,elapsed:0,last_fail:''};
      L('☁️ 云端出片：'+n+' 秒 · '+String(body.size).replace('x','×')+' · 号「主号」· 平台计费');
      return {ok:true,total:1,exec:'cloud',acct:'主号'};
    }
    if(cfg.env_on&&cfg.env_on.h3===false)return {ok:false,msg:'H3 环境已关闭 · 到「环境管理 → H3」开启'};
    if(!String(body.prompt||'').trim())return {ok:false,msg:'先写一句想要什么画面'};
    st.total=4;st.done=0;st.engine='moss';st.video_exec='local';
    const started=MOSS.running||st.comfyui_on;
    if(!started){
      st.running='load';st.load_pct=0;st.load_stage='拉起 ComfyUI 子进程';wantVideo=true;
      L('H3 引擎未运行：先拉起 ComfyUI，随后自动开始出片');
      return {ok:true,total:4,frames:n*24};
    }
    st.running='video';st.status='出片 0/4';
    L('🎬 开始出片：'+n+' 秒 · '+String(body.size).replace('x','×')+' · 4 步 · '+
      (body.seed<0?'随机种子':'种子 '+body.seed)+
      (body.first?' · 参考图 '+String(body.first).split(/[\\/]/).pop():''));
    return {ok:true,total:4,frames:n*24};},
  /* ---------- 文本 API：拆镜/润色；Key 只记「有没有」，界面拿不到明文 ---------- */
  ai_state(){return {ok:true,has_key:AI.has,base:cfg.ai.base,model:cfg.ai.model,
    env:false,saved:AI.has};},
  ai_set(p){
    p=p||{};
    if(String(p.key||'').trim())AI.has=true;
    if(p.base)cfg.ai.base=p.base;
    if(p.model)cfg.ai.model=p.model;
    if(p.temp!=null)cfg.ai.temp=p.temp;
    st.ai_key=AI.has;
    L('🔐 文本 API 设置已更新（Key '+(AI.has?'已保存':'未填')+'）');
    return this.ai_state();},
  ai_key_clear(){AI.has=false;st.ai_key=false;L('🔐 文本 API Key 已清除');
    return this.ai_state();},
  ai_test(){return Promise.resolve({ok:true,ms:126,model:cfg.ai.model,reply:'可用'});},
  ai_polish(text){
    return Promise.resolve({ok:true,text:'傍晚旧书店门口，美少女站在半开的木门旁，中景略低机位，'
      +'镜头从她侧后方缓慢推近；暖黄顶灯与冷蓝街灯对打，背景书架层层退远。'+String(text||'')});},
  /* ---------- 成片：拆分镜 → 逐段出片 → 合成 ---------- */
  film_plan(p){
    const f=Object.assign({},cfg.film,p||{});
    if(String(f.story||'').trim().length<4)return {ok:false,msg:'先写一段剧情'};
    const shot=[5,10,15].indexOf(+f.shot)>=0?+f.shot:15;
    const total=parseInt(f.total,10)||60;
    if(total>40*shot)return {ok:false,msg:'最多 40 段：把总时长压到 600 秒内，或拆成两集'};
    const n=Math.max(1,Math.min(40,Math.round(total/shot)));
    const shots=[];
    for(let i=1;i<=n;i++)shots.push({i:i,summary:'第 '+i+' 镜：雨夜旧书店',
      prompt:'镜头 '+i+'：美少女推开旧书店木门，雨水顺伞尖滴落，暖黄灯光照亮侧脸，'
        +'主体居左，镜头缓慢推进，浅景深，电影感写实。',seconds:shot});
    return Promise.resolve({ok:true,title:'雨夜旧书店',shots:shots,count:n,
      shot_sec:shot,total_sec:n*shot});},
  film_start(p){
    const f=Object.assign({},cfg.film,p||{});
    const cloud=String(f.exec)==='cloud';
    if(cloud?st.cloud.run:st.running)
      return {ok:false,msg:'有任务在跑：'+(cloud?st.cloud.run:st.running)};
    const shot=[5,10,15].indexOf(+f.shot)>=0?+f.shot:15;
    let rows=(p&&p.shots)||[];
    if(rows.length>40)return {ok:false,msg:'最多 40 段：把总时长压到 600 秒内，或拆成两集'};
    if(!rows.length){
      const n=Math.max(1,Math.min(40,Math.round((parseInt(f.total,10)||60)/shot)));
      for(let i=1;i<=n;i++)rows.push({prompt:'第 '+i+' 镜：雨夜旧书店，美少女回头。',seconds:shot});
    }
    st.film={state:'running',phase:'出片',status:'准备中…',id:'demo',
      title:(p&&p.title)||'雨夜旧书店',dir:'D:/AI/Qwen-Image-2.1/outputs/films/demo',
      total:rows.length,done:0,current:1,elapsed:0,film:'',err:'',missing:0,
      merge_ok:true,msg:'',exec:f.exec,mode:f.mode,
      width:parseInt(f.cw,10)||768,height:parseInt(f.ch,10)||1344,
      shots:rows.map(function(r,i){return {i:i+1,summary:r.summary||'',
        prompt:r.prompt||'',seconds:r.seconds||shot,state:i===0?'run':'wait',
        file:'',frame:'',sec:0,err:'',file_abs:'',frame_abs:''};})};
    FILM.tick=0;
    if(cloud){
      st.cloud={run:'film',task:'成片',status:'准备中…',done:0,total:rows.length,
                t_start:Date.now()/1000,elapsed:0,last_fail:''};
    }else{st.running='film';st.status='准备中…';}
    L('🎬 成片开跑：'+st.film.title+' · '+rows.length+' 段 × '+shot+' 秒 · '
      +(cloud?'云端':'本地'));
    return {ok:true,shots:rows.length,shot_sec:shot,exec:f.exec,
      estimate:(rows.length*6)+'~'+(rows.length*10)+' 分钟'};},
  film_stop(){
    const fs=st.film;
    if(st.cloud.run==='film'){
      st.cloud.status='已停止';st.cloud.run=null;
      fs.state='stopped';fs.phase='已停';
      fs.status='已停止 · '+fs.done+'/'+fs.total+' 段';
      L('⏹ 成片已停：已出的段都留着');return {ok:true};
    }
    if(st.running!=='film')return {ok:false,msg:'成片没在跑'};
    st.running=null;
    fs.state='stopped';fs.phase='已停';
    fs.status='已停止 · '+fs.done+'/'+fs.total+' 段';
    L('⏹ 成片已停：已出的段都留着');return {ok:true};},
  film_state(){return {ok:true,film:st.film,ffmpeg:true,ai_key:AI.has};},
  film_list(){
    const fs=st.film;
    return {ok:true,items:fs.total?[{id:fs.id,title:fs.title,dir:fs.dir,time:stamp(),
      done:fs.done,total:fs.total,film:fs.film,current:true,
      running:st.running==='film'||st.cloud.run==='film'}]:[]};},
  /* 最近工程那行的 ×：真后端把整个目录搬进回收，这里只把状态清干净 */
  film_delete(dir){
    const fs=st.film;
    if(!fs.total||String(fs.dir)!==String(dir))
      return {ok:false,msg:'这个工程不在成片目录里，不动它'};
    if(st.running==='film'||st.cloud.run==='film')
      return {ok:false,msg:'这个工程正在跑：先停止再删'};
    L('🗑 删掉工程：'+fs.title+'（演示数据，没真搬文件）');
    Object.assign(fs,{state:'idle',phase:'',status:'',id:'',title:'',dir:'',total:0,done:0,
                      current:0,elapsed:0,film:'',err:'',shots:[],missing:0,msg:''});
    return {ok:true};},
  film_resume(){
    const fs=st.film;
    if(!fs.total)return {ok:false,msg:'还没有可续跑的工程'};
    if(fs.done>=fs.total&&fs.film)return {ok:true,msg:'这部已经完成了',film:fs.film};
    if(String(fs.exec)==='cloud'){
      if(st.cloud.run)return {ok:false,msg:'云端已经有一段在跑'};
      st.cloud={run:'film',task:'成片',status:'继续出片…',done:fs.done,total:fs.total,
                t_start:Date.now()/1000,elapsed:fs.elapsed||0,last_fail:''};
    }else{
      if(st.running)return {ok:false,msg:'有任务在跑：'+st.running};
      st.running='film';
    }
    fs.state='running';fs.phase='出片';FILM.tick=0;
    const nxt=fs.shots.filter(function(s){return s.state==='wait';})[0];
    if(nxt){nxt.state='run';fs.current=nxt.i;}
    L('▶️ 继续成片：'+fs.title);return {ok:true};},
  film_redo(i,deep){
    const fs=st.film;
    if(!fs.total)return {ok:false,msg:'没有工程'};
    i=Math.max(1,Math.min(fs.total,parseInt(i,10)||1));
    const hit=fs.shots.filter(function(s){return s.i===i||(deep&&s.i>i);});
    hit.forEach(function(s){s.state='wait';s.file='';s.frame='';s.frame_abs='';
      s.sec=0;s.err='';});
    fs.film='';fs.done=fs.shots.filter(function(s){return s.state==='done';}).length;
    fs.state='running';FILM.tick=0;
    if(String(fs.exec)==='cloud'){
      if(st.cloud.run)return {ok:false,msg:'云端已经有一段在跑'};
      st.cloud={run:'film',task:'成片',status:'重出第 '+i+' 段…',done:fs.done,
                total:fs.total,t_start:Date.now()/1000,elapsed:0,last_fail:''};
    }else{
      if(st.running)return {ok:false,msg:'有任务在跑：'+st.running};
      st.running='film';
    }
    L('↻ 重出第 '+i+' 段：作废 '+hit.length+' 段');
    return {ok:true,msg:'从第 '+i+' 段重出，作废 '+hit.length+' 段',count:hit.length};},
  film_redo_failed(){
    const fs=st.film;
    if(!fs.total)return {ok:false,msg:'没有工程'};
    const bad=fs.shots.filter(s=>s.state!=='done');
    if(!bad.length)return {ok:false,msg:'没有没出成的段：全部都在'};
    const i0=Math.min.apply(null,bad.map(s=>s.i));
    return this.film_redo(i0,String(fs.mode)==='chain');},
  film_merge(){
    const fs=st.film;
    if(!fs.done)return {ok:false,msg:'还没有一段成功出片'};
    st.running='film_merge';fs.state='running';fs.phase='合成';
    fs.status='合成中…';return {ok:true};},
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
        else if(k==='model')L('…下载中：'+x.detail.split('：')[1].split(' · ')[0]);
        else if(k==='comfyui')L('Cloning into comfyui/ … Receiving objects: 100%（v0.42.1）');
        else if(k==='comfyvenv')L('Successfully installed comfyui deps（独立 .venv）');
        else L('✅ 建好目录 '+x.label);
        x.state='ok';
        x.detail=k==='pip'?'已装（刚补）'
          :k==='model'?'文件齐全（校验过）'
          :k==='comfyui'?'main.py 就位'
          :k==='comfyvenv'?'.venv 已建'
          :'可写';
        if(x.env==='moss'&&(k==='model'||k==='comfyui'||k==='comfyvenv')){
          MOSS.installed=true;st.moss_installed=true;
        }
      });
      L('✅ 补全结束：成功 '+hit.length+' · 失败 0 · 还差 '+envTodo().length+' 项');
      st.env_busy=false;st.env_todo=envTodo().length;
      st.env_todo_by=envTodoBy();
    },5000);
    return {ok:true,count:hit.length,labels:hit.map(x=>x.label)};},
  cloud_state(){return {ok:true,dp:true,accounts:CLOUD.accts.map(a=>Object.assign({},a)),
    browser:Object.assign({},CLOUD.br),keep:Object.assign({},CLOUD.keep),
    busy:st.cloud_busy,msg:st.cloud_msg,concurrency:1,page:CLOUD.br.base};},
  /* 视频页云端那一格：只读档案，不起浏览器 */
  cloud_brief(){
    const accts=CLOUD.accts.filter(a=>a.state==='ok').map(a=>({id:a.id,name:a.name}));
    return {dp:true,accts:accts,wf:String(cfg.cloud.workflow||''),
      wf_preset:cfg.cloud.wf_preset||'default',wf_choices:WF_CHOICES,
      wf_default:WF_DEFAULT,wf_goldfish:WF_GOLDFISH,
      ready:accts.length>0,busy:!!st.cloud_busy||!!st.cloud.run};},
  /* 选完工作流先验结构：本地文件当场给结论，平台地址只能说「开页再验」 */
  cloud_check_wf(p){
    const s=String(p||cfg.cloud.workflow||'').trim();
    if(!s){
      if(cfg.cloud.wf_preset==='goldfish')
        return {ok:true,kind:'goldfish',msg:'当前用金鱼那张（MiniMax H3 参考生视频 #'+WF_GOLDFISH+'）'};
      return {ok:true,kind:'default',msg:'当前用默认那张（H3 参考生视频 #'+WF_DEFAULT+'）'};
    }
    if(!/\.(json|txt)$/i.test(s))
      return {ok:true,kind:'remote',msg:'平台工作流：开跑时进页面再验'};
    return {ok:true,kind:'file',nodes:100,links:75,shape:'kj',
      msg:'结构没问题：100 个节点 · 主节点/输出节点都在'};},
  cloud_new(name){
    const id='acc_'+Math.random().toString(36).slice(2,8);
    CLOUD.accts.push({id:id,name:String(name||'').trim()||('账号 '+(CLOUD.accts.length+1)),
      created:Date.now()/1000,last_saved:0,last_check:0,state:'pending',detail:'等待登录',backups:0,has_key:false});
    CLOUD.br.on=true;L('☁️ 新建登录：'+name+'（在浏览器里登录后点「保存」）');
    return {ok:true,account:{id:id},state:this.cloud_state()};},
  cloud_login(id){const a=CLOUD.accts.find(x=>x.id===id);if(a)a.state='pending';
    L('☁️ 打开登录页：'+(a?a.name:id));return {ok:true};},
  cloud_save(id){const a=CLOUD.accts.find(x=>x.id===id);if(!a)return {ok:false,msg:'账号不存在'};
    a.state='ok';a.detail='页面有登录后的入口';a.last_saved=Date.now()/1000;a.backups++;
    L('☁️ 登录态已保存：'+a.name+'（'+a.backups+' 份）');return {ok:true};},
  cloud_apply(id){const a=CLOUD.accts.find(x=>x.id===id);CLOUD.br.account=id;
    L('☁️ 切换到账号：'+(a?a.name:id));return {ok:true};},
  cloud_check(id){const a=CLOUD.accts.find(x=>x.id===id);if(!a)return {ok:false,msg:'账号不存在'};
    a.state='ok';a.detail='页面有登录后的入口';a.last_check=Date.now()/1000;
    st.cloud_msg=a.name+'：页面有登录后的入口';return {ok:true};},
  cloud_delete(id){const i=CLOUD.accts.findIndex(x=>x.id===id);if(i>=0)CLOUD.accts.splice(i,1);
    return {ok:true,state:this.cloud_state()};},
  cloud_rename(id,name){const a=CLOUD.accts.find(x=>x.id===id);if(a)a.name=name;
    return {ok:true,state:this.cloud_state()};},
  cloud_backups(id){const a=CLOUD.accts.find(x=>x.id===id);const n=a?a.backups:0;const out=[];
    for(let i=0;i<n;i++){const d=new Date(Date.now()-i*3600e3);const p=x=>String(x).padStart(2,'0');
      out.push({ts:'20261102-'+p(d.getHours())+p(d.getMinutes())+'00-000',
        label:p(d.getMonth()+1)+'-'+p(d.getDate())+' '+p(d.getHours())+':'+p(d.getMinutes())});}
    return {ok:true,spots:out,name:a?a.name:''};},
  cloud_restore(id,ts){L('☁️ 已恢复备份：'+ts);return {ok:true};},
  cloud_key_set(id,key){const a=CLOUD.accts.find(x=>x.id===id);if(a)a.has_key=true;
    L('☁️ 已保存 API Key：'+(a?a.name:id));return {ok:true,state:this.cloud_state()};},
  cloud_key_clear(id){const a=CLOUD.accts.find(x=>x.id===id);if(a)a.has_key=false;return {ok:true};},
  cloud_keep_now(){CLOUD.keep.last=Date.now()/1000;CLOUD.keep.msg='保活完成：'+CLOUD.accts.length+' 个账号';
    L('☁️ 浏览器保活：'+CLOUD.accts.length+' 个账号');return {ok:true};},
  cloud_browser_start(){CLOUD.br.on=true;L('☁️ 浏览器已启动（共用调试端口 9333）');return {ok:true};},
  cloud_browser_stop(){CLOUD.br.on=false;L('☁️ 浏览器已关闭');return {ok:true};},
  cloud_auth_names(id){return {ok:true,names:['Rh-Comfy-Auth','Rh-Identify']};},
};
})();
