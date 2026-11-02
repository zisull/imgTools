# DrissionPage 4.1.1.4 速查（AI 版）

来源：官网 4.1.1.4 全量文档（65 页）+ 本地包 `.pyi` 签名逐条核对。签名默认值可信。
完整原文（按需 grep，别整读）：`D:\hw\docs\DrissionPage官方文档-4.1.1.4.md`

## 0 心智模型

- 三层：`Chromium`（管浏览器/标签页）→ `Tab`（管一个标签页，90% 操作在这）→ `Element`（交互）。
- `Chromium()` 同端口重复调用返回同一对象；进程结束不关浏览器，下次同 addr 自动接管（调试友好）。
- `tab(...)` 是 `tab.ele(...)` 的简写，可链式：`tab('#s_fm')('#su')`。
- 查找/点击/等待全部内置超时，默认 `tab.timeout=10`；找不到元素返回 `NoneElement`（不抛）。
- 双模：`d`=浏览器（可交互），`s`=requests（快几个量级，不可交互）。只在需要渲染/点击时用 d，取数据切 s。

## 1 连接与启动

```python
from DrissionPage import Chromium, ChromiumOptions, SessionPage, WebPage, ChromiumPage
browser = Chromium()                 # 默认 127.0.0.1:9222，自动启动或接管
browser = Chromium(9333)             # 接管/启动指定端口（'ip:port'、'ws://...' 同理）
tab = browser.latest_tab
```

`Chromium(addr_or_opts=None, session_options=None)`；`ChromiumOptions(read_file=True, ini_path=None)`，链式，**仅在启动时生效**（接管已开浏览器时除 address/local_port 外全部无效）。

常用 `co` 方法（均返回自身）：

```
set_browser_path(p)  set_local_port(n)  set_address('ip:port')  set_paths(local_port, user_data_path)
set_user_data_path(p) set_tmp_path(p)  set_cache_path(p)  use_system_user_path(on=True)
auto_port(on=True, scope=None)   new_env()   incognito()   headless(on=True)   mute()   no_imgs()   no_js()
ignore_certificate_errors()      set_user_agent(ua)        set_flag(flag, value=None)
set_argument(arg, value=None)    remove_argument(arg)      clear_arguments()
set_pref(name, value)  remove_pref(name)  remove_pref_from_file(name)  clear_prefs()
set_timeouts(base=None, page_load=None, script=None)  set_retry(times=None, interval=None)
set_load_mode('normal'|'eager'|'none')  set_proxy('http://ip:port')  set_download_path(p)
add_extension(p)  remove_extensions()  existing_only(on=True)  user='Default'/set_user(u)
save(path=None)  save_to_default()
```

- 默认值：端口 `9222`；`browser_path='chrome'`（找不到查注册表）；超时 `base=10 page_load=30 script=30`；`retry_times=3`、`retry_interval=2`。
- 默认 ini：`<site-packages>/DrissionPage/_configs/configs.ini`（升级会被重置）；项目根放 `dp_configs.ini` 优先读（`dp -c` 或 `configs_to_here()` 生成）。
- 用户文件夹：默认 `%TEMP%\DrissionPage\userData\<端口>`（复用、不清）；`auto_port()` → `%TEMP%\DrissionPage\autoPortData\<端口>`（用完删除、每次全新）。
- 多浏览器并存：每个必须**独立端口 + 独立用户文件夹**，或共用一个 `auto_port()` 配置对象。
- 接管手动开的浏览器：给快捷方式/命令行加 `--remote-debugging-port=9333`，再 `Chromium(9333)`。
- 关无头残留：`browser.quit(timeout=5, force=False, del_data=False)`；`co.headless(False)` 会自动关掉旧无头进程。

## 2 定位语法（最高频，务必记牢）

`ele(locator, index=1, timeout=None)` / `eles(locator, timeout=None)` / `tab(locator)`。`index` 从 1 起、可负倒数；`index=2` 比 `eles()[1]` 快。找不到：`ele`→`NoneElement`，`eles`→`[]`。

逻辑符：`@` 单属性｜`@@` 与｜`@|` 或｜`@!` 否定。`@@` 与 `@|` 不可同句混用。

```
@id=one          单属性；只写 @id = 含该属性即可
@@class=p_cls@@text()=第三行     与
@|id=row1@|id=row2               或
@!id=one          否定；@!class = 没有 class 属性
```

匹配模式（对属性名和属性值都适用）：`=` 精确、`:` 包含、`^` 开头、`$` 结尾。例 `@href^=https`、`@id:ow`。tag 与 `xpath`/`css` 只走精确（`:` 与 `=` 等效）。

句首简写（**必须位于句首且单独使用**）：

```
#one  → @id=one        .cls → @class=cls      '第二' / text:第二 → 模糊文本
tag:div → @tag()=div   css:.a > div           xpath:.//div[@id='x']
简化名：t:=tag  c:=css  x:=xpath  tx:=text  @tx()=@text()   例 tab('t:a')、tab('x://div')
```

- 无任何匹配符时 = 模糊文本匹配：`tab('文档')` == `tab('text:文档')`。
- `@text()` 只看**直接文本节点**；`@@text():前沿` 搜元素内全部文本。用 `@@/@|` 时 text 不能当唯一条件（会命中最外层），要配 `tag:`。
- 多 class 不加 `.`，整串按普通字符串比，空格是普通字符（与 selenium 不同）。
- 文本含 `&nbsp;` 等实体要转 `\uXXXX`：`'第\u00A0二'`。要匹配 `"text:"` 本身写 `text:text:`。
- 属性名含特殊字符（如 `@`）→ 用 css 并 `\` 转义；值里含 `@@`/`@|` → 改用 xpath。
- `tag:p@class=p_cls`、`tag:p@@class=p_cls@@text()=第二行`、`tag:div@text():abc`（仅直接节点）/`tag:div@@text():abc`（全文）。
- 支持 selenium 元组：`tab.ele((By.ID, 'one'))`（`from DrissionPage.common import By`）。
- 元素内可用完整 xpath 并取属性返回字符串：`ele.ele('xpath://div/@class')`；`'//'` 前的 `'.'` 可省略。
- 别用 IDE 复制的绝对 xpath/css（易失效、不能相对定位、不能跨 iframe）。

其他查找：

```
find(locators, any_one=True, first_ele=True, timeout=None)  → (定位符, 元素或列表) / dict
get_frame(loc_ind_ele, timeout=None) → ChromiumFrame|NoneElement   # 定位符/序号/id/name/对象
get_frames(locator=None, timeout=None) → List[ChromiumFrame]       # None=全部，很慢慎用
s_ele(locator=None, index=1, timeout=None) / s_eles(locator, timeout=None)  # 静态副本，批量解析提速
ele.shadow_root / .sr   → 可当查找入口链式：tab('#app').sr('#x').sr.eles('t:item')
tab.active_ele → 焦点元素
```

相对定位（DOM 节点级，可返回 str——如 `next('xpath:text()',1)`）：

```
parent(level_or_loc=1, index=1, timeout=0)  child(locator='', index=1, timeout=None, ele_only=True)
children(...)  next(locator=''|int, index=1, ...)  nexts(...)  prev(...)  prevs(...)
after/befores/before/afters —— 全文档范围，不限同级
首参传数字自动当 index；ele.east/west/south/north(loc_or_pixel=None, index=1)、offset(x,y)、over(timeout=None)
视觉相对定位仅 d 模式、仅可见元素、locator 只支持 str（不支持 xpath/css）
```

列表筛选（`eles()`/`nexts()` 返回的 list 自带）：

```
eles.filter.tag(name, equal=True)/.attr(n,v,equal=True)/.style/.property/.text(t, fuzzy=True, contain=True)
     /.displayed()/.checked()/.selected()/.enabled()/.clickable()/.have_rect(equal=True)   # 链式，与关系
eles.filter_one(N).text('图')        # 取第 N 个符合条件的元素（不传 N 可省括号）
eles.search(displayed=True).enabled() / search_one(...)   # 或关系，仅浏览器列表
eles.get.texts() / .links() / .attrs(name) → List[str]
```

## 3 标签页 / 访问 / 页面操作（Tab）

```
browser.get_tab(id_or_num=None, title=None, url=None, tab_type='page', as_id=False)
browser.get_tabs(...)  browser.latest_tab  browser.tabs_count  browser.tab_ids
browser.new_tab(url=None, new_window=False, background=False, new_context=False)
browser.activate_tab(id_ind_tab)  browser.close_tabs(tabs_or_ids, others=False)
tab.close(others=False)  tab.disconnect()  tab.reconnect(wait=0)   # 长跑内存高时 reconnect
```

- `tab_type='page'` 只取普通页；序号按激活顺序非视觉顺序；`new_context=True` 的标签不共享 cookies。

访问：

```
tab.get(url, show_errmsg=False, retry=None, interval=None, timeout=None) -> bool   # 支持本地文件
tab.post(url, params=None, data=None, json=None, headers=None, cookies=None, files=None,
         auth=None, allow_redirects=True, proxies=None, hooks=None, stream=None, verify=None, cert=None)
tab.back(steps=1) tab.forward(steps=1) tab.refresh(ignore_cache=False) tab.stop_loading()
```

- 加载模式：`normal` 等全部资源（默认）｜`eager` DOM 就绪即停｜`none` 连上就返回、超时也不自动停（须自己 `stop_loading()`）。`get()` 已内置等待，**不要再补 `wait.load_start()`**。
- 「加载完成」只指主文档，不含 js 触发的加载与重定向。

脚本 / CDP / 元素增删：

```
tab.run_js(script, *args, as_expr=False, timeout=None)   # args 对应 arguments[0..]；as_expr=True 须是表达式且 args 失效
tab.run_js_loaded(...)  tab.run_async_js(script, *args, as_expr=False)
tab.run_cdp(cmd, **cmd_args) -> dict   tab.run_cdp_loaded(...)   # 如 tab.run_cdp('Page.stopLoading')
tab.add_ele(html_or_info, insert_to=None, before=None)   # 传 (tag,{attr:val}) 且不指定 insert_to → 不插入DOM，须 ele.click(by_js=True)
tab.remove_ele(loc_or_ele)  tab.set.blocked_urls(urls)   # 支持 '*'
```

设置（`tab.set.*`）：

```
set.timeouts(base=None, page_load=None, script=None)   set.retry_times(n)  set.retry_interval(s)
set.load_mode.normal()/eager()/none()   set.user_agent(ua, platform=None)   set.headers(dict|str)
set.cookies(...)/.clear()/.remove(name,url=None,domain=None,path=None)
set.session_storage(item, value) / set.local_storage(item, value)   # value=False 删该项
set.auto_handle_alert(on_off=True, accept=True)   set.scroll.smooth(on=True) / set.scroll.wait_complete(on=True)
set.window.max()/mini()/full()/normal()/size(w=None,h=None)/location(x=None,y=None)/hide()/show()
set.activate()   # 把本标签页切到前台（不是 window 下）
set.download_path(p)  set.download_file_name(name=None, suffix=None)  set.when_download_file_exists('rename'|'overwrite'|'skip')
set.upload_files(files)   set.NoneElement_value(value=None, on_off=True)  # 浏览器级：browser.set.*
```

- `window.hide()` 依赖 pypiwin32、仅 Windows，且新窗口出现会重新显示。平滑滚动建议 `set.scroll.smooth(False)`。

滚动（`tab.scroll.*` / `ele.scroll.*`）：

```
scroll(pixel=300) 向下 | down/up/left/right(pixel=300)
to_top() to_bottom() to_half() to_rightmost() to_leftmost() to_location(x, y)
tab.scroll.to_see(loc_or_ele, center=None)      # 页面级：滚到元素可见
ele.scroll.to_see(center=None) / to_center()    # 元素级：把自己滚进视口
```

弹窗 / 截图 / 存页 / 信息：

```
tab.handle_alert(accept=True, send=None, timeout=None, next_one=False) -> str|False
  accept=None 只取文本不点按钮；send 给 prompt 输入；next_one=True 处理下一个（离页弹窗）
tab.states.has_alert / is_loading / is_alive / ready_state('connecting|loading|interactive|complete')
tab.get_screenshot(path=None, name=None, as_bytes=None, as_base64=None, full_page=False, left_top=None, right_bottom=None)
ele.get_screenshot(path=None, name=None, as_bytes=None, as_base64=None, scroll_to_center=True)
tab.save(path=None, name=None, as_pdf=False, **kw)   # 都不传只返回内容；默认 mhtml
tab.html（不含 iframe）  tab.json  tab.title  tab.url  tab.tab_id  tab.user_agent  tab.url_available
tab.rect.size/viewport_size/window_size/window_location/window_state/scroll_position/page_location/viewport_location
tab.timeout / timeouts / retry_times / retry_interval / load_mode
tab.cookies(all_domains=False, all_info=False).as_str()|.as_dict()|.as_json()
tab.session_storage(item=None)  tab.local_storage(item=None)  tab.clear_cache(session_storage=True, local_storage=True, cache=True, cookies=True)
```

## 4 元素交互与信息（Element）

```
ele.click(by_js=False, timeout=1.5, wait_stop=True) -> ele|False    # 同 ele.click.left(...)
   by_js: False 纯模拟（遮挡也点该位置，不可见/不可用返回 False）｜True 纯 js｜None 先模拟、遇阻改 js ← 最常用
   timeout 是点击前等「可见+可用+进视口」的超时；wait_stop=True 先等元素停止运动
ele.click.right()  ele.click.middle(get_tab=True)→新tab  ele.click.multi(times=2)
ele.click.at(offset_x=None, offset_y=None, button='left', count=1)   # button 可选 left/middle/right/back/forward
ele.click.for_new_tab(by_js=False, timeout=3)→Tab
ele.click.for_url_change(text=None, exclude=False, by_js=False, timeout=None)→bool
ele.click.for_title_change(...)→bool
ele.click.to_upload(file_paths, by_js=False)      # 多文件传 list 或 '\n' 分隔
ele.click.to_download(save_path=None, rename=None, suffix=None, new_tab=None, by_js=False, timeout=None)→DownloadMission
ele.input(vals, clear=False, by_js=False)→ele     # 组合键用 tuple；by_js=True 不能输组合键；末尾 '\n' 当回车
ele.clear(by_js=False)→ele  ele.focus()→ele  ele.check(uncheck=False, by_js=False)
ele.hover(offset_x=None, offset_y=None)→ele       # hover 出菜单后再点菜单项
ele.drag(offset_x=0, offset_y=0, duration=0.5)  ele.drag_to(ele_or_loc, duration=0.5)
ele.set.attr(name, value='') / .property(n,v) / .style(n,v) / .innerHTML(html) / .value(v)；ele.remove_attr(name)
ele.run_js(script, *args, as_expr=False, timeout=None)   # 脚本里 this = 元素，要返回值须写 return
ele.run_async_js(...)  ele.add_init_js(script)→id / ele.remove_init_js(id=None)
ele.scroll.*（见上，元素级）  ele.select.*（见下）
```

下拉列表（非 `<select>` 元素 `ele.select` 为 `False/None`，用前先判）：

```
select(text, timeout=None) ≡ select.by_text(...)  by_value / by_index(从1) / by_locator / by_option
cancel_by_text / cancel_by_value / cancel_by_index / cancel_by_locator / cancel_by_option
all() / clear() / invert()（仅多选有效）；属性 is_multi / options / selected_option / selected_options
```

信息与属性：

```
tag  html(outer)  inner_html  text(已格式化，含子孙)  raw_text(原始)  texts(text_node_only=False)→List[str]
comments→List[str]  attrs→dict  attr(name)→str|None（src/href 已补全绝对路径）  property(name)  value
link→str|None  pseudo.before/.after→str  style(name, pseudo_ele='')→str  child_count  xpath  css_path
shadow_root/.sr  == 比较是否同一元素
states: is_displayed is_enabled is_clickable(不判遮挡) is_checked is_selected
        is_in_viewport is_whole_in_viewport is_alive(页面刷新后失效) is_covered(False|覆盖元素id) has_rect
rect: size location midpoint click_point corners viewport_corners viewport_location
      viewport_midpoint viewport_click_point screen_location screen_midpoint screen_click_point scroll_position
ele.src(timeout=None, base64_to_bytes=True)→bytes|str|None   # 直读缓存，无需二次下载
ele.save(path=None, name=None, timeout=None, rename=True)→str
eles.get.texts()/.links()/.attrs(name)
```

- `attr('src')` 已补全路径，要原始值取 `attrs['src']`。混排文本用 `texts(text_node_only=True)`。

Shadow DOM：不能跨级查，必须逐级 `.sr`。嵌套 iframe 序号定位不准（有两个是嵌套关系），改用定位符/id/name。

## 5 等待 / 监听 / 控制台 / 动作链 / 双模

```
tab.wait.eles_loaded(locator, timeout=None, any_one=False, raise_err=None)→bool
tab.wait.ele_displayed(loc_or_ele,...) / ele_hidden / ele_deleted → bool
tab.wait.load_start(...) / doc_loaded(...)      # 仅 load_mode='none' 才需要
tab.wait.title_change(text, exclude=False, timeout, ...) / url_change(...) → tab|False
tab.wait.alert_closed(timeout)  tab.wait.upload_paths_inputted()
tab.wait.download_begin(timeout=None, cancel_it=False)→DownloadMission|False
tab.wait.downloads_done(timeout=None, cancel_if_timeout=True)→bool
browser.wait.new_tab(timeout=None, curr_tab=None, raise_err=None)→id|False
browser.wait.download_begin(...) browser.wait.downloads_done(...)   # 闪现标签页的下载必须用 browser 级
ele.wait.displayed/hidden/deleted/covered/not_covered/enabled/disabled/disabled_or_deleted/has_rect/stop_moving/clickable
任意对象.wait(second, scope=None)  # scope 给定时等 [second, scope) 随机秒
```

- 所有 `timeout=None` 默认用页面 timeout（`listen.wait`/`downloads_done` 例外 = 无限等）；`raise_err=None` 按 `Settings` 决定返回 False 还是抛。

网络监听（拿接口数据，比解析 DOM 稳）：

```
tab.listen.start(targets=None, is_regex=None, method=None, res_type=None)   # 必须在 get/click 之前
tab.listen.set_targets(targets=True, is_regex=False, method=('GET','POST'), res_type=True)
tab.listen.wait(count=1, timeout=None, fit_count=True, raise_err=None) → DataPacket | list | False
tab.listen.steps(count=None, timeout=None, gap=1) → 可迭代，实时逐包
tab.listen.wait_silent(timeout=None, targets_only=False, limit=0)→bool
tab.listen.pause(clear=True) / resume() / clear() / stop() / targets
packet: tab_id frameId target url method is_failed resourceType request response fail_info wait_extra_info(timeout=None)
packet.request: url method params(dict) headers cookies postData(json→dict) extra_info
packet.response: url headers status statusText mimeType body(json→dict, base64→bytes) raw_body timing extra_info
packet.fail_info: errorText canceled blockedReason corsErrorStatus
```

- 坑：`start(targets=...)` 会把 `is_regex` 重置为 False，用正则必须每次显式 `is_regex=True`；未 stop 再次 `start` 会清空已抓队列；`stop` 清队列不清 targets；符合条件的水包进队列，页面刷走不丢。
- `res_type` 可按资源类型过滤（`Document/XHR/Fetch/Image/Media/...`），`method=True` 监听全部。

控制台（只收页面主动 `console.log` 等）：

```
tab.console.start()/stop()/clear()  tab.console.wait(timeout=None)→ConsoleData|False
tab.console.steps(timeout=None)  tab.console.messages（读即清空）  tab.console.listening
ConsoleData: source level text body(text 的 json) url line column
```

动作链（模拟鼠标键盘，真鼠标不动，可多标签并行）：

```
tab.actions.<step>（内置，会先等文档加载完）  或 Actions(page)（不等）；链式即时生效，无需 perform()
move_to(ele_or_loc, offset_x=None, offset_y=None, duration=0.5)  move(dx,dy,duration) up/down/left/right(pixel)
click(on_ele=None, times=1) r_click m_click  hold(on_ele=None) release(...) r_hold r_release m_hold m_release
scroll(delta_y=0, delta_x=0, on_ele=None)  key_down(key) key_up(key)  input(text) type(keys)
drag_in(ele_or_loc, files=None, text=None, title=None, baseURL=None)   # 外部文件/文本拖入
wait(second, scope=None)；属性 owner curr_x curr_y
拖拽 = ac.hold('#a').release('#b')
```

双模 / 模式切换（`WebPage`+`MixTab` 才有；`Chromium`+`ChromiumTab`、`ChromiumPage` 没有）：

```
page = WebPage(mode='d', chromium_options=None, session_or_options=None)   # 需要双模就用它
tab.mode → 'd'|'s'
tab.change_mode(mode=None, go=True, copy_cookies=True)   # mode=None 切到另一模式
tab.cookies_to_session(copy_user_agent=True) / tab.cookies_to_browser()
```

- 切换只同步 cookies 不同步 headers；站点校验 headers 会卡超时 → `change_mode('s', go=False)` 后自建 headers。
- s 模式下 `ele()/get()` 作用于 requests 结果，返回 `SessionElement`（不可交互）；d 模式独占：点击/输入/js/开关标签页/截图。
- 切到 s 后可 `close()`/`quit()` 关掉浏览器继续收发。

录像（需 `pip install opencv-python`，路径与文件名建议纯英文）：

```
tab.screencast.set_mode.video_mode()/frugal_video_mode()/js_video_mode()/imgs_mode()/frugal_imgs_mode()
tab.screencast.set_save_path(p) / start(save_path=None) / stop(video_name=None, suffix='mp4', coding='mp4v')
```

## 6 下载与上传

- 下载管理**默认不开启**：只有设过 `co.set_download_path()` 或 `set.download_path()`（或用了 `click.to_download`）才启用，且不弹「另存为」；未设路径 = 下到程序当前目录。
- `browser.set.download_path` 只影响之后新建 Tab；Tab 级仅本 Tab。`set.download_file_name` 只对**下一个**文件生效，用完自动清空。
- **文件名在下载结束时才重命名**，之前是临时任务 id → 必须 `mission.wait()` / `downloads_done()` 之后才拿得到最终名。
- 闪现标签页触发的下载：`tab` 抓不到，必须 `browser.set.download_file_name()` + `browser.wait.download_begin()`。

```
mission = ele.click.to_download(save_path=None, rename=None, suffix=None, new_tab=None, by_js=False, timeout=None)
tab.set.download_path(r'D:\tmp'); tab.set.download_file_name('new')
mission = tab.wait.download_begin(); path = mission.wait(show=True, timeout=None, cancel_if_timeout=False)
DownloadMission: url tab_id id folder name tmp_path state('running|done|canceled|skipped')
                 total_bytes received_bytes final_path is_done rate  wait(...) cancel()
```

内置多线程下载器（已知直链 / 批量 / 大文件用它，非浏览器行为）：

```
page.download(url, save_path, ...) → ('success', '路径')            # 阻塞单线程
page.download.add(url, save_path=None, split=True) → Mission        # >50M 默认分块多线程
page.download.set.save_path(p) / set.block_size('30m') / set.线程数/重试/超时/冲突处理/日志
page.download.missions → dict{id: Mission}   get_mission(id)   get_failed_missions() → list
Mission: id rate state info result data（data 存原始参数，可重试）
```

上传三种：

```
ele.click.to_upload(paths, by_js=False)                              # 推荐，自动拦截文件框
tab.set.upload_files(paths) → btn.click() → tab.wait.upload_paths_inputted()   # 手动式
tab('tag:input@type=file').input(paths)                              # 传统式；无视 clear 参数总会先清空
```

- 填入是异步的，必须 `wait.upload_paths_inputted()`。异域 iframe 上传要用 **iframe 对象**的 `set/wait`，用 tab 设置无效。

## 7 SessionPage（纯 requests，不启浏览器）

```
page = SessionPage(session_or_options=None)   # Session 对象 | SessionOptions | None 读 ini | False 用内置
page.get(url, show_errmsg=False, retry=None, interval=None, timeout=None, params=None, data=None, json=None,
         headers=None, cookies=None, files=None, auth=None, allow_redirects=True, proxies=None,
         hooks=None, stream=None, verify=None, cert=None) -> bool     # post 参数完全一致
其余方法用原生：page.session.request/delete/...  page.response.status_code
不返回 Response：结果从 page.html / page.json / page.raw_data / page.title / page.url / page.encoding 读
查找：page('loc') page.ele(...) page.eles(...) page.find(...) 相对定位同 Element，返回 SessionElement（只读）
批量：eles.get.texts()/.links()/.attrs(name)
设置：page.set.retry_times/.retry_interval/.timeout/.encoding/.headers/.header/.user_agent/
      .proxies(http,https)/.auth/.hooks/.params/.verify/.cert/.stream/.trust_env/.max_redirects/.add_adapter
      page.set.cookies(...)/.clear()/.remove(name)  page.cookies(all_domains=False, all_info=False)
`SessionOptions(read_file=True, ini_path=None)` 同名方法（set_headers/set_a_header/remove_a_header/clear_headers/
      set_cookies/set_timeout/set_retry/set_proxies/set_download_path/set_auth/set_hooks/set_params/set_verify/
      set_cert/set_stream/set_trust_env/set_max_redirects/add_adapter）+ save()/save_to_default()
SessionElement: tag html inner_html text raw_text texts() comments attrs attr(name) link value
                child_count page xpath css_path（不能 click/input/js）
```

- headers 等 kwargs 是**逐项覆盖**，不是整体替换；自动补 Host/Referer、自动判编码；`url` 可指向本地 html 做静态解析。

## 8 全局开关与报错

```
from DrissionPage.common import Settings, Keys, By
Settings.set_raise_when_ele_not_found(on=True)   # 找不到元素立刻抛（默认返回 NoneElement）
Settings.set_raise_when_click_failed(on=True)    # 点击失败抛（默认返回 False）
Settings.set_raise_when_wait_failed(on=True)     # 等待失败抛
Settings.set_singleton_tab_obj(on=True)          # False → 一个标签页可存在多个 Tab 对象，latest_tab 返回 id
Settings.set_cdp_timeout(second)                 # 默认 30
Settings.set_browser_connect_timeout(second)     # 默认 30
Settings.set_auto_handle_alert(accept=True)      # 全局弹窗，None 不处理
Settings.set_language('zh_cn'|'en')  Settings.set_suffixes_list(path)   # 均返回 Settings，可链式
组合键：ele.input((Keys.CTRL, 'a', Keys.DEL))；内置 CTRL_A/C/X/V/Z/Y
```

报错对照（写 try 时按根因区分）：`ElementNotFoundError` 找不到｜`CanNotClickError` 不可点｜`WaitTimeoutError` 等待超时｜`ElementLostError`/`ContextLostError` 页面刷新后用了旧元素（取到就尽快转 `s_ele()` 或重取）｜`PageDisconnectedError` 页已关｜`BrowserConnectError` 端口/地址不对或浏览器没带调试端口｜`AlertExistsError` 有未处理弹窗时跑 js｜`NoRectError` 点击报「无位置及大小」，多为定位符命中了同名元素，确属无形元素用 `click(by_js=True)`｜`NoResourceError` src/save 取资源失败｜`IncorrectURLError`/`CookieFormatError`/`StorageError`/`LocatorError` 格式或站点限制。

## 9 性能与选型

- 批量解析：最外层容器 `s_ele()` 转静态一次，再在其中 `s_eles()`；别反复转（官网样例 4s → 0.28s）。
- 只要数据不要渲染 → `SessionPage`；接口能监听 → `tab.listen`，都优于 d 模式解析 DOM。
- 提速组合：`co.headless().no_imgs().mute().set_load_mode('none')` + `listen`/`ele` 拿到即 `tab.stop_loading()`。
- 打包：用只装 DrissionPage 的新虚拟环境（约 14M）；避免依赖 ini 时 `ChromiumOptions(read_file=False)` 且 `Chromium(..., session_options=False)`。
- 浏览器建议 ≥100 版本；整页/视口外截图要求 Chrome 90+。
