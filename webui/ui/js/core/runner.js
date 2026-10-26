/* core/runner.js —— 任务启停：先把表单写回配置，再调后端；失败只提示不打断界面
   生图域只有一种生成任务（gen）；模型装卸是它的两条前置路径，也放这里统一入口。 */
(function(){
const MIC=window.MIC=window.MIC||{};

function start(key,payload){
  const patch=MIC.form.commit();
  const body=Object.assign({},patch[key]||{},payload||{});
  if(key!=='gen'){MIC.toast('未注册的任务：'+key);return;}
  MIC.api.startGen(body).then(r=>{
    if(!r||!r.ok){MIC.toast((r&&r.msg)||'任务未启动');return;}
    MIC.s.st.running=key;MIC.s.st.done=0;MIC.s.st.total=r.total||8;
    MIC.s.st.status='运行中…';
    MIC.render();
  }).catch(e=>MIC.toast('启动失败：'+(e.message||e)));
}
function stop(key){
  MIC.api.stop(key||MIC.s.st.running).then(r=>{
    if(!r||!r.ok)MIC.toast((r&&r.msg)||'没有运行中的任务');
  }).catch(()=>{});
}
/* 运行中（load 或 gen 任一阶段）再点同一个按钮 = 停止；否则开始。
   旧写法判 running===key，载入阶段 running='load' 会漏判成「开始」→ 停止点了没反应。 */
function toggle(key){
  if(MIC.s.st.running)stop(key);else start(key);
}
/* 模型装卸：载入约需十几秒（fp8 权重整份进显存），卸载归还显存 */
function load(){
  if(MIC.s.st.model_loaded){MIC.toast('模型已在显存里');return;}
  if(MIC.s.st.running){MIC.toast('有任务在跑：'+MIC.s.st.running);return;}
  MIC.api.loadModel().then(r=>{
    if(!r||!r.ok)MIC.toast((r&&r.msg)||'未能开始载入');
    else MIC.render();
  }).catch(e=>MIC.toast('载入失败：'+(e.message||e)));
}
function unload(){
  if(!MIC.s.st.model_loaded){MIC.toast('模型本来就没在显存里');return;}
  if(MIC.s.st.running){MIC.toast('生成还在跑，先停止');return;}
  MIC.api.unloadModel().then(r=>{
    if(!r||!r.ok)MIC.toast((r&&r.msg)||'未能卸载');
    else MIC.render();
  }).catch(e=>MIC.toast('卸载失败：'+(e.message||e)));
}

/* 成图接力：把上一张成图当输入送进编辑页。局部改=当原图去涂抹，整张改=当参考图。 */
function again(target){
  const p=MIC.s.st.last_image;
  if(!p){MIC.toast('还没有成图');return;}
  if(target==='inpaint')MIC.inp.useImage(p);
  else if(target==='edit')MIC.edit.useImage(p);
  else{MIC.toast('不认识的接力目标：'+target);return;}
  MIC.nav.goto(target);
}
/* Ctrl+Enter = 按下本页那个「开始」：写完提示词手不用离开键盘去找按钮。
   运行中不接管——快捷键去按「停止」太容易误伤，那一下留给人明确点。 */
document.addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){
    if(MIC.s&&MIC.s.st&&MIC.s.st.running)return;
    const b=document.querySelector('#view [data-start]');
    if(!b)return;
    e.preventDefault();b.click();
  }
});

MIC.runner={start,stop,toggle,load,unload,again,payload:{}};

/* 运行卡 + 成图预览 + 日志卡：文生图/编辑/局部/透明四页同构，收成一个 helper。
   startCall 是「空闲时点开始」要执行的表达式（如 "MIC.edit.start()"）；
   运行中固定显示停止按钮（后端只有一种在跑的任务，一律 toggle 'gen'）。 */
MIC.runner.runCard=function(runNote,startCall){
  const s=MIC.s.st, run=!!s.running, C=MIC.form, ic=MIC.ic;
  const btn=run
    ? '<button class="btn pri" onclick="MIC.runner.stop(\'gen\')">'+ic('stop','s')+'停止</button>'
    : '<button class="btn pri" data-start title="Ctrl+Enter 也能开始" onclick="'
      +(startCall||'MIC.runner.start(\'gen\')')+'">'+ic('play','s')+'开始</button>';
  const statusBody=
    '<div class="status">'+
      C.strow('任务状态','<span class="dot '+(run?'run':'')+'" data-role="dot"></span><span data-role="st"></span>')+
      C.strow('进度','<div class="prog"><i data-role="prog"></i></div><span class="mut fine" data-role="pgtext"></span>')+
      C.strow('本轮结果','<span class="mut" data-role="result">'+(runNote||'就绪后开始')+'</span>')+'</div>'+
    '<div class="btnrow">'+btn+
      '<button class="btn" onclick="MIC.gen.openDir()">'+ic('folder','s')+'打开输出目录</button>'+
    '</div>';
  return C.card('运行','play',statusBody)+
    C.card('成图预览','image','<div data-role="imgprev" class="prevwrap"></div>',{tight:true})+
    C.logcard('gen','生成日志');
};
})();
