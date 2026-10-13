/* pages/gallery.js —— 画廊：输出目录缩略网格，点开=系统看图，就地删除 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

let busy=false;
function load(force){
  if(busy)return Promise.resolve();
  if(force)MIC.s.gal=null;
  busy=true;
  if(force)MIC.render();   // 先画出「正在扫描」占位
  return MIC.api.galleryList().then(r=>{
    MIC.s.gal=(r&&r.ok&&r.items)||[];
    busy=false;
    MIC.render();
  }).catch(()=>{busy=false;MIC.render();});
}
/* 单元格按索引引用：Windows 路径带反斜杠，不往 onclick 字符串里塞 */
function cellHTML(it,i){
  return `<div class="gcell" title="${esc(it.prompt||'')}">
    <img src="${esc(it.url||'')}" alt="" onclick="MIC.gal.open(${i})">
    <div class="gi"><span>${esc(it.name)}</span></div>
    <div class="gf">${esc(it.t||'')} · ${esc(it.size||'')}${it.seed!=null&&it.seed!==''?' · 种子 '+esc(it.seed):''}</div>
    <button class="gdel" title="删除这张" onclick="MIC.gal.del(${i})">${ic('trash','s')}</button>
  </div>`;
}

MIC.registerPage('gallery',{
  title:'画廊',sub:'输出目录里的全部成图',icon:'image',
  render(){
    const items=MIC.s.gal;
    const grid=items===null
      ?`<div class="empty">正在扫描输出目录…</div>`
      :(items.length
        ?`<div class="ggrid">${items.map(cellHTML).join('')}</div>`
        :`<div class="empty">输出目录还没有图 · 去「文生图」跑一张</div>`);
    return C.card('成图','grid',
      `<div class="bar">
         <span class="mut fine">${items&&items.length?'共 '+items.length+' 张':'尚无成图'}</span>
         <span class="grow"></span>
         <button class="btn sm gho" onclick="MIC.gal.load(1)">${ic('refresh','s')}重新扫描</button>
         <button class="btn sm gho" onclick="MIC.gal.openDir()">${ic('folder','s')}打开目录</button>
         <button class="btn sm gho" onclick="MIC.gal.clear()">${ic('trash','s')}清空</button>
       </div>${grid}`,{tight:true})+
      C.logcard('sys','系统日志');
  },
  mount(){if(!MIC.s.gal)load();},
});

MIC.gal={
  load,
  invalidate(){MIC.s.gal=null;},
  open(i){const it=(MIC.s.gal||[])[i];if(it)MIC.api.openPath(it.file).catch(()=>{});},
  openDir(){
    const d=(MIC.s.cfg.console||{}).output_dir||'';
    MIC.api.openPath(d).catch(()=>MIC.toast('还没配输出目录'));
  },
  del(i){
    const it=(MIC.s.gal||[])[i];if(!it)return;
    MIC.api.galleryDelete(it.file).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'删除失败');return;}
      MIC.s.gal=MIC.s.gal.filter(x=>x.file!==it.file);
      MIC.render();
    }).catch(()=>MIC.toast('删除失败'));
  },
  clear(){
    if(!confirm('清空输出目录里的全部成图？这一步不进回收站。'))return;
    MIC.api.galleryClear().then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'清空失败');return;}
      MIC.s.gal=[];MIC.render();
    }).catch(()=>MIC.toast('清空失败'));
  },
};
})();
