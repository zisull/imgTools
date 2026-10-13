/* pages/blank.js —— 兜底页：导航绑定了不存在的功能页时显示 */
(function(){
const MIC=window.MIC=window.MIC||{};
MIC.registerPage('__blank__',{
  title:'页面不存在',sub:'这个标签页绑定的功能页还没有注册',icon:'tool',
  render(){
    return `<div class="empty">没有对应的功能页 · 用「绑定功能页」重新选一个，或右键导航「恢复默认导航」</div>`;
  },
});
})();
