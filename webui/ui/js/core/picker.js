/* core/picker.js —— 画廊选图弹层：视频与成片的首帧不必再走系统对话框
   清单取 gallery_list（新图在前，最多 120 张），只列图片——成片是 mp4，当不了参考图。
   缩略仍按「滚到哪张取哪张」，缓存跨次打开保留：反复挑同一批图不再重复解码。
   「从文件夹选」把系统对话框的起始目录定在输出目录，等价于在画廊文件夹里挑。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const esc=MIC.esc, ic=MIC.ic;

let box=null, grid=null, note=null, key='', pick=null, items=[], cache={}, io=null;

function ensure(){
  if(box)return box;
  box=document.createElement('div');
  box.className='mask hide';
  box.innerHTML=`<div class="modal pickmodal">
      <div class="mh">${ic('image')}<b>从画廊选图</b>
        <span class="grow"></span><span class="mut fine" id="pickNote"></span>
        <button class="btn sm gho" onclick="MIC.picker.dir()">${ic('folder','s')}从文件夹选</button>
        <button class="iconbtn" onclick="MIC.picker.close()" title="关闭">${ic('close')}</button></div>
      <div class="pickgrid" id="pickGrid"></div>
    </div>`;
  box.addEventListener('click',e=>{if(e.target===box)close();});
  grid=box.querySelector('#pickGrid');
  note=box.querySelector('#pickNote');
  grid.addEventListener('click',e=>{
    const cell=e.target.closest('.pickcell');
    if(cell)take(items[+cell.dataset.i]);
  });
  document.body.appendChild(box);
  return box;
}

function isVid(it){
  return !!(it&&(it.video||/\.(mp4|webm|mov|mkv|avi)$/i.test(it.file||'')));
}

/* cb(file,name)：多图参考要「选一张追加一张」，写配置由调用方自己收；
   不传 cb 就是原来的单选格子——选完直接写回 data-k 那个键。 */
function open(k,cb){
  key=String(k||'');
  pick=typeof cb==='function'?cb:null;
  ensure().classList.remove('hide');
  grid.innerHTML='<div class="empty">正在读画廊 …</div>';
  note.textContent='';
  document.addEventListener('keydown',onKey);
  MIC.api.galleryList().then(r=>{
    items=((r&&r.items)||[]).filter(it=>!isVid(it));
    note.textContent=items.length+' 张 · 新图在前';
    draw();
  }).catch(()=>{
    grid.innerHTML='<div class="empty">读不到画廊清单</div>';
  });
}

function draw(){
  if(!items.length){
    grid.innerHTML='<div class="empty">画廊还空着 · 先去「文生图」或「视频生成」跑一张</div>';
    return;
  }
  grid.innerHTML=items.map((it,i)=>
    `<button type="button" class="pickcell" data-i="${i}" title="${esc(it.file)}">
      <img data-i="${i}" alt="" loading="lazy"><span>${esc(it.name)}</span></button>`).join('');
  hydrate();
}

function hydrate(){
  const todo=[].slice.call(grid.querySelectorAll('img[data-i]'))
              .filter(el=>!el.getAttribute('src')&&!el.dataset.want);
  if(!todo.length)return;
  if(!('IntersectionObserver' in window)){todo.forEach(getThumb);return;}
  const vh=window.innerHeight||document.documentElement.clientHeight||0;
  const rest=[];
  todo.forEach(el=>{
    const r=el.getBoundingClientRect();
    if(r.bottom>-300&&r.top<vh+300)getThumb(el);else rest.push(el);
  });
  if(!rest.length)return;
  if(io)io.disconnect();
  io=new IntersectionObserver(es=>{
    es.forEach(e=>{
      if(!e.isIntersecting)return;
      io.unobserve(e.target);
      getThumb(e.target);
    });
  },{root:grid,rootMargin:'300px 0px'});
  rest.forEach(el=>io.observe(el));
}

function getThumb(el){
  const it=items[+el.dataset.i];
  if(!it)return;
  el.dataset.want='1';
  if(cache[it.file]){el.src=cache[it.file];return;}
  MIC.api.thumb(it.file,256).then(r=>{
    if(!r||!r.ok||!r.url)return;
    cache[it.file]=r.url;
    const nodes=grid.querySelectorAll('img[data-i]');
    for(let k=0;k<nodes.length;k++){
      const now=items[+nodes[k].dataset.i];
      if(now&&now.file===it.file){nodes[k].src=r.url;break;}
    }
  }).catch(()=>{});
}

/* 选图前先把这一屏正在编辑的输入收下：整页重画会把没 blur 的描述框画回旧值 */
function take(it){
  if(!it)return;
  const cb=pick;
  MIC.form.commit();
  close();
  if(cb){cb(it.file,it.name);return;}
  MIC.form.commitPath(key,it.file);
  MIC.render();
  MIC.toast('已选：'+it.name);
}

function dir(){
  MIC.api.pick('output').then(p=>{
    if(!p)return;
    take({file:p,name:String(p).split(/[\\/]/).pop()||p});
  }).catch(()=>{});
}

function close(){
  if(box)box.classList.add('hide');
  document.removeEventListener('keydown',onKey);
}
function onKey(e){if(e.key==='Escape')close();}

MIC.picker={open,close,dir};
})();
