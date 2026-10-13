/* pages/overview.js —— 概览：模型状态 / 显存 / 图库 + 快捷入口 + 最近日志 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

function stat(cls,k,v,u,role,field){
  return `<div class="stat ${cls}"><div class="k">${k}</div><div class="v">${
    role?`<b data-role="${role}" data-field="${field}">${v}</b>`:v}${u?`<span class="u">${u}</span>`:''}</div></div>`;
}
function tile(page,icon,title,desc){
  return `<button class="tile" onclick="MIC.nav.goto('${page}')"><div class="tic">${ic(icon)}</div>
    <div><div class="tt">${title}</div><div class="td">${desc}</div></div></button>`;
}

MIC.registerPage('overview',{
  title:'概览',sub:'模型、显存与图库一览',icon:'home',
  render(){
    const s=MIC.s.st;
    return `<div class="stats">
      ${stat(s.model_loaded?'ok':'warn','模型状态',s.model_loaded?'已载入':'未载入','')}
      ${stat('ac','图库',MIC.n(s.img_count),'张','count','img_count')}
      ${stat('','上一张用时',(Number(s.last_sec)||0).toFixed(1),'秒')}
      ${stat('','目标','≤60','秒/张')}
    </div>
    ${C.card('引擎','power',C.lock(s.running==='load'||s.running==='gen',
      `<div class="strow"><span class="k">显存占用</span><span data-role="vram" style="flex:1;display:flex;gap:10px;align-items:center"></span></div>
       <div class="strow"><span class="k">动作</span>
         <button class="btn sm ${s.model_loaded?'gho':'pri'}" onclick="MIC.runner.load()">${ic('down','s')}载入模型</button>
         <button class="btn sm gho" onclick="MIC.runner.unload()">${ic('power','s')}卸载（归还显存）</button>
         <span class="mut fine">${esc(s.model_name||'')} · fp8 + CPU offload 是 12G 卡上唯一跑得动的组合（实测 1024≈28s）</span>
       </div>
       <div class="strow"><span class="k">进度</span><div class="prog"><i data-role="prog"></i></div><span class="mut fine" data-role="pgtext"></span></div>`),{note:s.quant==='fp8'?'量化 fp8':'未量化（会爆显存）'})}
    ${C.card('快速开始','play',`<div class="tiles">
        ${tile('t2i','flower','文生图','提示词 → 1024/1536 成图，Turbo 8 步')}
        ${tile('gallery','image','画廊','浏览与删除输出目录里的成图')}
        ${tile('settings','cog','设置','模型目录 / 输出目录 / API 服务')}
      </div>`,{note:'3 个功能页'})}
    ${C.logcard('','最近日志',
      `<button class="btn sm gho" onclick="MIC.view.refreshStats()">${ic('refresh','s')}刷新状态</button>`)}`;
  },
});
})();
