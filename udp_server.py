# udp_server.py
# Single-client UDP server -> ViGEmBridge (Windows).
# Real rumble (FFB) flows back from the game via ViGEmBridge and is returned to the phone.

import socket, threading, time, datetime, platform, struct, json, os, sys
# Ensure this repo root is on sys.path when launched from another CWD (Windows)
try:
    _HERE = os.path.dirname(__file__)
    if _HERE and _HERE not in sys.path:
        sys.path.insert(0, _HERE)
except Exception:
    pass
from dataclasses import dataclass
from typing import Optional, Tuple, Dict
from PySide6 import QtCore

from vigem_bridge import ViGEmBridge, XGamepad
try:
    from haptics.rumble_expander import RumbleExpander
except Exception:
    RumbleExpander = None  # type: ignore
try:
    from haptics.audio_probe import AudioProbe
except Exception:
    AudioProbe = None  # type: ignore
try:
    from haptics.memscan import MemoryScanManager
except Exception:
    MemoryScanManager = None  # type: ignore
try:
    from hid_bridge import HIDBridge  # optional; only used if WHEELER_BRIDGE=hid
except Exception:
    HIDBridge = None  # type: ignore
try:
    from vjoy_bridge import VJoyBridge  # optional
except Exception:
    VJoyBridge = None  # type: ignore
try:
    from dk_bridge_proc import DKBridgeProc  # optional (macOS DriverKit bridge helper)
except Exception:
    DKBridgeProc = None  # type: ignore

try:
    from macos_gamepad_bridge import MacOSGamepadBridge  # cross-platform
except Exception:
    MacOSGamepadBridge = None  # type: ignore

try:
    from driverkit_gamepad_bridge import DriverKitGamepadBridge  # macOS DriverKit
except Exception:
    DriverKitGamepadBridge = None  # type: ignore

# ---------- Logging ----------
class Logger(QtCore.QObject):
    line = QtCore.Signal(str)
    def log(self, s: str):
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
        line = f"[{ts}] {s}"
        print(line, flush=True)
        self.line.emit(line + "\n")
LOG = Logger()

# ---------- Settings ----------
class Settings(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self.invert = True
        self.gain = 1.0
        self.deadzone = 0.06
        self.expo = 0.30
        self.max_deg = 40.0
SETTINGS = Settings()

@dataclass
class ClientState:
    addr: Tuple[str,int]
    last_rx_ms: int
    state: str = "active"
    neutral_sent: bool = False

class UDPServer(QtCore.QObject):
    telemetry = QtCore.Signal(float, float, float, float, object, float, float, str)  # x,thr,brk,latG,seq,L,R,src
    buttons   = QtCore.Signal(dict)
    tuning    = QtCore.Signal(dict)
    clients_changed = QtCore.Signal(list)

    def __init__(self, port: int):
        super().__init__()
        self.port = port
        self._th: Optional[threading.Thread] = None
        self._stop = threading.Event()

        self._client: Optional[ClientState] = None
        self._locked = True
        self._idle_after_ms = 900

        # Bridge (prefer ViGEm; else vJoy if available)
        self._bridge = None
        self._bridge_name = ""
        self._init_bridge()
        self._ffbL = 0.0
        self._ffbR = 0.0
        self._ffb_ms = 0
        self._bridge.set_feedback_callback(self._on_ffb)
        self._ffb_test_timer: Optional[QtCore.QTimer] = None

        # Haptics: signal expander (maps 2‑ch FFB to richer features)
        self._hx = RumbleExpander() if RumbleExpander else None
        self._hx_tprev = None
        # Audio probe (fallback when no real FFB)
        self._audio_enabled = str(os.environ.get("WHEELER_AUDIO", "1")).strip().lower() not in ("0","off","false","no")
        self._audio_dev = -1  # -1 = Auto
        self._audio = AudioProbe(device=None) if (AudioProbe and self._audio_enabled) else None
        # Memory scan (optional, Windows only). Profile via env JSON-like or defaults empty
        self._mem_enabled = str(os.environ.get("WHEELER_MEMSCAN", "0")).strip().lower() in ("1","on","true","yes")
        self._mem = None
        if self._mem_enabled and MemoryScanManager is not None:
            try:
                prof_env = os.environ.get("WHEELER_MEM_PROFILE", "").strip()
                profile = {}
                if prof_env:
                    try:
                        import json as _json
                        profile = _json.loads(prof_env)
                    except Exception:
                        profile = {}
                self._mem = MemoryScanManager(profile=profile)
                LOG.log("🧠 Memory scan enabled")
            except Exception as e:
                LOG.log(f"⚠️ Memory scan init failed: {e}")

        # low-rate debug to verify we really send packets to the bridge
        self._last_dbg_ms = 0
        # low-rate debug for force feedback values coming from the bridge
        self._last_ffb_log_ms = 0
        # Debug: freeze steering to neutral (ignore phone steering)
        self._freeze_steer = False
        # Simplified FFB controls: allow audio fallback by default; no bed/mask tricks
        self._ffb_passthrough_only = False
        self._bed_when_real_zero = False
        self._hybrid_when_weak = False
        self._mask_real_zero = False
        env_syn = str(os.environ.get("WHEELER_SYNTH", "1")).strip().lower()
        self._synth_enabled = env_syn not in ("0","off","false","no")

    def _on_ffb(self, L: float, R: float):
        self._ffbL = float(max(0.0, min(1.0, L)))
        self._ffbR = float(max(0.0, min(1.0, R)))
        self._ffb_ms = int(time.time()*1000)
        # Log FFB occasionally so we know games are producing rumble
        now_ms = self._ffb_ms
        if now_ms - self._last_ffb_log_ms > 500:
            LOG.log(f"⬅️ FFB rumble from game L={self._ffbL:.2f} R={self._ffbR:.2f}")
            self._last_ffb_log_ms = now_ms

    # ---- debug knobs ----
    @QtCore.Slot(bool)
    def set_freeze_steering(self, freeze: bool):
        self._freeze_steer = bool(freeze)
        LOG.log(f"🧊 Debug: freeze steering set to {self._freeze_steer}")

    @QtCore.Slot(bool)
    def set_ffb_passthrough_only(self, on: bool):
        self._ffb_passthrough_only = bool(on)
        LOG.log(f"🎛️ FFB passthrough-only set to {self._ffb_passthrough_only}")

    # Runtime toggles
    @QtCore.Slot(bool)
    def set_bed_when_real_zero(self, on: bool):
        # legacy no-op
        self._bed_when_real_zero = False

    @QtCore.Slot(str)
    def set_pad_target(self, target: str):
        t = (target or "").strip().lower()
        if t not in ("x360", "ds4"):
            return
        try:
            if hasattr(self._bridge, 'set_target'):
                self._bridge.set_target(t)
                self._bridge_name = f"ViGEmBridge-{t.upper()}"
                LOG.log(f"🎮 Switched pad target to {t.upper()}")
        except Exception as e:
            LOG.log(f"⚠️ Failed to switch pad target: {e}")

    @QtCore.Slot()
    def ffb_test(self):
        """Inject a short test rumble (2s) as if coming from the game."""
        # Start/refresh timer updating freshness
        L, R = 0.6, 0.8
        self._ffbL = L; self._ffbR = R; self._ffb_ms = int(time.time()*1000)
        end_ms = self._ffb_ms + 2000
        if self._ffb_test_timer is None:
            self._ffb_test_timer = QtCore.QTimer(self)
            self._ffb_test_timer.setInterval(120)
            self._ffb_test_timer.timeout.connect(lambda: self._tick_ffb_test(end_ms))
        if not self._ffb_test_timer.isActive():
            self._ffb_test_timer.start()
        LOG.log("🧪 FFB test: injected L=0.6 R=0.8 for ~2s")

    def _tick_ffb_test(self, end_ms: int):
        now = int(time.time()*1000)
        if now >= end_ms:
            # stop
            if self._ffb_test_timer and self._ffb_test_timer.isActive():
                self._ffb_test_timer.stop()
            self._ffbL = 0.0; self._ffbR = 0.0; self._ffb_ms = now
            LOG.log("🧪 FFB test: finished")
            return
        # keep freshness
        self._ffb_ms = now

    @QtCore.Slot(bool)
    def set_hybrid_when_weak(self, on: bool):
        self._hybrid_when_weak = False

    @QtCore.Slot(bool)
    def set_mask_real_zero(self, on: bool):
        self._mask_real_zero = False

    def start(self):
        if self._th and self._th.is_alive(): return
        self._stop.clear()
        self._th = threading.Thread(target=self._run, daemon=True); self._th.start()
        LOG.log(f"🟢 UDP server ready on :{self.port} ({self._bridge_name})")

    def stop(self):
        self._stop.set()
        LOG.log("🛑 UDP server stopping...")

    # ---- shaping ----
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

    # ---- clients ----
    def _emit_clients(self):
        items = []
        if self._client: items.append(f"{self._client.addr[0]}:{self._client.addr[1]} ({self._client.state})")
        self.clients_changed.emit(items)

    def _maybe_apply_remote_tuning(self, obj: dict):
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
            LOG.log(f"🔧 Remote tuning: {changed}")
            return changed
        return None

    def _accepts(self, addr: Tuple[str,int]) -> bool:
        if not self._client: return True
        if self._locked and addr != self._client.addr: return False
        return True

    def _lock_to(self, addr: Tuple[str,int]):
        self._client = ClientState(addr=addr, last_rx_ms=int(time.time()*1000), state="active", neutral_sent=False)
        self._locked = True
        LOG.log(f"🔒 Locked to {addr[0]}:{addr[1]} ({self._bridge_name})")
        self._emit_clients()

    def _disconnect(self, note: str):
        if not self._client: return
        # center everything
        try:
            self._bridge.send_state(0.0, 0.0, 0, 0, 0)
        except Exception:
            pass
        self._client.neutral_sent = True
        self._client.state = "disconnected"
        LOG.log(f"⏹️ {note}: {self._client.addr[0]}:{self._client.addr[1]} (pad kept alive)")
        self._emit_clients()

    # ---- main loop ----
    def _run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:
            pass

        # Windows UDP connreset suppress (10054)
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
            now_ms = int(time.time()*1000)

            # Idle neutral
            if self._client and self._client.state == "active":
                quiet = now_ms - self._client.last_rx_ms
                if quiet > self._idle_after_ms and not self._client.neutral_sent:
                    try: self._bridge.send_state(0.0, 0.0, 0, 0, 0)
                    except Exception: pass
                    self._client.neutral_sent = True

            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError as e:
                if self._stop.is_set(): break
                if now_ms - last_udp_err_ms > 2000:
                    LOG.log(f"⚠️ UDP socket error (continuing): {e}")
                    last_udp_err_ms = now_ms
                continue
            except Exception:
                continue

            try:
                if not data or data[:1] != b'{': continue
                s = data.decode("utf-8", "ignore")
                obj = json.loads(s)

                # Control messages first
                t = obj.get("type")
                if t == "finetune":
                    ch = self._maybe_apply_remote_tuning(obj)
                    if ch: self.tuning.emit(ch)
                    continue
                if t in ("inbackground", "disconnect", "destroy"):
                    if self._client and addr == self._client.addr:
                        if t in ("disconnect", "destroy"):
                            # Fully remove client entry on explicit disconnect/destroy
                            try:
                                self._bridge.send_state(0.0, 0.0, 0, 0, 0)
                            except Exception:
                                pass
                            self._client = None
                            self._emit_clients()
                            LOG.log(f"⏹️ {t.title()}: client removed")
                        else:
                            self._disconnect(t.title())
                    continue

                # Lock to first client
                if not self._accepts(addr): 
                    continue
                if not self._client:
                    self._lock_to(addr)

                # Telemetry packets
                if not isinstance(obj, dict) or obj.get("sig") != "WHEEL1":
                    # Not telemetry: just refresh activity
                    self._client.last_rx_ms = now_ms
                    self._client.neutral_sent = False
                    if self._client.state != "active":
                        self._client.state = "active"; self._emit_clients()
                    continue

                axis = obj.get("axis") or {}
                buttons = obj.get("buttons") or {}

                def to_float(x, d=0.0):
                    try:
                        if isinstance(x, (int,float)): return float(x)
                        if isinstance(x, str): return float(x.strip())
                    except Exception:
                        return float(d)
                def to_int(x, d=0):
                    try: return int(float(x))
                    except Exception: return int(d)

                x_raw    = to_float(axis.get("steering_x", 0.0))
                throttle = to_float(axis.get("throttle",   0.0))
                brake    = to_float(axis.get("brake",      0.0))
                latG     = to_float(axis.get("latG",       0.0))
                ls_x     = to_float(axis.get("ls_x",       0.0))
                ls_y     = to_float(axis.get("ls_y",       0.0))
                seq      = to_int(obj.get("seq", 0))

                # Buttons map → bools
                names = ("A","B","X","Y","LB","RB","Start","Back","DPadUp","DPadDown","DPadLeft","DPadRight")
                btns: Dict[str,bool] = {}
                for n in names:
                    v = buttons.get(n, False)
                    if isinstance(v, bool): btns[n] = v
                    elif isinstance(v,(int,float)): btns[n] = (v != 0)
                    elif isinstance(v,str): btns[n] = v.strip().lower() in ("1","true","on","yes","down","pressed")
                    else: btns[n] = False

                # Update activity
                self._client.last_rx_ms = now_ms
                self._client.neutral_sent = False
                if self._client.state != "active":
                    self._client.state = "active"; self._emit_clients()

                # Shape steering and prefer DPAD/LS-x if provided
                x_proc = self._apply_filters(x_raw)
                use_lx = ls_x if abs(ls_x) > 1e-6 else x_proc
                if self._freeze_steer:
                    use_lx = 0.0
                use_ly = -ls_y  # invert Y (DIRT-like)
                rt = int(max(0.0, min(1.0, throttle)) * 255)
                lt = int(max(0.0, min(1.0, brake   )) * 255)

                # Compose bitmask in same order as the bridge expects
                mask = 0
                for i, n in enumerate(names):
                    if btns.get(n, False): mask |= (1 << i)

                # *** SEND TO BRIDGE EVERY TELEMETRY PACKET ***
                try:
                    self._bridge.send_state(use_lx, use_ly, rt, lt, mask)
                except Exception as e:
                    if now_ms - self._last_dbg_ms > 1000:
                        LOG.log(f"⚠️ bridge send error: {e}")
                        self._last_dbg_ms = now_ms

                # Real FFB if fresh (<300ms), else (optionally) synthesize from telemetry
                if now_ms - self._ffb_ms <= 300:
                    # Fresh real FFB from game
                    rumbleL = float(self._ffbL)
                    rumbleR = float(self._ffbR)
                    src = "real"
                    # No bed/mask/hybrid modifications — pass as-is
                else:
                    # No fresh real FFB
                    if self._ffb_passthrough_only or not self._audio:
                        rumbleL = 0.0
                        rumbleR = 0.0
                        src = "none"
                    else:
                        try:
                            feat = self._audio.get()
                            # Map audio features to rumble: use bodyL/bodyR and a dash of impact
                            bodyL = float(max(0.0, min(1.0, feat.get("bodyL", 0.0))))
                            bodyR = float(max(0.0, min(1.0, feat.get("bodyR", 0.0))))
                            imp   = float(max(0.0, min(1.0, feat.get("impact", 0.0))))
                            rumbleL = max(bodyL, 0.35 * imp)
                            rumbleR = max(bodyR, 0.45 * imp)
                            src = "audio"
                        except Exception:
                            rumbleL = 0.0; rumbleR = 0.0; src = "none"

                # Haptics expander (derive impact/trigger cues for phone)
                impact = 0.0; trigL_out = 0.0; trigR_out = 0.0
                if self._hx is not None:
                    # Compute dt in seconds (fall back to 1/120)
                    if self._hx_tprev is None:
                        dt = 1.0/120.0
                    else:
                        dt = max(1e-4, min(0.050, (now_ms - self._hx_tprev) / 1000.0))
                    self._hx_tprev = now_ms
                    # Use current rumble as input; route with current controls + memscan hints
                    ms = self._mem.get() if self._mem is not None else {}
                    brakePressed = (brake > 0.4) or bool(ms.get('absGate', 0.0) > 0.5)
                    throttlePressed = (throttle > 0.4)
                    slipGate = float(ms.get('slipGate', 0.0))
                    # Slightly bias right (slip) and impact channels if mem hints present
                    feat = self._hx.process(
                        dt, rumbleL, rumbleR,
                        lt=max(0.0, min(1.0, brake)),
                        rt=max(0.0, min(1.0, throttle)),
                        speed01=float(ms.get('speed01', 0.0)),
                        brakePressed=brakePressed,
                        throttlePressed=throttlePressed,
                        isOffroad=False,
                    )
                    impact = float(feat.get("impact", 0.0))
                    trigL_out = float(feat.get("trigL", 0.0))
                    trigR_out = float(feat.get("trigR", 0.0)) + 0.25 * slipGate

                # UI/overlay
                self.telemetry.emit(x_proc, throttle, brake, latG, seq, rumbleL, rumbleR, src)
                self.buttons.emit(btns)

                # Reply to phone (includes real rumble)
                reply = {
                    "ack": seq, "status":"ok",
                    "rumble": max(rumbleL, rumbleR),
                    "rumbleL": rumbleL, "rumbleR": rumbleR,
                    "impact": impact,
                    "trigL": trigL_out,
                    "trigR": trigR_out,
                    "center": max(-1.0, min(1.0, -x_proc)),
                    "centerDeg": 0.0,
                    "resistance": 1.0,
                    "note": "ok"
                }
                try:
                    sock.sendto(json.dumps(reply).encode("utf-8"), addr)
                except Exception:
                    pass

            except json.JSONDecodeError:
                continue
            except Exception:
                continue

        try: sock.close()
        except Exception: pass
        try: self._bridge.close()
        except Exception: pass
        LOG.log("🛑 UDP server stopped")

    # ----- audio tuning -----
    @QtCore.Slot(float)
    def set_audio_road_gain(self, v: float):
        if self._audio:
            try: self._audio.set_params(road_gain=float(v))
            except Exception: pass
            LOG.log(f"🎚️ Audio road gain = {v:.2f}")

    @QtCore.Slot(float)
    def set_audio_engine_gain(self, v: float):
        if self._audio:
            try: self._audio.set_params(engine_gain=float(v))
            except Exception: pass
            LOG.log(f"🎚️ Audio engine gain = {v:.2f}")

    @QtCore.Slot(float)
    def set_audio_impact_gain(self, v: float):
        if self._audio:
            try: self._audio.set_params(impact_gain=float(v))
            except Exception: pass
            LOG.log(f"🎚️ Audio impact gain = {v:.2f}")

    @QtCore.Slot(float)
    def set_audio_music_suppress(self, v: float):
        # 0..1
        v = max(0.0, min(1.0, float(v)))
        if self._audio:
            try: self._audio.set_params(music_suppress=v)
            except Exception: pass
            LOG.log(f"🎛️ Music suppression = {v:.2f}")

    @QtCore.Slot(int)
    def set_audio_device(self, idx: int):
        self._audio_dev = int(idx)
        if self._audio is None and AudioProbe and self._audio_enabled:
            try:
                self._audio = AudioProbe(device=(None if idx < 0 else idx))
            except Exception:
                self._audio = None
        elif self._audio is not None:
            try:
                ok = self._audio.switch_device(idx)
                LOG.log(f"🔊 Audio device switch to {idx}: {'OK' if ok else 'FAIL'}")
            except Exception as e:
                LOG.log(f"🔊 Audio device switch error: {e}")

    def _init_bridge(self):
        """Select and initialize input bridge with comprehensive platform support."""
        import os
        
        # Check platform
        system = platform.system().lower()
        
        # macOS: Try multiple DriverKit approaches, then cross-platform fallback
        if system == "darwin":  # macOS
            # First try: DKBridgeProc (external executable approach)
            try:
                if DKBridgeProc is not None:
                    self._bridge = DKBridgeProc()
                    self._bridge_name = "DriverKitBridge"
                    LOG.log(f"Using DriverKit bridge (external) for macOS")
                    return
            except Exception as e:
                LOG.log(f"DriverKit bridge (external) failed: {e}")
            
            # Second try: DriverKitGamepadBridge (direct IOKit approach)
            try:
                if DriverKitGamepadBridge is not None:
                    self._bridge = DriverKitGamepadBridge()
                    self._bridge_name = "DriverKit-macOS"
                    self._ffbL = 0.0; self._ffbR = 0.0; self._ffb_ms = 0
                    self._bridge.set_feedback_callback(self._on_ffb)
                    LOG.log(f"Using DriverKit bridge (direct) for macOS")
                    return
            except Exception as e:
                LOG.log(f"DriverKit bridge (direct) failed: {e}")
        
        # Windows: Try ViGEm, then HID, then vJoy
        if system == "windows":
            bridge_type = os.environ.get("WHEELER_BRIDGE", "vigem").strip().lower()
            target = os.environ.get("WHEELER_PAD", "x360").strip().lower()
            if target not in ("x360","ds4"): target = "x360"
            try:
                if bridge_type == "vigem":
                    self._bridge = ViGEmBridge(target=target)
                    self._bridge_name = f"ViGEmBridge-{target.upper()}"
                elif bridge_type == "hid":
                    self._bridge = HIDBridge()
                    self._bridge_name = "CustomHID"
                else:
                    raise RuntimeError("Unknown bridge type")
                self._ffbL = 0.0; self._ffbR = 0.0; self._ffb_ms = 0
                self._bridge.set_feedback_callback(self._on_ffb)
                return
            except Exception as e:
                LOG.log(f"{bridge_type} bridge failed: {e}")
            # Fall back to vJoy if available
            try:
                if VJoyBridge is None:
                    raise RuntimeError("vJoy bridge not available")
                self._bridge = VJoyBridge(device_id=1)
                self._bridge_name = "vJoy"
                # no FFB available via vJoy; keep passthrough-only off to allow synth fallback
                return
            except Exception as e:
                LOG.log(f"vJoy bridge failed: {e}")
        
        # macOS, Linux, or Windows fallback: Use cross-platform bridge
        try:
            if MacOSGamepadBridge is None:
                raise RuntimeError("Cross-platform bridge not available")
            # Our macOS cross-platform bridge does not take a device_id
            self._bridge = MacOSGamepadBridge()
            self._bridge_name = f"CrossPlatform-{system.title()}"
            self._ffbL = 0.0; self._ffbR = 0.0; self._ffb_ms = 0
            self._bridge.set_feedback_callback(self._on_ffb)
            LOG.log(f"Using cross-platform bridge for {system}")
            return
        except Exception as e:
            LOG.log(f"Cross-platform bridge failed: {e}")
        
        raise RuntimeError(
            f"No input bridge available for {system}. "
            f"On Windows: Install ViGEm (ViGEmBridge.exe) or vJoy + pyvjoy. "
            f"On macOS/Linux: Ensure pynput and evdev are installed."
        )
