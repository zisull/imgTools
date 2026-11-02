/* core/form.js —— 表单构件 + 双向绑定：控件带 data-k="rfq.pages"，改完自动写回配置 */
(function(){
const MIC=window.MIC=window.MIC||{};
const esc=MIC.esc, ic=MIC.ic;

/* ---------- 构件 ---------- */
/* 说明语一律做成悬浮提示（挂在标签上）：摆在明面上每页要多占一行，
   而真正需要解释的控件是少数——鼠标停一下就能看到，界面本身干净得多。 */
function field(label,control,hint){
  return `<div class="f"><label${hint?` class="tip" title="${esc(hint)}"`:''}>${label}</label>`+
    `<div class="c">${control}</div></div>`;
}
function card(title,iconName,body,opts){
  const o=opts||{};
  return `<section class="card ${o.cls||''}">
    <header class="card-h"${o.tip?` title="${esc(o.tip)}"`:''}>${ic(iconName)}<h2>${title}</h2>
      ${o.note?`<span class="note">${o.note}</span>`:''}
      <span class="grow"></span>${o.actions||''}</header>
    <div class="card-b${o.tight?' tight':''}">${body}</div></section>`;
}
/* 卡片里的折叠块：只是分隔线 + 一行标题，不再套一层卡片（嵌套边框是最显乱的来源） */
function fold(title,iconName,body,note){
  return `<div class="fold">
    <div class="fold-h closed" onclick="MIC.form.foldToggle(this)">
      ${ic('chev')}${ic(iconName,'s')}<span>${title}</span><span class="hint">${note||''}</span></div>
    <div class="fold-b hide">${body}</div></div>`;
}
function foldcard(title,iconName,body,note){
  return `<section class="card"><div class="fold flat">
    <div class="fold-h closed" onclick="MIC.form.foldToggle(this)">
      ${ic('chev')}${ic(iconName,'s')}<span>${title}</span><span class="hint">${note||''}</span></div>
    <div class="fold-b hide">${body}</div></div></section>`;
}
/* 运行卡下半截：状态灯 + 进度这两行在各页完全同构，只差最后一行统计，
   所以收成一个 helper；按钮行各页不一样，仍由调用方自己拼。 */
function strow(k,inner){return `<div class="strow"><span class="k">${k}</span>${inner}</div>`;}
/* 双栏页构件：左主右辅。生成页=左参数右运行预览；环境页=左千问右Moss；设置页同理。
   窄窗口自动落回单列（见 base.css .duo 媒体查询）。cls 传 'eq' 让左右等宽（双分区对比用）。 */
function duo(left,right,cls){
  return `<div class="duo${cls?' '+cls:''}"><div class="duo-m">${left}</div><div class="duo-s">${right}</div></div>`;
}
function runstat(run,extra){
  return `<div class="status" style="margin-top:10px">${
    strow('任务状态',`<span class="dot ${run?'run':''}" data-role="dot"></span><span data-role="st"></span>`)+
    strow('进度',`<div class="prog"><i data-role="prog"></i></div><span class="mut fine" data-role="pgtext"></span>`)+
    (extra||'')}</div>`;
}
function txt(k,ph,cls,rr){
  /* rr：这一格改完整页重画（工作流那格填没填决定云端那条路通不通，提醒要跟着当场收走） */
  return `<input class="inp ${cls||''}"${rr?' data-rr="1"':''} data-k="${k}" value="${esc(MIC.mget(MIC.s.cfg,k))}" placeholder="${esc(ph||'')}">`;
}
/* 多行输入（提示词这类）：data-k 绑定与 txt 同一套 */
function ta(k,rows,ph){
  return `<textarea class="inp" data-k="${k}" rows="${rows||3}" placeholder="${esc(ph||'')}">${esc(MIC.mget(MIC.s.cfg,k))}</textarea>`;
}
function num(k,unit){
  return `<div class="numw"><input class="inp w" data-k="${k}" data-t="num" value="${esc(MIC.mget(MIC.s.cfg,k))}">${unit?`<span class="unit">${unit}</span>`:''}</div>`;
}
/* 种子：随机/指定做成一下点得动的开关——为了随机去敲 -1 太别扭了。
   随机=配置里存 -1（后端每轮换一个全新种子，张张不同）；
   指定=沿用这次界面里输过的数值（seedKeep 只活在内存，不落配置）。
   随机态下输入框摘掉 data-k：否则 read() 会把空框读成 0，把随机顶掉。 */
const seedKeep={};
function seedRow(k){
  const v=parseInt(MIC.mget(MIC.s.cfg,k),10);
  const rand=!(v>=0);
  return `<div class="seedw${rand?' off':''}" data-sk="${k}">
    <div class="sw${rand?' on':''}" title="开=每次换一张新图；关=固定种子，同样的参数复现同样的图"></div>
    <span class="unit">随机</span>
    <input class="inp w" data-t="num" data-k="${rand?'':k}" value="${rand?'':esc(v)}"${rand?' inert':''}
      placeholder="种子数"></div>`;
}
function seedMode(box,rand){
  const k=box.dataset.sk,inp=box.querySelector('input');
  box.classList.toggle('off',rand);
  box.querySelector('.sw').classList.toggle('on',rand);
  inp.toggleAttribute('inert',rand);
  inp.dataset.k=rand?'':k;
  if(rand)inp.value='';
  else if(inp.value===''||inp.value=='-1')inp.value=seedKeep[k]!=null&&seedKeep[k]!==''?seedKeep[k]:'0';
}
function seedFlip(box){
  const k=box.dataset.sk,toRand=!box.classList.contains('off');
  if(toRand)seedKeep[k]=box.querySelector('input').value;
  seedMode(box,toRand);
  commitPath(k,toRand?-1:parseInt(box.querySelector('input').value,10)||0);
}
function sel(k,list,ph){
  const v=MIC.mget(MIC.s.cfg,k);
  let h=`<select class="inp" data-k="${k}">`;
  if(ph!==undefined)h+=`<option value=""${!v?' selected':''}>${esc(ph)}</option>`;
  list.forEach(o=>{
    const name=o.name!=null?o.name:o, code=o.code!=null?o.code:o;
    h+=`<option value="${esc(code)}"${String(code)===String(v)?' selected':''}>${esc(name)}</option>`;
  });
  /* 配置里这个值不在档位表里（老配置、别的机器带回来的、后端补的默认值）：
     一条都不选中的话浏览器就默认亮第一项，下一次整屏 read() 把第一项写回配置——
     用户的值被无声换掉了。补一项留在表里，和尺寸那条「历史自定义」同一套路。 */
  if(v!==''&&v!=null&&!list.some(o=>String(o.code!=null?o.code:o)===String(v)))
    h+=`<option value="${esc(v)}" selected>${esc(v)}（原值）</option>`;
  return h+'</select>';
}
function chk(k,label){
  return `<label class="chk ${MIC.mget(MIC.s.cfg,k)?'on':''}" data-k="${k}"><i>${ic('check')}</i>${label}</label>`;
}
function sw(k){
  return `<div class="sw ${MIC.mget(MIC.s.cfg,k)?'on':''}" data-k="${k}"></div>`;
}
/* rr=true：这一档一改整页布局都要跟着变（如「输出格式」切透明），点完重画一次 */
function seg(k,items,rr){
  const v=String(MIC.mget(MIC.s.cfg,k));
  return `<div class="seg"${rr?' data-rr="1"':''} data-k="${k}">${items.map(([val,label])=>
    `<button class="${val===v?'on':''}" data-v="${esc(val)}">${label}</button>`).join('')}</div>`;
}
function pathrow(k,ph,pickKind,rr){
  /* 类名别叫 path：nav.css 里的 .path 是给侧栏面包屑的（max-width:88px;flex:none），
     挂到输入框上会把目录路径压成「D:/AI/Qwe…」，也长不大 */
  return `<div class="inrow dropz" data-into="${k}" data-drop="${pickKind||'file'}"
      title="可以直接把文件从资源管理器拖进来">${txt(k,ph,'fpath',rr)}
    <button class="btn" onclick="MIC.form.pickInto('${k}','${pickKind}')">浏览</button></div>`;
}
/* 尺寸/画幅下拉：三个出图页各有一份档位表，构件只有一个 sizeSel，
   档位表由各页给（两台模型的可用尺寸本来就不一样）。
   rr=true：选「自定义」要当场多出宽高输入框，选完重画一次。 */
function sizeSel(k,list,dis,rr){
  const v=String(MIC.mget(MIC.s.cfg,k));
  /* 画廊回填的可能是档位表外的历史自定义尺寸（960x704 这类）：
     不补一个选项的话下拉会空着，看起来像没选上 */
  const extra=(!list.some(o=>o.code===v)&&/^\d+x\d+$/.test(v))
    ?`<option value="${esc(v)}" selected>${esc(v)}（历史自定义）</option>`:'';
  return `<select class="inp" data-k="${k}"${rr?' data-rr="1"':''}>${list.map(o=>
      `<option value="${esc(o.code)}"${o.code===v?' selected':''}>${esc(o.name)}</option>`).join('')}${extra}${
      dis?`<option value="" disabled>${esc(dis)}</option>`:''}</select>`;
}

/* ---------- P 档分辨率 ----------
   P 数只认短边：横版=16:9、方形=1:1、竖版=9:16，所以同一个 720P
   在横版是 1280×720、竖版是 720×1280。宽高统一贴 16 的倍数，
   与 Moss/ComfyUI 的 latent 网格一致；老配置的 WxH 原样保留成「历史尺寸」。 */
const P_ASPECT={h:[16,9],s:[1,1],v:[9,16]};
const P_ORIENT=[['h','横版'],['s','方形'],['v','竖版']];
const P_IMG=[480,512,720,768,1024];
const P_VIDEO=[480,640,720,768];
/* 云端那一路的档位只受平台收不收限：最高 2K＝短边 1440（长边 2560）。
   本地那条仍停在 768——权重是 768P 训的，再往上是拿算法放大，不值那几分钟。 */
const P_VIDEO_CLOUD=[480,640,720,768,1024,1080,1440];
function a16(x){return Math.max(16,Math.min(4096,Math.round(Number(x||0)/16)*16));}
function pDims(p,o){
  const a=P_ASPECT[o]||P_ASPECT.s;
  const pn=Math.max(16,Math.round(Number(p)||1024));
  const long=a16(pn*Math.max(a[0],a[1])/Math.min(a[0],a[1]));
  /* 两边各自贴 16，和后端 _h3_size 同一套：1080 不是 16 的倍数 → 1088，
     长边仍按 1920 贴（别拿贴过的 1088 再去推长边，会推出 1936 这种没人认的数） */
  return a[0]>=a[1]?{w:long,h:a16(pn)}:{w:a16(pn),h:long};
}
function orientOf(w,h){
  const r=Math.log((Number(w)||1)/(Number(h)||1));
  let best='s',bd=1e9;
  Object.keys(P_ASPECT).forEach(o=>{
    const a=P_ASPECT[o],d=Math.abs(Math.log(a[0]/a[1])-r);
    if(d<bd){bd=d;best=o;}
  });
  return best;
}
function pairOf(v,cw,ch){
  const m=/^(\d+)x(\d+)$/i.exec(String(v||''));
  if(m)return {w:+m[1],h:+m[2],custom:false};
  return {w:Number(cw)||1024,h:Number(ch)||1024,custom:true};
}
function pOf(n,list){
  let best=list[0],bd=1e9;
  list.forEach(p=>{const d=Math.abs(p-Number(n||0));if(d<bd){bd=d;best=p;}});
  return best;
}
function pLabel(p,w,h){return p+'P : '+w+' × '+h;}
/* 两件套：左边选 P（选项里直接写当前朝向的真实分辨率），右边选横/方/竖。
   朝向不单独存配置，由当前 WxH 反推；换朝向就把 size 改写成新的 WxH。
   某一路模型有「原生画幅」（H3 的 768P 是 1344×768，不是按 16 取整的 1360）时，
   由那一页登记一个 dimSnap：下拉里写的、换朝向写回的、后端算的都是同一套数。 */
function pSizeSel(k,list,opts){
  const o=opts||{},v=String(MIC.mget(MIC.s.cfg,k)||'');
  const dimOf=MIC.form.dimSnap[k]||pDims;
  const cwKey=o.cw||'',chKey=o.ch||'';
  const cw=cwKey?Number(MIC.mget(MIC.s.cfg,cwKey))||1024:1024;
  const ch=chKey?Number(MIC.mget(MIC.s.cfg,chKey))||1024:1024;
  const cur=pairOf(v,cw,ch);
  const orient=orientOf(cur.w,cur.h);
  const rows=list.map(p=>{const d=dimOf(p,orient);return {code:d.w+'x'+d.h,label:pLabel(p,d.w,d.h)};});
  let extra='';
  if(v&&v!=='custom'&&!rows.some(x=>x.code===v)){
    /* 画廊回填/老配置：P 数按短边显示，尺寸保持原样，不替用户改 */
    extra=`<option value="${esc(v)}" selected>${esc(pLabel(Math.min(cur.w,cur.h),cur.w,cur.h))}</option>`;
  }
  const custom=o.custom===false?'':`<option value="custom"${v==='custom'?' selected':''}>自定义宽 × 高</option>`;
  const ori=P_ORIENT.map(([code,label])=>
    `<option value="${code}"${code===orient?' selected':''}>${label}</option>`).join('');
  return `<div class="ppick">
    <select class="inp" data-k="${esc(k)}" data-rr="1">${rows.map(x=>
      `<option value="${esc(x.code)}"${x.code===v?' selected':''}>${esc(x.label)}</option>`).join('')}${extra}${custom}</select>
    <select class="inp pangle" data-ori="${esc(k)}" data-cw="${esc(cwKey)}" data-ch="${esc(chKey)}"
      data-plist="${list.join(',')}"${v==='custom'?' disabled':''}>${ori}</select>
  </div>`;
}
function pickOrientation(el){
  const k=el.dataset.ori;if(!k)return;
  const raw=String(MIC.mget(MIC.s.cfg,k)||'');
  const cw=el.dataset.cw?MIC.mget(MIC.s.cfg,el.dataset.cw):null;
  const ch=el.dataset.ch?MIC.mget(MIC.s.cfg,el.dataset.ch):null;
  const cur=pairOf(raw,cw,ch);
  const list=String(el.dataset.plist||'').split(',').map(Number).filter(Boolean);
  const p=pOf(Math.min(cur.w,cur.h),list.length?list:P_IMG);
  const d=(MIC.form.dimSnap[k]||pDims)(p,el.value);
  /* 一次读完整屏、只落一次盘：分两次保存的话，先发的旧尺寸回包可能把新值又盖回去 */
  const patch=read();
  MIC.mset(patch,k,d.w+'x'+d.h);
  merge(patch);
  saved(patch);
  MIC.render();
}
/* 任务跑着的时候参数改不动（与桌面版禁用控件同义）：inert 挡键盘，dis 挡鼠标 */
function lock(run,inner){
  return `<div class="lockw${run?' dis':''}"${run?' inert':''}>${inner}</div>`;
}

/* ---------- 取值 / 写回 ---------- */
/* 后端保存后会回一份完整配置（换类别会改起始页码、抓取中会推进页码），
   前端必须换成这份，否则下一次提交会把旧值写回去。default_nav 只在内存，保留。 */
function applyCfg(c){
  if(!c)return;
  const dn=MIC.s.cfg&&MIC.s.cfg.default_nav;
  MIC.s.cfg=c;
  if(dn)MIC.s.cfg.default_nav=dn;
}
/* 把界面上的控件对齐到 MIC.s.cfg：正在输入的不打断 */
function syncFields(){
  document.querySelectorAll('#view [data-k]').forEach(el=>{
    const k=el.dataset.k;if(!k)return;
    const v=MIC.mget(MIC.s.cfg,k);
    if(el.classList.contains('chk')||el.classList.contains('sw')){el.classList.toggle('on',!!v);return;}
    if(el.classList.contains('seg')){
      el.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.v===String(v)));return;
    }
    if(el===document.activeElement)return;
    const nv=v==null?'':String(v);
    /* 判的是「这张表里有没有这一项」，不是「有没有取到值」：
       写成 some(x=>x.value) 永远返回 true（选项值都是非空串），
       于是每轮同步都给每个下拉补一条重复的「（原值）」——档位看着像被改过。 */
    const has=!!nv&&[].some.call(el.options,x=>x.value===nv);
    if(el.tagName==='SELECT'&&nv&&!has){
      /* 回填或老配置给的是这张档位表里没有的值：补一项留在下拉里。
         缩成空白的话，下一次整屏 read() 会把空串写回配置，用户的档位就被无声换掉了。 */
      const op=document.createElement('option');
      op.value=nv;op.textContent=nv+'（原值）';el.appendChild(op);
    }
    if(el.value!==nv)el.value=nv;
  });
  /* 种子那一行是开关+输入框两件套：画廊回填/后端回包把值换成具体数字时，
     开关也要跟着落到「指定」，不然界面显示随机、实际发的是那个数 */
  document.querySelectorAll('#view .seedw').forEach(box=>{
    const v=parseInt(MIC.mget(MIC.s.cfg,box.dataset.sk),10);
    if(box.querySelector('input')===document.activeElement)return;
    seedMode(box,!(v>=0));
  });
  document.querySelectorAll('#view select[data-ori]').forEach(el=>{
    const k=el.dataset.ori;
    const raw=String(MIC.mget(MIC.s.cfg,k)||'');
    const cw=el.dataset.cw?MIC.mget(MIC.s.cfg,el.dataset.cw):null;
    const ch=el.dataset.ch?MIC.mget(MIC.s.cfg,el.dataset.ch):null;
    const cur=pairOf(raw,cw,ch);
    const o=orientOf(cur.w,cur.h);
    if(el.value!==o)el.value=o;
    el.disabled=raw==='custom';
  });
}
function saved(patch){
  MIC.api.save(patch).then(r=>{
    if(!r||!r.cfg)return;
    applyCfg(r.cfg);
    /* 后端会改起始页码/剩余页数（换类别回填、抓取中推进），控件要跟着对齐 */
    syncFields();
  }).catch(()=>{});
}
function valOf(el){
  if(el.classList.contains('chk')||el.classList.contains('sw'))return el.classList.contains('on');
  if(el.classList.contains('seg')){const b=el.querySelector('button.on');return b?b.dataset.v:'';}
  const raw=el.value;
  if(el.dataset.t==='num'){const n=parseFloat(raw);return isNaN(n)?0:n;}
  return raw;
}
function read(){
  const patch={};
  document.querySelectorAll('#view [data-k]').forEach(el=>{
    const k=el.dataset.k;if(!k)return;
    MIC.mset(patch,k,valOf(el));
  });
  return patch;
}
function commitPath(k,v){
  MIC.mset(MIC.s.cfg,k,v);
  const patch={};MIC.mset(patch,k,v);
  saved(patch);
}
/* 一次改多个键（品类下拉要同时写 cat/excat/cat_name），只落盘一次 */
function commitMany(pairs){
  const patch={};
  Object.keys(pairs).forEach(k=>{MIC.mset(MIC.s.cfg,k,pairs[k]);MIC.mset(patch,k,pairs[k]);});
  saved(patch);
}
function commit(){
  const patch=read();
  if(!Object.keys(patch).length)return patch;
  merge(patch);
  saved(patch);
  return patch;
}
function merge(patch){
  Object.keys(patch).forEach(k=>{
    const v=patch[k];
    if(v&&typeof v==='object'&&!Array.isArray(v)){
      if(typeof MIC.s.cfg[k]!=='object'||MIC.s.cfg[k]===null)MIC.s.cfg[k]={};
      mergeInto(MIC.s.cfg[k],v);
    }else MIC.s.cfg[k]=v;
  });
}
function mergeInto(t,s){
  Object.keys(s).forEach(k=>{
    if(s[k]&&typeof s[k]==='object'&&!Array.isArray(s[k])){
      if(typeof t[k]!=='object'||t[k]===null)t[k]={};mergeInto(t[k],s[k]);
    }else t[k]=s[k];
  });
}
function pickInto(k,kind){
  MIC.api.pick(kind).then(p=>{
    if(!p)return;
    MIC.mset(MIC.s.cfg,k,p);
    const el=document.querySelector(`#view [data-k="${k}"]`);if(el)el.value=p;
    commitPath(k,p);
    rrRepaint(el);
  }).catch(()=>{});
}
/* data-rr 的格子改完要整页重画：工作流填成本地文件时，「宿主页」那格得当场长出来 */
function rrRepaint(el){if(el&&el.dataset&&el.dataset.rr)MIC.render();}
/* 事件委托：文本/下拉 change 即存；勾选/开关/分段 click 即存 */
document.addEventListener('change',e=>{
  const ori=e.target.closest?e.target.closest('#view select[data-ori]'):null;
  if(ori){pickOrientation(ori);return;}
  const el=e.target.closest?e.target.closest('#view [data-k]'):null;
  if(!el||el.classList.contains('chk')||el.classList.contains('sw')||el.classList.contains('seg'))return;
  /* data-rr 的下拉（尺寸选「自定义」）改完整页重画：先 commit 收下这一屏的字 */
  if(el.dataset.rr){commit();MIC.render();return;}
  commitPath(el.dataset.k,valOf(el));
});
document.addEventListener('click',e=>{
  const btn=e.target.closest?e.target.closest('.seg[data-k] button'):null;
  if(btn){
    const box=btn.parentElement;
    box.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b===btn));
    /* 带 data-rr 的那档改完要整页重画：先 commit 把这一屏的输入全收下
       （只落一个 mode 键的话，重画会把没blur的提示词框画回上次的旧值）；
       环境开关这类还会动导航树，applyMode 先把可见页修好再重画主区 */
    if(box.dataset.rr){
      /* fit：这一页可以登记「切完顺手校正别的键」的规则（视频页换通道要把清晰度收进档位表），
         校正落在同一个 patch 里只写一次盘——分两次存的话，先发的旧回包可能把新值盖回去 */
      const patch=read();
      const fit=MIC.form.segFit&&MIC.form.segFit[box.dataset.k];
      if(fit)fit(btn.dataset.v,patch);
      merge(patch);saved(patch);
      if(MIC.nav&&MIC.nav.applyMode)MIC.nav.applyMode();
      MIC.render();
    }else commitPath(box.dataset.k,btn.dataset.v);
    return;
  }
  /* 种子的随机开关没有 data-k（避免和下面的通用开关逻辑撞车），单独接 */
  const sd=e.target.closest?e.target.closest('#view .seedw .sw'):null;
  if(sd){seedFlip(sd.parentElement);return;}
  const t=e.target.closest?e.target.closest('#view .chk[data-k],#view .sw[data-k]'):null;
  if(t){t.classList.toggle('on');commitPath(t.dataset.k,t.classList.contains('on'));}
});
/* ---------- 拖文件进来填路径 ----------
   只有 .dropz（文件路径格）接住，其余位置一律 preventDefault：
   浏览器默认「拖文件=打开文件」会把整页换掉，跑一半的状态当场就没。 */
function dropCands(dt){
  const full=[],names=[];
  const fl=dt.files||[];
  for(let i=0;i<fl.length;i++){
    if(fl[i].path)full.push(fl[i].path);       // 有的内核给得出完整路径
    if(fl[i].name)names.push(fl[i].name);      // 只给得出文件名时交给后端去找
  }
  ['text/uri-list','DownloadURL','text/plain'].forEach(t=>{
    let v='';try{v=dt.getData(t);}catch(e){}
    if(v)v.split(/\r?\n/).forEach(s=>full.push(s));
  });
  const clean=a=>a.map(s=>String(s||'').trim()).filter(Boolean);
  /* 完整路径排在前面：只剩文件名的兜底会在输出目录/桌面/下载里按名字找，
     排前面可能撞上同名不同目录的另一张图 */
  return clean(full).concat(clean(names)).slice(0,8);
}
function zones(keep){
  document.querySelectorAll('.dropz.over').forEach(x=>{if(x!==keep)x.classList.remove('over');});
}
/* 拖放统一出口：先按路径解析；WebView2 只给得出文件名时（拿不到完整路径），
   把字节读成 dataURL 交后端代收落盘，别让「拖了没反应」变成死路。 */
function resolveDrop(dt,kind){
  const cands=dropCands(dt);
  const f=(dt&&dt.files&&dt.files[0])||null;
  if(kind==='dir'||!f)
    return MIC.api.dropPath(cands,kind);
  return MIC.api.dropPath(cands,kind).then(r=>{
    if(r&&r.ok)return r;
    if(f.size>40*1048576)return {ok:false,msg:'这张太大，请用「浏览」选'};
    return new Promise(res=>{
      const fr=new FileReader();
      fr.onload=()=>res(MIC.api.saveDrop(f.name,String(fr.result||'')));
      fr.onerror=()=>res({ok:false,msg:'读文件失败，请用「浏览」选'});
      fr.readAsDataURL(f);
    });
  });
}
document.addEventListener('dragover',e=>{
  if(!e.dataTransfer)return;
  e.preventDefault();
  const z=e.target.closest?e.target.closest('.dropz'):null;
  zones(z);
  if(z)z.classList.add('over');
});
document.addEventListener('dragend',()=>zones());
document.addEventListener('drop',e=>{
  if(!e.dataTransfer)return;
  e.preventDefault();
  const z=e.target.closest?e.target.closest('.dropz'):null;
  zones();
  if(!z)return;
  const k=z.dataset.into;
  resolveDrop(e.dataTransfer,z.dataset.drop||'file').then(r=>{
    if(!r||!r.ok){MIC.toast((r&&r.msg)||'没能识别这个文件');return;}
    const el=document.querySelector(`#view [data-k="${k}"]`);if(el)el.value=r.path;
    commitPath(k,r.path);
    rrRepaint(el);
    MIC.toast('已载入 '+r.path);
  }).catch(err=>MIC.toast('识别失败：'+(err&&err.message||err)));
});

MIC.form={field,card,fold,foldcard,runstat,strow,duo,txt,ta,num,seedRow,sel,chk,sw,seg,pathrow,sizeSel,pSizeSel,lock,read,commit,commitPath,commitMany,pickInto,
  applyCfg,dropCands,resolveDrop,a16,pDims,orientOf,pairOf,pOf,P_IMG,P_VIDEO,P_VIDEO_CLOUD,P_ASPECT,P_ORIENT,
  /* 每页可登记的「原生画幅」换算：键是 size 控件绑的配置路径；segFit 是「切完顺手校正」的规则 */
  dimSnap:{},segFit:{},
  foldToggle(h){h.classList.toggle('closed');h.nextElementSibling.classList.toggle('hide');},
  /* 页面里非 data-k 的临时控件：取值不写配置 */
  raw(id){const el=MIC.$(id);return el?(el.value!=null?el.value.trim():el.textContent):'';},
};
})();
