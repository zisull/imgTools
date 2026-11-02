/* core/runner.js —— 任务启停：先把表单写回配置，再调后端；失败只提示不打断界面
   生图域只有一种生成任务（gen）；模型装卸是它的两条前置路径，也放这里统一入口。 */
(function(){
const MIC=window.MIC=window.MIC||{};

/* 表单块按引擎分：千问参数在 gen.*，Moss 在 moss.*；后端都记成 gen 任务。
   firing 是界面这层的占位：桥调用是异步的，r.ok 回来之前连点第二下会再提交一次。 */
const TASKS={gen:{block:'gen'},moss:{block:'moss',extra:{engine:'moss'}}};
let firing=false;
function start(key,payload){
  const t=TASKS[key]||TASKS.gen;
  if(firing||MIC.s.st.running)return;
  firing=true;
  const patch=MIC.form.commit();
  const body=Object.assign({},patch[t.block]||{},t.extra||{},payload||{});
  /* 尺寸选了「自定义」：宽高取整到 16 的倍数（两台模型都按 16 对齐最稳），
     限 256~2048（12G 卡再大就溢共享内存了），折成后端认的 size 字符串 */
  if(body.size==='custom'){
    const r16=n=>Math.max(256,Math.min(2048,Math.round((Number(n)||1024)/16)*16));
    body.size=r16(body.cw)+'x'+r16(body.ch);
  }
  MIC.api.startGen(body).then(r=>{
    firing=false;
    if(!r||!r.ok){MIC.toast((r&&r.msg)||'任务没起来');return;}
    MIC.s.st.running='gen';MIC.s.st.done=0;MIC.s.st.total=r.total||8;
    MIC.s.st.status='运行中…';
    MIC.render();
  }).catch(e=>{firing=false;MIC.toast('启动失败：'+(e.message||e));});
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
  if(MIC.s.st.model_loaded){MIC.toast('模型已在显存');return;}
  if(MIC.s.st.running){MIC.toast('有任务在跑，先停止');return;}
  MIC.api.loadModel().then(r=>{
    if(!r||!r.ok)MIC.toast((r&&r.msg)||'未能开始载入');
    else MIC.render();
  }).catch(e=>MIC.toast('载入失败：'+(e.message||e)));
}
function unload(){
  if(!MIC.s.st.model_loaded){MIC.toast('显存里没有模型');return;}
  if(MIC.s.st.running){MIC.toast('生成还在跑，先停止');return;}
  MIC.api.unloadModel().then(r=>{
    if(!r||!r.ok)MIC.toast((r&&r.msg)||'未能卸载');
    else MIC.render();
  }).catch(e=>MIC.toast('卸载失败：'+(e.message||e)));
}

/* 成图接力：上一张成图当输入。局部改=当原图去涂抹，整张改=当参考图。 */
function again(target){
  const p=MIC.s.st.last_image;
  if(!p){MIC.toast('还没有成图');return;}
  if(MIC.nav.pageHidden&&MIC.nav.pageHidden(target)){
    MIC.toast('「'+(MIC.pages[target]||{}).title+'」那一路的环境关着，到「环境」页开启后再接力');return;}
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

MIC.runner={start,stop,toggle,load,unload,again};

/* 「点开始要不要先等载入」这句话千问的三个出图页都要说；引擎切在 Moss 那边时
   s.model_loaded 指的是 ComfyUI，照抄会把灯说反——按引擎给话术。 */
MIC.runner.modelNote=function(run){
  const s=MIC.s.st;
  if(run)return '运行中，参数已锁定';
  if(s.engine==='moss')return '现在是 Moss 引擎：点开始会先切回千问';
  return s.model_loaded?'模型已在显存，点开始直接出图':'点开始会自动载入模型（十几秒）';
};

/* 主操作行：开始按钮在参数卡末尾（锁外面——运行中「停止」必须点得动）。
   按当前引擎决定发哪一块：千问发 gen.*，Moss 发 moss.* 并带上 engine 让后端走 ComfyUI。 */
MIC.runner.action=function(startCall){
  const run=!!MIC.s.st.running,ic=MIC.ic;
  const key=MIC.s.st.engine==='moss'?'moss':'gen';
  return run
    ? '<div class="actrow"><button class="btn pri big" onclick="MIC.runner.stop(\'gen\')">'+ic('stop','s')+'停止</button><span class="mut fine">参数已锁定</span></div>'
    : '<div class="actrow"><button class="btn pri big" data-start title="Ctrl+Enter" '+
      'onclick="'+(startCall||('MIC.runner.start(\''+key+'\')'))+'">'+ic('play','s')+'开始生成</button>'+
      '<span class="mut fine">Ctrl+Enter</span></div>';
};

/* 运行卡 + 成图预览：三个出图页同构，收成一个 helper。
   主「开始/停止」在参数卡的 MIC.runner.action() 里；这里只留状态、进度、
   本轮结果、成图与页特有的次级按钮。
   opts.rows / opts.btns 给页面塞自己的状态行和按钮（生图页的显存条与载入/卸载）。
   预览并进同一张卡：以前「运行」「成图预览」两张卡上下摞着，多一层壳就多一截空；
   现在一道虚线隔开，配合 .duo 双栏整块吸在右栏。 */
MIC.runner.runCard=function(runNote,opts){
  const s=MIC.s.st, run=!!s.running, C=MIC.form, ic=MIC.ic;
  const o=opts||{};
  const statusBody=
    '<div class="status">'+
      C.strow('任务状态','<span class="dot '+(run?'run':'')+'" data-role="dot"></span><span data-role="st"></span>')+
      C.strow('进度','<div class="prog"><i data-role="prog"></i></div><span class="mut fine" data-role="pgtext"></span>')+
      (o.rows||'')+
      C.strow('本轮结果','<span class="mut" data-role="result">'+(runNote||'就绪后开始')+'</span>')+'</div>'+
    '<div class="btnrow">'+(o.btns||'')+
      '<button class="btn" onclick="MIC.gen.openDir()">'+ic('folder','s')+'打开输出目录</button>'+
    '</div>'+
    '<div class="rprev"><div class="prevwrap" data-role="imgprev"></div></div>';
  return C.card('运行','play',statusBody);
};
})();
