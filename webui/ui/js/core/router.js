/* core/router.js —— 页面注册表 + 主区渲染：新增功能 = 一个页面模块 + 一个标签页 */
(function(){
const MIC=window.MIC=window.MIC||{};
const esc=MIC.esc;

MIC.pages={};
MIC.registerPage=function(key,def){MIC.pages[key]=def;};

MIC.render=function(){
  /* 没选过引擎（cfg.welcomed 还是 false）→ 主区先给欢迎页：
     门一开就问「你要哪一路」，答完界面自己变成那一套，别让人先去设置页找开关。 */
  const greet=!MIC.s.cfg.welcomed&&MIC.pages.welcome;
  const sel=MIC.nav.state.sel;
  const key=greet?'welcome':MIC.nav.pageOf();
  const p=MIC.pages[key]||MIC.pages.__blank__;
  const path=greet?['欢迎']:MIC.nav.pathOf(sel);
  MIC.$('crumb').innerHTML=path.map((x,i,a)=>
    i===a.length-1?`<b>${esc(x)}</b>`:`<span>${esc(x)}</span><span class="sep">/</span>`).join('');
  /* 页头压成一行：标题 + 副标题同一行基线对齐，页身立刻开始。
     sub 写成函数=活副标题（当前引擎、档位、条数这些跟着轮询变），写字符串=固定说明。
     bare 的页（欢迎页）自己带大标题，再挂一行小页头只是把同一个词说两遍。 */
  const sub=typeof p.sub==='function'?(p.sub()||''):(p.sub||'');
  MIC.$('view').innerHTML=(p.bare?'':`<div class="phead">
      <span class="ptitle">${esc(p.title)}</span><span class="psub">${esc(sub)}</span>
    </div>`)+(p.render?p.render():'');
  MIC.view.tick();
  if(p.mount)p.mount();   /* 结果区这类要等 DOM 落地再刷一次 */
};
})();
