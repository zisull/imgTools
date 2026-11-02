/* pages/video.js —— H3 视频：一句描述 → 一段带声音的成片
   两个通道出同一样的片、进同一个画廊，只差「在哪跑」：
     本地＝自己的卡拉起 ComfyUI，占显存、不花钱，4 步是权重里烘死的；
     云端＝RunningHub 那份工作流，不占显存、按平台计费，要一个保存过的登录号。
   所以切换通道只换执行地，描述/时长/尺寸/参考图这四个键两条路共用，不各留一套。 */
(function(){
const MIC=window.MIC=window.MIC||{};
const C=MIC.form, ic=MIC.ic, esc=MIC.esc;

const LEN=[{code:'5',name:'5 秒'},{code:'10',name:'10 秒'},{code:'15',name:'15 秒'}];

/* H3 的原生画幅是 1344×768（768P / 16:9），竖屏镜像 768×1344。
   按 16 取整会算成 1360，所以给这一档登记一个换算：下拉里写的、换朝向写回的、
   后端算的全是同一套数——以前前端一套 sizeOf、后端一套 tier×ratio，两边各算各的。 */
const NATIVE={h768:[1344,768],v768:[768,1344]};
C.dimSnap['video.size']=function(p,o){
  const n=NATIVE[o+p];
  return n?{w:n[0],h:n[1]}:C.pDims(p,o);
};

/* 换通道顺手把清晰度收进这一档的档位表：云端能到 2K，本地只到 768（权重原生档）。
   不收的话，在云端选了 1440P 再切回本地，界面写着 2560×1440、后端按本地上限缩成别的数——
   界面上写的数就不是出片的数了。'custom' 是用户自己填的，不动。 */
C.segFit['video.exec']=function(val,patch){
  const list=val==='cloud'?C.P_VIDEO_CLOUD:C.P_VIDEO;
  const m=/^(\d+)x(\d+)$/i.exec(String((patch.video||{}).size||''));
  if(!m)return;
  const w=+m[1],h=+m[2],cap=list[list.length-1];
  if(Math.min(w,h)<=cap)return;
  const d=C.dimSnap['video.size'](C.pOf(Math.min(w,h),list),C.orientOf(w,h));
  MIC.mset(patch,'video.size',d.w+'x'+d.h);
};

/* 云端那一格读的是账号档案（只读，绝不为「看一眼」拉起浏览器）。
   登录/换号在另一页做，回来时这里得自己跟上：隔一会儿重读一次，内容没变就不重画，
   免得把正在打的字打断（与「H3云端」页同一套刷新节奏）。 */
let brief=null,briefing=false,last=0;
function sig(o){return JSON.stringify([o&&o.dp,o&&o.accts,o&&o.wf,o&&o.busy]);}
function askBrief(force){
  if(briefing)return;
  if(!force&&brief&&Date.now()-last<8000)return;
  briefing=true;
  MIC.api.cloudBrief().then(r=>{
    briefing=false;last=Date.now();
    if(!r)return;
    const changed=sig(r)!==sig(brief);
    brief=r;
    if(changed)repaint();
  }).catch(()=>{briefing=false;});
}
/* 重读有可能落在人正在打字的时候：那一下先不重画，下一轮再补 */
function repaint(){
  const a=document.activeElement;
  const typing=a&&/^(INPUT|TEXTAREA)$/.test(a.tagName)&&a.closest&&a.closest('#view');
  if(!typing)MIC.render();
}
/* 工作流只有一个真源：界面里那一格写的就是配置，档案（brief）只是它的镜像。
   只读镜像的话，人刚粘完地址、提醒还挂着「差工作流」——那玩意儿 8 秒才重读一次。 */
function wfNow(){
  const c=(MIC.s.cfg&&MIC.s.cfg.cloud)||{};
  return String(c.workflow||(brief&&brief.wf)||'').trim();
}
/* 本地导出的那份（.json/.txt）没有平台工作流编号：开页时自动借一页 H3 画布，不再要人填宿主页 */
const isFile=()=>/\.(json|txt)$/i.test(wfNow());
const firstNow=()=>String(((MIC.s.cfg||{}).video||{}).first||'').trim();
function cloudReady(){return !!brief&&brief.ready&&!!wfNow();}
function acctName(v){
  const list=(brief&&brief.accts)||[];
  const hit=list.filter(a=>a.id===v.cloud_acct)[0]||list[0];
  return hit?hit.name:'没号';
}

/* 尺寸只有一个来源：video.size（WxH）。'custom' 时才看 cw/ch，
   与后端 _h3_size 的优先级排法一致，界面上写的数就是出片的数。 */
function dimText(v){
  const s=String(v.size||'');
  if(s==='custom')return C.a16(Number(v.cw)||1344)+'×'+C.a16(Number(v.ch)||768);
  return s?s.replace('x','×'):'—';
}

/* 描述语下面那行是活的：这一段到底会出成什么样，不用点开始才知道 */
function liveSub(){
  const s=MIC.s.st,v=MIC.s.cfg.video||{};
  const bits=[String(v.seconds||5)+' 秒',dimText(v)];
  if(String(v.exec)==='cloud'){
    bits.push('云端',acctName(v));
    bits.push(s.running==='video'?'平台侧计时'
      :(!cloudReady()?'差登录或工作流':(!firstNow()?'差参考图':'随时能跑')));
    return bits.join(' · ');
  }
  bits.push('4 步');
  bits.push((MIC.s.st.env_on||MIC.s.cfg.env_on||{}).h3===false?'H3 已关闭'
            :s.comfyui_on?(s.comfyui_loaded?'引擎在跑':'引擎启动中'):'点开始自动拉起');
  return bits.join(' · ');
}

MIC.registerPage('video',{
  title:'视频生成',sub:liveSub,icon:'film',
  render(){
    const s=MIC.s.st,v=MIC.s.cfg.video||{},run=!!s.running;
    const cloud=String(v.exec)==='cloud';
    if(cloud&&!briefing)askBrief();

    /* 两条路都需要的四样：说清想要什么、多长、多大、从哪张图开始 */
    const shared=
      C.field('通道',C.seg('video.exec',[['local','本地'],['cloud','云端']],true),
        cloud?'云端跑：不占显存、按平台计费，要一个保存过的登录号'
             :'本机跑：拉起 ComfyUI、占显存，不花钱；4 步是权重里烘死的')+
      C.field('描述',
        C.ta('video.prompt',4,
          '一只猫推开木门，阳光落在地板上，镜头缓慢推进')+
        `<div class="btnrow" style="margin-top:6px"><button class="btn sm gho"`+
        ` onclick="MIC.polish.prompt('video.prompt','video')">${ic('wand','s')}AI 润色</button></div>`,
        '写清动作和镜头怎么动，比堆形容词管用；带声音的片子连环境音一起出')+
      '<div class="grid3">'+
        C.field('时长',C.sel('video.seconds',LEN),
          '帧数会自动贴到模型认的 17k+5 网格，所以选 5 秒可能出来 5.2 秒')+
        C.field('清晰度',C.pSizeSel('video.size',cloud?C.P_VIDEO_CLOUD:C.P_VIDEO,{cw:'video.cw',ch:'video.ch'}),
          cloud?'P=短边，云端按宽高出片，最高 2K（短边 1440＝2560×1440）'
               :'P=短边；768P 是权重原生档 1344×768，再往上是算法放大，不值那几分钟')+
        (cloud?C.field('账号',acctSel(v),'用哪个号的登录态出片；留默认＝档案里第一个可用的号')
              :C.field('步数','<span class="mut fine">4 步 · Turbo 固定</span>',
                '权重里那条 Turbo LoRA 就是训到 4 步的，加步数只会更糊；要换步数得先换 LoRA'))+
      '</div>'+
      (String(v.size)==='custom'?'<div class="grid3">'+
        C.field('宽（px）',C.num('video.cw','1344'),'自动贴到 16 的倍数')+
        C.field('高（px）',C.num('video.ch','768'),'自动贴到 16 的倍数')+
      '</div>':'')+
      C.field(cloud?'参考图（必填）':'首帧',
        C.pathrow('video.first',cloud?'选一张图：云端按参考生成，纯文字不接':'留空=文生视频 · 选一张图=从它开始动','file'),
        cloud?'上传到这个号的平台 input 里当首帧/身份参考。这份 H3 工作流只有图生与参考生视频两种模式，不填平台会判失败'
             :'想接着上一段拍就把那一帧存成图填进来')+
      (cloud?wfRow():'')+
      (cloud?'':C.field('种子',C.seedRow('video.seed'),'开着每次换一版；关掉固定种子可复现'))+
      MIC.runner.action('MIC.video.start()');

    /* 缺什么就在这一页说，不动全局横幅：本地差开关/权重、云端差号或工作流，各自一条短提示。
       「已关闭」和「还差几项」是两件事：关掉时后端根本不体检，todo 是 0，
       于是页面看着一切正常、点开始才报错——所以开关这一层单独判，别让绿状态骗人。 */
    const off=!cloud&&(MIC.s.st.env_on||MIC.s.cfg.env_on||{}).h3===false;
    const todo=Number((s.env_todo_by||{}).h3)||0;
    const note=off
      ?`<div class="notebar">${ic('power','s')}<b>H3 环境已关闭：本地这一路整条停用</b><span class="grow"></span>`+
        `<button class="btn sm pri" onclick="MIC.env.set('h3',1)">开启</button>`+
        `<button class="btn sm" onclick="MIC.nav.goto('env_h3')">去看明细</button></div>`
      :(!cloud&&todo
        ?`<div class="notebar">${ic('db','s')}<b>H3 环境还差 ${todo} 项</b><span class="grow"></span>`+
          `<button class="btn sm pri" onclick="MIC.nav.goto('env_h3')">去补齐</button></div>`
        :(cloud&&brief&&(!cloudReady()||!firstNow())
          ?`<div class="notebar">${ic('globe','s')}<b>${esc(cloudHint())}</b><span class="grow"></span>`+
            (cloudReady()?'':`<button class="btn sm pri" onclick="MIC.nav.goto('cloud')">去处理</button>`)+
            `</div>`
          :''));
    return note+C.duo(
      C.card('生成参数','film',C.lock(run,shared)),
      MIC.runner.runCard(cloud?'云端这一段要等平台排，出片前别关这个软件':'说清想要什么画面就能开拍'));
  },
});

/* 云端两格：账号从档案里列（只列存过登录态的），工作流是这一路唯一必填的平台参数。
   工作流绑在 cloud.workflow：以后视频以外还有云端活用时，它是环境那一条，不是任务那一条。
   填本地导出的 .json 也行：托管前端能把图灌进页面；导出的文件不带平台编号，
   开跑时软件自己借一页已知能开的 H3 画布进去（换图不换实例），不用再填宿主页。 */
function acctSel(v){
  const list=(brief&&brief.accts)||[];
  if(!list.length)return '<span class="mut fine">还没有可用的号 · 到「H3云端」页登录并保存</span>';
  return C.sel('video.cloud_acct',list.map(a=>({name:a.name,code:a.id})),'默认第一个号');
}
function wfRow(){
  const local=isFile();
  return C.field('工作流',
      C.pathrow('cloud.workflow',local?'本地导出的工作流（.json）':'网页上跑通过的 H3 工作流地址或 ID','file',true),
    '粘贴浏览器里那份能出片的 H3yun 工作流地址，或把「导出工作流」存下来的 .json 拖进来。'+
    (local?' 本地文件开跑时自己借平台页面，不用再填别的。':'')+
    (wfNow()?'':' 现在还没填，填了云端这条路才算通。'));
}
function cloudHint(){
  const b=brief||{};
  if(b.dp===false)return '缺 DrissionPage：到「环境 → 基础」补齐后重开软件';
  if(!(b.accts||[]).length)return '还没有可用的登录号：到「H3云端」页新建登录并保存';
  if(!wfNow())return '还差一份工作流：在上面那格粘贴网页上跑通过的地址';
  if(!firstNow())return '云端还差一张参考图：这份工作流按参考生成，纯文字平台会判失败';
  return '云端还差一步';
}

/* 换号/保活都在后台线程：坐在这一页时账号清单会自己变旧。
   和「H3云端」页同一套节奏——到点重读，内容真变了才重画，打字的时候不打扰。 */
setInterval(()=>{
  if(!MIC.nav||MIC.nav.pageOf()!=='video')return;
  if(String((MIC.s.cfg.video||{}).exec)!=='cloud')return;
  if(!briefing&&Date.now()-last>8000)askBrief();
},1500);

let firing=false;
MIC.video={
  start(){
    if(firing||MIC.s.st.running)return;
    const patch=MIC.form.commit();
    const v=Object.assign({},MIC.s.cfg.video||{},patch.video||{});
    if(!String(v.prompt||'').trim()){MIC.toast('先写一句想要什么画面');return;}
    firing=true;
    MIC.api.videoGen(v).then(r=>{
      firing=false;
      if(!r||!r.ok){MIC.toast((r&&r.msg)||'任务没起来');return;}
      MIC.s.st.running='video';MIC.s.st.done=0;MIC.s.st.total=r.total||4;
      MIC.s.st.status='运行中…';
      MIC.render();
    }).catch(e=>{firing=false;MIC.toast('启动失败：'+(e.message||e));});
  },
};
})();
