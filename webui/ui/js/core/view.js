/* core/view.js —— 运行态显示：顶栏药丸 / 状态行 / 进度 / 显存条 / 日志框
   页面只写 data-role 占位，轮询回来后由 tick() 统一刷新 */
(function(){
const MIC=window.MIC=window.MIC||{};
const esc=MIC.esc, ic=MIC.ic;

const RE_ER=/❌|⚠|失败|错误|已停止|异常|OOM|溢出/;
const RE_OK=/✅|完成|成功|已载入|已保存|→/;
const RE_WN=/跳过|卸载|释放/;
const RE_HI=/开始|启动|载入|第 \d+ 步|队列|🚀/;
function cls(t){
  if(RE_ER.test(t))return 'er';
  if(RE_OK.test(t))return 'ok';
  if(RE_WN.test(t))return 'wn';
  if(RE_HI.test(t))return 'hi';
  return '';
}
function logHTML(keys){
  const lines=MIC.logsOf(keys);
  if(!lines.length)return `<div class="empty">暂无日志 · 运行后这里逐条追加，文字可直接选中复制</div>`;
  return lines.slice(-200).map(l=>{
    return `<div class="ln ${cls(l.text)}"><span class="t">${esc(l.t)}</span>`+
      `<span class="x">${esc(l.text)}</span></div>`;
  }).join('');
}
/* 日志框每次都是整块重画，浏览器会把滚动条弹回顶部：
   原本贴在底部就继续贴底（跟着新行走），人在翻旧日志就原地不动。 */
function fillLog(el,keys){
  const pinned=el.scrollHeight-el.scrollTop-el.clientHeight<64;
  const top=el.scrollTop;
  el.innerHTML=logHTML(keys);
  el.scrollTop=pinned?el.scrollHeight:top;
}
function logText(keys){
  return MIC.logsOf(keys).map(l=>l.t+'  '+l.text).join('\n');
}
function pct(){
  const s=MIC.s.st;
  if(!s.total)return 0;
  return Math.max(0,Math.min(100,Math.round(s.done/s.total*100)));
}
function elText(){
  const e=Number(MIC.s.st.elapsed)||0;
  return e>=60?`已用 ${Math.floor(e/60)} 分 ${Math.round(e%60)} 秒`:`已用 ${e.toFixed(0)} 秒`;
}
function pgText(){
  const s=MIC.s.st;
  if(!s.running)return s.status||'';
  if(s.running==='load')return `载入 ${Number(s.load_pct)||0}%${s.load_stage?' · '+s.load_stage:''} · ${elText()}`;
  return `去噪 ${s.done||0}/${s.total||0} · ${pct()}% · ${elText()}`;
}
/* 显存条：>90% 变警告色——12G 卡上这就是「要不要降档」的决策线 */
function vramHTML(){
  const s=MIC.s.st;
  const used=Number(s.vram_used)||0, tot=Number(s.vram_total)||12;
  const p=Math.max(0,Math.min(100,Math.round(used/tot*100)));
  const hot=used>=tot*0.92;
  return `<div class="vbar"><i style="width:${p}%;${hot?'background:var(--warn)':''}"></i></div>`+
    `<span class="mut fine">${used.toFixed(1)} / ${tot} GB${hot?' · 接近上限，建议 1024 档':''}</span>`;
}
function pillsHTML(){
  const s=MIC.s.st;
  return `<span class="pill ${s.model_loaded?'on':''}"><span class="dot ${s.model_loaded?'ok':''}"></span>${
      s.model_loaded?'模型已载入':'模型未载入'}</span>
    <span class="pill">显存 <b>${(Number(s.vram_used)||0).toFixed(1)}</b>/${s.vram_total||12}G</span>
    <span class="pill">图库 <b>${MIC.n(s.img_count)}</b></span>
    <span class="pill ${s.running?'on':''}"><span class="dot ${s.running?'run':''}"></span>${s.running?'运行中':'空闲'}</span>`;
}

/* 收起的只是预览：记住收起时那张的路径，下一张（路径变了）自然又显示出来 */
let prevHidden='';
function hidePrev(){prevHidden=MIC.s.st.last_image||'';MIC.render();}
function showPrev(){prevHidden='';MIC.render();}

/* 环境补全收尾：后端把 env_busy 落下来的那一刻重新体检一次，
   否则卡片会一直停在「补全中…」，得人手点「重新体检」才更新 */
let lastEnv=false;
function watchEnv(){
  const b=!!MIC.s.st.env_busy;
  if(lastEnv&&!b){
    if(MIC.env&&MIC.env.check)MIC.env.check();else MIC.render();
  }
  lastEnv=b;
}

/* 每次轮询后调用：只刷新页面上存在的插槽 */
function tick(){
  const s=MIC.s.st;
  MIC.$('pills').innerHTML=pillsHTML();
  document.querySelectorAll('#view [data-role]').forEach(el=>{
    const r=el.dataset.role;
    if(r==='log')fillLog(el,el.dataset.keys?el.dataset.keys.split(','):null);
    else if(r==='st')el.textContent=s.status||'就绪';
    else if(r==='dot')el.className='dot '+(el.dataset.mode==='model'
        ?(s.model_loaded?'ok':''):(s.running?'run':''));
    else if(r==='prog'){
      const bar=el.parentElement;
      if(s.running==='load'){
        /* 载入阶段也走真刻度：后端把第三方库的文本条折算成了百分比，
           只有第一帧还没数出来时暂时用不确定动画顶着 */
        const lp=Number(s.load_pct)||0;
        if(lp>0){bar.classList.remove('indet');el.style.width=lp+'%';}
        else{bar.classList.add('indet');el.style.width='';}
      }
      else{bar.classList.remove('indet');el.style.width=pct()+'%';}
    }
    else if(r==='pgtext')el.textContent=pgText();
    else if(r==='vram')el.innerHTML=vramHTML();
    else if(r==='count')el.textContent=MIC.n(s[el.dataset.field||'img_count']);
    else if(r==='result')el.innerHTML=`上一张 <b>${(Number(s.last_sec)||0).toFixed(1)}</b> 秒 · `+
      `用时目标 ≤60 秒 · `+(s.last_image?`输出 <b>${esc(String(s.last_image).split(/[\\/]/).pop())}</b>`:'尚无输出');
    else if(r==='imgprev'){
      if(!s.last_image){el.innerHTML=`<div class="empty">尚无成图 · 生成完成后这里出预览，点图片可打开所在文件夹</div>`;return;}
      if(prevHidden===s.last_image){
        el.innerHTML=`<div class="empty">预览已收起（文件还在，删图去画廊） · `+
          `<button class="btn sm gho" onclick="MIC.view.showPrev()">重新显示</button></div>`;return;
      }
      const T=MIC.s.lastThumb;
      if(T&&T.path===s.last_image)
        el.innerHTML=`<div class="prevbox"><img class="prev" src="${esc(T.url)}" alt="上一张" onclick="MIC.api.openPath(MIC.s.st.last_image)">`+
          `<button class="px" onclick="MIC.view.hidePrev()" title="收起这张预览（不删文件）">${ic('close','s')}</button></div>`+
          `<div class="btnrow"><span class="mut fine">这一张还想再改？</span><span class="grow"></span>`+
          `<button class="btn sm gho" onclick="MIC.runner.again('inpaint')">局部改这块</button>`+
          `<button class="btn sm gho" onclick="MIC.runner.again('edit')">整张再编辑</button></div>`;
      else{el.innerHTML=`<div class="empty">正在载入预览…</div>`;fetchThumb(s.last_image);}
    }
  });
  watchEnv();
}

/* 预览图走后端按需给 data:（html= 内联页里 file:// 图片显示不出来，也省得每轮询重传） */
let thumbBusy=false;
function fetchThumb(path){
  if(thumbBusy)return;
  thumbBusy=true;
  MIC.api.thumb(path).then(r=>{
    MIC.s.lastThumb=r&&r.ok?{path:path,url:r.url}:null;
    tick();
  }).catch(()=>{}).then(()=>{thumbBusy=false;});
}

/* 正在输入时不整页重画（会打断敲字），但这一跳过了不能就此不补：
   记一笔欠账，等焦点真从输入框移开了再补一次重画。 */
let pendingRender=false;
function skipForFocus(){
  const a=document.activeElement;
  if(a&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)&&a.closest&&a.closest('#view')){
    pendingRender=true;return true;}
  return false;
}
document.addEventListener('focusout',()=>{
  setTimeout(()=>{
    const a=document.activeElement;
    // 焦点只是从一个框挪到另一个框：接着打字，别拿整页重画去打断（tab 键会被吞）
    if(pendingRender&&(!a||!/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName))){
      pendingRender=false;MIC.render();}
  },0);
});

/* 任务起止：按钮/状态行要跟着重画；正在输入时不抢渲染（避免清空未保存的输入） */
let lastRun=null;
function watchFinish(){
  const cur=MIC.s.st.running;
  if(cur===lastRun)return;
  const ended=lastRun==='gen'&&cur===null;
  lastRun=cur;
  if(ended){
    if(MIC.gal)MIC.gal.invalidate();   // 生成收尾：画廊缓存作废，下次进页重扫
    if(MIC.s.cfg.notify!==false)MIC.toast(MIC.s.st.status||'生成已结束');
  }
  if(skipForFocus())return;
  MIC.render();
}

/* 右键/快捷键复制一类的小工具 */
function copyText(t,msg){
  const done=()=>MIC.toast(msg||'已复制');
  const fallback=()=>{
    const ta=document.createElement('textarea');
    ta.value=t;ta.style.position='fixed';ta.style.opacity='0';
    document.body.appendChild(ta);ta.select();
    try{document.execCommand('copy');done();}catch(e){MIC.toast('复制失败，请手动选择');}
    ta.remove();
  };
  if(navigator.clipboard&&navigator.clipboard.writeText)
    navigator.clipboard.writeText(t).then(done).catch(fallback);
  else fallback();
}

/* 让后端重扫画廊/显存并刷界面 */
function refreshStats(){
  return MIC.api.refreshStats().then(r=>{
    if(r&&r.state)MIC.mergeState(r.state);
    tick();
  }).catch(()=>{});
}

MIC.view={tick,watchFinish,logHTML,logText,fillLog,copy:copyText,
  pct,refreshStats,vramHTML,hidePrev,showPrev};
})();
