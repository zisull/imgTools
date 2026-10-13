/* core/dom.js —— 通用小工具：取值 / 转义 / 图标 / 时间 / 轻提示 */
(function(){
const MIC=window.MIC=window.MIC||{};

MIC.$=id=>document.getElementById(id);
MIC.esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
MIC.ic=(n,c)=>`<svg class="ic ${c||''}"><use href="#i-${n}"/></svg>`;
MIC.uid=p=>p+'_'+Date.now().toString(36)+Math.random().toString(36).slice(2,5);
MIC.now=()=>new Date().toTimeString().slice(0,8);
MIC.n=v=>(Number(v)||0).toLocaleString();

/* 点路径取值：micGet(cfg,'rfq.pages') */
MIC.mget=(o,p)=>p.split('.').reduce((a,k)=>(a==null?a:a[k]),o);
MIC.mset=(o,p,v)=>{const ks=p.split('.');const last=ks.pop();
  let t=o;ks.forEach(k=>{if(typeof t[k]!=='object'||t[k]===null)t[k]={};t=t[k];});t[last]=v;};

let toastTimer=null;
MIC.toast=(msg,kind)=>{
  const el=MIC.$('toast');if(!el)return;
  el.className='toast '+(kind||'');
  el.textContent=msg;
  clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>el.classList.add('hide'),2600);
};

/* 浮层定位：贴着锚点元素，越界自动翻到上方 */
MIC.place=(anchor,el)=>{
  const r=anchor.getBoundingClientRect();
  el.style.left=Math.max(8,Math.min(r.left,innerWidth-el.offsetWidth-10))+'px';
  el.style.top=(r.bottom+6+el.offsetHeight>innerHeight?r.top-el.offsetHeight-6:r.bottom+6)+'px';
};
MIC.closeMenu=()=>MIC.$('menu').classList.add('hide');
MIC.closePop=()=>MIC.$('pop').classList.add('hide');
let menuAnchor=null;
MIC.openMenu=(anchor,h)=>{
  menuAnchor=anchor||menuAnchor;
  const m=MIC.$('menu');m.innerHTML=h;m.classList.remove('hide');MIC.place(menuAnchor,m);
  MIC.closePop();
};
document.addEventListener('mousedown',e=>{
  if(!e.target.closest('#menu'))MIC.closeMenu();
  if(!e.target.closest('#pop'))MIC.closePop();
});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){MIC.closeMenu();MIC.closePop();}
  if(e.key==='F2'&&MIC.nav.state.sel)MIC.nav.startRename(MIC.nav.state.sel);
});
})();
