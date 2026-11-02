/* pages/env.js —— 环境：一个模型一页，开关、明细、一键补齐都在这页上
   开关是这一页的第一件事：关掉的环境后端根本不体检（env_check 先按 env_on 过滤），
   于是待补数、横幅提醒、功能页一起安静下来——用户要的是「关掉就当它不存在」。
   分区数据来自 envs/index.json 注册表（后端 env_check 回 r.envs），
   新增一个模型只要加一个 envs/<id>/ 目录 + 一条注册表，再在这张列表里加一页。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

let envItems=null, env=null, envAt=null, dir='', mdl=null;

const ST={ok:['on','ok','就绪'],miss:['','bad','没装'],part:['','bad','待补'],warn:['','','提醒']};
const G={PY:'运行环境',PKG:'依赖包',TOOL:'扩展工具',MODEL:'模型权重',RT:'ComfyUI 运行时',DIR:'目录'};
const ORDER=[G.PY,G.PKG,G.TOOL,G.RT,G.MODEL,G.DIR];

/* 工具环境（ffmpeg）没有自己的导航页，明细并到基础页；
   它们不是一路模型，缺了只算可选扩展，不进「还差几项」。 */
function toolIds(){
  return new Set(((env&&env.envs)||[]).filter(x=>x.tool).map(x=>x.id));
}

/* 页名与图标：环境 id → 这一页的表头。叫法跟着导航走，两字对齐。 */
const PAGES=[
  {id:'base',page:'env_base',name:'基础',icon:'db'},
  {id:'qwen',page:'env_qwen',name:'千问',icon:'flower'},
  {id:'moss',page:'env_moss',name:'Moss',icon:'wave'},
  {id:'h3',page:'env_h3',name:'H3',icon:'film'},
];

/* 后端还没回体检结果时的占位分区（真分区以 env.envs 为准）。 */
const FALLBACK={
  base:{id:'base',label:'基础',engine:'',title:'基础（两路共用）',desc:''},
  qwen:{id:'qwen',label:'千问',engine:'qwen',title:'千问环境',desc:''},
  moss:{id:'moss',label:'Moss',engine:'moss',title:'Moss 环境',desc:''},
  h3:{id:'h3',label:'H3 视频',engine:'moss',optional:true,title:'H3 视频环境',desc:''},
};

function meta(id){
  const e=(env&&env.envs||[]).filter(x=>x.id===id)[0];
  return e||FALLBACK[id]||{id:id,label:id,title:id,desc:''};
}
function on(id){
  if(id==='base')return true;
  const m=(MIC.s.st.env_on||MIC.s.cfg.env_on||{});
  return m[id]!==false;
}
function itemsOf(id){
  const out=[],tools=toolIds();
  (envItems||[]).forEach((it,i)=>{
    const e=String(it.env||'base');
    if(e===id||(id==='base'&&tools.has(e)))out.push({it:it,i:i});
  });
  return out;
}
function todoOf(id){
  /* optional 的工具项只叫「可选扩展没装」：在明细里能点补，但不计入
     「还差几项」、也不进一键补齐——不需要合成的用户不该一直被提醒。 */
  return itemsOf(id).filter(x=>(x.it.state==='miss'||x.it.state==='part')&&!x.it.optional);
}
function gbOf(list){
  let g=0;list.forEach(x=>{g+=Number(x.it.gb)||0;});
  return g?Math.round(g*10)/10:0;
}

function envRow(it,i){
  const s=ST[it.state]||ST.warn;
  const fixable=(it.state==='miss'||it.state==='part'||it.state==='warn')&&it.fix&&it.fix.kind!=='none';
  return `<div class="mrow">
    <div class="minfo"><b>${esc(it.label)}</b>
      <span class="mut fine">${esc(it.detail)}</span></div>
    <span class="grow"></span>
    ${fixable?'<button class="btn sm" onclick="MIC.env.fixAt('+i+')">'+ic('down','s')+'补这项</button>':''}
    <span class="pill ${s[0]}"><span class="dot ${s[1]}"></span>${s[2]}</span>
  </div>`;
}

function body(id){
  if(envItems===null)return '<div class="empty">正在体检 …</div>';
  const rows=itemsOf(id);
  if(!rows.length)return '<div class="empty">这一路没有体检项</div>';
  const out=[];
  ORDER.forEach(g=>{
    const sub=rows.filter(x=>x.it.group===g);
    if(sub.length)out.push(sub.map(x=>envRow(x.it,x.i)).join(''));
  });
  const known=new Set(ORDER);
  const odd=rows.filter(x=>!known.has(x.it.group));
  if(odd.length)out.push(odd.map(x=>envRow(x.it,x.i)).join(''));
  return out.join('');
}

/* 开关那一行：状态一句话 + 开关本身。关着的时候下面不放任何明细——
   这正是这一页要的效果：没开的东西不该拿「还差几项」来烦人。
   基础页不给开关：壳自己得活着，摆一颗点了只会回一句「不给关」的开关是骗人。 */
function switchRow(id){
  const m=meta(id), isOn=on(id);
  const t=todoOf(id);
  const note=!isOn?'已关闭 · 不体检、不提醒'
      :envItems===null?'体检中…'
      :(t.length?'还差 '+t.length+' 项'+(gbOf(t)?'（约 '+gbOf(t)+' GB）':''):'已就绪');
  const sw=id==='base'?ic('db','s')
    :`<div class="sw ${isOn?'on':''}" title="关掉这一路：不体检、功能页一并收起"
        onclick="MIC.env.set('${id}',${isOn?0:1})"></div>`;
  return `<div class="bar" style="border:0;padding:0 0 8px">
    ${sw}
    <b>${esc(m.title||m.label||id)}</b>
    <span class="mut fine">${esc(note)}</span><span class="grow"></span>${
      isOn?btn(id,t):''}</div>`;
}

function btn(id,t){
  const s=MIC.s.st;
  if(s.env_busy||(s.dl&&s.dl.busy))
    return '<button class="btn sm pri" disabled>'+(s.env_busy?'补全中…':'下载中…')+'</button>';
  if(envItems===null)return '<button class="btn sm gho" disabled>一键补齐</button>';
  if(!t.length)return '<button class="btn sm gho" disabled>已就绪</button>';
  return '<button class="btn sm pri" onclick="MIC.env.fixZone(\''+id+'\')">'+
    ic('down','s')+(id==='h3'?'下载 ':'一键补齐 ')+t.length+' 项</button>';
}

/* 千问那两块的归属：权重目录与下载器只服务千问，放在千问这一页而不是基础页 */
function qwenExtra(){
  const s=MIC.s.st;
  const list=mdl===null?'<div class="empty">正在扫描权重目录 …</div>'
    :(mdl.length?mdl.map(row).join(''):'<div class="empty">还没有千问模型 · 用下面的下载器拉一个</div>');
  const local=
    '<div class="bar" style="border:0;padding:0 0 6px"><span class="mut fine">'+esc(dir||'envs/qwen/models')+'</span>'+
    '<span class="grow"></span>'+
    '<button class="btn sm gho" onclick="MIC.models.refresh()">'+ic('refresh','s')+'重新扫描</button></div>'+list;
  const dl=
    C.field('仓库 ID','<input class="inp" id="dl-repo" value="Qwen/Qwen-Image-2.1-Turbo" placeholder="org/name">','HuggingFace 上的 org/name')+
    C.field('本地目录名','<input class="inp" id="dl-name" placeholder="例如 Qwen-Image-2.1-Turbo">','留空=用仓库名末段')+
    '<div class="btnrow"><button class="btn pri" onclick="MIC.models.start()" '+
      'title="自动选镜像、多线程分段、断点续传；开着 Motrix 时先交给它">'+
      ic('down','s')+'开始下载（断点续传）</button></div>';
  return C.duo(C.card('本机模型','db',local,{tight:true,tip:'千问的权重目录，换激活模型在这里切（Moss 与 H3 的权重在各自环境目录，由那一页管）'+
      (s.model_loaded?'；显存里已载入模型，切换后要先卸载再载入才生效':'')}),
      C.card('下载权重','down',dl),'eq');
}

function render(id){
  const isOn=on(id);
  const m=meta(id);
  const head=switchRow(id);
  if(!isOn)
    return head+`<div class="empty">这一路关着：不体检、不占显存，功能页也收起了。<br>
      <button class="btn sm pri" onclick="MIC.env.set('${id}',1)">${ic('power','s')}开启这一路</button></div>`;
  const extra=id==='qwen'?qwenExtra():'';
  const tip=m.desc?`<div class="mut fine" style="padding:2px 0 8px">${esc(m.desc)}</div>`:'';
  return head+tip+C.card('明细','db',body(id),{tight:true})+extra;
}

PAGES.forEach(p=>{
  MIC.registerPage(p.page,{
    title:p.name,icon:p.icon,
    sub(){
      if(!on(p.id))return '已关闭';
      if(envItems===null)return '体检中…';
      const n=todoOf(p.id).length;
      return n?'还差 '+n+' 项':'已就绪';
    },
    render(){
      return '<div class="pagebar"><span class="mut fine">体检于 '
          +(envAt?envAt.toLocaleTimeString('zh-CN',{hour12:false}):'…')+'</span><span class="grow"></span>'+
        '<button class="btn sm gho" onclick="MIC.env.check()">'+ic('refresh','s')+'重新体检</button></div>'+
        render(p.id);
    },
    mount(){
      if(p.id==='qwen'&&!mdl)MIC.models.refresh();
      if(!env)MIC.env.check();
    },
  });
});

/* ---------- 体检 / 开关 / 补齐 ---------- */
MIC.env={
  check(){
    MIC.api.envCheck().then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'体检失败');return;}
      envItems=r.items;env=r;envAt=new Date();
      MIC.env.lastItems=r.items;
      if(r.env_on)MIC.s.st.env_on=r.env_on;
      MIC.nav.applyMode();
      MIC.render();
    }).catch(()=>MIC.toast('体检失败'));
  },
  /* 开关走后端 env_set（它要顺手放显存、重跑体检），不能只当表单字段存：
     先落 cfg 让界面立刻变，再用后端回的这份对齐。 */
  set(id,want){
    MIC.api.envSet(id,!!want).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'开关没生效');return;}
      MIC.s.cfg.env_on=Object.assign({},MIC.s.cfg.env_on,r.env_on||{});
      MIC.s.st.env_on=Object.assign({},MIC.s.st.env_on,r.env_on||{});
      env=null;envItems=null;
      MIC.nav.applyMode();
      MIC.render();
      MIC.toast((want?'已开启 ':'已关闭 ')+((FALLBACK[id]||{}).label||id));
    }).catch(()=>MIC.toast('开关没生效'));
  },
  fixAt(i){
    const it=(envItems||[])[i];if(!it)return;
    MIC.env._go([it.key]);
  },
  fixZone(id){
    const keys=todoOf(id).map(x=>x.it.key);
    if(!keys.length){MIC.toast('这一路已经齐了');return;}
    MIC.env._go(keys);
  },
  fixAll(){
    /* 横幅也调这里：那时本地还没体检过、没缓存，
       补哪些项让后端现算（keys=null），别拿「没有要补的」把人挡回去 */
    MIC.env._go(env&&env.todo&&env.todo.length?env.todo:null);
  },
  _go(keys){
    MIC.api.envFix(keys).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'补全没起来');return;}
      if(!r.count){MIC.toast('没有需要补的');return;}
      MIC.s.st.env_busy=true;MIC.s.st.env_todo=r.count;
      MIC.s.st.env_steps=r.count;MIC.s.st.env_step=0;
      MIC.toast('补全已开始（'+r.count+' 项），进度看上方');
      MIC.render();
    }).catch(()=>MIC.toast('补全没起来'));
  },
};

function row(it,i){
  const ok=it.index&&it.shards>0;
  return `<div class="mrow">
    <div class="minfo"><b>${esc(it.name)}</b>
      <span class="mut fine">${it.gb} GB · ${it.shards} 个权重分片 · ${ok?'文件齐全':'缺 model_index.json 或分片，校验未过'}</span></div>
    <span class="grow"></span>
    ${it.active?'<span class="pill on"><span class="dot ok"></span>激活中</span>'
      :'<button class="btn sm" onclick="MIC.models.activate('+i+')">'+ic('power','s')+'设为激活</button>'}
    <button class="btn sm gho" onclick="MIC.models.openDir(${i})">${ic('folder','s')}目录</button>
  </div>`;
}

MIC.models={
  refresh(){
    MIC.api.modelsList().then(r=>{
      if(r&&r.ok){mdl=r.items;dir=r.dir;}
      MIC.render();
    }).catch(()=>{mdl=[];MIC.render();});
  },
  activate(i){
    const it=(mdl||[])[i];if(!it)return;
    MIC.api.modelsSetActive(it.name).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'切换失败');return;}
      if(r.cfg)MIC.form.applyCfg(r.cfg);
      MIC.toast('已设为激活：'+it.name);
      MIC.models.refresh();
    }).catch(()=>MIC.toast('切换失败'));
  },
  openDir(i){
    const it=(mdl||[])[i];if(!it||!dir)return;
    MIC.api.openPath(dir+'/'+it.name).catch(()=>{});
  },
  start(){
    const repo=(MIC.$('dl-repo')||{}).value||'';
    const name=(MIC.$('dl-name')||{}).value||'';
    if(!repo.trim()){MIC.toast('先填仓库 ID');return;}
    MIC.api.modelsDownload(repo.trim(),name.trim()).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'启动下载失败');return;}
      MIC.s.st.dl={busy:true,phase:'download',repo:repo.trim(),file:'',done:0,total:0,
                   speed:0,eta:0,files_done:0,files_total:0};
      MIC.toast('下载已开始，进度看上方');
      MIC.render();
    }).catch(()=>MIC.toast('启动下载失败'));
  },
};
})();
