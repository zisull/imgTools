/* pages/welcome.js —— 首启欢迎页：先决定这台机器管哪几路模型
   这页就是那几路环境的开关总入口，点一张牌 = 开 / 关那一路。
   关掉的那一路后端根本不体检（env_check 先按 env_on 过滤），
   于是待补数、横幅提醒、功能页一起安静下来——「关掉就当它不存在」。
   这一页不挂导航标签（是一次性的门），cfg.welcomed 落 true 就再也不来；
   设置页留了「重看」，开关本身也随时能在「环境 → 各页」上改。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const ic=MIC.ic, esc=MIC.esc;

const CARDS=[
  {id:'qwen',icon:'flower',name:'千问',tag:'生图 + 改图',
   desc:'Qwen-Image-2.1-Turbo，画质稳，能整图改绘与局部重绘。',
   cost:'权重约 30 GB · 1024 约 28 秒',page:'env_qwen'},
  {id:'moss',icon:'wave',name:'Moss',tag:'出图快',
   desc:'MOSS-Image，内嵌 ComfyUI；只出图，不做改绘。',
   cost:'权重约 12 GB · 1024 约 3.3 秒',page:'env_moss'},
  {id:'h3',icon:'film',name:'H3 视频',tag:'出成片',
   desc:'MiniMax H3，一句话出一段带声音的成片；和 Moss 共用那个运行时。',
   cost:'权重约 41 GB · 12G 显存',page:'env_h3'},
];

/* 这一路在「这台机器」上缺不缺东西：开机那趟后台体检把数按环境拆好（st.env_todo_by），
   所以点之前就能看出「Moss 已就绪、千问还差 2 项」。数没回来时整行不出现，
   不拿「已就绪」糊人。关着的这一路不问体检——关掉就没有欠账。 */
function note(id){
  const s=MIC.s.st;
  if(MIC.nav.envOn()[id]===false)
    return '<span class="wr">已关闭 · 不体检、不提醒</span>';
  const by=s.env_todo_by;
  if(!by)return '';
  const n=Number(by[id])||0;
  return n?`<span class="wr bad">这台机器还差 ${n} 项</span>`
          :'<span class="wr ok">这台机器已就绪</span>';
}

function card(c){
  const o=MIC.nav.envOn();
  const on=o[c.id]!==false;
  return `<div class="wcard" onclick="MIC.welcome.toggle('${c.id}',${on?0:1})"
      title="${on?'点一下关掉这一路':'点开这一路：体检、提醒和功能页一起回来'}">
    <div class="sw ${on?'on':''}" style="pointer-events:none"></div>
    ${ic(c.icon,'wi')}<b>${esc(c.name)}</b><span class="wt">${esc(c.tag)}</span>
    <span class="wd">${esc(c.desc)}</span>
    <span class="wc">${esc(c.cost)}</span>${note(c.id)}</div>`;
}

MIC.registerPage('welcome',{
  title:'欢迎',icon:'flower',bare:true,
  render(){
    const s=MIC.s.st,open=['qwen','moss','h3'].filter(id=>MIC.nav.envOn()[id]!==false);
    return `<div class="welcome">
      <div class="whead">${ic('flower','wl')}<h1>这台机器管哪几路</h1>
        <p>都占同一张显卡，同一时间只有一路常驻显存。关掉的那路不体检、不提醒，功能页也收起。</p></div>
      <div class="wgrid">${CARDS.map(card).join('')}</div>
      <div class="wfoot">
        <button class="btn pri big" onclick="MIC.welcome.enter()">${ic('play','s')}进入控制台</button>
        <div class="mut fine" style="margin-top:8px">${
          open.length?'已开 '+open.map(c=>({qwen:'千问',moss:'Moss',h3:'H3'}[c])).join(' / '):'一路都没开，进去只看得到环境与设置'
        } · 开关随时能在「环境」那几页改 · H3 云端（RunningHub）在接入中</div></div>
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
  toggle(id,want){
    MIC.env.set(id,!!want);
  },
  /* 进控制台：落 welcomed，起始页挑第一张还开着的页；
     引擎对齐到开着的其中一路（set_engine 是后台活，桥调用当场就回，进度由轮询跟） */
  enter(){
    const o=MIC.nav.envOn();
    MIC.api.save({welcomed:true}).then(r=>{
      if(r&&r.cfg)MIC.form.applyCfg(r.cfg);
      else MIC.s.cfg.welcomed=true;
      MIC.nav.applyMode();
      const cur=MIC.s.st.engine;
      const want=o.qwen!==false?'qwen':(o.moss!==false||o.h3!==false)?'moss':'';
      if(want&&want!==cur)
        MIC.api.setEngine(want).then(x=>{
          if(x&&x.ok)MIC.s.st.engine=want;
          MIC.render();
        }).catch(()=>{});
      MIC.render();
    }).catch(()=>MIC.toast('没存上，再点一次'));
  },
};
})();
