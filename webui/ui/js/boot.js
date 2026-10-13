/* boot.js —— 启动装配：取配置 → 渲染导航与首屏 → 定时拉取后端状态
   拉取式（非推送）：刷新/卡顿都不会丢日志，游标只在前移时消费 */
(function(){
const MIC=window.MIC=window.MIC||{};
const POLL_MS=800;

function brand(t){
  const el=MIC.$('brandName');
  if(el)el.textContent=t||'Qwen 生图控制台';
  document.title=t||'Qwen 生图控制台';
}

/* 设置页的「应用」按钮 */
function rename(){
  const v=MIC.form.raw('appName');
  if(!v)return;
  MIC.api.setTitle(v).then(r=>{if(r&&r.title)brand(r.title);}).catch(()=>{});
}

/* 双击左上角就地改名：pywebview 不支持 window.prompt，只能用行内输入框 */
function editName(){
  const el=MIC.$('brandName');if(!el||el.dataset.editing)return;
  el.dataset.editing='1';
  const inp=document.createElement('input');
  inp.className='inp';
  inp.style.cssText='width:100%;max-width:150px;padding:2px 7px;font-size:12.5px';
  inp.value=el.textContent;
  el.style.display='none';
  el.parentNode.insertBefore(inp,el);
  inp.focus();inp.select();
  let done=false;
  const finish=ok=>{
    if(done)return;done=true;
    inp.remove();el.style.display='';delete el.dataset.editing;
    const v=inp.value.trim();
    if(ok&&v&&v!==el.textContent){
      MIC.api.setTitle(v).then(r=>{if(r&&r.title)brand(r.title);}).catch(()=>{});
    }else brand(MIC.s.cfg.app_title);
  };
  inp.addEventListener('blur',()=>finish(true));
  inp.addEventListener('keydown',e=>{
    if(e.key==='Enter')finish(true);
    if(e.key==='Escape')finish(false);
    e.stopPropagation();
  });
}

function applyBoot(b){
  MIC.s.cfg=b.cfg||{};
  MIC.s.version=b.version||'';
  /* 默认导航只在内存里给，避免写进用户配置文件 */
  MIC.s.cfg.default_nav=b.default_nav||[];
  MIC.mergeState(b.state);
  const vt=MIC.$('verTag');if(vt)vt.textContent='v'+(MIC.s.version||'-');
  brand(MIC.s.cfg.app_title);
  MIC.nav.state.layout=MIC.s.cfg.layout||'flat';
  MIC.theme.apply();
  MIC.nav.load(MIC.s.cfg.nav,MIC.s.cfg.open);
  MIC.nav.renderTree();
  MIC.render();
  MIC.s.pollTimer=setInterval(poll,POLL_MS);
}

let fails=0;
function poll(){
  if(MIC.s.polling)return;
  MIC.s.polling=true;
  MIC.api.poll(MIC.s.cursor).then(r=>{
    fails=0;
    /* 先并状态再收日志：日志要按「当时在跑哪个任务」打标签 */
    MIC.mergeState(r.state);
    MIC.pushLogs(r.logs);
    MIC.s.cursor=r.seq;
    MIC.view.tick();
    MIC.view.watchFinish();
  }).catch(()=>{
    if(++fails===5)MIC.toast('界面与后台的连接中断');
  }).then(()=>{MIC.s.polling=false;});
}

function init(){
  const br=MIC.$('brand');
  if(br)br.addEventListener('dblclick',editName);
  /* win.init 必须在桥接就绪之后：它靠 api.booted() 判定是不是真窗口，
     放在 ready() 之前跑，pywebview 还没注入 window.pywebview，拖动/缩放就永远绑不上。 */
  MIC.api.ready().then(()=>{MIC.win.init();return MIC.api.boot();}).then(applyBoot).catch(e=>{
    MIC.$('view').innerHTML=`<div class="phead"><div><div class="ptitle">未连接到后端</div>
      <div class="psub">${MIC.esc(e&&e.message?e.message:e)}</div></div></div>`;
  });
}

MIC.app={brand,rename,editName};

if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);
else init();
})();
