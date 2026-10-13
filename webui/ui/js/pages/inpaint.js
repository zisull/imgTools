/* pages/inpaint.js —— 局部编辑：选一张原图 → 在画布上涂抹「要重绘」的区域 →
   涂抹区被合成进输入图的 alpha（透明=模型重绘，其余保留原样）。
   机制来自 pipeline：条件图强制 RGBA，透明区即待生成区，文本编码器看合成白底后的图。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

const RES=[
  {code:'512',name:'草图画幅 512² · 最快最稳（约 22 秒）'},
  {code:'768',name:'中画幅 768² · 更清晰（约 27 秒，显存已接近上限）'},
];
let base='';          // 原图绝对路径
let bgData='';        // 原图缩略 data-uri（当画布背景）
let paint=null;       // 涂抹层的离屏副本：#view 每次 render 都会换掉 canvas 节点，不存这里就被抹平
let painted=false;    // 涂过没有：没涂就别发任务（后端只会拿到一张全保留的蒙版）
let undoStack=[];     // 每一笔开始前的涂抹层副本，最多 10 步
let area=0;           // 已涂面积百分比（提示用，也是「涂太少」的报警器）

/* 改尺寸会清空 canvas，先把已有的涂抹层缩放搬过去 */
function resizeKeep(cv,w,h){
  if(!(w>0&&h>0)||cv.width===w&&cv.height===h)return;
  const tmp=document.createElement('canvas');
  tmp.width=cv.width;tmp.height=cv.height;
  if(tmp.width&&tmp.height)tmp.getContext('2d').drawImage(cv,0,0);
  cv.width=w;cv.height=h;
  if(tmp.width&&tmp.height)
    cv.getContext('2d').drawImage(tmp,0,0,tmp.width,tmp.height,0,0,w,h);
}
function remember(cv){
  if(!cv.width||!cv.height)return;
  if(!paint)paint=document.createElement('canvas');
  if(paint.width!==cv.width||paint.height!==cv.height){paint.width=cv.width;paint.height=cv.height;}
  const pc=paint.getContext('2d');
  pc.clearRect(0,0,paint.width,paint.height);
  pc.drawImage(cv,0,0);
}
function restore(cv){
  if(!painted||!paint||!cv.width||!cv.height||!paint.width||!paint.height)return;
  cv.getContext('2d').drawImage(paint,0,0,paint.width,paint.height,0,0,cv.width,cv.height);
}
function pushUndo(){
  if(!paint||!paint.width)return;
  const c=document.createElement('canvas');
  c.width=paint.width;c.height=paint.height;
  c.getContext('2d').drawImage(paint,0,0);
  undoStack.push(c);
  if(undoStack.length>10)undoStack.shift();
}
/* 数 alpha 通道：只用来显示「已涂 x%」，涂到 0.x% 说明手滑了一笔，比事后发现强 */
function measure(cv){
  if(!cv||!cv.width||!cv.height){area=0;return;}
  const d=cv.getContext('2d').getImageData(0,0,cv.width,cv.height).data;
  let n=0;
  for(let i=3;i<d.length;i+=4)if(d[i]>10)n++;
  area=Math.round(n/(d.length/4)*1000)/10;
  const el=document.getElementById('paintArea');
  if(el)el.textContent=area?'已涂 '+area+'%':'还没涂抹';
}

function resSel(k){
  const v=String(MIC.mget(MIC.s.cfg,k));
  return '<select class="inp" data-k="'+k+'">'+RES.map(function(o){
    return '<option value="'+o.code+'"'+(o.code===v?' selected':'')+'>'+esc(o.name)+'</option>';
  }).join('')+'<option value="" disabled>1024² —— 12G 显存会溢出到共享内存，实测慢几十倍，暂不可用</option></select>';
}

function stage(){
  if(!base){
    return '<div class="refdrop" onclick="MIC.inp.pickBase()" '+
      'ondragover="event.preventDefault();this.classList.add(\'over\')" '+
      'ondragleave="this.classList.remove(\'over\')" '+
      'ondrop="event.preventDefault();this.classList.remove(\'over\');MIC.inp.onDrop(event)">'+
      ic('plus','s')+'点我选原图，或把图片拖到这里</div>';
  }
  const fn=String(base).split(/[\\/]/).pop();
  return '<div class="paintwrap">'+
    '<div class="paintbar">'+
      '<span class="mut fine" title="'+esc(base)+'">'+esc(fn)+'</span>'+
      '<span class="mut fine" id="paintArea">'+(area?'已涂 '+area+'%':'还没涂抹')+'</span>'+
      '<span class="grow"></span>'+
      '<button class="btn sm gho" onclick="MIC.inp.undo()">'+ic('hist','s')+'撤销一笔</button>'+
      '<button class="btn sm gho" onclick="MIC.inp.clearPaint()">'+ic('trash','s')+'清空涂抹</button>'+
      '<button class="btn sm gho" onclick="MIC.inp.removeBase()" title="移除这张原图，回到选图状态">'+ic('close','s')+'移除原图</button>'+
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
      C.field('重绘指令',C.ta('inpaint.prompt',3,
        'A pair of sunglasses resting on the dashboard.'),'想在这个区域改成什么')+
      C.field('原图',stage(),'在图上涂抹：涂到的地方才会被重新生成，其余保持原样')+
      C.field('画笔粗细',C.num('inpaint.brush','px'))+
      C.field('画幅',resSel('inpaint.res'),
        '跟随原图比例。要手机竖屏图：原图用竖版（如 9:16）即可，画幅自动跟随')+
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
  /* 换原图 = 一切重来：旧涂抹层对新图毫无意义 */
  setBase(p){
    base=String(p||'');bgData='';painted=false;paint=null;undoStack=[];area=0;
    if(!base){MIC.render();return;}
    MIC.api.thumb(base).then(function(r){if(r&&r.ok)bgData=r.url;MIC.render();})
      .catch(function(){MIC.render();});
  },
  pickBase(){
    MIC.api.pick('file').then(function(p){if(p)MIC.inp.setBase(p);}).catch(function(){});
  },
  onDrop(e){
    MIC.form.resolveDrop(e.dataTransfer,'file').then(function(r){
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'没能识别这个文件');return;}
      MIC.inp.setBase(r.path);
    }).catch(function(){});
  },
  initCanvas(){
    const cv=document.getElementById('paintCv');
    const bg=document.getElementById('paintBg');
    if(!cv||!bg)return;
    const ctx=cv.getContext('2d');
    const size=()=>{
      const nw=bg.naturalWidth||0,nh=bg.naturalHeight||0;
      /* 图还没解码完时 clientWidth/naturalWidth 可能同时是 0：
         一律兜一个正尺寸，否则 canvas 被拍成 0 高，下一次 drawImage 直接抛 */
      const w=Math.round(bg.clientWidth||nw||640);
      const h=Math.round(bg.clientHeight||(nw&&nh?w*nh/nw:0)||w*0.75);
      resizeKeep(cv,w,h);
      ctx.lineWidth=40;ctx.lineCap='round';ctx.lineJoin='round';
      ctx.strokeStyle='rgba(255,72,72,0.85)';
      restore(cv);            // 每次 render 都是一张新节点：把离屏涂抹层贴回来，否则画两笔就没了
      remember(cv);
      measure(cv);
    };
    if(bg.complete)size();else bg.addEventListener('load',size);
    let drawing=false,lx=0,ly=0;
    const pos=e=>{const r=cv.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top];};
    cv.addEventListener('pointerdown',e=>{
      drawing=true;const[x,y]=pos(e);lx=x;ly=y;
      pushUndo();             // 先记账再落笔：撤销才能回到这一笔之前
      ctx.beginPath();ctx.arc(x,y,ctx.lineWidth/2,0,6.283);ctx.fillStyle='rgba(255,72,72,0.85)';ctx.fill();
      try{cv.setPointerCapture(e.pointerId);}catch(err){}   // 合成事件/失效指针会让它抛，别把这一笔的记账一起吞了
      painted=true;remember(cv);
    });
    cv.addEventListener('pointermove',e=>{
      if(!drawing)return;
      const[x,y]=pos(e);ctx.beginPath();ctx.moveTo(lx,ly);ctx.lineTo(x,y);ctx.stroke();lx=x;ly=y;
      remember(cv);
    });
    const up=()=>{if(!drawing)return;drawing=false;measure(cv);};
    cv.addEventListener('pointerup',up);cv.addEventListener('pointerleave',up);
    MIC.inp._cv=cv;
    // 画笔粗细改一下实时生效
    const bw=document.querySelector('#view [data-k="inpaint.brush"]');
    if(bw){const apply=()=>{ctx.lineWidth=Math.max(4,parseFloat(bw.value)||40);};bw.addEventListener('input',apply);apply();}
  },
  clearPaint(){
    pushUndo();
    painted=false;area=0;
    if(paint)paint.getContext('2d').clearRect(0,0,paint.width,paint.height);
    const cv=MIC.inp._cv;
    if(cv){cv.getContext('2d').clearRect(0,0,cv.width,cv.height);measure(cv);}
    else{const el=document.getElementById('paintArea');if(el)el.textContent='还没涂抹';}
  },
  undo(){
    const cv=MIC.inp._cv;
    if(!cv||!cv.width||!cv.height){MIC.toast('画布还没就绪');return;}
    const prev=undoStack.pop();
    if(!prev){MIC.toast('没有可撤销的笔迹');return;}
    const ctx=cv.getContext('2d');
    ctx.clearRect(0,0,cv.width,cv.height);
    ctx.drawImage(prev,0,0,prev.width,prev.height,0,0,cv.width,cv.height);
    measure(cv);
    painted=area>0;
    remember(cv);
  },
  removeBase(){MIC.inp.setBase('');},
  /* 别页把成图送进来当原图（画廊/预览接力） */
  useImage(p){MIC.inp.setBase(p);},
  start(){
    if(!base){MIC.toast('先选一张原图');return;}
    const cv=MIC.inp._cv;
    if(!cv||!cv.width||!cv.height){MIC.toast('画布还没就绪');return;}
    if(!painted){MIC.toast('还没涂抹：在图上涂出要重绘的区域');return;}
    // 只导出涂抹层（透明底上的红痕）→ alpha>0 处即重绘区
    const mask=cv.toDataURL('image/png');
    MIC.form.commit();          // 先写回界面值，否则刚打的指令会被旧配置顶掉
    const g=MIC.s.cfg.inpaint||{};
    MIC.runner.start('gen',{mode:'inpaint',images:[base],mask:mask,
      prompt:g.prompt||'',res:g.res||'1024',steps:g.steps||'8',
      seed:g.seed!=null?g.seed:-1,count:g.count||1,negative:g.negative||'',
      kv_cache:g.kv_cache!==false});
  },
};
})();
