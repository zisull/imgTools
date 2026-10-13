/* core/nav.js —— 导航树：标签页=功能页，分组可多级嵌套；平铺/分组两种形态
   结构变更（改名/新建分组/移动/解散）即时写回后端 cfg.nav。
   不提供新建标签页、删除与副本：标签页就是代码注册的那几功能页，
   空标签页点进去没内容，删了又找不到回来的路——排乱了用「恢复默认导航」。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const esc=MIC.esc, ic=MIC.ic;

const S={layout:'flat',min:false,sel:null,open:{}};
let TREE=[];

/* ---------- 读写 ---------- */
function load(tree,open){
  TREE=Array.isArray(tree)&&tree.length?JSON.parse(JSON.stringify(tree)):[];
  if(open)S.open=Object.assign({},open);
  S.sel=findId(S.sel)||findId(MIC.s.cfg.last_tab)||firstTab()||(TREE[0]&&TREE[0].id);
}
function save(){MIC.api.save({nav:TREE,open:S.open}).catch(()=>{});}
function walk(nodes,fn,parent,depth){
  (nodes||TREE).forEach((n,i)=>{fn(n,parent,depth||0,i);if(n.children)walk(n.children,fn,n,(depth||0)+1);});
}
function find(id){let hit=null;walk(TREE,(n,p,d,i)=>{if(n.id===id)hit={node:n,parent:p,arr:p?p.children:TREE,idx:i,depth:d};});return hit;}
function findId(id){return id&&find(id)?id:null;}
function pathOf(id){const parts=[];let f=find(id);while(f){parts.unshift(f.node.name);f=f.parent?find(f.parent.id):null;}return parts;}
function allTabs(){const r=[];walk(TREE,n=>{if(n.type==='tab')r.push(n);});return r;}
function allGroups(){const r=[];walk(TREE,n=>{if(n.type==='group')r.push(n);});return r;}
function firstTab(){const t=allTabs();return t.length?t[0].id:null;}
function isDesc(grp,id){let f=false;if(grp.children)walk(grp.children,n=>{if(n.id===id)f=true;});return f;}

/* ---------- 渲染 ---------- */
function renderTree(){
  const box=MIC.$('tree');if(!box)return;
  box.innerHTML=S.layout==='flat'
    ? allTabs().map(n=>tabHTML(n)).join('')
    : TREE.map(n=>nodeHTML(n)).join('');
  MIC.$('btnFlat').classList.toggle('on',S.layout==='flat');
  MIC.$('btnTree').classList.toggle('on',S.layout==='tree');
}
function nodeHTML(n){return n.type==='group'?grpHTML(n):tabHTML(n);}
function grpHTML(n){
  const closed=!S.open[n.id];
  const kids=n.children||[];
  return `<div class="node grp ${closed?'closed':''}" data-id="${n.id}" data-type="group" data-open="${closed?0:1}" draggable="true"
      onclick="MIC.nav.click('${n.id}')" ondblclick="MIC.nav.startRename('${n.id}')">
    <span class="tw" onclick="MIC.nav.toggleOpen('${n.id}',event)">${ic('chev')}</span>
    ${ic(n.icon||'folder','ni')}
    <span class="nm">${esc(n.name)}</span>
    <span class="path">${kids.length||''}</span>
    <span class="more" onclick="MIC.nav.nodeMenu(event,'${n.id}')">${ic('dots')}</span>
  </div>${closed?'':`<div class="kids">${kids.map(c=>nodeHTML(c)).join('')}</div>`}
    ${kids.length===0?`<div class="emptygrp" data-id="${n.id}" data-type="group">空分组 · 拖标签页进来</div>`:''}`;
}
function tabHTML(n){
  const path=S.layout==='flat'?pathOf(n.id).slice(0,-1).join(' / '):'';
  return `<div class="node tab ${S.sel===n.id?'sel':''}" data-id="${n.id}" data-type="tab" draggable="true"
      onclick="MIC.nav.click('${n.id}')" ondblclick="MIC.nav.startRename('${n.id}')">
    ${ic(n.icon||'tool','ni')}
    <span class="nm">${esc(n.name)}</span>
    ${path?`<span class="path" title="${esc(path)}">${esc(path)}</span>`:''}
    <span class="more" onclick="MIC.nav.nodeMenu(event,'${n.id}')">${ic('dots')}</span>
  </div>`;
}

/* ---------- 交互 ---------- */
function toggleOpen(id,e){if(e)e.stopPropagation();S.open[id]=!S.open[id];renderTree();save();}
function click(id){
  const f=find(id);if(!f)return;
  if(f.node.type!=='tab'){toggleOpen(id);return;}
  S.sel=id;MIC.s.cfg.last_tab=id;
  renderTree();MIC.render();
  MIC.api.save({last_tab:id}).catch(()=>{});
}
function setLayout(l){
  S.layout=l;renderTree();
  MIC.s.cfg.layout=l;MIC.api.save({layout:l}).catch(()=>{});
}
function toggleMin(){S.min=!S.min;document.body.classList.toggle('min',S.min);
  MIC.s.cfg.sidebar_min=S.min;MIC.api.save({sidebar_min:S.min}).catch(()=>{});}

/* 就地重命名（不弹窗） */
function startRename(id){
  renderTree();
  const node=document.querySelector(`.node[data-id="${id}"]`);if(!node)return;
  const nm=node.querySelector('.nm');if(!nm)return;
  const f=find(id);if(!f)return;
  const input=document.createElement('input');
  input.className='rename';input.value=f.node.name;
  nm.replaceWith(input);input.focus();input.select();
  let done=false;
  const commit=ok=>{
    if(done)return;done=true;
    if(ok){const v=input.value.trim();if(v)f.node.name=v;}
    renderTree();save();MIC.render();
  };
  input.addEventListener('blur',()=>commit(true));
  input.addEventListener('keydown',e=>{
    if(e.key==='Enter')commit(true);
    if(e.key==='Escape')commit(false);
    e.stopPropagation();
  });
  input.addEventListener('click',e=>e.stopPropagation());
}

/* ---------- 增删 / 移动 / 复制 ---------- */
/* 不提供「新建标签页」：标签页只是功能页的入口，功能页由代码注册（ui/js/pages/），
   界面里新建出来的只能是一张空白页——既没内容可显示，又因为不给删除而清不掉。
   分组是真的有用（把标签页归拢），所以这里只留建分组。 */
function newGroup(){
  const target=pickParent();
  const n={id:MIC.uid('g'),type:'group',name:'新分组',icon:'folder',children:[]};
  if(target){target.children.push(n);S.open[target.id]=1;}else TREE.push(n);
  renderTree();save();setTimeout(()=>startRename(n.id),30);
}
function pickParent(){
  const f=find(S.sel);
  if(f&&f.node.type==='group')return f.node;
  if(f&&f.parent)return f.parent;
  return null;
}
function dissolve(id){
  const f=find(id);if(!f||f.node.type!=='group')return;
  const kids=f.node.children||[];
  if(!kids.length){f.arr.splice(f.idx,1);renderTree();save();return;}
  if(!confirm(`解散分组「${f.node.name}」？子项会上提一层，标签页不会丢失。`))return;
  f.arr.splice(f.idx,1,...kids);
  renderTree();save();MIC.render();
}
function dissolveAll(){
  if(!confirm('解散所有分组？所有标签页会平铺到顶层，功能页本身不会丢失。'))return;
  TREE=allTabs().map(n=>({id:n.id,type:'tab',name:n.name,icon:n.icon,page:n.page}));
  S.open={};renderTree();save();MIC.render();
}
function resetNav(){
  if(!confirm('恢复默认导航结构？自定义标签页与分组会被替换。'))return;
  TREE=JSON.parse(JSON.stringify(MIC.s.cfg.default_nav||[]));
  S.open={};S.sel=firstTab();
  renderTree();save();MIC.render();
}
function moveTo(id,groupId){
  const f=find(id);if(!f)return;
  if(f.node.type==='group'&&isDesc(f.node,groupId))return;
  f.arr.splice(f.idx,1);
  if(groupId==='__top__')TREE.push(f.node);
  else{const g=find(groupId);if(!g)return;g.node.children.push(f.node);S.open[groupId]=1;}
  renderTree();save();
}
function moveBefore(id,targetId,after){
  const f=find(id);const t=find(targetId);if(!f||!t)return;
  if(f.node.type==='group'&&isDesc(f.node,targetId))return;
  f.arr.splice(f.idx,1);
  const t2=find(targetId);if(!t2)return;
  t2.arr.splice(t2.idx+(after?1:0),0,f.node);
  renderTree();save();
}
function setOpenAll(v){S.open={};walk(TREE,n=>{if(n.type==='group')S.open[n.id]=v;});renderTree();save();}

/* ---------- 绑定功能页 ---------- */
function bindPage(id){
  const f=find(id);if(!f)return;
  MIC.closeMenu();
  const keys=Object.keys(MIC.pages).filter(k=>k!=='__blank__');
  const p=MIC.$('pop');
  p.innerHTML=`<div class="ph">${ic('link')}<b>绑定功能页</b><span class="grow"></span>
      <span class="mut fine">${esc(f.node.name)}</span></div>
    <div class="plist">${keys.map(k=>`<div class="pitem" onclick="MIC.nav.doBind('${id}','${k}')">
      ${ic(MIC.pages[k].icon||'tool','ni')}<span>${esc(MIC.pages[k].title)}</span><span class="grow"></span>
      <span class="mut fine">${k===f.node.page?'当前':esc(k)}</span></div>`).join('')}</div>
    <div class="pfoot"><span class="mut fine">新增功能：加一个页面模块 + 注册键名，导航不用改</span></div>`;
  p.classList.remove('hide');
  MIC.place(document.querySelector(`.node[data-id="${id}"]`)||MIC.$('view'),p);
}
function doBind(id,key){const f=find(id);if(f){f.node.page=key;renderTree();save();MIC.render();}MIC.closePop();}

/* ---------- 菜单 ---------- */
function nodeMenu(e,id){
  e.stopPropagation();e.preventDefault();
  const f=find(id);if(!f)return;
  const isGrp=f.node.type==='group';
  let h=`<div class="mh">${esc(pathOf(id).join(' / '))}</div>`;
  h+=`<button onclick="MIC.nav.startRename('${id}');MIC.closeMenu()">${ic('cog','s')}重命名<kbd>F2</kbd></button>`;
  if(isGrp){
    h+=`<button onclick="MIC.nav.mAddGrp('${id}')">${ic('folder','s')}在此新建子分组</button>`;
  }else{
    h+=`<button onclick="MIC.nav.bindPage('${id}');MIC.closeMenu()">${ic('link','s')}绑定功能页</button>`;
  }
  h+=`<div class="sep"></div>`;
  h+=`<button onclick="MIC.nav.movePop(event,'${id}')">${ic('move','s')}移动到…</button>`;
  if(f.parent)h+=`<button onclick="MIC.nav.moveTo('${id}','__top__');MIC.closeMenu()">${ic('expand','s')}移到顶层</button>`;
  /* 这里不给「删除」和「创建副本」：标签页就是那几功能页，删了/复制了反而找不到绑定的页；
     排乱了用「恢复默认导航」一键回去。空分组解散时直接消失。 */
  if(isGrp){
    h+=`<div class="sep"></div>`;
    h+=`<button class="dgr" onclick="MIC.nav.dissolve('${id}');MIC.closeMenu()">${ic('ungroup','s')}解散分组（子项上提）</button>`;
  }
  MIC.openMenu(e.target.closest('.more'),h);
}
function mAddGrp(id){
  MIC.closeMenu();
  const g=find(id).node;const n={id:MIC.uid('g'),type:'group',name:'新分组',icon:'folder',children:[]};
  g.children.push(n);S.open[g.id]=1;renderTree();save();setTimeout(()=>startRename(n.id),30);
}
function movePop(e,id){
  const f=find(id);if(!f)return;
  let h=`<div class="ph">${ic('move','s')}<b>移动到…</b></div><div class="plist">`;
  h+=`<div class="pitem" onclick="MIC.nav.moveTo('${id}','__top__');MIC.closeMenu()">▲<span>顶层</span></div>`;
  allGroups().forEach(g=>{
    if(f.node.type==='group'&&(g.id===id||isDesc(f.node,g.id)))return;
    h+=`<div class="pitem" onclick="MIC.nav.moveTo('${id}','${g.id}');MIC.closeMenu()">${ic(g.icon||'folder','ni')}<span>${esc(pathOf(g.id).join(' / '))}</span></div>`;
  });
  h+=`</div><div class="pfoot"><span class="mut fine">也可以直接把标签页拖进分组</span></div>`;
  MIC.openMenu(e.target.closest('.more'),h);
}
function menu(e){
  e.stopPropagation();
  let h=`<div class="mh">导航选项</div>`;
  h+=`<button onclick="MIC.nav.setOpenAll(1);MIC.closeMenu()">${ic('expand','s')}全部展开</button>`;
  h+=`<button onclick="MIC.nav.setOpenAll(0);MIC.closeMenu()">${ic('collapse','s')}全部折叠</button>`;
  h+=`<div class="sep"></div>`;
  h+=`<button onclick="MIC.nav.setLayout('flat');MIC.closeMenu()">${ic('rows','s')}平铺（临时解散分组）${S.layout==='flat'?' ✓':''}</button>`;
  h+=`<button onclick="MIC.nav.setLayout('tree');MIC.closeMenu()">${ic('tree','s')}分组树${S.layout==='tree'?' ✓':''}</button>`;
  h+=`<button class="dgr" onclick="MIC.nav.dissolveAll();MIC.closeMenu()">${ic('ungroup','s')}解散所有分组（写入结构）</button>`;
  h+=`<div class="sep"></div>`;
  h+=`<button onclick="MIC.nav.newGroup();MIC.closeMenu()">${ic('folder','s')}新建分组</button>`;
  h+=`<button onclick="MIC.nav.resetNav();MIC.closeMenu()">${ic('refresh','s')}恢复默认导航</button>`;
  MIC.openMenu(MIC.$('navOpt'),h);
}

/* ---------- 拖拽（跨层级移动） ---------- */
let dragId=null,hoverTimer=null;
function clearMarks(){
  document.querySelectorAll('.node').forEach(x=>x.classList.remove('drop-before','drop-after','drop-in'));
  document.querySelectorAll('.emptygrp').forEach(x=>x.classList.remove('drop-in'));
}
document.addEventListener('dragstart',e=>{
  const n=e.target.closest?e.target.closest('.node'):null;if(!n)return;
  dragId=n.dataset.id;n.classList.add('dragging');
  e.dataTransfer.effectAllowed='move';
  try{e.dataTransfer.setData('text/plain',dragId);}catch(err){}
});
document.addEventListener('dragend',()=>{dragId=null;clearTimeout(hoverTimer);renderTree();});
document.addEventListener('dragover',e=>{
  if(!dragId)return;
  const hit=e.target.closest?e.target.closest('.node,.emptygrp'):null;
  if(!hit)return;
  e.preventDefault();
  clearMarks();
  const isNode=hit.classList.contains('node');
  if(isNode&&hit.dataset.id===dragId)return;
  const r=hit.getBoundingClientRect();const p=(e.clientY-r.top)/r.height;
  const canContain=!isNode||hit.dataset.type==='group';
  if(canContain&&p>0.28&&p<0.72){
    hit.classList.add('drop-in');
    if(isNode&&hit.dataset.open==='0'){
      if(hoverTimer)return;
      hoverTimer=setTimeout(()=>{
        hoverTimer=null;
        if(dragId&&document.contains(hit)){S.open[hit.dataset.id]=1;renderTree();}
      },650);
    }
  }else if(isNode)hit.classList.add(p<0.5?'drop-before':'drop-after');
});
document.addEventListener('drop',e=>{
  if(!dragId)return;
  const hit=e.target.closest?e.target.closest('.node,.emptygrp'):null;
  if(!hit)return;
  e.preventDefault();
  clearTimeout(hoverTimer);hoverTimer=null;
  const id=hit.dataset.id;
  const f=find(dragId);
  if(!f){dragId=null;return;}
  const isIn=hit.classList.contains('drop-in')||hit.classList.contains('emptygrp');
  if(f.node.type==='group'&&isDesc(f.node,id)){dragId=null;renderTree();return;}
  if(isIn)moveTo(dragId,id);
  else{
    const r=hit.getBoundingClientRect();
    moveBefore(dragId,id,(e.clientY-r.top)/r.height>=0.5);
  }
  dragId=null;
});

MIC.nav={
  state:S,load,save,walk,find,pathOf,allTabs,allGroups,renderTree,
  toggleOpen,click,setLayout,toggleMin,startRename,
  newGroup,dissolve,dissolveAll,resetNav,moveTo,moveBefore,setOpenAll,
  bindPage,doBind,nodeMenu,mAddGrp,movePop,menu,
  pageOf(){const f=find(S.sel);return (f&&f.node.page)||'__blank__';},
  tabIdFor(page){const t=allTabs().filter(n=>n.page===page);return t.length?t[0].id:null;},
  goto(page){const id=this.tabIdFor(page);if(id)this.click(id);},
};
})();
