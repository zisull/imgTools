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

TAB = {"overview": "t_ov", "t2i": "t_gen", "edit": "t_edit", "inpaint": "t_inp",
       "rgba": "t_rgba", "gallery": "t_gal", "pe": "t_pe", "models": "t_mod",
       "api": "t_api", "settings": "t_set"}
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
    # 成图 → 编辑页 的接力：在文生图页上跑，两个目标页都要顾到
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
    ok('送进图像编辑=一张参考图', cells()===1, 'cells='+cells());
    ok('参考图上有 × 可移除', document.querySelectorAll('#view .gcell .gdel').length===1);
    MIC.edit.del(0);
    await wait(300);
    ok('点 × 真的少一张', cells()===0, 'cells='+cells());
    MIC.runner.again('inpaint');
    await wait(900);
    ok('送进局部编辑=出画布', !!document.getElementById('paintCv'));
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
    # 环境体检卡：待补项、一键补齐、补完自动重新体检（都跑在 mock 的假补全上）
    "env": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const btns=()=>[].slice.call(document.querySelectorAll('#view button')).map(b=>b.textContent.trim());
  const pills=()=>[].slice.call(document.querySelectorAll('#view .mrow .pill'))
      .map(p=>p.textContent.trim()).filter(t=>/^(就绪|没装|待补|提醒)$/.test(t));
  try{
    await wait(1800);
    const v=document.getElementById('view').textContent;
    ok('四个分组都在', ['运行环境','依赖包','模型权重','目录'].every(g=>v.indexOf(g)>=0));
    ok('待补三项各有「补这项」', btns().filter(t=>t==='补这项').length===3, btns().join('|'));
    ok('顶栏写着还差几项', btns().some(t=>/一键补齐 3 项/.test(t)), btns().slice(0,4).join('|'));
    ok('明细另起一行没被挤掉', document.querySelectorAll('#view .minfo .fine').length>=10,
       document.querySelectorAll('#view .minfo .fine').length);
    MIC.env.fixAll();
    await wait(400);
    ok('点补齐后按钮进「补全中」', btns().some(t=>/补全中/.test(t)), btns().slice(0,4).join('|'));
    await wait(9000);
    ok('补完自动重新体检：没有待补项', btns().indexOf('补这项')<0&&pills().length>=9,
       'rows='+pills().length);
    ok('顶栏改成「环境已就绪」', btns().some(t=>/环境已就绪/.test(t)), btns().slice(0,4).join('|'));
    ok('状态药丸全绿', pills().length>0&&pills().every(t=>/就绪/.test(t)), pills().join('|'));
  }catch(e){ok('探针跑完',false,String(e));}
  document.body.insertAdjacentHTML('beforeend','<pre id="probe">'+R.join('\\n')+'</pre>');
})();
</script>
""",
    # 懒人路径：开机就在概览页看到「还差几项」→ 点一下补齐；生图页 Ctrl+Enter 直接开始
    "lazy": """
<script>
(async function(){
  const R=[],ok=(n,c,x)=>R.push((c?'PASS ':'FAIL ')+n+(x!=null?' '+x:''));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const bar=()=>document.querySelector('#view [data-role=envbar] .envbar');
  const btns=()=>[].slice.call(document.querySelectorAll('#view button')).map(b=>b.textContent.trim());
  const barBtns=()=>{const b=bar();return b?[].slice.call(b.querySelectorAll('button')).map(x=>x.textContent.trim()):[]};
  try{
    await wait(1800);
    /* 体检回来前（env_todo 还是 null）不该有任何横幅 */
    ok('没数据时横幅不占位', !bar() && MIC.s.st.env_todo===null, String(MIC.s.st.env_todo));
    MIC.env.check();                 // 概览页也做一次体检：mock 里 3 项待补
    await wait(1200);
    ok('体检后横幅出现', !!bar() && /还差 3 项/.test(bar().textContent),
       bar()&&bar().textContent.trim().slice(0,20));
    ok('横幅上就两个按钮', barBtns().filter(t=>/一键补齐|看明细/.test(t)).length===2, barBtns().join('|'));
    MIC.env.fixAll();
    await wait(1200);
    ok('一键补齐把横幅换成补全中', !!bar() && /补全中/.test(bar().textContent),
       bar()&&bar().textContent.trim().slice(0,16));
    ok('补全中不重复给按钮', barBtns().filter(t=>/一键补齐/.test(t)).length===0, barBtns().join('|'));
    await wait(9000);
    ok('补完横幅整条消失（齐了不占地方）', !bar(),
       bar()?bar().textContent.trim().slice(0,20):'空');
    /* Ctrl+Enter：写完提示词手不离开键盘 */
    MIC.nav.goto('t2i');
    await wait(700);
    const b=document.querySelector('#view [data-start]');
    ok('生图页有可快捷键的开始按钮', !!b, b&&b.getAttribute('title'));
    MIC.s.st.running=null;
    document.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',ctrlKey:true,bubbles:true}));
    await wait(500);
    ok('Ctrl+Enter 真的开始了', MIC.s.st.running==='gen'||/运行中/.test(MIC.s.st.status),
       MIC.s.st.status);
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
}

# 探针跑在哪一页上（键是探针名，值是 shoot 的页名）
PROBE_PAGE = {"inpaint": "inpaint", "again": "t2i", "loadbar": "overview", "env": "models",
              "lazy": "overview"}


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
        assert "last_tab:'t_ov'" in base, "mock.js 的起始页写法变了，脚本要跟着改"
        html = base.replace("last_tab:'t_ov'", "last_tab:'%s'" % tid)
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
                   "--virtual-time-budget=%d" % (args.budget or 9000),
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
