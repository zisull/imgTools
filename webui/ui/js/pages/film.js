/* pages/film.js —— 成片：一段剧情 → AI 拆分镜 → 逐段出片 → 合成一条
   左右两栏，左=剧本与分镜，右=进度与成片。
   出片通道与视频页同义：本地占显存、云端要登录号；两种接法：
     接帧＝每段拿上一段尾帧当参考（画面连贯，要 FFmpeg 抽帧）；
     逐镜＝每段各自成片（不强接，适合快剪或纯文字起步）。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

const DUR=[[30,'30 秒'],[60,'1 分'],[120,'2 分'],[180,'3 分'],[300,'5 分']];
const LEN=[{code:'5',name:'5 秒'},{code:'10',name:'10 秒'},{code:'15',name:'15 秒'}];

/* 与视频页同一套原生画幅：H3 的 768P 是 1344×768，竖屏镜像 768×1344 */
const NATIVE={h768:[1344,768],v768:[768,1344]};
C.dimSnap['film.size']=function(p,o){
  const n=NATIVE[o+p];
  return n?{w:n[0],h:n[1]}:C.pDims(p,o);
};
/* 多号不能接帧：每段都要等上一段尾帧，并行就落空了。切到多号时顺手把接法收成逐镜，
   免得界面写着「接帧」、开跑才被降级。 */
C.segFit['film.acct_mode']=function(val,patch){
  if(val==='multi')MIC.mset(patch,'film.mode','shot');
};
C.segFit['film.exec']=function(val,patch){
  const list=val==='cloud'?C.P_VIDEO_CLOUD:C.P_VIDEO;
  const m=/^(\d+)x(\d+)$/i.exec(String((patch.film||{}).size||''));
  if(!m)return;
  const w=+m[1],h=+m[2],cap=list[list.length-1];
  if(Math.min(w,h)<=cap)return;
  const d=C.dimSnap['film.size'](C.pOf(Math.min(w,h),list),C.orientOf(w,h));
  MIC.mset(patch,'film.size',d.w+'x'+d.h);
};

/* ---------- 云端档案（只读，绝不为「看一眼」拉起浏览器） ---------- */
let brief=null,briefing=false,briefAt=0;
function sigBrief(o){return JSON.stringify([o&&o.dp,o&&o.accts,o&&o.wf,o&&o.busy]);}
function askBrief(force){
  if(briefing)return;
  if(!force&&brief&&Date.now()-briefAt<8000)return;
  briefing=true;
  MIC.api.cloudBrief().then(r=>{
    briefing=false;briefAt=Date.now();
    if(!r)return;
    const changed=sigBrief(r)!==sigBrief(brief);
    brief=r;
    if(changed)repaint();
  }).catch(()=>{briefing=false;});
}
function wfNow(){
  const c=(MIC.s.cfg&&MIC.s.cfg.cloud)||{};
  return String(c.workflow||(brief&&brief.wf)||'').trim();
}
const isFile=()=>/\.(json|txt)$/i.test(wfNow());
const refsNow=()=>C.refsOf('film.refs');
/* 多号只在云端生效；切回本地时接法按原来的看，别把「逐镜」当成用户的选择 */
function acctMode(){
  const f=MIC.s.cfg.film||{};
  return String(f.exec)==='cloud'&&String(f.acct_mode)==='multi'?'multi':'single';
}
function effMode(){return acctMode()==='multi'?'shot':String(((MIC.s.cfg||{}).film||{}).mode||'');}
/* 本地工作流先验结构：和视频页同一个桥，选完就能看出能不能跑 */
let wfChk=null,wfChkKey='';
function wfChkHTML(){
  if(!isFile())return '';
  if(!wfChk)return '<span class="mut fine">正在检查这份工作流…</span>';
  return '<span class="'+(wfChk.ok?'mut fine':'bad')+'">'+
    (wfChk.ok?'✓ ':'✗ ')+esc(wfChk.msg||'')+'</span>';
}
function askWfCheck(force){
  const p=wfNow();
  if(!isFile()||!p){wfChk=null;wfChkKey='';return;}
  if(!force&&wfChkKey===p)return;
  wfChkKey=p;wfChk=null;
  MIC.api.cloudCheckWf(p).then(r=>{
    if(wfNow()!==p)return;
    wfChk=r||{ok:false,msg:'没回话'};
    const el=document.querySelector('#view [data-role="wfchk"]');
    if(el)el.innerHTML=wfChkHTML();
  }).catch(e=>{wfChk={ok:false,msg:String(e&&e.message||e)};});
}

/* ---------- 最近工程 ---------- */
let projects=[],listBusy=false,listAt=0;
function sigList(items){
  return JSON.stringify((items||[]).map(x=>
    [x.id,x.done,x.total,x.film,x.time,x.running,x.current]));
}
function askList(force){
  if(listBusy)return;
  if(!force&&listAt&&Date.now()-listAt<8000)return;
  listBusy=true;
  MIC.api.filmList().then(r=>{
    listBusy=false;listAt=Date.now();
    if(!r||!r.ok)return;
    const items=r.items||[];
    const changed=sigList(items)!==sigList(projects);
    projects=items;
    if(changed)repaint();
  }).catch(()=>{listBusy=false;});
}

/* 重读档案/工程别在人打字时整页重画 */
function repaint(){
  if(!MIC.nav||MIC.nav.pageOf()!=='film')return;
  const a=document.activeElement;
  if(a&&/^(INPUT|TEXTAREA)$/.test(a.tagName)&&a.closest&&a.closest('#view'))return;
  MIC.render();
}

/* ---------- 拆分镜结果（页内存状态：改完描述直接参与出片） ---------- */
let plan=null,planning=false,firing=false,regenBusy=false;
function shotSec(){const s=+(MIC.mget(MIC.s.cfg,'film.shot')||15);return s===5||s===10?s:15;}
function inputSig(){
  const f=MIC.s.cfg.film||{};
  return [String(f.story||'').trim(),+f.total||0,+f.shot||15,
          String(f.style||''),String(f.size||'')].join('|');
}
function planStale(){return !!plan&&plan.sig!==inputSig();}
function normPlanShot(sh){
  return {summary:String((sh&&sh.summary)||'').trim(),
          prompt:String((sh&&sh.prompt)||'').trim(),
          seconds:Number(sh&&sh.seconds)||shotSec()};
}
/* 整页重画前先把还没 blur 的输入收进 plan，删/重写才不会被旧值盖回去 */
function syncRows(){
  if(!plan)return;
  document.querySelectorAll('#view textarea[data-shot]').forEach(el=>{
    const i=+el.dataset.shot;
    if(plan.shots[i])plan.shots[i].prompt=String(el.value||'').trim();
  });
}

/* ---------- 进度时间线 ---------- */
const thumbs={};
function ensureThumb(p){
  if(!p||p in thumbs)return;
  thumbs[p]='';
  MIC.api.thumb(p).then(r=>{
    if(!r||!r.ok)return;
    thumbs[p]=r.url;
    document.querySelectorAll('#view img[data-thumb]').forEach(im=>{
      if(im.dataset.thumb===p)im.src=r.url;
    });
  }).catch(()=>{});
}
const pad=n=>String(n||0).padStart(2,'0');
const shortName=p=>String(p||'').split(/[\\/]/).pop()||'';
function pctOf(fs){const t=+fs.total||0;return t?Math.max(0,Math.min(100,
  Math.round((+fs.done||0)/t*100))):0;}
function elapsedText(e){
  e=Number(e)||0;if(!e)return '';
  return e>=60?Math.floor(e/60)+' 分 '+Math.round(e%60)+' 秒':Math.round(e)+' 秒';
}
function phaseText(fs){
  const st=fs.state;
  if(st==='running')return fs.phase||'出片';
  if(st==='planning')return '拆分镜';
  if(st==='paused')return '已暂停';
  if(st==='stopped')return '已停止';
  if(st==='failed')return '中断';
  if(st==='done')return fs.merge_ok?'已完成':'分段完成';
  return '未开始';
}
function sigFilm(fs){
  return [fs.state,fs.phase,fs.done,fs.total,fs.current,fs.film,
          fs.merge_ok,fs.msg,fs.parallel,
          (fs.shots||[]).map(s=>[s.i,s.state,s.sec,s.file_abs,s.frame_abs,s.acct_name]
            .join(',')).join('|')
         ].join('~');
}
function filmHTML(fs){
  if(!fs||!(+fs.total)){
    if(fs&&fs.state==='planning')
      return `<div class="filmstat"><span class="dot run"></span><b>拆分镜中</b>`+
        `<span class="mut">AI 正在按剧情拆镜头…</span></div>`;
    return `<div class="empty">还没有分镜 · 左边写剧情，点「AI 拆分镜」或「开始成片」</div>`;
  }
  const cells=(fs.shots||[]).map(sh=>{
    const st=String(sh.state||'wait'),ok=st==='done';
    const sec=Number(sh.sec)||0;
    const lab=ok?(sec?sec.toFixed(1)+' 秒':'完成')
      :st==='run'?'出片中':st==='fail'?'失败':st==='skip'?'跳过':'待出';
    const err=st==='fail'&&sh.err?' · '+sh.err:'';
    const who=sh.acct_name?' · '+sh.acct_name:'';
    const rn=String(sh.ref_note||'');
    const src=sh.frame_abs?(thumbs[sh.frame_abs]||''):'';
    return `<div class="fshot ${st}"${ok?` onclick="MIC.film.openShot(${sh.i})"`:''}`+
      ` title="${esc((ok?'打开第 '+sh.i+' 段':'第 '+sh.i+' 段 · '+lab)+who+err+
        (rn?' · 参考 '+rn:''))}">`+
      `<div class="fthumb">${sh.frame_abs?`<img${src?` src="${esc(src)}"`:''}`+
        ` data-thumb="${esc(sh.frame_abs)}" alt="">`:
        ic(st==='run'?'refresh':'image','s')}</div>`+
      `<span class="fno">${pad(sh.i)}</span>`+
      (rn?`<span class="fref">${esc(rn)}</span>`:'')+
      `<span class="fstate ${ok?'ok':(st==='fail'?'er':'')}">${esc(lab+who)}</span>`+
      (ok||st==='fail'?`<button class="fre" title="重出第 ${sh.i} 段"`+
        ` onclick="event.stopPropagation();MIC.film.redo(${sh.i})">${ic('refresh','s')}</button>`:'')+
      `</div>`;
  }).join('');
  const dot=fs.state==='running'?'run':(fs.state==='done'?'ok':'off');
  return `<div class="filmstat">
      <span class="dot ${dot}"></span><b>${esc(phaseText(fs))}</b>
      <span class="mut" data-fs-status>${esc(fs.status||'')}</span><span class="grow"></span>
      <span class="mut fine" data-fs-done>${+fs.done||0}/${+fs.total||0}</span>
      <span class="mut fine" data-fs-elapsed>${esc(elapsedText(fs.elapsed))}</span>
    </div>
    <div class="fbar"><i style="width:${pctOf(fs)}%"></i></div>
    <div class="filmline">${cells}</div>
    ${fs.film?`<div class="filmout">${ic('film','s')} <b>${esc(shortName(fs.film))}</b>
      <span class="grow"></span>
      <button class="btn sm pri" onclick="MIC.film.openFilm()">${ic('play','s')}播放</button></div>`:''}`;
}
function paint(el){
  const fs=MIC.s.st.film||{};
  const s=sigFilm(fs);
  if(el.dataset.sig!==s){
    el.dataset.sig=s;
    el.innerHTML=filmHTML(fs);
    (fs.shots||[]).forEach(sh=>{if(sh.frame_abs)ensureThumb(sh.frame_abs);});
  }
  const bar=el.querySelector('.fbar i');if(bar)bar.style.width=pctOf(fs)+'%';
  const dn=el.querySelector('[data-fs-done]');
  if(dn)dn.textContent=(+fs.done||0)+'/'+(+fs.total||0);
  const et=el.querySelector('[data-fs-elapsed]');
  if(et)et.textContent=elapsedText(fs.elapsed);
  const st=el.querySelector('[data-fs-status]');
  if(st)st.textContent=fs.status||'';
}

/* ---------- 页面 ---------- */
function liveSub(){
  const f=MIC.s.cfg.film||{},fs=MIC.s.st.film||{};
  if(fs.state==='running'||fs.state==='planning')
    return (fs.phase||'出片')+' · '+(+fs.done||0)+'/'+(+fs.total||0)+
      ((+fs.parallel)>1?' · '+(+fs.parallel)+' 号并行':'');
  const total=+f.total||60,shot=+f.shot||15;
  const n=Math.max(1,Math.min(40,Math.round(total/shot)));
  return (String(f.exec)==='cloud'?'云端':'本地')+' · '+n+' 段 × '+shot+' 秒 · '+
    (acctMode()==='multi'?'多号并行'
      :(String(f.mode)==='shot'?'逐镜':'接帧'));
}
function note(icon,text,btn){
  return `<div class="notebar">${ic(icon,'s')}<b>${esc(text)}</b>`+
    `<span class="grow"></span>${btn||''}</div>`;
}
function cloudProblem(){
  const b=brief;if(!b)return '';
  if(b.dp===false)return '缺 DrissionPage：到「环境管理 → 基础」补齐后重开软件';
  if(!(b.accts||[]).length)
    return (+b.failed||0)
      ? '可用的号都标成「出片失败」了：到「环境管理 → 云端账号」重新登录或换号'
      : '还没有可用的登录号：到「环境管理 → 云端账号」登录并保存';
  if(!wfNow()&&!b.wf_default)
    return '还差一份 H3 工作流：在下面那格填网页上跑通过的地址或本地 .json';
  if(!refsNow().length)return '云端按参考生成：先选一张参考图（本地可纯文字起步）';
  return '';
}
function acctSel(f){
  const list=(brief&&brief.accts)||[];
  if(!list.length)
    return '<span class="mut fine">还没有可用的号 · 到「环境管理 → 云端账号」登录并保存</span>';
  return C.sel('film.acct',list.map(a=>({name:a.name,code:a.id})),'自动分配（按空闲号）');
}
function wfRow(cloud){
  const local=isFile(),cur=wfNow(),def=String((brief&&brief.wf_default)||'');
  return C.field('工作流',
    C.pathrow('cloud.workflow',local?'本地导出的工作流（.json）':
      '网页上跑通过的 H3 工作流地址或 ID','file',true)+
    (local?'<div data-role="wfchk" style="margin-top:4px">'+wfChkHTML()+'</div>':'')+
    (cur?'<div class="fine mut" style="margin-top:4px">这趟用的是上面那份，不是默认那张 '+
      '<button class="btn" onclick="MIC.film.useWfDefault()">用回默认</button></div>':''),
    '和视频页共用同一份：粘地址，或把「导出工作流」存下的 .json 拖进来。本地文件开跑时自己借平台页面。'+
    (cur?'':' 留空＝默认那张'+(def?'（#'+def+'）':'')+'。'));
}
/* 时长快捷键：只做「写一个键 + 重画」，不参与 data-k——
   和「秒」输入框绑同一个键的话，点按钮时读屏会把输入框里的旧数又写回去 */
function durChips(){
  const cur=+MIC.mget(MIC.s.cfg,'film.total');
  return '<div class="chiprow">'+DUR.map(([v,l])=>
    `<button class="chip${cur===v?' on':''}" onclick="MIC.film.setDur(${v})">${l}</button>`
  ).join('')+'</div>';
}
/* 这一段会带哪几张图：和 refs_for 同一套规则，只是接帧的尾帧要等出片，先标成 @1 */
function refHint(i){
  const f=MIC.s.cfg.film||{},refs=C.refsOf('film.refs'),n=refs.length;
  const rm=String(f.ref_mode||'same');
  if(effMode()==='chain'&&i>1){
    if(!n)return '@1=上一段尾帧';
    const k=rm==='all'?Math.min(n,3):1;
    return '@1=上一段尾帧'+(k>1?' · @2..@'+(k+1)+'=固定图':' · @2=固定图');
  }
  if(!n)return '';
  if(rm==='seq')return '参考 @'+((i-1)%n+1);
  if(rm==='all')return '参考 '+refs.map((_,k)=>'@'+(k+1)).join(' ');
  return '参考 @1';
}
function planHTML(){
  if(!plan)return '';
  const rows=plan.shots.map((sh,i)=>
    `<div class="shotrow">
      <div class="sno">${pad(i+1)}</div>
      <div class="smain">
        ${sh.summary?`<div class="ssum">${esc(sh.summary)}</div>`:''}
        <textarea class="inp" rows="2" data-shot="${i}"
          oninput="MIC.film.edit(${i},this.value)"
          placeholder="画面描述词">${esc(sh.prompt)}</textarea>
        ${refHint(i+1)?`<div class="sref">${esc(refHint(i+1))}</div>`:''}
      </div>
      <div class="sact"><span class="mut fine">${+sh.seconds||shotSec()} 秒</span>
        <div class="sbtns">
          <button class="btn sm gho" title="按剧情和前后镜重写这一段"
            onclick="MIC.film.regen(${i})">${ic('refresh','s')}重写</button>
          <button class="btn sm gho" title="润色这段描述"
            onclick="MIC.film.polish(${i})">${ic('wand','s')}润色</button>
          <button class="btn sm gho" title="删除这一段"
            onclick="MIC.film.drop(${i})">${ic('trash','s')}</button>
        </div>
      </div>
    </div>`).join('');
  return `<div class="planhead">
      <b>${esc(plan.title||'分镜')}</b>
      <span class="mut fine">${plan.shots.length} 段 × ${+plan.shot_sec||shotSec()} 秒`+
      `${plan.total_sec?' · 约 '+plan.total_sec+' 秒':''}</span>
      ${planStale()?`<span class="warn fine">参数改过，这份还是上一版</span>`:''}
      <span class="grow"></span>
      <button class="btn sm gho" onclick="MIC.film.plan()">${ic('refresh','s')}重新拆</button>
    </div><div class="shotlist">${rows}</div>`;
}
function projectsHTML(){
  if(!projects.length)return '<div class="empty">还没有工程 · 跑完一部会记在这里</div>';
  return projects.map((it,i)=>{
    const cur=!!it.current,run=!!it.running;
    return `<div class="mrow">
      <div class="minfo"><b>${esc(it.title||it.id)}</b>
        <span class="fine">${esc(it.time||'')} · ${+it.done||0}/${+it.total||0} 段`+
        `${it.film?' · 有成片':''}${cur?' · 当前':''}</span></div>
      ${run?'':`<button class="btn sm" onclick="MIC.film.resumeAt(${i})">继续</button>`}
      ${it.film?`<button class="btn sm gho" onclick="MIC.film.openAt(${i})">${ic('play','s')}成片</button>`:''}
      ${run?'':`<button class="btn sm gho" title="删掉这个工程" `+
        `onclick="MIC.film.delAt(${i})">${ic('close','s')}</button>`}
    </div>`;
  }).join('');
}

MIC.registerPage('film',{
  title:'剧本成片',sub:liveSub,icon:'film',
  render(){
    const s=MIC.s.st,f=MIC.s.cfg.film||{},fs=s.film||{},c=s.cloud||{};
    const cloud=String(f.exec)==='cloud';
    /* 任务位按通道算：云端成片在跑只锁云端这条路，本地生图/本地成片照常；
       反过来本地占着卡，也不该把云端这条锁死。 */
    const ownRun=cloud?c.run==='film':!!s.running;
    const cloudBusy=!!c.run;
    const busy=ownRun;
    if(cloud&&!briefing)askBrief();
    if(cloud&&isFile())askWfCheck();
    if(!listAt)askList();

    const total=+f.total||60,shot=+f.shot||15;
    const n=Math.max(1,Math.min(40,Math.round(total/shot)));
    const over=Math.round(total/shot)>40;
    const custom=String(f.size)==='custom';

    const fields=
      C.field('剧情',C.ta('film.story',6,
        '一个女孩推门走进雨夜的旧书店，店主抬头，她认出了他…'),
        '写人物、场景、起承转合；AI 按这个拆镜头，没写到的细节它会自己补')+
      '<div class="grid3">'+
        C.field('总时长',durChips()+
          '<div style="margin-top:6px">'+C.num('film.total','秒（可手填）')+'</div>',
          '每段秒数 × 段数；最多 40 段（15 秒一段＝10 分钟），再长就分两集')+
        C.field('每段',C.sel('film.shot',LEN),
          'H3 只认 5/10/15 秒；短段接得密，长段信息多')+
        C.field('通道',C.seg('film.exec',[['local','本地'],['cloud','云端']],true),
          cloud?'云端跑：不占显存、按平台计费，要一个保存过的登录号'
               :'本机跑：拉起 ComfyUI、占显存，不花钱')+
      '</div>'+
      (over?`<div class="hint warn">约 ${Math.round(total/shot)} 段，超过 40 段上限：把总时长压到 600 秒内，或拆两集</div>`:'')+
      '<div class="grid3">'+
        C.field('清晰度',C.pSizeSel('film.size',cloud?C.P_VIDEO_CLOUD:C.P_VIDEO,
          {cw:'film.cw',ch:'film.ch'}),
          cloud?'P=短边，云端最高 2K（短边 1440）':'P=短边；768P 是 H3 原生档 1344×768')+
        (custom?C.field('宽（px）',C.num('film.cw','768'),'自动贴到 16 的倍数'):'')+
        (custom?C.field('高（px）',C.num('film.ch','1344'),'自动贴到 16 的倍数'):'')+
        C.field('风格',C.txt('film.style','电影感写实'),
          '会追加到每一段的描述后面；留空就不加')+
      '</div>'+
      C.field(cloud?'参考图（1~4 张）':'首帧（可选）',
        C.refsRow('film.refs',4,
          cloud?'点「加图」从画廊挑；描述里用 @1 @2 点名第几张'
               :'本地只认第一张；多图参考走云端'),
        cloud?'这份工作流按参考生成：不填平台会判失败。接帧时第 2 段起上一段尾帧排 @1，固定参考图顺延'
             :'接帧模式下全片从第一张开始；不给就用文字直接起第一段')+
      (cloud?'<div class="grid3">'+
        C.field('账号',acctSel(f),'留默认＝按空闲号自动分配；一个号两次没出成会被标记并换号')+
        C.field('账号模式',C.seg('film.acct_mode',[['single','单号'],['multi','多号']],true),
          '多号=每段直接用同一组参考图，空闲号并行出；接帧要等尾帧，只能单号')+
        C.field('参考',C.seg('film.ref_mode',[['same','同一张'],['seq','按序'],['all','全带']],true),
          '同一张=每段都用第 1 张；按序=第 i 段用第 i 张轮换；全带=每段带上全部')+
      '</div>'+wfRow(true):'')+
      (cloud&&acctMode()==='multi'
        ?'<div class="hint">多号并行按逐镜跑：每段不等上一段尾帧，画面不承接；要连贯就改单号接帧</div>'
        :'')+
      C.fold('更专业','cog',
        '<div class="grid3">'+
          C.field('接法',acctMode()==='multi'
              ?'<span class="mut fine">逐镜 · 多号并行不收尾帧</span>'
              :C.seg('film.mode',[['chain','接帧'],['shot','逐镜']]),
            '接帧=每段拿上一段尾帧当参考，画面连贯（要 FFmpeg 抽帧）；'+
            '逐镜=每段各自成片，云端会按空闲号并行')+
          C.field('重试',C.num('film.retry','次'),
            '本机：单段失败重试次数；云端固定每个号试 2 次（失败先重启浏览器）再换号')+
          C.field('种子',C.seedRow('film.seed'),'随机=每段新种子；固定=同参数可复现')+
        '</div>','接法 · 重试 · 种子')+
      planHTML();

    const runKey=s.running==='film'||c.run==='film';
    let act='<div class="actrow">'+
      (busy?'':`<button class="btn gho" onclick="MIC.film.plan()">${ic('wand','s')}AI 拆分镜</button>`);
    if(runKey)
      act+=`<button class="btn pri big" onclick="MIC.film.stop()">${ic('stop','s')}停止</button>`+
        '<span class="mut fine">当前段收尾后停，已出的段都留着</span>';
    else if(s.running==='film_merge')
      act+='<span class="mut fine">合成中，等它结束…</span>';
    else if(busy)
      act+=`<span class="mut fine">${cloud?'云端':'本机'}有任务在跑，等它结束…</span>`;
    else if(cloud&&cloudBusy)
      act+=`<button class="btn pri big" disabled title="云端视频在跑">${ic('play','s')}开始成片</button>`+
        '<span class="mut fine">云端视频在跑，等它结束或先停掉</span>';
    else
      act+=`<button class="btn pri big" data-start onclick="MIC.film.start()">${ic('play','s')}开始成片</button>`+
        `<span class="mut fine">${n} 段 · 约 ${Math.max(1,Math.round(n*(cloud?6:4)))}~`+
        `${Math.max(2,Math.round(n*10))} 分钟</span>`;
    act+='</div>';

    /* 缺什么就在这一页说：Key、FFmpeg、云端登录/工作流各一条 */
    let notes='';
    if(!s.ai_key)
      notes+=note('key','文本 API 未配置：拆分镜与润色用不了，手填分镜仍能出片',
        `<button class="btn sm pri" onclick="MIC.nav.goto('settings')">去设置</button>`);
    if(effMode()==='chain'&&!s.ffmpeg)
      notes+=note('tool','接帧要 FFmpeg 抽尾帧：补上「FFmpeg 静态包」，或把接法改成逐镜',
        `<button class="btn sm pri" onclick="MIC.env.focus('base')">去补齐</button>`);
    if(!cloud&&refsNow().length>1)
      notes+=note('image','本地只认第一张参考图：多图参考走云端', '');
    if(cloud&&brief){
      const p=cloudProblem();
      /* 缺依赖/缺号能跳到对应那一格；缺工作流或首帧图就在本页，不用把人支走 */
      const to=brief.dp===false?'base':(!(brief.accts||[]).length?'cloud':'');
      if(p)notes+=note('globe',p,to?
        `<button class="btn sm pri" onclick="MIC.env.focus('${to}')">去处理</button>`:'');
    }

    let acts='';
    if(runKey){
      acts=`<button class="btn" onclick="MIC.film.stop()">${ic('stop','s')}停止</button>`;
    }else if(s.running==='film_merge'){
      acts='<span class="mut fine">合成中…</span>';
    }else{
      const canResume=fs.state==='paused'||fs.state==='stopped'||fs.state==='failed';
      if(canResume)
        acts+=`<button class="btn pri" onclick="MIC.film.resume()">${ic('play','s')}继续</button>`;
      if(fs.dir&&(+fs.missing||0)>0)
        acts+=`<button class="${canResume?'btn':'btn pri'}" onclick="MIC.film.redoFailed()">`+
          `${ic('refresh','s')}重出失败段</button>`;
      if(fs.dir&&(+fs.done||0)>0)
        acts+=`<button class="btn" onclick="MIC.film.merge()">${ic('film','s')}重新合成</button>`;
      if(fs.dir)
        acts+=`<button class="btn gho" onclick="MIC.film.openDir()">${ic('folder','s')}工程目录</button>`;
    }
    const right=C.card('进度与成片','film',
      '<div class="filmwrap" data-role="film"></div>'+
      (fs.msg?`<div class="hint" style="margin-top:8px">${esc(fs.msg)}</div>`:'')+
      '<div class="btnrow filmacts">'+acts+'</div>'+
      C.fold('最近工程','hist',projectsHTML(),'续跑 · 打开成片'),
      {note:fs.state==='running'?'进行中':(fs.film?'有成片':'')});

    return notes+C.duo(
      C.card('剧本与分镜','film',C.lock(busy,fields)+act),
      right);
  },
  mount(){askList();if(String((MIC.s.cfg.film||{}).exec)==='cloud')askBrief();},
});

/* ---------- 动作 ---------- */
const padOk=r=>r&&r.ok;
function toastErr(r,def){MIC.toast((r&&r.msg)||def);}

MIC.film={
  paint,
  useWfDefault(){MIC.form.commitPath('cloud.workflow','');MIC.render();},
  refresh(){askList(true);},
  setDur(v){
    MIC.form.commitPath('film.total',+v||60);
    MIC.render();
  },
  plan(){
    if(planning||MIC.s.st.running)return;
    if(!MIC.s.st.ai_key){
      MIC.toast('先在设置页填文本 API Key');MIC.nav.goto('settings');return;
    }
    const patch=MIC.form.commit();
    const f=Object.assign({},MIC.s.cfg.film||{},patch.film||{});
    if(String(f.story||'').trim().length<4){MIC.toast('先写一段剧情');return;}
    planning=true;
    MIC.toast('AI 拆分镜中…');
    MIC.api.filmPlan(f).then(r=>{
      planning=false;
      if(!padOk(r)){toastErr(r,'拆分镜失败');return;}
      plan={title:r.title||'未命名短剧',
        shots:(r.shots||[]).map(normPlanShot),
        shot_sec:r.shot_sec||shotSec(),total_sec:r.total_sec||0,
        sig:inputSig()};
      MIC.render();
      MIC.toast('已拆成 '+(r.count||plan.shots.length)+' 段');
    }).catch(e=>{planning=false;MIC.toast('拆分镜失败：'+(e&&e.message||e));});
  },
  edit(i,v){
    if(plan&&plan.shots[i])plan.shots[i].prompt=String(v||'');
  },
  polish(i){
    if(!plan||!plan.shots[i])return;
    const sh=plan.shots[i];
    const ta=document.querySelector(`#view textarea[data-shot="${i}"]`);
    const t=String(ta&&ta.value||sh.prompt||'').trim();
    if(!t){MIC.toast('这一段还没有描述');return;}
    if(!MIC.s.st.ai_key){
      MIC.toast('先在设置页填文本 API Key');MIC.nav.goto('settings');return;
    }
    MIC.toast('润色中…');
    MIC.api.aiPolish(t,'video').then(r=>{
      if(!padOk(r)){toastErr(r,'润色失败');return;}
      if(!plan||plan.shots.indexOf(sh)<0)return;   // 等回包时这一段被删了
      sh.prompt=r.text;
      if(ta&&ta.isConnected)ta.value=r.text;
      MIC.toast('第 '+(plan.shots.indexOf(sh)+1)+' 段已润色');
    }).catch(e=>MIC.toast('润色失败：'+(e&&e.message||e)));
  },
  /* 只重写这一段：把剧情和前后镜一起给模型，改完仍留在分镜表里 */
  regen(i){
    if(regenBusy||!plan||!plan.shots[i])return;
    const patch=MIC.form.commit();
    const f=Object.assign({},MIC.s.cfg.film||{},patch.film||{});
    if(String(f.story||'').trim().length<4){MIC.toast('先在左边写一段剧情');return;}
    if(!MIC.s.st.ai_key){
      MIC.toast('先在设置页填文本 API Key');MIC.nav.goto('settings');return;
    }
    syncRows();
    const sh=plan.shots[i],prev=plan.shots[i-1],next=plan.shots[i+1];
    if(String(sh.prompt||'').trim()&&
       !confirm('重写第 '+(i+1)+' 段？这一段现在的描述会被替换。'))return;
    regenBusy=true;MIC.toast('AI 重写第 '+(i+1)+' 段…');
    const ctx=x=>x?{summary:String(x.summary||''),prompt:String(x.prompt||'')}:null;
    MIC.api.filmShotAi({
      index:i,count:plan.shots.length,seconds:+sh.seconds||shotSec(),
      story:String(f.story||''),style:String(f.style||''),size:String(f.size||''),
      shot:+f.shot||shotSec(),summary:String(sh.summary||''),
      prompt:String(sh.prompt||''),prev:ctx(prev),next:ctx(next),
    }).then(r=>{
      regenBusy=false;
      if(!padOk(r)){toastErr(r,'重写失败');return;}
      /* 写回按段对象找位置：等回包期间用户可能删了别的段，下标已经变了 */
      const at=plan?plan.shots.indexOf(sh):-1;
      if(at<0)return;
      sh.prompt=String(r.prompt||sh.prompt||'');
      if(r.summary)sh.summary=String(r.summary);
      if(r.seconds)sh.seconds=+r.seconds;
      MIC.render();
      MIC.toast('第 '+(at+1)+' 段已重写');
    }).catch(e=>{regenBusy=false;MIC.toast('重写失败：'+(e&&e.message||e));});
  },
  /* 删除这一段：只改当前分镜表，序号按剩下的重排；至少留一段 */
  drop(i){
    if(!plan||!plan.shots[i])return;
    if(plan.shots.length<=1){MIC.toast('至少留一段，不能全删');return;}
    syncRows();
    const sh=plan.shots[i];
    const name=String(sh.summary||sh.prompt||'').slice(0,16)||('第 '+(i+1)+' 段');
    if(!confirm('删除「'+name+'」？后面的分镜会依次前移。'))return;
    plan.shots.splice(i,1);
    if(plan.shot_sec)plan.total_sec=plan.shots.length*plan.shot_sec;
    MIC.render();
    MIC.toast('已删除，还剩 '+plan.shots.length+' 段');
  },
  shots(){
    if(!plan)return [];
    syncRows();
    return plan.shots.map((sh,i)=>({i:i+1,summary:sh.summary||'',
      prompt:sh.prompt||'',seconds:+sh.seconds||shotSec()}));
  },
  start(){
    if(firing)return;
    const patch=MIC.form.commit();
    const f=Object.assign({},MIC.s.cfg.film||{},patch.film||{});
    const cloud=String(f.exec)==='cloud',c=MIC.s.st.cloud||{};
    if(cloud?c.run:MIC.s.st.running)return;
    if(cloud&&!refsNow().length){MIC.toast('云端按参考生成：先选一张参考图');return;}
    if(cloud&&isFile()&&wfChk&&!wfChk.ok){MIC.toast(wfChk.msg||'这份工作流有问题');return;}
    const rows=this.shots();
    if(plan&&planStale()&&
       !confirm('剧情或时长改过，当前分镜还是上一版拆的。继续用这份分镜出片？'))return;
    if(!rows.length&&String(f.story||'').trim().length<4){
      MIC.toast('先写一段剧情，或先点「AI 拆分镜」');return;
    }
    if(!rows.length&&!MIC.s.st.ai_key){
      MIC.toast('没有分镜时要 AI 拆：先在设置页填文本 API Key');
      MIC.nav.goto('settings');return;
    }
    firing=true;
    MIC.api.filmStart(Object.assign({shots:rows,title:plan?plan.title:''},f)).then(r=>{
      firing=false;
      if(!padOk(r)){
        if(String(f.exec)==='cloud'&&isFile())askWfCheck(true);
        toastErr(r,'成片没起来');return;
      }
      if(String(r.exec)==='cloud')
        MIC.s.st.cloud=Object.assign({},MIC.s.st.cloud||{},{run:'film',task:'成片',
          status:'准备中…',done:0,total:r.shots||rows.length,elapsed:0,last_fail:''});
      else{
        MIC.s.st.running='film';
        MIC.s.st.status='准备中…';
      }
      askList(true);
      MIC.toast('开始 · '+(r.shots||rows.length)+' 段 · 预计 '+(r.estimate||'—'));
      MIC.render();
    }).catch(e=>{firing=false;MIC.toast('启动失败：'+(e&&e.message||e));});
  },
  stop(){
    MIC.api.filmStop().then(r=>{
      if(!padOk(r))toastErr(r,'成片没在跑');
      else MIC.toast('正在停：当前段收尾后结束');
    }).catch(()=>MIC.toast('停止失败'));
  },
  resume(dir){
    const cloud=String(((MIC.s.st.film||{}).exec))==='cloud';
    if(cloud?((MIC.s.st.cloud||{}).run):MIC.s.st.running)return;
    MIC.toast('继续中…');
    MIC.api.filmResume(dir||'').then(r=>{
      if(!padOk(r)){toastErr(r,'没能继续');return;}
      if(r.msg)MIC.toast(r.msg);
      if(!r.film){
        if(String(r.exec)==='cloud')
          MIC.s.st.cloud=Object.assign({},MIC.s.st.cloud||{},{run:'film',task:'成片',
            status:'准备中…',done:0,total:0,elapsed:0,last_fail:''});
        else MIC.s.st.running='film';
      }
      askList(true);
      MIC.render();
    }).catch(e=>MIC.toast('继续失败：'+(e&&e.message||e)));
  },
  merge(dir){
    if(MIC.s.st.running)return;
    MIC.api.filmMerge(dir||'').then(r=>{
      if(!padOk(r)){toastErr(r,'没能合成');return;}
      MIC.s.st.running='film_merge';
      MIC.toast('合成中…');
      MIC.render();
    }).catch(e=>MIC.toast('合成失败：'+(e&&e.message||e)));
  },
  redo(i){
    const fs=MIC.s.st.film||{};
    if(fs.state==='running'||fs.state==='planning')return;
    const chain=fs.mode==='chain';
    const msg=chain
      ?'接帧模式下重出第 '+i+' 段会作废它和后面所有段（画面要重新接）。继续？'
      :'重出第 '+i+' 段？只跑这一段，别的段和浏览器不动。';
    if(!confirm(msg))return;
    MIC.api.filmRedo(i,chain).then(r=>{
      if(!padOk(r)){toastErr(r,'没能重出');return;}
      if(String(r.exec||fs.exec)==='cloud')
        MIC.s.st.cloud=Object.assign({},MIC.s.st.cloud||{},{run:'film',task:'成片',
          status:'准备中…',done:0,total:0,elapsed:0,last_fail:''});
      else MIC.s.st.running='film';
      if(r.msg)MIC.toast(r.msg);
      askList(true);
      MIC.render();
    }).catch(e=>MIC.toast('重出失败：'+(e&&e.message||e)));
  },
  redoFailed(){
    const fs=MIC.s.st.film||{};
    if(fs.state==='running'||fs.state==='planning')return;
    const miss=+fs.missing||0;
    if(!miss){MIC.toast('没有没出成的段');return;}
    const deep=fs.mode==='chain';
    if(!confirm('重出 '+miss+' 段没出成的？'+
       (deep?'接帧会从最早失败那段往后一起重接。':'只跑这几段，别的段和浏览器不动。')))return;
    MIC.api.filmRedoFailed().then(r=>{
      if(!padOk(r)){toastErr(r,'没能重出');return;}
      if(String(r.exec||fs.exec)==='cloud')
        MIC.s.st.cloud=Object.assign({},MIC.s.st.cloud||{},{run:'film',task:'成片',
          status:'准备中…',done:0,total:0,elapsed:0,last_fail:''});
      else MIC.s.st.running='film';
      if(r.msg)MIC.toast(r.msg);
      askList(true);
      MIC.render();
    }).catch(e=>MIC.toast('重出失败：'+(e&&e.message||e)));
  },
  openShot(i){
    const fs=MIC.s.st.film||{};
    const sh=(fs.shots||[]).filter(x=>x.i===i)[0];
    if(!sh)return;
    if(sh.file_abs){MIC.api.openPath(sh.file_abs);return;}
    if(sh.frame_abs)MIC.api.openPath(sh.frame_abs);
  },
  openFilm(){
    const p=(MIC.s.st.film||{}).film;
    if(p)MIC.api.openPath(p);else MIC.toast('还没有成片');
  },
  openDir(){
    const d=(MIC.s.st.film||{}).dir;
    if(d)MIC.api.openPath(d);else MIC.toast('还没有工程目录');
  },
  resumeAt(i){const it=projects[i];if(it)this.resume(it.dir);},
  mergeAt(i){const it=projects[i];if(it)this.merge(it.dir);},
  openAt(i){const it=projects[i];if(it&&it.film)MIC.api.openPath(it.film);},
  /* 小叉号删工程：整个目录搬进回收目录（不是硬删），所以先问一句 */
  delAt(i){
    const it=projects[i];if(!it)return;
    const t=it.title||it.id;
    if(!confirm('删掉工程「'+t+'」？分镜和已出的段一起搬走，回收目录里还留几天。'))return;
    MIC.api.filmDelete(it.dir).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'删除失败');return;}
      projects=projects.filter(x=>x.dir!==it.dir);
      MIC.render();
      MIC.toast('已删工程：'+t);
    }).catch(()=>MIC.toast('删除失败'));
  },
};

/* 生图/视频页的「AI 润色」：取当前那格的文字，交给文本 API 按专业构图语言重写。
   只写回这一格并落盘；写回前不动别的设置，失败也保留原文。 */
MIC.polish={
  prompt(key,kind){
    const el=document.querySelector(`#view [data-k="${key}"]`);
    const t=String(el&&el.value||'').trim();
    if(!t){MIC.toast('先写一句提示词');return;}
    if(!MIC.s.st.ai_key){
      MIC.toast('先在设置页填文本 API Key');MIC.nav.goto('settings');return;
    }
    MIC.toast('润色中…');
    MIC.api.aiPolish(t,kind==='video'?'video':'image').then(r=>{
      if(!padOk(r)){toastErr(r,'润色失败');return;}
      if(el)el.value=r.text;
      MIC.form.commitPath(key,r.text);
      MIC.toast('已润色并保存');
    }).catch(e=>MIC.toast('润色失败：'+(e&&e.message||e)));
  },
};
})();
