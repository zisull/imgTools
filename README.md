# Qwen 生图控制台

一个本地桌面生图工作台：同一扇窗口里管理两套本地模型——**千问 Qwen-Image-2.1**（diffusers，进程内）与 **MOSS-Image**（内嵌 ComfyUI 子进程）。pywebview + WebView2 无边框窗口，没有浏览器标签页，也没有命令行黑框；整个程序就是一个文件夹，删掉即净。

## 特性

- **双引擎、单激活**：千问与 Moss 任意时刻只常驻一个，切换时先卸载另一个，不抢显存
- **Moss 三档**：极速 8 步（DMD LoRA）/ 均衡 25 步 / 精修 50 步，另有「让出显存」一键停掉子进程
- **千问两档**：Turbo 8 步 / 精细 40 步，fp8 量化 + CPU offload，12 GB 级显存可跑
- **出图四件事**：文生图、参考图编辑、涂抹重绘、透明底 PNG
- **提示词词库**：人物 / 场景 / 风格 / 光影 / 构图 / 质感 / 反向 七类 56 条中文整句；「灵感」行按类翻卡，通用反向词默认带上且不覆盖手写内容
- **画廊**：SQLite 历史与收藏，成图可一键回填参数继续改
- **环境体检与一键补齐**：按引擎独立判定缺什么（包 / 权重 / 目录），逐条显示、断点续传，补一个引擎就能单独用
- **首启欢迎页**：第一次打开先选「千问 / Moss / 两个都要」，界面按所选自动收放
- **OpenAI 风格 API**：生图、编辑、查任务、取图；支持同步 `b64_json` 直出，供其它本地程序调用

## 界面

导航两组七页：

| 组 | 页面 | 作用 |
|---|---|---|
| 出图 | 生图 | 双引擎文生图 + 灵感/词库 |
| | 编辑 | 参考图编辑（千问） |
| | 重绘 | 涂抹局部重绘（千问） |
| 系统 | 画廊 | 历史、收藏、参数回填 |
| | 环境 | 两引擎体检与一键补齐 |
| | 日志 | 运行日志 |
| | 设置 | 引擎、界面、目录、API |

## 环境要求

- Windows 10 / 11（依赖 WebView2 运行时，Win11 自带）
- NVIDIA 显卡，**12 GB 显存级**起步
- Python 3.11 – 3.13（推荐 3.12）
- 磁盘：模型权重约 45 GB（千问 30.3 GB + Moss 13.0 GB + LoRA 1.1 GB），叠加依赖建议预留 80 GB

## 快速开始

```bat
git clone https://github.com/zisull/imgTools.git
cd imgTools
```

双击 **`启动.bat`**：

1. 首次会自动建 `.venv` 并装好界面壳（只需几秒）
2. 弹出欢迎页，选要走哪一路引擎
3. 到「环境」页点「一键补齐」——下载与安装都在后台跑，界面不卡，进度可见
4. 回到「生图」页，写提示词，Ctrl+Enter 出图

需要命令行一把装齐（可选的旧路径）：

```bat
setup.bat            :: 建 .venv 并按 env.json 装依赖
setup.bat /auto      :: 不暂停，便于脚本调用
```

权重不在 `setup.bat` 里下，统一由「环境」页的「一键补齐」处理（hf-mirror 断点续传）。

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
├─ 启动.bat / setup.bat          启动壳 / 装依赖
├─ env.json                      环境清单：依赖版本、权重仓库、目录约定
├─ config.json                   运行配置（首次启动生成，不进版本库）
├─ engine/
│  ├─ pipeline_mgr.py            千问 diffusers 引擎
│  └─ moss_mgr.py                内嵌 ComfyUI 子进程管理
├─ webui/
│  ├─ app.py                     pywebview 壳 + js_api
│  ├─ api_server.py              REST API
│  ├─ env_check.py               环境体检
│  ├─ store.py                   SQLite 历史库
│  ├─ ui/                        前端（assemble.py 构建期拼成单文件）
│  └─ moss/                      ComfyUI workflow 模板
├─ scripts/                      安装、下载、自测、无头探针
└─ outputs/ logs/ data/          成图、日志、历史库（均不进版本库）
```

## 配置

- `config.json`：窗口、主题、控制台模式、当前引擎、各引擎参数、API 设置、导航布局。删掉会按默认值重建。
- `env.json`：唯一的环境真源。加依赖、换模型版本只改这里，体检与一键补齐都按它执行。
- 想直接看界面（不连引擎）：`MIC_DEV=1` 启动时额外注入 `dev/mock.js`，可用普通浏览器预览。

## 自测

```bash
.venv\Scripts\python.exe scripts\moss_selftest.py   # Moss 接线静态自测（无需 GPU）
.venv\Scripts\python.exe scripts\shoot.py           # 13 个无头 Edge 探针（UI 回归）
.venv\Scripts\python.exe scripts\env_test.py        # 环境体检
.venv\Scripts\python.exe scripts\task_test.py       # 千问任务与连续出图
.venv\Scripts\python.exe scripts\api_task_test.py   # API 任务队列
.venv\Scripts\python.exe scripts\moss_bench.py      # Moss 真机测速
```

测试脚本都会使用自己的临时配置，不会写 `config.json`。

## 模型与许可

- **Qwen-Image-2.1**：Qwen Research License，**仅限非商业使用**；商用需另行申请授权。
- **MOSS-Image / Kromoss DMD LoRA / ComfyUI**：分别遵循其上游仓库的许可。
- 本仓库代码暂未附开源许可证；如需复用其中代码，请先与作者联系。
