# wheeler_windows_ui.py
# Windows UI + UDP server + multi-client ViGEm Xbox 360 pads with anti-flap states
# + ALWAYS-ON-TOP CLICK-THROUGH OVERLAY (steering pill + G-force side glow)
# + GLOBAL hotkeys: F9/F10/F11, draggable side bars AND draggable bottom bar
# pip install PySide6 PySide6-Addons qrcode pillow vgamepad

import sys, io, os, json, socket, threading, time, datetime, platform, struct, math, traceback
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt

import qrcode
from PIL import Image

# ---------- Logging ----------
class Logger(QtCore.QObject):
    line = QtCore.Signal(str)
    def __init__(self):
        super().__init__()
        self._buf = []
    def log(self, s: str):
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
        line = f"[{ts}] {s}"
        print(line, flush=True)
        self._buf.append(line)
        self.line.emit(line + "\n")
    def clear(self):
        self._buf.clear()
        self.line.emit("")

LOG = Logger()

def _install_excepthook():
    def _hook(etype, value, tb):
        LOG.log("🔥 Uncaught exception at top-level:")
        for line in traceback.format_exception(etype, value, tb):
            LOG.log(line.rstrip())
    sys.excepthook = _hook
_install_excepthook()

# ---------- Network utils ----------
def list_ipv4() -> List[str]:
    ips = []
    hostname = socket.gethostname()
    try:
        for info in socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP):
            addr = info[4][0]
            if "." in addr and not addr.startswith("127."):
                if addr not in ips: ips.append(addr)
    except Exception:
        pass
    for host in ["localhost"]:
        try:
            addr = socket.gethostbyname(host)
            if "." in addr and not addr.startswith("127.") and addr not in ips:
                ips.append(addr)
        except Exception:
            pass
    return ips or ["127.0.0.1"]

# ---------- Settings ----------
@dataclass
class Settings:
    invert: bool = True
    gain: float = 1.0
    deadzone: float = 0.06
    expo: float = 0.30
    max_deg: float = 40.0  # UI display only

SETTINGS = Settings()

# ---------- ViGEm Gamepad wrapper ----------
class XGamepad:
    def __init__(self):
        self.available = False
        self.pad = None
        self.vg = None
        self.BTN = {}
        try:
            import vgamepad as vg
            self.vg = vg
            self.pad = vg.VX360Gamepad()
            b = vg.XUSB_BUTTON
            def pick(*names):
                for n in names:
                    if hasattr(b, n): return getattr(b, n)
                return None
            self.BTN = {
                "A": pick("A", "XUSB_GAMEPAD_A"),
                "B": pick("B", "XUSB_GAMEPAD_B"),
                "X": pick("X", "XUSB_GAMEPAD_X"),
                "Y": pick("Y", "XUSB_GAMEPAD_Y"),
                "LB": pick("LEFT_SHOULDER", "XUSB_GAMEPAD_LEFT_SHOULDER"),
                "RB": pick("RIGHT_SHOULDER", "XUSB_GAMEPAD_RIGHT_SHOULDER"),
                "START": pick("START", "XUSB_GAMEPAD_START"),
                "BACK": pick("BACK", "XUSB_GAMEPAD_BACK"),
            }
            self.available = True
        except Exception as e:
            LOG.log(f"⚠️ ViGEm unavailable: {e}")

    @staticmethod
    def _clamp(v, lo, hi):
        return lo if v < lo else hi if v > hi else v

    def update(
        self,
        steering_x: float,
        throttle: float,
        brake: float,
        btn_mask: int,
        rumbleL: float = 0.0,
        rumbleR: float = 0.0,
        rsx: float = 0.0,
        rsy: float = 0.0,
    ):
        if not self.available:
            return
        try:
            use_lx = rsx if abs(rsx) > 1e-6 else steering_x
            use_ly = -rsy  # invert Y for Dirt 5

            lx = int(self._clamp(use_lx, -1.0, 1.0) * 32767)
            ly = int(self._clamp(use_ly, -1.0, 1.0) * 32767)

            rt = int(self._clamp(throttle, 0.0, 1.0) * 255)
            lt = int(self._clamp(brake,    0.0, 1.0) * 255)
            def on(bit): return (btn_mask & (1 << bit)) != 0

            self.pad.reset()
            self.pad.left_joystick(x_value=lx, y_value=ly)
            self.pad.right_trigger(value=rt)
            self.pad.left_trigger(value=lt)

            if on(0) and self.BTN.get("A"):     self.pad.press_button(button=self.BTN["A"])
            if on(1) and self.BTN.get("B"):     self.pad.press_button(button=self.BTN["B"])
            if on(2) and self.BTN.get("X"):     self.pad.press_button(button=self.BTN["X"])
            if on(3) and self.BTN.get("Y"):     self.pad.press_button(button=self.BTN["Y"])
            if on(4) and self.BTN.get("LB"):    self.pad.press_button(button=self.BTN["LB"])
            if on(5) and self.BTN.get("RB"):    self.pad.press_button(button=self.BTN["RB"])
            if on(6) and self.BTN.get("START"): self.pad.press_button(button=self.BTN["START"])
            if on(7) and self.BTN.get("BACK"):  self.pad.press_button(button=self.BTN["BACK"])

            try:
                self.pad.set_vibration(
                    int(self._clamp(rumbleL, 0.0, 1.0) * 65535),
                    int(self._clamp(rumbleR, 0.0, 1.0) * 65535)
                )
            except Exception:
                pass
            self.pad.update()
        except Exception as e:
            LOG.log(f"⚠️ ViGEm send error: {e}")

    def neutral(self):
        self.update(0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0)

    def close(self):
        try:
            if self.available and self.pad:
                self.neutral()
        except Exception:
            pass

# ---------- Per-client state ----------
@dataclass
class ClientState:
    pad: XGamepad
    last_rx_ms: int
    addr: Tuple[str, int]
    name: str = ""
    state: str = "active"  # "active" | "idle" | "disconnected"
    neutral_sent: bool = False
    state_changed_ms: int = 0

# ---------- UDP Server (Qt object) ----------
class UDPServer(QtCore.QObject):
    # telemetry includes rumbleL, rumbleR (we keep emitting for future, but overlay uses latG)
    telemetry = QtCore.Signal(float, float, float, float, object, float, float)
    buttons   = QtCore.Signal(dict)
    tuning    = QtCore.Signal(dict)
    clients_changed = QtCore.Signal(list)

    def __init__(self, port: int):
        super().__init__()
        self.port = port
        self._th: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._clients: Dict[Tuple[str,int], ClientState] = {}
        self._last_active: Optional[Tuple[str,int]] = None
        self._idle_after_ms    = 900
        self._destroy_after_ms = 60_000

    def start(self):
        if self._th and self._th.is_alive():
            return
        self._stop.clear()
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()
        LOG.log(f"🟢 UDP server ready on :{self.port}")

    def stop(self):
        self._stop.set()
        LOG.log("🛑 UDP server stopping...")

    # ---- input shaping ----
    def _apply_filters(self, x: float) -> float:
        sgn = -1.0 if SETTINGS.invert else 1.0
        x = x * sgn * SETTINGS.gain
        dz = max(0.0, min(0.3, SETTINGS.deadzone))
        if abs(x) < dz:
            x = 0.0
        else:
            s = -1.0 if x < 0 else 1.0
            x = s * ((abs(x) - dz) / (1.0 - dz))
        e = max(0.0, min(1.0, SETTINGS.expo))
        x = (1.0 - e) * x + e * (x * x * x)
        return max(-1.0, min(1.0, x))

    def _qt_safe_seq(self, x):
        try:
            xi = int(x)
        except Exception:
            return str(x)
        if -2147483648 <= xi <= 2147483647:
            return xi
        return str(xi)

    # ---- remote tuning ----
    def _maybe_apply_remote_tuning(self, obj: dict) -> Optional[dict]:
        changed = {}
        if obj.get("type") == "finetune" and isinstance(obj.get("params"), dict):
            p = obj["params"]
            mapping = {
                "gain": ("gain", float),
                "deadzone": ("deadzone", float),
                "expo": ("expo", float),
                "maxAngle": ("max_deg", float),
                "invert": ("invert", bool),
            }
            for k_src, (k_dst, cast) in mapping.items():
                if k_src in p:
                    try:
                        val = cast(p[k_src])
                        setattr(SETTINGS, k_dst, val)
                        changed[k_dst] = val
                    except Exception:
                        pass
            if changed:
                LOG.log(f"🔧 Remote tuning (params): {changed}")
                return changed

        tune_src = obj.get("tune") if isinstance(obj.get("tune"), dict) else obj
        mapping_v1 = {
            "gainvalue": ("gain", float),
            "deadzonevalue": ("deadzone", float),
            "expovalue": ("expo", float),
            "maxanglevalue": ("max_deg", float),
            "invert": ("invert", bool),
        }
        for k_src, (k_dst, cast) in mapping_v1.items():
            if k_src in tune_src:
                try:
                    val = cast(tune_src[k_src])
                    setattr(SETTINGS, k_dst, val)
                    changed[k_dst] = val
                except Exception:
                    pass
        if changed:
            LOG.log(f"🔧 Remote tuning (legacy): {changed}")
            return changed
        return None

    # ---- client management ----
    def _status_label(self, cs: ClientState) -> str:
        return f"{cs.addr[0]}:{cs.addr[1]}  ({cs.state})"

    def _emit_clients(self):
        items = [self._status_label(cs) for cs in self._clients.values()]
        self.clients_changed.emit(items)

    def _get_or_create_client(self, addr: Tuple[str,int]) -> ClientState:
        cs = self._clients.get(addr)
        if cs is None:
            pad = XGamepad()
            now = int(time.time()*1000)
            cs = ClientState(pad=pad, last_rx_ms=now, addr=addr,
                             name=f"{addr[0]}:{addr[1]}", state="active",
                             neutral_sent=False, state_changed_ms=now)
            self._clients[addr] = cs
            LOG.log(f"➕ Client created: {addr[0]}:{addr[1]} (gamepad {'OK' if pad.available else 'N/A'})")
            self._emit_clients()
        return cs

    def _maybe_set_state(self, cs: ClientState, new_state: str, now_ms: int):
        if cs.state != new_state:
            cs.state = new_state
            cs.state_changed_ms = now_ms
            self._emit_clients()

    def _idle_maintenance(self, now_ms: int):
        for cs in self._clients.values():
            if cs.state == "disconnected":
                continue
            quiet_ms = now_ms - cs.last_rx_ms
            if quiet_ms > self._idle_after_ms:
                if not cs.neutral_sent:
                    cs.pad.neutral()
                    cs.neutral_sent = True
                self._maybe_set_state(cs, "idle", now_ms)

    def _destroy_idle_clients(self, now_ms: int):
        stale = [addr for addr, cs in self._clients.items()
                 if cs.state == "idle" and (now_ms - cs.last_rx_ms) > self._destroy_after_ms]
        for addr in stale:
            cs = self._clients.pop(addr, None)
            if not cs: continue
            try:
                cs.pad.neutral()
                cs.pad.close()
            except Exception:
                pass
            LOG.log(f"🗑️ Client destroyed after idle: {addr[0]}:{addr[1]}")
            self._emit_clients()

    def _handle_disconnect(self, addr: Tuple[str,int], note="Client requested disconnect"):
        cs = self._clients.get(addr)
        if not cs:
            return
        now = int(time.time()*1000)
        cs.neutral_sent = False
        cs.pad.neutral()
        cs.neutral_sent = True
        self._maybe_set_state(cs, "disconnected", now)
        LOG.log(f"⏹️ {note}: {addr[0]}:{addr[1]} (pad kept alive)")

    def _handle_destroy(self, addr: Tuple[str,int]):
        cs = self._clients.pop(addr, None)
        if not cs:
            return
        try:
            cs.pad.neutral()
            cs.pad.close()
        except Exception:
            pass
        LOG.log(f"🗑️ Client destroyed on request: {addr[0]}:{addr[1]} (pad closed + removed)")
        self._emit_clients()

    # ---- main loop ----
    def _run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:
            pass
        try:
            SIO_UDP_CONNRESET = getattr(socket, "SIO_UDP_CONNRESET", 0x9800000C)
            if platform.system() == "Windows" and hasattr(sock, "ioctl"):
                sock.ioctl(SIO_UDP_CONNRESET, struct.pack("I", 0))
        except Exception as e:
            LOG.log(f"⚠️ Could not disable UDP connreset: {e}")

        sock.bind(("0.0.0.0", self.port))
        sock.settimeout(0.2)
        last_udp_err_ms = 0

        while not self._stop.is_set():
            now_ms = int(time.time() * 1000)
            self._idle_maintenance(now_ms)
            self._destroy_idle_clients(now_ms)

            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError as e:
                if self._stop.is_set():
                    break
                if now_ms - last_udp_err_ms > 2000:
                    LOG.log(f"⚠️ UDP socket error (continuing): {e}")
                    last_udp_err_ms = now_ms
                continue
            except Exception:
                continue

            try:
                if not data or data[:1] != b'{':
                    continue

                s = data.decode("utf-8", errors="ignore")
                obj = json.loads(s)

                # control packets (no client spawn)
                t = obj.get("type")
                if t == "finetune":
                    changed = self._maybe_apply_remote_tuning(obj)
                    if changed: self.tuning.emit(changed)
                    continue

                caddr = (addr[0], addr[1])

                if t == "inbackground":
                    self._handle_disconnect(caddr, note="Background mode")
                    continue
                if t == "disconnect":
                    self._handle_disconnect(caddr)
                    continue
                if t == "destroy":
                    self._handle_destroy(caddr)
                    continue

                # telemetry
                cs = self._get_or_create_client(caddr)

                if not isinstance(obj, dict) or obj.get("sig") != "WHEEL1":
                    cs.last_rx_ms = now_ms
                    cs.neutral_sent = False
                    self._maybe_set_state(cs, "active", now_ms)
                    continue

                axis = obj.get("axis") or {}
                if not isinstance(axis, dict): axis = {}
                buttons = obj.get("buttons") or {}
                if not isinstance(buttons, dict): buttons = {}

                def to_float(x, default=0.0):
                    try:
                        if isinstance(x, (int, float)): return float(x)
                        if isinstance(x, str): return float(x.strip())
                    except Exception:
                        pass
                    return float(default)

                def to_int(x, default=0):
                    try: return int(float(x))
                    except Exception: return int(default)

                x_raw   = to_float(axis.get("steering_x", 0.0))
                throttle = to_float(axis.get("throttle", 0.0))
                brake    = to_float(axis.get("brake", 0.0))
                latG     = to_float(axis.get("latG", 0.0))
                ls_x     = to_float(axis.get("ls_x", 0.0))
                ls_y     = to_float(axis.get("ls_y", 0.0))
                seq      = to_int(obj.get("seq", 0))

                cs.last_rx_ms = now_ms
                cs.neutral_sent = False
                self._maybe_set_state(cs, "active", now_ms)

                x_proc = self._apply_filters(x_raw)

                VALID = ("A","B","X","Y","LB","RB","Start","Back")
                btns: Dict[str, bool] = {}
                for name in VALID:
                    v = buttons.get(name, False)
                    if isinstance(v, bool): btns[name] = v
                    elif isinstance(v, (int, float)): btns[name] = (v != 0)
                    elif isinstance(v, str): btns[name] = v.strip().lower() in ("1","true","on","yes","pressed")
                    else: btns[name] = False

                mask = 0
                for idx, name in enumerate(VALID):
                    if btns.get(name, False):
                        mask |= (1 << idx)

                centered = abs(x_proc) < 0.06
                calm = (throttle < 0.18 and brake < 0.18 and abs(latG) < 0.06)

                if centered and calm:
                    resistance = 1.0
                    center = 0.0
                    rumbleL = 0.0
                    rumbleR = 0.0
                else:
                    resistance = max(0.0, min(1.0,
                        0.35 + 0.30 * min(1.0, abs(latG)) + 0.25 * throttle - 0.20 * brake
                    ))
                    center = max(-1.0, min(1.0, -x_proc))
                    # leave rumble calc intact for phone feedback consistency
                    rumbleL = max(0.0, min(1.0, 0.12 + 0.65 * throttle + 0.22 * min(1.0, abs(latG))))
                    rumbleR = max(0.0, min(1.0, 0.50 * min(1.0, abs(latG)) + 0.50 * brake))

                if cs.pad:
                    cs.pad.update(
                        x_proc, throttle, brake, mask,
                        rumbleL, rumbleR,
                        rsx=ls_x, rsy=ls_y
                    )

                # emit (overlay now uses latG rather than rumble)
                self.telemetry.emit(x_proc, throttle, brake, latG, self._qt_safe_seq(seq), rumbleL, rumbleR)
                self.buttons.emit(btns)

                reply = {
                    "ack": seq,
                    "status": "ok",
                    "rumble": max(rumbleL, rumbleR),
                    "rumbleL": rumbleL,
                    "rumbleR": rumbleR,
                    "center": center,
                    "centerDeg": 0.0,
                    "resistance": resistance,
                    "note": "ok",
                }
                try:
                    sock.sendto(json.dumps(reply).encode("utf-8"), addr)
                except Exception:
                    pass

            except json.JSONDecodeError:
                continue
            except Exception:
                continue

        for cs in self._clients.values():
            try: cs.pad.neutral()
            except Exception: pass
        try:
            sock.close()
        except Exception:
            pass
        LOG.log("🛑 UDP server stopped")

# ---------- Fonts + Theme ----------
def _find_font_file(names: List[str]) -> Optional[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    search_dirs = [here, os.getcwd(), "/mnt/data"]
    for n in names:
        for d in search_dirs:
            p = os.path.join(d, n)
            if os.path.isfile(p): return p
    return None

def load_monument_fonts() -> Dict[str, str]:
    db = QtGui.QFontDatabase()
    families = {"regular": "", "ultra": ""}
    regular_path = _find_font_file(["MonumentExtended-Regular.otf", "Monument Extended Regular.otf"])
    ultra_path   = _find_font_file(["MonumentExtended-Ultrabold.otf", "Monument Extended Ultrabold.otf"])
    if regular_path:
        fid = db.addApplicationFont(regular_path)
        fams = db.applicationFontFamilies(fid)
        if fams: families["regular"] = fams[0]
        LOG.log(f"🎨 Loaded font: {regular_path} -> {families['regular']}")
    else:
        LOG.log("⚠️ MonumentExtended-Regular.otf not found; using system font.")
    if ultra_path:
        fid2 = db.addApplicationFont(ultra_path)
        fams2 = db.applicationFontFamilies(fid2)
        if fams2: families["ultra"] = fams2[0]
        LOG.log(f"🎨 Loaded font: {ultra_path} -> {families['ultra']}")
    else:
        LOG.log("⚠️ MonumentExtended-Ultrabold.otf not found; using system font.")
    return families

def apply_theme(app: QtWidgets.QApplication, families: Dict[str, str]):
    NAVY   = "#0F2431"; PANEL  = "#112B3A"; LIME   = "#D4FF00"; MUTED  = "#8BA3B0"; WHITE  = "#F2F5F8"
    reg = families.get("regular") or app.font().family()
    ultra = families.get("ultra") or reg
    base = QtGui.QFont(reg, 10); app.setFont(base)
    qss = f"""
    QWidget {{ background: {NAVY}; color: {WHITE}; font-family: "{reg}"; font-size: 12pt; }}
    QLabel#Section {{ font-family: "{ultra}"; font-size: 11pt; color: {MUTED}; letter-spacing: 1px; }}
    QLabel#Tiny {{ font-family: "{reg}"; font-size: 8pt; color: {MUTED}; }}
    QPushButton {{ background: transparent; color: {LIME}; border: 2px solid {LIME}; padding: 6px 14px; border-radius: 14px; }}
    QPushButton:hover {{ background: {LIME}; color: {NAVY}; }}
    QCheckBox {{ color: {WHITE}; spacing: 8px; font-family: "{ultra}"; font-size: 10pt; }}
    QSlider::groove:horizontal {{ height: 12px; background: {PANEL}; border-radius: 6px; }}
    QSlider::handle:horizontal {{ width: 18px; height: 18px; margin-top: -4px; margin-bottom: -4px; border-radius: 9px; background: {LIME}; border: 2px solid {NAVY}; }}
    QProgressBar {{ background: {PANEL}; border: none; border-radius: 10px; text-align: center; height: 20px; }}
    QProgressBar::chunk {{ background: {LIME}; border-radius: 10px; }}
    QPlainTextEdit {{ background: {PANEL}; border: none; border-radius: 10px; padding: 8px; color: {WHITE}; font-size: 10pt; }}
    .Led {{ background: #233747; border-radius: 12px; min-width: 44px; min-height: 32px; border: 2px solid #233747; }}
    .Led[on="true"] {{ background: {LIME}; border: 2px solid {LIME}; }}
    """
    app.setStyleSheet(qss)

# ---------- Global hotkeys (Windows) ----------
class WinHotkeys(QtCore.QObject, QtCore.QAbstractNativeEventFilter):
    """
    System-wide F9/F10/F11 using RegisterHotKey; emits signals when pressed.
    """
    hotkeyPressed = QtCore.Signal(int)  # id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ids = []
        self._registered = False

    def nativeEventFilter(self, eventType, message):
        if platform.system() != "Windows":
            return False, 0
        try:
            import ctypes
            from ctypes import wintypes
            msg = ctypes.cast(int(message), ctypes.POINTER(ctypes.wintypes.MSG)).contents
            WM_HOTKEY = 0x0312
            if msg.message == WM_HOTKEY:
                self.hotkeyPressed.emit(msg.wParam)
        except Exception:
            pass
        return False, 0

    def register(self):
        if platform.system() != "Windows" or self._registered:
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            RegisterHotKey = user32.RegisterHotKey
            UnregisterHotKey = user32.UnregisterHotKey
            MOD_NOREPEAT = 0x4000
            VK_F9, VK_F10, VK_F11 = 0x78, 0x79, 0x7A
            hwnd = 0  # global
            # ids
            id_f9, id_f10, id_f11 = 1001, 1002, 1003
            for (vk, _id) in [(VK_F9, id_f9), (VK_F10, id_f10), (VK_F11, id_f11)]:
                if not RegisterHotKey(hwnd, _id, MOD_NOREPEAT, vk):
                    LOG.log(f"⚠️ RegisterHotKey failed for id={_id}")
                else:
                    self._ids.append(_id)
            self._registered = True
            LOG.log("⌨️ Global hotkeys ready: F9/F10/F11")
        except Exception as e:
            LOG.log(f"⚠️ Global hotkeys unavailable: {e}")

    def unregister(self):
        if platform.system() != "Windows" or not self._registered:
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            for _id in self._ids:
                user32.UnregisterHotKey(0, _id)
        except Exception:
            pass
        self._registered = False
        self._ids.clear()

# ---------- Overlay ----------
class Overlay(QtWidgets.QWidget):
    """
    Always-on-top translucent overlay:
      - bottom steering pill (SVG/PNG, preserves aspect)
      - left/right gradient bars for *latG*-driven G feel (drift/turn)
      - draggable side bars AND draggable bottom bar when input enabled
      - global hotkeys: controlled from MainWindow via callbacks
    """
    NAVY = QtGui.QColor("#0F2431")
    LIME = QtGui.QColor("#D4FF00")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wheeler Overlay")
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # click-through by default
        self._input_enabled = False

        # telemetry + smoothed values
        self._sx = 0.0
        self._sg = 0.0  # smoothed |latG| mapped
        self._g_sign = 0  # -1 left, +1 right, 0 none

        # smoothing
        self._alpha_pos = 0.25
        self._alpha_g   = 0.20

        # visuals / layout defaults
        self._bar_width = 80
        self._margin    = 16

        # draggable side positions
        self._left_x  = 0
        self._right_x = 0
        self._drag_side = None
        self._drag_dx = 0

        # bottom bar placement (draggable)
        self._track_w_target = 520  # desired width (height follows aspect)
        self._track_pos = QtCore.QPointF(0, 0)  # will be set to bottom center
        self._drag_bar = False
        self._drag_bar_offset = QtCore.QPointF(0,0)

        # art assets (SVG or raster) + aspect
        self._bar_svg = None
        self._bar_pix = None
        self._bar_aspect = 520/22  # sane default; will be overwritten
        self._load_bar_art()

        # set window click-through state
        self._apply_click_through()

        # geometry = primary screen & edges
        self._apply_screen_geometry()

        # repaint timer
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(33)

        # react screen changes
        app = QtWidgets.QApplication.instance()
        for s in app.screens():
            s.geometryChanged.connect(self._apply_screen_geometry)

        self.show()

    def _load_bar_art(self):
        svg_paths = [
            os.path.join(os.path.dirname(__file__), "BAR.svg"),
            "BAR.svg",
            "/mnt/data/BAR.svg",
        ]
        raster_paths = [
            os.path.join(os.path.dirname(__file__), "BAR.jpeg"),
            os.path.join(os.path.dirname(__file__), "BAR.png"),
            "BAR.jpeg","BAR.png","bar.jpeg","bar.png",
            "/mnt/data/BAR.jpeg","/mnt/data/BAR.png","/mnt/data/bar.png"
        ]
        try:
            from PySide6 import QtSvg
            for pth in svg_paths:
                if os.path.isfile(pth):
                    r = QtSvg.QSvgRenderer(pth)
                    if r.isValid():
                        self._bar_svg = r
                        vb = r.viewBoxF()
                        if vb.width() > 0 and vb.height() > 0:
                            self._bar_aspect = vb.width() / vb.height()
                        LOG.log(f"🖼️ Using SVG bar: {pth} (aspect {self._bar_aspect:.3f})")
                        return
        except Exception:
            pass
        for pth in raster_paths:
            if os.path.isfile(pth):
                pm = QtGui.QPixmap(pth)
                if not pm.isNull():
                    self._bar_pix = pm
                    if pm.height() > 0:
                        self._bar_aspect = pm.width() / pm.height()
                    LOG.log(f"🖼️ Using raster bar: {pth} (aspect {self._bar_aspect:.3f})")
                    return
        LOG.log("🖼️ No bar art found; drawing fallback pill (aspect preserved).")

    # ---------- input toggles ----------
    def set_input_enabled(self, enabled: bool):
        self._input_enabled = bool(enabled)
        self._apply_click_through()
        if self._input_enabled:
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(Qt.BlankCursor))

    def _apply_click_through(self):
        try:
            self.setWindowFlag(Qt.WindowTransparentForInput, not self._input_enabled)
        except Exception:
            pass
        self.show()
        if platform.system() == "Windows":
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                gwl_exstyle = -20
                ws_ex_layered = 0x00080000
                ws_ex_transparent = 0x00000020
                hwnd = int(self.winId())
                GetWindowLongW = user32.GetWindowLongW
                SetWindowLongW = user32.SetWindowLongW
                GetWindowLongW.restype = ctypes.c_long
                GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
                SetWindowLongW.restype = ctypes.c_long
                SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
                ex = GetWindowLongW(hwnd, gwl_exstyle)
                ex |= ws_ex_layered
                if not self._input_enabled:
                    ex |= ws_ex_transparent
                else:
                    ex &= ~ws_ex_transparent
                SetWindowLongW(hwnd, gwl_exstyle, ex)
            except Exception as e:
                LOG.log(f"⚠️ Click-through toggle failed: {e}")

    # ---------- geometry ----------
    def _apply_screen_geometry(self):
        scr = QtWidgets.QApplication.primaryScreen()
        if not scr: return
        geo = scr.geometry()
        self.setGeometry(geo)
        # side bars at edges
        self._left_x  = max(0, min(self._left_x,  geo.width() - self._bar_width))
        self._right_x = max(0, geo.width() - self._bar_width)
        # bottom bar at bottom center, keep margins
        track_w = self._track_w_target
        track_h = track_w / self._bar_aspect
        x = (geo.width() - track_w)/2
        y = geo.height() - track_h - self._margin
        self._track_pos = QtCore.QPointF(x, y)

    def reset_layout(self):
        self._sx = 0.0
        self._sg = 0.0
        self._g_sign = 0
        self._apply_screen_geometry()

    # ---------- telemetry (steering + G) ----------
    def set_telemetry(self, x: float, latg: float):
        # steering
        x = max(-1.0, min(1.0, float(x)))
        self._sx += self._alpha_pos * (x - self._sx)
        # latG -> side and magnitude (map |g| ~1.2 to full)
        g = float(latg)
        self._g_sign = -1 if g < 0 else (1 if g > 0 else 0)
        a = max(0.0, min(1.5, abs(g))) / 1.2  # 1.2g ~ full
        self._sg += self._alpha_g * (a - self._sg)

    # ---------- drawing helpers ----------
    def _bottom_rect(self) -> QtCore.QRectF:
        w = float(self._track_w_target)
        h = float(w / self._bar_aspect)  # preserve aspect
        return QtCore.QRectF(self._track_pos.x(), self._track_pos.y(), w, h)

    # ---------- paint ----------
    def paintEvent(self, ev: QtGui.QPaintEvent):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        W = self.width(); H = self.height()

        # side bars from latG
        def draw_side(x0: int, intensity: float, left: bool, active: bool):
            if not active: return
            a = max(0.0, min(1.0, intensity))
            a = 1.0 - math.exp(-3.0 * a)
            if a <= 0.001: return
            bar = QtCore.QRectF(x0, 0, self._bar_width, H)
            grad = QtGui.QLinearGradient(
                bar.left() if not left else bar.right(), 0,
                bar.right() if not left else bar.left(), 0
            )
            c0 = QtGui.QColor(self.LIME); c0.setAlphaF(0.0)
            c1 = QtGui.QColor(self.LIME); c1.setAlphaF(0.75 * a)
            grad.setColorAt(0.0, c0)
            grad.setColorAt(1.0, c1)
            p.fillRect(bar, QtGui.QBrush(grad))

        show_sides = getattr(self, "_show_sidebars", True)
        draw_side(self._left_x,  self._sg, True,  show_sides and (self._g_sign <= 0 or self._sg < 0.12))
        draw_side(self._right_x, self._sg, False, show_sides and (self._g_sign >= 0 or self._sg < 0.12))

        # bottom steering pill (preserve aspect; draggable)
        rect = self._bottom_rect()
        if self._bar_svg is not None:
            try:
                self._bar_svg.render(p, rect)
            except Exception:
                pass
        elif self._bar_pix and not self._bar_pix.isNull():
            p.drawPixmap(rect, self._bar_pix, QtCore.QRectF(0,0,self._bar_pix.width(), self._bar_pix.height()))
        else:
            # fallback: navy rounded track
            path = QtGui.QPainterPath()
            path.addRoundedRect(rect, rect.height()/2, rect.height()/2)
            p.fillPath(path, self.NAVY.darker(115))

        # indicator knob (same height as bar)
        t = max(0.0, min(1.0, self._sx * 0.5 + 0.5))
        knob_w = rect.height()
        knob_x = rect.x() + (rect.width() - knob_w) * t
        knob_path = QtGui.QPainterPath()
        knob_path.addRoundedRect(QtCore.QRectF(knob_x, rect.y(), knob_w, rect.height()), rect.height()/2, rect.height()/2)
        p.fillPath(knob_path, self.LIME)

        p.end()

    # ---------- mouse (drag sides + drag bottom bar) ----------
    def _side_hit(self, pos: QtCore.QPointF) -> Optional[str]:
        if not self._input_enabled: return None
        rectL = QtCore.QRectF(self._left_x, 0, self._bar_width, self.height())
        rectR = QtCore.QRectF(self._right_x, 0, self._bar_width, self.height())
        if rectL.contains(pos): return "L"
        if rectR.contains(pos): return "R"
        return None

    def _bar_hit(self, pos: QtCore.QPointF) -> bool:
        if not self._input_enabled: return False
        return self._bottom_rect().contains(pos)

    def mousePressEvent(self, e: QtGui.QMouseEvent):
        if not self._input_enabled: return
        pos = e.position()
        side = self._side_hit(pos)
        if side:
            self._drag_side = side
            self._drag_dx = pos.x() - (self._left_x if side == "L" else self._right_x)
            return
        if self._bar_hit(pos):
            self._drag_bar = True
            r = self._bottom_rect()
            self._drag_bar_offset = QtCore.QPointF(pos.x()-r.x(), pos.y()-r.y())

    def mouseMoveEvent(self, e: QtGui.QMouseEvent):
        if not self._input_enabled: return
        if self._drag_side:
            x = int(e.position().x() - self._drag_dx)
            x = max(0, min(self.width() - self._bar_width, x))
            if self._drag_side == "L":
                self._left_x = x
            else:
                self._right_x = x
        elif self._drag_bar:
            nx = e.position().x() - self._drag_bar_offset.x()
            ny = e.position().y() - self._drag_bar_offset.y()
            # clamp to screen with margins
            r = self._bottom_rect()
            w, h = r.width(), r.height()
            nx = max(0, min(self.width() - w, nx))
            ny = max(0, min(self.height() - h, ny))
            self._track_pos = QtCore.QPointF(nx, ny)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        self._drag_side = None
        self._drag_bar = False

    # ---------- visibility helpers ----------
    def set_overlay_visible(self, vis: bool):
        if vis: self.show()
        else:   self.hide()

    def set_sidebars_visible(self, vis: bool):
        self._show_sidebars = bool(vis)

# ---------- QR pane ----------
class QRPane(QtWidgets.QScrollArea):
    def __init__(self, port: int):
        super().__init__()
        self.port = port
        self.setWidgetResizable(True)
        self._inner = QtWidgets.QWidget()
        self.setWidget(self._inner)
        self.hbox = QtWidgets.QHBoxLayout(self._inner)
        self.hbox.setContentsMargins(8,8,8,8)
        self.hbox.setSpacing(12)
        self.refresh()
    def refresh(self):
        while (item := self.hbox.takeAt(0)) is not None:
            w = item.widget()
            if w: w.deleteLater()
        for ip in list_ipv4():
            url = f"udp://{ip}:{self.port}"
            qr_img = qrcode.make(url)
            if hasattr(qr_img, "get_image"): qr_img = qr_img.get_image()
            qr_img = qr_img.convert("RGB")
            buf = io.BytesIO(); qr_img.save(buf, format="PNG")
            pix = QtGui.QPixmap(); pix.loadFromData(buf.getvalue(), "PNG")
            panel = QtWidgets.QFrame(); panel.setFrameShape(QtWidgets.QFrame.NoFrame)
            v = QtWidgets.QVBoxLayout(panel); v.setContentsMargins(10,10,10,10); v.setSpacing(8)
            lblImg = QtWidgets.QLabel(); lblImg.setPixmap(pix); lblImg.setAlignment(Qt.AlignCenter)
            lblTxt = QtWidgets.QLabel(url); lblTxt.setAlignment(Qt.AlignCenter)
            lblTxt.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lblTxt.setObjectName("Tiny")
            v.addWidget(lblImg); v.addWidget(lblTxt)
            self.hbox.addWidget(panel)
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.hbox.addWidget(spacer)

# ---------- Main Window ----------
class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wheeler (UDP) — Windows (Overlay + Global Hotkeys)")
        self.resize(1180, 820)

        self.server = UDPServer(port=8765)
        self.server.telemetry.connect(self.onTelemetry)
        self.server.buttons.connect(self.onButtons)
        self.server.tuning.connect(self.onRemoteTuning)
        self.server.clients_changed.connect(self.onClientsChanged)

        # Overlay (startup-safe)
        self.overlay = None
        self._overlay_visible = True
        try:
            self.overlay = Overlay()
            self.overlay.set_input_enabled(False)  # click-through + hidden cursor
        except Exception as e:
            LOG.log(f"⚠️ Overlay failed to initialize: {e}")
            self.overlay = None

        # Global hotkeys (F9/F10/F11)
        self._hot = WinHotkeys()
        QtWidgets.QApplication.instance().installNativeEventFilter(self._hot)
        self._hot.register()
        self._hot.hotkeyPressed.connect(self._on_hotkey)

        # Top bar
        top = QtWidgets.QHBoxLayout()
        self.lblLan = QtWidgets.QLabel(f"{list_ipv4()[0]}:8765"); self.lblLan.setObjectName("Tiny")

        # Overlay controls
        self.btnToggleOverlay = QtWidgets.QPushButton("Hide Overlay (F9)")
        self.btnToggleCursor  = QtWidgets.QPushButton("Cursor On (F10)")
        self.btnResetOverlay  = QtWidgets.QPushButton("Reset Overlay (F11)")

        self.btnStart = QtWidgets.QPushButton("STOP")
        self.chkInvert = QtWidgets.QCheckBox("INVERT STEERING")
        self.chkInvert.setChecked(SETTINGS.invert); self.chkInvert.setEnabled(False)

        top.addWidget(self.lblLan); top.addStretch(1)
        top.addWidget(self.btnToggleOverlay)
        top.addWidget(self.btnToggleCursor)
        top.addWidget(self.btnResetOverlay)
        top.addSpacing(12)
        top.addWidget(self.btnStart); top.addSpacing(12); top.addWidget(self.chkInvert)

        self.btnStart.clicked.connect(self.toggleServer)
        self.btnToggleOverlay.clicked.connect(self._toggle_overlay)
        self.btnToggleCursor.clicked.connect(self._toggle_cursor)
        self.btnResetOverlay.clicked.connect(self._reset_overlay)

        # Shortcuts (still work while window focused; globals handled above)
        QtGui.QShortcut(QtGui.QKeySequence("F9"),  self, activated=self._toggle_overlay)
        QtGui.QShortcut(QtGui.QKeySequence("F10"), self, activated=self._toggle_cursor)
        QtGui.QShortcut(QtGui.QKeySequence("F11"), self, activated=self._reset_overlay)

        # Left column: QR + Inputs
        leftCol = QtWidgets.QVBoxLayout()
        self.qrPane = QRPane(8765)
        leftCol.addWidget(self.qrPane, 3)

        labInputs = QtWidgets.QLabel("INPUTS (last active client)"); labInputs.setObjectName("Section")
        leftCol.addWidget(labInputs)
        inGrid = QtWidgets.QGridLayout(); inGrid.setHorizontalSpacing(16); inGrid.setVerticalSpacing(8)

        self.lblSteerVal = QtWidgets.QLabel("0.00"); self.lblSteerVal.setAlignment(Qt.AlignRight); self.lblSteerVal.setObjectName("Tiny")
        self.prSteer = QtWidgets.QProgressBar(); self.prSteer.setRange(0,1000); self.prSteer.setTextVisible(False); self.prSteer.setMinimumHeight(20)

        self.lblThrVal = QtWidgets.QLabel("0%"); self.lblThrVal.setAlignment(Qt.AlignRight); self.lblThrVal.setObjectName("Tiny")
        self.prThrottle = QtWidgets.QProgressBar(); self.prThrottle.setRange(0,1000); self.prThrottle.setFormat("Throttle %p%")

        self.lblBrkVal = QtWidgets.QLabel("0%"); self.lblBrkVal.setAlignment(Qt.AlignRight); self.lblBrkVal.setObjectName("Tiny")
        self.prBrake = QtWidgets.QProgressBar(); self.prBrake.setRange(0,1000); self.prBrake.setFormat("Brake %p%")

        inGrid.addWidget(QtWidgets.QLabel("STEERING"), 0, 0); inGrid.addWidget(self.lblSteerVal, 0, 1); inGrid.addWidget(self.prSteer, 1, 0, 1, 2)
        inGrid.addWidget(QtWidgets.QLabel("THROTTLE"), 2, 0); inGrid.addWidget(self.lblThrVal, 2, 1); inGrid.addWidget(self.prThrottle, 3, 0, 1, 2)
        inGrid.addWidget(QtWidgets.QLabel("BRAKE"),    4, 0); inGrid.addWidget(self.lblBrkVal, 4, 1); inGrid.addWidget(self.prBrake,    5, 0, 1, 2)
        leftCol.addLayout(inGrid)

        # Right column: tuning (display-only) + clients list
        rightCol = QtWidgets.QVBoxLayout()
        labTuning = QtWidgets.QLabel("TUNING"); labTuning.setObjectName("Section")
        rightCol.addWidget(labTuning)

        self.gainValLab,   self.gainRow   = self._display_slider("GAIN",      0.20, 5.00, SETTINGS.gain)
        self.dzValLab,     self.dzRow     = self._display_slider("DEADZONE",  0.00, 0.20, SETTINGS.deadzone, fmt="{:.3f}")
        self.expoValLab,   self.expoRow   = self._display_slider("EXPO",      0.00, 1.00, SETTINGS.expo)
        self.maxDegValLab, self.maxDegRow = self._display_slider("MAX ANGLE", 10.0, 90.0, SETTINGS.max_deg, fmt="{:.0f}")

        g = QtWidgets.QVBoxLayout()
        g.addWidget(self.gainRow); g.addWidget(self.dzRow); g.addWidget(self.expoRow); g.addWidget(self.maxDegRow)
        rightCol.addLayout(g)

        labClients = QtWidgets.QLabel("CLIENTS (idle>60s → destroy)"); labClients.setObjectName("Section")
        rightCol.addWidget(labClients)
        self.lstClients = QtWidgets.QListWidget()
        rightCol.addWidget(self.lstClients, 1)

        # Buttons LEDs
        labButtons = QtWidgets.QLabel("BUTTONS (last active)"); labButtons.setObjectName("Section")
        ledsRow = QtWidgets.QHBoxLayout()
        self.btnLabels: Dict[str, QtWidgets.QLabel] = {}
        for name in ["A","B","X","Y","LB","RB","Start","Back"]:
            lab = QtWidgets.QLabel()
            lab.setFixedSize(44, 32)
            lab.setProperty("on", "false")
            lab.setStyleSheet("")
            lab.setAccessibleDescription(name)
            lab.setProperty("class", "Led")
            self.btnLabels[name] = lab
            ledsRow.addWidget(lab)

        # Log
        labLog = QtWidgets.QLabel("LOG"); labLog.setObjectName("Section")
        self.txtLog = QtWidgets.QPlainTextEdit(); self.txtLog.setReadOnly(True)
        LOG.line.connect(self._appendLog)

        # Layout
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(20, 16, 20, 16)
        grid.setHorizontalSpacing(24); grid.setVerticalSpacing(14)
        grid.addLayout(top,        0, 0, 1, 2)
        grid.addLayout(leftCol,    1, 0, 1, 1)
        grid.addLayout(rightCol,   1, 1, 1, 1)
        grid.addWidget(labButtons, 2, 0, 1, 2)
        grid.addLayout(ledsRow,    3, 0, 1, 2)
        grid.addWidget(labLog,     4, 0, 1, 2)
        grid.addWidget(self.txtLog,5, 0, 1, 2)

        # Start
        self.toggleServer()

    # ---- helpers ----
    def _display_slider(self, title: str, lo: float, hi: float, init: float, fmt="{:.2f}"):
        lab = QtWidgets.QLabel(title); lab.setObjectName("Section")
        s = QtWidgets.QSlider(Qt.Horizontal); s.setMinimum(0); s.setMaximum(1000); s.setEnabled(False)
        valLab = QtWidgets.QLabel(fmt.format(init)); valLab.setAlignment(Qt.AlignRight); valLab.setObjectName("Tiny")
        row = QtWidgets.QGridLayout()
        row.addWidget(lab, 0, 0, 1, 1)
        row.addWidget(valLab, 0, 2, 1, 1)
        row.addWidget(s, 1, 0, 1, 3)
        w = QtWidgets.QWidget(); w.setLayout(row)
        pos0 = int((init - lo) / (hi - lo) * 1000)
        pos0 = max(0, min(1000, pos0))
        s.setValue(pos0)
        w._range = (lo, hi, fmt, s, valLab)
        return valLab, w

    def _set_display_slider(self, w: QtWidgets.QWidget, value: float):
        lo, hi, fmt, s, valLab = w._range
        val = max(lo, min(hi, float(value)))
        pos = int((val - lo) / (hi - lo) * 1000)
        s.setValue(pos)
        valLab.setText(fmt.format(val))

    def toggleServer(self):
        running = getattr(self, "_running", False)
        if not running:
            self.server.start()
            self.btnStart.setText("STOP")
            self.qrPane.refresh()
            self.lblLan.setText(f"{list_ipv4()[0]}:8765")
        else:
            self.server.stop()
            self.btnStart.setText("START")
        self._running = not running

    def _appendLog(self, s: str):
        self.txtLog.moveCursor(QtGui.QTextCursor.End)
        self.txtLog.insertPlainText(s)
        self.txtLog.moveCursor(QtGui.QTextCursor.End)

    # ---- Global hotkeys dispatch ----
    def _on_hotkey(self, hot_id: int):
        if   hot_id == 1001: self._toggle_overlay()
        elif hot_id == 1002: self._toggle_cursor()
        elif hot_id == 1003: self._reset_overlay()

    # ---- Overlay controls ----
    def _toggle_overlay(self):
        self._overlay_visible = not self._overlay_visible
        if self.overlay:
            self.overlay.set_overlay_visible(self._overlay_visible)
        self.btnToggleOverlay.setText(("Hide" if self._overlay_visible else "Show") + " Overlay (F9)")

    def _toggle_cursor(self):
        new_state = not (self.overlay and self.overlay._input_enabled)
        if self.overlay:
            self.overlay.set_input_enabled(new_state)
        self.btnToggleCursor.setText(("Cursor Off" if new_state else "Cursor On") + " (F10)")

    def _reset_overlay(self):
        if self.overlay:
            self.overlay.reset_layout()

    # ---- Slots ----
    def onTelemetry(self, x, throttle, brake, latG, seq_any, rumbleL, rumbleR):
        if self.overlay:
            self.overlay.set_telemetry(x, latG)

        steer_bar = int((x * 0.5 + 0.5) * 1000)
        self.prSteer.setValue(max(0, min(1000, steer_bar)))
        self.lblSteerVal.setText(f"{x:+.2f}")
        self.prThrottle.setValue(int(max(0.0, min(1.0, throttle)) * 1000))
        self.prBrake.setValue(int(max(0.0, min(1.0, brake)) * 1000))
        self.lblThrVal.setText(f"{int(throttle*100):d}%")
        self.lblBrkVal.setText(f"{int(brake*100):d}%")

    def onButtons(self, btns: Dict[str, bool]):
        for name, lab in self.btnLabels.items():
            on = bool(btns.get(name, False))
            lab.setProperty("on", "true" if on else "false")
            lab.style().unpolish(lab); lab.style().polish(lab); lab.update()

    def onRemoteTuning(self, changed: dict):
        if "gain" in changed:      self._set_display_slider(self.gainRow,   changed["gain"])
        if "deadzone" in changed:  self._set_display_slider(self.dzRow,     changed["deadzone"])
        if "expo" in changed:      self._set_display_slider(self.expoRow,   changed["expo"])
        if "max_deg" in changed:   self._set_display_slider(self.maxDegRow, changed["max_deg"])
        if "invert" in changed:    self.chkInvert.setChecked(bool(changed["invert"]))

    def onClientsChanged(self, items: List[str]):
        self.lstClients.clear()
        self.lstClients.addItems(items)
        # sidebars visible only if exactly one active/idle client
        active_count = 0
        for it in items:
            if "(active)" in it or "(idle)" in it:
                active_count += 1
        if self.overlay:
            self.overlay.set_sidebars_visible(active_count == 1)

    def closeEvent(self, e: QtGui.QCloseEvent):
        try:
            if self.overlay:
                self.overlay.close()
        except Exception:
            pass
        try:
            self._hot.unregister()
        except Exception:
            pass
        super().closeEvent(e)

# ---------- main ----------
def main():
    try:
        app = QtWidgets.QApplication(sys.argv)
    except Exception as e:
        LOG.log(f"❌ QApplication failed to start: {e}")
        LOG.log("Tip: pip install --upgrade PySide6")
        return

    try:
        fams = load_monument_fonts()
        apply_theme(app, fams)
    except Exception as e:
        LOG.log(f"⚠️ Theme init failed (continuing): {e}")

    try:
        win = MainWindow()
        win.show()
        sys.exit(app.exec())
    except Exception as e:
        LOG.log(f"❌ Main window failed: {e}")
        raise

if __name__ == "__main__":
    main()


