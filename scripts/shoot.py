# -*- coding: utf-8 -*-
"""界面截图：用 assemble(mock=True) 现拼一份 HTML，无头 Edge 逐页拍下来人工核对。

只验界面（含 mock 数据），不碰后端。产物写到 %TEMP%\\qic_shoot\\，看完整页要 --full。
"""
import argparse
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))
sys.path.insert(0, os.path.join(ROOT, "webui", "ui"))

from assemble import assemble  # noqa: E402

# v6：词库并进生图页（灵感行 + 全览折叠），导航七个标签两组
TAB = {"t2i": "t_gen", "edit": "t_edit", "inpaint": "t_inp",
       "gallery": "t_gal", "logs": "t_log", "models": "t_mod", "settings": "t_set"}
EDGE = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")

# 交互探针：headless 里真点一遍，把结论写进 <pre id=probe>，再用 --dump-dom 取回来
PROBE = {
    "inpaint": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  function ink(){
    const cv=document.getElementById('paintCv');
    if(!cv||!cv.width)return 0;
    const d=cv.getContext('2d').getImageData(0,0,cv.width,cv.height).data;
    let n=0;for(let i=3;i<d.length;i+=4)if(d[i]>0)n++;
    return n;
  }
  try{
    await wait(1500);
    MIC.inp.pickBase();
    await wait(800);
    let cv=document.getElementById('paintCv');
    ok('选完原图有画布', !!cv && cv.width>0, cv&&cv.width);
    /* 每次都要重新取节点：MIC.render() 会换掉 canvas，往旧节点上派发等于没涂 */
    const at=(t,fx,fy)=>{
      const c=document.getElementById('paintCv'),r=c.getBoundingClientRect();
      c.dispatchEvent(new PointerEvent(t,{clientX:r.left+r.width*fx,
        clientY:r.top+r.height*fy,pointerId:1,bubbles:true}));
    };
    at('pointerdown',0.3,0.3);at('pointermove',0.6,0.6);at('pointerup',0.6,0.6);
    await wait(80);
    const before=ink();
    ok('涂一笔有像素', before>0, before);
    MIC.render();                       /* 模拟一次轮询重画：老写法在这里把涂抹层抹平 */
    await wait(400);
    const after=ink();
    ok('重画后涂抹层还在', after>before*0.5, before+' -> '+after);
    MIC.inp.clearPaint();
    await wait(60);
    ok('清空后归零', ink()===0, ink());
    at('pointerdown',0.4,0.4);at('pointerup',0.4,0.4);
    await wait(60);
    ok('重画后还能接着涂', ink()>0, ink());
    MIC.render();
    await wait(400);
    ok('再重画一次涂抹层还在', ink()>0, ink());
    /* 撤销：再涂第二笔，撤一次，像素必须真的少回去（而且扛得住重画） */
    at('pointerdown',0.7,0.25);at('pointermove',0.85,0.45);at('pointerup',0.85,0.45);
    await wait(80);
    const two=ink();
    const areaTxt=(document.getElementById('paintArea')||{}).textContent||'';
    ok('面积读数跟着笔走', /已涂/.test(areaTxt), areaTxt);
    MIC.inp.undo();
    await wait(80);
    const one=ink();
    ok('撤销一笔后像素变少', two>0&&one>0&&one<two, two+' -> '+one);
    MIC.render();
    await wait(400);
    ok('撤销的结果扛得住重画', Math.abs(ink()-one)<=two*0.15, one+' -> '+ink());
    /* 移除原图：回到「点我选原图」的落区，别只剩「换图」一条路 */
    MIC.inp.removeBase();
    await wait(300);
    ok('移除原图后回到选图态', !document.getElementById('paintCv')
        && !!document.querySelector('.refdrop'));
    MIC.inp.pickBase();                 /* 换图：旧涂抹层对新图没意义 */
    await wait(800);
    ok('换图后涂抹层清空', ink()===0, ink());
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 成图 → 编辑页 的接力：在生图页上跑，两个目标页都要顾到
    "again": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const cells=()=>document.querySelectorAll('#view .gcell').length;
  try{
    await wait(1500);
    MIC.s.st.last_image='D:/AI/Qwen-Image-2.1/outputs/gen_probe.png';
    MIC.render();
    await wait(600);
    const btns=[].slice.call(document.querySelectorAll('#view button')).map(b=>b.textContent.trim());
    ok('预览下有接力按钮', btns.some(t=>/局部改/.test(t))&&btns.some(t=>/整张再编辑/.test(t)),
       btns.slice(-3).join('|'));
    /* 成图预览的 ×：收的是预览，不是磁盘上的文件 */
    const box=()=>document.querySelector('#view .prevbox');
    const slot=()=>document.querySelector('#view [data-role=imgprev]');
    ok('预览图上有 ×', !!box() && box().querySelectorAll('.px').length===1
        && !!box().querySelector('img.prev'));
    MIC.view.hidePrev();
    await wait(400);
    ok('点 × 后预览收起', !box() && /预览已收起/.test(slot().textContent),
        slot().textContent.trim().slice(0,24));
    MIC.view.showPrev();
    await wait(400);
    ok('重新显示又回来', !!box() && !!box().querySelector('img.prev'));
    MIC.runner.again('edit');
    await wait(900);
    ok('送进编辑页=一张参考图', cells()===1, 'cells='+cells());
    ok('参考图上有 × 可移除', document.querySelectorAll('#view .gcell .gdel').length===1);
    MIC.edit.del(0);
    await wait(300);
    ok('点 × 真的少一张', cells()===0, 'cells='+cells());
    MIC.runner.again('inpaint');
    await wait(900);
    ok('送进重绘页=出画布', !!document.getElementById('paintCv'));
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 失败轮次 / 同图轮次：状态行与成图预览都要把话说明白，不许拿上一张装没事
    "repeat": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const result=()=>((document.querySelector('#view [data-role=result]')||{}).textContent||'');
  const prev=()=>document.querySelector('#view [data-role=imgprev]');
  try{
    await wait(1500);
    clearInterval(MIC.s.pollTimer);     /* 这轮断言的是「状态里写失败时界面怎么说」，别让 mock 轮询把状态盖回去 */
    MIC.s.st.last_image='D:/AI/Qwen-Image-2.1/outputs/gen_probe.png';
    MIC.s.st.last_sec=1.2;
    MIC.s.st.dup_last=false;
    MIC.s.st.last_fail='ComfyUI 进程中途退了（显存不够或节点报错）';
    MIC.s.st.status='Moss 生成失败';
    MIC.render();
    await wait(800);
    ok('失败写在结果行上', /本轮失败/.test(result())&&/画面仍是上一张/.test(result()),
       result().trim().slice(0,60));
    ok('预览图上标着「下面是上一张」',
       !!prev()&&!!prev().querySelector('.failnote')&&!!prev().querySelector('img.prev'));
    MIC.s.st.status='✅ 完成';MIC.s.st.last_fail='';MIC.s.st.dup_last=true;
    MIC.render();
    await wait(600);
    ok('同图提醒看得见', /与上一张相同/.test(result()), result().trim().slice(0,60));
    ok('同图时不标失败',
       !/本轮失败/.test(result())&&!!prev()&&!prev().querySelector('.failnote'));
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 灵感行 + 词库全览（词库页并进来的那一块，都在生图页里）：
    # 分类切换 / 整句填入 / 追加词拼接 / 反向词只在空着时补 / 悬停看全句
    "kits": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const row=()=>document.querySelector('#view .insrow');
  const chips=()=>[].slice.call((row()||{querySelectorAll:()=>[]}).querySelectorAll('.chip'));
  const catChips=()=>[].slice.call((document.querySelector('#view .catrow')
      ||{querySelectorAll:()=>[]}).querySelectorAll('.chip'));
  const cfg=k=>String(MIC.mget(MIC.s.cfg,k)||'');
  const set=(k,v)=>{MIC.form.commitPath(k,v);MIC.render();};
  const fold=()=>[].slice.call(document.querySelectorAll('#view .fold-h'))
      .filter(h=>/词库全览/.test(h.textContent))[0];
  const rows=()=>document.querySelectorAll('#view .fold-b .prow').length;
  const btns=()=>[].slice.call(document.querySelectorAll('#view .fold-b .prow button'));
  const by=t=>btns().filter(b=>t.test(b.textContent.trim()));
  /* 「填进反向框」挂在每类末尾那条 pfoot 上，不在 .prow 里，得单独捞 */
  const negBtns=()=>[].slice.call(document.querySelectorAll('#view .fold-b .pfoot button'));
  const fhide=()=>{const f=fold();return !!(f&&f.nextElementSibling
      &&f.nextElementSibling.classList.contains('hide'));};
  try{
    await wait(1500);
    clearInterval(MIC.s.pollTimer);
    ok('灵感上面一行是分类（7 类）', catChips().length===7,
       catChips().map(c=>c.textContent.trim()).join('|'));
    ok('分类只点亮当前那一类（人物）', catChips().filter(c=>c.classList.contains('on')).length===1
        && /人物/.test((catChips().filter(c=>c.classList.contains('on'))[0]||{}).textContent),
       catChips().filter(c=>c.classList.contains('on')).map(c=>c.textContent).join('|'));
    ok('灵感行摊开这一类全部 8 条（不再翻页）', chips().length===8,
       chips().length+' | '+chips().map(c=>c.textContent.trim()).join('|'));
    ok('每张卡悬停给出整句', chips().every(c=>(c.title||'').length>10),
       (chips()[0].title||'').slice(0,24));
    set('gen.prompt','');set('gen.negative','');
    await wait(200);
    chips()[0].click();
    await wait(300);
    ok('点灵感卡整句提示词填进框', cfg('gen.prompt')===MIC.lib.CATS[0].items[0].pos,
       cfg('gen.prompt').slice(0,40));
    ok('反向词空着时自动配好', cfg('gen.negative').length>5, cfg('gen.negative').slice(0,30));
    set('gen.negative','my own neg');
    await wait(200);
    chips()[1].click();
    await wait(300);
    ok('自己写过的反向词不被覆盖', cfg('gen.negative')==='my own neg', cfg('gen.negative'));
    ok('提示词换成新卡那一句', cfg('gen.prompt')===MIC.lib.CATS[0].items[1].pos,
       cfg('gen.prompt').slice(0,40));
    /* 追加那一类（光影/构图/质感）：不整句替换，接在自己写好的句子后面 */
    set('lib.cat','light');
    await wait(300);
    ok('换分类后灵感行跟着换', /逆光|黄金时刻|丁达尔/.test(chips().map(c=>c.textContent).join('|')),
       chips().map(c=>c.textContent.trim()).join('|'));
    const base='一只柴犬坐在草地上';
    set('gen.prompt',base);
    await wait(200);
    chips()[0].click();
    await wait(300);
    ok('追加词接在原句后面（不是覆盖）', cfg('gen.prompt').indexOf(base)===0
        && cfg('gen.prompt').length>base.length, cfg('gen.prompt').slice(0,40));
    /* 反向那一类：灵感卡点的就是反向框，自己写过的提示词一个字都不动 */
    set('gen.prompt','keep me');set('gen.negative','');
    await wait(200);
    set('lib.cat','negative');
    await wait(300);
    chips()[1].click();
    await wait(300);
    ok('反向类：点卡填的是反向框、提示词不动',
       cfg('gen.negative')===MIC.lib.cat('negative').items[1].pos && cfg('gen.prompt')==='keep me',
       cfg('gen.negative').slice(0,24));
    set('lib.cat','person');
    /* ---- 词库全览：折起来不占地方，展开才是整本 ---- */
    const f=fold();
    ok('生图页里有一块折起来的词库全览', !!f&&f.classList.contains('closed'),
       f?(f.classList.contains('closed')?'折着':'已展开'):'没有这块');
    ok('折着时 56 条在 DOM 里但不显示', rows()===56&&fhide(), rows()+'');
    f.click();
    await wait(200);
    ok('点标题摊开整本', rows()===56&&!fhide(), fhide()?'还是折着':'已摊开 '+rows());
    ok('七类各有小标题、反向那类的按钮叫「填反向」',
       document.querySelectorAll('#view .fold-b .egroup').length===7
       && by(/^填反向$/).length===8, by(/^填反向$/).length+'');
    set('gen.negative','');
    await wait(200);
    negBtns().forEach(b=>b.click());
    await wait(300);
    ok('有通用反向的那几类各挂一条（4 类）',
       negBtns().length===4 && cfg('gen.negative').length>5,
       negBtns().length+' | '+cfg('gen.negative').slice(0,24));
    by(/^填入$/)[0].click();
    await wait(300);
    ok('全览「填入」写进当前引擎的提示词', cfg('gen.prompt')===MIC.lib.CATS[0].items[0].pos,
       cfg('gen.prompt').slice(0,30));
    /* 一页两引擎：Moss 那块的字走 moss.*，词库填的是当前引擎那一块 */
    MIC.s.st.engine='moss';MIC.render();
    await wait(300);
    ok('切 Moss 后灵感行还在，分类照旧 7 类',
       !!row()&&catChips().length===7, chips().length+'');
    const gp=cfg('gen.prompt');
    chips()[2].click();
    await wait(300);
    ok('填的是 Moss 那块的框（千问的字一个不动）',
       cfg('moss.prompt')===MIC.lib.CATS[0].items[2].pos && cfg('gen.prompt')===gp,
       cfg('moss.prompt').slice(0,24));
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 载入进度条：后端把第三方文本条折算成百分比后，前端这段要换成真刻度
    "loadbar": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const inp=()=>document.querySelector('#view [data-role=prog]');
  const txt=()=>inp().parentElement.parentElement.querySelector('[data-role=pgtext]').textContent;
  try{
    await wait(1500);
    const s=MIC.s.st, sv={};
    ['running','status','load_pct','load_stage','done','total'].forEach(k=>sv[k]=s[k]);
    /* 每次都「改状态 → 立刻 render → 立刻读 DOM」：mock 的定时器随时改写 st，
       中间插一个 await 就可能被它覆盖，测出来的就不是这段逻辑了 */
    s.running='load';s.load_pct=0;s.load_stage='';MIC.render();
    ok('第一帧前用不确定动画', inp().parentElement.classList.contains('indet')
        && inp().style.width==='', inp().style.width);
    s.load_pct=42;s.load_stage='载入 text_encoder';MIC.render();
    ok('有百分比就换成真刻度', !inp().parentElement.classList.contains('indet')
        && inp().style.width==='42%', inp().style.width);
    ok('文字带阶段名', /^载入 42% · 载入 text_encoder/.test(txt()), txt());
    Object.keys(sv).forEach(k=>{s[k]=sv[k];});
    s.running='gen';s.done=3;s.total=8;MIC.render();
    ok('去噪阶段回到步数刻度', inp().style.width==='38%' && /^去噪 3\\/8/.test(txt()),
        inp().style.width+' | '+txt());
    Object.keys(sv).forEach(k=>{s[k]=sv[k];});MIC.render();
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 环境体检卡：两个引擎分区各自「一键补齐」，补完自动重新体检（都跑在 mock 的假补全上）
    "env": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const btns=()=>[].slice.call(document.querySelectorAll('#view button')).map(b=>b.textContent.trim());
  const cards=()=>[].slice.call(document.querySelectorAll('#view .card'));
  const head=c=>{const h=c&&c.querySelector('.card-h');return h?h.textContent:'';};
  const pills=()=>[].slice.call(document.querySelectorAll('#view .mrow .pill'))
      .map(p=>p.textContent.trim()).filter(t=>/^(就绪|没装|待补|提醒)$/.test(t));
  try{
    await wait(1800);
    const v=document.getElementById('view').textContent;
    ok('两个分区标题都在', v.indexOf('千问环境')>=0 && v.indexOf('Moss 环境')>=0);
    ok('每个分区有一句作用说明（挂在标题上悬浮看，不占明面）',
       cards().filter(c=>/diffusers 直跑/.test(c.querySelector('.card-h').getAttribute('title')||'')).length===1
       && cards().filter(c=>/内嵌 ComfyUI/.test(c.querySelector('.card-h').getAttribute('title')||'')).length===1
       && !document.querySelector('#view .card-b .sub'),
       cards().map(c=>(c.querySelector('.card-h').getAttribute('title')||'').slice(0,10)).join('|'));
    // mock：千问 3 项待补（torchao/diffusers/Turbo 权重），Moss 4 项（comfy 与 moss 前缀）
    ok('千问分区给出「一键补齐 3 项」', btns().some(t=>/一键补齐 3 项/.test(t)), btns().join('|'));
    ok('Moss 分区给出「一键补齐 4 项」', btns().some(t=>/一键补齐 4 项/.test(t)), btns().join('|'));
    ok('逐条「补这项」共 7 个（3+4）', btns().filter(t=>t==='补这项').length===7,
       btns().filter(t=>t==='补这项').length);
    ok('千问分区点名权重量级', /30 GB/.test(v));
    ok('补齐只留横幅与分区卡两处、顶栏不再重复一颗',
       /一键补齐/.test((document.getElementById('envslot')||{}).textContent||'')
       && !btns().some(t=>/两边都补/.test(t)), btns().slice(0,6).join('|'));
    /* 只补千问这一块：Moss 那四项必须原样待补，不能被一锅端 */
    MIC.env.fixZone('qwen');
    await wait(400);
    ok('点补齐后按钮进「补全中」', btns().some(t=>/补全中/.test(t)), btns().slice(0,6).join('|'));
    await wait(9000);
    const q=cards().filter(c=>/千问环境/.test(head(c)))[0];
    const m=cards().filter(c=>/Moss 环境/.test(head(c)))[0];
    const qBad=q?[].slice.call(q.querySelectorAll('.mrow .pill')).filter(p=>!/就绪/.test(p.textContent)).length:-1;
    const mBad=m?[].slice.call(m.querySelectorAll('.mrow .pill')).filter(p=>!/就绪/.test(p.textContent)).length:-1;
    ok('千问分区补完全绿', qBad===0, '待补='+qBad);
    ok('没打扰 Moss 分区（仍 4 项待补）', mBad===4, '待补='+mBad);
    ok('千问按钮变「已就绪」', q?/已就绪/.test(head(q)):false, q?head(q).slice(-24):'no card');
    /* 再补 Moss 这一块 */
    MIC.env.fixZone('moss');
    await wait(9000);
    /* render() 换掉了整棵 DOM：旧的 m 节点已经脱离文档，必须重新取卡才看得到新状态 */
    const m2=cards().filter(c=>/Moss 环境/.test(head(c)))[0];
    const mPills=m2?[].slice.call(m2.querySelectorAll('.mrow .pill')).map(p=>p.textContent.trim()):null;
    ok('Moss 分区补完全绿', !!m2&&mPills.length>0&&mPills.every(t=>/就绪/.test(t)),
       mPills?mPills.join('|'):'no card');
    ok('Moss 按钮变「已就绪」', m2?/已就绪/.test(head(m2)):false, m2?head(m2).slice(-24):'');
    ok('状态药丸总数不少（分区拆分没漏项）', pills().length>=12, 'rows='+pills().length);
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 懒人路径：缺环境提示只在「环境」页（别的页不被横幅挡）；Ctrl+Enter 直接开始
    "lazy": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  /* 横幅挂在 topbar 下面的全局插槽：环境页才出内容，其他页永远空着 */
  const bar=()=>document.querySelector('#envslot .envbar');
  const barBtns=()=>{const b=bar();return b?[].slice.call(b.querySelectorAll('button')).map(x=>x.textContent.trim()):[]};
  try{
    await wait(1800);
    /* 体检回来前（env_todo 还是 null）不该有任何横幅 */
    ok('没数据时横幅不占位', !bar() && MIC.s.st.env_todo===null, String(MIC.s.st.env_todo));
    ok('起始页就是生图页（没有概览页）', MIC.nav.pageOf()==='t2i', MIC.nav.pageOf());
    MIC.env.check();                 // mock 里千问 3 + Moss 4 共 7 项待补
    await wait(1200);
    const n=(MIC.s.st.env_todo||0);
    ok('生图页不挂缺环境横幅', !bar() && n>3, 'env_todo='+n);
    MIC.nav.goto('models');
    await wait(600);
    ok('环境页横幅出现（计数=两个分区的待补总和）',
       !!bar() && new RegExp('还差 '+n+' 项').test(bar().textContent),
       (bar()?bar().textContent.trim().slice(0,16):'')+' · env_todo='+n);
    ok('横幅上只有一个补齐按钮（人已经在明细页）',
       barBtns().filter(t=>/一键补齐/.test(t)).length===1 && barBtns().indexOf('看明细')<0,
       barBtns().join('|'));
    MIC.env.fixAll();
    await wait(1200);
    ok('一键补齐把横幅换成补全中', !!bar() && /补全中/.test(bar().textContent),
       bar()&&bar().textContent.trim().slice(0,16));
    ok('补全中不重复给按钮', barBtns().filter(t=>/一键补齐/.test(t)).length===0, barBtns().join('|'));
    ok('补全中给一条「看日志」的路', barBtns().filter(t=>/看日志/.test(t)).length===1, barBtns().join('|'));
    /* 切去别的页：补全中的提示也跟着收走，不追着人 */
    MIC.nav.goto('gallery');
    await wait(600);
    ok('离了环境页横幅就消失', !bar(), bar()&&bar().textContent.trim().slice(0,12));
    MIC.nav.goto('t2i');
    await wait(600);
    await wait(9000);
    MIC.nav.goto('models');
    await wait(600);
    ok('补完横幅整条消失（齐了不占地方）', !bar(),
       bar()?bar().textContent.trim().slice(0,20):'空');
    /* Ctrl+Enter：写完提示词手不离开键盘 */
    MIC.nav.goto('t2i');
    await wait(400);
    const b=document.querySelector('#view [data-start]');
    ok('生图页有可快捷键的开始按钮', !!b, b&&b.getAttribute('title'));
    MIC.s.st.running=null;
    document.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',ctrlKey:true,bubbles:true}));
    await wait(500);
    ok('Ctrl+Enter 真的开始了', !!MIC.s.st.running,
       MIC.s.st.running+' | '+MIC.s.st.status);
    /* 运行中再按同一路径不能被当成「停止」——快捷键不许误伤
       （mock 的任务推进器会把 running 从 gen 换成 load，所以判「还在跑」而不是「没变」）*/
    document.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',ctrlKey:true,bubbles:true}));
    await wait(300);
    ok('运行中不接管快捷键', !!MIC.s.st.running, String(MIC.s.st.running));
    MIC.s.st.running=null;MIC.render();
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # v6 导航：默认分组树（出图 / 系统）+ 标签名统一两字；平铺形态把分组名当副标题挂着，
    # 分组树形态那一格给的是引擎归属（编辑/重绘只有千问走得通）
    "nav": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const tabs=()=>[].slice.call(document.querySelectorAll('#tree .node.tab'));
  const path=pid=>((document.querySelector('#tree .node[data-id="'+pid+'"] .path')||{}).textContent||'').trim();
  const shown=pid=>!!document.querySelector('#tree .node[data-id="'+pid+'"]');
  try{
    await wait(1500);
    ok('默认分组树、正好两个分组', MIC.nav.state.layout==='tree'
        && document.querySelectorAll('#tree .node.grp').length===2);
    const names=tabs().map(n=>n.querySelector('.nm').textContent.trim());
    ok('七个标签：生图/编辑/重绘/画廊/环境/日志/设置',
       names.join('|')==='生图|编辑|重绘|画廊|环境|日志|设置', names.join('|'));
    ok('名称全是两字（竖排才对齐得整齐）', names.every(t=>t.length===2), names.join('|'));
    ok('组名也是两字：出图|系统',
       MIC.nav.allGroups().map(g=>g.name).join('|')==='出图|系统',
       MIC.nav.allGroups().map(g=>g.name).join('|'));
    ok('七页都在分组里、顶层不留散页', MIC.nav.allTabs().every(n=>!!MIC.nav.find(n.id).parent));
    /* 每页都渲染得出来：侧栏点一遍，看有没有哪页留白或抛异常 */
    const gone=[],pages=['t2i','edit','inpaint','gallery','logs','models','settings'];
    for(const p of pages){
      MIC.nav.goto(p);
      await wait(420);
      const v=document.getElementById('view');
      if(MIC.nav.pageOf()!==p||!v||v.querySelectorAll('.card').length===0)gone.push(p);
    }
    ok('7 个功能页都能切出来且不空白', gone.length===0, gone.join('|'));
    /* 引擎归属标在行尾：切到「仅 Moss」会凭空少两页，先说在哪一页上 */
    ok('分组树里千问专属那两页标了归属', path('t_edit')==='千问'&&path('t_inp')==='千问'
        && path('t_gen')===''&&path('t_gal')==='',
       ['t_gen','t_edit','t_inp','t_gal'].map(path).join('|'));
    /* 平铺（临时解散分组）：那一格给分组路径，比归属更要紧 */
    MIC.nav.setLayout('flat');
    await wait(150);
    ok('平铺 7 个标签且带分组副标题', tabs().length===7&&path('t_inp')==='出图', path('t_inp'));
    MIC.nav.setLayout('tree');
    await wait(150);
    ok('切回分组树', document.querySelectorAll('#tree .node.grp').length===2
        && path('t_set')==='');
    /* 想自己归拢还是能建分组：新建→移入→移出→解散（空分组解散不弹确认） */
    MIC.nav.newGroup();
    await wait(250);
    const g=MIC.nav.allGroups().slice(-1)[0];
    ok('新建分组后树里三个分组', !!g&&document.querySelectorAll('#tree .node.grp').length===3);
    MIC.nav.moveTo('t_inp',g.id);
    await wait(150);
    ok('标签页能移进新分组', (g.children||[]).map(x=>x.page).join('|')==='inpaint',
       (g.children||[]).map(x=>x.page).join('|'));
    MIC.nav.moveTo('t_inp','__top__');
    await wait(150);
    MIC.nav.dissolve(g.id);
    await wait(150);
    ok('分组用完即散、标签页一个不少', MIC.nav.allGroups().length===2
        && MIC.nav.allTabs().length===7 && shown('t_inp'));
    MIC.nav.goto('t2i');
    await wait(400);
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 画廊：清单不带缩略图，滚到哪张才让后端解哪一张（一次内联 120 张是 3MB + 8 秒 CPU）
    "gal": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' · '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  try{
    await wait(1500);
    const r=await MIC.api.galleryList();
    const it=(r&&r.items)||[];
    ok('清单里有图', it.length>0, it.length+' 张');
    ok('清单不再内联缩略图（每条都不带 url）', it.every(x=>x.url===undefined));
    MIC.nav.goto('gallery');
    await wait(1500);
    const imgs=[].slice.call(document.querySelectorAll('#view img[data-g]'));
    ok('网格里每张图都挂了按需取的钩子', imgs.length===it.length, imgs.length+'/'+it.length);
    await wait(2500);
    const got=imgs.filter(el=>/^data:image/.test(el.getAttribute('src')||'')).length;
    ok('首屏看得见的缩略图当场取到（不等观察器）', got===imgs.length,
       got+'/'+imgs.length+' 张已出图');
    const bad=imgs.filter(el=>{const s=el.getAttribute('src')||'';
      return s&&!/^data:image/.test(s);}).length;
    ok('没有半截的 src', bad===0, bad);
    // 同一张再要一次应当走界面里的缓存，不该再问后端
    const before=imgs.filter(el=>/^data:image/.test(el.getAttribute('src')||'')).length;
    MIC.render();
    await wait(900);
    const after=[].slice.call(document.querySelectorAll('#view img[data-g]'))
      .filter(el=>/^data:image/.test(el.getAttribute('src')||'')).length;
    ok('整页重画后缩略图不闪没（用缓存复用）', after>=before, before+'→'+after);
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 合并轮收的尾：透明素材并成档位、Moss 并成同页双引擎、日志收成单页、API 并进设置
    "merge": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' · '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const cards=()=>[].slice.call(document.querySelectorAll('#view .card-h h2')).map(h=>h.textContent.trim());
  const segOf=k=>[].slice.call(document.querySelectorAll('#view .seg[data-k="'+k+'"] button'));
  const ta=k=>document.querySelector('#view [data-k="'+k+'"]');
  const hint=()=>{const h=[].slice.call(document.querySelectorAll('#view label.tip'))
      .filter(x=>x.textContent.trim()==='输出格式')[0];return h?h.getAttribute('title'):'';};
  const clickBtn=re=>{const b=[].slice.call(document.querySelectorAll('#view button'))
      .filter(x=>re.test(x.textContent.trim()))[0];if(b)b.click();return !!b;};
  const nLog=()=>document.querySelectorAll('#view .log').length;
  const viewTxt=()=>document.getElementById('view').textContent;
  try{
    await wait(1600);
    /* ---- 1) 并掉的独立页真没了，别留半截注册 ---- */
    ok('概览/透明/工坊/API/Moss 五页已注销',
       ['overview','rgba','pe','api','moss'].every(k=>!MIC.pages[k]),
       ['overview','rgba','pe','api','moss'].filter(k=>MIC.pages[k]).join('|')||'都没了');
    ok('每页一张日志卡的构件也拆了', !MIC.form.logcard);
    /* ---- 2) 透明素材 = 生图页的一档，切档要把整套提示词写法换掉 ---- */
    const gb=segOf('gen.mode');
    ok('输出格式给两档', gb.length===2 && /透明 PNG/.test(gb[1].textContent),
       gb.map(b=>b.textContent.trim()).join('|'));
    const phGen=ta('gen.prompt').placeholder;
    gb[1].click();
    await wait(400);
    ok('切档落到 cfg.gen.mode', String(MIC.mget(MIC.s.cfg,'gen.mode'))==='rgba',
       String(MIC.mget(MIC.s.cfg,'gen.mode')));
    ok('换档把示范提示词换了', ta('gen.prompt').placeholder!==phGen
       && /透明背景/.test(ta('gen.prompt').placeholder),
       ta('gen.prompt').placeholder.slice(0,30));
    ok('换档把提醒换了', /不是抠图/.test(hint()), hint().slice(0,40));
    /* 真按一次开始：mode 得顺着表单一路走进 payload，后端才知道这轮出的是 rgba。
       把 startGen 拦下来看参数，比让 mock 真跑一轮稳（不占界面、不受轮询改写）。 */
    const cap={};const orig=MIC.api.startGen;
    MIC.api.startGen=(p)=>{cap.got=p;return Promise.resolve({ok:false,msg:'探针拦下，不真跑'});};
    ta('gen.prompt').value='a flat vector icon, isolated on a transparent background';
    clickBtn(/开始/);
    await wait(300);
    ok('透明档把 mode=rgba 发了出去', !!cap.got&&cap.got.mode==='rgba', cap.got&&cap.got.mode);
    segOf('gen.mode')[0].click();
    await wait(400);
    ok('切回普通档', String(MIC.mget(MIC.s.cfg,'gen.mode'))==='gen'
       && ta('gen.prompt').placeholder===phGen && /透明底的图标/.test(hint()),
       String(MIC.mget(MIC.s.cfg,'gen.mode'))+' | '+hint().slice(0,20));
    ta('gen.prompt').value='a fox walking in the snow';
    clickBtn(/开始/);
    await wait(300);
    ok('普通档发的是 mode=gen', !!cap.got&&cap.got.mode==='gen'
       && /fox/.test(cap.got.prompt||''), cap.got&&cap.got.mode);
    MIC.api.startGen=orig;
    /* ---- 3) 一页两引擎：表单块跟着引擎走，灵感行填的就是当前那一块 ---- */
    ok('灵感行长在提示词框下面', !!document.querySelector('#view .insrow'),
       document.querySelectorAll('#view .insrow .chip').length+' 张卡');
    const ic0=MIC.mget(MIC.s.cfg,'gen.prompt');
    document.querySelector('#view .insrow .chip').click();
    await wait(300);
    const filled=String(MIC.mget(MIC.s.cfg,'gen.prompt')||'');
    ok('点灵感卡真的填了千问那块的框', filled.length>20 && filled!==ic0, filled.slice(0,30));
    /* 切引擎不换页：Moss 的参数在 moss.* 那一块，千问专属的档位控件收走。
       只改界面这一层的 s.engine，不走 mock 的 set_engine——那会真把任务跑起来，
       参数卡一进「运行中」就锁住，后面什么都点不动。 */
    MIC.s.st.engine='moss';MIC.render();
    await wait(400);
    ok('切 Moss：还在生图这一页，灵感行照旧', MIC.nav.pageOf()==='t2i'
        && !!document.querySelector('#view .insrow'), MIC.nav.pageOf());
    const grade=()=>{const s=document.querySelector('#view [onchange*="gradePick"]');
      return s?[].slice.call(s.options).map(o=>o.textContent.trim()):null;};
    ok('切 Moss：档位收成一个下拉（含让出显存）',
       grade()&&grade().length===4&&/让出显存/.test(grade().join('|')), (grade()||[]).join('|'));
    ok('切 Moss：种子与张数摆在明面上（不藏高级）',
       !!document.querySelector('#view .seedw[data-sk="moss.seed"]')
       && !!document.querySelector('#view [data-k="moss.count"]'),'');
    ok('切 Moss：千问专属的透明档收走',
       document.querySelectorAll('#view .seg[data-k="gen.mode"]').length===0,'');
    document.querySelector('#view .insrow .chip').click();
    await wait(300);
    ok('填入的是当前引擎那块的框', String(MIC.mget(MIC.s.cfg,'moss.prompt')||'').length>20,
       String(MIC.mget(MIC.s.cfg,'moss.prompt')||'').slice(0,30));
    MIC.s.st.engine='qwen';MIC.render();
    await wait(400);
    ok('切回千问：那一块的字没被吃掉', String(MIC.mget(MIC.s.cfg,'gen.prompt')||'')===filled,
       String(MIC.mget(MIC.s.cfg,'gen.prompt')||'').slice(0,30));
    ok('切回千问：透明档又回来了', segOf('gen.mode').length===2,'');
    /* ---- 4) 日志：只有这一页有，且「生成」档不再漏掉载入阶段 ---- */
    for(const p of ['t2i','models','settings']){
      MIC.nav.goto(p);await wait(400);
      if(nLog()){ok(p+' 页不该再有日志',false,'还有 '+nLog()+' 张');break;}
    }
    MIC.nav.goto('logs');
    await wait(500);
    ok('日志页就一张 tall 卡', nLog()===1 && !!document.querySelector('#view .log.tall'));
    ok('三个过滤档', document.querySelectorAll('#view .bar .seg button').length===3,
       [].slice.call(document.querySelectorAll('#view .bar .seg button')).map(b=>b.textContent.trim()).join('|'));
    MIC.s.logs=[{t:'10:00:00',text:'ZZ生成行',key:'gen'},{t:'10:00:01',text:'ZZ载入行',key:'load'},
                {t:'10:00:02',text:'ZZ系统行',key:'sys'}];
    MIC.logs.set('gen,load');
    await wait(500);
    const b1=document.querySelector('#view .log').textContent;
    ok('「生成」档把载入阶段一起算进来', /ZZ生成行/.test(b1)&&/ZZ载入行/.test(b1)&&!/ZZ系统行/.test(b1),
       b1.replace(/\\s+/g,' ').slice(0,44));
    MIC.logs.set('sys');
    await wait(500);
    const b2=document.querySelector('#view .log').textContent;
    ok('「系统」档只剩系统行', /ZZ系统行/.test(b2)&&!/ZZ生成行/.test(b2),
       b2.replace(/\\s+/g,' ').slice(0,44));
    MIC.logs.set('');
    await wait(400);
    /* ---- 5) API 服务并进了设置页 ---- */
    MIC.nav.goto('settings');
    await wait(600);
    const cs=cards().join('|');
    ok('设置页里有 API 服务卡', /API 服务/.test(cs), cs);
    ok('端口/令牌都在这一页', !!document.querySelector('#view [data-k="api.port"]')
       && /Bearer 令牌/.test(document.getElementById('view').textContent), cs);
    /* 折叠卡的内容一直在 DOM 里，只是 .hide 着：断言「折着」而不是「没有」 */
    const advFold=[].slice.call(document.querySelectorAll('#view .fold-h'))
      .filter(h=>/高级/.test(h.textContent))[0];
    ok('不常用的收进「高级」且默认折着', !!advFold&&advFold.classList.contains('closed')
       && /局域网访问/.test((advFold.nextElementSibling||{}).textContent||''), '');
    const curlFold=[].slice.call(document.querySelectorAll('#view .fold-b.hide'))
      .filter(x=>/curl /.test(x.textContent))[0];
    ok('curl 示例折起来了（不占首屏）', /端点与 curl 示例/.test(viewTxt()) && !!curlFold, cs);
    ok('页头不再有重复的改名/移动按钮',
       ![].slice.call(document.querySelectorAll('#view .phead button')).length, cs);
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 十九轮：首启欢迎页（选完引擎界面自动配好）+ 顶栏按千问/Moss/系统分类 + 活的副标题
    "greet": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const view=()=>document.getElementById('view').textContent;
  const crumb=()=>document.getElementById('crumb').textContent.trim();
  const sub=()=>((document.querySelector('#view .psub')||{}).textContent||'').trim();
  const tabs=()=>[].slice.call(document.querySelectorAll('#tree .node.tab .nm')).map(n=>n.textContent.trim());
  const pills=()=>[].slice.call(document.querySelectorAll('#pills .pill b')).map(n=>n.textContent.trim());
  const wcards=()=>[].slice.call(document.querySelectorAll('#view .wcard b')).map(n=>n.textContent.trim());
  try{
    await wait(1500);
    clearInterval(MIC.s.pollTimer);
    /* 引擎切换在 mock 里会真起任务（参数卡一锁后面什么都点不动），
       这段要验的是「选完有没有去对齐引擎」，所以把桥换成一支笔记下调用 */
    const calls=[],orig=MIC.api.setEngine;
    MIC.api.setEngine=n=>{calls.push(n);return Promise.resolve({ok:true,engine:n,msg:'切好了'});};
    /* ---- 1) 没选过：主区先给欢迎页 ---- */
    MIC.s.cfg.welcomed=false;MIC.render();
    await wait(300);
    ok('没选过引擎：主区换成欢迎页', /先选一路模型/.test(view())
        && document.querySelectorAll('#view .wcard').length===3, wcards().join('|'));
    ok('面包屑跟着说「欢迎」', crumb()==='欢迎', crumb());
    ok('欢迎页不重复挂一行小页头（自己带大标题）', !document.querySelector('#view .phead'),'');
    ok('三张牌：千问 / Moss / 两个都有', wcards().join('|')==='千问|Moss|两个都有', wcards().join('|'));
    ok('每张牌写了代价（体量与耗时）', /30 GB/.test(view())&&/3\\.3 秒/.test(view()),'');
    /* 体检数按引擎拆开后，选之前就该看出「这一路在这台机器上还差几项」 */
    MIC.s.st.env_todo=6;MIC.s.st.env_todo_qwen=2;MIC.s.st.env_todo_moss=4;MIC.render();
    await wait(200);
    const wr=()=>[].slice.call(document.querySelectorAll('#view .wr')).map(n=>n.textContent.trim());
    ok('三张牌各报自己那一路的待补数（合计=两路相加）',
       wr().join('|')==='这台机器还差 2 项|这台机器还差 4 项|这台机器还差 6 项', wr().join('|'));
    MIC.s.st.env_todo=0;MIC.s.st.env_todo_qwen=0;MIC.s.st.env_todo_moss=0;MIC.render();
    await wait(200);
    ok('两路都齐了改口「已就绪」，也不再挂环境横幅',
       wr().length===3&&wr().every(t=>/已就绪/.test(t))&&!/还差 \\d+ 项环境/.test(view()), wr().join('|'));
    MIC.s.st.env_todo=6;MIC.s.st.env_todo_qwen=2;MIC.s.st.env_todo_moss=4;MIC.render();
    await wait(200);
    /* ---- 2) 点「仅 Moss」：模式、导航、起始页、引擎一起对上 ---- */
    document.querySelectorAll('#view .wcard')[1].click();
    await wait(500);
    ok('选完落盘：console_mode=moss 且 welcomed=true',
       String(MIC.s.cfg.console_mode)==='moss'&&MIC.s.cfg.welcomed===true,
       String(MIC.s.cfg.console_mode)+'|'+String(MIC.s.cfg.welcomed));
    ok('导航自动收成 Moss 那一套（5 页，编辑/重绘没了）',
       tabs().length===5&&tabs().join('|').indexOf('编辑')<0, tabs().join('|'));
    ok('落在两引擎共用的生图页', MIC.nav.pageOf()==='t2i', MIC.nav.pageOf());
    ok('顺手把激活引擎对齐到 Moss', calls.join('|')==='moss', calls.join('|'));
    ok('欢迎页不再挡路', !/先选一路模型/.test(view()),'');
    /* ---- 3) 设置页那颗「重看」把这一屏叫回来 ---- */
    MIC.nav.goto('settings');
    await wait(500);
    ok('设置页有「重看欢迎页」', !![].slice.call(document.querySelectorAll('#view button'))
       .filter(b=>/重看选引擎那一屏/.test(b.textContent))[0],'');
    [].slice.call(document.querySelectorAll('#view button'))
      .filter(b=>/重看选引擎那一屏/.test(b.textContent))[0].click();
    await wait(400);
    ok('重看：欢迎页又回到主区', /先选一路模型/.test(view())
        && MIC.s.cfg.welcomed===false, String(MIC.s.cfg.welcomed));
    /* ---- 4) 顶栏三盏灯按 千问 / Moss / 系统 分着摆 ---- */
    MIC.s.cfg.welcomed=true;MIC.s.cfg.console_mode='both';
    MIC.form.commitPath('console_mode','both');MIC.nav.applyMode();MIC.render();
    await wait(400);
    ok('两者兼有：灯是 千问|Moss|系统 三颗', pills().join('|')==='千问|Moss|系统', pills().join('|'));
    MIC.s.cfg.console_mode='moss';MIC.view.tick();
    ok('仅 Moss：千问那盏不出现', pills().join('|')==='Moss|系统', pills().join('|'));
    MIC.s.cfg.console_mode='qwen';MIC.view.tick();
    ok('仅千问：Moss 那盏不出现', pills().join('|')==='千问|系统', pills().join('|'));
    /* ---- 5) 副标题是活的：跟着当前引擎与档位改口 ---- */
    MIC.s.cfg.console_mode='both';MIC.s.st.engine='qwen';
    MIC.nav.goto('t2i');MIC.render();
    await wait(300);
    ok('生图页副标题报当前引擎与档位', /千问 · .*步 · \\d+×\\d+/.test(sub()), sub());
    MIC.s.st.engine='moss';MIC.render();
    await wait(200);
    ok('切 Moss 后同一行改成 Moss', /^Moss · /.test(sub()), sub());
    MIC.s.st.engine='qwen';MIC.render();
    await wait(200);
    ok('词库那页没了：导航里不再有「词库」', tabs().join('|').indexOf('词库')<0, tabs().join('|'));
    MIC.api.setEngine=orig;
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 控制台模式：仅 Moss / 仅千问时侧栏只留那个引擎用得上的页，环境页分区与设置项同步收放
    "mode": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const tabs=()=>[].slice.call(document.querySelectorAll('#tree .node.tab .nm')).map(n=>n.textContent.trim());
  try{
    await wait(1500);
    ok('默认两者兼有：7 个标签', String(MIC.s.cfg.console_mode||'both')==='both'
        && tabs().length===7, tabs().join('|'));
    /* 切到仅 Moss：千问专属的两页从侧栏收走，共用的生图页留着 */
    MIC.form.commitPath('console_mode','moss');
    MIC.nav.applyMode();MIC.render();
    await wait(400);
    const t1=tabs().join('|');
    ok('仅 Moss：编辑/重绘收走、其余 5 页都在',
       t1.indexOf('编辑')<0 && t1.indexOf('重绘')<0 && tabs().length===5, t1);
    ok('仅 Moss：停在两引擎共用的生图页', MIC.nav.pageOf()==='t2i', MIC.nav.pageOf());
    MIC.nav.goto('edit');
    await wait(300);
    ok('仅 Moss：跳千问专属页被拦下', MIC.nav.pageOf()==='t2i', MIC.nav.pageOf());
    MIC.nav.goto('models');
    await wait(500);
    const v=MIC.$('view').textContent;
    ok('仅 Moss：环境页只剩 Moss 分区（千问的下载器也收走）',
       /Moss 环境/.test(v)&&!/千问环境/.test(v)&&!/下载权重/.test(v),'');
    /* 收起的页不只是点不到：跨页动作（成图接力/参数回填）也得给个说法，不能静默没反应 */
    MIC.s.st.last_image='D:/x/demo.png';
    MIC.runner.again('inpaint');
    await wait(200);
    ok('仅 Moss：成图接力被拦下并说明原因', /收起/.test(MIC.$('toast').textContent),
       MIC.$('toast').textContent);
    MIC.nav.goto('settings');
    await wait(400);
    const tips=()=>[].slice.call(document.querySelectorAll('#view label.tip'))
        .map(l=>l.getAttribute('title')||'').join('|');
    ok('仅 Moss：设置页收走千问的量化/offload 档，指引改挂在悬浮提示上',
       !document.querySelector('#view [data-k="console.quant"]')
       && /Moss 的档位/.test(tips()),'');
    /* 切到仅千问：Moss 只剩引擎那一档，页面本来就没有独立的 Moss 页 */
    MIC.form.commitPath('console_mode','qwen');
    MIC.nav.applyMode();MIC.render();
    await wait(400);
    ok('仅千问：7 个标签一个不少', tabs().length===7, tabs().join('|'));
    MIC.nav.goto('models');
    await wait(500);
    const v2=MIC.$('view').textContent;
    ok('仅千问：环境页千问分区和下载器都在，Moss 分区没了',
       /千问环境/.test(v2)&&/下载权重/.test(v2)&&!/Moss 环境/.test(v2),'');
    /* 切回两者兼有：被收走的设置项跟着回来 */
    MIC.form.commitPath('console_mode','both');
    MIC.nav.applyMode();
    MIC.nav.goto('settings');
    await wait(500);
    ok('切回兼有：设置页千问量化档回来',
       !!document.querySelector('#view [data-k="console.quant"]'),'');
    ok('切回兼有：7 个标签都回来', tabs().length===7, tabs().join('|'));
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 十八轮三件事：Moss 档位收成一个下拉（含让出显存）、种子改成点得动的随机开关、
    # 说明语一律挂到悬浮提示上（界面上不再摆着一排排小字）
    "tier": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' · '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const sel=()=>document.querySelector('#view [onchange*="gradePick"]');
  const pick=async v=>{const s=sel();if(!s)return false;s.value=v;
    s.dispatchEvent(new Event('change',{bubbles:true}));await wait(350);return true;};
  const seedBox=()=>document.querySelector('#view .seedw');
  try{
    await wait(1500);
    /* ---- 1) 说明语不再摆在明面上 ---- */
    ok('卡片里没有摆着的说明行', !document.querySelector('.card-b .sub')
       && document.querySelectorAll('#view .f .hint').length===0);
    const tips=[].slice.call(document.querySelectorAll('#view label.tip'));
    ok('尺寸/步数/种子/张数都带悬浮提示',
       ['尺寸','步数','种子','张数'].every(l=>tips.some(x=>x.textContent.trim()===l
         && (x.getAttribute('title')||'').length>6)),
       tips.map(x=>x.textContent.trim()).join('|'));
    /* ---- 2) 千问：步数也是下拉，两档 ---- */
    const qw=sel&&0;
    ok('千问的步数收成下拉（极速/精细）',
       [].slice.call(document.querySelectorAll('#view select'))
         .some(s=>s.options.length===2&&/精细/.test(s.options[1].textContent))&&!sel());
    /* ---- 3) Moss：一个下拉管两条轴 ---- */
    /* 引擎走真接口切：只改界面层的 s.engine，下一次轮询就把 mock 那一份 qwen 并回来 */
    await MIC.api.setEngine('moss');
    for(let i=0;i<60&&(MIC.s.st.engine!=='moss'||MIC.s.st.running);i++)await wait(150);
    MIC.render();
    await wait(300);
    const o=sel();
    ok('切 Moss 后档位是个下拉，四选一', !!o&&o.options.length===4,
       o?[].slice.call(o.options).map(x=>x.textContent.trim()).join('|'):'没有下拉');
    ok('默认落在日常档的极速', o&&o.value==='fast'
       && String(MIC.mget(MIC.s.cfg,'moss.quality'))==='fast',(o||{}).value);
    ok('引擎条上不再摆日常/让出显存两个按钮',
       document.querySelectorAll('.enginebar .seg button').length===2
       && document.querySelectorAll('.enginebar select').length===0,
       document.querySelectorAll('.enginebar button').length+' 个按钮');
    /* 只记录不拦截：档位状态得留在 mock 那一份里，否则轮询一来就翻脸 */
    const calls=[];const orig=MIC.api.mossSetTier;
    MIC.api.mossSetTier=(t)=>{calls.push(t);return orig(t);};
    ok('选「让出显存」叫的是 moss_set_tier(yield)', await pick('yield')
       && calls.join('|')==='yield'&&String(MIC.s.st.moss_tier)==='yield', calls.join('|'));
    ok('下拉这时显示让出显存', sel()&&sel().value==='yield',(sel()||{}).value);
    calls.length=0;
    ok('从让出显存选回均衡：先要回显存再改质量档', await pick('mid')
       && calls.join('|')==='daily'&&String(MIC.mget(MIC.s.cfg,'moss.quality'))==='mid',
       calls.join('|')+' | '+MIC.mget(MIC.s.cfg,'moss.quality'));
    for(let i=0;i<60&&MIC.s.st.running;i++)await wait(150);   // 等 ComfyUI 拉完，别带着「运行中」进下一步
    calls.length=0;
    ok('日常档内部换档不惊动引擎（不调档位接口）', await pick('full')
       && !calls.length&&String(MIC.mget(MIC.s.cfg,'moss.quality'))==='full', calls.join('|')||'没调');
    MIC.api.mossSetTier=orig;
    /* ---- 4) 种子：随机是点一下，不用敲 -1 ---- */
    await MIC.api.setEngine('qwen');
    for(let i=0;i<40&&MIC.s.st.engine!=='qwen';i++)await wait(150);
    MIC.s.cfg.gen.seed=-1;MIC.render();
    await wait(400);
    const b=seedBox();
    ok('种子行=开关+输入框，且摆在主层（不在高级里）', !!b
       && !b.closest('.fold-b')&&!!b.querySelector('.sw')&&!!b.querySelector('input'));
    ok('随机态：开关亮着、输入框灰着且不参与落盘',
       b.classList.contains('off')&&b.querySelector('.sw').classList.contains('on')
       && b.querySelector('input').hasAttribute('inert')&&!b.querySelector('input').dataset.k,'');
    b.querySelector('.sw').click();
    await wait(400);
    ok('点一下切到指定：输入框能写了，值落进配置',
       !seedBox().classList.contains('off')&&!seedBox().querySelector('input').hasAttribute('inert')
       && seedBox().querySelector('input').dataset.k==='gen.seed'
       && parseInt(MIC.mget(MIC.s.cfg,'gen.seed'),10)>=0,
       'cfg='+MIC.mget(MIC.s.cfg,'gen.seed'));
    const inp=seedBox().querySelector('input');
    inp.value='777';inp.dispatchEvent(new Event('change',{bubbles:true}));
    await wait(400);
    ok('写的种子数存得下', parseInt(MIC.mget(MIC.s.cfg,'gen.seed'),10)===777,
       String(MIC.mget(MIC.s.cfg,'gen.seed')));
    seedBox().querySelector('.sw').click();
    await wait(400);
    ok('再点回随机：配置回到 -1、输入框不再参与落盘',
       parseInt(MIC.mget(MIC.s.cfg,'gen.seed'),10)===-1
       && !seedBox().querySelector('input').dataset.k,
       'cfg='+MIC.mget(MIC.s.cfg,'gen.seed'));
    seedBox().querySelector('.sw').click();
    await wait(400);
    ok('切回指定：刚才那个数还留着，不用重敲',
       seedBox().querySelector('input').value==='777'
       && parseInt(MIC.mget(MIC.s.cfg,'gen.seed'),10)===777,
       '框里='+seedBox().querySelector('input').value+' cfg='+MIC.mget(MIC.s.cfg,'gen.seed'));
    /* ---- 5) 张数：连着发 N 张要真发 N 张（参数原样带给后端） ---- */
    const cap={};const orig2=MIC.api.startGen;
    MIC.api.startGen=(p)=>{cap.got=p;return Promise.resolve({ok:false,msg:'探针拦下，不真跑'});};
    const cn=document.querySelector('#view [data-k="gen.count"]');
    cn.value='4';cn.dispatchEvent(new Event('change',{bubbles:true}));
    await wait(300);
    document.querySelector('#view [data-start]').click();
    await wait(300);
    ok('张数 4 与种子 777 原样发到后端', !!cap.got&&String(cap.got.count)==='4'
       && String(cap.got.seed)==='777', JSON.stringify(cap.got&&{c:cap.got.count,s:cap.got.seed}));
    MIC.api.startGen=orig2;
    ok('构件表里能拿到 seedRow', typeof MIC.form.seedRow==='function','');
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
}

# 探针跑在哪一页上（键是探针名，值是 shoot 的页名）
PROBE_PAGE = {"inpaint": "inpaint", "again": "t2i", "repeat": "t2i", "kits": "t2i",
              "loadbar": "t2i", "env": "models", "lazy": "t2i", "nav": "t2i",
              "gal": "gallery", "merge": "t2i", "mode": "t2i", "tier": "t2i",
              "greet": "t2i"}

# 有的探针要等两轮「一键补齐」跑完（mock 里补全按秒级推进），默认 9 秒预算根本活不到收尾。
# 没列在这里的探针用默认值。
PROBE_BUDGET = {"env": 45000, "lazy": 30000, "tier": 25000}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", nargs="*", default=["settings"])
    ap.add_argument("--full", action="store_true", help="截完整页高，不只视口")
    ap.add_argument("--h", type=int, default=0, help="视口高度（配合 --full 用）")
    ap.add_argument("--toast", action="store_true", help="顺手把轻提示弹出来")
    ap.add_argument("--probe", choices=sorted(PROBE), help="跑交互探针，输出 PASS/FAIL 而不是截图")
    ap.add_argument("--pre", default="", help="截图前先跑一段 JS（1.2s 后执行），用来铺状态")
    ap.add_argument("--budget", type=int, default=0, help="无头虚拟时间预算 ms（截中途状态时调小）")
    args = ap.parse_args()

    out = os.path.join(tempfile.gettempdir(), "qic_shoot")
    os.makedirs(out, exist_ok=True)
    edge = next((p for p in EDGE if os.path.exists(p)), None)
    if not edge:
        print("找不到 Edge"); return 1

    if args.probe:
        pages = [PROBE_PAGE.get(args.probe, args.probe)]
    else:
        pages = args.pages or ["settings"]
    base = assemble(mock=True)
    made = []
    rc = 0
    for name in pages:
        tid = TAB.get(name)
        if not tid:
            print("不认识这页：%s（可选 %s）" % (name, ",".join(TAB))); continue
        assert "last_tab:'t_gen'" in base, "mock.js 的起始页写法变了，脚本要跟着改"
        html = base.replace("last_tab:'t_gen'", "last_tab:'%s'" % tid)
        if args.toast:
            html = html.replace("</body>",
                                "<script>setTimeout(function(){MIC.toast('轻提示位置核对');},5200);</script></body>")
        if args.pre:
            # 截图前先把页面铺成要看的样子（选过图 / 正在载入 / 接力之后）
            html = html.replace("</body>",
                                "<script>setTimeout(function(){%s},1200);</script></body>" % args.pre)
        if args.probe:
            html = html.replace("</body>", PROBE[args.probe] + "</body>")
        f = os.path.join(out, "%s%s.html" % (name, args.probe and "_probe" or ""))
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(html)
        url = "file:///" + f.replace(os.sep, "/")
        if args.probe:
            cmd = [edge, "--headless=new", "--no-sandbox", "--disable-gpu",
                   "--user-data-dir=" + os.path.join(out, "profile"),
                   "--window-size=1420,1100",
                   "--virtual-time-budget=%d" % (args.budget or
                       PROBE_BUDGET.get(args.probe, 9000)),
                   "--dump-dom", url]
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               timeout=180, encoding="utf-8", errors="replace")
            dom = p.stdout or ""
            # 探针脚本源码里也带着这个串，取最后一次出现才是真元素
            i = dom.rfind('<pre id="probe">')
            if i < 0:
                print("探针没跑出来（页面没起来？）")
                return 1
            i += len('<pre id="probe">')
            j = dom.find("</pre>", i)
            body = dom[i:j].replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
            print(body)
            lines = [x for x in body.splitlines() if x.startswith(("PASS", "FAIL"))]
            bad = [x for x in lines if x.startswith("FAIL")]
            # 一行结论都没有＝探针根本没跑完，不能当成通过
            if not lines:
                verdict = "FAIL 无输出（预算不够或页面没起来）"
                rc = 1
            else:
                verdict = "PASS" if not bad else "FAIL " + str(len(bad))
                rc = rc or (1 if bad else 0)
            print("\nPROBE %s: %s" % (args.probe, verdict))
            made.append("(probe)")
            continue
        png = os.path.join(out, "%s.png" % name)
        h = args.h or (1400 if args.full else 940)
        cmd = [edge, "--headless=new", "--no-sandbox", "--disable-gpu",
               "--hide-scrollbars", "--user-data-dir=" + os.path.join(out, "profile"),
               "--window-size=1420,%d" % h,
               "--virtual-time-budget=%d" % (args.budget or 6000),
               "--screenshot=" + png, url]
        if args.full:
            cmd.append("--force-device-scale-factor=1")
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=120)
        made.append(png if os.path.exists(png) else "没出图:" + name)
    for m in made:
        print(m)
    return rc


if __name__ == "__main__":
    sys.exit(main())
