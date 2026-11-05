/* core/styles.js —— 风格预设库：一行 chips 随手套用，展开是整库管理
   数据只有后端那一份 JSON（<数据目录>/styles/presets.json），界面上改完直接写回那个文件，
   所以手改、拷贝、换机器都认。模板里的 {prompt} 代表这一页正在写的那句话：
   含占位就原位插进去，不含就接在原话后面——拼法只在后端一处，两头不各拼一遍。
   按引擎归属过滤：千问/Moss 的图像档不会出现在视频页，反过来也一样。
   缩略图跟画廊一个路子：清单只给路径，滚到哪张取哪张，缓存跨页留着。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

const ENG=[['qwen','千问'],['moss','Moss'],['h3','H3 视频'],['cloud','云端视频']];
const REF_MAX=4;

let target='',eng='',items=null,state='idle',seq=0,lastEng=null;
let tcache={},box=null,body=null,ed=null;

/* ---------- 一行 chips ---------- */
function row(k,engine){
  target=String(k||target||'');
  eng=engine==null?eng:String(engine||'');
  load();
  return `<div class="chiprow" data-st-chips>${chips()}</div>`;
}

function chips(){
  /* 名字和「分类」「灵感」那两行同宽，不带图标：34px 的槽位塞不下图标＋两个字 */
  const name='<span class="chipname">风格</span>';
  if(state==='err')return name+'<span class="mut fine">读不出来 · 到「环境管理」看下后端是否还在</span>';
  if(state!=='ready')return name+'<span class="mut fine">正在读风格库…</span>';
  if(!items.length)return name+'<span class="mut fine">还没有 · 展开「风格库」建一条</span>';
  return name+items.map(p=>`<button class="chip" title="${esc(p.name)}：${esc(snip(p.tpl))}" `+
    `onclick="MIC.styles.apply('${p.id}')">${esc(p.name)}</button>`).join('');
}
function snip(t){return String(t||'').replace(/\s+/g,' ').slice(0,140);}

/* 取清单：同一路引擎只取一次；改过库调 invalidate()。
   seq 挡住「先切千问再切 Moss」时旧回包盖新清单。 */
function load(){
  if(state==='ready'&&lastEng===eng)return;
  if(state==='load'&&lastEng===eng)return;
  lastEng=eng;state='load';
  const my=++seq;
  MIC.api.styleList(eng).then(r=>{
    if(my!==seq)return;
    if(!r||!r.ok){state='err';items=null;paint();return;}
    items=r.items||[];state='ready';paint();
  }).catch(()=>{if(my!==seq)return;state='err';items=null;paint();});
}
function invalidate(){state='idle';lastEng=null;load();}

/* 清单回来只换风格这几处：整页重画会把正在打的提示词吃掉 */
function paint(){
  document.querySelectorAll('#view [data-st-chips]').forEach(el=>{el.innerHTML=chips();});
  const b=document.querySelector('#view [data-st-panel]');
  if(b&&b.dataset.built)b.innerHTML=panelHTML();
  hydrate();
}

/* ---------- 库面板（展开才画，见 form.foldLazy） ---------- */
function foldLib(k,engine){
  target=String(k||target||'');
  eng=engine==null?eng:String(engine||'');
  load();
  /* builder 返回的那串是 foldToggle 直接 innerHTML 进去的，不经过 paint()：
     缩略图这一趟得自己点水，不然第一次展开全是空框。 */
  return C.foldLazy('风格库','palette',()=>{
    const h=panelHTML();
    setTimeout(hydrate,0);
    return h;
  },'缩略图 · 参考图 · 一份 JSON','data-st-panel');
}

function panelHTML(){
  const head=`<div class="btnrow stbar">`+
    `<button class="btn sm" onclick="MIC.styles.editNew()">${ic('plus','s')}新建风格</button>`+
    `<button class="btn sm gho" onclick="MIC.styles.reset()">${ic('refresh','s')}恢复出厂</button>`+
    `<span class="grow"></span><span class="mut fine">${
      state!=='ready'?'':items.length+' 条 · styles/presets.json'}</span></div>`;
  if(state==='err')return head+'<div class="empty">风格库读不出来 · 换一页或重开一次会再试</div>';
  if(state!=='ready')return head+'<div class="empty">正在读风格库 …</div>';
  if(!items.length)return head+'<div class="empty">还没有风格 · 点「新建」，或在画廊那张图上点「存为风格」</div>';
  return head+items.map(cardHTML).join('');
}

function cardHTML(p){
  const badges=(p.eng&&p.eng.length)
    ?p.eng.map(e=>`<i class="sten">${esc(labelOf(e))}</i>`).join('')
    :'<i class="sten">通用</i>';
  const refs=(p.refs_abs||[]).map(x=>thumb(x,'stref')).join('');
  return `<div class="stcard">
    ${p.thumb_abs?thumb(p.thumb_abs,'stthumb'):'<div class="stthumb ph">'+ic('image','s')+'</div>'}
    <div class="stmain">
      <div class="sth"><b>${esc(p.name)}</b>${badges}</div>
      <span class="ptxt">${esc(p.tpl)}</span>
      ${p.note?`<span class="mut fine">${esc(p.note)}</span>`:''}
      ${refs?`<div class="strefs">${refs}</div>`:''}
    </div>
    <div class="stacts">
      <button class="btn sm pri" onclick="MIC.styles.apply('${p.id}')">套用</button>
      <button class="btn sm gho" title="编辑" onclick="MIC.styles.edit('${p.id}')">${ic('cog','s')}</button>
      <button class="btn sm gho" title="删除" onclick="MIC.styles.del('${p.id}')">${ic('trash','s')}</button>
    </div></div>`;
}

function thumb(p,cls){
  return `<img class="${cls}" data-stthumb="${esc(p)}" alt="" loading="lazy">`;
}
/* 缩略图按需取：清单只给路径，滚到哪张才问后端要那一张。
   面板在 #view 里、编辑弹层挂在 body 上，两处以同一个口子点水，共用一份缓存。 */
function hydrateIn(scope){
  if(!scope)return;
  scope.querySelectorAll('img[data-stthumb]').forEach(im=>{
    const p=im.dataset.stthumb;
    if(!p||im.getAttribute('src'))return;
    if(tcache[p]){im.src=tcache[p];return;}
    if(im.dataset.want)return;
    im.dataset.want='1';
    MIC.api.thumb(p,256).then(r=>{
      if(!r||!r.ok||!r.url)return;
      tcache[p]=r.url;
      if(im.isConnected)im.src=r.url;
    }).catch(()=>{});
  });
}
function hydrate(){hydrateIn(document.getElementById('view'));}

/* ---------- 套用 ---------- */
function curText(){
  const el=document.querySelector(`#view [data-k="${target}"]`);
  if(el)return String(el.value==null?el.textContent||'':el.value);
  return String(MIC.mget(MIC.s.cfg,target)||'');
}

function apply(pid){
  C.commit();                       // 先把这一屏的字收进 cfg，不然刚打的半句会被旧值画回去
  const t=curText();
  MIC.api.styleApply(pid,t).then(r=>{
    if(!r||!r.ok){MIC.toast((r&&r.msg)||'风格没应用上');return;}
    const patch={};
    patch[target]=r.prompt;
    const nk=target.replace(/\.prompt$/,'.negative');
    if(nk!==target&&r.negative)patch[nk]=r.negative;
    C.commitMany(patch);
    /* 参考图有余位才补，已经手工挑过的不挤掉 */
    if(!putRefs(r.refs||[]))MIC.render();
    MIC.toast('已套用「'+r.name+'」'+(r.lost?'（'+r.lost+' 张参考图不在了）':''));
  }).catch(()=>MIC.toast('风格没应用上'));
}

/* 这一屏有没有参考图格子：视频/成片那一路走 data-refs，编辑页自己管着一组图 */
function putRefs(list){
  if(!list.length)return false;
  const boxEl=document.querySelector('#view [data-refs]');
  if(boxEl){
    const k=boxEl.dataset.refs,cur=C.refsOf(k);
    const add=list.filter(p=>cur.indexOf(p)<0);
    if(!add.length)return false;
    C.refsSet(k,cur.concat(add).slice(0,REF_MAX));   // refsSet 自己会写 first 并重画
    return true;
  }
  if(MIC.edit&&/^edit\./.test(target)&&MIC.edit.addMany){
    MIC.edit.addMany(list);
    return true;
  }
  return false;
}

/* ---------- 编辑弹层 ----------
   挂在 document.body 上而不是 #view 里：整页重画只换 #view，
   写了一半的模板不会被一次轮询后的重画吃掉。 */
function ensure(){
  if(box)return box;
  box=document.createElement('div');
  box.className='mask hide';
  box.innerHTML=`<div class="modal stmodal">
    <div class="mh">${ic('palette')}<b id="stEdTitle">风格预设</b><span class="grow"></span>
      <span class="mut fine">${REF_MAX} 张参考图以内</span>
      <button class="iconbtn" onclick="MIC.styles.closeEdit()" title="关闭">${ic('close')}</button></div>
    <div class="mb" id="stEdBody"></div>
    <div class="mf"><span class="mut fine">{prompt}＝这一页写的那句话；不带它就接在原话后面</span>
      <span class="grow"></span>
      <button class="btn gho" onclick="MIC.styles.closeEdit()">取消</button>
      <button class="btn pri" onclick="MIC.styles.saveEdit()">保存</button></div></div>`;
  box.addEventListener('click',e=>{if(e.target===box)closeEdit();});
  body=box.querySelector('#stEdBody');
  document.body.appendChild(box);
  document.addEventListener('keydown',onKey);
  return box;
}

function openEd(p,title){
  ed=Object.assign({id:'',name:'',tpl:'',neg:'',note:'',eng:[],thumb:'',thumb_abs:'',refs:[],refs_abs:[]},p||{});
  ensure().classList.remove('hide');
  box.querySelector('#stEdTitle').textContent=title||'风格预设';
  drawEd();
  const f=body.querySelector('[data-f="name"]');
  if(f)setTimeout(()=>f.focus(),30);
}
function drawEd(){
  body.innerHTML=
    `<div class="stgrid">
      <div class="f"><label>名字</label><div class="c">
        <input class="inp" data-f="name" maxlength="24" value="${esc(ed.name)}" placeholder="电影感"></div></div>
      <div class="f"><label class="tip" title="一个都不勾＝所有页都能用">适用</label>
        <div class="c"><div class="seg">
        ${ENG.map(([v,label])=>`<button type="button" class="engbtn ${
          ed.eng.indexOf(v)>=0?'on':''}" data-e="${v}"
          onclick="this.classList.toggle('on')">${label}</button>`).join('')}
      </div></div></div>
     </div>
     <div class="f"><label>提示词模板</label><div class="c">
       <textarea class="inp" data-f="tpl" rows="5" placeholder="胶片质感，35mm，颗粒与暗角，{prompt}">${esc(ed.tpl)}</textarea>
     </div></div>
     <div class="f"><label>通用反向</label><div class="c">
       <textarea class="inp" data-f="neg" rows="2" placeholder="留空＝不动反向框">${esc(ed.neg)}</textarea>
     </div></div>
     <div class="stgrid">
       <div class="f"><label>缩略图</label><div class="c">${mediaHTML('thumb')}</div></div>
       <div class="f"><label>参考图</label><div class="c">${mediaHTML('refs')}</div></div>
     </div>
     <div class="f"><label>备注</label><div class="c">
       <input class="inp" data-f="note" maxlength="80" value="${esc(ed.note)}" placeholder="什么时候用它"></div></div>`;
  hydrateIn(body);
}
function mediaHTML(kind){
  if(kind==='thumb')
    return ed.thumb_abs?`<div class="stmedia"><div class="stpic">
        ${thumb(ed.thumb_abs,'stthumb')}
        <button type="button" class="refx" title="去掉" onclick="MIC.styles.pickThumb('')">${ic('close','s')}</button>
      </div></div>`
      :`<button type="button" class="btn sm gho" onclick="MIC.styles.pickThumb()">${ic('image','s')}选一张</button>`;
  const cells=(ed.refs_abs||[]).map((p,i)=>`<div class="stpic">
      ${thumb(p,'stref')}
      <button type="button" class="refx" title="去掉" onclick="MIC.styles.dropRef(${i})">${ic('close','s')}</button>
    </div>`).join('');
  const add=(ed.refs_abs||[]).length<REF_MAX
    ?`<button type="button" class="btn sm gho" onclick="MIC.styles.pickRef()">${ic('plus','s')}加图</button>`:'';
  return `<div class="stmedia">${cells}${add}</div>`;
}

function pickThumb(p){
  if(p===''){ed.thumb='';ed.thumb_abs='';drawEd();return;}
  MIC.picker.open('',file=>{ed.thumb=file;ed.thumb_abs=file;drawEd();});
}
function pickRef(){
  if((ed.refs_abs||[]).length>=REF_MAX){MIC.toast('参考图最多 '+REF_MAX+' 张');return;}
  MIC.picker.open('',file=>{
    ed.refs=ed.refs||[];ed.refs_abs=ed.refs_abs||[];
    if(ed.refs_abs.indexOf(file)<0){ed.refs.push(file);ed.refs_abs.push(file);}
    drawEd();
  });
}
function dropRef(i){
  (ed.refs||[]).splice(i,1);(ed.refs_abs||[]).splice(i,1);drawEd();
}

function formEd(){
  const v=f=>{const el=body.querySelector(`[data-f="${f}"]`);return el?String(el.value||''):'';};
  return {id:ed.id||'',name:v('name'),tpl:v('tpl'),neg:v('neg'),note:v('note'),
    eng:[].slice.call(body.querySelectorAll('.engbtn.on')).map(b=>b.dataset.e),
    thumb:ed.thumb||'',refs:(ed.refs||[]).slice()};
}

function saveEdit(){
  const p=formEd();
  MIC.api.styleSave(p).then(r=>{
    if(!r||!r.ok){MIC.toast((r&&r.msg)||'风格没存上');return;}
    closeEdit();
    /* 后端回的是全量清单（不分引擎），这里重新按这一页那一路取一次，
       不然千问页存一条「只给 Moss 用」的，界面上会看到它出现在 chips 里 */
    invalidate();
    MIC.toast('已保存：'+p.name);
  }).catch(()=>MIC.toast('风格没存上'));
}
function del(pid){
  const p=findP(pid);
  if(!confirm('删掉「'+((p&&p.name)||'这条风格')+'」？模板和参考图都会没，收进风格库的副本一并清掉。'))return;
  MIC.api.styleDelete(pid).then(r=>{
    if(!r||!r.ok){MIC.toast((r&&r.msg)||'风格没删掉');return;}
    invalidate();
    MIC.toast('已删除');
  }).catch(()=>MIC.toast('风格没删掉'));
}
function reset(){
  if(!confirm('恢复出厂？自己新建的风格会全部消失，换成包里那份默认清单。'))return;
  MIC.api.styleReset().then(r=>{
    if(!r||!r.ok){MIC.toast((r&&r.msg)||'恢复没成功');return;}
    invalidate();
    MIC.toast('已恢复出厂清单');
  }).catch(()=>MIC.toast('恢复没成功'));
}
function findP(pid){
  return (items||[]).filter(p=>p.id===pid)[0]||null;
}
function edit(pid){
  const p=findP(pid);
  if(!p){MIC.toast('这条已经不在了');return;}
  openEd({id:p.id,name:p.name,tpl:p.tpl,neg:p.neg,note:p.note,eng:(p.eng||[]).slice(),
    thumb:p.thumb,thumb_abs:p.thumb_abs,refs:(p.refs||[]).slice(),refs_abs:(p.refs_abs||[]).slice()},
    '编辑风格');
}
function editNew(){
  openEd({name:'',tpl:'{prompt}',neg:'',eng:eng?[eng]:[]},'新建风格');
}
function closeEdit(){if(box)box.classList.add('hide');}
function onKey(e){if(e.key==='Escape'&&!box.classList.contains('hide'))closeEdit();}

/* 画廊那张图 → 编辑框：提示词、反向、缩略图都从那张的记账里拿，改完再存 */
function fromGallery(file,engine){
  MIC.api.styleDraft(file,engine||'').then(r=>{
    if(!r||!r.ok){MIC.toast((r&&r.msg)||'存不了');return;}
    const p=r.preset;
    openEd({name:p.name,tpl:p.tpl,neg:p.neg,note:'',eng:p.eng||[],
      thumb:p.thumb,thumb_abs:p.thumb_abs,refs:[],refs_abs:[]},'存为风格');
  }).catch(()=>MIC.toast('存不了'));
}

function labelOf(e){
  for(let i=0;i<ENG.length;i++)if(ENG[i][0]===e)return ENG[i][1];
  return e;
}

MIC.styles={row,foldLib,apply,edit,editNew,closeEdit,saveEdit,del,reset,pickThumb,pickRef,dropRef,fromGallery,invalidate};
})();
