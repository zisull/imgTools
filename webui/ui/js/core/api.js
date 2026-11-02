/* core/api.js —— pywebview js_api 桥
   生产：window.pywebview.api.*（Python 侧 webui/app.py 的 App 方法）
   开发：window.MIC_MOCK.*（ui/dev/mock.js，仅无桥环境生效，用于浏览器里看界面） */
(function(){
const MIC=window.MIC=window.MIC||{};

function bridge(){const w=window.pywebview;return (w&&w.api&&w.api.boot)?w.api:null;}

function call(name){
  const args=Array.prototype.slice.call(arguments,1);
  const api=bridge();
  if(api&&api[name])return api[name].apply(api,args);
  const m=window.MIC_MOCK;
  if(m&&m[name])return Promise.resolve(m[name].apply(m,args));
  return Promise.reject(new Error('接口未就绪：'+name));
}

MIC.api={
  /* 等桥接就绪。真窗口里 pywebview 注入可能比 DOM 还晚：那时提前放行等于判自己死刑
     （boot() 拿不到桥就永远停在「未连接到后端」，拖动/缩放也永远不会绑）。
     所以只有「浏览器预览挂了 mock」这一种情况才用 1.2 秒兜底放行。 */
  ready(){
    if(bridge()||window.MIC_MOCK)return Promise.resolve();
    return new Promise(res=>{
      const preview=!!window.MIC_MOCK;
      window.addEventListener('pywebviewready',()=>{stop();res();},{once:true});
      const timer=setInterval(()=>{if(bridge()){stop();res();}},150);
      const fb=preview?setTimeout(()=>{stop();res();},1200):null;
      // 后端就是没起来时也要有个头：20 秒后放行，让下面把错显示出来（不然界面一直白着）
      const cap=setTimeout(()=>{stop();res();},20000);
      function stop(){clearInterval(timer);clearTimeout(cap);if(fb)clearTimeout(fb);}
    });
  },
  booted(){return !!bridge();},
  boot:()=>call('boot'),
  poll:c=>call('poll',c||0),
  refreshStats:()=>call('refresh_stats'),
  save:patch=>call('save_cfg',patch),
  pick:kind=>call('pick',kind),
  /* 拖进来的文件 → 完整路径（后端拿不到就回原因，前端只负责填框） */
  dropPath:(c,kind)=>call('drop_path',c,kind||'file'),
  /* 拖放兜底：路径解析不出来时把字节交后端代收 */
  saveDrop:(n,d)=>call('save_drop',n,d),
  setTitle:t=>call('set_title',t),
  /* 引擎：模型装卸与生成（都是后端起线程，调用即返回） */
  loadModel:()=>call('load_model'),
  unloadModel:()=>call('unload_model'),
  startGen:p=>call('start_gen',p),
  stop:key=>call('stop',key||'gen'),
  /* 引擎切换与 Moss 档位：同一时间只激活一个生图引擎；档位是 Moss 的显存分时复用 */
  setEngine:n=>call('set_engine',n),
  mossSetTier:t=>call('moss_set_tier',t),
  mossStatus:()=>call('moss_status'),
  /* 画廊：扫描输出目录；预览图统一走 thumb（data: 缩略，html= 内联页显示不了 file://） */
  thumb:(p,wide)=>call('thumb',p,wide),
  galleryList:()=>call('gallery_list'),
  galleryDelete:f=>call('gallery_delete',f||''),
  galleryUndo:()=>call('gallery_undo'),
  galleryFav:(f,on)=>call('gallery_fav',f,!!on),
  galleryClear:()=>call('gallery_clear'),
  /* 模型管理：列表/切换激活/hf-mirror 断点续传下载 */
  modelsList:()=>call('models_list'),
  modelsSetActive:n=>call('models_set_active',n),
  modelsDownload:(r,n)=>call('models_download',r,n||''),
  /* 环境体检与一键补全：清单在 ROOT/envs/，缺的包与权重由后端后台补齐 */
  /* 环境：体检/补全 + 每条模型一路的开关（关掉＝后端不体检、功能页一并收起） */
  envCheck:()=>call('env_check'),
  envFix:k=>call('env_fix',k||null),
  envSet:(i,w)=>call('env_set',i,!!w),
  /* 视频：本地 H3 出一条成片（后端起线程，调用即返回；进度走 poll） */
  videoGen:p=>call('video_gen',p),
  /* 云端账号：一只共用浏览器 + 多份登录态快照；浏览器操作全部后台线程 */
  cloudState:()=>call('cloud_state'),
  /* 视频页云端那一格要的一句话实话（有几个号、缺不缺 DrissionPage、用的哪份工作流）：
     只读档案，绝不为「看一眼」拉起浏览器 */
  cloudBrief:()=>call('cloud_brief'),
  cloudNew:n=>call('cloud_new',n||''),
  cloudLogin:id=>call('cloud_login',id||''),
  cloudSave:(id,n)=>call('cloud_save',id||'',n||''),
  cloudApply:id=>call('cloud_apply',id||''),
  cloudCheck:id=>call('cloud_check',id||''),
  cloudDelete:id=>call('cloud_delete',id||''),
  cloudRename:(id,n)=>call('cloud_rename',id||'',n||''),
  cloudBackups:id=>call('cloud_backups',id||''),
  cloudRestore:(id,ts)=>call('cloud_restore',id||'',ts||''),
  cloudKeySet:(id,k)=>call('cloud_key_set',id||'',k||''),
  cloudKeyClear:id=>call('cloud_key_clear',id||''),
  cloudKeepNow:()=>call('cloud_keep_now'),
  cloudBrowserStart:()=>call('cloud_browser_start'),
  cloudBrowserStop:()=>call('cloud_browser_stop'),
  cloudAuthNames:id=>call('cloud_auth_names',id||''),
  openPath:p=>call('open_path',p),
  openUrl:u=>call('open_url',u),
  /* API 服务：状态/开关/令牌（后端即时重启监听，都返回最新 state） */
  apiState:()=>call('api_state'),
  apiSet:p=>call('api_set',p),
  apiTokenReset:()=>call('api_token_reset'),
  /* 无框窗口：几何与拖动/缩放/窗控（逻辑像素，见 core/win.js） */
  winGeo:()=>call('win_geo'),
  winMove:(x,y)=>call('win_move',Math.round(x),Math.round(y)),
  winSet:(x,y,w,h)=>call('win_set',Math.round(x),Math.round(y),Math.round(w),Math.round(h)),
  winMin:()=>call('win_min'),
  winMax:on=>call('win_max',on===undefined?null:!!on),
  winClose:()=>call('win_close'),
};
})();
