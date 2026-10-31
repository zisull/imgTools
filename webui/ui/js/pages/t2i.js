/* pages/t2i.js —— 生图：千问与 Moss 两个引擎共用这一页
   Moss 原来单开一页，其实两边是同一件事（写提示词、挑尺寸、点开始），
   差别只在引擎与档位——合成一页，切换引擎只换掉档位与尺寸表。
   表单绑在当前引擎那一块上：千问写 gen.*，Moss 写 moss.*。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

const QW_SIZES=[
  {code:'512x512',name:'512×512 草图'},
  {code:'768x768',name:'768×768 中幅'},
  {code:'1024x1024',name:'1024×1024 标准'},
  {code:'576x1024',name:'576×1024 竖 9:16'},
  {code:'1024x1536',name:'1024×1536 竖 2:3'},
  {code:'1536x1024',name:'1536×1024 横 3:2'},
  {code:'1536x1536',name:'1536×1536 高清'},
  {code:'custom',name:'自定义宽 × 高'},
];
const MOSS_SIZES=[
  {code:'512x512',name:'512×512 草图'},
  {code:'768x768',name:'768×768 中幅'},
  {code:'1024x1024',name:'1024×1024 标准'},
  {code:'832x1216',name:'832×1216 竖版'},
  {code:'1216x832',name:'1216×832 横版'},
  {code:'1024x1536',name:'1024×1536 竖 2:3'},
  {code:'1536x1024',name:'1536×1024 横 3:2'},
  {code:'custom',name:'自定义宽 × 高'},
];

/* 引擎那条灯：进程活着不等于权重上卡，说清是没跑、在搬权重、还是已常驻 */
function engineNote(s,on){
  if(!on)return '未激活';
  if(s.engine!=='moss')return s.model_loaded?'权重在显存':'模型未载入，点开始会自动载入';
  if(!s.comfyui_on)return 'ComfyUI 已停，点开始会自动拉起';
  if(!s.comfyui_loaded)return '正在把权重搬上显存';
  return 'ComfyUI 在跑，权重已常驻';
}

function engineBar(){
  const s=MIC.s.st,m=String(MIC.s.cfg.console_mode||'both');
  const both=m==='both';
  const seg='<div class="seg">'+
    [['qwen','千问'],['moss','Moss']].filter(x=>both||x[0]===m).map(([v,label])=>
      `<button class="${s.engine===v?'on':''}" onclick="MIC.engine.set('${v}')">${label}</button>`).join('')+
    '</div>';
  return `<div class="enginebar">${seg}
    <span class="mut fine" style="flex:1;min-width:160px">${engineNote(s,true)} · `+
    `${esc(vramText(s))}</span></div>`;
}
function vramText(s){
  return s.vram_used!=null&&s.vram_total?(s.vram_used+'/'+s.vram_total+'G 显存'):'';
}

/* Moss 的两条轴以前各摆一排分段按钮在引擎条上，横着吃掉一整行。
   这里合成一个下拉：极速/均衡/精修是日常档里的出图质量，
   「让出显存」是把 ComfyUI 停掉、把 12G 交给外部文字模型软件（实测整卡 10897→2174 MiB）。 */
const MOSS_GRADE=[
  {code:'fast',name:'极速 · 8 步'},
  {code:'mid',name:'均衡 · 25 步'},
  {code:'full',name:'精修 · 50 步'},
  {code:'yield',name:'让出显存'},
];
function gradeSel(){
  const v=String(MIC.s.st.moss_tier||'daily')==='yield'
    ?'yield':String(MIC.mget(MIC.s.cfg,'moss.quality')||'fast');
  return `<select class="inp" onchange="MIC.engine.gradePick(this.value)">${MOSS_GRADE.map(o=>
    `<option value="${o.code}"${o.code===v?' selected':''}>${esc(o.name)}</option>`).join('')}</select>`;
}

/* 副标题是活的：当前引擎、档位、画幅、权重状态一眼看完——这一屏到底会怎么出图，
   不用去逐个控件上扫一遍。watchStruct 认的就是这几个数，所以它们一变这行字就跟着变。 */
function liveSub(){
  const s=MIC.s.st,moss=s.engine==='moss',K=moss?'moss':'gen';
  const sz=String(MIC.mget(MIC.s.cfg,K+'.size')||'1024x1024');
  const dim=sz==='custom'?(MIC.mget(MIC.s.cfg,K+'.cw')+'×'+MIC.mget(MIC.s.cfg,K+'.ch'))
      :sz.replace('x','×');
  const grade=moss?(String(s.moss_tier||'daily')==='yield'?'让出显存'
      :({fast:'极速 8 步',mid:'均衡 25 步',full:'精修 50 步'})[String(MIC.mget(MIC.s.cfg,'moss.quality')||'fast')])
    :MIC.mget(MIC.s.cfg,'gen.steps')+' 步';
  const rgba=!moss&&String(MIC.mget(MIC.s.cfg,'gen.mode'))==='rgba'?' · 透明 PNG':'';
  const ready=moss?(s.comfyui_on?(s.comfyui_loaded?'权重常驻':'权重搬运中'):'引擎已停')
      :(s.model_loaded?'权重在显存':'权重未载入');
  return (moss?'Moss':'千问')+' · '+grade+rgba+' · '+dim+' · '+ready;
}

MIC.registerPage('t2i',{
  title:'生图',sub:liveSub,icon:'flower',
  render(){
    const s=MIC.s.st,run=!!s.running,moss=s.engine==='moss',K=moss?'moss':'gen';
    const installed=s.moss_installed;
    const rgba=!moss&&String(MIC.mget(MIC.s.cfg,'gen.mode'))==='rgba';
    /* 透明档不是抠图：全靠提示词里那句「纯透明背景」，所以提示词的示范也换一个写法 */
    /* 切档要整页重画：示范提示词和提醒都跟着换，seg 的 rr 标记就是干这个的 */
    const mode=moss?'':C.field('输出格式',
      C.seg('gen.mode',[['gen','普通'],['rgba','透明 PNG']],true),
      '透明底的图标、贴纸切这一档；透明底靠提示词写「纯透明背景」，不是抠图');
    const ph=rgba?'一枚扁平矢量图标，纯透明背景，边缘干净'
        :(moss?'银发少女，柔和棚拍光，眼睛细节清晰':'雨夜的霓虹小巷，湿路面反光，电影感光线');
    const sizes=moss?MOSS_SIZES:QW_SIZES;
    const custom=String(MIC.mget(MIC.s.cfg,K+'.size'))==='custom';
    const row='<div class="grid4">'+
        C.field('尺寸',C.sizeSel(K+'.size',sizes,'',true),moss
          ?'Moss 512 约 1 秒、1024 约 3.3 秒；自定义宽高自动取整到 16 的倍数'
          :'千问 1024 约 28 秒、1536 约 77 秒；2048 在 12G 上会溢出')+
        C.field(moss?'档位':'步数',moss?gradeSel():C.sel(K+'.steps',
          [{code:'8',name:'极速 · 8 步'},{code:'40',name:'精细 · 40 步'}]),
          moss?'极速最快，25 步均衡，50 步最细；「让出显存」停掉引擎，切回来会自动重新拉起'
              :'8 步够用，40 步更细（慢 5 倍）')+
        C.field('种子',C.seedRow(K+'.seed'),'开着每次换一张新图；关掉就固定这个数，同参数复现同图')+
        C.field('张数',C.num(K+'.count','张'),'连发这么多张，每张一个不同种子')+
      '</div>';
    const adv=C.field('反向提示词',C.ta(K+'.negative',2,MIC.lib.NEG_BASE),'空着时点灵感卡会自动配一条通用的')+
        (moss?'':C.field('KV 缓存',C.chk(K+'.kv_cache','长提示词更快'),'文本编码器缓存，提示词越长省得越多'));
    const params=
      mode+
      C.field('提示词',C.ta(K+'.prompt',4,ph),'中文英文都行')+
      MIC.inspire.box(K+'.prompt')+
      row+
      (custom?'<div class="grid4">'+
        C.field('宽（px）',C.num(K+'.cw','1024'))+
        C.field('高（px）',C.num(K+'.ch','1024'))+
      '</div>':'')+
      C.fold('高级','cog',adv,'反向提示词'+(moss?'':' · KV 缓存'))+
      /* 词库原来单开一页，挑完还是得回这一页填——并进来：日常看灵感行两行 chips，
         要通览 56 条就展开这块（收起时不占一行地方） */
      C.fold('词库全览','book',MIC.inspire.panel(K+'.prompt'),'7 类 · 悬停看全句');
    const btns=moss
      ?'<button class="btn sm gho" onclick="MIC.gen.openDir(true)">'+ic('folder','s')+'Moss 输出目录</button>'
      :'<button class="btn sm gho" onclick="MIC.runner.load()">载入模型</button>'+
        '<button class="btn sm gho" onclick="MIC.runner.unload()">卸载模型</button>';
    /* Moss 那套环境（内嵌 ComfyUI 与权重）没补齐时给一条短提示，明细都留在环境页 */
    const envNote=moss&&installed===false
      ?`<div class="notebar">${ic('db','s')}<b>Moss 环境还没补齐</b><span class="grow"></span>`+
        `<button class="btn sm pri" onclick="MIC.nav.goto('models')">去补齐</button></div>`
      :'';
    return engineBar()+envNote+C.duo(
      C.card('生成参数','flower',C.lock(run,params)+MIC.runner.action()),
      MIC.runner.runCard('',{btns:btns}));
  },
  mount(){
    /* moss_installed 是进过一次 Moss 才有的数：这一页第一次打开先问一次，
       不然环境提示永远等不到显示（老版 Moss 页的 mount 就是干这个的） */
    if(MIC.s.st.engine==='moss'&&MIC.s.st.moss_installed==null)MIC.engine.refresh();
  },
});

/* 引擎切换与档位：都是后端的长活，点完先给一句话，状态由轮询跟上来 */
MIC.engine={
  refresh(){
    MIC.api.mossStatus().then(r=>{
      if(!r||!r.ok)return;
      let chg=false;
      if(r.installed!=null&&MIC.s.st.moss_installed!==r.installed){
        MIC.s.st.moss_installed=r.installed;chg=true;}
      if(r.tier&&!MIC.s.st.moss_tier){MIC.s.st.moss_tier=r.tier;chg=true;}
      if(chg)MIC.render();          // 没变就别整页重画：白闪一次，输入焦点也没了
    }).catch(()=>{});
  },
  set(name){
    MIC.api.setEngine(name).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'切换失败');return;}
      MIC.s.st.engine=name;
      if(r.msg)MIC.toast(r.msg);
      MIC.render();
    }).catch(()=>MIC.toast('切换失败'));
  },
  tier(t){
    MIC.api.mossSetTier(t).then(r=>{
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'档位切换失败');return;}
      if(r.tier)MIC.s.st.moss_tier=r.tier;
      MIC.toast(t==='yield'?'已让出显存':'正在拉起 Moss');
      MIC.render();
    }).catch(()=>MIC.toast('档位切换失败'));
  },
  /* 一个下拉管两条轴：选质量档=回日常档（正让着显存就顺手唤醒 ComfyUI），
     选「让出显存」=只停引擎、质量档留着下次用 */
  gradePick(v){
    if(v==='yield'){MIC.engine.tier('yield');return;}
    const wasYield=String(MIC.s.st.moss_tier||'daily')==='yield';
    if(wasYield){
      /* 先让后端把显存收回来，权重上卡的同时就把质量档一起改了：
         分两步走的话中间那份旧配置可能先被这次出图用掉 */
      MIC.api.mossSetTier('daily').then(r=>{
        if(!r||!r.ok){MIC.toast((r&&r.msg)||'档位切换失败');return;}
        if(r.tier)MIC.s.st.moss_tier=r.tier;
        MIC.form.commitPath('moss.quality',v);
        MIC.toast('正在拉起 Moss · '+(v==='fast'?'极速':v==='mid'?'均衡':'精修'));
        MIC.render();
      }).catch(()=>MIC.toast('档位切换失败'));
      return;
    }
    MIC.form.commitPath('moss.quality',v);
    MIC.render();
  },
};

MIC.gen={
  /* preferMoss：Moss 的成图可以单独配输出目录 */
  openDir(preferMoss){
    const c=MIC.s.cfg;
    const d=((preferMoss&&c.moss)||{}).output_dir||(c.console||{}).output_dir||'';
    MIC.api.openPath(d).catch(()=>MIC.toast('还没配输出目录'));
  },
};
})();
