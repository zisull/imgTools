# H3yun 全量盘点与合并方案（待审核）

> 2026-11-01 · 只做设计，没改代码、没下载、没占显存。
> 范围按你重述的那句：**整个 H3yun**，不只视频那条链路。
> 配套文档：本地视频权重那条线在 [H3视频方案设计.md](H3视频方案设计.md)；**落地顺序与最简产品形态已被 [剧本一键成片方案.md](剧本一键成片方案.md) 取代**（云端必须有 + 只给剧本就出成片），这份保留功能盘点。

## 一、三条结论

1. **云端能出视频，但它不是本地模型的替代品，是另一条产线。**
   H3yun 的「云端」= DrissionPage 驱动 Chrome/Edge 打开 RunningHub 的工作流页，用 JS 直接改 iframe 里那个 `FeiHouEasyH3RH` 节点（389）的控件值，点提交，然后每 5 秒读输出节点（325）的 `videopreview` 拿 COS 地址再下载。
   它能给到 **15 秒、1080P、带声、零显存、零下载、并发=账号数**；代价是**没有 LoRA/步数/种子**、**网页一改版整条链就废**、**掉登录就停**、**任务号只在内存**（重启不继承，续跑靠扫盘）、**按积分扣钱**。
   本地能给的是 **0.9 秒热态出图、可控、离线、边际成本为零**；本地要换到「15 秒带声视频」得先下 41.4 GB、每次再等 4~10 分钟。
   → 判定：**互补，不互替**。云端在「按时长批量出货」上比这台 12G 机器实用，本地在「随手出图 + 可控」上不可替代。

2. **H3yun 里最值钱的不是视频，是那条创作管线。**
   剧本 → 分镜 → 资产台账 → 缺图核对 → 全局序号 → 断点续跑 → 剧集存档，这一整套**跟云端无关、也跟本地引擎无关**，是纯逻辑代码，而 Moss 控制台目前**一条都没有**：Moss 只有「一句提示词、一张图、一次一张」。

3. ~~**云端出图（geeknow.ai）不合并。**~~ **（本轮已修正，见 [剧本一键成片方案.md](剧本一键成片方案.md) §附）**
   原判断的前提是「这台机器本地已覆盖」；用户把**低配机器也纳进目标用户**之后前提变了——没卡的人连参考图都出不了。改法：不内置某家服务，做成**可配的 OpenAI 兼容出图端点**（默认空），弱机填一个 Key 就能全流程跑通；有卡仍优先本地（0.9s/张）。反向建议照旧成立：H3yun 的出图可以直接改调 Moss 已提供的 `/v1/images/generations`。

## 二、H3yun 的骨架（先看它自己怎么分层）

| 层 | 文件（行数） | 是否依赖云端 | 判定 |
|---|---|---|---|
| 创作管线 | `storyboard.py`(17.6k) `deepseek_client.py`(43.6k) `episode_store.py`(21.2k) | 只依赖一个 LLM Key | **整体移植** |
| 资产体系 | `asset_sheet.py`(44.6k) `assets.py`(15.5k) `asset_check.py`(14.7k) | 出图那步依赖 geeknow，台账本身不依赖 | **移植台账，出图换本地** |
| 出片执行 | `browser.py`(128k) `workflow.py`(17.6k) `account_pool.py`(27.9k) `runner.py`(1.4k) | 强依赖 RunningHub + 浏览器自动化 | **拆两半：调度移植，自动化进可选环境** |
| 配置与存档 | `config.py`(161k) `history/` `project.json` | 不依赖 | **移植规则，不搬载体** |
| 界面 | `ui.py`(501k，9122 行 tkinter) | 不依赖 | **不移植**，只移植行为 |

`ui.py` 一上来就是 9122 行 tkinter：顶部剧本栏 + 「一份剧本一个页签」的 NoteBook + 三个设置页（基础 / AI 与剧集 / 规范与高级）+ 底部三栏（分镜列表 / 运行日志 / 生成结果）+ 右栏两个页签（资产库 / 场景服装·锚点·元素），动作加起来 100 多个。**这个形态不搬**，Moss 是 pywebview 单页、导航平铺、文案要短——照搬等于把刚减掉的层级加回去。

## 三、逐功能判定（全集）

标记：**合**=逻辑直接移植；**改**=移植思路但换成 Moss 的实现；**云**=只在云端环境里才成立；**不**=不移植。

### 3.1 创作管线

| 功能 | H3yun 怎么做 | 判定 | 落到 Moss 哪里 |
|---|---|---|---|
| 剧本文件夹=一部剧、一文件=一集 | 自然排序，标题按 `[-—_·空白]` 切，utf-8/utf-8-sig/gbk 兜底 | 合 | 新 `webui/series/script_io.py`，「剧集」页的项目选择 |
| 剧集工程文件 | `<项目>/project.json`（version=1），磁盘为真源 | 合 | **原样兼容**：Moss 直接读写同一份，能打开 H3yun 的历史项目 |
| 全局序号 1..N 跨集锁定 | `assign_missing_indices` 返回 {旧:新}，`rename_videos` 两步改名防互换 | 合 | 队列的排序依据，文件名规则 |
| 分镜表 | `storyboards:[{index,references,source,scene_anchor,scene_elements,prompt}]` | 合 | `store.py` 加 `shots` 表（只是缓存，真相在 project.json） |
| 分镜容错解析 | 去围栏 → loads → 抓 `[…]` → 括号配对只捞已闭合对象；字段别名；seconds 夹 5.0–15.0 | 合 | 血泪代码，**逐字搬**，别自己重写一遍 |
| 分镜 prompt 六段结构 | 首行 `【单元XX】15秒 / 主题：…` + subject_definitions/summary/retention_analysis/detailed_description/overall_soundscape/non_diegetic_music | 合 | 云端与本地 H3 通用；声音段正好对上 H3「一次出音画」 |
| 分段方式（AI 导演 / 固定 15 秒，下限5上限15） | 写进 user 消息 | 改 | 本地走 17k+5 网格：5/10/15 秒 = 124/243/362 帧 |
| DeepSeek 转分镜 | system=分镜规范 + user 分块拼装（附加要求→分段→参考图对照→资产词库→可用资产→图片→服装→正文→5 条硬规则），前缀顺序为跨集缓存命中 | 改 | 移植拼装顺序与缓存这个思路；模型走可配的 OpenAI 兼容端点（DeepSeek 或本机 llama.cpp） |
| 「改原文重转本镜」+ 单镜编辑器 | 弹窗改原文再重转 | 合 | 分镜行内「重转」按钮 |
| 按顺序重排全剧序号 / 清除本集或全部分镜 | 有 | 合 | 剧集页工具条 |
| 文档批量优化 | 4000 字分块、并发 6、900s 超时 | 不 | 剧本创作不是控制台的活 |
| 断点续跑两个开关 | 「已转分镜的集跳过」「已存在非空视频则跳过」，0 字节算中断 | 合 | 队列的默认行为，**本地也一样用** |
| 本轮文件夹 | `前缀_日期_时刻`，清全部分镜后自动换新轮 | 改 | 批量出图/出视频按组建目录，单张仍平铺 `outputs/` |

### 3.2 资产体系

| 功能 | H3yun 怎么做 | 判定 | 落到 Moss 哪里 |
|---|---|---|---|
| 资产台账 | 扫目录：`场景_*`/`道具_*`/人物无前缀/`*声音.wav` 归并，服装变体走 `-`，同名按 图>视频>音 | 合 | 新 `webui/series/assets.py`（逻辑照搬） |
| 资产词库 asset_sheet | JSON 词库：base 样貌层 + outfits + `sig` 指纹 + `file_sig` 检测换图 + `sheet_prompt_text` 渲染注入文本 | 合 | 与现有 `core/prompts.js` 分工：那份是「风格整句」，这份是「角色/场景身份证」 |
| 检查缺图 | 只报不改、一次最多 6 条、双向包含算「已有」（宁漏报）、给 `suggest_filename` 与可直接当提示词的 description | 合 | 「补一张」的输入就是它给的 description |
| 缺失资产自动出图 | geeknow `/images/generations`，人物/场景强制 1536x1024 | 改 | **优先走本地千问/Moss**（复用 `app.start_gen`，0.9s/张）；弱机改成「可配 OpenAI 兼容端点」兜底，见 [剧本一键成片方案.md](剧本一键成片方案.md) §附 |
| AI 重绘（换装/改年龄/换场景） | `/images/edits`，参考图 ≤4 张、上传前压长边 1280 | 改 | 接重绘页那套遮罩与参考图通路 |
| 场景服装·锚点·元素三栏 | 右栏独立页签 | 改 | 收进剧集页一张折叠卡，不单独开页签 |
| 看图生成描述词 / 复制描述词 | 喂给 DeepSeek | 合 | 跟转分镜同一个 LLM 端点 |
| @提及 → `<Picture N>`/`<Video N>`/`<Audio N>` | By index / By filename 两种模式 | 合 | 本地 H3 的 ref2va 用同一套占位符，一次投入两边都赚 |
| 词库整句注入分镜提示词 | `sheet_prompt_text` 拼进 user 消息 | 合 | 生图页提示词的「身份层」，在灵感行之前 |

### 3.3 出片执行与调度

| 功能 | H3yun 怎么做 | 判定 | 落到 Moss 哪里 |
|---|---|---|---|
| 全局序号领任务 | `take_next` 永远取最小序号；失败 `bisect.insort` **插回原位不跳号** | 合 | 队列核心，本地批同样要 |
| 补镜插队 | `priority>0` 优先 | 合 | 分镜行「单镜重出」= 插队 |
| 失败重试与熔断 | 镜头重试默认 10、账号连败 10 熔断、`reload_workflow` 后再试 | 改 | 本地没有「账号」，改成**连续 N 张失败就停整批**并保留现场 |
| fatal 分类 | 掉登录/封禁=立即停用并把镜头交回队列；浏览器故障=累加到阈值才停 | 云 | 只在云端环境成立 |
| 多账号池 | 账号数=同时出片镜头数，跨剧本共用按剧本数均分，各自 `profiles/<账号>` 登录态 | 云 | MVP 先 1 个账号；池子留接口 |
| 登录态维护 | cookies+localStorage 存 `~/.rh_storage_<port>.json` 回灌；15 秒自检、启动 8 秒清理、聚焦 2 秒节流 | 云 | 同上 |
| 防重复提交 | 批量在跑再点→提示先停止；序号重复直接拦；出片/转分镜/检查缺图三者互斥 | 合 | Moss 现有 `_claim/_busy` 只挡单任务，补「批」这一类 |
| 进度反馈 | 结果表按序号建行「等待/跳过/运行中/完成/失败」并复用行；页签标题显示分到几个账号 | 合 | 任务页一张表，进度不再只有一条横幅 |
| 每 5 秒轮询输出节点、1800s 超时 | 读 `videopreview.params.cos_url` | 云 | 本地已有 `/ws` 事件，不需要轮询 |
| 节点 ID 与控件序号（389/325，0/2/3/4/5/6/7/8/10/12/13/14/21/22/23） | 硬编码 + 「检测工作流节点」按钮 | 云 | 逆向补丁，脆弱；只当云端环境的自检工具，不进主流程 |
| iframe JS 注入写 widget、`.execute-btn-wrap` 点提交 | `getNodeById(389).widgets[i].value`；提示词写 `.h3-prompt-editor` DOM 并派发 input | 云 | 同上 |
| 图片上传（唯一真 API） | `POST https://www.runninghub.cn/<authpath>` multipart + Cookie，重试 3 次 / 3 秒 | 云 | 云端环境里保留 |
| 帧率必须显式 24 | 不显式设就出 1fps 成片 | 合 | **这条是知识，不是代码**：本地和云端都吃，写进体检/自检的断言 |

### 3.4 配置、存档与健壮性

| 功能 | H3yun 怎么做 | 判定 | 落到 Moss 哪里 |
|---|---|---|---|
| 历史项目快照 | `history/<项目名>.json`（version/name/saved_at/project_dir/episode_count/storyboard_count/settings/project） | 合 | 剧集页「存档/打开存档」，与 Moss 的 `data/` 同目录规则 |
| 配置版本迁移 | `CONFIG_VERSION=3`、`SPEC_VERSION=30`，版本不符就用内置覆盖并日志说明；旧中文选项值归一化 | 合 | Moss 已有 `NAV_VER` 换代这套，同一思路接到分镜规范上 |
| 分镜规范/资产模版/附加要求三份可编辑文本 + 恢复默认 | 三栏并排 + 内嵌三模版页签 | 改 | 收进剧集页一张折叠卡，默认值内置 |
| 停止输入 1.2 秒自动落盘 | 正文与资产编辑都自动存 | 合 | `project.json` 写入用同一节流（配原子写） |
| 关窗先补存再存配置、停所有浏览器 | on_closing 收尾 | 合 | `App.on_closing` 里加「队列先落盘、云端浏览器先关」 |
| 无文件日志，只有 print + 本页文本框 | `_log` | 改 | Moss 已有 `logs/` 与日志页，行为照搬「每个动作都进日志页」 |
| 配置文件里明文存 API Key | `~/.h3_drama_config.json` | 改 | Moss 的 config 不进仓库；Key 走设置页 + 掩码显示，文档/日志里永不出现 |
| 端口 9222 起取最小空闲 | 每账号一个调试端口 | 云 | 云端环境内 |
| 多剧本 NoteBook 页签 | 一剧本一页签，右键重命名/打开目录/移除 | 改 | 「当前项目」单选 + 顶栏切换，不做无限页签 |
| 三个设置页 | 基础 / AI 与剧集 / 规范与高级 | 不 | 参数不该分三页；按「项目页 + 折叠明细」重组 |

## 四、云端 vs 本地（判定依据）

| 维度 | 本地（千问 / Moss / 可选 H3 权重） | 云端（RunningHub，H3yun 那条路） |
|---|---|---|
| 出图 | 512² 热态 **0.9s**、1024² 3.6s、768²/25 步 11.8s | 单张几十秒起，还要先开浏览器 |
| 出视频 | 要下 41.4 GB；5 秒预估 4~10 分钟；上限 768p | **零下载**；5~15 秒；360P~1080P 12 档；原生带声 |
| 可控 | LoRA / 步数 / CFG / 种子 / 遮罩重绘 | 只有档位（Lite/Standard、Lite/Plus、Ultra·6000D），**无 LoRA、无步数** |
| 并发 | 1 张 12G 卡，串行 | **账号数 = 并发数**，不占本机 |
| 显存 | 常驻 9.7 GB，视频档还要吃 32 GB 内存来回搬 | 0 |
| 稳定性 | 本地代码 + 权重，自己说了算 | 网页改版即失效、掉登录/封禁、任务号只在内存、积分扣费 |
| 离线 | 可以 | 不行 |
| 边际成本 | 电费 | 积分 |

**结论**：云端值得做成**一个可选环境**（跟 `envs/h3` 一样登记在 `envs/index.json`），而不是第二个引擎——它没有 venv、没有权重，「装」的含义是「浏览器 + DrissionPage + 一个登录好的账号」三件体检项。执行器抽象一层，local 与 cloud 两个后端，分镜表不关心自己交给谁。

## 五、接进来的形状

```
envs/runninghub/env.json          云端环境（可选）：packages=DrissionPage，checks=浏览器/包/账号登录态，无权重
webui/series/                     新模块，与 envkit 同级：script_io / storyboard / asset_sheet / asset_check / project
webui/executor/                   出片后端抽象：local.py（走 moss_mgr / pipeline_mgr）· cloud.py（走浏览器自动化）· queue.py（序号调度）
webui/store.py                    加 shots / jobs 两张表（project.json 仍是真相，表只是缓存与队列）
webui/app.py                      新桥方法：series_open / shots_list / shot_save / batch_start / batch_stop / jobs_state / cloud_login / cloud_check_nodes
webui/ui/js/pages/series.js       新「剧集」页（两字，归出图组）
webui/ui/js/pages/jobs.js         新「任务」页：一张表看排队/进行中/失败/跳过
webui/ui/js/core/nav.js           NAV_VER 换代 + 两页
```

- **界面按引擎归属切块**：剧集页顶部一条「执行：本机 Moss / 本机千问 / 云端」，跟生图页那条引擎栏同一个写法。
- **导航平铺、名字统一两字**：生图 / 编辑 / 重绘 / 剧集 / 任务 / 词库…（现有 8 页会涨到 9~10 页，出图组与系统组各自还能放得下）。
- **不新增引擎概念**：云端是环境，不是引擎；`set_engine` 的互斥规则不动，云端出片**不占卡**，所以允许和本地出图同时跑——这是云端唯一的结构性优势，界面要说清（云端任务不点亮显存灯）。
- **提示词分层**：资产身份证（`sheet_prompt_text`）→ 用户写的分镜正文 → 通用反向词 `NEG_BASE`。三层的顺序写死，灵感行只碰中间那层。

## 六、优先级与分档（我拍板）

> **本轮已改序**：用户把「云端必须有」和「一切最简」提上来之后，落地顺序以 [剧本一键成片方案.md](剧本一键成片方案.md) §八 为准（P0 先真机冒烟尾帧续接 → P1 成片页最小闭环 → P2 任务化 → P3 身份锚 → P4 本地通道）。下表保留作盘点结论，P0/P1 的「剧集工程 + 批量队列」在新序里被吸收进「成片页 + `film/queue.py`」，不是作废。

| 档 | 做什么 | 为什么要先 | 代价 |
|---|---|---|---|
| **P0** | **剧集工程**：打开剧本目录 → 分镜表 → 全局序号 → 成组输出目录 → project.json 读写（含直接打开 H3yun 的历史存档） | 后面一切的地基；纯本地、零风险、不占卡；能把已攒下的分镜资产一次性接进 Moss | 新模块 + 2 张表 + 1 页界面 |
| **P1** | **批量队列**：整片/勾选分镜逐张出图，失败插回原位不跳号、连续 N 次失败熔断、跳过已有、后台跑不守进度条、任务页看状态 | 这是 H3yun 调度层里最可移植的一块，也直接解决「Moss 一次只能点一张」这个最大短板 | `queue.py` + 任务页；改 `_claim` 的粒度 |
| **P2** | **DeepSeek 转分镜**：移植规范拼装（含前缀缓存顺序）与容错解析，LLM 端点可配（DeepSeek / 本机 llama.cpp） | 没有它，P0 那张表要手填；有了它，一句剧本变一片分镜 | 一个 LLM Key；spec 文本 ~300 行 |
| **P3** | **资产台账与一致性**：扫描归并、资产词库、缺图核对、「补一张」走本地引擎、`<Picture N>` 提及 | 角色/场景跨镜一致是短剧真正的痛点，也是本地引擎最能打的点（可控） | `asset_sheet.py` 逻辑移植 + 生图接线 |
| **P4** | **云端环境**（可选）：三件体检、单账号登录、浏览器自动化提交与取片、`local|cloud` 双后端 | 唯一能在这台 12G 上「不下载 41 GB 就出 15 秒带声视频」的路；但它最脆，所以排在能落地的价值之后 | `browser.py` 128k 行里只需要那一小条链路 |
| **P5** | **本地 H3 视频**：41.4 GB 权重 + 视频页 | 见 [H3视频方案设计.md](H3视频方案设计.md)；P4 或 P5 任选其一即可让「剧集 → 成片」闭环 | 41.4 GB + 每次 4~10 分钟 |

P0/P1 之间不并行：队列没有分镜表就是「批量版生图页」，价值只有一半。P2 之后，P3 与 P4 谁先看下面的拍板项。

## 七、明确不做

- 不搬 `ui.py` 那套 tkinter 界面、三个设置页、无限剧本页签——只搬行为，界面按 Moss 现有的短文案重做。
- 不内置某家云端出图服务（geeknow 那类）：弱机需要兜底时走「可配 OpenAI 兼容端点」，默认空；有卡一律本地优先。反向建议照旧：H3yun 的出图改调 Moss 的 `/v1/images/generations`（已认 OpenAI 形状，免令牌可开）。
- 不在主流程里依赖 RunningHub 的节点序号硬编码；它只作为云端环境的「节点自检」，改页面时先自检再报错，不静默出废片。
- 不做多账号池的 MVP（先 1 个账号跑通），池子留接口不留实现。
- 不自动下载任何东西：`启动.bat` 仍只备界面壳；云端环境的 DrissionPage 走环境页分区点名补齐（与 `envs/h3` 同一套规则，可选环境默认不进待补）。
- API Key、Motrix 密钥、RunningHub 登录态一律运行时读、不进仓库/文档/日志。
- 不做 2K、不做超过 15 秒的单段、不「同时开千问 + 本地 H3」。

## 八、需要你拍板

1. **视频走云端还是本地？** 云端零下载、要积分、会因网页改版断链；本地一次性 41.4 GB、每次 4~10 分钟、完全可控。我的建议：**先 P0+P1 把地基打好，视频按云端（P4）试**——因为这台机器的 32 GB 内存跑本地 H3 是踩地板，而 P0~P3 的价值跟选哪条视频路线无关。
2. **P2 用哪家 LLM？** 只要一个 OpenAI 兼容端点就能同时吃「转分镜 + 看描述词」。你有本机 llama.cpp（15 轮那条链已验证 `enable_thinking:false` 通路），DeepSeek 官方更省事但要 Key。默认按可配端点写，两家都能填。
3. **资产台账和现在的「参考图」合并吗？** 现在编辑/重绘页有参考图通路，H3yun 的资产库是「有名字、有词库、有服装套、会查缺」的台账。我建议**合并成一套**（台账为准，参考图从台账挑），否则同一个角色在两个地方各存一份、必然漂。
4. **批量要不要「后台跑、不守进度条」？** 队列一开，5 秒一张和 10 分钟一段视频混在一起时，进度横幅会长期被占。建议任务页给「本批完成后停/继续循环」与系统托盘式摘要，横幅只报当前这一件。
5. **P0 的兼容边界**：要不要真去读 H3yun 的 `history/<项目名>.json` 和它的 `project.json`（读得到 = 你能把已经攒的剧直接搬过来）？我按「读得懂它的、写它也能读回来」设计，这是 P0 里唯一需要额外测试用例的部分。

## 九、P0 验收标准（做完要能报这几条）

1. 指一个 H3yun 剧本目录 → 列出集与镜头，全局序号与它自己算出来的一致（拿一份真存档对拍）。
2. 在 Moss 里改 3 条分镜提示词、删 1 条、给 2 条设「跳过」→ 关掉再开，状态原样回来，`project.json` 与 H3yun 打开同一项目不冲突。
3. 对同一项目点「批量出图」→ 按序号成组目录落 N 张，中途停止后立刻重跑**跳过已存在的非空文件、失败位不跳号**；`nvidia-smi` 峰值不超过单卡串行水位。
4. 全部改动过 `node --check` / `py_compile` / `moss_selftest` / shoot 探针（新增 `series`、`jobs` 两个探针），真机数字写进交付说明。

## 附：H3yun 关键事实（核过的）

> 2026-11-02 已在登录态浏览器 + 工作流导出 JSON 上重新核验；**工作流 ID / iframe / 提示词写入这三条旧结论已变化**，以 §十 为准。

- 出片节点 `FeiHouEasyH3RH` = 389，输出节点 = 325；保存的工作流 ID `2103759530927673346` 会打开一个**运行时副本**（新数字 id，每次不同），`iframe{WORKFLOW_ID}` 已不能用来定位。
- 控件：模式 0 / 文案 2 / 分辨率 3 / 宽高比 4 / 宽 5 / 高 6 / 音频时长 7 / 秒数 8 / advanced 9 / 帧率 10 / 参考尺寸 12 / 提及模式 13 / 提示词优化 14 / 仅文本 21 / 低显存 22 / 媒体 JSON 23；界面默认 768P、9:16、15 秒、640、By index、三个开关全关、监控超时 30 分钟。**序号会随扩展加控件而整体后移，写入一律按 `widget.name` 查，不按序号。**
- **帧率不显式设 24 就出 1 秒慢放的成片**；提示词三个开关别开（扩写会 SSL 报错）。
- 唯一真 API：图片上传 `POST https://www.runninghub.cn/<authpath>`（multipart `image` + `Cookie`，重试 3 次 / 3 秒）；其余全是 DOM 自动化。
- 提示词不是普通控件：真源是 `node.__h3Editor`（contenteditable，**不挂在 document 上**），`document.querySelector('.h3-prompt-editor')` 在节点未渲染时取不到；改 `widget.value` 会被 `graphToPrompt()` 用编辑器内容覆盖回来。
- 任务号只在内存（`_my_task_id`/`_task_submitted`），重启不继承；续跑靠扫 `前缀-序号` 非空文件，0 字节算中断。
- 仅 5 处需要 LLM API：`generate_storyboards` / `generate_asset_sheet` / `chat_json` / `optimize_document` / `asset_check.check_docs`——**创作管线其余部分完全离线**。
- DeepSeek 参数：`deepseek-flash`、temp 0.3（建库/改写 0.2）、`max_tokens=65536`、stream=False、timeout 600、429/503 指数退避 ≤60s 最多 6 次、`finish_reason=length` 续写最多 4 轮、请求体 >24MB 自动去图。
- 本机修好的启动链路：`启动H3短剧版.bat` 重写后（UTF-8 无 BOM + CRLF + `chcp 65001`）已实测拉起 `H3 短剧自动生成` 窗口；原文件 427 个 `?` 的中文不可恢复，此前那版脚本里的 `>/dev/null` 是 cmd 打不开的路径，会直接报「系统找不到指定的路径」。

## 十、云端链路实机核验（2026-11-02）

> 依据：Qoder 内置浏览器里的登录态实机 + 用户提供的 `H3修改为艾特工作流_fixed.json`（23 节点 / 33 连线，拓扑与线上一致）。
> 只做读取与一次「改完立刻还原」的提交契约验证，**没有点运行、没有扣积分、没有改仓库代码**。

### 10.1 页面与图对象

- 打开 `https://www.runninghub.cn/workflow/2103759530927673346` → 平台生成**运行时副本**，URL 与 iframe id 都换成新数字（两次实测 `…0781482242049`、`…1746516090881`），标题与内容仍是同一份 `H3修改为艾特工作流_fixed`。**保存**才写回原工作流。
  → `IFRAME_ID = f"iframe{WORKFLOW_ID}"` 失效。取法改为 `document.querySelector('iframe[src*="comfyUI.html"]')`，或从当前 location 读运行时 id。
- `app.graph` 与 `app.rootGraphRef.value` 是**同一个 LGraph 实例**；`app.graph.getNodeById(389)` 仍然可用（H3yun 的旧访问器没坏）。
- `app.graphToPrompt()` 直接产出**即将提交的 API 格式**（`{workflow, output}`），不必自己把 UI JSON 转成 API JSON——这是最稳的序列化入口。

### 10.2 节点 389 的提交契约

**按名字取控件，不按序号。** 线上 24 个控件（`embedded_media` 是纯 UI 控件，`embedded_media_json` 是隐藏传输控件），导出 JSON 的 `widgets_values` 只有 22 项且不含这两个——两者不是一回事。

| 控件 name | API input | 值 |
|---|---|---|
| mode | mode | `Reference-to-video` → `reference`（I2V → `image`） |
| prompt | prompt | 真源是编辑器，见下 |
| resolution / aspect_ratio / width / height | 同名 | `768P` / `9:16` / 432 / 768 |
| audio_duration_auto | audio_duration_auto | `Off` → `off` |
| seconds / fps | 同名 | 15 / 24 |
| keyframe_role | keyframe_role | `First frame priority` → `first` |
| ref_image_size | ref_image_size | `640` |
| reference_mention_mode | reference_mention_mode | `By index` → `index` |
| prompt_optimizer_* | 同名 | 默认关；扩写开关打开有 SSL 报错风险，保持关 |
| reference_text_only / low_vram_streamed_attention / force_offload | 同名 | false / false / true |

**提示词写入（本次最关键的新发现）**

- `graphToPrompt()` 在序列化前会调用 `syncPromptFromEditor(node)`，把 `node.__h3Editor` 的内容回写到 `widgets[prompt].value` 与 `properties.minimax_h3_prompt_reference_doc`。所以**直接改 widget.value 无效**；只改 properties 也会被编辑器覆盖。
- `node.__h3Editor` 是一个 `contenteditable` 的 `div.h3-prompt-editor`，**节点不在视口内时 `isConnected === false`**（挂在 `div.h3-prompt-editor-wrap` 下但不在 document 里），因此 H3yun 的 `document.querySelector('.h3-prompt-editor')` 会找不到。必须从 `getNodeById(389).__h3Editor` 拿。
- 写法：`editor.innerHTML = 文本 + <span class="h3-mention-chip" data-token data-tag data-label data-full-label data-media-type data-reference-mode data-ordinal data-source-id data-source-slot>…</span>`，随后调用一次 `graphToPrompt()` 即完成同步（不依赖 input 事件）。
- 序列化时 `<Picture N>` 被换成 `__MINIMAX_H3_REF_<k>__`：k 是**跨类型合并后的 1-based 序号**，排序 image → video → audio。例：7 张图 + 3 段音频，`<Audio 1>` = `__MINIMAX_H3_REF_8__`。
  - 实测：把编辑器内容改成 `TEST_A <Picture 2> TEST_B` → 提交体为 `TEST_A __MINIMAX_H3_REF_2__ TEST_B`，改完已还原。

**媒体**

- 真源：`node.properties.feihou_h3_embedded_media = [{media_type, ordinal, filename, subfolder, storage, audio_trim}]`；`graphToPrompt()` 每次都会 `ensureEmbeddedMedia()` 重新归一化，并生成 `media_N / media_type_N / media_trim_N / embedded_media_json`。
- 上限：image 9 / video 3 / audio 3；ordinal 按类型从 1 递增；audio/video 的 `audio_trim` 用 `00:00-00:00` 格式（旧导出里的 `00:00:000-00:00:000` 会被归一化）。
- 上传：`POST apiURL('upload/image')`，FormData `image=<file>` + `type=input`，返回 `{name, subfolder, type}`；与 H3yun 的 `POST https://www.runninghub.cn/<authpath>` 是同一个接口，认证参数由 `apiURL()` 自动拼。
  → Moss 直接走页面里的 `api.fetchApi('/upload/image', …)`，不用自己拼 `Rh-Comfy-Auth`。

**普通控件**：`NumberWidget/ComboWidget` 直接 `widget.value = x` 有效（实测 seconds=12 → 提交体 12，已还原）；只有 prompt 例外。

### 10.3 提交与取片

- 运行入口在**顶层页**（不在 iframe）：`.execute-btn-wrap` 下三颗按钮，`.plus-tags` 依次为 `Lite/Standard` / `Lite/Plus` / `Ultra·6000D`；H3yun 默认点 `Lite/Plus`。
- 状态机：`提交中` → `继续运行`（运行中）→ `运行`（空闲）；`getComputedStyle(btn).cursor !== 'pointer'` 视为锁定。
- 完成判定：轮询 `getNodeById(325)` 的 `widgets` 里 `name==='videopreview'`，`value.params.filename` 变化即完成；`params` 还带 `cos_url / objectKey / fullpath / bucket / storageProvider:'tos'`。
- 下载：`params.cos_url` 是**公开 TOS 地址**，实测 HEAD 200、无需 Cookie，15 秒 / 768P 约 4.2–4.5 MB。`type` 为 `temp`，尽快下载。
- 账号差异：COS 路径段、`Rh-Identify`、上传后的哈希文件名都随账号变化；同一份工作流 JSON 换账号**必须重新上传媒体**。

### 10.4 对 H3yun 现有实现的直接影响

| 现有写法 | 实机结果 |
|---|---|
| `IFRAME_ID = f"iframe{WORKFLOW_ID}"` | **失效**：iframe 用运行时 id |
| `document.querySelector('.h3-prompt-editor')` | **失效**：编辑器不在 document 里 |
| `getNodeById(389).widgets[i].value`（i 按数组序号） | 仍可用，但建议改按 `name`（`advanced` 已插到 9 号位） |
| `.execute-btn-wrap` 状态机 / 325 轮询 / COS 下载 | 实测仍成立 |
| 提示词 chip 用 `build_mention_html` 生成后写 DOM | 思路对；改写成 `node.__h3Editor` + chip 的 data-* 即可 |

### 10.5 Moss 的落地口径（不新增引擎）

- 云端仍按「可选环境」：DrissionPage + 浏览器 + 已登录账号三项体检；不建 venv、不下权重。
- `cloud.py` 只做四步：确保页面与图加载 → 上传媒体 → 写 389（编辑器 + properties.media + 普通控件）→ 点运行并轮询 325。
- 点运行前先 `graphToPrompt()` **自检**：prompt 含 `__MINIMAX_H3_REF_`、`media_N` 数量等于资产数、`fps===24`、`5 ≤ seconds ≤ 15`、`mode==='reference'`；任一项不符就报错不提交——宁可停下，也不静默出废片。
- 分镜 → 云端：`source` 正文进编辑器；资产按类型编 `<Picture N>` / `<Audio N>`；**不复用导入 JSON 里的旧哈希文件名**。
- 导出 JSON 可当「模板」导入，但换账号后要重传媒体并改写 `feihou_h3_embedded_media`；doc 里过期的 `previewUrl` 只影响缩略图，不影响出片。
- 已知数据质量坑：用户提供的导出里，同一角色「图+声」那一行出现了重复的 mention 片段（`王桂香<Picture 1><Audio 1>`），提交文案会被重复写一遍。Moss 拼 doc 时应保证每个 mention 只出现一次。

## 十一、浏览器只管登录、生成全走协议：可行性与边界（2026-11-02 分析，未写代码）

> 结论先说：**能做到，而且这是比「全浏览器自动化」更稳的形状**；但「只存 Cookie」不够——协议侧真正要的凭证是每账号一条 **API Key**，Cookie 只负责登录。另一个硬限制在节点上：H3 的提示词不是普通输入框（见 §10.2），走协议时那套「编辑器内容 → `__MINIMAX_H3_REF_k__` + 隐藏媒体字段」的序列化必须由我们自己完成。

### 11.1 官方 OpenAPI 的形状

| 动作 | 端点 | 关键点 |
|---|---|---|
| 传素材 | `POST /task/openapi/upload` | multipart：`apiKey` + `fileType`(image/video/audio)；回文件名，供 `nodeInfoList` 引用 |
| 建任务 | `POST /task/openapi/create` | Header `Authorization: Bearer <API Key>`；body `{workflowId, nodeInfoList:[{nodeId, fieldName, fieldValue}], addMetadata, webhookUrl}` |
| 取结果 | `POST /task/openapi/outputs` | 旧 `/status` 已弃用；新版查询在 `/openapi/v2/query`，AI 应用走 `/openapi/v2/run/ai-app/<id>` |
| 能力清单 | 个人中心生成 API Key | 需要**基础版及以上会员**；工作流必须先让它在网页里跑过一次，平台才有 API 形态 |

`nodeInfoList` 的语义是「按节点 id + 控件名改值，然后跑已保存的那份工作流」——它**不是**一个能自定义拓扑的通用接口。对我们来说这不是缺点：H3 的图根本不需要改，只换提示词、秒数、分辨率、媒体。

### 11.2 唯一真风险：H3 的提示词不是普通 widget

§10.2 那 24 个控件分两类：

- **标准控件**（`mode / resolution / aspect_ratio / seconds / fps / keyframe_role / ref_image_size / reference_mention_mode / …`）：`nodeInfoList` 直接按 `fieldName` 改，没问题。
- **特殊控件**（`prompt`、`embedded_media`）：网页上它们是前端组件，提交前由 `graphToPrompt()` 现算。走协议就没有前端，必须自己补齐三组东西：
  1. `prompt` 里的 `<Picture N>` / `<Audio N>` 序列化成 `__MINIMAX_H3_REF_<k>__`（k 为跨类型合并后的 1-based 序号，排序 image → video → audio）；
  2. `properties.minimax_h3_prompt_reference_doc`（编辑器回写的同一份文案）；
  3. `media_N / media_type_N / media_trim_N / embedded_media_json` 这组隐藏字段，由 `feihou_h3_embedded_media` 归一化而来。

**做法**：不要手写模板。在网页里对 `app.graphToPrompt()` 的结果导一份 **API 格式 JSON** 当模板，之后只替换上面这几个字段。隐藏字段的形状一旦钉下来，平台改版时才需要重新导一次模板——这是可以接受的维护成本，比解析 DOM 强得多。

验收时必须逐字比对：同一段文案、同一组图，用「网页点运行」和「OpenAPI 建任务」各提交一次，抓提交体比对 `prompt` 与 `embedded_media_json`，差一个字符都不算通过。

### 11.3 浏览器留下什么，协议需要什么

登录一次后本地实际有三样东西，作用完全不同：

| 东西 | 来源 | 用途 | 时效 |
|---|---|---|---|
| 浏览器 profile（Cookie / `Rh-Identify` / `Rh-Comfy-Auth`） | DrissionPage 的 user-data-dir，用户自己登一次 | 续登、开网页看积分与历史、兜底走页面内接口 | 会过期，需人工续登 |
| **API Key** | 个人中心手动生成，每账号一条 | 协议侧跑任务的唯一正牌凭证 | 长期，可吊销 |
| 积分余额 / 并发档位 | 账号信息接口或网页 | 调度决策 | 实时 |

所以账号档案应是：`{名称, profile 目录, apiKey, 并发上限, 最近一次余额}`。

- apiKey 若能用登录态自动拉取就自动（该端点未核实）；拉不到就让用户黏一次——**一次操作，不是每次**。
- apiKey 一律运行时从 `%APPDATA%` 下的私有账号库（或环境变量）读，**不进仓库/文档/日志**；日志里只出现账号名和打码后的 `sk_***ab12`。
- 换账号必须**重传媒体**（§10.3：上传后的哈希文件名带账号）；同一批资产给 N 个账号并行，就要传 N 份。这是多账号的隐性成本，别按「一次上传到处用」来估。

### 11.4 多账号并行

- 官方口径：**消费级账号默认单任务队列**，高并发要多开属企业级-共享。所以并行的来源是「**多账号 × 每号 1 并发**」，不是单号多并发。
- 调度：`accounts[]` 每个账号一条通道、一份互斥闸门（1）；任务按「账号空闲 + 余额够 + 冷却结束」领取；限流（429 / 队列满）按账号退避 30s→60s→120s，失败不连坐其他账号。
- 失败归类要按账号维度记：积分不足、Key 失效、被风控、模板字段变更——前两种停该账号，后两种停全局。
- 合规：多账号并联要先看平台的账号条款，被判定为刷量会封号；调度器应保留「单号串行」的降级开关。

### 11.5 浏览器自动化最后剩多少

如果按上面走，DrissionPage 只剩三件事：**登录/续登**、**建 API Key（可代点）**、**兜底**（网页独有能力、看账单、偶发验证码）。生成链路彻底不进浏览器，`.execute-btn-wrap` 的状态机、iframe 运行时 id 这些 §10.4 列的坑全部不再相关；只有模板里的 `fieldName` 需要跟版本。

### 11.6 建议的落地顺序（拍板）

1. `cloud_api.py`：OpenAPI 建任务 + 轮询 + 下载；`accounts.py`：账号档案与并发闸门；`cloud_web.py` 保留现在的浏览器实现作兜底，`cfg.cloud.mode = api | web`，默认 `api`。
2. 第一版只放开四个字段跑通一条：`seconds / resolution+aspect_ratio / prompt / media`，其余用模板默认值。
3. 验收门：① 模板 + 三张图出片成功；② OpenAPI 提交体与网页提交体 `prompt`/`embedded_media_json` 逐字一致；③ 换账号重传媒体后仍出片；④ 两账号并行互不排队、限流能退避。
4. 文档留一条「平台改版 → 重新导出 API 模板」的操作指引；这条是协议方案唯一的维护动作。

---

## 十二、落地现状：账号平台（2026-11-02，只做登录与档案，未接 OpenAPI）

§十一 的「API Key + 协议生成」仍是下一阶段；本轮先把**登录侧的平台**搭起来，对应上文 11.1/11.2 里「浏览器只管登录」的部分。

- **一只浏览器，多份数据**：`webui/cloudkit/browser.py` 固定调试端口（默认 9333）与 `data/cloud/browser` 档案；换号 = `apply_state` 清空当前 cookies/localStorage 后灌入目标账号快照，不重启、不换端口。`user-data-dir` 是启动参数，多开浏览器这条路本来就走不通。
- **账号档案**：`webui/cloudkit/store.py` 每号一份 `latest.json` + 12 份带时间戳的备份 + 可选 `key.json`；`accounts.json` 只有名字/状态摘要，**cookie 值与 API Key 不进索引、不进日志、不回界面**。恢复备份是复制成新的一份，历史不删。
- **保活**：每 30 分钟轮着访问平台，只在浏览器已启动时跑；登录页开着时让路；cookie 指纹没变不落盘。
- **并发**：固定 1（多账号轮流），不做单号并发。
- **鉴权头**：能从快照里派生 `Rh-*`（`auth_headers`），界面只显示名字；真正提交任务时再用 11.6 的 OpenAPI 方案。
- **界面**：导航「系统 → 云端」，12 页体系（`NAV_VER=8`）。DrissionPage 为可选依赖，缺失只影响本页。
- **下一步**：按 11.6 接 `cloud_api.py`（upload → create → outputs），把「账号快照 + API Key」作为协议侧的凭证来源；然后用「网页提交体 vs OpenAPI 提交体」逐字比对做验收门。

---

## 十三、落地现状：云端出片执行器（2026-11-02 真机）

§十二 那个「下一步（OpenAPI）」还没做，也做不了——本轮实测确认**提交这件事没有公开可复现的协议口**，所以云端出片落地成 `webui/cloudkit/gen.py`：上传走协议，提交点页面那颗按钮。

### 13.1 真机跑通了什么

- 界面：视频页顶部一条分段控件（本地 / 云端），两档共用描述、时长、清晰度×画幅、参考图；云端专属两格是账号与工作流，本地专属的是步数（只读）与种子。`cfg.video.exec` 一份配置两个执行地，成片进同一个画廊。
- 一轮真机冒烟（`scripts/h3_cloud_smoke.py`，走 `App.video_gen` 同一条路）：**5 秒 · 界面写 848×480 → 落盘文件里真是 848×480**，提交到下载 **353.1 秒**，画廊记下参数与秒数。这条同时也证明了「清空工作流自带的 6 张参考图」是有效的——不清空就是花钱重渲平台自己的图。
- 第二段同参数：**等满 1800 秒上限也没出新片**（整轮 1812.4 秒，`outputs/` 里没有新 mp4）；第三段同参数、换了新代码，同样等满 1800 秒。也就是说云端耗时波动以“倍”计（353 秒 vs 至少 1800 秒），任何“预计几分钟”的口径都不准；界面上必须有平台真实状态，而不是一句「已等 N 秒」。

### 13.2 四条实测纠正（覆盖 10.2 / 10.3 的推断）

| 之前的写法或推断 | 线上事实 |
|---|---|
| `graphToPrompt().output[nid].inputs` 直接同步取 | **它返回 Promise**。同步取到 `undefined`，于是每一项都「没值」、自检全绿——防线看着在，其实一条也没生效。现在 `then` 里读，读不到序列化结果就**拒绝提交**。 |
| `mode` 序列化后可能是选项原文 | 只有两个选项 `I2V or First/Last Frame` / `Reference-to-video`，序列化后是 **`image` / `reference`**。 |
| 档位（`resolution`）与画幅（`aspect_ratio`）会决定宽高 | **不会**。改这两颗控件后序列化里的宽高纹丝不动（432×768 八种组合全不变），出片尺寸完全由 `width/height` 决定。所以执行器永远原样写宽高，档位只当一个名字（`pick_size` 因此简化成四件套）。 |
| 提交有协议口 | 外发 `POST /prompt` → nginx 403；页面内 `POST` → 回 SPA 首页。只读的 `GET /history`、`POST /upload/image` 是通的。**唯一真 API 仍是上传。** |

顺带记一条控件写的坑（10.2 的「普通控件直接 `widget.value=` 有效」在本版仍然成立，但 combo 要走 `setOption`，否则选项校验不过）。

### 13.3 提交前自检现在拦什么

`_JS_WRITE` 一次写完（普通控件 + `__h3Editor` + `feihou_h3_embedded_media`），随后拿**即将提交的那份序列化**逐项比：`mode`、`fps===24`、`seconds`、`resolution`、媒体条数、`media_N` 槽位数、提示词开头若干字。任一项不符就 `CloudError`，不提交；序列化读不到也算失败（缺证据即失败）。槽位那条是本轮新增：工作流里原本挂着 6 张图，只清 `embedded_media_json` 不清槽位，平台照样按旧媒体出片。

### 13.4 H3 环境关掉之后

`nav.js` 的 `PAGE_ENV` 不再管视频页——**本地那一路归 h3 环境，云端那一路只要一个登录号**，关掉 h3 就把整页收走等于把云端这条路也堵死。改成：页还在，选中「本地」时这一页直说「H3 环境已关闭：本地这一路整条停用」并给一颗开回来的按钮，切到「云端」提醒立刻换成云端那一条。副标题同步（不再报「点开始自动拉起」而是「H3 已关闭」）。
这里有个容易看漏的坑：关掉的环境根本不体检（`env_todo_by.h3` 归零），所以**只看待补数会以为一切正常**，点开始才报错——开关那一层必须单独判。

### 13.5 还欠的两条 P0

`剧本一键成片方案.md` 第四条那三件事，现在只过了「单段能不能出片」。剩下两条：

1. **首帧模式给单张图能不能成立**（`mode=image` + 一条媒体，不给尾帧）——尾帧续接整条链的前提。执行器已经把这条路写好了（`MODE_I2V` + `media_item`），缺一次真机。
2. **多段编码参数一致不一致**——不一致 PyAV 直接花屏。要三条同参数段拼一次才知道。

探针 `scripts/h3_cloud_probe.py` 现在有四条只读子命令支撑这件事：`--graph`（看序列化）、`--size`（扫档位问宽高与 mode 映射）、`--queue`（看平台到底在排队还是在跑，不提交不扣分）、`--state`（直接跑 `cloudkit` 那份真代码读一次状态句，验的就是 Promise 回不回得来）。

### 13.6 「这段到底到哪一步了」：平台侧读数的真机口径（2026-11-02 凌晨）

等片那 30 分钟里界面上只有一句「已等 N 秒」，等于没报。本轮去问平台自己，量到的形状：

- `w.app.queue` **在新打开的工作流页上是 null**（探针就是这么撞出来的），新版还把队列另挂了一份 `w.app.queueItems` 数组（实测空闲时长度 0）；但在真跑着的那次会话里，`app.queue` 又一直在、还读到了空队列。结论不是「哪个能用」，而是**两份都得读、谁真读到用谁，并且以内存那份为准**——它是页面按 WebSocket 推送维护的，和人在平台上看到的口径一致；`GET /queue` 只当网关挡了推送时的备份。
- `GET /queue` 通、200，正文还是老叫法：`{"queue_running": [], "queue_pending": []}`；`GET /history` 同样通。两条口径并存：计数以内存那份为准，HTTP 那份补它读不到的场合，两边都说空才允许说「查不到」。
- **但这台实例的 `GET /history` 恒是 0 条**（`--state` 连测两次都是 `h:{n:0}`，而输出节点预览里还挂着上一段成片的名字）：托管 ComfyUI 不把历史透出到工作流页面。所以「平台已经收下这段」「跑完但输出节点没刷新」这两句在这台实例上出不来，常态就是那句中性的「查不到」。这不是代码问题，是这台机器的口就这么窄——要真状态只能等 §十一 的 OpenAPI。
- `_JS_PROGRESS` 现在返回 Promise（两次 fetch 得等），这版 DrissionPage 4.1.1.4 的 `run_js` 里 `awaitPromise=True` 是硬编码的，实测回包类型就是 `str`；换成不等 Promise 的库就得先确认这一条。
- 顶层那颗执行按钮空闲时写「运行Lite/Standard|运行|运行」，跑起来会换字——最后一道兜底，也最好读。
- **关键的一条**：`_JS_PROGRESS` 里那个 `fid` 是 iframe 的 DOM id，不是任务 id。第一版把它当 prompt_id 拼进 `/history/{fid}`，永远查不到东西——所以历史改成读整份、和提交前那条数比「有没有多出来」。
- 读到的状态归成五句实话：正在跑 / 排队中（前面 N 个）/ 平台已收下这段 / 平台把这段判了失败 / 平台上查不到这段任务。读不到就留空，绝不编。超时那句错误也把看见的状态带上。
- 「查不到」不等于「没提交成功」：实测出片成功的那一段，同一时刻读到的队列同样是空的——平台真正的排队不在这个页面里，只在它自己的池子里。所以这句只能说到「看不到它到哪一步」，不能顺势劝人去查工作流权限。

`cloud_test.py` 的「云端状态」「云端超时收尾」两组把这五种说法和「不许把查不到说成没提交」钉住了（现在是 15 组，另加「云端工作流」「本地工作流灌入」两组）。


### 13.7 工作流换成「本地那一份」和「出片尺寸谁说了算」（2026-11-02 只读实测）

两条都是用户提的：云端能不能用本地工作流文件；云端长宽是不是无所谓、能不能到 2K。答案都是能，且都是量出来的：

- **本地工作流文件能灌进去**。平台页面里的托管 ComfyUI 前端有 `app.loadGraphData(graph, true, false, name)`（`app.serialize()` 不存在，第一版探针就栽在这上面）。往返实测：`app.graph.serialize()` 导出 **65,605 字节 / 23 个节点 / 33 条连线**，灌回去还是 23 个节点，主节点（`FeiHouEasyH3RH`）与输出节点（`VHS_VideoCombine`）按类型都认得出——**主节点 id 未必还是 389、输出节点也未必还是 325**，所以认节点一律按 `class_type`。
- **导出的文件里没有工作流编号**（只有一个随机 uuid）：托管实例是按页给的，本地那份只能借一个「宿主页」进去，进去之后再把画布换成你这份——「换图不换实例」。所以界面在填了 `.json` 时会多要一格宿主页，没填就直说，不等到点开始才报。
- 我们自己那份 `webui/moss/workflow_h3.json` 是 **API 格式**（`{"1": {class_type…}}`），不是画布，灌不进去；`load_local_wf` 会拦下并说清「要带 nodes 的那种」。
- **尺寸：档位是标签，宽高才是命令**。4 档清晰度 × 8 种画幅全扫一遍，序列化里的 `width/height` 始终是 432×768；直接写隐藏的 `width/height` 则原样生效（1920×1080 / 2560×1440 / 3072×1728 / 3840×2160 都留得住），且写完宽高再改画幅也不会被盖回去。平台自己的 `resolution` 档到 1080P + Custom、`aspect_ratio` 八种，但都不影响出片尺寸。
- 因此云端档位表放到 **480P…1440P（2K）**：2K 就是短边 1440（2560×1440），是官方上限；本地仍停在 768（权重原生档），两条路各用各的表，换通道时界面自动把超出的尺寸收进当前那档的档位表。
- 代价与边界：高分辨率段没做过真机成片（每段扣积分），界面不给「预计几分钟」的假数；1080 不是 16 的倍数，界面上如实写 1920×1088。
