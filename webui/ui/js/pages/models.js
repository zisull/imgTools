/* pages/models.js —— 环境与模型：按 env.json 体检 → 一键补齐缺的依赖与权重
   换电脑时 git 只带走代码，.venv/ 和 models/ 都不进仓库；这一页就是「clone 之后点一下」。
   体检与补全都在后端（env_check / env_fix），这里只管发起、分组显示、刷新。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

let envItems=null, env=null, envAt=null, dir='', mdl=null;

const ST={ok:['on','ok','就绪'],miss:['','bad','没装'],part:['','bad','待补'],warn:['','','提醒']};
const GROUPS=['运行环境','依赖包','模型权重','目录'];

function envRow(it,i){
  const s=ST[it.state]||ST.warn;
  const fixable=(it.state==='miss'||it.state==='part')&&it.fix&&it.fix.kind!=='none';
  return `<div class="mrow">
    <div class="minfo"><b>${esc(it.label)}</b>
      <span class="mut fine">${esc(it.detail)}</span></div>
    <span class="grow"></span>
    ${fixable?'<button class="btn sm" onclick="MIC.env.fixAt('+i+')">'+ic('down','s')+'补这项</button>':''}
    <span class="pill ${s[0]}"><span class="dot ${s[1]}"></span>${s[2]}</span>
  </div>`;
}

function envBody(){
  if(envItems===null)return '<div class="empty">正在体检 …</div>';
  const out=[];
  GROUPS.forEach(g=>{
    const rows=envItems.map((it,i)=>({it:it,i:i})).filter(x=>x.it.group===g);
    if(!rows.length)return;
    out.push('<div class="egroup">'+g+'</div>'+rows.map(x=>envRow(x.it,x.i)).join(''));
  });
  return out.join('');
}

MIC.registerPage('models',{
  title:'环境与模型',sub:'env.json 体检 · 一键补齐 · hf-mirror 下载器',icon:'db',
  render(){
    const s=MIC.s.st;
    const todo=(s.env_todo==null?(env?env.todo.length:null):s.env_todo)||0;
    const bar='<div class="bar"><span class="mut fine">清单 env.json · 体检于 '
        +(envAt?envAt.toLocaleTimeString('zh-CN',{hour12:false}):'…')+'</span><span class="grow"></span>'+
      '<button class="btn sm gho" onclick="MIC.env.check()">'+ic('refresh','s')+'重新体检</button>'+
      '<button class="btn sm '+(todo?'pri':'gho')+'" '+(s.env_busy?'disabled':'')+
        ' onclick="MIC.env.fixAll()">'+ic('down','s')+(s.env_busy?'补全中…':(todo?'一键补齐 '+todo+' 项':'环境已就绪'))+
      '</button></div>';
    const envCard=C.card('环境体检','power',bar+envBody(),
      {note:todo?('还差 '+todo+' 项'+(env&&env.gb?'，约 '+env.gb+' GB':'')+' · 点「一键补齐」后台下载，进度看下面日志')
        :'代码 + 依赖 + 权重齐了，换电脑就这一屏'});
    const list=mdl===null?'<div class="empty">正在扫描 models/ …</div>'
      :(mdl.length?mdl.map(row).join(''):'<div class="empty">models/ 下还没有模型 · 用下面的下载器拉一个</div>');
    const body=
      '<div class="bar"><span class="mut fine">'+esc(dir||'models/')+'</span><span class="grow"></span>'+
      '<button class="btn sm gho" onclick="MIC.models.refresh()">'+ic('refresh','s')+'重新扫描</button></div>'+
      list+
      (s.model_loaded?'<div class="hint" style="margin-top:10px">⚠️ 显存里已载入模型：切换激活后要「卸载模型」再载入才生效</div>':'');
    const dl=
      C.field('仓库 ID','<input class="inp" id="dl-repo" value="Qwen/Qwen-Image-2.1-Turbo" placeholder="org/name">','HuggingFace 上的 org/name')+
      C.field('本地目录名','<input class="inp" id="dl-name" placeholder="例如 Qwen-Image-2.1-Turbo">','留空=用仓库名末段')+
      '<div class="btnrow"><button class="btn pri" onclick="MIC.models.start()">'+
        ic('down','s')+'开始下载（断点续传）</button>'+
      '<span class="mut fine">　走 hf-mirror，中断自动重连，进度看下面日志</span></div>';
    return envCard+
      C.card('本机模型','db',body,{tight:true})+
      C.card('下载新模型','down',dl)+
      C.logcard('sys','体检 / 下载 / 系统日志');
  },
  mount(){
    if(!mdl)MIC.models.refresh();
    if(!env)MIC.env.check();
  },
});

MIC.env={
  check(){
    MIC.api.envCheck().then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'体检失败');return;}
      envItems=r.items;env=r;envAt=new Date();
      MIC.render();
    }).catch(()=>MIC.toast('体检失败'));
  },
  fixAt(i){
    const it=(envItems||[])[i];if(!it)return;
    MIC.env._go([it.key]);
  },
  fixAll(){
    if(!(env&&env.todo.length)){MIC.toast('没有要补的项');return;}
    MIC.env._go(env.todo);
  },
  _go(keys){
    MIC.api.envFix(keys).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'补全没起来');return;}
      if(!r.count){MIC.toast('没有需要补的');return;}
      MIC.s.st.env_busy=true;MIC.s.st.env_todo=keys.length;
      MIC.toast('补全已在后台开始（'+r.count+' 项），进度看日志');
      MIC.render();
    }).catch(()=>MIC.toast('补全没起来'));
  },
};

function row(it,i){
  const ok=it.index&&it.shards>0;
  return `<div class="mrow">
    <div class="minfo"><b>${esc(it.name)}</b>
      <span class="mut fine">${it.gb} GB · ${it.shards} 个权重分片 · ${ok?'文件齐全':'缺 model_index.json 或分片，校验未过'}</span></div>
    <span class="grow"></span>
    ${it.active?'<span class="pill on"><span class="dot ok"></span>激活中</span>'
      :'<button class="btn sm" onclick="MIC.models.activate('+i+')">'+ic('power','s')+'设为激活</button>'}
    <button class="btn sm gho" onclick="MIC.models.openDir(${i})">${ic('folder','s')}目录</button>
  </div>`;
}

MIC.models={
  refresh(){
    MIC.api.modelsList().then(r=>{
      if(r&&r.ok){mdl=r.items;dir=r.dir;}
      MIC.render();
    }).catch(()=>{mdl=[];MIC.render();});
  },
  activate(i){
    const it=(mdl||[])[i];if(!it)return;
    MIC.api.modelsSetActive(it.name).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'切换失败');return;}
      if(r.cfg)MIC.form.applyCfg(r.cfg);
      MIC.toast('已设为激活：'+it.name);
      MIC.models.refresh();
    }).catch(()=>MIC.toast('切换失败'));
  },
  openDir(i){
    const it=(mdl||[])[i];if(!it||!dir)return;
    MIC.api.openPath(dir+'/'+it.name).catch(()=>{});
  },
  start(){
    const repo=(MIC.$('dl-repo')||{}).value||'';
    const name=(MIC.$('dl-name')||{}).value||'';
    if(!repo.trim()){MIC.toast('先填仓库 ID');return;}
    MIC.api.modelsDownload(repo.trim(),name.trim()).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'启动下载失败');return;}
      MIC.toast('下载已在后台开始，进度看日志');
      MIC.render();
    }).catch(()=>MIC.toast('启动下载失败'));
  },
};
})();
