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
/* 运行中再点同一个按钮 = 停止 */
function toggle(key){
  if(MIC.s.st.running===key)stop(key);else start(key);
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

MIC.runner={start,stop,toggle,load,unload,payload:{}};
})();
