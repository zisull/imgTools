/* pages/rgba.js —— 透明素材：靠提示词触发原生 RGBA 输出（VAE 4 通道）。
   官方口径：直接文生图，不喂输入图；提示词里明确“透明背景 / isolated on transparent”即可，
   出图即带 alpha，保存的 PNG 自带透明。预览在画廊/这里贴棋盘底显示。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

const SIZES=[
  {code:'512x512',name:'512×512 图标 · 最快最省显存（约 12~15 秒）'},
  {code:'1024x1024',name:'1024×1024 方形 · 标准（约 28 秒）'},
  {code:'1024x1536',name:'1024×1536 竖版 2:3'},
  {code:'1536x1024',name:'1536×1024 横版 3:2'},
  {code:'1536x1536',name:'1536×1536 高清（约 77 秒，接近显存上限）'},
];
function sizeSel(k){
  const v=String(MIC.mget(MIC.s.cfg,k));
  return '<select class="inp" data-k="'+k+'">'+SIZES.map(function(o){
    return '<option value="'+o.code+'"'+(o.code===v?' selected':'')+'>'+esc(o.name)+'</option>';
  }).join('')+'<option value="" disabled>2048×2048 —— 12G 显存不够，暂不可用</option></select>';
}

MIC.registerPage('rgba',{
  title:'透明素材',sub:'原生 RGBA 出图 · 导出带 alpha 的 PNG',icon:'layers',
  render(){
    const s=MIC.s.st, run=!!s.running;
    const params=
      C.field('提示词（务必点明“透明背景 / isolated on a transparent background”）',
        C.ta('rgba.prompt',4,'A flat vector icon of a lightbulb, isolated on a fully transparent background, clean edges, sticker style.'))+
      C.field('尺寸档位',sizeSel('rgba.size'))+
      '<div class="grid3">'+
        C.field('步数',C.seg('rgba.steps',[['8','8 步 · Turbo'],['40','40 步 · 精细']]))+
        C.field('随机种子',C.num('rgba.seed','-1 = 随机'))+
        C.field('张数',C.num('rgba.count','张'))+
      '</div>'+
      C.foldcard('反向提示词 / 高级','cog',
        C.field('反向提示词',C.ta('rgba.negative',2,'background, shadow, white box'))+
        C.field('KV 缓存',C.chk('rgba.kv_cache','use_kv_cache')),'可选，默认收起');
    return C.card('透明素材参数','layers',C.lock(run,params),
        {note:'出图直接存成带 alpha 的 PNG，去画廊或输出目录取用'})+
      MIC.runner.runCard('写好提示词后开始','MIC.rgba.start()');
  },
});

MIC.rgba={
  start(){
    const g=MIC.s.cfg.rgba||{};
    MIC.runner.start('gen',{mode:'rgba',
      prompt:g.prompt||'',size:g.size||'1024x1024',steps:g.steps||'8',
      seed:g.seed!=null?g.seed:-1,count:g.count||1,negative:g.negative||'',
      kv_cache:g.kv_cache!==false});
  },
};
})();
