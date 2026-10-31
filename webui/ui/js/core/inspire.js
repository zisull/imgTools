/* core/inspire.js —— 提示词构件：灵感行（分类 + 这一类全部词条）与词库全览面板
   词库原来单开一页，其实只在「想挑一挑」时用得着，挑完还得回生图页填——并进来：
   日常只看两行 chips（悬停看全句），要通览就展开面板，同一份数据、同一套填入/复制。
   整句那几类直接换掉提示词框；光影/构图/质感往后面追加；反向那一类填进反向框。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;
let key='';                       // 这一屏填进哪一块（gen.prompt / moss.prompt）

function cat(){return MIC.lib.cat(String(MIC.mget(MIC.s.cfg,'lib.cat')||'person'));}

function box(promptKey){
  key=promptKey;
  const c=cat();
  const cats='<div class="chiprow catrow"><span class="chipname">分类</span>'+
    MIC.lib.CATS.map(x=>`<button class="chip ${x.id===c.id?'on':''}" `+
      `onclick="MIC.inspire.setCat('${x.id}')">${esc(x.name)}</button>`).join('')+'</div>';
  const list='<div class="chiprow insrow"><span class="chipname">灵感</span>'+
    c.items.map((it,i)=>`<button class="chip" title="${esc(it.pos)}" `+
      `onclick="MIC.inspire.pick(${i})">${esc(it.name)}</button>`).join('')+'</div>';
  return cats+list;
}

/* 全览：七类逐条摊开，每条都给「填入 / 复制」——整句太长，chips 上放不下。
   每一类末尾那条通用反向是这一类最常见的失败，一键进反向框，不用去反向那一类里翻。 */
function panel(promptKey){
  key=promptKey;
  return MIC.lib.CATS.map(c=>{
    const rows=c.items.map((it,i)=>`<div class="prow">
      <div class="pmain"><b>${esc(it.name)}</b><span class="ptxt">${esc(it.pos)}</span></div>
      <span class="grow"></span>
      <button class="btn sm" onclick="MIC.inspire.fill('${c.id}',${i})">${
        c.id==='negative'?'填反向':'填入'}</button>
      <button class="btn sm gho" title="复制这句" onclick="MIC.inspire.copy('${c.id}',${i})">${ic('copy','s')}</button>
    </div>`).join('');
    const foot=(c.id==='negative'||!c.neg)?'':
      `<div class="pfoot"><span class="mut">这一类的通用反向</span>`+
      `<span class="ptxt">${esc(c.neg)}</span>`+
      `<button class="btn sm gho" onclick="MIC.inspire.negFill('${c.id}')">填进反向框</button></div>`;
    return `<div class="egroup">${esc(c.name)} · ${c.items.length} 条</div>`+rows+foot;
  }).join('');
}

function setCat(id){
  C.commit();                     // 先把这一屏的字收进 cfg，重画才不丢
  C.commitPath('lib.cat',id);
  MIC.render();
}
function pick(i){fill(cat().id,i);}
function fill(catId,i){
  const c=MIC.lib.cat(catId),item=c.items[i];
  if(!item)return;
  C.commit();
  MIC.lib.fill(key,item,c);       // 填进去的同时把空着的反向词配上
  MIC.render();
}
function copy(catId,i){
  const it=MIC.lib.cat(catId).items[i];
  if(it)MIC.view.copy(it.pos,'已复制：'+it.name);
}
/* 这一类的通用反向：反向框空着时的默认值，单独给一颗按钮省得手动挑 */
function negFill(catId){
  const c=MIC.lib.cat(catId);
  C.commitPath(key.replace(/\.prompt$/,'.negative'),c.neg||MIC.lib.NEG_BASE);
  MIC.toast('通用反向已填进反向框');
}

MIC.inspire={box,panel,pick,fill,setCat,copy,negFill};
})();
