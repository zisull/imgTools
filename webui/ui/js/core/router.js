/* core/router.js —— 页面注册表 + 主区渲染：新增功能 = 一个页面模块 + 一个标签页 */
(function(){
const MIC=window.MIC=window.MIC||{};
const esc=MIC.esc, ic=MIC.ic;

MIC.pages={};
MIC.registerPage=function(key,def){MIC.pages[key]=def;};

MIC.render=function(){
  const sel=MIC.nav.state.sel;
  const key=MIC.nav.pageOf();
  const p=MIC.pages[key]||MIC.pages.__blank__;
  const path=MIC.nav.pathOf(sel);
  MIC.$('crumb').innerHTML=path.map((x,i,a)=>
    i===a.length-1?`<b>${esc(x)}</b>`:`<span>${esc(x)}</span><span class="sep">/</span>`).join('');
  MIC.$('view').innerHTML=`<div class="phead">
      <div style="min-width:0"><div class="ptitle">${esc(p.title)}</div><div class="psub">${esc(p.sub||'')}</div></div>
      <div class="grow"></div>
      <div class="acts">
        <button class="btn sm gho" onclick="MIC.nav.startRename('${sel}')">${ic('cog','s')}改名</button>
        <button class="btn sm gho" onclick="MIC.nav.nodeMenu(event,'${sel}')">${ic('move','s')}移动</button>
      </div></div>`+(p.render?p.render():'');
  MIC.view.tick();
  if(p.mount)p.mount();   /* 结果区这类要等 DOM 落地再刷一次 */
};
})();
