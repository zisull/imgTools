# -*- coding: utf-8 -*-
"""single_instance.py —— 防多开：和旧版桌面壳共用同一把锁，新老不能同时跑。

三处契约照旧壳（PySide6，已删；逐字对照去 git `88b536d^` 翻 mic_webtm_desktop.py）搬过来，
**只换实现、不换协议**，所以两头互相认得：

    锁文件  %APPDATA%\\Mictools\\mictools_single.lock   Qt 侧 = QLockFile（Windows 上就是独占持有文件句柄）
    通知    \\\\.\\pipe\\MiCTools_SingleInstance          Qt 侧 = QLocalServer（Windows 上落地为命名管道）
    字节    activate                                     旧壳 _notify_existing_instance() 写的那串

因此：旧 exe 在跑时启动新版 → 新版被挡住，并把旧窗口弹到前台；新版在跑时启动旧 exe → 旧版同样退出。
两边共用 .rfq 计数和同一个 SQLite，双开会各写各的，所以这把锁是真需要。
"""

import ctypes
import os
import socket
import threading
from ctypes import wintypes

LOCK_DIR_NAME = "Mictools"                      # 与 rfq_core / app.py 的数据目录同名
LOCK_FILE_NAME = "mictools_single.lock"         # 旧壳 _INSTANCE_LOCK_NAME
PIPE_SERVER_NAME = "MiCTools_SingleInstance"    # 旧壳 _INSTANCE_SERVER_NAME
ACTIVATE = b"activate"                          # 旧壳写进 socket 的那 8 个字节
LOCK_APP_NAME = "MiC Tools"                     # 锁文件第三行：Qt 只拿它拼提示语

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
CREATE_NEW = 1
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_BEGIN = 0
# 句柄一律用 c_ssize_t 取回：这样 INVALID_HANDLE_VALUE 正好是 -1
# （c_void_p 会把 -1 当成无符号大整数，比较起来是个坑，实测踩过）
INVALID = -1
ERROR_FILE_EXISTS = 80
ERROR_ALREADY_EXISTS = 183
ERROR_SHARING_VIOLATION = 32
ERROR_ACCESS_DENIED = 5
ERROR_PIPE_CONNECTED = 534
PIPE_ACCESS_DUPLEX = 0x3
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
SW_RESTORE = 9
ASFW_ANY = -1

_K32 = None
_U32 = None


def _k32():
    global _K32
    if _K32 is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = ctypes.c_ssize_t
        k.CreateFileW.restype = handle
        k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p]   # 末位 hTemplateFile 传 None，别按整数声明
        k.CreateNamedPipeW.restype = handle
        k.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                       wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                       wintypes.DWORD, ctypes.c_void_p]
        k.ConnectNamedPipe.argtypes = [handle, ctypes.c_void_p]
        k.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        k.ReadFile.argtypes = [handle, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        k.WriteFile.argtypes = [handle, ctypes.c_void_p, wintypes.DWORD,
                                ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        k.CloseHandle.argtypes = [handle]
        k.SetFilePointer.restype = wintypes.DWORD
        k.SetFilePointer.argtypes = [handle, ctypes.c_long, ctypes.c_void_p, wintypes.DWORD]
        k.GetFileSizeEx.argtypes = [handle, ctypes.POINTER(ctypes.c_longlong)]
        k.SetEndOfFile.argtypes = [handle]
        k.OpenProcess.restype = handle
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.GetExitCodeProcess.argtypes = [handle, ctypes.POINTER(wintypes.DWORD)]
        _K32 = k
    return _K32


def _u32():
    global _U32
    if _U32 is None:
        u = ctypes.WinDLL("user32")
        hwnd = ctypes.c_void_p
        u.ShowWindow.argtypes = [hwnd, ctypes.c_int]
        u.SetForegroundWindow.argtypes = [hwnd]
        u.SwitchToThisWindow.argtypes = [hwnd, wintypes.BOOL]
        u.AllowSetForegroundWindow.argtypes = [ctypes.c_int]   # ASFW_ANY = -1，别按无符号传
        _U32 = u
    return _U32


def lock_path():
    """锁文件路径，和旧壳逐字一致：%APPDATA%\\Mictools\\mictools_single.lock。"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, LOCK_DIR_NAME)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return os.path.join(d, LOCK_FILE_NAME)


def pipe_path():
    """命名管道的完整路径：QLocalServer(name) 在 Windows 上就是 \\\\.\\pipe\\<name>。"""
    return r"\\.\pipe\%s" % PIPE_SERVER_NAME


def _hostname():
    return socket.gethostname().lower()


def _read_owner(handle):
    """读锁文件里登记的主人：(pid, hostname)。解析不出来当 (None, "")。

    用我们自己那个句柄读——Qt 侧写的就是同一个格式，所以老锁能被这里看懂，
    我们写的老 Qt 也看得懂。
    """
    k = _k32()
    k.SetFilePointer(handle, 0, None, FILE_BEGIN)
    size = ctypes.c_longlong(0)                   # GetFileSizeEx 是「返回 BOOL + 出参」，不是返回值本身
    if not k.GetFileSizeEx(handle, ctypes.byref(size)) or not (0 < size.value <= 4096):
        return None, ""
    buf = ctypes.create_string_buffer(size.value)
    got = wintypes.DWORD(0)
    if not k.ReadFile(handle, buf, size.value, ctypes.byref(got), None):
        return None, ""
    lines = buf.raw[:got.value].decode("utf-8", "replace").splitlines()
    pid = int(lines[0]) if lines and lines[0].strip().isdigit() else None
    host = lines[1].strip().lower() if len(lines) > 1 else ""
    return pid, host


def _write_owner(handle):
    """按 Qt 的三行格式登记自己：pid\\nhostname\\nappname\\n。"""
    data = ("%d\n%s\n%s\n" % (os.getpid(), _hostname(), LOCK_APP_NAME)).encode("utf-8")
    k = _k32()
    k.SetFilePointer(handle, 0, None, FILE_BEGIN)
    k.SetEndOfFile(handle)
    wrote = wintypes.DWORD(0)
    k.WriteFile(handle, data, len(data), ctypes.byref(wrote), None)


def _pid_alive(pid):
    k = _k32()
    h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    code = wintypes.DWORD(0)
    ok = k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    return bool(ok) and code.value == STILL_ACTIVE


def _held_by_live_other(handle):
    """句柄已经拿到手了，但文件里登记的进程可能还活着（老 Qt 那侧未必独占句柄）。

    换机器/漫游配置文件导致 hostname 对不上，按 stale 处理——和 Qt 的口径一致。
    """
    pid, host = _read_owner(handle)
    if pid is None:
        return False
    if host and host != _hostname():
        return False
    return pid != os.getpid() and _pid_alive(pid)


class SingleInstance:
    """一次启动一个实例：acquire 拿到锁才继续，拿不到就通知已有那份弹前台。

    path / pipe 是给跨进程测试留的口子（_single_probe.py 用临时路径 + 临时管道名，
    免得撞用户正开着的那份）；主程序一律走默认值，也就是旧壳那两处契约。
    """

    def __init__(self, path=None, pipe=None):
        self.path = path or lock_path()
        self.pipe = pipe or pipe_path()
        self._handle = None
        self._owned = False                   # 只删自己建过的那把锁：抢锁失败时锁是别人的
        self._cb = None
        self._stop = threading.Event()

    def acquire(self):
        """True = 我第一个起跑。非 Windows 直接放行（本项目只出 Windows 产物）。"""
        if os.name != "nt":
            return True
        k = _k32()
        h = k.CreateFileW(self.path, GENERIC_READ | GENERIC_WRITE, 0, None,
                          CREATE_NEW, FILE_ATTRIBUTE_NORMAL, None)
        err = ctypes.get_last_error()
        if h != INVALID:
            self._handle = h                      # 新建成功：没人起跑过
        elif err in (ERROR_SHARING_VIOLATION, ERROR_ACCESS_DENIED):
            return False                          # 有进程正独占着这个文件
        elif err in (ERROR_FILE_EXISTS, ERROR_ALREADY_EXISTS):
            # 文件在，但没人持有句柄 = 上次崩溃的残留 → 接管（旧壳 setStaleLockTime(0) 同一意思）
            h = k.CreateFileW(self.path, GENERIC_READ | GENERIC_WRITE, 0, None,
                              OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None)
            if h == INVALID:
                return False                      # 抢的时候被活实例拿走了
            if _held_by_live_other(h):
                k.CloseHandle(h)
                return False
            self._handle = h
        else:
            self._handle = None                   # 目录只读之类的怪错：拦不住就别拦，宁可可多开
            return True
        _write_owner(self._handle)
        self._owned = True
        return True

    def notify_existing(self):
        """告诉已经跑着的那份「有人要你了」，让它把自己弹到前台。"""
        if os.name != "nt":
            return False
        k = _k32()
        # 前台锁定策略会拒非前台进程的 SetForegroundWindow，先把这权利放开给对方
        try:
            _u32().AllowSetForegroundWindow(ASFW_ANY)
        except OSError:
            pass
        for _ in range(2):                        # 服务端在两次连接之间会重建管道，撞上空档就等一拍
            h = k.CreateFileW(self.pipe, GENERIC_WRITE, 0, None,
                              OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None)
            if h != INVALID:
                break
            if not k.WaitNamedPipeW(self.pipe, 300):
                return False
        else:
            return False
        wrote = wintypes.DWORD(0)
        k.WriteFile(h, ACTIVATE, len(ACTIVATE), ctypes.byref(wrote), None)
        k.CloseHandle(h)
        return True

    def serve(self, on_activate):
        """起一个命名管道服务线程：收到任何连接就回调（旧 exe 连过来也算）。"""
        self._cb = on_activate
        if os.name != "nt":
            return
        threading.Thread(target=self._pipe_loop, daemon=True).start()

    def _pipe_loop(self):
        k = _k32()
        path = self.pipe
        while not self._stop.is_set():
            # 必须 duplex：旧壳的 QLocalSocket 按读写方式开管道，只给 INBOUND 它连不上（实测 QT_NO_LISTENER）
            h = k.CreateNamedPipeW(path, PIPE_ACCESS_DUPLEX, 0, 1, 4096, 4096, 0, None)
            if h == INVALID:
                return                            # 名字被别的实例占着：文件锁那头已经互斥了
            ok = k.ConnectNamedPipe(h, None)
            if self._stop.is_set():
                k.CloseHandle(h)
                return
            if ok or ctypes.get_last_error() == ERROR_PIPE_CONNECTED:
                buf = ctypes.create_string_buffer(64)
                got = wintypes.DWORD(0)
                k.ReadFile(h, buf, 64, ctypes.byref(got), None)
                try:
                    self._cb()
                except Exception:
                    pass
            k.CloseHandle(h)                      # 关掉再重建，下一份通知才连得上

    def raise_to_front(self, hwnd):
        """把自己的窗口恢复到前台（管道回调里调，跨线程安全：纯 Win32 调用）。"""
        if os.name != "nt" or not hwnd:
            return
        u = _u32()
        u.ShowWindow(hwnd, SW_RESTORE)
        if not u.SetForegroundWindow(hwnd):
            u.SwitchToThisWindow(hwnd, True)      # 兜底：前台锁定没放开时这个还管用

    def release(self):
        """退出时删锁文件（Qt 的 unlock 也是这个行为，正常退出不留残留）。

        只清自己那把：acquire 失败时锁是别人持有的，删它等于把人家门槛拆了。
        """
        self._stop.set()
        if not self._owned:
            return
        self._owned = False
        if self._handle:
            try:
                _k32().CloseHandle(self._handle)
            except OSError:
                pass
            self._handle = None
        if os.name == "nt":
            try:
                os.remove(self.path)
            except OSError:
                pass
