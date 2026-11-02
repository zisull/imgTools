# -*- coding: utf-8 -*-
"""moss_mgr —— 内嵌 ComfyUI 子进程 + MOSS-Image 无界面出图客户端。

设计口径（与工作台「同一时间只激活一个生图模型」对齐）：
  · 千问走进程内 diffusers（engine/pipeline_mgr.py），Moss 走**独立子进程 ComfyUI**。
    两者靠 app.py 的引擎切换互斥：切到 Moss 先卸掉 Qwen 模型再拉起 ComfyUI，
    切回千问 / 切到「让出显存档」则**终止整个 ComfyUI 子进程**，把 12G 显存整体归还
    给工作台外部的文字模型软件（档位二的第一原则是「不用就卸」）。
  · 工作流对用户完全隐藏：本模块把 webui/moss/workflow_t2i.json 里的占位符按参数替换，
    直接 POST 给 ComfyUI 的 /prompt，再通过 /ws 拿步数进度、/history + /view 取回成图。

进度：优先用 websocket-client 连 /ws 读 execution_progress(value/max) 精确到步；
读不到就回落成「排队/运行/完成」粗粒度（不影响出图，只影响进度条刻度）。
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

LogFn = Callable[[str], None]
ProgressFn = Callable[[int, int], None]  # (已完成, 总数)

# 工作流里的「这路没给输入」记号，见 build_graph
OMIT = "__omit__"


class ComfyError(RuntimeError):
    """ComfyUI 侧可预期的错误（没起来 / 拒了工作流 / 缺节点），给上层一句人话。"""


def _is_win() -> bool:
    return os.name == "nt"


class _BasicLimit(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32)]


class _IoCounters(ctypes.Structure):
    _fields_ = [("ReadBytes", ctypes.c_ulonglong), ("WriteBytes", ctypes.c_ulonglong),
                ("OtherBytes", ctypes.c_ulonglong), ("ReadOperations", ctypes.c_ulonglong),
                ("WriteOperations", ctypes.c_ulonglong), ("OtherOperations", ctypes.c_ulonglong)]


class _ExtLimit(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimit),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _KillOnCloseJob:
    """Windows Job Object：作业里所有进程，随「最后一个句柄关闭」一起被杀。

    为什么需要它：正常退出和点「让出显存档」都会主动 taskkill 进程树，但壳
    （pythonw.exe）被任务管理器强杀、蓝屏、或崩在半路时没人来得及收尾——ComfyUI
    子进程就变成孤儿，继续占着 12GB 显存，「不用就卸」这条硬边界当场破掉，
    外部文字模型软件直接 OOM。把子进程绑进作业后，壳一死内核就连带收掉它。
    """

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JobObjectExtendedLimitInformation = 9

    def __init__(self):
        self.h = None

    @staticmethod
    def _k32():
        """kernel32 的句柄类型必须显式声明：ctypes 默认把返回值当 32 位 int，
        64 位 Windows 上 HANDLE 会被截断，后面每个调用都失败在「无效句柄」。"""
        k32 = ctypes.windll.kernel32
        k32.CreateJobObjectW.restype = ctypes.c_void_p
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        k32.SetInformationJobObject.restype = ctypes.c_int
        k32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                ctypes.c_void_p, ctypes.c_uint32]
        k32.AssignProcessToJobObject.restype = ctypes.c_int
        k32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        k32.CloseHandle.restype = ctypes.c_int
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        return k32

    def bind(self, proc) -> bool:
        """建作业并把进程绑进去；绑不上（老 Windows / 进程已退出）就返回 False 继续跑，
        有主动收尾那条路兜着，不能因为加固手段失败就不让用户出图。"""
        if not _is_win() or self.h or proc is None:
            return False
        try:
            k32 = self._k32()
            self.h = k32.CreateJobObjectW(None, None)
            if not self.h:
                return False
            info = _ExtLimit()
            info.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(self.h, self.JobObjectExtendedLimitInformation,
                                               ctypes.byref(info), ctypes.sizeof(info)):
                k32.CloseHandle(self.h)
                self.h = None
                return False
            # Windows 上 subprocess 把进程句柄放在私有的 _handle 里（没有 .handle 这个属性）
            ph = getattr(proc, "_handle", None) or getattr(proc, "handle", None)
            if not ph:
                k32.CloseHandle(self.h)
                self.h = None
                return False
            if not k32.AssignProcessToJobObject(self.h, ctypes.c_void_p(int(ph))):
                k32.CloseHandle(self.h)
                self.h = None
                return False
            return True
        except Exception:
            self.close()
            return False

    def close(self) -> None:
        """关掉作业句柄 = 作业里的进程一起没了。stop() 已经先 taskkill 过，这里只是收尾。"""
        if self.h:
            try:
                ctypes.windll.kernel32.CloseHandle(self.h)
            except Exception:
                pass
            self.h = None


@dataclass
class MossState:
    installed: bool = False        # comfyui 目录 + 权重是否齐（env 体检结果灌进来）
    running: bool = False          # ComfyUI 子进程活着且已过健康检查
    tier: str = "daily"            # daily（日常质量档）| yield（让出显存档）
    url: str = ""                  # http://127.0.0.1:<port>
    port: int = 0
    pid: int = 0
    loaded_model: bool = False     # 本会话是否已把 MOSS 权重灌进显存（首次出图后置真）
    last_error: str = ""
    timings: list = field(default_factory=list)


class MossManager:
    def __init__(self, comfyui_dir: str, port: int = 8876,
                 extra_args: Optional[list] = None, log: LogFn = print):
        self.comfyui_dir = os.path.abspath(comfyui_dir)
        self.port = int(port)
        self.extra_args = list(extra_args or [])
        self.log = log
        self.state = MossState(port=self.port)
        self._proc: Optional[subprocess.Popen] = None
        self._logf = None
        # 本轮启动在 logs/comfyui.log 里的字节起点：这份日志跨轮追加，
        # 不切段就会把上一轮的崩溃原因当成这一轮的报错端给人看（真踩过：
        # 换完 CUDA 轮子那一轮只是首次初始化慢，报错却写着上一轮的 CPU 断言）。
        self._log_mark = 0
        self._job = _KillOnCloseJob()   # 壳一死，内核连带收掉 ComfyUI（见类注释）
        # 必须是可重入锁：start() 的失败路径要在持锁状态下调 stop()，
        # 换成普通 Lock 会当场自锁——ComfyUI 崩了界面却不报错，一直停在「启动中」。
        self._lock = threading.RLock()
        self._client_id = uuid.uuid4().hex
        # 预热另用一个 clientId：这样它的事件既不会被投递到用户的进度通道，
        # 也不会因为「同一个 id 两条 /ws 连接」把用户那条挤掉（ComfyUI 按 id 只留一条）
        self._warm_id = uuid.uuid4().hex
        # 预热那条后台线程的手柄：真任务进来时靠这两个把预热撤掉（见 cancel_warm）
        self._warm_pid = None
        self._warm_gone = threading.Event()
        self._stop = threading.Event()
        # 工作流模板：构建期随仓库走，改节点只动这个 JSON，不动代码
        self._tpl_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "webui", "moss")
        ldir = os.path.join(os.path.dirname(self.comfyui_dir), "logs")
        self.log_path = os.path.join(ldir, "comfyui.log")

    # ---------------------------------------------------------------- 路径探针
    def _venv_python(self) -> str:
        return os.path.join(
            self.comfyui_dir, ".venv",
            "Scripts" if _is_win() else "bin",
            "python.exe" if _is_win() else "python")

    def main_script(self) -> str:
        return os.path.join(self.comfyui_dir, "main.py")

    def installed(self) -> bool:
        return (os.path.isfile(self.main_script())
                and os.path.isfile(self._venv_python()))

    # argparse 取最后一次出现，所以 extra_args 里一句 --listen 0.0.0.0 就能把
    # 前面写死的 127.0.0.1 顶掉——内嵌 ComfyUI 没有鉴权，落到局域网等于裸奔。
    _NET_ARGS = ("--listen", "--port", "--host")

    def _safe_extra(self) -> list:
        """用户附加参数里，凡是能改监听地址/端口的一律拒绝启动（不是悄悄丢掉）。

        这条边界是「默认只监听 127.0.0.1、要公开得手动开」的兜底：界面开关走的是
        api_server 那条有令牌的路，内嵌 ComfyUI 一旦被开放出去就是无鉴权的出图接口。
        """
        bad = [a for a in self.extra_args if any(
            str(a).strip() == k or any(str(a).strip().startswith(k + sep)
                                       for sep in ("=", ":"))
            for k in self._NET_ARGS)]
        if bad:
            self.state.last_error = (
                "附加参数 %s 会改掉内嵌 ComfyUI 的监听地址/端口，已拒绝启动："
                "这台引擎没有鉴权，不能暴露到局域网。请从 config.json 的 "
                "moss.extra_args 里去掉。" % "、".join(str(b) for b in bad))
            raise ComfyError(self.state.last_error)
        return [str(a) for a in self.extra_args if str(a).strip()]

    # ---------------------------------------------------------------- 进程生命周期
    def start(self, tier: str = "daily", timeout: float = 420.0, should_stop=None) -> bool:
        """拉起 ComfyUI 子进程并等它健康。yield 档不该调这里（那是停进程）。

        should_stop：可选的「该不该放弃等待」回调（如界面的停止位），首轮加载要一两分钟，
        没有它用户按停止只能干等超时。

        420 秒不是保守，是刚换完 CUDA 轮子那一次实测能吃掉 4 分多钟：Windows Defender 要扫
        cuDNN/cuBLAS 那 1~2GB 动态库、NVIDIA 还要建内核缓存，缓存热了之后同一个引擎 7 秒就绪。
        真崩了一秒就退（进程没了立刻返回），所以放宽超时只会让「慢启动」不再被误判成「启动失败」。
        """
        with self._lock:
            if self.state.running and self._proc_alive():
                self.state.tier = tier
                return True
            if not self.installed():
                self.state.last_error = "内嵌 ComfyUI 还没装好：去环境页一键补全"
                raise ComfyError(self.state.last_error)
            py = self._venv_python()
            if self._port_busy():
                # 端口被占：多半是上一次没杀干净或用户自己开了同端口 ComfyUI
                self.state.last_error = (
                    "端口 %d 已被占用：可能是残留的 ComfyUI，请先在 Moss 页停止引擎" % self.port)
                raise ComfyError(self.state.last_error)
            args = [py, self.main_script(),
                    "--listen", "127.0.0.1", "--port", str(self.port),
                    "--disable-auto-launch"]
            # 日常质量档：全量加载、性能全开，不加 --lowvram（让 ComfyUI 自己 offload 文本编码器）
            args += self._safe_extra()
            env = dict(os.environ, PYTHONUNBUFFERED="1",
                       PYTHONIOENCODING="utf-8", CUDA_VISIBLE_DEVICES="0")
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            try:
                self._log_mark = os.path.getsize(self.log_path)
            except OSError:
                self._log_mark = 0      # 文件还没有：整份都算本轮
            logf = open(self.log_path, "a", encoding="utf-8", errors="replace")
            logf.write("\n===== ComfyUI 启动 %s tier=%s =====\n"
                       % (time.strftime("%Y-%m-%d %H:%M:%S"), tier))
            logf.flush()
            self._close_log()
            self._logf = logf
            try:
                self._proc = subprocess.Popen(
                    args, cwd=self.comfyui_dir, env=env, stdout=logf, stderr=logf,
                    creationflags=(0x08000000 if _is_win() else 0))  # CREATE_NO_WINDOW
            except OSError as e:
                self.state.last_error = "起不了 ComfyUI：%s" % e
                raise ComfyError(self.state.last_error)
            self.state.pid = self._proc.pid
            self.state.url = "http://127.0.0.1:%d" % self.port
            # 绑不进作业只是「强杀壳」这条兜底失效，正常收尾仍在，不值得为此拦住出图
            if not self._job.bind(self._proc):
                self.log("· 未能绑定作业对象：强杀本程序时 ComfyUI 可能残留（可手动结束）")
            self.log("🌱 正在启动内嵌 ComfyUI（端口 %d，首次加载权重较慢）…" % self.port)
            why = self._wait_ready(timeout, should_stop)
            if why:
                alive = self._proc_alive()
                reason = "" if why.startswith("已取消") else self._fail_reason()
                self.stop()
                for ln in self._tail_log(10):
                    self.log("   │ " + ln)
                if reason:
                    tail = "；" + reason
                elif alive:
                    # 进程还在、只是没到 /system_stats：这不是崩，是还没起完。
                    # 最常见就是刚换完 CUDA 轮子的第一次初始化（Windows 要扫 1~2GB 动态库、建内核缓存）。
                    tail = ("；进程还活着，是没等够而不是起不来——首次装完 CUDA 版 torch 时 "
                            "Windows 要扫一遍 cuDNN/cuBLAS 那几个大动态库并建显存内核缓存，"
                            "可能好几分钟。再点一次启动通常就好了")
                else:
                    tail = "；进程已经退出，看上面末尾几行"
                self.state.last_error = "ComfyUI 没起来：%s%s（末尾日志见上，全量在 logs/comfyui.log）" % (
                    why, tail)
                raise ComfyError(self.state.last_error)
            self.state.running = True
            self.state.loaded_model = False   # 进程是新的，显存里的权重不算数了
            self.state.tier = tier
            self.state.last_error = ""
            self.log("✅ ComfyUI 已就绪：%s" % self.state.url)
            return True

    def stop(self, wait: float = 8.0) -> None:
        """终止整个子进程树：这是「让出显存档」和「切回千问」释放显存的动作。"""
        with self._lock:
            proc = self._proc
            if proc is not None and proc.poll() is None:
                self._kill_tree(proc.pid)
            try:
                if proc is not None:
                    proc.wait(timeout=wait)
            except Exception:
                pass
            self._proc = None
            self._close_log()
            self._job.close()      # 先杀树再放句柄：顺序反了会把刚拉起的进程一起带走
            self.state.running = False
            self.state.loaded_model = False
            self.state.pid = 0
            self.state.url = ""
            self.log("🛑 已停止 ComfyUI 子进程，显存归还给系统")

    def _close_log(self) -> None:
        """日志句柄要跟着进程关：反复启停会把 fd 漏光。"""
        if self._logf is not None:
            try:
                self._logf.close()
            except OSError:
                pass
            self._logf = None

    def _kill_tree(self, pid: int) -> None:
        if _is_win():
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=10)
                return
            except Exception:
                pass
        if pid and self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _proc_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _proc_died(self) -> bool:
        """子进程自己退了。没起进程（单测直连假 ComfyUI）时返回 False，别误报。"""
        return self._proc is not None and self._proc.poll() is not None

    def _tail_log(self, n: int = 10) -> list:
        """摘「本轮启动那一段」日志的末尾几行：崩在 import 阶段时，这几行就是根因。"""
        try:
            with open(self.log_path, "rb") as f:
                if self._log_mark:
                    f.seek(self._log_mark)
                raw = f.read()
            lines = [x.rstrip() for x in raw.decode("utf-8", "replace").splitlines() if x.strip()]
        except OSError:
            return []
        return [re.sub(r"\x1b\[[0-9;]*m", "", x) for x in lines[-n:]]

    def _fail_reason(self) -> str:
        """从本轮日志尾巴里挑最后一条异常行，拼进界面报错，省得人去翻文件。"""
        lines = self._tail_log(60)
        # 只有 1~2 行说明子进程刚起步就被杀（超时按停止、首次初始化慢），
        # 这种尾巴里最像异常的往往是 ComfyUI 自己那句「请升级 torch」的 WARNING，
        # 端给人当根因会让人去做根本不用做的事。
        if len(lines) < 3:
            return ""
        for ln in reversed(lines):
            m = re.match(r"^\s*([A-Za-z_][\w.]*(?:Error|Exception))\s*:?\s*(.*)", ln)
            if m:
                return "%s：%s" % (m.group(1), m.group(2) or "见日志")
        return ""

    def _port_busy(self) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.4)
        try:
            return s.connect_ex(("127.0.0.1", self.port)) == 0
        finally:
            s.close()

    # ---------------------------------------------------------------- HTTP
    def _get(self, path: str, timeout: float = 6.0) -> bytes:
        req = urllib.request.Request(self.state.url + path, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    def _post(self, path: str, obj: dict, timeout: float = 30.0) -> dict:
        data = json.dumps(obj).encode("utf-8")
        req = urllib.request.Request(self.state.url + path, data=data,
                                     method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise ComfyError("ComfyUI 拒绝请求（HTTP %d）：%s" % (e.code, _trim(body)))
        return json.loads(raw or b"{}")

    def _wait_ready(self, timeout: float, should_stop=None) -> str:
        """等 ComfyUI 健康。返回空串=起来了；否则一句「为什么没起来」。

        进程提前退出和超时是两回事：前者一秒都不该多等。
        首次拉起要一两分钟，这段时间用户点了「停止」就得立刻退，不能干等到超时。
        """
        t0 = time.time()
        next_note = t0 + 30.0
        while True:
            if should_stop and should_stop():
                return "已取消（用户按了停止）"
            if self._proc_died():
                return "进程退出（码 %s）" % self._proc.returncode
            try:
                self._get("/system_stats", timeout=3.0)
                return ""
            except Exception:
                pass
            if time.time() - t0 >= timeout:
                return "等 %d 秒没等到 /system_stats" % int(timeout)
            if time.time() >= next_note:
                # 每 30 秒把 ComfyUI 当前走到哪一步端上来：等待不是一个黑盒，
                # 用户才知道「还在装/还在初始化」和「死了」的区别
                tail = self._tail_log(1)
                self.log("   · 还在等 ComfyUI 就绪（已 %d 秒）%s"
                         % (int(time.time() - t0), "｜" + tail[0][:90] if tail else ""))
                next_note += 30.0
            # 头 15 秒多半还在 import，密一点探；之后退回 1 秒一轮别空转 CPU
            time.sleep(0.25 if time.time() - t0 < 15 else 1.0)

    def alive(self) -> bool:
        """引擎此刻还在不在。`state.running` 是「我们把它拉起过」的粘性标记：
        子进程中途没了（显存不够被系统端掉、用户在任务管理器里顺手结束）它不会自己翻，
        于是下一次出图会撞上一个说不清的 HTTP 错误。"""
        if not self.state.running:
            return False
        if self._proc_died():
            self.state.running = False
            self.state.loaded_model = False
            self.log("⚠️ ComfyUI 子进程中途退出了：下次生成会重新拉起")
            return False
        return True

    def occupying(self) -> bool:
        """有没有什么东西还占着显存/端口：粘性标记说拉起过，或者子进程真的还在。
        「停引擎」的三处（切回千问、让出显存档、手动卸载）都问这个，别只信
        `state.running`——启动到一半超时、进程还活着时那个标记是 False，
        用户点了「让出显存」而显存根本没还，这条硬边界就破了。"""
        return bool(self.state.running) or self._proc_alive()

    def health(self) -> dict:
        if not self.state.running:
            return {"running": False, "tier": self.state.tier}
        try:
            return {"running": True, "tier": self.state.tier,
                    "system_stats": json.loads(self._get("/system_stats", 3.0))}
        except Exception as e:
            return {"running": self._proc_alive(), "tier": self.state.tier,
                    "error": str(e)}

    # ---------------------------------------------------------------- 工作流组装
    def load_template(self, name: str = "workflow_t2i.json") -> dict:
        p = os.path.join(self._tpl_dir, name)
        if not os.path.isfile(p):
            raise ComfyError("工作流模板缺失：%s（应由一键补全从仓库拉齐）" % p)
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _substitute(node: dict, tokens: dict) -> dict:
        """把模板里 "{{key}}" 占位符换成具体值；整个值是单个占位符时保留原类型。"""
        def val_of(x):
            if isinstance(x, str) and x in tokens:
                return tokens[x]
            return None

        def walk(v):
            if isinstance(v, dict):
                return {k: walk(n) for k, n in v.items()}
            if isinstance(v, list):
                return [walk(n) for n in v]
            if isinstance(v, str):
                hit = val_of(v)
                if hit is not None:
                    return hit
                for k, tv in tokens.items():
                    if k in v:
                        v = v.replace(k, str(tv))
                return v
            return v

        return walk(node)

    def build_graph(self, *, template: str = "workflow_fast.json",
                    prompt: str, negative: str, width: int, height: int,
                    seed: int, steps: int = 8, cfg: float = 1.0,
                    shift: float = 5.0, slg_skip_layer: int = 22,
                    slg_start: float = 0.0, slg_end: float = 0.5,
                    lora_strength: float = 1.0, batch: int = 1,
                    length: int = 0, fps: float = 24.0,
                    first_image: str = "",
                    prefix: str = "moss") -> dict:
        """按 UI 参数填模板占位符。shift/SLG 等固定采样参数一般已烘进模板，
        这里保留同名占位符是为了极少数需要按档位覆盖的情况。

        OMIT（"__omit__"）是「这一路没给输入」的记号：填到某个输入上就把那个输入摘掉
        （视频页不给首帧时 MiniMaxH3ImageToVideo 就没有 first_frame 这条边），
        带 `_optional` 的节点只要有任一是 OMIT 就整节摘掉（没人连它的 LoadImage 留着
        会让 ComfyUI 校验报错，因为默认图名在这台机器的输入目录里根本不存在）。
        """
        tpl = self.load_template(template)
        tokens = {
            "{{prompt}}": prompt,
            "{{negative}}": negative,
            "{{width}}": int(width),
            "{{height}}": int(height),
            "{{batch}}": max(1, int(batch)),
            "{{seed}}": int(seed),
            "{{steps}}": int(steps),
            "{{cfg}}": float(cfg),
            "{{shift}}": float(shift),
            "{{slg_skip_layer}}": str(int(slg_skip_layer)),
            "{{slg_start}}": float(slg_start),
            "{{slg_end}}": float(slg_end),
            "{{lora_strength}}": float(lora_strength),
            "{{length}}": int(length),
            "{{fps}}": float(fps),
            "{{first_image}}": first_image or OMIT,
            "{{first_frame}}": ["16", 0] if first_image else OMIT,
            "{{prefix}}": str(prefix),
        }
        graph = {}
        for nid, node in tpl.items():
            if str(nid).startswith("_"):
                continue
            sub = self._substitute(node, tokens)
            ins = sub.get("inputs") or {}
            gone = any(v == OMIT for v in ins.values())
            if gone and sub.pop("_optional", None):
                continue
            sub["inputs"] = {k: v for k, v in ins.items() if v != OMIT}
            sub.pop("_optional", None)
            graph[nid] = sub
        return graph

    # ---------------------------------------------------------------- 出图
    def generate(self, params: dict, *, on_progress: Optional[ProgressFn] = None,
                 should_stop: Optional[Callable[[], bool]] = None,
                 out_dir: str, out_prefix: str = "moss") -> list:
        """组装工作流 → /prompt → 跟踪 → 取回 PNG 存进 out_dir，返回绝对路径列表。"""
        if not self.alive():
            raise ComfyError("ComfyUI 没在跑：先切到日常质量档或点开始（会自动拉起）")
        self.cancel_warm()      # 用户这一轮比预热重要：还排在后面的预热直接撤掉
        graph = self.build_graph(**params)
        # 先挂 /ws 再提交：ComfyUI 按 client_id 找连接投递事件，晚一步这一轮的
        # execution_progress / execution_success 就整批发给了还不存在的 socket，
        # 界面进度条全空、只能干等到超时（真机上 14 秒出图硬是拖成 20 分钟）。
        ws = self._open_ws()
        try:
            resp = self._post("/prompt", {"prompt": graph, "client_id": self._client_id})
            prompt_id = resp.get("prompt_id")
            if not prompt_id:
                raise ComfyError("提交失败：%s" % _trim(json.dumps(resp, ensure_ascii=False)))
            self.state.loaded_model = True
            self._track(prompt_id, on_progress, should_stop, ws=ws)
            if should_stop and should_stop():
                self._interrupt()
                return []
            return self._collect(prompt_id, out_dir, out_prefix)
        finally:
            self._close_ws(ws)

    def upload_image(self, path: str) -> str:
        """把本地图片交给 ComfyUI 的输入目录，返回它在 LoadImage 下拉里的名字。

        首帧是盘上的文件而工作流只认名字：不传这一步，视频页的「拿这张图当第一帧」
        就只能指望用户自己把图拷进 comfyui/input ——那是把人往坑里带。
        """
        if not os.path.isfile(path):
            raise ComfyError("首帧图不存在：%s" % path)
        name = os.path.basename(path)
        boundary = "----imgtools%d" % id(name)
        with open(path, "rb") as f:
            blob = f.read()
        head = ("--%s\r\nContent-Disposition: form-data; name=\"image\"; "
                "filename=\"%s\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                % (boundary, name)).encode("utf-8")
        tail = ("\r\n--%s--\r\n" % boundary).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:%d/upload/image" % self.port,
            data=head + blob + tail, method="POST",
            headers={"Content-Type": 'multipart/form-data; boundary="%s"' % boundary})
        try:
            with urllib.request.urlopen(req, timeout=60.0) as r:
                got = json.loads(r.read().decode("utf-8", "replace") or "{}")
        except Exception as e:
            raise ComfyError("首帧图传不进 ComfyUI：%s" % e)
        return str(got.get("name") or name)

    def warm(self, size: int = 256, steps: int = 1, timeout: float = 600.0) -> bool:
        """把权重真正搬上显存：ComfyUI 是懒加载，「/system_stats 应答了」不等于「模型上卡了」。

        这解决两件实测出来的事（12G 卡）：
          · 日常质量档刚点亮时整卡只有 1.2 G 左右，和「让出显存档」看不出任何区别——
            因为进程虽然起来了，那 12.7 G 权重还躺在硬盘上；
          · 第一张图因此要多等约 7 秒才出首帧，这 7 秒不在进度条里，用户体验成「卡住」。
        所以拉起进程后在后台提交一张 256²/1 步的小图，让 UNet + 文本编码器 + VAE 顺着
        真实推理路径加载进显存，成图随即删掉（不进图库）。

        预热只是兜底，不是前置条件：失败最坏就是第一张图照旧多等几秒，绝不能因为
        一个后台兜底线程报错，把已经就绪的引擎在界面上报成「启动失败」。
        """
        if not self.alive():
            return False
        pid0 = self.state.pid
        t0 = time.time()
        prompt_id = None
        self._warm_gone.clear()
        try:
            graph = self.build_graph(
                template="workflow_fast.json", prompt="warmup", negative="",
                width=size, height=size, steps=steps, cfg=1.0, batch=1,
                seed=int(time.time() * 1000) % 10 ** 8, prefix="moss_warm")
            # 用独立的 clientId 提交：/ws 事件按 clientId 投递，预热的进度事件绝不能
            # 挤进用户那一轮的通道（接收端虽然按 prompt_id 过滤，也不该把话说成赌它）。
            # number 给到 1e9：ComfyUI 的任务队列是「数字小的先跑」最小堆，预热排最后，
            # 用户点完「启用」立刻点「开始」时，真任务会插到预热前面。
            prompt_id = self._post("/prompt", {"prompt": graph,
                                               "client_id": self._warm_id,
                                               "number": 10 ** 9}).get("prompt_id")
            if not prompt_id:
                return False
            self._warm_pid = prompt_id
            if not self._warm_wait(prompt_id, pid0, timeout):
                return False
            self.state.loaded_model = True
            self.log("🔥 预热完成（%.1f 秒）：权重已常驻显存，第一张图不再等加载"
                     % (time.time() - t0))
            return True
        except Exception as e:
            # 进程还活着才有必要说话：被用户停掉/切档退掉时无声退场就够了
            if self._proc_alive():
                self.log("ℹ️ 预热没走完（%s）：不影响出图，第一张会自己把权重搬上卡" % e)
            return False
        finally:
            if self._warm_pid == prompt_id:
                self._warm_pid = None
            if prompt_id:
                self._drop_warm_images(prompt_id)

    def cancel_warm(self) -> None:
        """用户真的开始出图了：把还没跑完的预热撤掉，别让它挡在前面。

        预热省的是「权重上卡」那一次性的钱，它自己并不值钱——所以一旦有真任务进来，
        排在后面就该直接删掉，正在跑就该打断。只动预热那一条：/interrupt 打的是
        ComfyUI 当前正在跑的任务，先确认跑的就是预热才敢按。
        """
        pid = self._warm_pid
        if not pid:
            return
        self._warm_pid = None
        self._warm_gone.set()      # 让预热那条线程自己收工，别守到超时
        try:
            q = json.loads(self._get("/queue", 4.0))
            pend = [str(x[1]) for x in (q.get("queue_pending") or []) if isinstance(x, list)]
            run = [str(x[1]) for x in (q.get("queue_running") or []) if isinstance(x, list)]
            if pid in pend:
                self._post("/queue", {"delete": [pid]})
            elif pid in run:
                self._post("/interrupt", {})
        except Exception:
            pass                   # 撤不掉也就多等几秒，不值得把出图这条路带崩

    def _warm_wait(self, prompt_id: str, pid0: int, timeout: float) -> bool:
        """等预热那张图跑完。返回 False=该闭嘴退场，不抛错。

        不复用 _await_history：那条路在「该停了」时会 POST /interrupt，而中断打的是
        ComfyUI 当前正在跑的任务——预热被取消的同一时刻用户可能正好在出图，
        拿人家的任务当自己的收尾代价太大了。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._warm_gone.is_set():
                return False          # 有真任务进来了，预热让路：这是正常收场，不用吭声
            if self.state.pid != pid0 or self._proc_died():
                return False          # 引擎被停掉或重启了：这不是失败，不用吭声
            if self._in_history(prompt_id):
                return True
            time.sleep(1.0)
        self.log("ℹ️ 预热等够了 %d 秒还没完：第一张图可能仍要加载权重" % int(timeout))
        return False

    def _drop_warm_images(self, prompt_id: str) -> None:
        """删掉预热写进 comfyui/output 的那张垃圾小图。

        只认 moss_warm 前缀：真正出的图在这个目录里也有一份（SaveImage 落在 ComfyUI
        自己的 output，界面取图时再 /view 复制去配置的输出目录），不看前缀就是删人家的图。
        """
        try:
            h = json.loads(self._get("/history/" + prompt_id, 8.0))
            imgs = self._media_of((h.get(prompt_id) or {}).get("outputs") or {})
        except Exception:
            return
        for item in imgs:
            fn = os.path.basename(str(item.get("filename") or ""))
            if not fn.startswith("moss_warm"):
                continue
            sub = str(item.get("subfolder") or "").replace("..", "")
            try:
                os.remove(os.path.join(self.comfyui_dir, "output", sub, fn))
            except OSError:
                pass      # 已被 ComfyUI 清掉 / 只读：预热本来就不该留下东西

    def _open_ws(self):
        """建 /ws 长连；连不上回 None，由 _track 回落到完成轮询。

        查询参数名是 clientId（驼峰），必须和 POST /prompt 里的 client_id 同值：
        服务端把带 clientId 的连接注册进 sockets[clientId]，progress/executing/
        execution_success 只往这个 sid 投。写成 client_id 的话服务端给连接另发一个
        uuid，投递时 sid 找不到 socket，事件整批静默丢弃（socket 本身还是连着的，
        所以只会表现为「进度条空、等到天荒地老」，一点报错都没有）。
        """
        try:
            import websocket  # websocket-client（envs 清单已列）
            return websocket.create_connection(
                "ws://127.0.0.1:%d/ws?clientId=%s" % (self.port, self._client_id),
                timeout=8.0)
        except Exception as e:
            self.log("ℹ️ 实时进度通道连不上（%s），改用完成轮询" % e)
            return None

    @staticmethod
    def _close_ws(ws) -> None:
        if ws is None:
            return
        try:
            ws.close()
        except Exception:
            pass

    def _track(self, prompt_id: str, on_progress, should_stop, ws=None) -> None:
        """优先走 /ws 拿步级进度；失败回落到轮询 /history 判完成。"""
        if self._in_history(prompt_id):
            return          # 同参数复点会命中节点缓存：秒出图，/ws 一条消息都收不到
        if ws is None:
            self._track_poll(prompt_id, should_stop)
            return
        try:
            self._track_ws(prompt_id, on_progress, should_stop, ws)
        except ComfyError:
            raise
        except Exception as e:
            self.log("ℹ️ 实时进度通道断开（%s），改用完成轮询" % e)
            self._track_poll(prompt_id, should_stop)

    def _in_history(self, prompt_id: str) -> bool:
        try:
            return prompt_id in json.loads(self._get("/history/" + prompt_id, 4.0))
        except Exception:
            return False

    def _track_ws(self, prompt_id: str, on_progress, should_stop, ws) -> None:
        import websocket  # websocket-client（envs 清单已列）
        t0 = time.time()
        next_check = t0 + 2.0
        try:
            ws.settimeout(1.0)
        except Exception:
            pass
        while time.time() - t0 < 1200:
            if should_stop and should_stop():
                self._interrupt()
                break
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                # 心跳窗口顺手查一眼 history：一条事件都没收到时（连接时序、
                # 反代缓冲、ComfyUI 自己漏发），也得能秒收尾而不是耗到上限。
                if time.time() >= next_check:
                    next_check = time.time() + 2.0
                    if self._in_history(prompt_id):
                        return
                continue
            except websocket.WebSocketConnectionClosedException:
                break
            if not isinstance(raw, str):
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            mtype = msg.get("type")
            d = msg.get("data") or {}
            # 步级进度两代事件名都收：本仓内嵌这支 ComfyUI 发的是 "progress"
            # （main.py 的 hijack_progress），旧版叫 "execution_progress"。
            if mtype in ("execution_progress", "progress"):
                if d.get("prompt_id") in (None, prompt_id):
                    mx = int(d.get("max") or 0)
                    v = int(d.get("value") or 0)
                    if on_progress and mx:
                        on_progress(min(v, mx), mx)
            elif mtype == "execution_success":
                if d.get("prompt_id") == prompt_id:
                    break
            elif mtype == "execution_error":
                if d.get("prompt_id") == prompt_id:
                    raise ComfyError("节点报错：%s" % _trim(str(d.get("exception_message", ""))))
            elif mtype == "executing" and d.get("node") is None \
                    and d.get("prompt_id") == prompt_id:
                break
        # 收尾确认：/ws 可能因连接时序漏掉 success，再查一眼 history 兜底
        self._await_history(prompt_id, should_stop)

    def _track_poll(self, prompt_id: str, should_stop) -> None:
        self._await_history(prompt_id, should_stop)

    def _await_history(self, prompt_id: str, should_stop, timeout: float = 1200.0) -> None:
        """等这一轮的结果进 history。

        步长从 0.15 秒退避到 1 秒：/ws 收到 execution_success 后还要走这一道来确认，
        固定 1 秒意味着每张图都白等最多 1 秒收尾——极速档一张才 4 秒，这是 20% 的量；
        而精修档那种一分多钟的任务不需要密轮询，退避正好两头都占到。
        """
        t0 = time.time()
        wait = 0.15
        while time.time() - t0 < timeout:
            if should_stop and should_stop():
                self._interrupt()
                return
            if self._proc_died():
                raise ComfyError("ComfyUI 进程中途退了（显存不够或节点报错）：%s"
                                 % (self._fail_reason() or "见 logs/comfyui.log"))
            if self._in_history(prompt_id):
                return
            time.sleep(wait)
            wait = min(1.0, wait * 2)
        raise ComfyError("出图超时（%ds 没回结果）" % int(timeout))

    def _interrupt(self) -> None:
        try:
            self._post("/interrupt", {})
        except Exception:
            pass

    @staticmethod
    def _media_of(outputs: dict) -> list:
        """成图与成片的取回入口是两套键：SaveImage 写 images，SaveVideo 写 videos。

        视频页就靠这一条走到同一个 _collect 里来，不然跑完 41 GB 权重出的片
        只躺在 ComfyUI 的 output 目录里，界面报「工作流跑完但没取回图片」。
        """
        out = []
        for key in ("images", "videos", "audio"):
            if isinstance(outputs.get(key), list):
                out += outputs[key]
            for v in outputs.values():
                if isinstance(v, dict) and isinstance(v.get(key), list):
                    out += v[key]
        seen, uniq = set(), []
        for it in out:
            k = (it.get("filename"), it.get("subfolder"), it.get("type"))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(it)
        return uniq

    def _collect(self, prompt_id: str, out_dir: str, prefix: str) -> list:
        h = json.loads(self._get("/history/" + prompt_id, 8.0))
        entry = h.get(prompt_id) or {}
        imgs = self._media_of(entry.get("outputs") or {})
        if not imgs:
            # 节点报错时 history 里也有这条记录，只是没有出图结果：别报成「模板缺 SaveImage」
            st = entry.get("status") or {}
            if st.get("status_str") == "error":
                msgs = [str(m[1].get("message")) for m in (st.get("messages") or [])
                        if isinstance(m, list) and len(m) > 1 and isinstance(m[1], dict)]
                raise ComfyError("ComfyUI 报错了：%s"
                                 % (_trim(" / ".join(msgs)) if msgs else "见 logs/comfyui.log"))
            raise ComfyError("工作流跑完但没有出图/出片节点结果（检查模板里的 SaveImage/SaveVideo）")
        os.makedirs(out_dir, exist_ok=True)
        saved = []
        for item in imgs:
            fn = item.get("filename") or ""
            sub = item.get("subfolder") or ""
            q = urllib.parse.urlencode({"filename": fn, "subfolder": sub,
                                        "type": item.get("type", "output")})
            data = self._get("/view?" + q, timeout=30.0)
            stem = "%s_%s" % (prefix, time.strftime("%Y%m%d_%H%M%S"))
            ext = os.path.splitext(fn)[1].lower() or ".png"
            path = os.path.join(out_dir, "%s%s" % (stem, ext))
            bump = 0
            while os.path.exists(path):
                bump += 1
                path = os.path.join(out_dir, "%s_%d%s" % (stem, bump, ext))
            with open(path, "wb") as f:
                f.write(data)
            saved.append(path)
        return saved


def _trim(s: str, n: int = 300) -> str:
    s = str(s).strip().replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"
