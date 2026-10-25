/* dev/mock.js —— 浏览器预览用的假后端（正常启动不内联，仅截图/看界面用）
   提供 window.MIC_MOCK.*，接口签名与 webui/app.py 的 js_api 一一对应。 */
(function(){
const cfg={
  app_title:'Qwen 生图控制台',theme:'tide',mode:'dark',layout:'flat',sidebar_min:false,
  notify:true,last_tab:'t_ov',open:{},
  console:{model_dir:'D:/AI/Qwen-Image-2.1/models/Qwen-Image-2.1-Turbo',
           output_dir:'D:/AI/Qwen-Image-2.1/outputs',quant:'fp8',offload:true},
  gen:{prompt:'A neon-lit alley in the rain, reflections on wet pavement, cinematic lighting, 8k',
      negative:'',size:'1024x1024',steps:'8',seed:-1,count:1,kv_cache:true},
  edit:{prompt:'Turn the sketch into a photorealistic image on a white background.',
        negative:'',res:'512',steps:'8',seed:-1,count:1,kv_cache:true},
  inpaint:{prompt:'A pair of sunglasses resting on the dashboard.',
        negative:'',res:'512',steps:'8',seed:-1,count:1,kv_cache:true,brush:48},
  rgba:{prompt:'A flat vector icon of a lightbulb, isolated on a fully transparent background, sticker style.',
        negative:'',size:'1024x1024',steps:'8',seed:-1,count:1,kv_cache:true},
  api:{enabled:false,lan:false,host:'127.0.0.1',port:8765,token:''},
  nav:[
    {id:'t_ov',type:'tab',name:'概览',icon:'home',page:'overview'},
    {id:'t_gen',type:'tab',name:'文生图',icon:'flower',page:'t2i'},
    {id:'t_edit',type:'tab',name:'图像编辑',icon:'wand',page:'edit'},
    {id:'t_inp',type:'tab',name:'局部编辑',icon:'brush',page:'inpaint'},
    {id:'t_rgba',type:'tab',name:'透明素材',icon:'layers',page:'rgba'},
    {id:'t_gal',type:'tab',name:'画廊',icon:'image',page:'gallery'},
    {id:'t_pe',type:'tab',name:'提示词工坊',icon:'book',page:'pe'},
    {id:'t_mod',type:'tab',name:'模型管理',icon:'db',page:'models'},
    {id:'t_api',type:'tab',name:'API 服务',icon:'globe',page:'api'},
    {id:'t_set',type:'tab',name:'设置',icon:'cog',page:'settings'},
  ],
};
cfg.default_nav=JSON.parse(JSON.stringify(cfg.nav));

const st={running:null,status:'就绪',done:0,total:0,
  model_loaded:false,model_name:'Qwen-Image-2.1-Turbo',quant:'fp8',
  vram_used:0.6,vram_total:12,img_count:6,last_sec:28.4,
  last_image:'D:/AI/Qwen-Image-2.1/outputs/gen_20261013_094107.png',
  api_on:false,api_url:'',load_pct:0,load_stage:'',env_busy:false,env_todo:null};

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
  {key:'model:turbo',group:'模型权重',label:'主力模型 Turbo（Qwen/Qwen-Image-2.1-Turbo）',state:'part',
   detail:'权重不完整：1 个文件字节数不对（transformer/diffusion_pytorch_model-00002-of-00002.safetensors） · 续传补齐即可',
   gb:30.3,fix:{kind:'model'}},
  {key:'dir:outputs',group:'目录',label:'outputs/',state:'ok',detail:'可写',fix:{kind:'dir'}},
];
function envTodo(){return ENV.filter(x=>x.state==='miss'||x.state==='part').map(x=>x.key);}

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
    L(`第 ${st.done} / ${st.total} 步 去噪`);
    st.status=`去噪 ${st.done}/${st.total}`;
    st.vram_used=(String(cfg.gen.size).indexOf('1536')>=0?11.3:10.2)+Math.random()*0.4;
    if(st.done>=st.total)finishGen();
  }
}
function beginGen(){
  const steps=parseInt(cfg.gen.steps,10)||8;
  st.running='gen';st.done=0;st.total=steps;st.status='去噪 0/'+steps;
  L('🚀 开始生成：'+cfg.gen.size+' · '+steps+' 步 · 种子 '+cfg.gen.seed);
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
    st.running='load';loadTick=0;st.status='载入模型…';
    return {ok:true};},
  unload_model(){
    if(st.running)return {ok:false,msg:'有任务在跑：'+st.running};
    st.model_loaded=false;st.vram_used=0.6;st.status='模型已卸载';
    L('已卸载模型 · 显存归还（0.6/12 GB）');
    return {ok:true};},
  start_gen(p){
    if(st.running)return {ok:false,msg:'有任务在跑：'+st.running};
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
    st.running=null;wantGen=false;st.status='已停止';
    L('⏹ 已请求停止'+(key==='gen'?'：本步完成后中断':''));
    return {ok:true};},
  thumb(p){return Promise.resolve({ok:true,url:thumbFor(p)});},
  gallery_list(){st.img_count=GAL.length;return Promise.resolve({ok:true,items:GAL,stats:{total:GAL.length,fav:GAL.filter(g=>g.fav).length}});},
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
        else L('✅ 建好目录 '+x.label);
        x.state='ok';
        x.detail=k==='pip'?'已装（刚补）':k==='model'?'文件齐全（15 项校验过）':'可写';
      });
      L('✅ 补全结束：成功 '+hit.length+' · 失败 0 · 还差 0 项');
      st.env_busy=false;st.env_todo=0;
    },5000);
    return {ok:true,count:hit.length,labels:hit.map(x=>x.label)};},
};
})();
