/* core/form.js —— 表单构件 + 双向绑定：控件带 data-k="rfq.pages"，改完自动写回配置 */
(function(){
const MIC=window.MIC=window.MIC||{};
const esc=MIC.esc, ic=MIC.ic;

/* ---------- 构件 ---------- */
function field(label,control,hint){
  return `<div class="f"><label>${label}</label><div class="c">${control}</div>${hint?`<div class="hint">${hint}</div>`:''}</div>`;
}
function card(title,iconName,body,opts){
  const o=opts||{};
  return `<section class="card ${o.cls||''}">
    <header class="card-h">${ic(iconName)}<h2>${title}</h2>
      ${o.note?`<span class="note">${o.note}</span>`:''}
      <span class="grow"></span>${o.actions||''}</header>
    <div class="card-b${o.tight?' tight':''}">${body}</div></section>`;
}
function foldcard(title,iconName,body,note){
  return `<section class="card"><div class="fold" style="border-top:0">
    <div class="fold-h closed" onclick="MIC.form.fold(this)">
      ${ic('chev')}${ic(iconName,'s')}<span>${title}</span><span class="hint">${note||''}</span></div>
    <div class="fold-b hide">${body}</div></div></section>`;
}
/* 日志卡：各页面都用，标题可换，右上角固定「复制 / 清空」
   （复制走剪贴板，清空只清界面这一路的缓冲，后端日志文件不动）
   extra 传页面自己的按钮（如概览的刷新统计），排在复制之前。 */
function logcard(keys,title,extra){
  return card(title||'运行日志','refresh',
    `<div class="log" data-role="log" data-keys="${keys||''}"></div>`,
    {tight:true,actions:(extra||'')+
      `<button class="btn sm gho" onclick="MIC.form.copyLog('${keys||''}')">${ic('copy','s')}复制</button>`+
      `<button class="btn sm gho" onclick="MIC.form.clearLog('${keys||''}')">${ic('trash','s')}清空</button>`});
}
/* 运行卡下半截：状态灯 + 进度这两行在补邮箱/转换/导出三页完全同构，只差最后一行统计，
   所以收成一个 helper；按钮行各页不一样，仍由调用方自己拼。 */
function strow(k,inner){return `<div class="strow"><span class="k">${k}</span>${inner}</div>`;}
function runstat(run,extra){
  return `<div class="status" style="margin-top:16px">${
    strow('任务状态',`<span class="dot ${run?'run':''}" data-role="dot"></span><span data-role="st"></span>`)+
    strow('进度',`<div class="prog"><i data-role="prog"></i></div><span class="mut fine" data-role="pgtext"></span>`)+
    (extra||'')}</div>`;
}
function txt(k,ph,cls){
  return `<input class="inp ${cls||''}" data-k="${k}" value="${esc(MIC.mget(MIC.s.cfg,k))}" placeholder="${esc(ph||'')}">`;
}
/* 多行输入（提示词这类）：data-k 绑定与 txt 同一套 */
function ta(k,rows,ph){
  return `<textarea class="inp" data-k="${k}" rows="${rows||3}" placeholder="${esc(ph||'')}">${esc(MIC.mget(MIC.s.cfg,k))}</textarea>`;
}
function num(k,unit){
  return `<div class="numw"><input class="inp w" data-k="${k}" data-t="num" value="${esc(MIC.mget(MIC.s.cfg,k))}">${unit?`<span class="unit">${unit}</span>`:''}</div>`;
}
function sel(k,list,ph){
  const v=MIC.mget(MIC.s.cfg,k);
  let h=`<select class="inp" data-k="${k}">`;
  if(ph!==undefined)h+=`<option value=""${!v?' selected':''}>${esc(ph)}</option>`;
  list.forEach(o=>{
    const name=o.name!=null?o.name:o, code=o.code!=null?o.code:o;
    h+=`<option value="${esc(code)}"${String(code)===String(v)?' selected':''}>${esc(name)}</option>`;
  });
  return h+'</select>';
}
function chk(k,label){
  return `<label class="chk ${MIC.mget(MIC.s.cfg,k)?'on':''}" data-k="${k}"><i>${ic('check')}</i>${label}</label>`;
}
function sw(k){
  return `<div class="sw ${MIC.mget(MIC.s.cfg,k)?'on':''}" data-k="${k}"></div>`;
}
function seg(k,items){
  const v=String(MIC.mget(MIC.s.cfg,k));
  return `<div class="seg" data-k="${k}">${items.map(([val,label])=>
    `<button class="${val===v?'on':''}" data-v="${esc(val)}">${label}</button>`).join('')}</div>`;
}
function pathrow(k,ph,pickKind){
  return `<div class="inrow dropz" data-into="${k}" data-drop="${pickKind||'file'}"
      title="可以直接把文件从资源管理器拖进来">${txt(k,ph,'path')}
    <button class="btn" onclick="MIC.form.pickInto('${k}','${pickKind}')">浏览</button></div>`;
}
/* 任务跑着的时候参数改不动（与桌面版禁用控件同义）：inert 挡键盘，dis 挡鼠标 */
function lock(run,inner){
  return `<div class="lockw${run?' dis':''}"${run?' inert':''}>${inner}</div>`;
}

/* ---------- 取值 / 写回 ---------- */
/* 后端保存后会回一份完整配置（换类别会改起始页码、抓取中会推进页码），
   前端必须换成这份，否则下一次提交会把旧值写回去。default_nav 只在内存，保留。 */
function applyCfg(c){
  if(!c)return;
  const dn=MIC.s.cfg&&MIC.s.cfg.default_nav;
  MIC.s.cfg=c;
  if(dn)MIC.s.cfg.default_nav=dn;
}
/* 把界面上的控件对齐到 MIC.s.cfg：正在输入的不打断 */
function syncFields(){
  document.querySelectorAll('#view [data-k]').forEach(el=>{
    const k=el.dataset.k;if(!k)return;
    const v=MIC.mget(MIC.s.cfg,k);
    if(el.classList.contains('chk')||el.classList.contains('sw')){el.classList.toggle('on',!!v);return;}
    if(el.classList.contains('seg')){
      el.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.v===String(v)));return;
    }
    if(el===document.activeElement)return;
    const nv=v==null?'':String(v);
    if(el.value!==nv)el.value=nv;
  });
}
function saved(patch){
  MIC.api.save(patch).then(r=>{
    if(!r||!r.cfg)return;
    applyCfg(r.cfg);
    /* 后端会改起始页码/剩余页数（换类别回填、抓取中推进），控件要跟着对齐 */
    syncFields();
  }).catch(()=>{});
}
function valOf(el){
  if(el.classList.contains('chk')||el.classList.contains('sw'))return el.classList.contains('on');
  if(el.classList.contains('seg')){const b=el.querySelector('button.on');return b?b.dataset.v:'';}
  const raw=el.value;
  if(el.dataset.t==='num'){const n=parseFloat(raw);return isNaN(n)?0:n;}
  return raw;
}
function read(){
  const patch={};
  document.querySelectorAll('#view [data-k]').forEach(el=>{
    const k=el.dataset.k;if(!k)return;
    MIC.mset(patch,k,valOf(el));
  });
  return patch;
}
function commitPath(k,v){
  MIC.mset(MIC.s.cfg,k,v);
  const patch={};MIC.mset(patch,k,v);
  saved(patch);
}
/* 一次改多个键（品类下拉要同时写 cat/excat/cat_name），只落盘一次 */
function commitMany(pairs){
  const patch={};
  Object.keys(pairs).forEach(k=>{MIC.mset(MIC.s.cfg,k,pairs[k]);MIC.mset(patch,k,pairs[k]);});
  saved(patch);
}
function commit(){
  const patch=read();
  if(!Object.keys(patch).length)return patch;
  merge(patch);
  saved(patch);
  return patch;
}
function merge(patch){
  Object.keys(patch).forEach(k=>{
    const v=patch[k];
    if(v&&typeof v==='object'&&!Array.isArray(v)){
      if(typeof MIC.s.cfg[k]!=='object'||MIC.s.cfg[k]===null)MIC.s.cfg[k]={};
      mergeInto(MIC.s.cfg[k],v);
    }else MIC.s.cfg[k]=v;
  });
}
function mergeInto(t,s){
  Object.keys(s).forEach(k=>{
    if(s[k]&&typeof s[k]==='object'&&!Array.isArray(s[k])){
      if(typeof t[k]!=='object'||t[k]===null)t[k]={};mergeInto(t[k],s[k]);
    }else t[k]=s[k];
  });
}
function pickInto(k,kind){
  MIC.api.pick(kind).then(p=>{
    if(!p)return;
    MIC.mset(MIC.s.cfg,k,p);
    const el=document.querySelector(`#view [data-k="${k}"]`);if(el)el.value=p;
    commitPath(k,p);
  }).catch(()=>{});
}
/* 日志卡右上角两个按钮：keys 就是卡上 data-keys 那串（空 = 全部这一路）
   清空只清界面这份环形缓冲，后端日志文件照旧写。 */
function logKeys(keys){return keys?String(keys).split(','):null;}
function copyLog(keys){
  const t=MIC.view.logText(logKeys(keys));
  if(!t){MIC.toast('这一路还没有日志');return;}
  MIC.view.copy(t,'已复制全部日志');
}
function clearLog(keys){MIC.clearLogs(logKeys(keys));MIC.render();}

/* 事件委托：文本/下拉 change 即存；勾选/开关/分段 click 即存 */
document.addEventListener('change',e=>{
  const el=e.target.closest?e.target.closest('#view [data-k]'):null;
  if(!el||el.classList.contains('chk')||el.classList.contains('sw')||el.classList.contains('seg'))return;
  commitPath(el.dataset.k,valOf(el));
});
document.addEventListener('click',e=>{
  const btn=e.target.closest?e.target.closest('.seg[data-k] button'):null;
  if(btn){
    const box=btn.parentElement;
    box.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b===btn));
    commitPath(box.dataset.k,btn.dataset.v);
    return;
  }
  const t=e.target.closest?e.target.closest('#view .chk[data-k],#view .sw[data-k]'):null;
  if(t){t.classList.toggle('on');commitPath(t.dataset.k,t.classList.contains('on'));}
});

/* ---------- 拖文件进来填路径 ----------
   只有 .dropz（文件路径格）接住，其余位置一律 preventDefault：
   浏览器默认「拖文件=打开文件」会把整页换掉，跑一半的状态当场就没。 */
function dropCands(dt){
  const out=[];
  const fl=dt.files||[];
  for(let i=0;i<fl.length;i++){
    if(fl[i].path)out.push(fl[i].path);       // 有的内核给得出完整路径
    if(fl[i].name)out.push(fl[i].name);       // 只给得出文件名时交给后端去找
  }
  ['text/uri-list','DownloadURL','text/plain'].forEach(t=>{
    let v='';try{v=dt.getData(t);}catch(e){}
    if(v)v.split(/\r?\n/).forEach(s=>out.push(s));
  });
  return out.map(s=>String(s||'').trim()).filter(Boolean).slice(0,8);
}
function zones(keep){
  document.querySelectorAll('.dropz.over').forEach(x=>{if(x!==keep)x.classList.remove('over');});
}
document.addEventListener('dragover',e=>{
  if(!e.dataTransfer)return;
  e.preventDefault();
  const z=e.target.closest?e.target.closest('.dropz'):null;
  zones(z);
  if(z)z.classList.add('over');
});
document.addEventListener('dragend',()=>zones());
document.addEventListener('drop',e=>{
  if(!e.dataTransfer)return;
  e.preventDefault();
  const z=e.target.closest?e.target.closest('.dropz'):null;
  zones();
  if(!z)return;
  const cands=dropCands(e.dataTransfer);
  if(!cands.length)return;
  const k=z.dataset.into;
  MIC.api.dropPath(cands,z.dataset.drop||'file').then(r=>{
    if(!r||!r.ok){MIC.toast((r&&r.msg)||'没能识别这个文件');return;}
    const el=document.querySelector(`#view [data-k="${k}"]`);if(el)el.value=r.path;
    commitPath(k,r.path);
    MIC.toast('已载入 '+r.path);
  }).catch(err=>MIC.toast('识别失败：'+(err&&err.message||err)));
});

MIC.form={field,card,foldcard,logcard,runstat,strow,txt,ta,num,sel,chk,sw,seg,pathrow,lock,read,commit,commitPath,commitMany,pickInto,
  copyLog,clearLog,applyCfg,dropCands,
  fold(h){h.classList.toggle('closed');h.nextElementSibling.classList.toggle('hide');},
  /* 页面里非 data-k 的临时控件：取值不写配置 */
  raw(id){const el=MIC.$(id);return el?(el.value!=null?el.value.trim():el.textContent):'';},
};
})();
