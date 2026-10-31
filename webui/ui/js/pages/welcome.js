/* pages/welcome.js —— 首启欢迎页：先选一路模型，界面跟着变成那一套
   两台模型占的是同一张卡，装哪套、留哪套是每个人的事：
   选「仅千问」或「仅 Moss」后整个界面只留那一路的页，另一路的分区与环境提示一并收走。
   这一页不挂导航标签（不是常驻功能，是一次性的门），cfg.welcomed 落 true 就再也不来。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const ic=MIC.ic, esc=MIC.esc;

const CARDS=[
  {m:'qwen',icon:'flower',name:'千问',tag:'一路就够',
   desc:'Qwen-Image-2.1-Turbo，画质稳、能改图与局部重绘。',
   cost:'权重约 30 GB · 1024 约 28 秒'},
  {m:'moss',icon:'wave',name:'Moss',tag:'快，只要一路',
   desc:'MOSS-Image，内嵌 ComfyUI，只出图不做改绘。',
   cost:'权重约 12 GB · 1024 约 3.3 秒'},
  {m:'both',icon:'layers',name:'两个都有',tag:'切换着用',
   desc:'同一张卡上轮流出图，切引擎时另一路的权重自动让显存。',
   cost:'合计约 42 GB · 界面两路都留'},
];

/* 这一路在「这台机器」上到底缺不缺东西：体检按引擎拆了数（env_todo_qwen/moss），
   所以选之前就能看出「Moss 已就绪、千问还差 2 项」，不用选完再翻环境页。
   数还没回来（开机体检晚半秒）就整行不出现，不拿「已就绪」糊人。 */
function ready(m){
  const s=MIC.s.st, q=s.env_todo_qwen, o=s.env_todo_moss;
  if(q==null&&o==null)return '';
  const n=m==='qwen'?Number(q)||0:m==='moss'?Number(o)||0
                   :(Number(q)||0)+(Number(o)||0);
  return n?`<span class="wr bad">这台机器还差 ${n} 项</span>`
          :'<span class="wr ok">这台机器已就绪</span>';
}

MIC.registerPage('welcome',{
  title:'欢迎',icon:'flower',bare:true,
  render(){
    const s=MIC.s.st;
    const cards=CARDS.map(c=>`<button class="wcard" onclick="MIC.welcome.pick('${c.m}')">
        ${ic(c.icon,'wi')}<b>${esc(c.name)}</b><span class="wt">${esc(c.tag)}</span>
        <span class="wd">${esc(c.desc)}</span>
        <span class="wc">${esc(c.cost)}</span>${ready(c.m)}</button>`).join('');
    /* 缺哪一路的数已经写在每张牌底下了，不再另挂一条横幅：
       页脚一句说完「还差几项 + 去哪儿补」，选错了也在这里改。 */
    const n=Number(s.env_todo)||0;
    return `<div class="welcome">
      <div class="whead">${ic('flower','wl')}<h1>先选一路模型</h1>
        <p>千问和 Moss 共用这一张显卡，同一时间只有一路常驻显存。</p></div>
      <div class="wgrid">${cards}</div>
      <div class="wfoot"><span class="mut fine">${
          n?`这台机器还差 ${n} 项环境，选完到「环境」页一键补齐 · `:''
        }选错了随时改：设置 → 控制台模式</span></div>
    </div>`;
  },
});

MIC.welcome={
  /* 设置页那颗「重看」：把 welcomed 退回 false，主区下一次重画就是这一页 */
  review(){
    MIC.api.save({welcomed:false}).then(r=>{
      if(r&&r.cfg)MIC.form.applyCfg(r.cfg);
      MIC.render();
    }).catch(()=>MIC.toast('没存上'));
  },
  /* 选完三件事：落盘（console_mode + welcomed + 起始页落到生图）、按新模式重排导航、
     把激活引擎对齐到这一路。set_engine 是后台活（拉 ComfyUI 要几十秒），
     桥调用当场就回，进度由轮询跟——在这儿同步等会把界面冻成一块板。 */
  pick(mode){
    MIC.api.save({console_mode:mode,welcomed:true,last_tab:'t_gen'}).then(r=>{
      if(!r||!r.cfg){MIC.toast('没存上，再点一次');return;}
      MIC.form.applyCfg(r.cfg);
      MIC.nav.applyMode();
      MIC.nav.goto('t2i');
      const cur=MIC.s.st.engine;
      if(mode!=='both'&&mode!==cur)
        MIC.api.setEngine(mode).then(x=>{
          if(x&&x.msg)MIC.toast(x.msg);
          if(x&&x.ok)MIC.s.st.engine=mode;
          MIC.render();
        }).catch(()=>{});
    }).catch(()=>MIC.toast('切换失败'));
  },
};
})();
