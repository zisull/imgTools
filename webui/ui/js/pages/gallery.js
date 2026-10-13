/* pages/gallery.js —— 画廊：输出目录缩略网格 + 历史库参数（回填/收藏）
   参数来自 SQLite（store.py）：老图没记录就照常显示、按钮给提示。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

let busy=false, favOnly=false, view=[], err='';
/* 单元格按索引引用：Windows 路径带反斜杠，不往 onclick 字符串里塞。
   索引必须落在「界面上这一份」而不是原始数组上——只看收藏时两者会错位。 */
function at(i){return view[i]||null;}
function load(force){
  if(busy)return Promise.resolve();
  if(force)MIC.s.gal=null;
  busy=true;err='';
  if(force)MIC.render();   // 先画出「正在扫描」占位
  return MIC.api.galleryList().then(r=>{
    if(!r||!r.ok)err='扫描失败：'+((r&&r.msg)||'后台没给清单');
    MIC.s.gal=(r&&r.ok&&r.items)||[];
    busy=false;
    MIC.render();
  }).catch(e=>{
    err='扫描失败：'+(e&&e.message||e);
    MIC.s.gal=[];          // 失败也要落一个空清单：留着 null 会让每次 render 都重扫一遍
    busy=false;MIC.render();
  });
}
function cellHTML(it,i){
  return `<div class="gcell" title="${esc(it.prompt||'没有参数记录')}">
    <img src="${esc(it.url||'')}" alt="" onclick="MIC.gal.open(${i})">
    <div class="gi"><span>${esc(it.name)}</span></div>
    <div class="gf">${esc(it.t||'')} · ${esc(it.size||'')}　用时 ${it.sec!=null?esc(it.sec)+'s':'—'}</div>
    <button class="gstar ${it.fav?'on':''}" title="收藏" onclick="MIC.gal.fav(${i})">${ic('star','s')}</button>
    <button class="gfill" title="参数回填到原页" onclick="MIC.gal.backfill(${i})">${ic('wand','s')}</button>
    <button class="gdel" title="删除这张" onclick="MIC.gal.del(${i})">${ic('trash','s')}</button>
  </div>`;
}

MIC.registerPage('gallery',{
  title:'画廊',sub:'输出目录里的全部成图 · 点 ✦ 收藏 · 点魔棒回填参数',icon:'image',
  render(){
    let items=MIC.s.gal;
    const scan=items===null;
    if(!scan&&favOnly)items=items.filter(x=>x.fav);
    view=scan?[]:items;
    const grid=scan
      ?`<div class="empty">正在扫描输出目录…</div>`
      :(items.length
        ?`<div class="ggrid">${items.map(cellHTML).join('')}</div>`
        :`<div class="empty">${esc(err)||(favOnly?'还没有收藏的图 · 点缩略图左上角 ✦ 收藏':'输出目录还没有图 · 去「文生图」跑一张')}</div>`);
    const total=MIC.s.gal?MIC.s.gal.length:0;
    return C.card('成图','grid',
      `<div class="bar">
         <span class="mut fine">${scan?'扫描中…':'共 '+total+' 张'+(favOnly?' · 只看收藏':'')}</span>
         <span class="grow"></span>
         <button class="btn sm ${favOnly?'pri':'gho'}" onclick="MIC.gal.toggleFav()">${ic('star','s')}只看收藏</button>
         <button class="btn sm gho" onclick="MIC.gal.load(1)">${ic('refresh','s')}重新扫描</button>
         <button class="btn sm gho" onclick="MIC.gal.openDir()">${ic('folder','s')}打开目录</button>
         <button class="btn sm gho" onclick="MIC.gal.clear()">${ic('trash','s')}清空</button>
       </div>${grid}`,{tight:true})+
      C.logcard('sys','系统日志');
  },
  mount(){if(MIC.s.gal==null)load();},   // 空目录也是 []：用真值判断会把「扫过了、没图」当成没扫，每帧重扫
});

MIC.gal={
  load,
  invalidate(){MIC.s.gal=null;},
  toggleFav(){favOnly=!favOnly;MIC.render();},
  open(i){const it=at(i);if(it)MIC.api.openPath(it.file).catch(()=>{});},
  openDir(){
    const d=(MIC.s.cfg.console||{}).output_dir||'';
    MIC.api.openPath(d).catch(()=>MIC.toast('还没配输出目录'));
  },
  fav(i){
    const it=at(i);if(!it)return;
    if(!it.mode){MIC.toast('这张没有参数记录，收藏不了（老图）');return;}
    const on=!it.fav;
    MIC.api.galleryFav(it.file,on).then(r=>{
      if(r&&r.ok){it.fav=on?1:0;MIC.render();}
    }).catch(()=>MIC.toast('收藏失败'));
  },
  /* 回填：mode → 目标页 + 配置块；局部编辑的蒙版画不回，只带指令 */
  backfill(i){
    const it=at(i);
    if(!it||!it.mode){MIC.toast('这张没有参数记录，回填不了');return;}
    const map={gen:['gen','t2i'],edit:['edit','edit'],inpaint:['inpaint','inpaint'],rgba:['rgba','rgba']};
    const m=map[it.mode];
    if(!m){MIC.toast('不认识的任务类型：'+it.mode);return;}
    const k=m[0],patch={};
    MIC.mset(patch,k+'.prompt',it.prompt||'');
    if(it.negative!=null)MIC.mset(patch,k+'.negative',it.negative);
    if(it.steps)MIC.mset(patch,k+'.steps',String(it.steps));
    if(it.seed!=null)MIC.mset(patch,k+'.seed',it.seed);
    if(k==='gen'||k==='rgba'){
      if(it.size&&/^\d+x\d+$/.test(it.size))MIC.mset(patch,k+'.size',it.size);
    }else{
      const mm=String(it.size||'').match(/(\d+)²/);
      if(mm)MIC.mset(patch,k+'.res',mm[1]);
    }
    MIC.api.save(patch).then(r=>{
      if(r&&r.cfg)MIC.form.applyCfg(r.cfg);
      MIC.nav.goto(m[1]);
      MIC.toast(it.mode==='inpaint'?'指令已回填 · 局部编辑请重新选图涂抹':'参数已回填到'+
        ({gen:'文生图',edit:'图像编辑',inpaint:'局部编辑',rgba:'透明素材'})[it.mode]);
    }).catch(()=>MIC.toast('回填失败'));
  },
  del(i){
    const it=at(i);if(!it)return;
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
