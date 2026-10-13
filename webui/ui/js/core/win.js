/* core/win.js —— 无框窗口：任意位置拖动 + 自绘窗口控制 + 八向缩放
   后端是 create_window(frameless=True, easy_drag=False)：
   · easy_drag 给整个窗口绑 mousedown，选文字/点输入框都会把窗口拖着跑，而且只认
     一条 drag-region，达不到「任意位置拖动」，所以关掉自己实现（见 NO/hasText 的放行规则）；
   · frameless 后系统可拖边框没了（shadow 只剩 1px），缩放靠 shell.html 里那圈 .rz。
   量纲：几何全用逻辑像素。move/resize 的入参是逻辑像素（pywebview 内部再乘 DPI 缩放），
   前端把 CSS 位移按 innerWidth/窗口宽 校正一次，DPI 不 100% 也不会拖偏。*/
(function(){
const MIC=window.MIC=window.MIC||{};

/* 按下这些位置不拖窗：交互控件、可滚动容器、弹层，以及「点就直接落在字上」的文本节点
   （target 自己含非空白文本子节点 = 用户想选字，不是想拖窗） */
const NO='input,textarea,select,button,a,label,summary,[contenteditable],[data-nodrag],'
  +'.inp,.chk,.sw,.seg,.btn,.iconbtn,.wctl,.tblwrap,.log,.plist,.pitem,.modal,.mask,'
  +'.layer,.content,.toast,.wbtn';

function hasText(el){
  const n=el.childNodes||[];
  for(let i=0;i<n.length;i++)if(n[i].nodeType===3&&/\S/.test(n[i].nodeValue||''))return true;
  return false;
}
function blocked(t){
  if(!t||t.nodeType!==1)return true;
  if(t.closest&&t.closest(NO))return true;
  return hasText(t);
}

let geo=null;         // 按下瞬间从后端取的窗口/屏幕几何（逻辑像素）
let sx=0,sy=0;        // 按下时的 screenX/Y（CSS px）
let f=1;              // CSS px → 逻辑 px 校正系数
let mode=null;        // 'drag' | 边/角名（n/s/e/w/ne…）
function calib(g){
  /* 正常情况窗口逻辑宽 == innerWidth（系数 1）；差得远说明这套 DPI 下两者不是一回事 */
  const iw=window.innerWidth||g.w;
  let v=iw?g.w/iw:1;
  if(Math.abs(v-1)<0.06)v=1;                   // 滚动条/1px 阴影带来的零头不算漂移
  f=Math.max(0.4,Math.min(3,v||1));
}
/* 夹住窗口（别拖出屏幕、最大化别盖任务栏）交给原生守卫：app.py 的
   WM_WINDOWPOSCHANGING 钩子在 Win32 层把移动和缩放一起钳进工作区。
   前端再夹一次只会和它打架，所以这里按拖动增量原样提交。 */

function down(e){
  if(e.button!==0||mode)return;
  if(blocked(e.target))return;
  MIC.api.winGeo().then(g=>{
    if(!g||g.maxed)return;      // 最大化时不拖：先点还原再拖，免得误触一还原
    geo=g;calib(g);sx=e.screenX;sy=e.screenY;mode='drag';
    document.body.classList.add('win-drag');
  }).catch(()=>{});
}
function move(e){
  if(!mode||!geo)return;
  const dx=(e.screenX-sx)*f,dy=(e.screenY-sy)*f;
  if(!dx&&!dy)return;
  if(mode==='drag'){
    MIC.api.winMove(geo.x+dx,geo.y+dy);
    return;
  }
  /* 缩放：对角锚点不动。min_size 后端还会再兜一次，这里先算是为了夹住屏幕 */
  const min={w:geo.min_w||900,h:geo.min_h||560},m=mode;
  let x=geo.x,y=geo.y,w=geo.w,h=geo.h;
  if(m.indexOf('e')>=0)w=Math.max(min.w,geo.w+dx);
  if(m.indexOf('s')>=0)h=Math.max(min.h,geo.h+dy);
  if(m.indexOf('w')>=0){w=Math.max(min.w,geo.w-dx);x=geo.x+(geo.w-w);}
  if(m.indexOf('n')>=0){h=Math.max(min.h,geo.h-dy);y=geo.y+(geo.h-h);}
  MIC.api.winSet(x,y,w,h);
}
function up(){
  if(!mode)return;
  mode=null;geo=null;
  document.body.classList.remove('win-drag');
}

function rzDown(e){
  const el=e.target.closest?e.target.closest('.rz'):null;
  if(!el||e.button!==0||mode)return;
  MIC.api.winGeo().then(g=>{
    if(!g||g.maxed)return;
    geo=g;calib(g);sx=e.screenX;sy=e.screenY;mode=el.dataset.edge;
  }).catch(()=>{});
}

function maxToggle(){
  MIC.api.winMax().then(r=>{
    const on=!!(r&&r.maxed);
    document.body.classList.toggle('win-max',on);
    const el=MIC.$('winMax');
    if(el){el.innerHTML='<svg class="ic"><use href="#'+(on?'i-wrestore':'i-wmax')+'"/></svg>';
      el.title=on?'还原':'最大化';}
  }).catch(()=>{});
}

MIC.win={
  min(){MIC.api.winMin().catch(()=>{});},
  max:maxToggle,
  close(){MIC.api.winClose().catch(()=>{});},
  sync(g){                       // 后端状态变了（如启动即最大化）时对齐图标
    const on=!!(g&&g.maxed);
    document.body.classList.toggle('win-max',on);
  },
  init(){
    if(!MIC.api.booted())return;   // 纯浏览器预览（mock）下没有窗口，别绑
    document.addEventListener('mousedown',down);
    document.addEventListener('mousemove',move);
    document.addEventListener('mouseup',up);
    document.addEventListener('dblclick',e=>{
      if(blocked(e.target))return;
      maxToggle();
    });
    const box=MIC.$('rzg');
    if(box){
      box.querySelectorAll('.rz').forEach(el=>el.addEventListener('mousedown',rzDown));
      MIC.api.winGeo().then(g=>{if(g)MIC.win.sync(g);}).catch(()=>{});
    }
  },
};
})();
