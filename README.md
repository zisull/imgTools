# Qwen 生图控制台

一个本地桌面生图工作台：同一扇窗口里管理两套本地模型——**千问 Qwen-Image-2.1**（diffusers，进程内）与 **MOSS-Image**（内嵌 ComfyUI 子进程）。pywebview + WebView2 无边框窗口，没有浏览器标签页，也没有命令行黑框；整个程序就是一个文件夹，删掉即净。

## 特性

- **双引擎、单激活**：千问与 Moss 任意时刻只常驻一个，切换时先卸载另一个，不抢显存
- **Moss 三档**：极速 8 步（DMD LoRA）/ 均衡 25 步 / 精修 50 步，另有「让出显存」一键停掉子进程
- **千问两档**：Turbo 8 步 / 精细 40 步，fp8 量化 + CPU offload，12 GB 级显存可跑
- **环境开关**：千问 / Moss / H3 各自一颗开关；关掉就不体检、不进待补、不提醒，功能页一并收起，显存也交还——只开一个就是只用一个。唯一的例外是**视频页**：它两条通道，本地那路归 H3 环境，云端那路只要一个登录号，所以关掉 H3 页面还在、只把本地那一档标成停用
- **首启欢迎页**：第一次打开先问「这台机器管哪几路」，三张牌各写体量与待补数，点牌即开关
- **出图四件事**：文生图、参考图编辑、涂抹重绘、透明底 PNG；另有一页 **H3 视频**（一句描述出带声音的片子），页顶一条分段控件选执行地——**本地**（内嵌 ComfyUI，要 41 GB 权重，清晰度到 768P 原生档）或 **云端**（RunningHub 出片，不占显存、按平台计费，只填一份工作流——平台地址或本地导出的 `.json` 都行，其余自动借平台页面；清晰度到 2K）
- **剧本一键成片**：一页「成片」——贴一段剧情、选目标时长（30 秒~5 分），文本 API 自动拆成 5/10/15 秒的分镜并写好每镜提示词；再按本地或云端通道逐段出片，上一段尾帧接下一段，最后用 FFmpeg 拼成一部 MP4。分镜可逐条改、单段可重出，中途关掉能接着跑。生图/视频页的描述框另有「AI 润色」，按专业构图补齐机位、景别、光线与材质
- **提示词词库**：人物 / 场景 / 风格 / 光影 / 构图 / 质感 / 反向 七类 56 条中文整句；「灵感」行按类翻卡，通用反向词默认带上且不覆盖手写内容
- **画廊**：SQLite 历史与收藏，成图可一键回填参数继续改；删除进回收站可撤销，图片可一键送去当视频首帧
- **环境体检与一键补齐**：一个环境一个目录（`envs/qwen`、`envs/moss`、`envs/h3`），各自判定缺什么（包 / 权重 / 目录），逐条显示、断点续传，补一个引擎就能单独用
- **下载器**：优先接管本机 Motrix（aria2），没开就走内置多镜像分段下载，都能断点续传
- **OpenAI 风格 API**：生图、编辑、查任务、取图；支持同步 `b64_json` 直出，供其它本地程序调用
- **无框窗口**：任意空白处或外圈边缘按住就能移窗，四角拉尺寸；最大化 / 还原 / 关闭全是自绘

## 界面

导航三组十二页：

| 组 | 页面 | 作用 |
|---|---|---|
| 出图 | 文生图 | 双引擎文生图 + 灵感/词库 |
| | 图像编辑 | 参考图编辑（千问） |
| | 局部重绘 | 涂抹局部重绘（千问） |
| | 视频生成 | H3 出片（文生视频 / 给一张起始图，可从画廊挑）· 本地或云端两条通道在这一页切 |
| | 剧本成片 | 剧情 → AI 拆分镜 → 逐段出片 → 合成；逐镜可改、单段可重出、可续跑，首帧可从画廊挑 |
| 环境 | 基础环境 | 共用依赖、python、显卡与磁盘；FFmpeg 合成扩展也在这里补 |
| | 千问环境 | 明细、一键补齐、量化档 |
| | Moss 环境 | 明细、档位、权重 |
| | H3 视频 | 41 GB 权重与 ComfyUI 节点 |
| 系统 | 作品画廊 | 历史、收藏、参数回填、删除撤销、送视频首帧 |
| | H3 云端 | RunningHub 账号、登录态与浏览器保活，云端出片用 |
| | 运行日志 | 生成、体检、补全一条流 |
| | 全局设置 | 引擎、界面、目录、文本 API（拆分镜/润色）、API |

环境关掉时属于它的功能页从侧栏消失（生图是千问与 Moss 共用，任一路开着就在）；环境那四页永远在——不然关了就没有开回来的门。

## 环境要求

- Windows 10 / 11（依赖 WebView2 运行时，Win11 自带）
- NVIDIA 显卡，**12 GB 显存级**起步
- Python 3.11 – 3.13（推荐 3.12）
- 磁盘：模型权重约 45 GB（千问 30.3 GB + Moss 13.0 GB + LoRA 1.1 GB），叠加依赖建议预留 80 GB；另加 H3 视频约 41 GB（可选，不装不影响生图）；成片合成另要 FFmpeg 静态包约 190 MB（可选，不装仍可逐段出片）

## 快速开始

```bat
git clone https://github.com/zisull/imgTools.git
cd imgTools
```

双击 **`启动.bat`**，只这一个入口。它只负责把软件装到能打开：

1. 没有 `.venv` 就先建一个（几秒）
2. 装界面壳（pywebview）并建好目录，然后直接拉起界面
3. 界面起来后进「环境」页：缺什么、每一项是什么、多大，都在分区明细里；点分区的「一键补齐」，进度显示在页顶横幅上，断了重跑继续
4. 大权重（千问 30.3 GB、Moss 14.1 GB、H3 41.4 GB）全部在软件里下，BAT 不碰

想整包无人值守补齐（依赖 + ComfyUI + 权重）时再带 `--full`：

```bat
启动.bat --full             :: 连依赖、ComfyUI 与权重一起补
启动.bat --full --env qwen  :: 只补千问（--env moss / --env h3 同理）
启动.bat --full --no-models :: 只补依赖，不下权重
启动.bat --full --models-only :: 只下权重
启动.bat --full --jobs 16   :: 网络好时加大下载并发
启动.bat --dry-run          :: 只打印计划与磁盘估算，不动手
```

权重下载器（`webui/envkit/download.py`）先探 hf-mirror，不通再退 huggingface.co；
单文件按 64 MB 切段、8 条连接并行，`.mossdl` 记录每段进度，中断续传。
本机开着 Motrix 时会先把任务交给它的 aria2（端口与密钥运行时从 Motrix 自己的设置里读），
下不动再自动回落内置下载器。镜像与并发在 `envs/index.json` 的 `download` 段里改。

## 两个引擎

| | 千问 Qwen-Image-2.1-Turbo | Moss MOSS-Image |
|---|---|---|
| 运行方式 | diffusers 进程内 | 内嵌 ComfyUI 子进程（独立 venv） |
| 权重 | Turbo 30.3 GB | 13.0 GB（int8/w4a8）+ 8 步 DMD LoRA |
| 步数 | 8（Turbo）/ 40（精细） | 8 / 25 / 50 |
| 特色 | 中文排版、透明底、参考图编辑 | 速度优先、显存可一键让出 |

同一时间只有一个引擎占显存。Moss 的「让出显存」会停掉 ComfyUI 子进程；切回质量档时再拉起。

## REST API

默认关闭，在「设置 → API 服务」开启。默认只监听 `127.0.0.1:8765`，局域网广播默认关；未开启「免令牌」时请求需带 `Authorization: Bearer <token>`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/v1/health` | 健康检查（免鉴权，只回非敏感字段） |
| GET | `/v1/models` | 可用引擎、尺寸、档位与默认值 |
| POST | `/v1/images/generations` | 出图；`engine`/`model` 选引擎，可加 `response_format:"b64_json"` 同步直出 |
| POST | `/v1/images/edits` | 参考图编辑（multipart） |
| GET | `/v1/tasks/{id}` | 异步任务状态 |
| GET | `/v1/images/{id}` | 取结果图 |

```bash
curl http://127.0.0.1:8765/v1/health

curl -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"prompt":"雨夜霓虹下的少女，发丝贴在颊边","engine":"moss","size":"1024x1024","quality":"fast","n":1}' \
  http://127.0.0.1:8765/v1/images/generations
```

尺寸认预设档或 `WxH`：千问 64–4096，Moss 64–2048（非 16 倍数自动下取整）。不传引擎时跟随控制台当前激活引擎，也可在设置里指定默认引擎与默认分辨率。

## 目录结构

```
├─ 启动.bat                      唯一入口：建 .venv → 备界面壳 → 开界面（权重在软件里下）
├─ envs/                         环境目录（一个环境一套，下哪个用哪个）
│  ├─ index.json                 公共部分：python、镜像、下载参数、运行时、环境注册表
│  ├─ qwen/env.json              千问：pip 依赖 + models/ 里的 Turbo 权重
│  ├─ moss/env.json              Moss：ComfyUI 运行时 + 自己的权重
│  ├─ h3/env.json                H3 视频（可选，默认不下载）
│  ├─ ffmpeg/env.json            FFmpeg 合成扩展（可选：只解出 bin/ffmpeg.exe 与 ffprobe.exe）
│  └─ <id>/models/               各环境权重落盘处（不进版本库）
├─ config.json                   运行配置（首次启动生成，不进版本库）
├─ engine/
│  ├─ pipeline_mgr.py            千问 diffusers 引擎
│  └─ moss_mgr.py                内嵌 ComfyUI 子进程管理
├─ webui/
│  ├─ app.py                     pywebview 壳 + js_api
│  ├─ api_server.py              REST API
│  ├─ envkit/                    环境模块：清单解析 / 体检 / 安装 / 下载
│  ├─ filmkit/                   成片模块：AI 拆镜/润色 / 工程落盘 / FFmpeg 拼接与抽尾帧
│  ├─ cloudkit/                  云端：账号快照 / 共享浏览器 / H3 云端执行器
│  ├─ store.py                   SQLite 历史库
│  ├─ ui/                        前端（assemble.py 构建期拼成单文件）
│  └─ moss/                      ComfyUI workflow 模板
├─ scripts/                      安装、下载、自测、无头探针
└─ outputs/ logs/ data/          成图、日志、历史库（均不进版本库）
```

待定方案（只有设计，尚未实现）：

- [H3yun合并方案.md](H3yun合并方案.md)：隔壁那份云端短剧软件（`D:\AI\H3yun`）的全量功能盘点与逐条判定。
- [整体最优设计.md](整体最优设计.md)：当前形状的盘点、按性价比排的交互减法、三份设计文档的吸收清单。

[剧本一键成片方案.md](剧本一键成片方案.md) 已落地成「成片」页：贴剧情 → 选时长 → AI 拆成 5/10/15 秒分镜 → 逐段出片 → 合成。执行通道与视频页同义（本地占显存、云端要登录号），接帧模式用上一段尾帧接下一段，逐镜模式各自成片；分镜表可逐条改、单段可重出（接帧会连带作废下游），工程落在 `outputs/films/<id>/project.json`，关掉再开能续跑。拼接改用 `envs/ffmpeg` 的静态包（不引 PyAV），先校验编码/宽高/像素格式/帧率/音频再 `-c copy`，参数不一致就停下让人重出。文本 API 默认 DeepSeek（OpenAI 兼容），Key 只进本机 `config.json` 或环境变量，界面只显示是否已填。

[H3视频方案设计.md](H3视频方案设计.md) 已落地成「视频」页：一条分段控件选执行地——本地（内嵌 ComfyUI，41.4 GB 权重，4070 12G 上 5 秒 1344×768 约 5 分钟）或云端（RunningHub，不占显存、按积分计费，要一个保存过的登录号与一份工作流地址）。云端执行器在 `webui/cloudkit/gen.py`，等片那段的耗时以「倍」计（实测同参数一段 353 秒出片、一段等满 30 分钟没动），所以状态行只报平台上真读得到的那一句（在跑 / 排队 N 个 / 已收下 / 判失败 / 查不到），读不到就只报等了多久。实测数字见 `Moss交付说明.md` §六。工作流那格既能填平台地址，也能填平台「导出工作流」存下来的 `.json`——后者开跑时自己借一页平台画布进去（换图不换实例），不用再填宿主页；这份 H3 节点只有「首帧/尾帧」与「参考生视频」两档；云端固定走参考生视频、必须给一张参考图（纯文字它不接），本地仍可纯文字出片；出片尺寸由软件写进 `width/height`，云端档位 480P→1440P（2K＝2560×1440），本地停在 768P 原生档。

## 配置

- `config.json`：窗口、主题、环境开关（`env_on`）、当前引擎、各引擎参数（含 `video`、`film`）、文本 API（`ai`）、API 设置、导航布局。删掉会按默认值重建。
- `envs/index.json`：公共环境真源（python、镜像、下载参数、运行时、环境注册表）。
- `envs/<id>/env.json`：每个环境自己的真源（依赖与权重）。加环境就加一个目录、在注册表里挂一行，体检页会自动多一个分区。
- 想直接看界面（不连引擎）：`MIC_DEV=1` 启动时额外注入 `dev/mock.js`，可用普通浏览器预览。

## 自测

```bash
.venv\Scripts\python.exe scripts\moss_selftest.py   # Moss 接线静态自测（无需 GPU）
.venv\Scripts\python.exe scripts\shoot.py           # 16 个无头 Edge 探针（UI 回归）
.venv\Scripts\python.exe scripts\env_test.py        # 环境体检与开关
.venv\Scripts\python.exe scripts\setup_test.py      # 界面壳计划、下载器、Motrix 交接
.venv\Scripts\python.exe scripts\task_test.py       # 千问任务与连续出图
.venv\Scripts\python.exe scripts\api_task_test.py   # API 任务队列
.venv\Scripts\python.exe scripts\gallery_test.py    # 画廊删除撤销（回收站/参数回填/越界拒绝）
.venv\Scripts\python.exe scripts\moss_bench.py      # Moss 真机测速
.venv\Scripts\python.exe scripts\h3_video_smoke.py  # H3 出片真机冒烟（显存/秒数/成片）
```

测试脚本都会使用自己的临时配置，不会写 `config.json`。

## 模型与许可

- **Qwen-Image-2.1**：Qwen Research License，**仅限非商业使用**；商用需另行申请授权。
- **MOSS-Image / Kromoss DMD LoRA / ComfyUI**：分别遵循其上游仓库的许可。
- 本仓库代码暂未附开源许可证；如需复用其中代码，请先与作者联系。
