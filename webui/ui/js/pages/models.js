/* pages/models.js —— 模型管理：models/ 目录清单 + 切换激活 + hf-mirror 断点续传下载
   下载走后端后台线程（models_download），进度打日志；这里只管发起与刷新列表。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

let items=null, dir='';

function row(it,i){
  const ok=it.index&&it.shards>0;
  return `<div class="mrow">
    <div class="minfo"><b>${esc(it.name)}</b>
      <span class="mut fine">　${it.gb} GB · ${it.shards} 个权重分片 · ${ok?'文件齐全':'缺 model_index.json 或分片，校验未过'}</span></div>
    <span class="grow"></span>
    ${it.active?'<span class="pill on"><span class="dot ok"></span>激活中</span>'
      :'<button class="btn sm" onclick="MIC.models.activate('+i+')">'+ic('power','s')+'设为激活</button>'}
    <button class="btn sm gho" onclick="MIC.models.openDir(${i})">${ic('folder','s')}目录</button>
  </div>`;
}

MIC.registerPage('models',{
  title:'模型管理',sub:'models/ 整合包目录 · hf-mirror 下载器',icon:'db',
  render(){
    const s=MIC.s.st;
    const list=items===null?'<div class="empty">正在扫描 models/ …</div>'
      :(items.length?items.map(row).join(''):'<div class="empty">models/ 下还没有模型 · 用下面的下载器拉一个</div>');
    const body=
      '<div class="bar"><span class="mut fine">'+esc(dir||'models/')+'</span><span class="grow"></span>'+
      '<button class="btn sm gho" onclick="MIC.models.refresh()">'+ic('refresh','s')+'重新扫描</button></div>'+
      list+
      (s.model_loaded?'<div class="hint" style="margin-top:10px">⚠️ 显存里已载入模型：切换激活后要「卸载模型」再载入才生效</div>':'');
    const dl=
      C.field('仓库 ID（HuggingFace 上的 org/name）','<input class="inp" id="dl-repo" value="Qwen/Qwen-Image-2.1-Turbo" placeholder="org/name">')+
      C.field('本地目录名（留空=用仓库名末段）','<input class="inp" id="dl-name" placeholder="例如 Qwen-Image-2.1-Turbo">')+
      '<div class="btnrow"><button class="btn pri" onclick="MIC.models.start()">'+
        ic('down','s')+'开始下载（断点续传）</button>'+
      '<span class="mut fine">　走 hf-mirror，中断自动重连，进度看下面日志</span></div>';
    return C.card('本机模型','db',body,{tight:true})+
      C.card('下载新模型','down',dl)+
      C.logcard('sys','下载 / 系统日志');
  },
  mount(){if(!items)MIC.models.refresh();},
});

MIC.models={
  refresh(){
    MIC.api.modelsList().then(r=>{
      if(r&&r.ok){items=r.items;dir=r.dir;}
      MIC.render();
    }).catch(()=>{items=[];MIC.render();});
  },
  activate(i){
    const it=(items||[])[i];if(!it)return;
    MIC.api.modelsSetActive(it.name).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'切换失败');return;}
      if(r.cfg)MIC.form.applyCfg(r.cfg);
      MIC.toast('已设为激活：'+it.name);
      MIC.models.refresh();
    }).catch(()=>MIC.toast('切换失败'));
  },
  openDir(i){
    const it=(items||[])[i];if(!it||!dir)return;
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
