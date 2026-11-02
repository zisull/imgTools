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
  if(!lines.length)return `<div class="empty">暂无日志 · 运行后逐条追加</div>`;
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
function elText(sec){
  const e=Number(sec!=null?sec:MIC.s.st.elapsed)||0;
  return e>=60?`已用 ${Math.floor(e/60)} 分 ${Math.round(e%60)} 秒`:`已用 ${e.toFixed(0)} 秒`;
}
function cloudOf(){return (MIC.s.st.cloud||{});}
function pgText(lane){
  const s=MIC.s.st;
  if(lane==='cloud'){
    const c=cloudOf();
    if(!c.run)return c.status||'';
    return (c.status||'云端出片中')+' · '+elText(c.elapsed);
  }
  if(!s.running)return s.status||'';
  if(s.running==='load')return `载入 ${Number(s.load_pct)||0}%${s.load_stage?' · '+s.load_stage:''} · ${elText()}`;
  /* 出片只有 4 步（烘在 Turbo LoRA 里）：按步数走的百分比每步跨度太大，
     这一段更该看的是已经跑了多久，进度条就按步数粗算 */
  if(s.running==='video'){
    return `出片 ${s.done||0}/${s.total||0} 步 · ${elText()}`;
  }
  return `去噪 ${s.done||0}/${s.total||0} · ${pct()}% · ${elText()}`;
}
/* 显存条：>90% 变警告色——12G 卡上这就是「要不要降档」的决策线 */
function vramHTML(){
  const s=MIC.s.st;
  const used=Number(s.vram_used)||0, tot=Number(s.vram_total)||12;
  const p=Math.max(0,Math.min(100,Math.round(used/tot*100)));
  const hot=used>=tot*0.92;
  return `<div class="vbar"><i style="width:${p}%;${hot?'background:var(--warn)':''}"></i></div>`+
    `<span class="mut fine">${used.toFixed(1)} / ${tot} GB${hot?' · 接近上限，建议降一档':''}</span>`;
}
/* 顶栏三盏灯按「千问 / Moss / 系统」分类摆：两个引擎各有各的常驻态，
   混在一颗灯里就看不出「现在这张卡到底被谁占着」。
   环境关掉的那一路灯也不出现——和导航同一套判定，别让页面上残留一个开不了的开关。
   引擎灯三段：进程活着 ≠ 权重上卡，所以 Moss 分「已停 / 搬权重 / 已常驻」。 */
/* 一盏灯 = 图标 + 类名 + 灯 + 状态字：三段各有用处，
   图标与类名认得出是哪一路，灯看活没活，状态字说活到哪一步。 */
function engPill(name,icon,on,txt,tip){
  return `<span class="pill ${on?'on':''}" title="${esc(tip)}">${ic(icon,'s')}<b>${name}</b>`+
    `<span class="dot ${on?'ok':'off'}"></span><i>${esc(txt)}</i></span>`;
}
function pillsHTML(){
  const s=MIC.s.st,o=MIC.nav.envOn(),pills=[],c=cloudOf();
  if(o.qwen!==false)
    pills.push(engPill('千问','flower',!!s.model_loaded,s.model_loaded?'已载入':'未载入',
      '千问（diffusers 直跑）：权重在显存才谈得上秒出'));
  if(o.moss!==false||o.h3!==false)
    pills.push(engPill('Moss','wave',!!s.comfyui_loaded,
      s.comfyui_on?(s.comfyui_loaded?'已常驻':'搬权重'):'已停',
      'Moss / H3（内嵌 ComfyUI）：已停=没起进程，搬权重=正在把权重上显存'));
  /* 云端在跑时单列一盏：它不是「本机在忙」，但占着平台那边的一条线，
     从任何一页都该一眼看见，而不是跑回视频页才知道还没完。 */
  if(c.run)
    pills.push(engPill('云端','globe',true,c.run==='film'?'成片':'视频',
      '云端任务正在跑：本地照常能出图，云端这一路等它结束'));
  const busy=!!s.running||!!c.run;
  pills.push(engPill('系统','cog',busy,
    '显存 '+(Number(s.vram_used)||0).toFixed(1)+'/'+(s.vram_total||12)+'G · '+
      (busy?((c.run&&!s.running)?'云端出片中':'出图中'):'空闲'),
    '整卡显存与任务队列；两个引擎共用这一张卡，同一时间只可能一边在载'));
  return pills.join('');
}

/* 收起的只是预览：记住收起时那张的路径，下一张（路径变了）自然又显示出来 */
let prevHidden='';
function hidePrev(){prevHidden=MIC.s.st.last_image||'';MIC.render();}
function showPrev(){prevHidden='';MIC.render();}

/* 失败轮次不许被一张旧图盖住：状态里写的是失败，就把失败摊在结果行上 */
function failed(){return /失败|没出图/.test(String(MIC.s.st.status||''));}
const VIDEO_EXT=/\.(mp4|webm|mov|mkv)$/i;
function isVideo(p){return VIDEO_EXT.test(String(p||''));}
function resultHTML(lane){
  const s=MIC.s.st;
  if(lane==='cloud'){
    const c=cloudOf();
    if(c.last_fail)return `<b class="bad">❌ 本轮失败</b>：${esc(c.last_fail)}`;
    if(c.run)return esc(c.status||'云端出片中…');
    if(!c.status)return '就绪后开始';
    return esc(c.status)+(s.last_image?
      ` · 输出 <b>${esc(String(s.last_image).split(/[\\/]/).pop())}</b>`:'');
  }
  if(failed())
    return `<b class="bad">❌ 本轮失败</b>${s.last_fail?'：'+esc(s.last_fail):''} · `+
      (s.last_image?(isVideo(s.last_image)?'成片仍是上一段':'画面仍是上一张'):'尚无成图');
  return (isVideo(s.last_image)?'上一段':'上一张')+' <b>'+(Number(s.last_sec)||0).toFixed(1)+'</b> 秒 · '+
    (s.last_image?`输出 <b>${esc(String(s.last_image).split(/[\\/]/).pop())}</b>`:'尚无输出')+
    (s.dup_last?' · <span class="warn">与上一张相同（种子固定，填 -1 每轮随机）</span>':'');
}

/* 环境补全收尾：后端把 env_busy 落下来的那一刻重新体检一次，
   否则卡片会一直停在「补全中…」，得人手点「重新体检」才更新。
   手动下载没有 env_busy，单独看 dl.busy 的落沿。 */
let lastEnv=false, lastDl=false;
function watchEnv(){
  const b=!!MIC.s.st.env_busy, db=!!(MIC.s.st.dl||{}).busy;
  if(lastEnv&&!b){
    if(MIC.env&&MIC.env.check)MIC.env.check();else MIC.render();
  }
  if(lastDl&&!db&&!b&&!lastEnv){
    if(MIC.models&&MIC.models.refresh)MIC.models.refresh();
    if(MIC.env&&MIC.env.check)MIC.env.check();
  }
  lastEnv=b;lastDl=db;
}

function fmtB(n){
  n=Number(n)||0;const u=['B','KB','MB','GB','TB'];let i=0;
  while(n>=1024&&i<u.length-1){n/=1024;i++;}
  return (i?n.toFixed(1):Math.round(n))+' '+u[i];
}
function fmtT(s){
  s=Number(s)||0;if(!s||s>86400*7)return '';
  if(s<60)return Math.round(s)+' 秒';
  if(s<3600)return Math.round(s/60)+' 分';
  return Math.floor(s/3600)+' 小时 '+Math.round((s%3600)/60)+' 分';
}
function hostOf(u){return String(u||'').replace(/^https?:\/\//,'').split('/')[0];}

/* 环境横幅：只在「环境管理」这一页显示（四路环境收成了页内子页）。
   数字也按当前子页取：停在 H3 那格只报 H3 还差几项，不拿别的环境的欠账烦人。
   补全/下载进行中时，这里换成步骤 + 百分比 + 速度 + 剩余时间的那条。
   挂在 data-role 插槽上而不是整页重画：进度是从轮询并进来的，八百毫秒自己就变了。 */
function envBarHTML(){
  const s=MIC.s.st;
  const page=MIC.nav&&MIC.nav.pageOf?MIC.nav.pageOf():'';
  if(page!=='env')return '';
  const d=s.dl||{};
  if(s.env_busy||d.busy){
    const st=Number(s.env_step)||0, n=Number(s.env_steps)||0;
    const head=(n?'步骤 '+(st||'—')+'/'+n+' · ':'')+
      esc(s.env_label||(d.repo?'下载 '+d.repo:'补全中'));
    const total=Number(d.total)||0, done=Number(d.done)||0;
    const p=total?Math.max(0,Math.min(100,Math.round(done/total*100))):null;
    const bits=[];
    if(total)bits.push(fmtB(done)+' / '+fmtB(total));
    if(d.speed)bits.push(fmtB(d.speed)+'/s');
    const eta=fmtT(d.eta);if(eta)bits.push('剩 '+eta);
    if(d.files_total)bits.push((d.files_done||0)+'/'+d.files_total+' 文件');
    if(d.endpoint)bits.push(esc(hostOf(d.endpoint)));
    return `<div class="envbar busy"><span class="tic">${ic('refresh','s')}</span>
      <b>${head}</b>${p===null?'':`<div class="prog"><i style="width:${p}%"></i></div>`}
      <span class="mut fine">${bits.join(' · ')||'准备中…'}</span><span class="grow"></span>
      <button class="btn sm gho" onclick="MIC.nav.goto('logs')">${ic('hist','s')}看日志</button></div>`;
  }
  const zone=MIC.env&&MIC.env.tabId?MIC.env.tabId():'base';
  if(zone==='cloud')return '';
  const n=Number((s.env_todo_by||{})[zone])||0;
  if(!n)return '';
  return `<div class="envbar warn"><span class="tic">${ic('tool','s')}</span>
    <b>这一路还差 ${n} 项</b>
    <span class="mut fine">各环境互相独立，齐一个就能先用一个</span><span class="grow"></span>
    <button class="btn sm pri" onclick="MIC.env.fixZone('${zone}')">${ic('down','s')}一键补齐</button></div>`;
}

/* 每次轮询后调用：只刷新页面上存在的插槽 */
/* 左上角那一行跟着开着的环境走：一眼看出这台机器现在管得了哪几路 */
function envKey(){
  const o=MIC.nav.envOn();
  return ['qwen','moss','h3'].map(k=>o[k]===false?'0':'1').join('');
}
function brandSub(){
  const o=MIC.nav.envOn(),names=[];
  if(o.qwen!==false)names.push('千问');
  if(o.moss!==false)names.push('Moss');
  if(o.h3!==false)names.push('H3');
  return names.length?names.join(' + ')+' · 本地生图': '所有模型环境都关着';
}
function tick(){
  const s=MIC.s.st;
  MIC.$('pills').innerHTML=pillsHTML();
  const bs=MIC.$('brandSub');
  if(bs)bs.textContent=brandSub();
  /* 环境横幅在全局插槽上（不在 #view 里）：哪一页都跟着刷新 */
  const slot=MIC.$('envslot');if(slot)slot.innerHTML=envBarHTML();
  document.querySelectorAll('#view [data-role]').forEach(el=>{
    const r=el.dataset.role;
    const cloud=el.dataset.lane==='cloud';
    const c=cloudOf();
    if(r==='log')fillLog(el,el.dataset.keys?el.dataset.keys.split(','):null);
    else if(r==='st')el.textContent=(cloud?c.status:s.status)||'就绪';
    else if(r==='dot')el.className='dot '+(el.dataset.mode==='model'
        ?(s.model_loaded?'ok':''):((cloud?c.run:s.running)?'run':''));
    else if(r==='prog'){
      const bar=el.parentElement;
      if(cloud){
        if(c.run){bar.classList.add('indet');el.style.width='';}
        else{bar.classList.remove('indet');el.style.width=(c.done&&c.total?'100%':'0%');}
      }
      else if(s.running==='load'){
        /* 载入阶段也走真刻度：后端把第三方库的文本条折算成了百分比，
           只有第一帧还没数出来时暂时用不确定动画顶着 */
        const lp=Number(s.load_pct)||0;
        if(lp>0){bar.classList.remove('indet');el.style.width=lp+'%';}
        else{bar.classList.add('indet');el.style.width='';}
      }
      else{bar.classList.remove('indet');el.style.width=pct()+'%';}
    }
    else if(r==='pgtext')el.textContent=pgText(cloud?'cloud':'');
    else if(r==='logcount')el.textContent=MIC.s.logs.length;
    else if(r==='vram')el.innerHTML=vramHTML();
    else if(r==='count')el.textContent=MIC.n(s[el.dataset.field||'img_count']);
    else if(r==='result')el.innerHTML=resultHTML(cloud?'cloud':'');
    /* 成片时间线：结构变了才重画，进度条/耗时每跳自己更新（见 film.js paint） */
    else if(r==='film'){if(MIC.film&&MIC.film.paint)MIC.film.paint(el);}
    else if(r==='imgprev'){
      if(!s.last_image){el.innerHTML=`<div class="empty">尚无成图 · 出图后在这里预览，点图可打开文件夹</div>`;return;}
      /* 成片不内嵌播放：内联页放不了 file://，引视频解码依赖不值当——
         给一颗按钮把成片交给系统播放器，缩略同理不做 */
      if(isVideo(s.last_image)){
        const sig='V|'+s.last_image;
        if(el.dataset.sig===sig)return;
        el.dataset.sig=sig;
        el.innerHTML=`<div class="empty">${ic('film','s')} 成片已生成 · `+
          `<b>${esc(String(s.last_image).split(/[\\/]/).pop())}</b><br>`+
          `<button class="btn sm pri" onclick="MIC.api.openPath(MIC.s.st.last_image)">${ic('play','s')}打开成片</button></div>`;
        return;
      }
      if(prevHidden===s.last_image){
        el.innerHTML=`<div class="empty">预览已收起 · 删图去画廊 · `+
          `<button class="btn sm gho" onclick="MIC.view.showPrev()">重新显示</button></div>`;return;
      }
      const T=MIC.s.lastThumb;
      /* 这块里嵌着一整张 base64 缩略图：每 800ms 无条件重刷 innerHTML，WebView2 就得把
         同一张图重新解码一遍。同一个文件、同一个收起态就直接跳过（取图失败时不记签名，
         下一跳还会重试）。失败标记也进签名：这一轮失败了要立刻在图上说一声。 */
      const bad=failed();
      const have=T&&T.path===s.last_image;
      const sig=s.last_image+'|'+(prevHidden===s.last_image?'h':'v')+'|'+(bad?'f':'-');
      if(have&&el.dataset.sig===sig)return;
      if(have)el.dataset.sig=sig;
      if(have)
        el.innerHTML=(bad?`<div class="failnote">❌ 本轮失败，下面是上一张</div>`:'')+
          `<div class="prevbox"><img class="prev" src="${esc(T.url)}" alt="上一张" onclick="MIC.api.openPath(MIC.s.st.last_image)">`+
          `<button class="px" onclick="MIC.view.hidePrev()" title="收起这张预览（不删文件）">${ic('close','s')}</button></div>`+
          `<div class="btnrow"><span class="grow"></span>`+
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

/* 任务起止：按钮/状态行要跟着重画；正在输入时不抢渲染（避免清空未保存的输入）。
   两条通道各记一个上值：云端（st.cloud.run）与本地（st.running）互不相干，
   任何一条收尾都要作废画廊缓存；只盯 st.running 会把云端那一路的收尾漏掉。 */
let lastRun=null,lastCloud=null;
function watchFinish(){
  const s=MIC.s.st, cur=s.running, cRun=(s.cloud||{}).run||null;
  if(cur===lastRun&&cRun===lastCloud)return;
  const wasGpu=lastRun==='gen'||lastRun==='video'||
               lastRun==='film'||lastRun==='film_merge';
  const ended=wasGpu&&cur===null;
  const cloudEnded=!!lastCloud&&!cRun;
  lastRun=cur;lastCloud=cRun;
  if(ended||cloudEnded){
    if(MIC.gal)MIC.gal.invalidate();   // 收尾：画廊缓存作废，下次进页重扫
    if(MIC.film&&MIC.film.refresh)MIC.film.refresh();
    if(MIC.s.cfg.notify!==false)
      MIC.toast(cloudEnded?((s.cloud||{}).status||'云端任务已结束')
                          :(s.status||'生成已结束'));
  }
  if(skipForFocus())return;
  MIC.render();
}

/* 结构性状态一变，整页布局就得跟着变：engine / 档位 / 引擎灯这些决定的是
   「这一屏该出现哪颗按钮」，不是 data-role 占位，tick 只补占位会留下一屏旧按钮
   （引擎已经切走了，页上还挂着上一档的按钮）。走同一道输入闸门。 */
let lastStruct="";
function watchStruct(){
  const s=MIC.s.st;
  /* env_todo 也算结构：它决定欢迎页/生图页那条环境提示在不在，
     开机体检晚半秒到，到了一屏字得自己补上。
     云端任务起止也进这个键：视频页/成片页/云端账号页的锁与停止按钮要跟着换。 */
  const k=[s.engine,s.moss_tier,s.comfyui_on,s.comfyui_loaded,s.moss_installed,
           s.env_todo,envKey(),(s.cloud||{}).run||''].join('|');
  if(k===lastStruct)return;
  const first=lastStruct==="";
  lastStruct=k;
  if(first)return;                 // 进页面头一帧由 boot 的 render 负责，别抢
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

MIC.view={tick,watchFinish,watchStruct,logHTML,logText,fillLog,copy:copyText,
  pct,refreshStats,vramHTML,hidePrev,showPrev,envBarHTML,isVideo};
})();
