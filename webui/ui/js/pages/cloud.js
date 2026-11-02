/* pages/cloud.js —— 云端账号：登录一次存成档案，之后换号只换数据
   登录/看平台仍用主窗口那只（一个浏览器 + 多份 cookies/localStorage 快照）；
   成片逐镜要并行时，每个号各起一只独立浏览器（不同端口/profile），跑完就收。
   保活按账号轮着访问平台（并发固定 1），浏览器只管登录，生成仍走协议。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

let data=null, loading=false, last=0;

/* 登录态四态：ok=平台认、expired=掉登录、saved=存过没验证、unknown=没信号 */
const STATE={
  ok:{dot:'ok',txt:'登录有效'},
  expired:{dot:'bad',txt:'登录已失效'},
  saved:{dot:'',txt:'已保存 · 未验证'},
  unknown:{dot:'',txt:'已保存 · 无明确信号'},
  pending:{dot:'',txt:'等待登录'},
  new:{dot:'',txt:'还没保存登录态'},
  error:{dot:'bad',txt:'上次检查出错'},
  fail:{dot:'bad',txt:'出片失败 · 需重新登录或换号'},
};

function byId(id){return (data&&data.accounts||[]).filter(a=>a.id===id)[0]||{};}
/* 浏览器这只窗口当下被谁占着（后端 host.purpose）：保活见到非空闲就让路 */
const BUSY_TXT={login:'登录页开着',gen:'云端出片中',hold:'有人在用'};
/* 云端出片占着同一只浏览器：这期间登录/换号/关浏览器都会把正在跑的号顶掉 */
function runBusy(){return !!((MIC.s.st.cloud||{}).run);}
function locked(){return !!MIC.s.st.cloud_busy||runBusy();}
function stamp(ts){
  const n=Number(ts)||0;if(!n)return '';
  const d=new Date(n*1000),p=x=>String(x).padStart(2,'0');
  return `${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function acctSub(a){
  const s=STATE[a.state]||STATE.new;
  const bits=[s.txt];
  if(a.state==='ok'||a.state==='unknown'||a.state==='expired'||a.state==='fail'){
    if(a.detail)bits.push(a.detail);
    if(a.last_check)bits.push('检查于 '+stamp(a.last_check));
  }
  if(a.last_saved)bits.push('保存于 '+stamp(a.last_saved));
  if(a.has_key)bits.push('有 API Key');
  return bits.join(' · ');
}
function liveSub(){
  const n=(data&&data.accounts||[]).length;
  if(runBusy())return '云端任务在跑 · 账号先别动';
  const busy=MIC.s.st.cloud_busy;
  if(busy)return busy+'…';
  const on=data&&data.browser&&data.browser.on;
  const par=+(data&&data.parallel)||0;
  return n+' 个账号 · '+(on?'浏览器已连':'浏览器未启动')+
    (par>1?' · 成片可 '+par+' 号并行':' · 并发 1');
}

function row(a){
  const s=STATE[a.state]||STATE.new;
  const off=locked()||(data&&data.dp===false);   // 缺浏览器依赖或出片中：登录/保存点不动，档案仍可改名/备份
  return `<div class="mrow">
    <span class="dot ${s.dot}"></span>
    <div class="minfo"><b>${esc(a.name)}</b><span class="mut fine">${esc(acctSub(a))}</span></div>
    <span class="grow"></span>
    <button class="btn sm gho" onclick="MIC.cloud.login('${a.id}')"${off?' disabled':''}>登录</button>
    <button class="btn sm pri" onclick="MIC.cloud.save('${a.id}')"${off?' disabled':''}>保存</button>
    <button class="btn sm" title="更多" onclick="MIC.cloud.more(event,'${a.id}')">${ic('dots','s')}</button>
  </div>`;
}

function createRow(){
  return `<div class="inrow">
      <input id="cloudNewName" class="inp" placeholder="给这次登录起个名（如 主号）"
        onkeydown="if(event.key==='Enter')MIC.cloud.create()">
      <button class="btn pri" onclick="MIC.cloud.create()"${locked()?' disabled':''}>新建登录</button>
    </div>
    <div class="mut fine" style="margin-top:6px">点开后在新窗口里登录；登录完回到这里点「保存」，这个号就留下了。</div>`;
}

function browserCard(){
  const d=data||{}, b=d.browser||{}, k=d.keep||{};
  const busy=locked();
  const cur=byId(b.account);
  const on=!!b.on, noDp=d.dp===false;
  return C.card('浏览器','globe',
    '<div class="status">'+
      C.strow('状态',`<span class="dot ${on?'ok':'off'}"></span><span>${on?'已启动':'未启动'}</span>`)+
      C.strow('调试端口',`<span class="mut">${esc(String(b.port||''))}</span>`)+
      C.strow('当前账号',`<span class="mut">${esc(cur.name||'—')}</span>`)+
      C.strow('保活',`<span class="mut">${esc(k.on?'每 '+(k.min||30)+' 分钟':'关')}${k.msg?' · '+esc(k.msg):''}</span>`)+
      /* 这只窗口现在归谁用：保活看到非「空闲」就让路，登录/出片期间不会被人换号 */
      C.strow('当前用途',`<span class="mut">${esc(BUSY_TXT[k.purpose]||'空闲')}</span>`)+
      C.strow('并发',`<span class="mut">单条视频 1 个号；成片逐镜最多 ${+(data&&data.parallel)||1} 个号并行（每号一只浏览器）</span>`)+
    '</div>'+
    '<div class="btnrow" style="margin-top:10px">'+
      `<button class="btn sm pri" onclick="MIC.cloud.start()"${busy||on||noDp?' disabled':''}>打开平台</button>`+
      `<button class="btn sm gho" onclick="MIC.cloud.checkAll()"${busy||!on?' disabled':''}>立即保活</button>`+
      `<button class="btn sm gho" onclick="MIC.cloud.stop()"${busy||!on?' disabled':''}>关闭浏览器</button>`+
    '</div>'+
    C.field('自动保活',C.sw('cloud.keep'),
      `每 ${k.min||30} 分钟把每个号轮着访问一次平台，把服务端刷新的 cookie 存回去；浏览器没开就跳过`));
}

function page(){
  const d=data, busy=MIC.s.st.cloud_busy;
  if(!d){
    return C.card('账号','globe',
      `<div class="empty">${loading?'正在读账号库…':'还没读到账号库'}</div>`);
  }
  const warn=d.dp?'':
    `<div class="notebar">${ic('tool','s')}<b>缺 DrissionPage</b>`+
    `<span class="grow"></span><button class="btn sm pri" onclick="MIC.env.focus('base')">去基础补</button></div>`;
  /* 出片占着这只浏览器：登录/换号/关窗口都先把话说明白，别让人点了才发现弹回来一句忙 */
  const run=runBusy()?`<div class="notebar">${ic('refresh','s')}
      <b>云端任务在跑 · 登录、换号、关浏览器先等它结束</b>
      <span class="grow"></span><button class="btn sm gho" onclick="MIC.nav.goto('${
        (MIC.s.st.cloud||{}).run==='film'?'film':'video'}')">去看进度</button></div>`:'';
  const rows=(d.accounts||[]).map(row).join('')||
    `<div class="empty">还没有账号 · 上面起个名点「新建登录」</div>`;
  const msg=busy?`<div class="status" style="margin-bottom:8px">${C.strow('进行中',
      `<span class="dot run"></span><span>${esc(busy)}</span>`)}</div>`:
    (d.msg?`<div class="mut fine" style="margin-bottom:8px">${esc(d.msg)}</div>`:'');
  return warn+run+C.duo(
    C.card('账号','globe',msg+createRow()+`<div style="margin-top:10px">${rows}</div>`),
    browserCard());
}

MIC.registerPage('cloud',{
  title:'云端账号',sub:liveSub,icon:'globe',
  render(){return page();},
});

function refresh(){
  if(loading)return Promise.resolve();
  loading=true;
  return MIC.api.cloudState().then(r=>{
    if(r){data=r;last=Date.now();}
  }).catch(()=>{}).then(()=>{
    loading=false;
    if(!onPage())return;
    const a=document.activeElement;
    const typing=a&&/^(INPUT|TEXTAREA)$/.test(a.tagName)&&a.closest&&a.closest('#view');
    if(!typing)MIC.render();
  });
}
function after(r,msg){
  if(r&&!r.ok)MIC.toast(r.msg||'没成功','bad');
  else if(msg)MIC.toast(msg);
  refresh();
  setTimeout(refresh,1200);
}
/* 云端操作是后台线程：busy 期间隔一会儿再读一次，收尾那一刻账号表自己补上。
   这页现在挂在「环境管理 → 云端账号」里，页面键是 env，看子页停在不在这一格。 */
function onPage(){
  if(!MIC.nav)return false;
  const p=MIC.nav.pageOf();
  return p==='cloud'||(p==='env'&&MIC.env&&MIC.env.tabId()==='cloud');
}
setInterval(()=>{
  if(!onPage())return;
  if(loading)return;
  if(MIC.s.st.cloud_busy||Date.now()-last>6000)refresh();
},1500);

MIC.cloud={
  get data(){return data;},
  refresh,
  render:page,
  mount(){
    if(!data||Date.now()-last>6000)refresh();
  },
  create(){
    const el=MIC.$('cloudNewName');
    const name=el?el.value.trim():'';
    if(el)el.value='';
    MIC.api.cloudNew(name).then(r=>after(r,'正在打开登录页…'));
  },
  login(id){MIC.api.cloudLogin(id).then(r=>after(r,'正在打开登录页…'));},
  save(id){MIC.api.cloudSave(id).then(r=>after(r,'登录态已保存'));},
  apply(id){MIC.api.cloudApply(id).then(r=>after(r,'已切到这个号'));},
  check(id){MIC.api.cloudCheck(id).then(r=>after(r,''));},
  checkAll(){MIC.api.cloudKeepNow().then(r=>after(r,''));},
  start(){MIC.api.cloudBrowserStart().then(r=>after(r,'正在启动浏览器…'));},
  stop(){MIC.api.cloudBrowserStop().then(r=>after(r,'浏览器已关闭'));},
  more(e,id){
    e.stopPropagation();
    const a=byId(id);
    MIC.openMenu(e.currentTarget,`<div class="mh">${esc(a.name||'')}</div>
      <button onclick="MIC.cloud.apply('${id}');MIC.closeMenu()">${ic('globe','s')}用这个号打开平台</button>
      <button onclick="MIC.cloud.checks('${id}');MIC.closeMenu()">${ic('refresh','s')}检查登录</button>
      <button onclick="MIC.cloud.authNames('${id}');MIC.closeMenu()">${ic('key','s')}鉴权头（只列名字）</button>
      <button onclick="MIC.cloud.backupMenu('${id}',event)">${ic('hist','s')}备份（${a.backups||0} 份）</button>
      <button onclick="MIC.cloud.keyMenu('${id}',event)">${ic('key','s')}${a.has_key?'更换 API Key':'设置 API Key'}</button>
      <button onclick="MIC.cloud.renameMenu('${id}',event)">${ic('cog','s')}改名</button>
      <div class="sep"></div>
      <button class="dgr" onclick="MIC.cloud.del('${id}')">${ic('trash','s')}删除账号</button>`);
  },
  checks(id){MIC.api.cloudCheck(id).then(r=>after(r,''));},
  authNames(id){
    MIC.api.cloudAuthNames(id).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'读不到鉴权头','bad');return;}
      const n=r.names||[];
      MIC.toast(n.length?'登录态里的鉴权头：'+n.join('、'):'登录态里没有 Rh-* 鉴权头');
    });
  },
  backupMenu(id,e){
    e.stopPropagation();
    MIC.api.cloudBackups(id).then(r=>{
      const spots=r&&r.spots||[];
      const rows=spots.map((s,i)=>`<button onclick="MIC.cloud.restore('${id}','${s.ts}');MIC.closeMenu()">`+
        `${ic('hist','s')}${esc(s.label)}${i===0?' · 最新':''}</button>`).join('')||
        `<div class="mh">还没有备份</div>`;
      MIC.openMenu(e.currentTarget,`<div class="mh">备份 · 点一条恢复</div>`+rows);
    });
  },
  restore(id,ts){MIC.api.cloudRestore(id,ts).then(r=>after(r,'已恢复这份备份'));},
  keyMenu(id,e){
    e.stopPropagation();
    const a=byId(id);
    MIC.openMenu(e.currentTarget,`<div class="mh">API Key · ${esc(a.name||'')}</div>
      <div style="padding:6px 11px"><input id="cloudKey" class="inp" placeholder="粘贴 API Key" autocomplete="off"></div>
      <button onclick="MIC.cloud.saveKey('${id}')">${ic('check','s')}保存</button>
      ${a.has_key?`<button class="dgr" onclick="MIC.cloud.clearKey('${id}')">${ic('trash','s')}清除</button>`:''}`);
  },
  saveKey(id){
    const el=MIC.$('cloudKey');const k=el?el.value.trim():'';
    if(!k){MIC.toast('Key 不能为空');return;}
    MIC.closeMenu();
    MIC.api.cloudKeySet(id,k).then(r=>after(r,'API Key 已保存'));
  },
  clearKey(id){
    MIC.closeMenu();
    MIC.api.cloudKeyClear(id).then(r=>after(r,'已清除 API Key'));
  },
  renameMenu(id,e){
    e.stopPropagation();
    const a=byId(id);
    MIC.openMenu(e.currentTarget,`<div class="mh">改名</div>
      <div style="padding:6px 11px"><input id="cloudRename" class="inp" value="${esc(a.name||'')}"></div>
      <button onclick="MIC.cloud.renameSave('${id}')">${ic('check','s')}保存</button>`);
  },
  renameSave(id){
    const el=MIC.$('cloudRename');const n=el?el.value.trim():'';
    MIC.closeMenu();
    if(!n){MIC.toast('名字不能为空');return;}
    MIC.api.cloudRename(id,n).then(r=>after(r,'已改名'));
  },
  del(id){
    MIC.closeMenu();
    const a=byId(id);
    MIC.toast(`删除「${a.name||''}」？快照与备份一起删`, 'bad',
      {label:'删除',ms:5000,fn:()=>MIC.api.cloudDelete(id).then(r=>after(r,'账号已删除'))});
  },
};
})();
