/* core/theme.js —— 潮汐/花间 × 深色/浅色，含环境粒子与外观浮层 */
(function(){
const MIC=window.MIC=window.MIC||{};
const cfg=()=>MIC.s.cfg||{};

function apply(){
  const c=cfg();
  document.body.className=(c.theme||'tide')+' '+(c.mode||'dark')+(c.sidebar_min?' min':'');
  ambient();
}
function setTheme(t){cfg().theme=t;apply();MIC.api.save({theme:t}).catch(()=>{});}
function setMode(m){cfg().mode=m;apply();MIC.api.save({mode:m}).catch(()=>{});}

function ambient(){
  document.querySelectorAll('.bubble,.petal').forEach(e=>e.remove());
  const tide=(cfg().theme||'tide')==='tide';
  const n=tide?11:14;
  for(let i=0;i<n;i++){
    const el=document.createElement('span');
    el.className=tide?'bubble':'petal';
    const sz=tide?5+Math.random()*11:7+Math.random()*9;
    el.style.cssText='left:'+(Math.random()*104)+'vw;width:'+sz+'px;height:'+(tide?sz:sz*0.8)+
      'px;animation-duration:'+(16+Math.random()*18)+'s;animation-delay:'+(-Math.random()*30)+'s';
    document.body.appendChild(el);
  }
}

function pop(e){
  e.stopPropagation();
  const c=cfg();
  const t=[['tide','潮汐','海浪与深海，冷静取数'],['plum','花间','花枝与落瓣，柔和护眼']];
  let h=`<div class="ph">${MIC.ic('palette','s')}<b>外观</b></div><div class="themes">`;
  t.forEach(([k,name,desc])=>{
    h+=`<button class="tcard ${c.theme===k?'on':''}" onclick="MIC.theme.setTheme('${k}');MIC.closePop()">
      <div class="tn">${MIC.ic(k==='tide'?'wave':'flower')}${name}</div>
      <div class="ts">${desc}</div>
      <div class="sw2"><i style="background:${k==='tide'?'#57d8e6':'#e78fb3'}"></i>
      <i style="background:${k==='tide'?'#82e8d4':'#f3c17f'}"></i>
      <i style="background:${c.theme===k&&c.mode==='dark'?'#0b1a24':'#ffffff'};border:1px solid var(--line2)"></i></div>
    </button>`;
  });
  h+=`</div><div class="pfoot">
      <button class="btn sm ${c.mode==='dark'?'pri':'gho'}" onclick="MIC.theme.setMode('dark')">${MIC.ic('moon','s')}深色</button>
      <button class="btn sm ${c.mode==='light'?'pri':'gho'}" onclick="MIC.theme.setMode('light')">${MIC.ic('sun','s')}浅色</button>
      <span class="grow"></span><span class="mut fine">即时生效 · 写入配置</span></div>`;
  const p=MIC.$('pop');p.innerHTML=h;p.classList.remove('hide');
  MIC.place(e.target.closest('button'),p);
  MIC.closeMenu();
}

MIC.theme={apply,setTheme,setMode,pop,ambient};
})();
