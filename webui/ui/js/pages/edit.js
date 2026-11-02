/* pages/edit.js —— 编辑（多参考图）：≤10 张参考图 + 一句指令，出一张合成或改绘。
   官方配方：输入图转 RGBA 透传给 pipeline 的 image 参数（扁平列表=多参考图），
   最后一张决定输出画幅比例。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

const RES=[
  {code:'512',name:'512P : 跟随原图'},
  {code:'768',name:'768P : 跟随原图'},
];

let imgs=[];          // 已选参考图绝对路径
const thumbs={};      // path -> data url 缓存

function grid(){
  /* 一张没选时不占位：拖放区自己就写着「点我/拖进来」，再补一行空态只是重复 */
  if(!imgs.length)return '';
  return '<div class="ggrid">'+imgs.map(function(p,i){
    const t=thumbs[p]||'';
    /* 两个节点都带 data-f：缩略图回来时按这个找得到自己那一格，
       不必整页重画（整页重画会把正在打的指令吃掉） */
    return '<div class="gcell">'+
      (t?'<img data-f="'+esc(p)+'" src="'+t+'">':'<div class="gph" data-f="'+esc(p)+'">载入中…</div>')+
      '<div class="gi">图 '+(i+1)+' · '+esc(p.split(/[\\/]/).pop())+'</div>'+
      '<button class="gdel" onclick="MIC.edit.del('+i+')">'+ic('close','s')+'</button>'+
    '</div>';
  }).join('')+'</div>';
}

function paintThumb(p,url){
  const nodes=document.querySelectorAll('#view [data-f]');
  for(let k=0;k<nodes.length;k++){
    if(nodes[k].dataset.f!==p)continue;
    if(nodes[k].tagName==='IMG')nodes[k].src=url;
    else nodes[k].outerHTML='<img data-f="'+esc(p)+'" src="'+url+'">';
    return true;
  }
  return false;
}

function loadThumb(p){
  /* 用 in 判重：写进去的可能是空串（后端出图失败），真值判断会把这张当成「没请求过」，
     每次 render 都重发一次缩略图请求，坏文件就会没完没了地重做。 */
  if(p in thumbs)return;
  thumbs[p]='';
  MIC.api.thumb(p).then(function(r){
    if(!r||!r.ok)return;
    thumbs[p]=r.url;
    /* 只换这一格；这一屏不在视频/编辑页了（找不到节点）才重画一次 */
    if(!paintThumb(p,r.url))MIC.render();
  }).catch(function(){});
}

MIC.registerPage('edit',{
  title:'图像编辑',sub:'≤10 张参考图，合成或改绘',icon:'wand',
  render(){
    const run=!!MIC.s.st.running;
    const dropzone='<div class="refdrop" onclick="MIC.edit.add()" '+
      'ondragover="event.preventDefault();this.classList.add(\'over\')" '+
      'ondragleave="this.classList.remove(\'over\')" '+
      'ondrop="event.preventDefault();this.classList.remove(\'over\');MIC.edit.onDrop(event)">'+
      ic('plus','s')+'点我添加参考图，或把图片拖到这里</div>';
    const params=
      C.field('编辑指令',C.ta('edit.prompt',4,'把这张铅笔素描变成白底上的同款实物照片。'),
        '说清要怎么改这组图')+
      MIC.inspire.box('edit.prompt')+
      C.field('参考图',dropzone+grid(),'最多 10 张，最后一张决定输出画幅比例')+
      '<div class="grid4">'+
        C.field('画幅',C.sizeSel('edit.res',RES),'比例跟随最后一张参考图；768² 已接近 12G 显存上限')+
        C.field('步数',C.sel('edit.steps',
          [{code:'8',name:'极速 · 8 步'},{code:'40',name:'精细 · 40 步'}]),'8 步够用，40 步更细（慢 5 倍）')+
        C.field('种子',C.seedRow('edit.seed'),'开着每次换一张新图；关掉就固定这个数，同参数复现同图')+
        C.field('张数',C.num('edit.count','张'),'连发这么多张，每张一个不同种子')+
      '</div>'+
      C.fold('高级','cog',
        C.field('反向提示词',C.ta('edit.negative',2,MIC.lib.NEG_BASE),'空着时点灵感卡会自动配一条通用的'));
    return C.duo(
      C.card('编辑参数','wand',C.lock(run,params)+MIC.runner.action('MIC.edit.start()'),
        {note:MIC.runner.modelNote(run)}),
      MIC.runner.runCard(''));
  },
  mount(){imgs.forEach(loadThumb);},
});

MIC.edit={
  addPath(p){
    if(!p)return;
    if(imgs.indexOf(p)<0){if(imgs.length>=10){MIC.toast('最多 10 张');return;}imgs.push(p);loadThumb(p);}
    MIC.render();
  },
  add(){MIC.api.pick('file').then(function(p){MIC.edit.addPath(p);}).catch(function(){});},
  onDrop(e){
    MIC.form.resolveDrop(e.dataTransfer,'file').then(function(r){
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'没能识别这个文件');return;}
      MIC.edit.addPath(r.path);
    }).catch(function(){});
  },
  del(i){imgs.splice(i,1);MIC.render();},
  /* 别页送图进来当参考图（成图接力）：整组换掉，不是追加 */
  useImage(p){imgs=[];[].concat(p||[]).forEach(MIC.edit.addPath);},
  start(){
    if(!imgs.length){MIC.toast('先添加至少一张参考图');return;}
    /* 先把界面上的值写回 cfg：不 commit 读到的是上次落盘的旧值，刚打的指令会被丢掉 */
    MIC.form.commit();
    const g=MIC.s.cfg.edit||{};
    MIC.runner.start('gen',{mode:'edit',images:imgs.slice(),
      prompt:g.prompt||'',res:g.res||'768',steps:g.steps||'8',
      seed:g.seed!=null?g.seed:-1,count:g.count||1,negative:g.negative||'',
      kv_cache:g.kv_cache!==false});
  },
};
})();
