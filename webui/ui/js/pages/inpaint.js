/* pages/inpaint.js —— 局部编辑：选一张原图 → 在画布上涂抹「要重绘」的区域 →
   涂抹区被合成进输入图的 alpha（透明=模型重绘，其余保留原样）。
   机制来自 pipeline：条件图强制 RGBA，透明区即待生成区，文本编码器看合成白底后的图。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

const RES=[
  {code:'512',name:'草图画幅 512² · 最快（试构图用）'},
  {code:'768',name:'中画幅 768² · 折中'},
  {code:'1024',name:'标准画幅 1024² · 明显慢于文生图（编码+长序列）'},
];
let base='';          // 原图绝对路径
let bgData='';        // 原图缩略 data-uri（当画布背景）

function resSel(k){
  const v=String(MIC.mget(MIC.s.cfg,k));
  return '<select class="inp" data-k="'+k+'">'+RES.map(function(o){
    return '<option value="'+o.code+'"'+(o.code===v?' selected':'')+'>'+esc(o.name)+'</option>';
  }).join('')+'</select>';
}

function stage(){
  if(!base){
    return '<div class="refdrop" onclick="MIC.inp.pickBase()" '+
      'ondragover="event.preventDefault();this.classList.add(\'over\')" '+
      'ondragleave="this.classList.remove(\'over\')" '+
      'ondrop="event.preventDefault();this.classList.remove(\'over\');MIC.inp.onDrop(event)">'+
      ic('plus','s')+'点我选原图，或把图片拖到这里</div>';
  }
  return '<div class="paintwrap">'+
    '<div class="paintbar">'+
      '<span class="mut fine">用鼠标在图上涂抹 —— 涂到的地方才会被重新生成，其余保持原样</span>'+
      '<span class="grow"></span>'+
      '<button class="btn sm" onclick="MIC.inp.clearPaint()">'+ic('trash','s')+'清空涂抹</button>'+
      '<button class="btn sm gho" onclick="MIC.inp.pickBase()">'+ic('refresh','s')+'换图</button>'+
    '</div>'+
    '<div class="stage" id="paintStage">'+
      '<img id="paintBg" class="paintbg" src="'+bgData+'" alt="">'+
      '<canvas id="paintCv" class="paintcv"></canvas>'+
    '</div>'+
  '</div>';
}

MIC.registerPage('inpaint',{
  title:'局部编辑',sub:'涂抹蒙版 · 只改选中的区域',icon:'brush',
  render(){
    const s=MIC.s.st, run=!!s.running;
    const params=
      C.field('重绘指令（想在这个区域改成什么）',C.ta('inpaint.prompt',3,
        'A pair of sunglasses resting on the dashboard.'))+
      C.field('原图',stage(),'涂抹层单独导出为蒙版，后端按原图尺寸对齐')+
      C.field('画笔粗细',C.num('inpaint.brush','px'))+
      C.field('画幅（跟随原图比例）',resSel('inpaint.res'))+
      '<div class="grid3">'+
        C.field('步数',C.seg('inpaint.steps',[['8','8 步 · Turbo'],['40','40 步 · 精细']]))+
        C.field('随机种子',C.num('inpaint.seed','-1 = 随机'))+
        C.field('张数',C.num('inpaint.count','张'))+
      '</div>'+
      C.foldcard('反向提示词 / 高级','cog',
        C.field('反向提示词',C.ta('inpaint.negative',2,'blurry, watermark'))+
        C.field('KV 缓存',C.chk('inpaint.kv_cache','use_kv_cache')),'可选，默认收起');
    return C.card('局部重绘','brush',C.lock(run,params),
        {note:s.model_loaded?'模型已就绪':'未载入模型时点开始会先自动载入（十几秒）'})+
      MIC.runner.runCard('选好原图并涂抹区域后开始','MIC.inp.start()');
  },
  mount(){MIC.inp.initCanvas();},
});

MIC.inp={
  pickBase(){
    MIC.api.pick('file').then(function(p){
      if(!p)return;
      base=p;bgData='';
      MIC.api.thumb(p).then(function(r){if(r&&r.ok){bgData=r.url;}MIC.render();}).catch(function(){MIC.render();});
    }).catch(function(){});
  },
  onDrop(e){
    const cands=MIC.form.dropCands(e.dataTransfer);
    if(!cands.length)return;
    MIC.api.dropPath(cands,'file').then(function(r){
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'没能识别这个文件');return;}
      base=r.path;bgData='';
      MIC.api.thumb(r.path).then(function(t){if(t&&t.ok)bgData=t.url;MIC.render();}).catch(function(){MIC.render();});
    }).catch(function(){});
  },
  initCanvas(){
    const cv=document.getElementById('paintCv');
    const bg=document.getElementById('paintBg');
    if(!cv||!bg)return;
    const ctx=cv.getContext('2d');
    const size=()=>{
      const w=bg.clientWidth||bg.naturalWidth||640;
      const h=bg.clientHeight||w*(bg.naturalHeight/(bg.naturalWidth||1));
      // 保留已涂内容：先存快照，缩放后不重绘（蒙版只按尺寸对齐，缩放无所谓）
      cv.width=Math.round(w);cv.height=Math.round(h);
      ctx.lineWidth=40;ctx.lineCap='round';ctx.lineJoin='round';
      ctx.strokeStyle='rgba(255,72,72,0.85)';
    };
    if(bg.complete)size();else bg.addEventListener('load',size);
    let drawing=false,lx=0,ly=0;
    const pos=e=>{const r=cv.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top];};
    cv.addEventListener('pointerdown',e=>{
      drawing=true;const[x,y]=pos(e);lx=x;ly=y;
      ctx.beginPath();ctx.arc(x,y,ctx.lineWidth/2,0,6.283);ctx.fillStyle='rgba(255,72,72,0.85)';ctx.fill();
      cv.setPointerCapture(e.pointerId);
    });
    cv.addEventListener('pointermove',e=>{
      if(!drawing)return;
      const[x,y]=pos(e);ctx.beginPath();ctx.moveTo(lx,ly);ctx.lineTo(x,y);ctx.stroke();lx=x;ly=y;
    });
    const up=()=>{drawing=false;};
    cv.addEventListener('pointerup',up);cv.addEventListener('pointerleave',up);
    MIC.inp._cv=cv;
    // 画笔粗细改一下实时生效
    const bw=document.querySelector('#view [data-k="inpaint.brush"]');
    if(bw){const apply=()=>{ctx.lineWidth=Math.max(4,parseFloat(bw.value)||40);};bw.addEventListener('input',apply);apply();}
  },
  clearPaint(){
    const cv=MIC.inp._cv;if(cv){cv.getContext('2d').clearRect(0,0,cv.width,cv.height);}
  },
  start(){
    if(!base){MIC.toast('先选一张原图');return;}
    const cv=MIC.inp._cv;
    if(!cv||!cv.width){MIC.toast('画布还没就绪');return;}
    // 只导出涂抹层（透明底上的红痕）→ alpha>0 处即重绘区
    const mask=cv.toDataURL('image/png');
    const g=MIC.s.cfg.inpaint||{};
    MIC.runner.start('gen',{mode:'inpaint',images:[base],mask:mask,
      prompt:g.prompt||'',res:g.res||'1024',steps:g.steps||'8',
      seed:g.seed!=null?g.seed:-1,count:g.count||1,negative:g.negative||'',
      kv_cache:g.kv_cache!==false});
  },
};
})();
