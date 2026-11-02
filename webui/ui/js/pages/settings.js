/* pages/settings.js —— 设置：引擎与目录 / API 服务（含鉴权与 curl 示例）/ 界面与软件名
   「API 服务」原来单开一页，其实只有三块控件 + 一段示例：并到设置里同一屏就能改完看完。
   控件不走 data-k 自动落盘：每一项改动都要求后端「立即生效」（起停监听），
   统一经 MIC.apiSrv → api_set，回包里的 state 是唯一真相。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

function url(){
  const a=MIC.s.cfg.api||{};
  return MIC.s.st.api_url||('http://'+(a.lan?'局域网IP':(a.host||'127.0.0.1'))+':'+(a.port||8765));
}
function curlText(){
  const u=url(),a=MIC.s.cfg.api||{};
  const t=a.token||'<token>';
  /* 免令牌模式下这些示例原样贴进终端会多一个没用的头（后端不校验，但别误导人） */
  const auth=a.no_token?'':'-H "Authorization: Bearer '+t+'" ';
  const A=auth.trim();
  const jh='  '+auth+'-H "Content-Type: application/json" \\';
  return [
'# 1) 提交出图任务（异步：立刻回 task_id，出图约 20~30 秒）'+(a.no_token?'（当前免令牌，鉴权头已省）':''),
`curl -X POST ${u}/v1/images/generations \\`,
jh,
'  -d \'{"prompt":"a red fox in the snow","size":"512x512","n":1}\'',
'',
'# 同步直出（同步客户端用这个）：加 response_format:"b64_json"，',
'# 等出图才返回，形状就是 OpenAI 的 {created, data:[{b64_json}]}；极速档 512² 一两秒',
`curl -X POST ${u}/v1/images/generations \\`,
jh,
'  -d \'{"prompt":"a red fox in the snow","size":"512x512","response_format":"b64_json"}\'',
'',
'# 选引擎：请求里带 "engine":"moss"（或 OpenAI 风格 "model":"moss"）；',
'# 都不带时用设置页的「默认引擎」，再回落控制台当前激活的引擎。',
'# 尺寸除预设档外认自定义 WxH：千问 64~4096，Moss 64~2048（16 的倍数，零头自动下取整对齐）',
'',
'# ── 接本地游戏 / AI 客户端（一次配好即可）：把下面这段并进它的 imageProviders ──',
'{ "id": "img-moss", "name": "Moss 生图", "enabled": true,',
`  "baseUrl": "${u}/v1", "apiKey": "", "model": "moss", "apiStyle": "openai", "priority": 1 },`,
'# 它走同步 b64_json；调用方自己的生图配置里 baseUrl 也换成同一个地址',
'',
'# 2) 轮询任务（status: queued/running/done/failed，done 里带 images[].id）',
`curl ${u}/v1/tasks/<task_id> ${A}`,
'',
'# 3) 下载结果 PNG',
`curl -o fox.png ${u}/v1/images/<image_id> ${A}`,
'',
'# 透明底素材：同一个端点加 "mode":"rgba"，出图直接带 alpha 通道',
'# 编辑图：multipart，参考图 ≤10 张（重复 -F image=@…）、单张 ≤25MB、单次合计 ≤100MB，res 只认 512/768',
`curl -X POST ${u}/v1/images/edits \\`,
`  ${A} \\`,
'  -F "prompt=turn the sketch into a photorealistic yacht" \\',
'  -F "res=512" -F "image=@ref.png"',
'',
'# Moss 生图（内嵌 ComfyUI，工作流隐藏）：带 engine:"moss"，quality=fast(8步)/mid(25步)/full(50步)',
'# 首次提交会自动拉起 ComfyUI；若当前是「让出显存档」也会先唤醒，慢的就第一次',
`curl -X POST ${u}/v1/images/generations \\`,
jh,
'  -d \'{"engine":"moss","prompt":"an anime girl with silver hair","size":"1024x1024","quality":"fast","n":1}\'',
'',
'# Moss 引擎状态（档位 / ComfyUI 是否拉起 / 权重是否就绪）',
`curl ${u}/v1/moss ${A}`,
'',
'# 能力清单（各引擎认哪些尺寸/档位、当前默认值）：',
`curl ${u}/v1/models ${A}`,
'',
'# 体检（不需要令牌；engine/tier/comfyui_on 会标出当前激活的是千问还是 Moss）',
`curl ${u}/v1/health`,
'',
'# 长跑上限：排队 >50 回 429（先取已完成的任务）；超体积回 413；',
'# 任务单只留最近 200 张或 24 小时，超出的老任务连结果图引用一起丢，所以要尽快取图',
].join('\n');
}

MIC.registerPage('settings',{
  title:'设置',sub:'界面、目录与对外接口',icon:'cog',
  render(){
    const s=MIC.s.st, a=MIC.s.cfg.api||{};
    const svc=
      C.strow('服务状态',`<span class="dot ${s.api_on?'ok':''}"></span><span>${
        s.api_on?'运行中 · '+esc(s.api_url):'未启动'}</span>`)+
      C.strow('服务开关',`<div class="sw ${a.enabled?'on':''}" onclick="MIC.apiSrv.setEnabled(${!a.enabled})"
        title="开=在本机起一个 OpenAI 风格的出图接口；关=不监听任何端口"></div>`)+
      C.field('默认引擎',
        `<select class="inp" onchange="MIC.apiSrv.setDefEngine(this.value)">${['follow','qwen','moss'].map(v=>
          `<option value="${v}"${(a.def_engine||'follow')===v?' selected':''}>${
            ({follow:'跟随控制台',qwen:'千问',moss:'Moss'})[v]}</option>`).join('')}</select>`,
        '请求里不带 engine/model 时用谁；跟随控制台=界面当前激活的引擎')+
      C.field('默认分辨率',
        `<select class="inp" onchange="MIC.apiSrv.setDefSize(this.value)">${
          ['512x512','768x768','1024x1024','576x1024','832x1216','1216x832',
           '1024x1536','1536x1024','1536x1536'].map(sz=>
            `<option value="${sz}"${(a.def_size||'1024x1024')===sz?' selected':''}>${sz}</option>`).join('')}</select>`,
        '请求里不带 size 时用它；各引擎按自己范围再校一遍')+
      C.fold('高级','cog',
        C.strow('局域网访问',`<div class="sw ${a.lan?'on':''}" onclick="MIC.apiSrv.setLan(${!a.lan})"
          title="开=绑 0.0.0.0，同网段设备可用；关=只监听 127.0.0.1（默认）。内嵌 ComfyUI 任何时候都不对外。"></div>`)+
        C.strow('免令牌访问',`<div class="sw ${a.no_token?'on':''}" onclick="MIC.apiSrv.setNoToken(${!a.no_token})"
          title="开了不校验 Bearer 令牌：本机调试省事；局域网开着时别开"></div>`)+
        C.field('Bearer 令牌','<div class="inrow"><code class="kcode">'+
          esc(a.token||'（开启服务后自动生成）')+'</code>'+
          '<button class="btn sm" onclick="MIC.apiSrv.copyToken()">'+ic('copy','s')+'复制</button>'+
          '<button class="btn sm gho" onclick="MIC.apiSrv.regen()">'+ic('refresh','s')+'重新生成</button></div>',
          a.no_token?'免令牌开着：令牌暂不校验（要安全就先把它关掉）'
                    :'除 /v1/health 外全部端点都要带这个令牌')+
        C.field('端口',C.num('api.port','tcp'),'改完要点下面那颗才生效（重启监听）')+
        '<div class="btnrow"><button class="btn" onclick="MIC.apiSrv.applyPort()">'+
          ic('refresh','s')+'应用端口并重启服务</button></div>',
        '局域网 · 免令牌 · 令牌 · 端口');
    const demo=
      '<div class="btnrow" style="margin:0 0 10px"><button class="btn sm" onclick="MIC.apiSrv.copyDemo()">'+
        ic('copy','s')+'复制全部示例</button></div>'+
      '<div class="codebox">'+esc(curlText())+'</div>';
    /* 双栏：左=目录、界面、关于，右=对外 API（吸顶） */
    /* 千问环境关着时量化/offload/载入状态跟这台机器无关，收走别占地方 */
    const qwenOn=MIC.nav.envOn().qwen!==false;
    const quantRow=qwenOn?`<div class="grid3">
          ${C.field('量化方式',C.seg('console.quant',[['fp8','fp8（12G 必选）'],['none','不量化（会爆显存）']]),
            'fp8+offload 是 12G 卡上唯一达标的组合；bf16/bnb8 溢出到共享内存，慢 6 倍以上')}
          ${C.field('CPU offload',C.sw('console.offload'),'权重按需换入换出内存：稍慢，但 12G 装得下')}
          ${C.field('载入状态','<span class="pill '+(s.model_loaded?'on':'')+'"><span class="dot '+
            (s.model_loaded?'ok':'')+'"></span>'+(s.model_loaded?'已在显存':'未载入')+'</span>')}
        </div>`
      :C.field('载入状态','<span class="pill '+(s.model_loaded?'on':'')+'"><span class="dot '+
            (s.model_loaded?'ok':'')+'"></span>'+(s.model_loaded?'已在显存':'未载入')+'</span>',
        '量化与 offload 是千问的参数；Moss 的档位在「生图」页切引擎后出现');
    /* 开关走后端 env_set（它要顺手放显存、重跑体检），不能当普通表单字段存 */
    const sw=(id,label)=>{const on=MIC.nav.envOn()[id]!==false;
      return `<span class="envsw"><span class="sw ${on?'on':''}" title="关掉：不体检、不提醒、功能页收起"
          onclick="MIC.env.set('${id}',${on?0:1})"></span>${label}</span>`;};
    return C.duo(
      C.card('引擎与目录','power',
        C.field('模型目录',C.pathrow('console.model_dir','envs/qwen/models/Qwen-Image-2.1-Turbo','dir'),'下载好的权重文件夹')+
        C.field('输出目录',C.pathrow('console.output_dir','outputs','dir'),'成图与成片落盘位置')+
        quantRow)
      +C.card('界面','palette',
        C.field('模型环境',sw('qwen','千问')+sw('moss','Moss')+sw('h3','H3'),
          '关掉的那一路不体检、不提醒，功能页也收起；明细与一键补齐在「环境」那几页')+
        C.field('欢迎页','<button class="btn sm" onclick="MIC.welcome.review()">'+
          ic('refresh','s')+'重看选环境那一屏','只有一开始那次会拦住你选路；这里点了才再看得到'),
        C.field('软件名',
          `<div class="inrow"><input class="inp" id="appName" value="${esc(MIC.s.cfg.app_title)}">`+
          `<button class="btn" onclick="MIC.app.rename()">应用</button></div>`,
          '窗口与顶栏标题，也可双击左上角改名')+
        C.field('通知',C.chk('notify','任务结束时弹轻提示')))
      +C.card('关于','book',
        `<div class="kv"><span>版本</span><b>v${esc(MIC.s.version||'-')}</b></div>
         <div class="kv"><span>模型</span><b>Qwen-Image-2.1-Turbo（Qwen Research License，非商用）· MOSS-Image · MiniMax H3（后两个走内嵌 ComfyUI）</b></div>
         <div class="kv"><span>建议配置</span><b>NVIDIA 12G 显存级 · 32G 以上内存 · 1024 档：千问约半分钟，Moss 约 3 秒</b></div>`),
      C.card('API 服务','globe',svc,{note:s.api_on?'运行中':'未启动'})
      +C.foldcard('端点与 curl 示例','globe',demo,'要接外部程序再展开'));
  },
});

MIC.apiSrv={
  done(r){
    if(!r)return;
    if(!r.ok&&r.msg)MIC.toast(r.msg);
    if(r.state){
      MIC.s.cfg.api=r.state.cfg;
      MIC.s.st.api_on=r.state.on;
      MIC.s.st.api_url=r.state.url;
    }
    MIC.render();
  },
  setEnabled(on){MIC.api.apiSet({enabled:on}).then(r=>MIC.apiSrv.done(r)).catch(()=>MIC.toast('操作失败'));},
  setLan(lan){MIC.api.apiSet({lan:lan}).then(r=>MIC.apiSrv.done(r)).catch(()=>MIC.toast('操作失败'));},
  setNoToken(on){MIC.api.apiSet({no_token:on}).then(r=>MIC.apiSrv.done(r)).catch(()=>MIC.toast('操作失败'));},
  setDefEngine(v){MIC.api.apiSet({def_engine:v}).then(r=>{MIC.apiSrv.done(r);if(r&&!r.ok)MIC.toast(r.msg);}).catch(()=>MIC.toast('操作失败'));},
  setDefSize(v){MIC.api.apiSet({def_size:v}).then(r=>{MIC.apiSrv.done(r);if(r&&!r.ok)MIC.toast(r.msg);}).catch(()=>MIC.toast('操作失败'));},
  applyPort(){
    const el=document.querySelector('#view [data-k="api.port"]');
    const p=parseInt(el&&el.value,10);
    if(!p||p<1||p>65535){MIC.toast('端口要给 1~65535 的数字');return;}
    MIC.api.apiSet({port:p}).then(r=>MIC.apiSrv.done(r)).catch(()=>MIC.toast('操作失败'));
  },
  regen(){MIC.api.apiTokenReset().then(r=>{MIC.apiSrv.done(r);MIC.toast('令牌已重新生成');}).catch(()=>MIC.toast('操作失败'));},
  copyToken(){
    const t=(MIC.s.cfg.api||{}).token||'';
    if(!t){MIC.toast('还没有令牌：先开启服务');return;}
    MIC.view.copy(t,'令牌已复制');
  },
  copyDemo(){MIC.view.copy(curlText(),'curl 示例已复制');},
};
})();
