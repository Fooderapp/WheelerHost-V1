# overlay.py
# Overlay with blurred dominant-side strips (drawn on opposite side), width grows inward with force,
# tunable blur/curve/opacity, toggleable bar/sides, size scale 1..3 anchored at bottom-center, persistence, draggable.

import os, platform
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt

NAVY = QtGui.QColor("#0F2431")
LIME = QtGui.QColor("#D4FF00")

class Overlay(QtWidgets.QWidget):
    layoutChanged = QtCore.Signal()

    def __init__(self, parent=None, screen: QtGui.QScreen | None = None):
        super().__init__(parent)
        self._screen = screen or QtWidgets.QApplication.primaryScreen()
        # Use different flags on macOS to improve stacking across Spaces/fullscreen
        if platform.system() == "Darwin":
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint | Qt.Window)
            try:
                self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
            except Exception:
                pass
        else:
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # toggles + scale
        self._show_bar = True
        self._show_sides = False  # default OFF now
        self._scale = 1.7  # 1..3 via UI

        # blur params
        self._blur_amount = 0.70     # 0..2 (mapped to 2..20 downscale)
        self._curve_gamma = 0.80     # 0.2..4.0
        self._alpha_strength = 0.60  # 0..1.5
        self._blur_min, self._blur_max = 2, 20

        # input (click-through when main window hidden)
        self._input_enabled = False
        self._drag_side = None
        self._drag_dx = 0
        self._drag_bar = False
        self._drag_bar_offset = QtCore.QPointF(0,0)

        # telemetry smoothing
        self._sx = 0.0
        self._sg = 0.0
        self._g_sign = 0
        self._a_pos = 0.25
        self._a_g   = 0.22

        # base sizes
        self._side_w_base = 110.0
        self._bar_w_base  = 354.54
        self._bar_h_base  = 25.18
        self._ind_w_base  = 16.0
        self._ind_h_base  = 30.0
        self._recalc_sizes()

        # positions
        self._left_x = 0
        self._right_x = 0
        self._bar_pos = QtCore.QPointF(0,0)

        # assets
        self._bar_svg = self._load_svg("BAR.svg")
        self._bar_pix = self._load_pix(["BAR.png","BAR.jpeg","bar.png","bar.jpeg"]) if not self._bar_svg else None
        self._ind_svg = self._load_svg("INDICATOR.svg")
        self._ind_pix = self._load_pix(["INDICATOR.png","INDICATOR.jpeg","indicator.png","indicator.jpeg"]) if not self._ind_svg else None

        self._apply_click_through()
        self._apply_macos_all_spaces()   # mac: keep overlay on all Spaces/fullscreen (best-effort)
        self._apply_macos_window_level() # mac: raise level (best-effort)
        self._apply_windows_topmost()    # win: enforce HWND_TOPMOST
        self._apply_screen_geometry()

        # repaint tick
        self._timer = QtCore.QTimer(self); self._timer.timeout.connect(self.update); self._timer.start(33)
        # Track geometry only for this overlay's screen
        if self._screen is not None:
            try:
                self._screen.geometryChanged.connect(self._apply_screen_geometry)
            except Exception:
                pass

        # Maintain topmost + all-spaces periodically (handles Space switches/fullscreen changes)
        if platform.system() == "Darwin":
            self._ontop_timer = QtCore.QTimer(self)
            self._ontop_timer.setInterval(1500)
            self._ontop_timer.timeout.connect(self._maintain_top)
            self._ontop_timer.start()
        elif platform.system() == "Windows":
            self._ontop_timer = QtCore.QTimer(self)
            self._ontop_timer.setInterval(2000)
            self._ontop_timer.timeout.connect(self._apply_windows_topmost)
            self._ontop_timer.start()

        self.show()

    # ---------- macOS: keep on all spaces / fullscreen ----------
    def _apply_macos_all_spaces(self):
        try:
            if platform.system() != "Darwin":
                return
            # Use Objective‑C runtime via ctypes to set NSWindow.collectionBehavior
            from ctypes import util, cdll, c_void_p, c_ulong, c_char_p
            libobjc_path = util.find_library('objc')
            if not libobjc_path:
                return
            objc = cdll.LoadLibrary(libobjc_path)

            # Selectors
            sel_getUid = objc.sel_registerName; sel_getUid.argtypes = [c_char_p]; sel_getUid.restype = c_void_p
            msgSend = objc.objc_msgSend

            # Get NSWindow* from NSView* (winId is NSView*)
            view = c_void_p(int(self.winId()))
            sel_window = sel_getUid(b"window")
            msgSend.restype = c_void_p
            msgSend.argtypes = [c_void_p, c_void_p]
            nswindow = msgSend(view, sel_window)
            if not nswindow:
                return

            # Flags (bit values per AppKit)
            NSWindowCollectionBehaviorCanJoinAllSpaces   = c_ulong(1 << 0)
            NSWindowCollectionBehaviorMoveToActiveSpace  = c_ulong(1 << 1)
            NSWindowCollectionBehaviorTransient          = c_ulong(1 << 3)
            NSWindowCollectionBehaviorStationary         = c_ulong(1 << 4)
            NSWindowCollectionBehaviorFullScreenAuxiliary= c_ulong(1 << 8)
            
            # Desired: join all spaces + stationary + fullscreen auxiliary (no move-to-active, no transient)
            desired = (NSWindowCollectionBehaviorCanJoinAllSpaces.value |
                       NSWindowCollectionBehaviorStationary.value |
                       NSWindowCollectionBehaviorFullScreenAuxiliary.value)

            # Apply directly (do not OR with current to avoid inheriting MoveToActiveSpace)
            sel_set = sel_getUid(b"setCollectionBehavior:")
            msgSend.restype = None
            msgSend.argtypes = [c_void_p, c_void_p, c_ulong]
            msgSend(nswindow, sel_set, c_ulong(desired))
        except Exception:
            # Best‑effort; ignore if PyObjC/Cocoa not available
            pass

    # ---------- macOS: raise overlay level ----------
    def _apply_macos_window_level(self):
        try:
            if platform.system() != "Darwin":
                return
            from ctypes import util, cdll, c_void_p, c_int, c_char_p
            libobjc_path = util.find_library('objc')
            if not libobjc_path:
                return
            objc = cdll.LoadLibrary(libobjc_path)
            sel_getUid = objc.sel_registerName; sel_getUid.argtypes = [c_char_p]; sel_getUid.restype = c_void_p
            msgSend = objc.objc_msgSend

            view = c_void_p(int(self.winId()))
            sel_window = sel_getUid(b"window")
            msgSend.restype = c_void_p
            msgSend.argtypes = [c_void_p, c_void_p]
            nswindow = msgSend(view, sel_window)
            if not nswindow:
                return

            # Raise higher so it overlays more apps and fullscreens during testing
            # Use a very high level (~2000) similar to CGShieldingWindowLevel
            HighOverlayLevel = 2000
            sel_setLevel = sel_getUid(b"setLevel:")
            msgSend.restype = None
            msgSend.argtypes = [c_void_p, c_void_p, c_int]
            msgSend(nswindow, sel_setLevel, c_int(HighOverlayLevel))

            # Bring to front regardless
            sel_orderFrontRegardless = sel_getUid(b"orderFrontRegardless")
            msgSend.restype = None
            msgSend.argtypes = [c_void_p, c_void_p]
            msgSend(nswindow, sel_orderFrontRegardless)
        except Exception:
            pass

    def _maintain_top(self):
        # Reapply flags and bring to front; helps when user switches Spaces/fullscreen
        try:
            self._apply_macos_all_spaces()
            self._apply_macos_window_level()
        except Exception:
            pass

    # ---------- Windows: enforce topmost ----------
    def _apply_windows_topmost(self):
        if platform.system() != "Windows":
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            SetWindowPos = user32.SetWindowPos
            SetWindowPos.restype = wintypes.BOOL
            SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]

            HWND_TOPMOST = wintypes.HWND(-1)
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE

            hwnd = wintypes.HWND(int(self.winId()))
            SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        except Exception:
            pass

    # ---------- assets ----------
    def _load_svg(self, name):
        try:
            from PySide6 import QtSvg
            for p in [os.path.join(os.path.dirname(__file__), name), name]:
                if os.path.isfile(p):
                    r = QtSvg.QSvgRenderer(p)
                    if r.isValid(): return r
        except Exception:
            pass
        return None

    def _load_pix(self, names):
        for n in names:
            for p in [os.path.join(os.path.dirname(__file__), n), n]:
                if os.path.isfile(p):
                    pm = QtGui.QPixmap(p)
                    if not pm.isNull(): return pm
        return None

    # ---------- public controls ----------
    def set_show_bar(self, on: bool):
        self._show_bar = bool(on); self.layoutChanged.emit(); self.update()

    def set_show_sides(self, on: bool):
        self._show_sides = bool(on); self.layoutChanged.emit(); self.update()

    def set_scale(self, scale: float):
        scale = float(max(1.0, min(3.0, scale)))
        if abs(scale - self._scale) < 1e-6: return
        prev_w, prev_h = self._bar_w, self._bar_h
        prev_cx = self._bar_pos.x() + prev_w * 0.5
        prev_by = self._bar_pos.y() + prev_h

        self._scale = scale
        self._recalc_sizes()

        new_x = prev_cx - self._bar_w * 0.5
        new_y = prev_by - self._bar_h
        self._bar_pos = QtCore.QPointF(new_x, new_y)

        self._apply_screen_geometry(reuse_positions=True)
        self.layoutChanged.emit(); self.update()

    def set_side_width_base(self, px: float):
        self._side_w_base = float(max(40.0, min(600.0, px)))
        self._recalc_sizes()
        self._apply_screen_geometry(reuse_positions=True)
        self.layoutChanged.emit(); self.update()

    def set_blur_amount(self, amt: float):
        self._blur_amount = float(max(0.0, min(2.0, amt)))
        self.layoutChanged.emit(); self.update()

    def set_curve_gamma(self, g: float):
        self._curve_gamma = float(max(0.2, min(4.0, g)))
        self.layoutChanged.emit(); self.update()

    def set_alpha_strength(self, a: float):
        self._alpha_strength = float(max(0.0, min(1.5, a)))
        self.layoutChanged.emit(); self.update()

    # ---------- persistence ----------
    def get_state(self) -> dict:
        return {
            "show_bar": self._show_bar,
            "show_sides": self._show_sides,
            "scale": self._scale,
            "side_w_base": self._side_w_base,
            "blur_amount": self._blur_amount,
            "curve_gamma": self._curve_gamma,
            "alpha_strength": self._alpha_strength,
            "bar_pos": [float(self._bar_pos.x()), float(self._bar_pos.y())],
            "left_x": float(self._left_x),
            "right_x": float(self._right_x),
        }

    def apply_state(self, st: dict):
        if not isinstance(st, dict): return
        self._show_bar     = bool(st.get("show_bar", self._show_bar))
        self._show_sides   = bool(st.get("show_sides", self._show_sides))
        self._scale        = float(st.get("scale", self._scale))
        self._side_w_base  = float(st.get("side_w_base", self._side_w_base))
        self._blur_amount  = float(st.get("blur_amount", self._blur_amount))
        self._curve_gamma  = float(st.get("curve_gamma", self._curve_gamma))
        self._alpha_strength = float(st.get("alpha_strength", self._alpha_strength))
        self._recalc_sizes()
        self._apply_screen_geometry()
        if "bar_pos" in st and isinstance(st["bar_pos"], (list, tuple)) and len(st["bar_pos"])==2:
            x,y = float(st["bar_pos"][0]), float(st["bar_pos"][1])
            self._bar_pos = QtCore.QPointF(x,y)
        if "left_x" in st:  self._left_x  = float(st["left_x"])
        if "right_x" in st: self._right_x = float(st["right_x"])
        self._apply_screen_geometry(reuse_positions=True)
        self.layoutChanged.emit(); self.update()

    def reset_all(self):
        self._show_bar = True
        self._show_sides = False
        self._scale = 1.7
        self._side_w_base = 110.0
        self._blur_amount = 0.70
        self._curve_gamma = 0.80
        self._alpha_strength = 0.60
        self.reset_layout()
        self.layoutChanged.emit(); self.update()

    # ---------- input toggle ----------
    def set_input_enabled(self, en: bool):
        self._input_enabled = bool(en)
        # Qt must also accept mouse when editing
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not self._input_enabled)
        self._apply_click_through()

    def _apply_click_through(self):
        # Qt-side toggle (cross-platform)
        try:
            self.setWindowFlag(Qt.WindowTransparentForInput, not self._input_enabled)
        except Exception:
            pass
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not self._input_enabled)
        self.show()

        # Native Windows toggle using SetWindowLongPtrW (64-bit safe)
        if platform.system() == "Windows":
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32

                GWL_EXSTYLE = -20
                WS_EX_LAYERED = 0x00080000
                WS_EX_TRANSPARENT = 0x00000020

                hwnd = int(self.winId())

                GetWindowLongPtrW = getattr(user32, "GetWindowLongPtrW")
                SetWindowLongPtrW = getattr(user32, "SetWindowLongPtrW")

                GetWindowLongPtrW.restype = ctypes.c_longlong
                GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
                SetWindowLongPtrW.restype = ctypes.c_longlong
                SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]

                ex = GetWindowLongPtrW(hwnd, GWL_EXSTYLE) or 0
                ex |= WS_EX_LAYERED
                if not self._input_enabled:
                    ex |= WS_EX_TRANSPARENT   # click-through
                else:
                    ex &= ~WS_EX_TRANSPARENT  # accept mouse
                SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
            except Exception:
                pass

    # ---------- geometry ----------
    def _recalc_sizes(self):
        s = self._scale
        self._side_w = self._side_w_base * s
        self._bar_w  = self._bar_w_base  * s
        self._bar_h  = self._bar_h_base  * s
        self._ind_w  = self._ind_w_base  * s
        self._ind_h  = self._ind_h_base  * s

    def _apply_screen_geometry(self, reuse_positions=False):
        scr = self._screen or QtWidgets.QApplication.primaryScreen()
        if not scr:
            return
        g = scr.geometry()
        self.setGeometry(g)
        if not reuse_positions:
            self._left_x = 0
            self._right_x = max(0, g.width() - self._side_w)
            self._bar_pos = QtCore.QPointF( (g.width()-self._bar_w)/2.0, g.height() - self._bar_h - 14.0 )
        else:
            self._left_x  = max(0, min(self._left_x,  g.width()  - self._side_w))
            self._right_x = max(0, min(self._right_x, g.width()  - self._side_w))
            bx = max(0, min(self._bar_pos.x(), g.width()  - self._bar_w))
            by = max(0, min(self._bar_pos.y(), g.height() - self._bar_h))
            self._bar_pos = QtCore.QPointF(bx, by)

    def reset_layout(self):
        self._sx = 0.0; self._sg = 0.0; self._g_sign = 0
        self._apply_screen_geometry(reuse_positions=False)

    # ---------- telemetry ----------
    def set_telemetry(self, steering_x: float, latG: float):
        sx_raw = max(-1.0, min(1.0, float(steering_x)))
        self._sx += self._a_pos * (sx_raw - self._sx)

        # flip latG: left turn → left force negative; right turn → positive
        g_signed = -float(latG)
        g_sign = -1 if g_signed < 0 else (1 if g_signed > 0 else 0)

        steer_sign = -1 if self._sx < -0.12 else (1 if self._sx > 0.12 else 0)
        if steer_sign != 0 and g_sign != 0 and (g_sign != steer_sign) and (abs(self._sx) >= 0.18):
            self._g_sign = steer_sign
        else:
            self._g_sign = g_sign if g_sign != 0 else steer_sign

        m = max(0.0, min(1.6, abs(g_signed))) / 1.2
        m = max(0.0, min(1.0, m))
        sm = m*m*(3 - 2*m)
        eased = sm ** self._curve_gamma
        if self._g_sign == steer_sign and g_sign != steer_sign:
            eased = max(eased, min(0.55, abs(self._sx)))
        self._sg += self._a_g * (eased - self._sg)

    # ---------- blur helper ----------
    def _draw_blur_strip(self, painter: QtGui.QPainter, rect: QtCore.QRectF, left_to_right: bool, intensity: float):
        screen = QtWidgets.QApplication.primaryScreen()
        if not screen: return
        full = screen.grabWindow(0)
        if full.isNull(): return

        crop = full.copy(int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height()))
        if crop.isNull(): return

        amt = max(0.0, min(2.0, self._blur_amount)) * max(0.0, min(1.0, intensity))
        factor = int(self._blur_min + (self._blur_max - self._blur_min) * min(1.0, amt))
        factor = max(self._blur_min, min(self._blur_max, factor))

        small_w = max(1, crop.width() // factor)
        small_h = max(1, crop.height() // factor)
        small = crop.scaled(small_w, small_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        blurred = small.scaled(crop.width(), crop.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        grad = QtGui.QLinearGradient(
            rect.right() if left_to_right else rect.left(), rect.top(),
            rect.left()  if left_to_right else rect.right(), rect.top()
        )
        alpha = self._alpha_strength * max(0.0, min(1.0, intensity))
        c0 = QtGui.QColor(255,255,255, 0)
        c1 = QtGui.QColor(255,255,255, int(alpha * 255))
        grad.setColorAt(0.0, c0); grad.setColorAt(1.0, c1)

        painter.save()
        painter.drawPixmap(rect, blurred, QtCore.QRectF(0,0,blurred.width(), blurred.height()))
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_DestinationIn)
        painter.fillRect(rect, QtGui.QBrush(grad))
        painter.restore()

    # ---------- painting ----------
    def paintEvent(self, ev):
        p = QtGui.QPainter(self); p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        H = self.height()

        # dominant side only; draw on opposite side; width scales with force (grows inward)
        if self._show_sides:
            a = max(0.0, min(1.0, self._sg))
            if a > 0.02 and self._g_sign != 0:
                active_left = (self._g_sign > 0)  # flipped: right force -> left strip
                base_w = self._side_w
                scale_w = 0.60 + 1.80 * a
                w_dyn = max(20.0, base_w * scale_w)
                x0 = self._left_x if active_left else max(0.0, self.width() - w_dyn)  # pinned to edge
                rect = QtCore.QRectF(x0, 0, w_dyn, H)
                self._draw_blur_strip(p, rect, left_to_right=active_left, intensity=a)

        # bottom bar + indicator
        if self._show_bar:
            bar_rect = QtCore.QRectF(self._bar_pos.x(), self._bar_pos.y(), self._bar_w, self._bar_h)
            if self._bar_svg:
                self._bar_svg.render(p, bar_rect)
            elif self._bar_pix and not self._bar_pix.isNull():
                p.drawPixmap(bar_rect, self._bar_pix, QtCore.QRectF(0,0,self._bar_pix.width(), self._bar_pix.height()))
            else:
                path = QtGui.QPainterPath()
                path.addRoundedRect(bar_rect, bar_rect.height()/2, bar_rect.height()/2)
                p.fillPath(path, NAVY.darker(115))

            t = max(0.0, min(1.0, self._sx*0.5 + 0.5))
            ind_w, ind_h = self._ind_w, self._ind_h
            ind_x = bar_rect.x() + (bar_rect.width() - ind_w) * t
            ind_y = bar_rect.y() + (bar_rect.height() - ind_h)  # bottom align
            ind_rect = QtCore.QRectF(ind_x, ind_y, ind_w, ind_h)
            if self._ind_svg:
                self._ind_svg.render(p, ind_rect)
            elif self._ind_pix and not self._ind_pix.isNull():
                p.drawPixmap(ind_rect, self._ind_pix, QtCore.QRectF(0,0,self._ind_pix.width(), self._ind_pix.height()))
            else:
                rp = QtGui.QPainterPath()
                rp.addRoundedRect(ind_rect, ind_h/2, ind_h/2)
                p.fillPath(rp, LIME)

        p.end()

    # ---------- hit/drag ----------
    def _side_hit(self, pos):
        if not self._input_enabled: return None
        rL = QtCore.QRectF(self._left_x, 0, self._side_w, self.height())
        rR = QtCore.QRectF(self.width()-self._side_w, 0, self._side_w, self.height())
        if rL.contains(pos): return "L"
        if rR.contains(pos): return "R"
        return None

    def _bar_hit(self, pos):
        if not self._input_enabled or not self._show_bar: return False
        r = QtCore.QRectF(self._bar_pos.x(), self._bar_pos.y(), self._bar_w, self._bar_h)
        return r.contains(pos)

    def mousePressEvent(self, e):
        if not self._input_enabled: return
        pos = e.position()
        s = self._side_hit(pos)
        if s:
            self._drag_side = s
            self._drag_dx = pos.x() - (self._left_x if s=="L" else self._right_x)
            return
        if self._bar_hit(pos):
            self._drag_bar = True
            self._drag_bar_offset = QtCore.QPointF(pos.x()-self._bar_pos.x(), pos.y()-self._bar_pos.y())

    def mouseMoveEvent(self, e):
        if not self._input_enabled: return
        if self._drag_side:
            x = int(e.position().x() - self._drag_dx)
            x = max(0, min(self.width()-self._side_w, x))
            if self._drag_side=="L": self._left_x = x
            else: self._right_x = x
            self.update()
        elif self._drag_bar:
            nx = e.position().x() - self._drag_bar_offset.x()
            ny = e.position().y() - self._drag_bar_offset.y()
            nx = max(0, min(self.width()-self._bar_w, nx))
            ny = max(0, min(self.height()-self._bar_h, ny))
            self._bar_pos = QtCore.QPointF(nx, ny)
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag_side or self._drag_bar:
            self.layoutChanged.emit()
        self._drag_side = None
        self._drag_bar = False

    # ---------- show/hide ----------
    def set_overlay_visible(self, vis: bool):
        (self.show if vis else self.hide)()
