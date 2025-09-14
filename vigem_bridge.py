# ---------- ViGEm Gamepad wrapper ----------
import logging

try:
    import vgamepad as vg
except Exception:
    vg = None

class XGamepad:
    def __init__(self):
        self.available = False
        self.pad = None
        self.vg = vg
        self.BTN = {}
        try:
            if vg is None:
                raise ImportError("vgamepad not available")
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
            logging.warning(f"⚠️ ViGEm unavailable: {e}")

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
            logging.warning(f"⚠️ ViGEm send error: {e}")

    def neutral(self):
        self.update(0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0)

    def close(self):
        try:
            if self.available and self.pad:
                self.neutral()
        except Exception:
            pass
# vigem_bridge.py
"""
Dedicated ViGEm bridge module for WheelerHost-V1.
Handles launching ViGEmBridge.exe, sending/receiving JSON, and gamepad emulation.
"""
import os
import subprocess
import threading
import json
import sys

class ViGEmBridge:
    def __init__(self, exe_path=None, target: str = "x360"):
        self._exe = exe_path or self._default_path()
        if not self._exe or not os.path.isfile(self._exe):
            raise RuntimeError("ViGEmBridge.exe not found. Pass exe_path or place it next to this script.")
        self._target = (target or "x360").lower().strip()
        self._p = None
        self._ffb_cb = None
        self._start()

    def _default_path(self):
        here = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(here, "ViGEmBridge.exe"),
            os.path.join(here, "ViGEmBridge", "bin", "Release", "net8.0", "ViGEmBridge.exe"),
            os.path.join(here, "ViGEmBridge", "bin", "Release", "net7.0", "ViGEmBridge.exe"),
            os.path.join(here, "ViGEmBridge", "bin", "Release", "net6.0", "ViGEmBridge.exe"),
        ]
        for p in candidates:
            if os.path.isfile(p): return p
        return None

    def _start(self):
        self._p = subprocess.Popen([
            self._exe
        ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Send target type
        self._send_json({"type": "target", "value": self._target})
        threading.Thread(target=self._read_stdout, daemon=True).start()

    def _send_json(self, obj):
        if self._p and self._p.stdin:
            self._p.stdin.write(json.dumps(obj) + "\n")
            self._p.stdin.flush()

    def send_state(self, lx, ly, rt, lt, buttons):
        self._send_json({
            "lx": lx,
            "ly": ly,
            "rt": rt,
            "lt": lt,
            "buttons": buttons
        })

    def set_feedback_callback(self, cb):
        """Register feedback callback.
        Expected signature: cb(left: float, right: float)
        """
        self._ffb_cb = cb

    def _read_stdout(self):
        while True:
            line = self._p.stdout.readline()
            if not line:
                break
            try:
                obj = json.loads(line)
                if obj.get("type") == "ffb" and self._ffb_cb:
                    # Normalize rumble payload to (L, R) floats in [0,1]
                    def _get(name, default=None):
                        return obj.get(name, default)
                    L = (
                        _get("L") or _get("l") or _get("left") or _get("rumbleL") or _get("low") or 0.0
                    )
                    R = (
                        _get("R") or _get("r") or _get("right") or _get("rumbleR") or _get("high") or 0.0
                    )
                    try:
                        Lf = float(L)
                        Rf = float(R)
                    except Exception:
                        # Some bridges may emit 0-65535; scale if ints are large
                        try:
                            Li = int(L)
                            Ri = int(R)
                            Lf = max(0.0, min(1.0, Li / 65535.0))
                            Rf = max(0.0, min(1.0, Ri / 65535.0))
                        except Exception:
                            Lf, Rf = 0.0, 0.0
                    try:
                        self._ffb_cb(Lf, Rf)
                    except Exception:
                        # Swallow to keep reader thread alive
                        pass
            except Exception:
                pass

    def close(self):
        if self._p:
            self._p.terminate()
            self._p = None
