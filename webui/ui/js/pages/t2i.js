/* pages/t2i.js —— 文生图：提示词 → 尺寸档位 → 步进控制 → 成图预览
   档位是实测出来的：1024 fp8+offload ≈28s（达标），1536 ≈77s（轻微溢出），
   2048 在 12G 上直接 OOM —— 选项保留但禁灰，原因写在提示里。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic;

const SIZES=[
  {code:'512x512',name:'512×512 草图 · 最快最省显存（约 12~15 秒）'},
  {code:'1024x1024',name:'1024×1024 方形 · 标准（约 28 秒）'},
  {code:'1024x1536',name:'1024×1536 竖版 2:3'},
  {code:'1536x1024',name:'1536×1024 横版 3:2'},
  {code:'1536x1536',name:'1536×1536 高清（约 77 秒，接近显存上限）'},
];
function sizeSel(k){
  const v=String(MIC.mget(MIC.s.cfg,k));
  return '<select class="inp" data-k="'+k+'">'+
    SIZES.map(o=>'<option value="'+o.code+'"'+(o.code===v?' selected':'')+'>'+MIC.esc(o.name)+'</option>').join('')+
    '<option value="" disabled>2048×2048 —— 12G 显存不够，暂不可用</option></select>';
}

MIC.registerPage('t2i',{
  title:'文生图',sub:'Qwen-Image-2.1-Turbo · 8 步极速出图',icon:'flower',
  render(){
    const s=MIC.s.st;
    const run=!!s.running;
    const params=
      C.field('提示词（描述画面内容，英文效果最稳）',C.ta('gen.prompt',4,'A neon-lit alley in the rain, cinematic lighting…'))+
      C.field('尺寸档位',sizeSel('gen.size'))+
      '<div class="grid3">'+
        C.field('步数',C.seg('gen.steps',[['8','8 步 · Turbo'],['40','40 步 · 精细']]))+
        C.field('随机种子',C.num('gen.seed','-1 = 每次随机'))+
        C.field('张数',C.num('gen.count','张'))+
      '</div>'+
      C.foldcard('反向提示词 / 高级','cog',
        C.field('反向提示词（不想出现的内容）',C.ta('gen.negative',2,'lowres, bad anatomy, watermark…'))+
        C.field('KV 缓存',C.chk('gen.kv_cache','use_kv_cache（官方推荐开，长提示词更快）')),'可选，默认收起');
    const statusBody=
      '<div class="status">'+
        C.strow('任务状态','<span class="dot '+(run?'run':'')+'" data-role="dot"></span><span data-role="st"></span>')+
        C.strow('去噪进度','<div class="prog"><i data-role="prog"></i></div><span class="mut fine" data-role="pgtext"></span>')+
        C.strow('本轮结果','<span class="mut" data-role="result">就绪后开始生成</span>')+'</div>'+
      '<div class="btnrow">'+
        '<button class="btn pri" onclick="MIC.runner.toggle(\'gen\')">'+
          ic(run?'stop':'play','s')+(run?'停止生成':'开始生成')+'</button>'+
        '<button class="btn" onclick="MIC.gen.openDir()">'+ic('folder','s')+'打开输出目录</button>'+
      '</div>';
    return C.card('生成参数','flower',C.lock(run,params),
        {note:s.model_loaded?'模型已就绪，点开始会直接出图':'未载入模型时点开始会先自动载入（十几秒）'})+
      C.card('运行','play',statusBody)+
      C.card('成图预览','image','<div data-role="imgprev" class="prevwrap"></div>',{tight:true})+
      C.logcard('gen','生成日志');
  },
});

MIC.gen={
  openDir(){
    const d=(MIC.s.cfg.console||{}).output_dir||'';
    MIC.api.openPath(d).catch(()=>MIC.toast('还没配输出目录'));
  },
};
})();
