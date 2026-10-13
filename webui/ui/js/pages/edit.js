/* pages/edit.js —— 图像编辑（多参考图）：给 ≤10 张参考图 + 编辑指令，出一张合成/改绘结果。
   官方配方：输入图转 RGBA 透传给 pipeline 的 image 参数（扁平列表=多参考图），
   最后一张决定输出画幅比例。12G 显存下 1024 档约 30~40 秒。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

const RES=[
  {code:'512',name:'草图画幅 512² · 最快（试构图用）'},
  {code:'768',name:'中画幅 768² · 折中'},
  {code:'1024',name:'标准画幅 1024² · 明显慢于文生图（编码+长序列）'},
];

let imgs=[];          // 已选参考图绝对路径
const thumbs={};      // path -> data url 缓存

function resSel(k){
  const v=String(MIC.mget(MIC.s.cfg,k));
  return '<select class="inp" data-k="'+k+'">'+RES.map(function(o){
    return '<option value="'+o.code+'"'+(o.code===v?' selected':'')+'>'+esc(o.name)+'</option>';
  }).join('')+'</select>';
}

function grid(){
  if(!imgs.length){
    return '<div class="empty">还没选参考图：点「添加参考图」或直接拖图片进来（最多 10 张）</div>';
  }
  return '<div class="ggrid">'+imgs.map(function(p,i){
    const t=thumbs[p]||'';
    return '<div class="gcell">'+
      (t?'<img src="'+t+'">':'<div class="gph">载入中…</div>')+
      '<div class="gi">图 '+(i+1)+' · '+esc(p.split(/[\\/]/).pop())+'</div>'+
      '<button class="gdel" onclick="MIC.edit.del('+i+')">'+ic('close','s')+'</button>'+
    '</div>';
  }).join('')+'</div>';
}

function loadThumb(p){
  if(thumbs[p])return;
  thumbs[p]='';
  MIC.api.thumb(p).then(function(r){
    if(r&&r.ok){thumbs[p]=r.url;MIC.render();}
  }).catch(function(){});
}

MIC.registerPage('edit',{
  title:'图像编辑',sub:'多参考图合成 · 改绘 / 风格迁移',icon:'wand',
  render(){
    const s=MIC.s.st, run=!!s.running;
    const dropzone='<div class="refdrop" onclick="MIC.edit.add()" '+
      'ondragover="event.preventDefault();this.classList.add(\'over\')" '+
      'ondragleave="this.classList.remove(\'over\')" '+
      'ondrop="event.preventDefault();this.classList.remove(\'over\');MIC.edit.onDrop(event)">'+
      ic('plus','s')+'点我添加参考图，或把图片拖到这里</div>';
    const params=
      C.field('编辑指令（想要怎么改这组图，英文最稳）',C.ta('edit.prompt',4,
        'Turn the pencil sketch into a photorealistic image of the same object on a white background.'))+
      C.field('参考图（≤10 张，最后一张定画幅比例）',dropzone+grid(),'选好后每张会显示缩略图，右上角 × 移除')+
      C.field('画幅（出图比例跟随最后一张参考图）',resSel('edit.res'))+
      '<div class="grid3">'+
        C.field('步数',C.seg('edit.steps',[['8','8 步 · Turbo'],['40','40 步 · 精细']]))+
        C.field('随机种子',C.num('edit.seed','-1 = 随机'))+
        C.field('张数',C.num('edit.count','张'))+
      '</div>'+
      C.foldcard('反向提示词 / 高级','cog',
        C.field('反向提示词',C.ta('edit.negative',2,'blurry, watermark, extra limbs…'))+
        C.field('KV 缓存',C.chk('edit.kv_cache','use_kv_cache（多参考图时更快）')),'可选，默认收起');
    return C.card('编辑参数','wand',C.lock(run,params),
        {note:s.model_loaded?'模型已就绪':'未载入模型时点开始会先自动载入（十几秒）'})+
      MIC.runner.runCard('选好几张参考图后开始','MIC.edit.start()');
  },
  mount(){imgs.forEach(loadThumb);},
});

MIC.edit={
  add(){
    MIC.api.pick('file').then(function(p){
      if(!p)return;
      if(imgs.indexOf(p)<0){if(imgs.length>=10){MIC.toast('最多 10 张');return;}imgs.push(p);loadThumb(p);}
      MIC.render();
    }).catch(function(){});
  },
  onDrop(e){
    const cands=MIC.form.dropCands(e.dataTransfer);
    if(!cands.length)return;
    MIC.api.dropPath(cands,'file').then(function(r){
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'没能识别这个文件');return;}
      if(imgs.indexOf(r.path)<0){if(imgs.length>=10){MIC.toast('最多 10 张');return;}imgs.push(r.path);loadThumb(r.path);}
      MIC.render();
    }).catch(function(){});
  },
  del(i){imgs.splice(i,1);MIC.render();},
  start(){
    if(!imgs.length){MIC.toast('先添加至少一张参考图');return;}
    const g=MIC.s.cfg.edit||{};
    MIC.runner.start('gen',{mode:'edit',images:imgs.slice(),
      prompt:g.prompt||'',res:g.res||'1024',steps:g.steps||'8',
      seed:g.seed!=null?g.seed:-1,count:g.count||1,negative:g.negative||'',
      kv_cache:g.kv_cache!==false});
  },
};
})();
