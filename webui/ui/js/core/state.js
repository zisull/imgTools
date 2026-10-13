/* core/state.js —— 前端唯一的数据中心：配置、后端状态快照、日志环形缓冲、画廊缓存 */
(function(){
const MIC=window.MIC=window.MIC||{};

MIC.s={
  cfg:null,                       // 后端 DEFAULT_CFG 合并后的配置
  version:'',
  st:{
    running:null,                 // null | 'load' | 'gen'
    status:'就绪',
    done:0,total:0,               // 去噪步数进度（8 或 40）
    model_loaded:false,
    model_name:'',
    quant:'fp8',
    vram_used:0,vram_total:12,    // GB，概览药丸与显存条用
    img_count:0,                  // 画廊张数
    last_sec:0,                   // 上一张耗时（秒）
    last_image:'',                // 上一张绝对路径
    api_on:false,api_url:'',
  },
  logs:[],                        // [{t,text,key}]
  gal:null,                       // 画廊列表缓存（进画廊页/生成收尾后刷新）
  lastThumb:null,                 // {path,url} 上一张预览的 data:（按需取，不进轮询）
  cursor:0,
  pollTimer:null,polling:false,lastPoll:0,
  tailRun:'',                     // 上一次轮询刚收尾的任务名（给收尾日志认账用）
};

/* 每并一次状态就把「刚收尾」这件事标一下（只活过一次轮询，见 pushLogs） */
MIC.mergeState=function(s){
  const prev=MIC.s.st.running;
  if(s)Object.assign(MIC.s.st,s);
  MIC.s.tailRun=prev&&!MIC.s.st.running?prev:'';
};

/* 收日志：按当前运行任务打标签，空闲时的系统类日志归到 sys。
   轮询是先并状态再收日志，收尾那几条（✅ 完成 / ── 结束 ──）到手时 running 已经清空，
   照当前值标就把它们推去了 sys —— 生成页那栏就永远缺个尾巴。
   所以「这一批日志到达时正好观察到任务结束」的话，仍记到刚结束那个任务名下。 */
MIC.pushLogs=function(list){
  const run=MIC.s.st.running||MIC.s.tailRun;
  (list||[]).forEach(l=>{
    MIC.s.logs.push({t:l[1],text:l[2],key:run||'sys'});
  });
  if(MIC.s.logs.length>2000)MIC.s.logs.splice(0,MIC.s.logs.length-2000);
};

MIC.logsOf=function(keys){
  if(!keys)return MIC.s.logs;
  return MIC.s.logs.filter(l=>keys.indexOf(l.key)>=0);
};
MIC.clearLogs=function(keys){
  if(!keys){MIC.s.logs=[];return;}
  MIC.s.logs=MIC.s.logs.filter(l=>keys.indexOf(l.key)<0);
};
})();
