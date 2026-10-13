/* pages/pe.js —— 提示词工坊（占位版）：中文选项 chips 拼英文提示词，免模型
   PE 模型按开发计划缓装；本页先做「风格/光线/构图 → 拼装 → 一键送进生成页」 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

const GROUPS=[
  {key:'style',name:'风格',list:[
    ['水墨','Chinese ink painting'],['赛博朋克','cyberpunk'],['吉卜力风','studio ghibli style'],
    ['产品摄影','product photography'],['3D 渲染','3d render'],['水彩','watercolor'],
    ['油画','oil painting'],['扁平插画','flat illustration']],
  },
  {key:'light',name:'光线',list:[
    ['柔光','soft lighting'],['电影光','cinematic lighting'],['黄金时刻','golden hour'],
    ['霓虹','neon lighting'],['体积光','volumetric lighting'],['逆光剪影','backlight silhouette']],
  },
  {key:'comp',name:'构图',list:[
    ['特写','close-up'],['广角全景','wide angle'],['俯视平铺','flat lay'],
    ['对称构图','symmetrical composition'],['留白极简','minimalist, negative space'],
    ['三分法','rule of thirds']],
  },
];
const sel={style:[],light:[],comp:[]};

function base(){return (MIC.s.cfg.pe||{}).base||'';}
function parts(){
  const out=[base().trim()];
  GROUPS.forEach(g=>g.list.forEach(([zh,en],i)=>{
    if(sel[g.key].indexOf(i)>=0)out.push(en);
  }));
  return out.filter(Boolean);
}
function preview(){return parts().join(', ');}

function groupHTML(g){
  const chips=g.list.map(([zh,en],i)=>{
    const on=sel[g.key].indexOf(i)>=0;
    return `<button class="chip${on?' on':''}" title="${esc(en)}"
      onclick="MIC.pe.pick('${g.key}',${i})">${esc(zh)}</button>`;
  }).join('');
  return `<div class="chiprow"><span class="chipname">${g.name}</span>${chips}</div>`;
}

MIC.registerPage('pe',{
  title:'提示词工坊',sub:'点选拼提示词 · 一键送进生成页',icon:'book',
  render(){
    const pv=preview();
    const body=
      C.field('基础描述（想要什么画面，中英文都行）',
        C.ta('pe.base',3,'一只在雪地里行走的白狐…'))+
      GROUPS.map(groupHTML).join('')+
      C.field('拼装结果','<div class="codebox" id="pe-prev">'+esc(pv||'（先写基础描述，再点几枚标签）')+'</div>')+
      '<div class="btnrow">'+
        '<button class="btn sm gho" onclick="MIC.pe.copy()">'+ic('copy','s')+'复制</button>'+
        '<button class="btn sm gho" onclick="MIC.pe.clear()">'+ic('refresh','s')+'清空选择</button>'+
        '<span class="grow"></span>'+
        '<button class="btn pri" onclick="MIC.pe.to(\'gen\')">'+ic('flower','s')+'送到文生图</button>'+
        '<button class="btn" onclick="MIC.pe.to(\'edit\')">'+ic('wand','s')+'送到图像编辑</button>'+
      '</div>';
    return C.card('拼提示词','book',body)+
      C.card('说明','book',
        '<div class="hint">占位版工坊：不调模型，纯模板拼装。接入 PE 增强模型后可把中文口语扩写成结构化长提示词（开发计划 B 项，缓装）。</div>');
  },
});

MIC.pe={
  pick(k,i){
    MIC.form.commit();                      // 先把文本框现值收进 cfg，重建界面才不丢
    const a=sel[k], j=a.indexOf(i);
    if(j>=0)a.splice(j,1);else a.push(i);
    MIC.render();
  },
  copy(){
    const t=preview();
    if(!t){MIC.toast('还没拼出内容');return;}
    MIC.view.copy(t,'提示词已复制');
  },
  clear(){
    GROUPS.forEach(g=>sel[g.key]=[]);
    MIC.render();
  },
  to(target){
    const t=preview();
    if(!t){MIC.toast('先写基础描述');return;}
    const patch={};
    MIC.mset(patch,target+'.prompt',t);
    MIC.api.save(patch).then(r=>{
      if(r&&r.cfg)MIC.form.applyCfg(r.cfg);
      MIC.nav.goto(target==='gen'?'t2i':'edit');
      MIC.toast('已送到'+(target==='gen'?'文生图':'图像编辑'));
    }).catch(()=>MIC.toast('保存失败'));
  },
};
})();
