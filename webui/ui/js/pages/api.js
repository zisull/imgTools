/* pages/api.js —— API 服务：开关 / 局域网 / 端口 / Bearer 令牌 / curl 示例
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
  const u=url(),t=(MIC.s.cfg.api||{}).token||'<token>';
  return [
'# 1) 提交出图任务（异步：立刻回 task_id，出图约 20~30 秒）',
`curl -X POST ${u}/v1/images/generations \\`,
`  -H "Authorization: Bearer ${t}" \\`,
'  -H "Content-Type: application/json" \\',
'  -d \'{"prompt":"a red fox in the snow","size":"512x512","n":1}\'',
'',
'# 2) 轮询任务（status: queued/running/done/failed，done 里带 images[].id）',
`curl ${u}/v1/tasks/<task_id> -H "Authorization: Bearer ${t}"`,
'',
'# 3) 下载结果 PNG',
`curl -o fox.png ${u}/v1/images/<image_id> -H "Authorization: Bearer ${t}"`,
'',
'# 编辑图：multipart，参考图 ≤10 张（重复 -F image=@…），res 只认 512/768',
`curl -X POST ${u}/v1/images/edits \\`,
`  -H "Authorization: Bearer ${t}" \\`,
'  -F "prompt=turn the sketch into a photorealistic yacht" \\',
'  -F "res=512" -F "image=@ref.png"',
'',
'# 体检（不需要令牌）',
`curl ${u}/v1/health`,
].join('\n');
}

MIC.registerPage('api',{
  title:'API 服务',sub:'FastAPI 对外接口 · Bearer 令牌 · 异步任务',icon:'globe',
  render(){
    const a=MIC.s.cfg.api||{}, on=!!MIC.s.st.api_on;
    const svc=
      C.strow('服务状态',`<span class="dot ${on?'ok':'run'}"></span>`+
        `<span>${on?'运行中 · '+esc(MIC.s.st.api_url):'已停止'}</span>`)+
      C.strow('服务开关',`<div class="sw ${a.enabled?'on':''}" onclick="MIC.apiSrv.setEnabled(${!a.enabled})"></div>`)+
      C.strow('局域网访问',`<div class="sw ${a.lan?'on':''}" onclick="MIC.apiSrv.setLan(${!a.lan})"></div>`+
        `<span class="mut fine">　开=绑 0.0.0.0，同网段设备可用；关=只监听 127.0.0.1</span>`)+
      C.field('端口',C.num('api.port','tcp'),'改完端口点下面按钮才生效')+
      '<div class="btnrow"><button class="btn" onclick="MIC.apiSrv.applyPort()">'+
        ic('refresh','s')+'应用端口并重启服务</button></div>';
    const tok=
      C.field('Bearer 令牌','<div class="inrow"><code class="kcode">'+
        esc(a.token||'（开启服务后自动生成）')+'</code>'+
        '<button class="btn sm" onclick="MIC.apiSrv.copyToken()">'+ic('copy','s')+'复制</button>'+
        '<button class="btn sm gho" onclick="MIC.apiSrv.regen()">'+ic('refresh','s')+'重新生成</button></div>',
        a.lan&&a.enabled?'⚠️ 局域网开着：令牌走的是 http 明文，仅限自家可信网络':'');
    const demo=
      '<div class="btnrow" style="margin:0 0 10px"><button class="btn sm" onclick="MIC.apiSrv.copyDemo()">'+
        ic('copy','s')+'复制全部示例</button><span class="mut fine">　示例已代入当前地址与令牌</span></div>'+
      '<div class="codebox">'+esc(curlText())+'</div>';
    return C.card('服务','power',svc)+
      C.card('鉴权','key',tok)+
      C.card('端点与 curl 示例','globe',demo,{tight:true})+
      C.logcard('gen,sys','任务日志（UI 与 API 同一条流）');
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
  applyPort(){
    const el=MIC.$('api-port')||document.querySelector('#view [data-k="api.port"]');
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
