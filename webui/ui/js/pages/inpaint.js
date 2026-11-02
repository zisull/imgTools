/* pages/inpaint.js —— 重绘：选一张原图 → 在画布上涂抹「要重绘」的区域 →
   涂抹区被合成进输入图的 alpha（透明=模型重绘，其余保留原样）。
   机制来自 pipeline：条件图强制 RGBA，透明区即待生成区，文本编码器看合成白底后的图。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

const RES=[
  {code:'512',name:'512P : 跟随原图'},
  {code:'768',name:'768P : 跟随原图'},
];
let base='';          // 原图绝对路径
let bgData='';        // 原图缩略 data-uri（当画布背景）
let paint=null;       // 涂抹层的离屏副本：#view 每次 render 都会换掉 canvas 节点，不存这里就被抹平
let painted=false;    // 涂过没有：没涂就别发任务（后端只会拿到一张全保留的蒙版）
let undoStack=[];     // 每一笔开始前的涂抹层副本，最多 10 步
let area=0;           // 已涂面积百分比（提示用，也是「涂太少」报警器）
let brushPx=48;       // 画笔粗细：配置里的 inpaint.brush，画布每次重定尺寸都按它来

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
      '<span class="unit">画笔</span>'+C.num('inpaint.brush','px')+
      '<button class="btn sm gho" onclick="MIC.inp.undo()">'+ic('hist','s')+'撤销一笔</button>'+
      '<button class="btn sm gho" onclick="MIC.inp.clearPaint()">'+ic('trash','s')+'清空涂抹</button>'+
      '<button class="btn sm gho" onclick="MIC.inp.removeBase()" title="回到选图状态">'+ic('close','s')+'移除原图</button>'+
    '</div>'+
    '<div class="stage" id="paintStage">'+
      '<img id="paintBg" class="paintbg" src="'+bgData+'" alt="">'+
      '<canvas id="paintCv" class="paintcv"></canvas>'+
    '</div>'+
  '</div>';
}

MIC.registerPage('inpaint',{
  title:'重绘',sub:'涂抹要改的区域，其余保持原样',icon:'brush',
  render(){
    const run=!!MIC.s.st.running;
    const params=
      C.field('重绘指令',C.ta('inpaint.prompt',3,'在仪表台上放一副墨镜。'),'说清要改成什么')+
      MIC.inspire.box('inpaint.prompt')+
      C.field('原图',stage(),'涂到的地方才会重绘，其余保持原样')+
      '<div class="grid4">'+
        C.field('画幅',C.sizeSel('inpaint.res',RES),'输出画幅跟随原图比例，这里只定清晰度')+
        C.field('步数',C.sel('inpaint.steps',
          [{code:'8',name:'极速 · 8 步'},{code:'40',name:'精细 · 40 步'}]),'8 步够用，40 步更细（慢 5 倍）')+
        C.field('种子',C.seedRow('inpaint.seed'),'开着每次换一张新图；关掉就固定这个数，同参数复现同图')+
        C.field('张数',C.num('inpaint.count','张'),'连发这么多张，每张一个不同种子')+
      '</div>'+
      C.fold('高级','cog',
        C.field('反向提示词',C.ta('inpaint.negative',2,MIC.lib.NEG_BASE),'空着时点灵感卡会自动配一条通用的'));
    return C.duo(
      C.card('重绘参数','brush',C.lock(run,params)+MIC.runner.action('MIC.inp.start()'),
        {note:MIC.runner.modelNote(run)}),
      MIC.runner.runCard(''));
  },
  mount(){MIC.inp.initCanvas();},
});

MIC.inp={
  /* 换原图 = 一切重来：旧涂抹层对新图毫无意义 */
  setBase(p){
    base=String(p||'');bgData='';painted=false;paint=null;undoStack=[];area=0;
    if(!base){MIC.render();return;}
    MIC.api.thumb(base).then(function(r){
      if(!r||!r.ok){MIC.render();return;}
      bgData=r.url;
      /* 缩略图回来只换那一张 <img>：整页重画会把正在打的指令吃掉，
         而 bg 的 load 事件本来就挂着画布尺寸钩子，节点还在就能接上 */
      const bg=document.getElementById('paintBg');
      if(bg)bg.src=bgData;else MIC.render();
    }).catch(function(){MIC.render();});
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
      /* 粗细只有这一个来源：写死 40 会把人调过的画笔在每次图幅变化时顶掉 */
      ctx.lineWidth=brushPx;ctx.lineCap='round';ctx.lineJoin='round';
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
    // 画笔粗细改一下实时生效（并记住它：画布重定尺寸时按这个数，不回落 40）
    const bw=document.querySelector('#view [data-k="inpaint.brush"]');
    if(bw){const apply=()=>{brushPx=Math.max(4,parseFloat(bw.value)||brushPx);ctx.lineWidth=brushPx;};
      bw.addEventListener('input',apply);apply();}
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
    if(!painted){MIC.toast('先在图上涂出要重绘的区域');return;}
    // 只导出涂抹层（透明底上的红痕）→ alpha>0 处即重绘区
    const mask=cv.toDataURL('image/png');
    MIC.form.commit();          // 先写回界面值，否则刚打的指令会被旧配置顶掉
    const g=MIC.s.cfg.inpaint||{};
    MIC.runner.start('gen',{mode:'inpaint',images:[base],mask:mask,
      prompt:g.prompt||'',res:g.res||'768',steps:g.steps||'8',
      seed:g.seed!=null?g.seed:-1,count:g.count||1,negative:g.negative||'',
      kv_cache:g.kv_cache!==false});
  },
};
})();
