/* pages/settings.js —— 设置：引擎与目录 / API 服务（M4 接线）/ 界面与软件名 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

MIC.registerPage('settings',{
  title:'设置',sub:'模型、输出与对外接口',icon:'cog',
  render(){
    const s=MIC.s.st, a=MIC.s.cfg.api||{};
    return C.card('引擎与目录','power',
      C.field('模型目录',C.pathrow('console.model_dir','models/Qwen-Image-2.1-Turbo','dir'),'下载好的权重文件夹')+
      C.field('输出目录',C.pathrow('console.output_dir','outputs','dir'),'成图落盘位置')+
      `<div class="grid3">
        ${C.field('量化方式',C.seg('console.quant',[['fp8','fp8（12G 必选）'],['none','不量化（会爆显存）']]))}
        ${C.field('CPU offload',C.sw('console.offload'))}
        ${C.field('载入状态','<span class="pill '+(s.model_loaded?'on':'')+'"><span class="dot '+
          (s.model_loaded?'ok':'')+'"></span>'+(s.model_loaded?'已在显存':'未载入')+'</span>')}
      </div>
      <div class="hint">fp8+offload 是实测唯一在 RTX 4070 12G 上达标（≤1 分钟/张）的组合；bf16/bnb8 会溢到共享内存慢 6 倍以上。</div>`)
      +C.card('API 服务','key',
      `<div class="status">
        ${C.strow('服务状态',`<span class="dot ${s.api_on?'ok':''}"></span><span>${
          s.api_on?'运行中 · '+esc(s.api_url):'未启动'}</span>`)}
        ${C.strow('绑定',`<span>${a.lan?'0.0.0.0（同网段可用）':'127.0.0.1（只本机）'} · 端口 ${esc(a.port)}</span>`)}
      </div>
      <div class="btnrow"><button class="btn" onclick="MIC.nav.goto('api')">${ic('globe','s')}去「API 服务」页</button></div>
      <div class="hint">开关、端口、令牌都只在「API 服务」页改：那里改完会立刻重建监听并给出 curl 示例。这一页以前那两个输入框（监听地址/令牌）后端根本不读，留着只会指错路，已撤掉。</div>`,
      {note:s.api_on?'运行中':'未启动'})
      +C.card('界面','palette',
      C.field('软件名',
        `<div class="inrow"><input class="inp" id="appName" value="${esc(MIC.s.cfg.app_title)}">`+
        `<button class="btn" onclick="MIC.app.rename()">应用</button></div>`,
        '窗口与顶栏标题，也可双击左上角改名')+
      C.field('通知',C.chk('notify','任务结束时弹轻提示')))
      +C.card('关于','book',
      `<div class="kv"><span>版本</span><b>v${MIC.esc(MIC.s.version||'-')}</b></div>
       <div class="kv"><span>模型</span><b>Qwen-Image-2.1-Turbo（Qwen Research License，非商用）</b></div>
       <div class="kv"><span>硬件基线</span><b>RTX 4070 12G · 32G DDR5 · 1024 档约 28 秒/张</b></div>`);
  },
});
})();
