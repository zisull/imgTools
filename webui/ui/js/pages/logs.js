/* pages/logs.js —— 日志：整个工作台唯一的一处
   以前六页各摆一张日志卡，切页看到的还是同一份环形缓冲，等于把一块屏复制了六遍；
   生成页那栏还按 'gen' 过滤，把载入阶段（key='load'）的日志整段漏掉。
   现在归这一页：全部 / 生成 / 系统 三个过滤 + 跟着新行贴底。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic;

/* 'load' 也算生成：点开始时先载入模型，那几行就是这一轮的前半段 */
const FILT=[['', '全部'], ['gen,load', '生成'], ['sys', '系统']];
let f='';

function bar(){
  const seg='<div class="seg">'+FILT.map(x=>
    `<button class="${x[0]===f?'on':''}" onclick="MIC.logs.set('${x[0]}')">${x[1]}</button>`).join('')+'</div>';
  return `<div class="bar">${seg}
      <span class="mut fine">　界面内保留最近 <span data-role="logcount">${MIC.s.logs.length}</span> 条（重启后看日志文件）</span>
      <span class="grow"></span>
      <button class="btn sm gho" onclick="MIC.view.refreshStats()">${ic('refresh','s')}刷新状态</button>
      <button class="btn sm gho" onclick="MIC.logs.copy()">${ic('copy','s')}复制</button>
      <button class="btn sm gho" onclick="MIC.logs.clear()">${ic('trash','s')}清空界面</button>
    </div>`;
}

MIC.registerPage('logs',{
  title:'日志',sub:()=>MIC.s.logs.length+' 条 · 生成 / 体检 / 补全同一条流',icon:'hist',
  render(){
    return C.card('运行日志','refresh',
        bar()+`<div class="log tall" data-role="log" data-keys="${MIC.esc(f)}"></div>`,{tight:true});
  },
});

MIC.logs={
  set(k){f=k||'';MIC.render();},
  copy(){
    const t=MIC.view.logText(f?f.split(','):null);
    if(!t){MIC.toast('这一路还没有日志');return;}
    MIC.view.copy(t,'已复制 '+t.split('\n').length+' 行');
  },
  clear(){MIC.clearLogs(f?f.split(','):null);MIC.render();},
};
})();
