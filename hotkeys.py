# hotkeys.py
# Global F9/F11 hotkeys for Windows using QAbstractNativeEventFilter (works when unfocused).
import ctypes
from ctypes import wintypes
from PySide6 import QtCore

WM_HOTKEY      = 0x0312
MOD_NOREPEAT   = 0x4000
VK_F9, VK_F11 = 0x78, 0x7A
_user32 = ctypes.windll.user32

class _NativeFilter(QtCore.QAbstractNativeEventFilter):
    def __init__(self, sig_emit):
        super().__init__()
        self._emit = sig_emit
    def nativeEventFilter(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == WM_HOTKEY:
                hk_id = int(msg.wParam)
                if hk_id in (1001, 1003):
                    self._emit(hk_id)
                    return True, 0
        return False, 0

class WinHotkeys(QtCore.QObject):
    pressed = QtCore.Signal(int)  # 1001=F9, 1003=F11
    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter = _NativeFilter(self.pressed.emit)
        self._registered = False
    def install(self):
        app = QtCore.QCoreApplication.instance()
        if app: app.installNativeEventFilter(self._filter)
    def remove(self):
        app = QtCore.QCoreApplication.instance()
        if app: app.removeNativeEventFilter(self._filter)
    def register(self):
        if self._registered: return
        for hk_id, vk in ((1001, VK_F9), (1003, VK_F11)):
            ok = _user32.RegisterHotKey(None, hk_id, MOD_NOREPEAT, vk)
            if not ok: _user32.RegisterHotKey(None, hk_id, 0, vk)
        self._registered = True
    def unregister(self):
        if not self._registered: return
        for hk_id in (1001, 1003):
            try: _user32.UnregisterHotKey(None, hk_id)
            except Exception: pass
        self._registered = False
