/* pages/models.js —— 环境：按生图引擎分两个区，各一键补齐
   换电脑时 git 只带走代码，.venv/、models/、comfyui/ 都不进仓库；这一页就是「clone 之后点一下」。
   体检与补全都在后端（env_check / env_fix），这里只管发起、显示、刷新。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

let envItems=null, env=null, envAt=null, dir='', mdl=null;

const ST={ok:['on','ok','就绪'],miss:['','bad','没装'],part:['','bad','待补'],warn:['','','提醒']};
const G={PY:'运行环境',PKG:'依赖包',MODEL:'模型权重',MOSS:'Moss 环境',DIR:'目录'};

/* 分区归属：Moss 那套（comfy:/moss: 前缀，或清单里标了 group=Moss 环境的包，如 websocket-client）
   归 Moss；其余（运行环境/依赖包/千问权重/目录）归千问。
   两套环境物理隔离：千问用主 .venv+models/，Moss 用 comfyui/.venv+comfyui/models。 */
const isMoss=it=>/^(comfy:|moss:)/.test(String(it.key||''))||it.group===G.MOSS;
const ZONES=[
  {id:'qwen',icon:'flower',title:'千问环境',
   desc:'diffusers 直跑的老引擎。装主 .venv 的 torch/diffusers 依赖和 models/ 里的 Turbo 权重。',
   isMine:it=>!isMoss(it),
   order:[G.PY,G.PKG,G.MODEL,G.DIR],
   heads:{[G.PKG]:'依赖包',[G.MODEL]:'模型权重（约 30 GB）',[G.DIR]:'目录'},
   extra:'models'},
  {id:'moss',icon:'wave',title:'Moss 环境',
   desc:'内嵌 ComfyUI 的新引擎。comfyui/ 下自带独立 venv 与权重，和千问互不打扰；只想要一个模型就别下这块。',
   isMine:isMoss,
   order:[G.MOSS],heads:{},extra:''},
];

/* 控制台模式：仅千问 / 仅 Moss 时，环境页也只看这个引擎自己的分区，
   千问专属的本机模型与手动下载卡同样收走（Moss 的权重归它分区自己管）。 */
function zoneOn(z){
  const m=String((MIC.s.cfg||{}).console_mode||'both');
  if(m==='qwen')return z.id==='qwen';
  if(m==='moss')return z.id==='moss';
  return true;
}

function zoneItems(z){
  const out=[];
  (envItems||[]).forEach((it,i)=>{if(z.isMine(it))out.push({it:it,i:i});});
  return out;
}
function zoneTodo(z){return zoneItems(z).filter(x=>x.it.state==='miss'||x.it.state==='part');}
function zoneGb(list){
  let g=0;list.forEach(x=>{g+=Number(x.gb)||0;});
  return g?Math.round(g*10)/10:0;
}
function zoneKeys(z){return zoneTodo(z).map(x=>x.it.key);}

function envRow(it,i,head){
  const s=ST[it.state]||ST.warn;
  const fixable=(it.state==='miss'||it.state==='part')&&it.fix&&it.fix.kind!=='none';
  return `<div class="mrow">
    <div class="minfo"><b>${esc(it.label)}</b>
      <span class="mut fine">${esc(it.detail)}</span></div>
    <span class="grow"></span>
    ${fixable?'<button class="btn sm" onclick="MIC.env.fixAt('+i+')">'+ic('down','s')+'补这项</button>':''}
    <span class="pill ${s[0]}"><span class="dot ${s[1]}"></span>${s[2]}</span>
  </div>`;
}

function zoneBody(z){
  if(envItems===null)return '<div class="empty">正在体检 …</div>';
  const rows=zoneItems(z);
  if(!rows.length)return '<div class="empty">这个分区没有体检项</div>';
  const out=[];
  z.order.forEach(g=>{
    const sub=rows.filter(x=>x.it.group===g);
    if(!sub.length)return;
    if(z.heads[g])out.push('<div class="egroup">'+esc(z.heads[g])+'</div>');
    out.push(sub.map(x=>envRow(x.it,x.i)).join(''));
  });
  /* 落在分组表之外的项（换了分组名之类）也别丢，兜底追加 */
  const known=new Set(z.order);
  const odd=rows.filter(x=>!known.has(x.it.group));
  if(odd.length)out.push(odd.map(x=>envRow(x.it,x.i)).join(''));
  return out.join('');
}

function zoneNote(z){
  if(envItems===null)return '体检中…';
  const t=zoneTodo(z);
  if(!t.length)return '已就绪';
  const g=zoneGb(t);
  return '还差 '+t.length+' 项'+(g?'（约 '+g+' GB）':'');
}

function zoneBtn(z){
  const s=MIC.s.st;
  if(s.env_busy)return '<button class="btn sm pri" disabled>补全中…</button>';
  const t=zoneTodo(z);
  if(envItems===null)return '<button class="btn sm gho" disabled>一键补齐</button>';
  if(!t.length)return '<button class="btn sm gho" disabled>已就绪</button>';
  return '<button class="btn sm pri" onclick="MIC.env.fixZone(\''+z.id+'\')">'+
    ic('down','s')+'一键补齐 '+t.length+' 项</button>';
}

function zoneCard(z){
  /* 分区说明挂在卡片标题上（悬浮看）：这条线摆在明面上，两张分区卡各多一行 */
  return '<div class="bar" style="border:0;padding:0 0 6px"><span class="grow"></span>'+zoneBtn(z)+'</div>'+
    zoneBody(z);
}

/* 副标题报的是「两路各自差几项」——体检数一落地就跟着变，
   没数的时候不编，只说这一页是干什么的。 */
MIC.registerPage('models',{
  title:'环境',
  sub(){
    if(envItems===null)return '两个引擎各一套环境 · 缺哪补哪';
    const n=z=>zoneTodo(z).length;
    return '千问 '+(n(ZONES[0])?'差 '+n(ZONES[0])+' 项':'就绪')+
      ' · Moss '+(n(ZONES[1])?'差 '+n(ZONES[1])+' 项':'就绪');
  },
  icon:'db',
  render(){
    const s=MIC.s.st;
    /* 顶部一条工具条：体检时间 + 重新体检。补齐不在这儿再来一颗按钮——
       上面那条横幅的「一键补齐」和每张分区卡自己那颗已经够了。 */
    const bar='<div class="pagebar"><span class="mut fine">体检于 '
        +(envAt?envAt.toLocaleTimeString('zh-CN',{hour12:false}):'…')+'</span><span class="grow"></span>'+
      '<button class="btn sm gho" onclick="MIC.env.check()">'+ic('refresh','s')+'重新体检</button>'+
      '</div>';
    const zones=ZONES.filter(zoneOn);
    const cards=zones.map(z=>C.card(z.title,z.icon,zoneCard(z),
      {note:zoneNote(z),tip:z.desc}));

    const list=mdl===null?'<div class="empty">正在扫描 models/ …</div>'
      :(mdl.length?mdl.map(row).join(''):'<div class="empty">models/ 下还没有模型 · 用下面的下载器拉一个</div>');
    const local=
      '<div class="bar" style="border:0;padding:0 0 6px"><span class="mut fine">'+esc(dir||'models/')+'</span>'+
      '<span class="grow"></span>'+
      '<button class="btn sm gho" onclick="MIC.models.refresh()">'+ic('refresh','s')+'重新扫描</button></div>'+list;
    const dl=
      C.field('仓库 ID','<input class="inp" id="dl-repo" value="Qwen/Qwen-Image-2.1-Turbo" placeholder="org/name">','HuggingFace 上的 org/name')+
      C.field('本地目录名','<input class="inp" id="dl-name" placeholder="例如 Qwen-Image-2.1-Turbo">','留空=用仓库名末段')+
      '<div class="btnrow"><button class="btn pri" onclick="MIC.models.start()" '+
        'title="走 hf-mirror，中断自动重连；进度看「日志」页">'+
        ic('down','s')+'开始下载（断点续传）</button></div>';

    /* 两个引擎分区并排、本机模型与下载器并排：四张卡两行看完，不再一条长竖列。
       单引擎模式下只剩一张分区卡，千问专属的两张卡也一并收走。 */
    const engineRow=cards.length>1?C.duo(cards[0],cards[1],'eq'):cards[0];
    const qwenRow=zoneOn(ZONES[0])
      ?C.duo(C.card('本机模型','db',local,{tight:true,tip:'千问的权重目录，换激活模型在这里切（Moss 权重在 comfyui/models，由上面分区管）'+
          (s.model_loaded?'；显存里已载入模型，切换后要先卸载再载入才生效':'')}),
          C.card('下载权重','down',dl),'eq')
      :'';
    return bar+engineRow+qwenRow;
  },
  mount(){
    if(!mdl)MIC.models.refresh();
    if(!env)MIC.env.check();
  },
});

MIC.env={
  check(){
    MIC.api.envCheck().then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'体检失败');return;}
      envItems=r.items;env=r;envAt=new Date();
      MIC.env.lastItems=r.items;
      MIC.render();
    }).catch(()=>MIC.toast('体检失败'));
  },
  fixAt(i){
    const it=(envItems||[])[i];if(!it)return;
    MIC.env._go([it.key]);
  },
  fixZone(id){
    const z=ZONES.filter(x=>x.id===id)[0];if(!z)return;
    const keys=zoneKeys(z);
    if(!keys.length){MIC.toast('这个分区已经齐了');return;}
    MIC.env._go(keys);
  },
  fixAll(){
    /* 环境页横幅也调这里：那时本地还没体检过、没缓存，
       补哪些项让后端现算（keys=null），别拿「没有要补的」把人挡回去 */
    MIC.env._go(env&&env.todo&&env.todo.length?env.todo:null);
  },
  _go(keys){
    MIC.api.envFix(keys).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'补全没起来');return;}
      if(!r.count){MIC.toast('没有需要补的');return;}
      MIC.s.st.env_busy=true;MIC.s.st.env_todo=r.count;
      MIC.toast('补全已在后台开始（'+r.count+' 项），进度看日志');
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
      MIC.toast('下载已在后台开始，进度看日志');
      MIC.render();
    }).catch(()=>MIC.toast('启动下载失败'));
  },
};
})();
