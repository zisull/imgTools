# -*- coding: utf-8 -*-
"""无框窗口的原生守卫 + 六个窗口方法（pywebview 6.x / Windows WebView2）。

用法
----
1) 窗口建好之后挂守卫（**只能挂在 shown 上**，且 shown 会重复触发）：
       webview.events('pywebview:windowloaded')  →  or  window.events.shown += lambda w: install_guard(w)
2) 把 WindowCtl 混进 js_api 宿主类，宿主提供 `self._window`（webview.Window）与一个 `_log(text)`。
3) 前端调 win_geo / win_move / win_set / win_min / win_max / win_close（见 win.js）。
4) 关闭只走 win_close → window.destroy()；**on_closing 处理器里不要有 return**，
   pywebview 6.2.1 会把 return False 当成「取消关闭」，症状是点关闭毫无反应。

量纲：几何全部逻辑像素（pywebview 内部再乘 DPI 缩放）。别在这里乘缩放因子。
提取自跑通的实现（webui/app.py:1739-1945），改动处只做了去项目化。
"""
import ctypes
from ctypes import wintypes

keepalive = []                                 # ctypes 回调必须自己留着引用


# ---------------------------------------------------------------- 原生守卫
def install_guard(window, once=[True]):
    """把窗口钳进「所在显示器工作区」：任何移动/缩放都过 WM_WINDOWPOSCHANGING。

    frameless 之后系统那套「拖出屏幕会弹回、最大化让出任务栏」的规则全没了，
    必须在这里补；前端不要再自己夹坐标，两边一起夹会打架。
    """
    if not once[0]:
        return
    once[0] = False

    # 独立 WinDLL 实例：ctypes.windll.user32 是全进程共享单例，
    # 在它上面设 argtypes 会把 pywebview 自己读屏幕信息的调用一起带坏。
    user32 = ctypes.WinDLL("user32")
    hwnd = window.native.Handle.ToInt32()

    class WINDOWPOS(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("hwnd_insert_after", wintypes.HWND),
                    ("x", ctypes.c_int), ("y", ctypes.c_int),
                    ("cx", ctypes.c_int), ("cy", ctypes.c_int),
                    ("flags", wintypes.UINT)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cb_size", wintypes.UINT), ("rc_monitor", wintypes.RECT),
                    ("rc_work", wintypes.RECT), ("dw_flags", wintypes.DWORD)]

    WM_WINDOWPOSCHANGING = 0x0046
    SWP_NOSIZE, SWP_NOMOVE = 0x0001, 0x0002
    MONITOR_DEFAULTTONEAREST = 0x00000002

    if hasattr(user32, "SetWindowLongPtrW"):
        get_long, set_long = user32.GetWindowLongPtrW, user32.SetWindowLongPtrW
    else:
        get_long, set_long = user32.GetWindowLongW, user32.SetWindowLongW
    get_long.restype = ctypes.c_void_p
    get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
    set_long.restype = ctypes.c_void_p
    set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    wndproc_t = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, wintypes.UINT,
                                  ctypes.c_void_p, ctypes.c_void_p)
    call_proc = user32.CallWindowProcW
    call_proc.restype = ctypes.c_ssize_t
    call_proc.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT,
                         ctypes.c_void_p, ctypes.c_void_p]
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]

    orig = get_long(hwnd, -4)                      # GWLP_WNDPROC
    rect, mi = wintypes.RECT(), MONITORINFO()
    mi.cb_size = ctypes.sizeof(MONITORINFO)

    def wnd_proc(h, msg, wparam, lparam):
        try:
            if msg == WM_WINDOWPOSCHANGING and lparam:
                wp = ctypes.cast(lparam, ctypes.POINTER(WINDOWPOS))[0]
                if (wp.flags & (SWP_NOMOVE | SWP_NOSIZE)) != (SWP_NOMOVE | SWP_NOSIZE):
                    user32.GetWindowRect(h, ctypes.byref(rect))
                    w = rect.right - rect.left if wp.flags & SWP_NOSIZE else wp.cx
                    hh = rect.bottom - rect.top if wp.flags & SWP_NOSIZE else wp.cy
                    mon = user32.MonitorFromWindow(h, MONITOR_DEFAULTTONEAREST)
                    if mon and user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
                        wa = mi.rc_work
                        if wp.flags & SWP_NOMOVE:
                            wp.x, wp.y = rect.left, rect.top
                        # 尺寸也一起钳：否则自绘「最大化」连任务栏一起盖住
                        if not (wp.flags & SWP_NOSIZE):
                            wp.cx = min(wp.cx, wa.right - wa.left)
                            wp.cy = min(wp.cy, wa.bottom - wa.top)
                        wp.x = (wa.left if w >= wa.right - wa.left
                                else min(max(wp.x, wa.left), wa.right - w))
                        wp.y = (wa.top if hh >= wa.bottom - wa.top
                                else min(max(wp.y, wa.top), wa.bottom - hh))
        except Exception:
            pass                                   # 钩子里绝不能抛：抛了窗口就再也不动
        return call_proc(orig, h, msg, wparam, lparam)

    proc = wndproc_t(wnd_proc)
    set_long(hwnd, -4, ctypes.cast(proc, ctypes.c_void_p))
    keepalive.append(proc)


# ---------------------------------------------------------------- 窗口方法（暴露给 JS）
class WindowCtl:
    """混入 js_api 宿主。宿主需有 self._window（webview.Window）与 self._log(text)。"""

    MIN_W, MIN_H = 980, 620                        # 改成你的最小尺寸（逻辑像素）
    _maxed = False                                 # Window 没有可读的 maximized，状态自己记

    def win_geo(self):
        """按下瞬间取一次几何，拖动过程只算增量。maxed 用于前端决定要不要开始拖。"""
        w = self._window
        if w is None:
            return None
        return {"x": int(w.x or 0), "y": int(w.y or 0),
                "w": int(w.width or 0), "h": int(w.height or 0),
                "maxed": self._maxed, "min_w": self.MIN_W, "min_h": self.MIN_H}

    def win_move(self, x=0, y=0):
        w = self._window
        if w is None or self._maxed:               # 最大化时不拖：先点还原再拖
            return {"ok": False}
        try:
            w.move(int(x), int(y))
        except Exception as e:
            self._log("⚠️ 窗口移动失败：%s" % e)
            return {"ok": False, "msg": str(e)}
        return {"ok": True}

    def win_set(self, x=None, y=None, width=0, height=0):
        """缩放：前端已按「对角不动」算好新几何，这里只落给窗口（先定尺寸再定位）。"""
        w = self._window
        if w is None or self._maxed:
            return {"ok": False}
        try:
            if width and height:
                w.resize(max(int(width), self.MIN_W), max(int(height), self.MIN_H))
            if x is not None and y is not None:
                w.move(int(x), int(y))
        except Exception as e:
            self._log("⚠️ 窗口缩放失败：%s" % e)
            return {"ok": False, "msg": str(e)}
        return {"ok": True}

    def win_min(self):
        w = self._window
        if w is None:
            return {"ok": False}
        try:
            w.minimize()
        except Exception as e:
            self._log("⚠️ 最小化失败：%s" % e)
            return {"ok": False, "msg": str(e)}
        return {"ok": True}

    def win_max(self, on=None):
        """最大化 / 还原。MaximizedBounds 默认取工作区，所以不会盖任务栏（守卫也兜一层）。"""
        w = self._window
        if w is None:
            return {"ok": False}
        want = (not self._maxed) if on is None else bool(on)
        try:
            (w.maximize if want else w.restore)()
        except Exception as e:
            self._log("⚠️ 最大化失败：%s" % e)
            return {"ok": False, "msg": str(e)}
        self._maxed = want
        return {"ok": True, "maxed": want}

    def win_close(self):
        """关闭：走 destroy → 原生 FormClosing → on_closing 收尾，只此一条路径。"""
        w = self._window
        if w is None:
            return {"ok": False}
        try:
            w.destroy()
        except Exception as e:
            self._log("⚠️ 关闭失败：%s" % e)
            return {"ok": False, "msg": str(e)}
        return {"ok": True}
