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

# v7：环境按模型拆成四页（基础/千问/Moss/H3）、开关总入口是欢迎页、H3 多了「视频」页
TAB = {"t2i": "t_gen", "edit": "t_edit", "inpaint": "t_inp", "video": "t_vid",
       "gallery": "t_gal", "logs": "t_log", "settings": "t_set",
       "env_base": "t_envb", "env_qwen": "t_envq", "env_moss": "t_envm", "env_h3": "t_envh"}
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
    ok('分类只点亮当前那一类（真人）', catChips().filter(c=>c.classList.contains('on')).length===1
        && /真人/.test((catChips().filter(c=>c.classList.contains('on'))[0]||{}).textContent),
       catChips().filter(c=>c.classList.contains('on')).map(c=>c.textContent).join('|'));
    ok('灵感行摊开这一类全部词条（不再翻页）',
       chips().length===MIC.lib.CATS[0].items.length,
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
    const total=MIC.lib.CATS.reduce((n,c)=>n+c.items.length,0);
    ok('折着时全部词条在 DOM 里但不显示', rows()===total&&fhide(), rows()+'/'+total);
    f.click();
    await wait(200);
    ok('点标题摊开整本', rows()===total&&!fhide(), fhide()?'还是折着':'已摊开 '+rows());
    ok('七类各有小标题、反向那类的按钮叫「填反向」',
       document.querySelectorAll('#view .fold-b .egroup').length===7
       && by(/^填反向$/).length===MIC.lib.cat('negative').items.length,
       by(/^填反向$/).length+'');
    set('gen.negative','');
    await wait(200);
    negBtns().forEach(b=>b.click());
    await wait(300);
    const negCats=MIC.lib.CATS.filter(c=>c.id!=='negative'&&c.neg).length;
    ok('有通用反向的那几类各挂一条',
       negBtns().length===negCats && cfg('gen.negative').length>5,
       negBtns().length+'/'+negCats+' | '+cfg('gen.negative').slice(0,24));
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
    # 环境页：一个模型一页，页头那颗开关就是这一路的总闸（v7）。
    # 探针跑在 env_qwen 上，跨页切一遍，最后真按一次开关看它收不收得干净。
    "env": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const btns=()=>[].slice.call(document.querySelectorAll('#view button')).map(b=>b.textContent.trim());
  const view=()=>document.getElementById('view').textContent;
  const bar=()=>document.querySelector('#envslot .envbar');
  /* 页头那一行 = 开关 + 环境名 + 一句话状态，整个页面只有它说「还差几项」 */
  const sw=()=>document.querySelector('#view .bar .sw');
  const note=()=>{const b=document.querySelector('#view .bar');if(!b)return '';
    return ((b.querySelector('.fine')||{}).textContent||'').trim();};
  const rows=()=>[].slice.call(document.querySelectorAll('#view .card'))
      .filter(c=>{const h=c.querySelector('.card-h h2');return h&&h.textContent.trim()==='明细';})
      .reduce((a,c)=>a.concat([].slice.call(c.querySelectorAll('.mrow .minfo b')).map(x=>x.textContent.trim())),[]);
  const heads=()=>[].slice.call(document.querySelectorAll('#view .card-h h2')).map(h=>h.textContent.trim());
  const pills=()=>[].slice.call(document.querySelectorAll('#view .card'))
      .filter(c=>{const h=c.querySelector('.card-h h2');return h&&h.textContent.trim()==='明细';})
      .reduce((a,c)=>a.concat([].slice.call(c.querySelectorAll('.mrow .pill')).map(p=>p.textContent.trim())),[]);
  try{
    await wait(1800);
    ok('千问页页头报这一路的欠账（含体量）',
       /还差 3 项/.test(note())&&/30\\.3 GB/.test(note()), note());
    ok('千问页给「一键补齐 3 项」', btns().some(t=>/一键补齐 3 项/.test(t)), btns().slice(0,4).join('|'));
    ok('明细只列千问自己那四行',
       rows().join('|').indexOf('MOSS-Image')<0 && rows().length===4, rows().join('|'));
    ok('权重目录与下载器留在千问页（基础页不掺模型）',
       heads().join('|').indexOf('本机模型')>=0 && heads().join('|').indexOf('下载权重')>=0,
       heads().join('|'));
    ok('横幅也只说这一路（不是全局合计 8 项）',
       !!bar()&&/这一路还差 3 项/.test(bar().textContent), bar()&&bar().textContent.trim().slice(0,14));
    /* 换页＝换一个环境：横幅、明细、按钮都得跟着换 */
    MIC.nav.goto('env_moss');
    await wait(700);
    ok('Moss 页换成自己那一差 4 项', /还差 4 项/.test(note())&&/一键补齐 4 项/.test(btns().join('|')), note());
    ok('Moss 明细里是运行时那几行', rows().join('|').indexOf('内嵌 ComfyUI')>=0, rows().join('|'));
    MIC.nav.goto('env_h3');
    await wait(700);
    ok('H3 页把下载单独点名', /下载 1 项/.test(btns().join('|'))&&/41/.test(view()), btns().slice(0,4).join('|'));
    MIC.nav.goto('env_base');
    await wait(700);
    ok('基础页没有开关（壳自己不给关）', !sw()&&/Python|磁盘/.test(rows().join('|')), rows().join('|'));
    ok('基础页齐了就不挂横幅', !bar(), note());
    /* ---- 开关：关掉这一路 = 后端根本不检，页面只剩一句说明 ---- */
    MIC.nav.goto('env_qwen');
    await wait(700);
    sw().click();                                  // MIC.env.set('qwen',0)
    await wait(900);
    ok('关掉后页里只剩一句「这一路关着」',
       /这一路关着/.test(view())&&!/明细/.test(heads().join('|')), heads().join('|'));
    ok('关掉后不再有补齐按钮', !/一键补齐/.test(btns().join('|')), btns().slice(0,4).join('|'));
    ok('关掉后横幅整条消失（不是换个说法继续提醒）', !bar(), bar()&&bar().textContent.trim().slice(0,16));
    ok('关掉后千问专属的功能页收走',
       !document.querySelector('#tree .node[data-id="t_edit"]')
       && !document.querySelector('#tree .node[data-id="t_inp"]'),'');
    ok('关掉后还留着一个开回来的门', btns().some(t=>/开启这一路/.test(t)), btns().slice(0,3).join('|'));
    sw().click();                                  // 开回来
    await wait(900);
    ok('重新开启后欠账照旧报出来', /还差 3 项/.test(note())&&!!bar(), note());
    ok('开回来功能页也回来了', !!document.querySelector('#tree .node[data-id="t_edit"]'),'');
    /* ---- 只补这一页：别的页不许被一锅端 ---- */
    MIC.env.fixZone('qwen');
    await wait(500);
    ok('点补齐后横幅换成补全中', !!bar()&&/补全中|步骤/.test(bar().textContent),
       bar()&&bar().textContent.trim().slice(0,14));
    await wait(9000);
    MIC.nav.goto('env_moss');
    await wait(900);
    ok('补千问没惊动 Moss 那一路（仍差 4 项）', /还差 4 项/.test(note()), note());
    MIC.nav.goto('env_qwen');
    await wait(900);
    ok('千问页补完全绿', pills().length===4&&pills().every(t=>/就绪/.test(t)), pills().join('|'));
    ok('补完页头改口「已就绪」且横幅消失', /已就绪/.test(note())&&!bar(), note());
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 懒人路径：缺环境的提醒只挂在会说这句话的那一页（全局横幅在 env_* 页，
    # 功能页各自给一条 notebar）；Ctrl+Enter 直接开始
    "lazy": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  /* 横幅挂在 topbar 下面的全局插槽：只有环境子页出内容，别的页永远空着 */
  const bar=()=>document.querySelector('#envslot .envbar');
  const note=()=>document.querySelector('#view .notebar');
  const barBtns=()=>{const b=bar();return b?[].slice.call(b.querySelectorAll('button')).map(x=>x.textContent.trim()):[]};
  try{
    await wait(1800);
    /* 体检回来前（env_todo 还是 null）不该有任何横幅 */
    ok('没数据时横幅不占位', !bar() && MIC.s.st.env_todo===null, String(MIC.s.st.env_todo));
    ok('起始页就是生图页（没有概览页）', MIC.nav.pageOf()==='t2i', MIC.nav.pageOf());
    MIC.env.check();                 // mock：千问 3 + Moss 4 + H3 1 共 8 项待补
    await wait(1200);
    const by=(MIC.s.st.env_todo_by||{});
    ok('待补数按环境拆好（每页只报自己那一格）',
       by.qwen===3&&by.moss===4&&by.h3===1&&MIC.s.st.env_todo===8, JSON.stringify(by));
    ok('生图页不挂全局横幅（千问引擎也不提 Moss 的欠账）',
       !bar() && !note(), 'env_todo='+MIC.s.st.env_todo);
    /* 视频页要 H3 那一路：欠账只在这页提一句，并给一条去明细页的路 */
    MIC.nav.goto('video');
    await wait(700);
    ok('视频页给自己那一行提醒（H3 差 1 项）',
       !!note()&&/H3 环境还差 1 项/.test(note().textContent)&&!bar(),
       note()&&note().textContent.trim().slice(0,20));
    [].slice.call(note().querySelectorAll('button'))[0].click();
    await wait(700);
    ok('那条提醒上的「去补齐」把人送到 H3 页', MIC.nav.pageOf()==='env_h3', MIC.nav.pageOf());
    MIC.nav.goto('env_qwen');
    await wait(700);
    ok('环境页横幅出现（只数这一路的 3 项）',
       !!bar()&&/这一路还差 3 项/.test(bar().textContent), bar()&&bar().textContent.trim().slice(0,16));
    ok('横幅上只有一个补齐按钮（人已经在明细页）',
       barBtns().filter(t=>/一键补齐/.test(t)).length===1 && barBtns().indexOf('看明细')<0,
       barBtns().join('|'));
    MIC.env.fixAll();
    await wait(1200);
    ok('一键补齐把横幅换成补全中', !!bar() && /补全中|步骤/.test(bar().textContent),
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
    MIC.nav.goto('env_moss');
    await wait(900);
    ok('补完全局横幅整条消失（齐了不占地方）', !bar(),
       bar()?bar().textContent.trim().slice(0,20):'空');
    MIC.nav.goto('video');
    await wait(700);
    ok('视频页那条提醒也一并收走', !note(), note()&&note().textContent.trim().slice(0,16));
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
    # v9 导航：三组（出图 / 环境 / 系统）12 页；标签名统一两字，专有名词除外（Moss / H3云端），
    # 分组树那一格给引擎归属，平铺那一格给分组路径
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
    ok('默认分组树、正好三个分组', MIC.nav.state.layout==='tree'
        && document.querySelectorAll('#tree .node.grp').length===3);
    const names=tabs().map(n=>n.querySelector('.nm').textContent.trim());
    ok('十二个标签：出图四个 + 环境四个 + 系统四个',
       names.join('|')==='生图|编辑|重绘|视频|基础|千问|Moss|H3|画廊|H3云端|日志|设置', names.join('|'));
    ok('名称全是两字（Moss / H3云端 按专有名词留着）',
       names.filter(t=>t!=='Moss'&&t!=='H3云端').every(t=>t.length===2), names.join('|'));
    ok('组名也是两字：出图|环境|系统',
       MIC.nav.allGroups().map(g=>g.name).join('|')==='出图|环境|系统',
       MIC.nav.allGroups().map(g=>g.name).join('|'));
    ok('十二页都在分组里、顶层不留散页', MIC.nav.allTabs().every(n=>!!MIC.nav.find(n.id).parent));
    /* 每页都渲染得出来：侧栏点一遍，看有没有哪页留白或抛异常 */
    const gone=[],pages=['t2i','edit','inpaint','video','env_base','env_qwen','env_moss',
                         'env_h3','gallery','cloud','logs','settings'];
    for(const p of pages){
      MIC.nav.goto(p);
      await wait(420);
      const v=document.getElementById('view');
      if(MIC.nav.pageOf()!==p||!v||v.querySelectorAll('.card').length===0)gone.push(p);
    }
    ok('12 个功能页都能切出来且不空白', gone.length===0, gone.join('|'));
    /* 引擎归属标在行尾：关掉环境会凭空少页，先说清每一页归谁 */
    ok('分组树里模型专属那几页标了归属',
       path('t_edit')==='千问'&&path('t_inp')==='千问'&&path('t_vid')==='H3'
       && path('t_gen')==='千问/Moss'&&path('t_gal')==='',
       ['t_gen','t_edit','t_inp','t_vid','t_gal'].map(path).join('|'));
    ok('环境四页不挂归属（页名就是环境名，再标一遍是废话）',
       ['t_envb','t_envq','t_envm','t_envh'].every(p=>path(p)===''),
       ['t_envb','t_envq','t_envm','t_envh'].map(path).join('|'));
    /* 平铺（临时解散分组）：那一格给分组路径，比归属更要紧 */
    MIC.nav.setLayout('flat');
    await wait(150);
    ok('平铺 12 个标签且带分组副标题', tabs().length===12&&path('t_inp')==='出图', path('t_inp'));
    MIC.nav.setLayout('tree');
    await wait(150);
    ok('切回分组树', document.querySelectorAll('#tree .node.grp').length===3
        && path('t_set')==='');
    /* 想自己归拢还是能建分组：新建→移入→移出→解散（空分组解散不弹确认） */
    MIC.nav.newGroup();
    await wait(250);
    const g=MIC.nav.allGroups().slice(-1)[0];
    ok('新建分组后树里四个分组', !!g&&document.querySelectorAll('#tree .node.grp').length===4);
    MIC.nav.moveTo('t_inp',g.id);
    await wait(150);
    ok('标签页能移进新分组', (g.children||[]).map(x=>x.page).join('|')==='inpaint',
       (g.children||[]).map(x=>x.page).join('|'));
    MIC.nav.moveTo('t_inp','__top__');
    await wait(150);
    MIC.nav.dissolve(g.id);
    await wait(150);
    ok('分组用完即散、标签页一个不少', MIC.nav.allGroups().length===3
        && MIC.nav.allTabs().length===12 && shown('t_inp'));
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
    ok('清单里有图', it.length>0, it.length+' 项');
    ok('清单不再内联缩略图（每条都不带 url）', it.every(x=>x.url===undefined));
    const nVid=it.filter(x=>x.video||/\\.(mp4|webm|mov|mkv)$/i.test(String(x.file||''))).length;
    MIC.nav.goto('gallery');
    await wait(1500);
    const imgs=[].slice.call(document.querySelectorAll('#view img[data-g]'));
    /* 成片那块砖不给它要缩略：一段 mp4 解首帧得引视频解码依赖，不值得 */
    ok('网格里每张图都挂了按需取的钩子（成片砖除外）',
       imgs.length===it.length-nVid&&nVid>0, imgs.length+'+'+nVid+'='+it.length);
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
    # 欢迎页＝三路环境的开关总入口（点牌＝开/关那一路），进控制台时把引擎对齐到开着的那一路；
    # 顶栏那几盏灯与左上角一行也跟着开关走
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
  const wr=()=>[].slice.call(document.querySelectorAll('#view .wr')).map(n=>n.textContent.trim());
  const brand=()=>((document.querySelector('#brand .bsub')||{}).textContent||'').trim();
  try{
    await wait(1500);
    clearInterval(MIC.s.pollTimer);
    /* 引擎切换与开关都走真接口，但这里只验「界面有没有跟着对齐」，把桥换成一支笔记下调用 */
    const calls=[],orig=MIC.api.setEngine;
    MIC.api.setEngine=n=>{calls.push(n);return Promise.resolve({ok:true,engine:n,msg:'切好了'});};
    const envCalls=[],origSet=MIC.api.envSet;
    MIC.api.envSet=(i,w)=>{envCalls.push(i+':'+(w?1:0));
      MIC.s.cfg.env_on[i]=!!w;MIC.s.st.env_on=Object.assign({},MIC.s.cfg.env_on);
      MIC.nav.applyMode();MIC.render();return Promise.resolve({ok:true,env_on:MIC.s.cfg.env_on,cfg:MIC.s.cfg});};
    /* ---- 1) 没选过：主区先给欢迎页，牌上带开关 ---- */
    MIC.s.cfg.welcomed=false;MIC.render();
    await wait(300);
    ok('没选过：主区换成欢迎页（问的是这台机器管哪几路）',
       /这台机器管哪几路/.test(view())&&document.querySelectorAll('#view .wcard').length===3,
       wcards().join('|'));
    ok('面包屑跟着说「欢迎」', crumb()==='欢迎', crumb());
    ok('欢迎页不重复挂一行小页头（自己带大标题）', !document.querySelector('#view .phead'),'');
    ok('三张牌：千问 / Moss / H3 视频', wcards().join('|')==='千问|Moss|H3 视频', wcards().join('|'));
    ok('每张牌写了代价（体量与耗时）', /30 GB/.test(view())&&/41 GB/.test(view()),'');
    ok('牌上有开关，且开关自己不吃点击（整张牌才是开关）',
       document.querySelectorAll('#view .wcard .sw').length===3
       && document.querySelectorAll('#view .wcard button').length===0,'');
    /* 待补数按环境拆开后，点之前就该看出「这一路在这台机器上还差几项」 */
    MIC.s.st.env_todo=8;MIC.s.st.env_todo_by={base:0,qwen:3,moss:4,h3:1};MIC.render();
    await wait(200);
    ok('三张牌各报自己那一路的待补数',
       wr().join('|')==='这台机器还差 3 项|这台机器还差 4 项|这台机器还差 1 项', wr().join('|'));
    /* 回到「各报自己那一路」的状态，再拿千问这张牌试开关 */
    MIC.s.st.env_todo=0;MIC.s.st.env_todo_by={base:0,qwen:0,moss:0,h3:0};MIC.render();
    await wait(200);
    ok('都齐了改口「已就绪」，也不再挂任何提醒',
       wr().length===3&&wr().every(t=>/已就绪/.test(t)), wr().join('|'));
    MIC.s.st.env_todo=8;MIC.s.st.env_todo_by={base:0,qwen:3,moss:4,h3:1};MIC.render();
    await wait(200);
    /* ---- 2) 点一张牌＝关掉那一路（不体检、不提醒、功能页收起） ---- */
    document.querySelectorAll('#view .wcard')[0].click();     // 千问
    await wait(500);
    ok('点牌走的是环境开关（qwen:0）', envCalls.join('|')==='qwen:0', envCalls.join('|'));
    ok('关掉的牌改口「已关闭 · 不体检、不提醒」',
       wr()[0]==='已关闭 · 不体检、不提醒', wr().join('|'));
    ok('关掉千问：生图页还在（Moss 也开着）、编辑/重绘收走',
       !!document.querySelector('#tree .node[data-id="t_gen"]')
       && !document.querySelector('#tree .node[data-id="t_edit"]'),'');
    ok('关掉一路不碰另一路：Moss 与 H3 的牌照旧报自己的数',
       wr().join('|')==='已关闭 · 不体检、不提醒|这台机器还差 4 项|这台机器还差 1 项', wr().join('|'));
    document.querySelectorAll('#view .wcard')[0].click();     // 开回来
    await wait(500);
    ok('再点一次开回来', envCalls.join('|')==='qwen:0|qwen:1'
       &&!!document.querySelector('#tree .node[data-id="t_edit"]'), envCalls.join('|'));
    /* ---- 3) 进控制台：welcomed 落盘、引擎对齐到还开着的那一路 ---- */
    /* 引擎已经是千问时不该多切一次（set_engine 是后台活，切一次就是一次显存搬运） */
    document.querySelector('#view .wfoot .btn').click();
    await wait(600);
    ok('进控制台落 welcomed=true', MIC.s.cfg.welcomed===true, String(MIC.s.cfg.welcomed));
    ok('当前引擎本来就开着：不重复切引擎', calls.length===0, calls.join('|'));
    ok('欢迎页不再挡路，落在生图页',
       !/这台机器管哪几路/.test(view())&&MIC.nav.pageOf()==='t2i', MIC.nav.pageOf());
    /* 关掉千问再进一次：这一回得把引擎交给还开着的 Moss，而不是停在没开的那一路 */
    MIC.env.set('qwen',0);
    await wait(500);
    MIC.s.cfg.welcomed=false;MIC.render();
    await wait(200);
    document.querySelector('#view .wfoot .btn').click();
    await wait(600);
    ok('千问关着进控制台：引擎对齐到开着的那一路（Moss）',
       calls.join('|')==='moss'&&MIC.s.cfg.welcomed===true, calls.join('|'));
    MIC.env.set('qwen',1);
    await wait(500);
    /* ---- 4) 设置页那颗「重看」与那行开关 ---- */
    MIC.nav.goto('settings');
    await wait(500);
    ok('设置页有「重看选环境那一屏」', !![].slice.call(document.querySelectorAll('#view button'))
       .filter(b=>/重看选环境那一屏/.test(b.textContent))[0],'');
    ok('设置页那行开关与欢迎页同源（三颗：千问/Moss/H3）',
       document.querySelectorAll('#view .envsw .sw').length===3,
       [].slice.call(document.querySelectorAll('#view .envsw')).map(x=>x.textContent.trim()).join('|'));
    /* ---- 5) 顶栏灯、左上角一行与侧栏按开关收放 ---- */
    MIC.s.st.engine='qwen';MIC.nav.goto('t2i');MIC.render();
    await wait(400);
    ok('三路都开：灯是 千问|Moss|系统 三颗', pills().join('|')==='千问|Moss|系统', pills().join('|'));
    /* 收放走用户点的那条路（环境开关），不直改 st.env_on：
       状态里那份只是后端配置刷出来的镜像——轮询、环境页挂载时的体检都拿配置盖它，
       前端直改下一拍就复原。探针验的是「关掉就收走」，那就得连配置一起关。 */
    const swall=async o=>{
      for(const k of ['qwen','moss','h3'])MIC.env.set(k,o[k]?1:0);
      await wait(1100);
    };
    await swall({qwen:0,moss:1,h3:1});
    ok('关掉千问：那一盏不出现、左上角不再写千问',
       pills().join('|')==='Moss|系统'&&/Moss/.test(brand())&&!/千问/.test(brand()),
       pills().join('|')+' | '+brand());
    await swall({qwen:0,moss:0,h3:0});
    ok('一路都不开：明说「所有模型环境都关着」，出图组整组收走',
       /都关着/.test(brand())&&!document.querySelector('#tree .node[data-id="t_gen"]')
       && !!document.querySelector('#tree .node[data-id="t_envq"]'), brand());
    await swall({qwen:1,moss:1,h3:1});
    ok('重新开一路：灯与页一起回来', pills().join('|')==='千问|Moss|系统'
        && !!document.querySelector('#tree .node[data-id="t_gen"]'), pills().join('|'));
    /* ---- 6) 副标题是活的：跟着当前引擎与档位改口 ---- */
    MIC.s.st.engine='qwen';MIC.nav.goto('t2i');MIC.render();
    await wait(300);
    ok('生图页副标题报当前引擎与档位', /千问 · .*步 · \\d+×\\d+/.test(sub()), sub());
    MIC.s.st.engine='moss';MIC.render();
    await wait(200);
    ok('切 Moss 后同一行改成 Moss', /^Moss · /.test(sub()), sub());
    MIC.s.st.engine='qwen';MIC.render();
    MIC.api.setEngine=orig;
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 环境开关收放的是整条路：侧栏页、设置项、跨页动作一起收，重新开启原样回来
    "sw": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const tabs=()=>[].slice.call(document.querySelectorAll('#tree .node.tab .nm')).map(n=>n.textContent.trim());
  const tips=()=>[].slice.call(document.querySelectorAll('#view label.tip'))
      .map(l=>l.getAttribute('title')||'').join('|');
  try{
    await wait(1500);
    ok('默认三路全开：12 个标签', MIC.nav.envOn().qwen!==false&&tabs().length===12, tabs().join('|'));
    /* 关千问：千问专属的两页从侧栏收走，两路共用的生图页留着。
       等满一轮轮询（800ms）再断言：开关表得是后端刷进状态的那一份，不是界面本地改的。 */
    MIC.env.set('qwen',0);
    await wait(1100);
    const t1=tabs().join('|');
    ok('关千问：编辑/重绘收走、其余 10 页都在',
       t1.indexOf('编辑')<0 && t1.indexOf('重绘')<0 && tabs().length===10, t1);
    ok('关千问：停在两路共用的生图页', MIC.nav.pageOf()==='t2i', MIC.nav.pageOf());
    MIC.nav.goto('edit');
    await wait(300);
    ok('关千问：跳千问专属页被拦下', MIC.nav.pageOf()==='t2i', MIC.nav.pageOf());
    /* 收起的页不只是点不到：跨页动作（成图接力）也得给个说法，不能静默没反应 */
    MIC.s.st.last_image='D:/x/demo.png';
    MIC.runner.again('inpaint');
    await wait(200);
    ok('关千问：成图接力被拦下并说清去哪儿开',
       /环境关着/.test(MIC.$('toast').textContent)&&/环境/.test(MIC.$('toast').textContent),
       MIC.$('toast').textContent);
    MIC.nav.goto('settings');
    await wait(400);
    ok('关千问：设置页收走千问的量化档，指引改挂在悬浮提示上',
       !document.querySelector('#view [data-k="console.quant"]')
       && /Moss 的档位/.test(tips()),'');
    ok('关千问：设置页那颗开关自己是灭的（还能一键开回来）',
       [].slice.call(document.querySelectorAll('#view .envsw'))
         .filter(x=>/千问/.test(x.textContent))[0].querySelector('.sw').className.indexOf('on')<0,'');
    /* 再关 H3（千问仍关着）：只剩 Moss 那一路。
       视频页不收走——它两条通道，本地归 h3、云端只要一个登录号；
       收走就等于把「这台机器只想用云端出片」那条路连门一起堵了（详见 vid 探针）。 */
    MIC.env.set('h3',0);
    await wait(1100);
    ok('关 H3：视频页留着（云端那条路不碰本机权重），收走的是它本地那一档',
       tabs().indexOf('视频')>=0 && tabs().indexOf('生图')>=0, tabs().join('|'));
    ok('只剩 Moss 一路：出图组两张（生图|视频），环境与系统页一页不少（10 页）',
       tabs().join('|')==='生图|视频|基础|千问|Moss|H3|画廊|H3云端|日志|设置', tabs().join('|'));
    /* 全部开回来：被收走的页与设置项原样回来（TREE 没动，只在显示层过滤） */
    MIC.env.set('qwen',1);MIC.env.set('h3',1);
    await wait(1200);
    ok('开回来：12 个标签一个不少', tabs().length===12, tabs().join('|'));
    MIC.nav.goto('settings');
    await wait(400);
    ok('开回来：设置页千问量化档跟着回来',
       !!document.querySelector('#view [data-k="console.quant"]'),'');
    MIC.nav.goto('t2i');
    await wait(400);
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 本地 H3 视频页（v7 新增）：只填「说什么 · 多长 · 多大」，首帧可选；
    # 出片落在画廊是同一种砖，但不取缩略（不为一段 mp4 引视频解码依赖）
    "vid": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' · '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const sub=()=>((document.querySelector('#view .psub')||{}).textContent||'').trim();
  const k=q=>document.querySelector('#view [data-k="'+q+'"]');
  const vtx=()=>((document.querySelector('#view')||{}).textContent||'');
  const tips=()=>[].slice.call(document.querySelectorAll('#view label.tip')).map(x=>x.title||'').join(' ');
  const btns=()=>[].slice.call(document.querySelectorAll('#view button')).map(b=>b.textContent.trim());
  const ta=()=>k('video.prompt');
  const ori=()=>document.querySelector('#view [data-ori="video.size"]');
  const segBtn=v=>document.querySelector('#view .seg[data-k="video.exec"] button[data-v="'+v+'"]');
  const flip=async(el,v)=>{el.value=v;el.dispatchEvent(new Event('change',{bubbles:true}));await wait(400);};
  const click=async(el)=>{el.click();await wait(500);};
  try{
    await wait(1800);
    ok('视频页活副标题报时长/尺寸/步数/引擎状态', /^\\d+ 秒 · \\d+×\\d+ · 4 步 · /.test(sub()), sub());
    ok('通道那一格在最上面：本地/云端两档，默认本地',
       !!segBtn('local')&&!!segBtn('cloud')&&segBtn('local').classList.contains('on'),
       btns().slice(0,4).join('|'));
    ok('只三样要填：描述、时长、清晰度×画幅（步数只读不放开）',
       !!ta()&&k('video.seconds')&&k('video.size')&&ori()
       && !document.querySelector('#view [data-k="video.steps"]'),'');
    ok('时长三档、清晰度四档 P + 自定义、朝向三档',
       k('video.seconds').options.length===3&&k('video.size').options.length===5
       && ori()&&ori().options.length===3,
       k('video.seconds').options.length+'/'+k('video.size').options.length+'/'+ori().options.length);
    const plabels=()=>[].slice.call(k('video.size').options).map(o=>o.textContent.trim());
    ok('P 档后面直接写真实分辨率：768P 横版＝原生 1344×768（不是 16 取整的 1360）',
       plabels().some(x=>/^768P : 1344 × 768$/.test(x)), plabels().join('|'));
    await flip(ori(),'v');
    ok('切竖版当场倒过来，仍按登记过的原生画幅 768×1344',
       plabels().some(x=>/^768P : 768 × 1344$/.test(x)), plabels().join('|'));
    await flip(ori(),'h');
    ok('首帧那一栏写清留空是文生视频',
       /留空=文生视频/.test((k('video.first')||{}).placeholder||''), (k('video.first')||{}).placeholder);
    /* 选自定义才出宽高两格；取整交给后端（16 的倍数），界面只负责原样送过去 */
    const cap={};const orig=MIC.api.videoGen;
    MIC.api.videoGen=p=>{cap.got=p;return Promise.resolve({ok:false,msg:'探针拦下，不真跑'});};
    await flip(k('video.size'),'custom');
    ok('切自定义：宽/高两格当场出现，朝向那格灰着留在那里（画幅由宽高自己决定，没什么可选）',
       !!k('video.cw')&&!!k('video.ch')&&ori()&&ori().disabled,'');
    k('video.cw').value='1350';k('video.cw').dispatchEvent(new Event('change',{bubbles:true}));
    k('video.ch').value='749';k('video.ch').dispatchEvent(new Event('change',{bubbles:true}));
    ta().value='一只猫推开木门，镜头缓慢推进';
    ta().dispatchEvent(new Event('input',{bubbles:true}));
    await wait(300);
    document.querySelector('#view [data-start]').click();
    await wait(400);
    ok('自定义宽高原样交给后端（取整在后端做）',
       !!cap.got&&String(cap.got.size)==='custom'
       && Number(cap.got.cw)===1350&&Number(cap.got.ch)===749,
       cap.got&&(cap.got.size+' '+cap.got.cw+'×'+cap.got.ch));
    /* 空描述不许起任务 */
    ta().value='';ta().dispatchEvent(new Event('input',{bubbles:true}));
    await wait(300);
    document.querySelector('#view [data-start]').click();
    await wait(300);
    ok('没写描述不开拍', !MIC.s.st.running&&/先写一句/.test(MIC.$('toast').textContent),
       MIC.$('toast').textContent);
    ok('拦下这一段没污染配置（清晰度仍按选的走）', String(MIC.s.cfg.video.size)==='custom',
       String(MIC.s.cfg.video.size));
    /* ---- 切到云端：同一页换执行地，账号/工作流跟着出来，步数与种子收走 ---- */
    await click(segBtn('cloud'));
    ok('云端那一档：账号与工作流两格出现，步数与种子不再摆着',
       !!k('video.cloud_acct')&&!!k('cloud.workflow')
       && !document.querySelector('#view [data-sk="video.seed"]')&&/Turbo 固定/.test(vtx())===false,
       !!k('video.cloud_acct')+'/'+!!k('cloud.workflow'));
    ok('云端副标题报「云端 · 号名」，不再报引擎',
       /云端/.test(sub())&&/4 步/.test(sub())===false, sub());
    ok('云端把参考图那格改了名（首帧只是本地那条路的说法）',
       /参考图/.test(vtx()), '');
    ok('工作流还没填：这一页直接说差什么，给一条去云端页的路',
       /还差一份工作流/.test(vtx())&&btns().some(x=>/去处理/.test(x)),
       (document.querySelector('#view .notebar')||{}).textContent);
    k('cloud.workflow').value='https://www.runninghub.cn/workflow/2103759530927673346';
    k('cloud.workflow').dispatchEvent(new Event('change',{bubbles:true}));
    await wait(500);
    ok('粘好工作流：先报缺参考图（这份 H3 工作流没有纯文字模式）',
       /差参考图/.test(sub())&&/还差一张参考图/.test((document.querySelector('#view .notebar')||{}).textContent),
       sub()+' | '+((document.querySelector('#view .notebar')||{}).textContent||''));
    k('video.first').value='C:/x/ref.png';
    k('video.first').dispatchEvent(new Event('change',{bubbles:true}));
    await wait(300);
    MIC.render();
    await wait(300);
    ok('补上参考图：提醒收走，副标题改成「随时能跑」',
       !document.querySelector('#view .notebar')&&/随时能跑/.test(sub()), sub());
    cap.got=null;
    ta().value='一只猫推开木门，镜头缓慢推进';
    ta().dispatchEvent(new Event('input',{bubbles:true}));
    await wait(300);
    document.querySelector('#view [data-start]').click();
    await wait(400);
    ok('云端开拍：交的是同一片参数（exec=cloud，尺寸仍是界面那串）',
       !!cap.got&&String(cap.got.exec)==='cloud'&&String(cap.got.size)==='custom'
       && Number(cap.got.cw)===1350, cap.got&&(cap.got.exec+' '+cap.got.size));
    /* 清晰度：云端能到 2K（短边 1440），本地停在 768——那是权重的原生档 */
    const sizes=()=>[].slice.call(k('video.size').options).map(o=>o.value);
    ok('云端清晰度到 2K：480P→1440P 七档 + 自定义',
       sizes().indexOf('2560x1440')>=0&&sizes().length===8, sizes().join('|'));
    await flip(k('video.size'),'2560x1440');
    await wait(400);
    ok('云端选 1440P 记成 2560×1440', String(MIC.s.cfg.video.size)==='2560x1440',
       String(MIC.s.cfg.video.size));
    await click(segBtn('local'));
    await wait(400);
    ok('切回本地：1440P 自动收进本地档位表（1344×768），不拿本地跑不动的数出去',
       String(MIC.s.cfg.video.size)==='1344x768'&&sizes().length===5,
       String(MIC.s.cfg.video.size)+'/'+sizes().join(','));
    await click(segBtn('cloud'));
    await wait(400);
    ok('再切回云端：这个数本来就在云端档位表里，原样留着',
       String(MIC.s.cfg.video.size)==='1344x768', String(MIC.s.cfg.video.size));
    /* 本地工作流文件：填 .json 不再多要宿主页，开跑时软件自己去平台借页面 */
    k('cloud.workflow').value='C:/x/h3.json';
    k('cloud.workflow').dispatchEvent(new Event('change',{bubbles:true}));
    await wait(500);
    ok('填本地 .json：不多要宿主页，提示里讲清开跑时自己借平台页面',
       !k('cloud.wf_host')&&/借平台页面/.test(tips())&&!document.querySelector('#view .notebar'), '');
    ok('本地 .json 也算备齐：副标题直接写「随时能跑」', /随时能跑/.test(sub()), sub());
    await click(segBtn('local'));
    ok('切回本地：步数那格（Turbo 4 步）与种子都回来，工作流格子收走',
       /Turbo 固定/.test(vtx())&&!!document.querySelector('#view .seedw')&&!k('cloud.workflow'),'');
    MIC.api.videoGen=orig;
    /* 真跑一轮：没拉起 ComfyUI 时先载入、随后自动接上出片（与后端那条路同构） */
    /* 换档会把整页重画一遍（自定义那两格要收走），所以先等这一拍落地再填描述——
       先填后画等于往已经被替换掉的 textarea 里写字，start() 读到的还是空的。 */
    await flip(k('video.size'),'1344x768');
    ta().value='一只猫推开木门，阳光落在地板上，镜头缓慢推进';
    ta().dispatchEvent(new Event('input',{bubbles:true}));
    await wait(300);
    document.querySelector('#view [data-start]').click();
    /* 起不起得来在 start() 的回调里就写进状态了，不等轮询；
       这里给一点余量只是为了别抢在回调之前读。 */
    await wait(600);
    ok('开拍：running 落 video/load（进度条走的是出片步数）',
       String(MIC.s.st.running)==='video'||String(MIC.s.st.running)==='load', MIC.s.st.running);
    for(let i=0;i<90&&MIC.s.st.running;i++)await wait(300);
    ok('出片跑完回到空闲', !MIC.s.st.running, String(MIC.s.st.running));
    MIC.nav.goto('gallery');
    await wait(1200);
    ok('成片进历史清单（带 video 标记）',
       (MIC.s.gal||[]).some(x=>/\\.mp4$/.test(String(x.file||''))), (MIC.s.gal||[]).length+' 项');
    const vids=document.querySelectorAll('#view .gcell .gvid').length;
    ok('画廊里成片是一块能点开播放的砖，不给它要缩略图',
       vids>0&&[].slice.call(document.querySelectorAll('#view .gcell .gvid'))
         .every(x=>!x.querySelector('img')), vids+' 块成片砖');
    /* 环境那一侧：本地那一路归 h3 环境，云端那一路只要一个登录号。
       所以关掉 h3 不收整页，只把「这一路停了」写在页里——
       关掉的页根本不体检（todo=0），光看 todo 会以为一切正常，点开始才报错。 */
    MIC.nav.goto('video');
    await wait(700);
    MIC.env.set('h3',0);
    await wait(700);
    ok('关 H3：视频页还在侧栏（只剩云端那条路的人也得进得来）',
       !!document.querySelector('#tree .node[data-id="t_vid"]'),'');
    ok('关 H3＋本地档：这一页直说「已关闭」，给一条开回来的路',
       /已关闭/.test((document.querySelector('#view .notebar')||{}).textContent||'')
       && btns().some(x=>/开启/.test(x)),
       (document.querySelector('#view .notebar')||{}).textContent);
    ok('副标题不再骗人：写「H3 已关闭」而不是「点开始自动拉起」',
       /H3 已关闭/.test(sub())&&/自动拉起/.test(sub())===false, sub());
    await click(segBtn('cloud'));
    ok('关着 H3 照切云端：账号/工作流照出，提醒换成云端那一条',
       !!k('video.cloud_acct')&&!/H3 环境已关闭/.test(vtx()),
       (document.querySelector('#view .notebar')||{}).textContent);
    await click(segBtn('local'));
    ok('切回本地：关闭的提醒又回来（提醒跟着这一档走，不挂全局横幅）',
       /已关闭/.test((document.querySelector('#view .notebar')||{}).textContent||''),'');
    MIC.env.set('h3',1);
    await wait(700);
    MIC.nav.goto('video');
    await wait(700);
    ok('开回来：缺项提醒跟着这一档回来，并给一条去 H3 页的路',
       !!document.querySelector('#view .notebar')
       && /H3 环境还差/.test(document.querySelector('#view .notebar').textContent),
       btns().slice(0,3).join('|'));
    /* 「齐了就不啰嗦」本地这一档在假后端里凑不出来（关着才归零、开着必差那 41G），
       同一句话由云端那条覆盖：粘好工作流后提醒当场收走。 */
    MIC.nav.goto('t2i');
    await wait(400);
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
    /* 生图尺寸：左边 P、右边横/方/竖，P 选项直接写真实分辨率 */
    const gs=()=>document.querySelector('#view [data-k="gen.size"]');
    const go=()=>document.querySelector('#view select[data-ori="gen.size"]');
    const labels=()=>gs()?[].slice.call(gs().options).map(o=>o.textContent.trim()):[];
    ok('生图尺寸是 P 档 + 朝向两件套',
       !!gs()&&!!go()&&labels().some(x=>/^1024P : 1024 × 1024$/.test(x)), labels().join('|'));
    go().value='h';go().dispatchEvent(new Event('change',{bubbles:true}));
    await wait(400);
    ok('切横版：标签与配置一起变成 1824×1024',
       labels().some(x=>/^1024P : 1824 × 1024$/.test(x))
       && MIC.mget(MIC.s.cfg,'gen.size')==='1824x1024',
       labels().join('|')+' · '+MIC.mget(MIC.s.cfg,'gen.size'));
    go().value='s';go().dispatchEvent(new Event('change',{bubbles:true}));
    await wait(400);
    ok('切回方形：恢复 1024×1024', MIC.mget(MIC.s.cfg,'gen.size')==='1024x1024',
       MIC.mget(MIC.s.cfg,'gen.size'));
    /* ---- 2) 千问：步数也是下拉，两档 ---- */
    ok('千问的步数收成下拉（极速/精细）',
       [].slice.call(document.querySelectorAll('#view select'))
         .some(s=>s.options.length===2&&/精细/.test(s.options[1].textContent))&&!sel(),
       '引擎='+MIC.s.st.engine+' 下拉='+[].slice.call(document.querySelectorAll('#view select'))
         .map(s=>(s.getAttribute('data-k')||s.getAttribute('onchange')||'?')+'=['
           +[].slice.call(s.options).map(o=>o.textContent).join('/')+']').join(' '));
    /* ---- 2b) 档位表里没有的值（老配置/画廊回填/后端默认）：留成「（原值）」，别被第一项顶掉 ---- */
    const stepSel=()=>[].slice.call(document.querySelectorAll('#view select'))
                        .find(s=>s.dataset.k==='gen.steps');
    MIC.mset(MIC.s.cfg,'gen.steps','13');MIC.render();await wait(400);
    const s2=stepSel();
    ok('表外的值补一项「13（原值）」并选中',
       s2&&s2.value==='13'&&[].some.call(s2.options,o=>/（原值）/.test(o.textContent)),
       s2?[].slice.call(s2.options).map(o=>o.textContent).join('/'):'没找到步数下拉');
    const rd=MIC.form.read()||{};
    ok('整屏 read() 带走的是 13，不是第一项「极速 · 8 步」',
       String((rd.gen||{}).steps)==='13',JSON.stringify(rd.gen||{}));
    await wait(1200);   // 轮询再跑几轮：老 bug 是每轮都补一条重复的「（原值）」
    const s3=stepSel();
    ok('轮询几轮后不重复补项', s3&&[].filter.call(s3.options,o=>/（原值）/.test(o.textContent)).length===1,
       s3?s3.options.length+' 项':'没找到');
    MIC.mset(MIC.s.cfg,'gen.steps','8');MIC.render();await wait(300);
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

PROBE["dlbar"] = """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  try{
    await wait(1800);
    /* 手动下载与一键补全共用顶部横幅：这里塞一份真形状的进度，看它画不画得对 */
    const DL={busy:true,phase:'download',repo:'Qwen/Qwen-Image-2.1-Turbo',
      done:12.7*1024*1024*1024,total:30.3*1024*1024*1024,
      speed:8.4*1024*1024,eta:1440,files_done:2,files_total:5,
      endpoint:'https://hf-mirror.com',file:'transformer/00002.safetensors'};
    Object.assign(MIC.s.st,{env_busy:false,env_step:0,env_steps:0,
      env_label:'',dl:DL});
    MIC.render();
    await wait(300);
    let slot=document.getElementById('envslot'), t=slot.textContent;
    ok('手动下载报仓库名', /下载 Qwen\\/Qwen-Image-2\\.1-Turbo/.test(t), t.slice(0,60));
    /* 一键补全时换成「第几步 / 当前项」，同一根进度条 */
    Object.assign(MIC.s.st,{env_step:1,env_steps:2,env_label:'千问 Turbo 权重'});
    MIC.render();
    await wait(300);
    slot=document.getElementById('envslot'); t=slot.textContent;
    ok('补全时报步骤与当前项', /步骤 1\\/2/.test(t)&&/千问 Turbo 权重/.test(t), t.slice(0,60));
    ok('报已下/总量与速度', /12\\.7 GB \\/ 30\\.3 GB/.test(t)&&/8\\.4 MB\\/s/.test(t), t.slice(0,90));
    ok('报剩余、文件数与镜像', /剩 24 分/.test(t)&&/2\\/5 文件/.test(t)&&/hf-mirror\\.com/.test(t),
       t.slice(60,160));
    const bar=slot.querySelector('.prog > i');
    ok('百分比条真画出来', !!bar&&parseInt(bar.style.width,10)===42, bar&&bar.style.width);
    ok('分区按钮改口「下载中…」并禁用',
       [].some.call(document.querySelectorAll('#view button'),
                    b=>/下载中/.test(b.textContent)&&b.disabled),
       [].slice.call(document.querySelectorAll('#view button'))
         .filter(b=>/中…/.test(b.textContent)).map(b=>b.textContent).join('|'));
    /* busy 一落，横幅要退回「还差 N 项」，不能残留一条永远转圈的下载 */
    MIC.s.st.dl={};
    MIC.render();
    await wait(300);
    const t2=document.getElementById('envslot').textContent;
    ok('下载结束横幅不残留', !/下载 Qwen|MB\\/s/.test(t2), t2.slice(0,50));
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
"""

PROBE["gal"] = """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const cells=()=>document.querySelectorAll('#view .gcell');
  const toast=()=>document.getElementById('toast');
  try{
    await wait(1600);
    const n0=cells().length;
    ok('画廊列出成图与成片', n0>=3 && document.querySelectorAll('#view .gcell .gvid').length>=1, n0);
    const im=document.querySelector('#view img[data-g]');
    ok('首屏缩略图按需取到了', !!im && /^data:image/.test(im.getAttribute('src')||''),
       im&&(im.getAttribute('src')||'').slice(0,22));
    const gone=cells()[0].querySelector('.gdel');
    gone.click();
    await wait(500);
    ok('删除后提示带「撤销」', !!toast().querySelector('.tact') && /已删除/.test(toast().textContent),
       toast().textContent);
    ok('这一格真的从网格里没了', cells().length===n0-1, cells().length);
    toast().querySelector('.tact').click();
    await wait(900);
    ok('撤销后这张回到网格', cells().length===n0, cells().length);
    ok('撤销有回执', /已恢复/.test(toast().textContent), toast().textContent);
    /* 图片砖才有「当首帧」，成片砖没有 */
    const vc=[].slice.call(cells()).find(c=>c.querySelector('.gvid'));
    const icell=[].slice.call(cells()).find(c=>!c.querySelector('.gvid'));
    ok('成片砖不提供首帧按钮', !!vc && !vc.querySelector('.gsend'));
    ok('图片砖提供首帧按钮', !!icell && !!icell.querySelector('.gsend'));
    icell.querySelector('.gsend').click();
    await wait(1000);
    const first=String(MIC.s.cfg.video.first||'');
    ok('首帧写进了配置', /\\.(png|jpg|jpeg|webp)$/i.test(first), first);
    const inp=document.querySelector('#view [data-k="video.first"]');
    ok('已经跳到视频页', !!inp, (document.getElementById('crumb')||{}).textContent);
    ok('首帧框显示这张', !!inp && inp.value===first, inp&&inp.value);
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
"""

PROBE["win"] = """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const calls=[];
  try{
    await wait(1500);
    /* mock 里没有窗口桥，win.init 本来会自己跳过：换一套假几何，把两条起手路径都跑一遍 */
    MIC.api.booted=()=>true;
    MIC.api.winGeo=()=>Promise.resolve({x:100,y:100,w:1200,h:800,min_w:900,min_h:560,maxed:false});
    MIC.api.winMove=(x,y)=>{calls.push(['move',x,y]);return Promise.resolve({ok:true});};
    MIC.api.winSet=(x,y,w,h)=>{calls.push(['set',x,y,w,h]);return Promise.resolve({ok:true});};
    MIC.win.init();
    const md=(el,t,x,y)=>el.dispatchEvent(new MouseEvent(t,{bubbles:true,
      clientX:x,clientY:y,screenX:x+300,screenY:y+50,button:0}));
    const rim=document.querySelector('#rzg .rz[data-move="1"]');
    ok('外圈直边标成拖动位', !!rim);
    md(rim,'mousedown',200,2);
    await wait(40);
    ok('按下边缘进入拖动态', document.body.classList.contains('win-drag'));
    md(document,'mousemove',240,12);
    await wait(40);
    ok('边缘拖动只移窗不缩放',
       calls.some(c=>c[0]==='move')&&!calls.some(c=>c[0]==='set'), JSON.stringify(calls));
    md(document,'mouseup',240,12);
    ok('松手退出拖动态', !document.body.classList.contains('win-drag'));
    /* 角上仍是缩放；顺带验证 document 那一路没有把 mode 抢成拖窗 */
    calls.length=0;
    const corner=document.querySelector('#rzg .rz[data-edge="ne"]');
    md(corner,'mousedown',1400,2);
    await wait(40);
    md(document,'mousemove',1440,40);
    await wait(40);
    ok('四角按下还是缩放',
       calls.some(c=>c[0]==='set')&&!calls.some(c=>c[0]==='move'), JSON.stringify(calls));
    md(document,'mouseup',1440,40);
    /* 正文空白处照旧任意位置拖 */
    calls.length=0;
    const blank=document.querySelector('.topbar .grow');
    md(blank,'mousedown',700,20);
    await wait(40);
    md(document,'mousemove',730,30);
    await wait(40);
    ok('空白处仍能拖窗', calls.some(c=>c[0]==='move'), JSON.stringify(calls));
    md(document,'mouseup',730,30);
    /* 控件上按下不许拖 */
    calls.length=0;
    const inp=document.querySelector('#view .inp');
    md(inp,'mousedown',600,300);
    await wait(40);
    md(document,'mousemove',640,330);
    await wait(40);
    ok('输入框上按下不拖窗', calls.length===0, JSON.stringify(calls));
    md(document,'mouseup',640,330);
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
"""

# 探针跑在哪一页上（键是探针名，值是 shoot 的页名）
PROBE_PAGE = {"inpaint": "inpaint", "again": "t2i", "repeat": "t2i", "kits": "t2i",
              "loadbar": "t2i", "env": "env_qwen", "lazy": "t2i", "nav": "t2i",
              "gal": "gallery", "merge": "t2i", "sw": "t2i", "tier": "t2i",
              "greet": "t2i", "vid": "video", "dlbar": "env_qwen", "win": "t2i"}

# 有的探针要等两轮「一键补齐」跑完（mock 里补全按秒级推进），默认 9 秒预算根本活不到收尾。
# 没列在这里的探针用默认值。
PROBE_BUDGET = {"env": 60000, "lazy": 40000, "tier": 25000, "vid": 45000, "sw": 20000,
                "greet": 30000, "dlbar": 30000, "gal": 30000, "win": 20000}


def main():
    # 探针输出里带 emoji（❌/✅），GBK 控制台默认会直接抛 UnicodeEncodeError
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
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
