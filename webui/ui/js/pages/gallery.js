/* pages/gallery.js —— 画廊：输出目录缩略网格 + 历史库参数（回填/收藏）
   参数来自 SQLite（store.py）：老图没记录就照常显示、按钮给提示。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

let busy=false, favOnly=false, view=[], err='';
let tcache={}, io=null;      // 缩略图缓存（文件路径 → data:）与滚动观察器
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
    <img data-g="${i}" src="${esc(tcache[it.file]||'')}" alt="" loading="lazy" onclick="MIC.gal.open(${i})">
    <div class="gi"><span>${esc(it.name)}</span></div>
    <div class="gf">${esc(it.t||'')} · ${esc(it.size||'')}　用时 ${it.sec!=null?esc(it.sec)+'s':'—'}</div>
    <button class="gstar ${it.fav?'on':''}" title="收藏" onclick="MIC.gal.fav(${i})">${ic('star','s')}</button>
    <button class="gfill" title="参数回填到原页" onclick="MIC.gal.backfill(${i})">${ic('wand','s')}</button>
    <button class="gdel" title="删除这张" onclick="MIC.gal.del(${i})">${ic('trash','s')}</button>
  </div>`;
}

/* 缩略图按需取：清单里不再内联 base64，滚到哪张才让后端解哪一张。
   取到的存进 tcache，整页重画时直接复用，不必再问一遍。 */
function hydrate(){
  const todo=[].slice.call(document.querySelectorAll('#view img[data-g]'))
              .filter(el=>!el.getAttribute('src')&&!el.dataset.want);
  if(!todo.length)return;
  if(!('IntersectionObserver' in window)){todo.forEach(getThumb);return;}
  /* 已经在视口附近的当场就取：观察器回调要等下一帧，帧排不上首屏就一片灰
     （无头截图、窗口刚显示还没滚过都撞得上），观察器只留给真在下面的那些 */
  const vh=window.innerHeight||document.documentElement.clientHeight||0;
  const rest=[];
  todo.forEach(el=>{
    const r=el.getBoundingClientRect();
    if(r.bottom>-400&&r.top<vh+400)getThumb(el);else rest.push(el);
  });
  if(!rest.length)return;
  if(io)io.disconnect();
  io=new IntersectionObserver(es=>{
    es.forEach(e=>{
      if(!e.isIntersecting)return;
      io.unobserve(e.target);
      getThumb(e.target);
    });
  },{rootMargin:'400px 0px'});
  rest.forEach(el=>io.observe(el));
}

function getThumb(el){
  const i=+el.dataset.g, it=at(i);
  if(!it)return;
  el.dataset.want='1';
  if(tcache[it.file]){el.src=tcache[it.file];return;}
  MIC.api.thumb(it.file,384).then(r=>{
    if(!r||!r.ok||!r.url)return;
    tcache[it.file]=r.url;
    // 等图这段时间里页面可能整块重画过，认现在 DOM 里的那张，别写回已废弃的节点
    const cur=document.querySelector('#view img[data-g="'+i+'"]');
    if(cur)cur.src=r.url;
  }).catch(()=>{});
}

MIC.registerPage('gallery',{
  title:'画廊',sub:()=>MIC.s.gal?(MIC.s.gal.length+' 张成图 · 收藏 / 回填 / 删除'):'输出目录的成图',icon:'image',
  render(){
    let items=MIC.s.gal;
    const scan=items===null;
    if(!scan&&favOnly)items=items.filter(x=>x.fav);
    view=scan?[]:items;
    const grid=scan
      ?`<div class="empty">正在扫描输出目录…</div>`
      :(items.length
        ?`<div class="ggrid">${items.map(cellHTML).join('')}</div>`
        :`<div class="empty">${esc(err)||(favOnly?'还没有收藏的图':'输出目录还没有图 · 去「生图」跑一张')}</div>`);
    const total=MIC.s.gal?MIC.s.gal.length:0;
    return C.card('成图','grid',
      `<div class="bar">
         <span class="mut fine">${scan?'扫描中…':'共 '+total+' 张'+(favOnly?' · 只看收藏':'')}</span>
         <span class="grow"></span>
         <button class="btn sm ${favOnly?'pri':'gho'}" onclick="MIC.gal.toggleFav()">${ic('star','s')}只看收藏</button>
         <button class="btn sm gho" onclick="MIC.gal.load(1)">${ic('refresh','s')}重新扫描</button>
         <button class="btn sm gho" onclick="MIC.gal.openDir()">${ic('folder','s')}打开目录</button>
         <button class="btn sm gho" onclick="MIC.gal.clear()">${ic('trash','s')}清空</button>
       </div>${grid}`,{tight:true});
  },
  mount(){if(MIC.s.gal==null)load();hydrate();},   // 空目录也是 []：用真值判断会把「扫过了、没图」当成没扫，每帧重扫
});

MIC.gal={
  load,
  invalidate(){MIC.s.gal=null;},
  toggleFav(){favOnly=!favOnly;MIC.render();},
  open(i){const it=at(i);if(it)MIC.api.openPath(it.file).catch(()=>{});},
  openDir(){MIC.gen.openDir();},
  fav(i){
    const it=at(i);if(!it)return;
    if(!it.mode){MIC.toast('这张没有参数记录，收藏不了（老图）');return;}
    const on=!it.fav;
    MIC.api.galleryFav(it.file,on).then(r=>{
      if(r&&r.ok){it.fav=on?1:0;MIC.render();}
    }).catch(()=>MIC.toast('收藏失败'));
  },
  /* 回填：mode → 配置块 + 目标页；重绘的蒙版画不回，只带指令。
     Moss 已并进「生图」页：参数写进 moss 块，页面跳过去；出图记录里存的是步数，按 8/25/50 倒回档位。
     切引擎会重占显存，这一步留给人自己点，别拿回填当借口偷偷拉起 ComfyUI。 */
  backfill(i){
    const it=at(i);
    if(!it||!it.mode){MIC.toast('这张没有参数记录，回填不了');return;}
    const map={gen:['gen','t2i'],rgba:['gen','t2i'],edit:['edit','edit'],
               inpaint:['inpaint','inpaint'],moss:['moss','t2i']};
    const m=map[it.mode];
    if(!m){MIC.toast('不认识的任务类型：'+it.mode);return;}
    if(MIC.nav.pageHidden&&MIC.nav.pageHidden(m[1])){
      MIC.toast('「'+(MIC.pages[m[1]]||{}).title+'」页被控制台模式收起了，切回「两者兼有」再回填');return;}
    const k=m[0],patch={};
    MIC.mset(patch,k+'.prompt',it.prompt||'');
    if(it.negative!=null)MIC.mset(patch,k+'.negative',it.negative);
    if(it.seed!=null)MIC.mset(patch,k+'.seed',it.seed);
    if(k==='moss'){
      if(it.size&&/^\d+x\d+$/.test(it.size))MIC.mset(patch,'moss.size',it.size);
      MIC.mset(patch,'moss.quality',it.steps>=50?'full':(it.steps>=25?'mid':'fast'));
    }else if(k==='gen'){
      MIC.mset(patch,'gen.mode',it.mode==='rgba'?'rgba':'gen');
      if(it.size&&/^\d+x\d+$/.test(it.size))MIC.mset(patch,'gen.size',it.size);
      if(it.steps)MIC.mset(patch,'gen.steps',String(it.steps));
    }else{
      if(it.steps)MIC.mset(patch,k+'.steps',String(it.steps));
      const mm=String(it.size||'').match(/(\d+)²/);
      if(mm)MIC.mset(patch,k+'.res',mm[1]);
    }
    MIC.api.save(patch).then(r=>{
      if(r&&r.cfg)MIC.form.applyCfg(r.cfg);
      MIC.nav.goto(m[1]);
      if(it.mode==='inpaint'){MIC.toast('指令已回填 · 请重新选图涂抹');return;}
      const where={gen:'生图',rgba:'生图（透明档）',edit:'编辑',moss:'生图（Moss 档）'}[it.mode];
      MIC.toast(it.mode==='moss'&&MIC.s.st.engine!=='moss'
        ?'参数已存好 · 在「生图」页把引擎切到 Moss 就能看到'
        :'参数已回填到「'+where+'」');
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
