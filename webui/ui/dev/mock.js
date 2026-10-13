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
  api:{enabled:false,host:'127.0.0.1',port:8765,token:''},
  nav:[
    {id:'t_ov',type:'tab',name:'概览',icon:'home',page:'overview'},
    {id:'t_gen',type:'tab',name:'文生图',icon:'flower',page:'t2i'},
    {id:'t_gal',type:'tab',name:'画廊',icon:'image',page:'gallery'},
    {id:'t_set',type:'tab',name:'设置',icon:'cog',page:'settings'},
  ],
};
cfg.default_nav=JSON.parse(JSON.stringify(cfg.nav));

const st={running:null,status:'就绪',done:0,total:0,
  model_loaded:false,model_name:'Qwen-Image-2.1-Turbo',quant:'fp8',
  vram_used:0.6,vram_total:12,img_count:6,last_sec:28.4,
  last_image:'D:/AI/Qwen-Image-2.1/outputs/gen_20261013_094107.png',
  api_on:false,api_url:''};

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

/* 画廊种子：形状与 App.gallery_list 一致（file/name/t/size/seed/prompt/url） */
const GAL=[
  {file:'D:/AI/Qwen-Image-2.1/outputs/gen_20261013_094107.png',name:'gen_20261013_094107.png',
   t:'2026-10-13 09:41',size:'1024×1024',seed:42,prompt:'A neon-lit alley in the rain…'},
  {file:'D:/AI/Qwen-Image-2.1/outputs/gen_20261013_091852.png',name:'gen_20261013_091852.png',
   t:'2026-10-13 09:18',size:'1536×1024',seed:7,prompt:'Chinese ink painting of misty mountains'},
  {file:'D:/AI/Qwen-Image-2.1/outputs/gen_20261012_223341.png',name:'gen_20261012_223341.png',
   t:'2026-10-12 22:33',size:'1024×1536',seed:-1,prompt:'Portrait of an elderly lighthouse keeper'},
  {file:'D:/AI/Qwen-Image-2.1/outputs/gen_20261012_215503.png',name:'gen_20261012_215503.png',
   t:'2026-10-12 21:55',size:'1024×1024',seed:2026,prompt:'Isometric smart warehouse, cutaway view'},
  {file:'D:/AI/Qwen-Image-2.1/outputs/gen_20261012_201144.png',name:'gen_20261012_201144.png',
   t:'2026-10-12 20:11',size:'1024×1024',seed:100,prompt:'产品白底图：磨砂黑保温杯，柔光'},
  {file:'D:/AI/Qwen-Image-2.1/outputs/gen_20261011_180209.png',name:'gen_20261011_180209.png',
   t:'2026-10-11 18:02',size:'1024×1024',seed:9,prompt:'Steampunk owl clockwork, macro detail'},
];
GAL.forEach(g=>g.url=thumbFor(g.file));

/* 假任务推进：载入 3 轮 → 生成按步走 → 收尾出图 */
let loadTick=0,genTok=0,wantGen=false;
function finishGen(){
  const name='gen_'+stamp().replace(/[-: ]/g,'').slice(0,14)+'.png';
  const file=(cfg.console.output_dir+'/'+name).replace(/\\/g,'/');
  const it={file:file,name:name,t:stamp(),size:cfg.gen.size,seed:cfg.gen.seed,
            prompt:cfg.gen.prompt,url:thumbFor(file)};
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
    L(loadTick===1?'载入模型（fp8 量化 + CPU offload）…':
      loadTick===2?'文本编码器就位':'DiT 权重就位，预热一遍');
    if(loadTick>=3){
      st.model_loaded=true;st.vram_used=9.6;st.status='模型已载入';
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
  gallery_list(){st.img_count=GAL.length;return Promise.resolve({ok:true,items:GAL});},
  gallery_delete(f){
    const i=GAL.map(x=>x.file).indexOf(f);
    if(i<0)return {ok:false,msg:'这张已经不在了'};
    L('已删除：'+GAL[i].name);GAL.splice(i,1);
    return {ok:true};},
  gallery_clear(){GAL.length=0;st.img_count=0;L('已清空输出目录（mock）');return {ok:true};},
  open_path(p){L('已打开：'+p);return {ok:true};},
  open_url(u){L('已在浏览器打开：'+u);return {ok:true};},
};
})();
